"""
Over-calls kept rather than counted, and CC/MCC labels checked.

Two things underneath the auditor analytics rather than in them.

Over-calling is the restraint half of what this module measures — an auditor
who marks every line wrong knows nothing — and only the COUNT was ever stored,
so "which codes get wrongly flagged" had no answer at all.

CC/MCC is worse: `drg_impacting` on every planted error is computed from the
trainer's typed label, and the generator also weights which secondary to break
by it. A wrong label changes what gets planted AND how it is reported, and
nothing anywhere calls it an error.
"""
from models import CodeDescription

from tests.test_auditor_analytics import _run
from tests.test_auditor_api import allocate, library, make_batch  # noqa: F401


class TestOverCallsAreKept:
    def test_an_over_call_is_persisted_with_the_finding_behind_it(
            self, client, db, library):
        """
        Not just `over_calls: 3`. The section, the line and the value the
        auditor objected to are what make the number answerable.
        """
        from tests.test_auditor_api import perfect_work, truth_map
        batch_id = make_batch(client, charts_per=4)
        token = allocate(client, batch_id)["access_codes"][0]["token"]
        payload = client.get(f"/auditor/sessions/by-token/{token}").json()
        truth = truth_map(client, batch_id)
        work = perfect_work(payload, truth)
        # One extra finding on top of a perfect audit: nothing was introduced
        # on that line, which is exactly what an over-call is.
        work["charts"][0]["findings"].append(
            {"section": "SDx", "action": "Revise", "field": "code", "line": 0,
             "claim_value": "ZZ9.99", "correct_value": "QQ0.00"})
        work["charts"][0]["section_verdicts"]["SDx"] = "needs_changes"
        r = client.post(f"/auditor/sessions/{payload['session_id']}/submit",
                        json=work)
        assert r.status_code == 200, r.text

        from models import AuditResult
        rows = db.query(AuditResult).filter(AuditResult.over_calls > 0).all()
        assert rows, "no over-call was recorded"
        over = [e for row in rows for e in (row.feedback or [])
                if e.get("outcome") == "over_call"]
        assert over, "the over-call was counted but the finding was discarded"
        assert over[0]["finding"]["section"] == "SDx"

    def test_detection_analytics_does_not_count_an_over_call_as_a_planting(
            self, client, db, library):
        """
        The trap this guard exists for. feedback now holds two kinds of entry,
        and an over-call has no "planting" — read without the guard it became a
        planting of kind "unknown", inflating total_plantings and depressing
        every detection rate on the tab.
        """
        batch_id = make_batch(client, charts_per=4)
        _run(client, batch_id, find_everything=False)
        body = client.get("/auditor/analytics/detection").json()
        # Over-calls must not appear as plantings of an "unknown" kind, and the
        # planting total must still reconcile with the kinds it is made of.
        assert all(k["key"] != "unknown" for k in body["by_kind"])
        assert sum(k["planted"] for k in body["by_kind"]) == body["total_plantings"]

    def test_the_review_screen_still_reads_a_chart_with_over_calls(
            self, client, db, library):
        """The payload the trainer review renders must stay well formed."""
        from tests.test_auditor_api import allocate as _alloc
        batch_id = make_batch(client, charts_per=4)
        token = _alloc(client, batch_id)["access_codes"][0]["token"]
        payload = client.get(f"/auditor/sessions/by-token/{token}").json()
        _run(client, batch_id, find_everything=False)
        r = client.get(f"/auditor/sessions/{payload['session_id']}/review")
        assert r.status_code == 200, r.text
        # Every outcome entry is one of the two shapes the screen knows how to
        # draw: a matched planting, or an over-call carrying its finding.
        for chart in (r.json().get("charts") or []):
            for entry in (chart.get("outcomes") or []):
                assert entry.get("planting") or entry.get("finding"), entry


class TestCcMccLabelsAreChecked:
    """
    Surfaced where a trainer authors audit errors for a chart, because that is
    where the label's consequences are decided.
    """

    def _chart_with_key(self, client, db, ccmcc):
        from conftest import make_chart
        from models import AnswerKey, Specialty
        chart = make_chart(db, specialty="IP-DRG")
        db.add(AnswerKey(chart_id=chart.id, specialty=Specialty.IP_DRG,
                         pdx_code="J18.9", pdx_poa="Y",
                         sdx=[{"code": "E11.9", "poa": "Y", "ccmcc": ccmcc}],
                         pcs=[], cpt=[], entered_by="t"))
        db.add_all([
            CodeDescription(code="E119", code_system="ICD10CM",
                            description="Type 2 diabetes without complications",
                            cc_mcc_status=None, is_billable=True),
            # At least one code WITH a severity, or the checker correctly
            # reports "not checked" — an appendix that was never loaded cannot
            # contradict anything.
            CodeDescription(code="A419", code_system="ICD10CM",
                            description="Sepsis", cc_mcc_status="MCC",
                            is_billable=True),
        ])
        db.commit()
        return chart

    def test_a_claimed_severity_the_manual_does_not_give_is_flagged(
            self, client, db):
        chart = self._chart_with_key(client, db, "MCC")
        body = client.get(f"/auditor/keys/chart/{chart.id}").json()
        assert body["ccmcc_conflicts"]
        assert body["ccmcc_conflicts"][0]["code"] == "E119"
        assert body["ccmcc_conflicts"][0]["claimed"] == "MCC"
        assert body["ccmcc_conflicts"][0]["published"] == "neither"

    def test_a_correct_label_is_not_flagged(self, client, db):
        chart = self._chart_with_key(client, db, "-")
        assert client.get(f"/auditor/keys/chart/{chart.id}").json()["ccmcc_conflicts"] == []

    def test_without_the_code_sets_it_reports_not_checked(self, client, db):
        """None, not [] — silence must not read as approval."""
        from conftest import make_chart
        from models import AnswerKey, Specialty
        chart = make_chart(db, specialty="IP-DRG")
        db.add(AnswerKey(chart_id=chart.id, specialty=Specialty.IP_DRG,
                         pdx_code="J18.9", pdx_poa="Y",
                         sdx=[{"code": "E11.9", "poa": "Y", "ccmcc": "MCC"}],
                         pcs=[], cpt=[], entered_by="t"))
        db.commit()
        assert client.get(f"/auditor/keys/chart/{chart.id}").json()["ccmcc_conflicts"] is None

    def test_a_chart_with_no_answer_key_does_not_break(self, client, db):
        from conftest import make_chart
        chart = make_chart(db, specialty="IP-DRG")
        db.commit()
        body = client.get(f"/auditor/keys/chart/{chart.id}").json()
        assert body["has_answer_key"] is False
