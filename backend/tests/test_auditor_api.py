"""
The auditor API end to end: author, allocate, audit, score.

The engines are proved in isolation elsewhere. What this file exists for is the
wiring between them, and three rules that live only at this layer:

  * The auditor is never told a chart's type. Not while working, not in their
    results. Charts recycle, so a chart labelled "clean" is an answer key the
    next time they meet it.
  * A claim is frozen when the auditor opens it. A trainer may reroll before
    that and not after — otherwise the question changes after the answer.
  * Every section needs a verdict before submission, which turns a blank chart
    into an explicit claim rather than an absence.
"""
import pytest

from models import (
    AnswerKey, AuditAssignment, AuditSource, Chart, ChartStatus, Difficulty,
    Specialty,
)

PASS = "test-passphrase"


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def library(db):
    """A pool of inpatient charts, each with a rich answer key."""
    charts = []
    for i in range(8):
        c = Chart(chart_number=f"AUD{i:03d}", specialty=Specialty.IP_DRG,
                  category="Cardiology", difficulty=Difficulty.INTERMEDIATE,
                  status=ChartStatus.ACTIVE, uploaded_by="t")
        db.add(c)
        db.flush()
        db.add(AnswerKey(
            chart_id=c.id, specialty=Specialty.IP_DRG,
            pdx_code="J18.9", pdx_poa="Y",
            sdx=[{"code": f"E11.{j}", "poa": "Y",
                  "ccmcc": "CC" if j % 2 == 0 else "-"} for j in range(8)],
            pcs=[{"code": f"0DTJ{j}ZZ"} for j in range(3)],
            cpt=[], entered_by="t"))
        charts.append(c)
    db.commit()
    return charts


def make_batch(client, auditors=("Asha R",), charts_per=4, **kw):
    body = {"name": "Audit wave", "specialty": "IP-DRG",
            "charts_per_auditor": charts_per, "created_by": "Trainer",
            "auditors": [{"name": n, "emp_id": f"E{i}"}
                         for i, n in enumerate(auditors)]}
    body.update(kw)
    r = client.post("/auditor/batches", json=body)
    assert r.status_code == 200, r.text
    return r.json()["batch_id"]


def allocate(client, batch_id, **kw):
    r = client.post(f"/auditor/batches/{batch_id}/run-allocation",
                    json={"run_by": "Trainer", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def perfect_work(session_payload, ground_truth_by_chart, verdicts_only=False):
    """Build a submission that finds everything, from the trainer-side truth."""
    charts = []
    for c in session_payload["charts"]:
        sections = [s["key"] for s in session_payload["form"]["sections"]]
        gt = ground_truth_by_chart.get(c["chart_id"], [])
        findings = []
        if not verdicts_only:
            for p in gt:
                f = {"section": p["section"], "action": p["action"]}
                if p["action"] == "Add":
                    f["correct_value"] = p["correct_value"]
                elif p["action"] == "Delete":
                    f["line"] = p["line"]
                    f["claim_value"] = p["claim_value"]
                else:
                    f["line"] = p["line"]
                    f["field"] = p.get("field", "code")
                    f["correct_value"] = p["correct_value"]
                findings.append(f)
        touched = {f["section"] for f in findings}
        charts.append({
            "chart_id": c["chart_id"],
            "section_verdicts": {s: ("needs_changes" if s in touched else "no_changes")
                                 for s in sections},
            "findings": findings,
        })
    return {"charts": charts}


def truth_map(client, batch_id):
    r = client.get(f"/auditor/batches/{batch_id}/plantings")
    assert r.status_code == 200, r.text
    return {p["chart_id"]: p["ground_truth"] for p in r.json()["plantings"]}


# ── the whole flow ───────────────────────────────────────────────────────────

class TestEndToEnd:

    def test_a_perfect_audit_scores_100(self, client, db, library):
        batch_id = make_batch(client)
        alloc = allocate(client, batch_id)
        token = alloc["access_codes"][0]["token"]

        opened = client.get(f"/auditor/sessions/by-token/{token}")
        assert opened.status_code == 200, opened.text
        payload = opened.json()

        work = perfect_work(payload, truth_map(client, batch_id))
        r = client.post(f"/auditor/sessions/{payload['session_id']}/submit", json=work)
        assert r.status_code == 200, r.text
        summary = r.json()["summary"]
        assert summary["audit_accuracy"] == 100.0
        assert summary["over_calls"] == 0

    def test_an_auditor_who_records_nothing_fails_the_opportunity_charts(
            self, client, db, library):
        batch_id = make_batch(client)
        alloc = allocate(client, batch_id)
        token = alloc["access_codes"][0]["token"]
        payload = client.get(f"/auditor/sessions/by-token/{token}").json()

        work = perfect_work(payload, truth_map(client, batch_id), verdicts_only=True)
        r = client.post(f"/auditor/sessions/{payload['session_id']}/submit", json=work)
        assert r.status_code == 200, r.text
        summary = r.json()["summary"]
        assert summary["clean_accuracy"] == 100.0
        assert summary["opportunity_accuracy"] == 0.0
        # Inaction is not invention — nothing was over-called.
        assert summary["over_calls"] == 0

    def test_the_clean_quota_is_honoured_and_rounds_down(self, client, db, library):
        batch_id = make_batch(client, charts_per=5)
        allocate(client, batch_id)
        plantings = client.get(f"/auditor/batches/{batch_id}/plantings").json()["plantings"]
        clean = [p for p in plantings if p["source"] == "Clean"]
        assert len(clean) == 2                      # 5 * 50% floors to 2
        assert len(plantings) - len(clean) == 3     # always an opportunity chart

    def test_two_auditors_on_one_chart_see_identical_errors(self, client, db, library):
        """
        The seed comes from (chart, cycle) and not the auditor, which is the
        only way their answers on a shared chart can be compared.
        """
        batch_id = make_batch(client, auditors=("Asha R", "Bo T"), charts_per=8)
        allocate(client, batch_id)
        plantings = client.get(f"/auditor/batches/{batch_id}/plantings").json()["plantings"]

        by_chart = {}
        for p in plantings:
            if p["source"] != "Auto":
                continue
            by_chart.setdefault(p["chart_id"], []).append(p["ground_truth"])
        shared = [v for v in by_chart.values() if len(v) > 1]
        assert shared, "expected at least one chart drawn by both auditors"
        for versions in shared:
            assert all(v == versions[0] for v in versions)


# ── what the auditor is allowed to know ──────────────────────────────────────

class TestAuditorNeverLearnsChartType:

    def test_the_open_payload_never_names_the_chart_type(self, client, db, library):
        batch_id = make_batch(client)
        token = allocate(client, batch_id)["access_codes"][0]["token"]
        body = client.get(f"/auditor/sessions/by-token/{token}").text.lower()
        for word in ("clean", "opportunity", "planting", "ground_truth", "source"):
            assert word not in body, f"{word!r} leaked to the auditor"

    def test_results_returned_to_the_auditor_never_name_it_either(
            self, client, db, library):
        """
        Charts recycle through cycles. Telling someone a chart was clean hands
        them the answer if they meet it again.
        """
        batch_id = make_batch(client)
        token = allocate(client, batch_id)["access_codes"][0]["token"]
        payload = client.get(f"/auditor/sessions/by-token/{token}").json()
        work = perfect_work(payload, truth_map(client, batch_id))
        body = client.post(f"/auditor/sessions/{payload['session_id']}/submit",
                           json=work).text.lower()
        assert "is_clean" not in body
        assert '"chart_type"' not in body
        assert '"source"' not in body

    def test_a_clean_chart_renders_exactly_like_a_planted_one(self, client, db, library):
        """
        Structure comes from the specialty and nothing else. A section drawn
        differently because nothing was mutated is a tell.
        """
        batch_id = make_batch(client, charts_per=6)
        token = allocate(client, batch_id)["access_codes"][0]["token"]
        payload = client.get(f"/auditor/sessions/by-token/{token}").json()
        shapes = {tuple(sorted(c["claim"].keys())) for c in payload["charts"]}
        assert len(shapes) == 1

    def test_the_trainer_view_does_name_the_type(self, client, db, library):
        """It is trainer vocabulary — this is the one place it belongs."""
        batch_id = make_batch(client)
        alloc = allocate(client, batch_id)
        token = alloc["access_codes"][0]["token"]
        payload = client.get(f"/auditor/sessions/by-token/{token}").json()
        client.post(f"/auditor/sessions/{payload['session_id']}/submit",
                    json=perfect_work(payload, truth_map(client, batch_id)))

        review = client.get(f"/auditor/sessions/{payload['session_id']}/review")
        assert review.status_code == 200, review.text
        types = {c["chart_type"] for c in review.json()["charts"]}
        assert types <= {"clean", "opportunity"} and types


# ── section verdicts ─────────────────────────────────────────────────────────

class TestSectionVerdicts:

    def test_submission_is_refused_without_a_verdict_on_every_section(
            self, client, db, library):
        batch_id = make_batch(client)
        token = allocate(client, batch_id)["access_codes"][0]["token"]
        payload = client.get(f"/auditor/sessions/by-token/{token}").json()
        r = client.post(f"/auditor/sessions/{payload['session_id']}/submit",
                        json={"charts": [{"chart_id": c["chart_id"],
                                          "section_verdicts": {"PDx": "no_changes"}}
                                         for c in payload["charts"]]})
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "verdict" in detail["message"]
        assert set(detail["charts"][0]["missing_sections"]) == {"SDx", "PCS"}

    def test_the_sections_required_follow_the_specialty(self, client, db):
        r = client.get("/auditor/form-spec")
        assert r.status_code == 200, r.text
        by_specialty = {s["specialty"]: [x["key"] for x in s["sections"]]
                        for s in r.json()["specialties"]}
        assert by_specialty["IP-DRG"] == ["PDx", "SDx", "PCS"]
        assert by_specialty["Ancillary"] == ["PDx", "SDx"]
        assert "CPT" in by_specialty["Surgery"]

    def test_pdx_offers_only_revise(self, client, db):
        spec = client.get("/auditor/form-spec").json()["specialties"][0]
        pdx = next(s for s in spec["sections"] if s["key"] == "PDx")
        assert pdx["actions"] == ["Revise"]


# ── freezing ─────────────────────────────────────────────────────────────────

class TestFreezing:

    def test_a_trainer_can_reroll_before_the_auditor_opens_it(self, client, db, library):
        batch_id = make_batch(client)
        allocate(client, batch_id)
        planted = [p for p in client.get(
            f"/auditor/batches/{batch_id}/plantings").json()["plantings"]
            if p["source"] == "Auto"]
        target = planted[0]
        before = target["ground_truth"]

        r = client.post(f"/auditor/assignments/{target['assignment_id']}/regenerate",
                        json={"run_by": "Trainer"})
        assert r.status_code == 200, r.text
        after = next(p for p in client.get(
            f"/auditor/batches/{batch_id}/plantings").json()["plantings"]
            if p["assignment_id"] == target["assignment_id"])["ground_truth"]
        assert after != before

    def test_a_reroll_is_refused_once_the_auditor_has_opened_it(
            self, client, db, library):
        batch_id = make_batch(client)
        token = allocate(client, batch_id)["access_codes"][0]["token"]
        client.get(f"/auditor/sessions/by-token/{token}")      # opens every chart

        p = client.get(f"/auditor/batches/{batch_id}/plantings").json()["plantings"][0]
        r = client.post(f"/auditor/assignments/{p['assignment_id']}/regenerate",
                        json={"run_by": "Trainer"})
        assert r.status_code == 409
        assert "already opened" in r.json()["detail"]

    def test_editing_a_key_set_does_not_change_a_live_assignment(
            self, client, db, library):
        """
        The freeze in one sentence: improving the library mid-batch must never
        disturb work in flight.
        """
        chart = library[0]
        made = client.post(f"/auditor/keys/chart/{chart.id}", json={
            "name": "Curated", "authored_by": "T", "passphrase": PASS,
            "always_plant": True,
            "mutations": [{"section": "SDx", "action": "Add", "correct_value": "E11.2"}]})
        assert made.status_code == 200, made.text
        set_id = made.json()["id"]

        batch_id = make_batch(client, charts_per=8)
        allocate(client, batch_id)
        before = [p for p in client.get(
            f"/auditor/batches/{batch_id}/plantings").json()["plantings"]
            if p["chart_id"] == chart.id][0]["ground_truth"]

        client.put(f"/auditor/keys/{set_id}", json={
            "name": "Curated", "authored_by": "T", "passphrase": PASS,
            "mutations": [{"section": "SDx", "action": "Add", "correct_value": "E11.6"}]})

        after = [p for p in client.get(
            f"/auditor/batches/{batch_id}/plantings").json()["plantings"]
            if p["chart_id"] == chart.id][0]["ground_truth"]
        assert after == before


# ── the key library ──────────────────────────────────────────────────────────

class TestKeySets:

    def test_authoring_a_set_and_previewing_the_claim_it_builds(self, client, db, library):
        chart = library[0]
        r = client.post(f"/auditor/keys/chart/{chart.id}/preview", json={
            "mutations": [{"section": "SDx", "action": "Add", "correct_value": "E11.3"},
                          {"section": "SDx", "action": "Delete", "line": 0,
                           "claim_value": "I10"}]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "E11.3" not in [s["code"] for s in body["claim"]["sdx"]]
        assert body["claim"]["sdx"][0]["code"] == "I10"
        assert body["planting_count"] == 2

    def test_a_planting_naming_a_code_not_on_the_key_is_dropped_with_a_warning(
            self, client, db, library):
        r = client.post(f"/auditor/keys/chart/{library[0].id}/preview", json={
            "mutations": [{"section": "SDx", "action": "Add",
                           "correct_value": "NOTHERE"}]})
        assert r.json()["planting_count"] == 0
        assert "not on this chart's answer key" in r.json()["warning"]

    def test_pdx_cannot_be_added_or_deleted(self, client, db, library):
        """It can be wrong; it cannot be absent."""
        for action in ("Add", "Delete"):
            r = client.post(f"/auditor/keys/chart/{library[0].id}", json={
                "name": "x", "authored_by": "T", "passphrase": PASS,
                "mutations": [{"section": "PDx", "action": action,
                               "correct_value": "J18.9", "claim_value": "J18.9"}]})
            assert r.status_code == 400
            assert "only be revised" in r.json()["detail"]

    def test_authoring_needs_the_passphrase(self, client, db, library):
        r = client.post(f"/auditor/keys/chart/{library[0].id}", json={
            "name": "x", "authored_by": "T", "passphrase": "wrong", "mutations": []})
        assert r.status_code == 403

    def test_a_chart_with_no_answer_key_cannot_be_curated(self, client, db):
        c = Chart(chart_number="NOKEY1", specialty=Specialty.IP_DRG, category="x",
                  difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
                  uploaded_by="t")
        db.add(c)
        db.commit()
        r = client.post(f"/auditor/keys/chart/{c.id}", json={
            "name": "x", "authored_by": "T", "passphrase": PASS, "mutations": []})
        assert r.status_code == 400
        assert "no answer key" in r.json()["detail"]

    def test_a_zero_mutation_set_with_a_query_is_a_curated_clean_chart(
            self, client, db, library):
        r = client.post(f"/auditor/keys/chart/{library[0].id}", json={
            "name": "Query only", "authored_by": "T", "passphrase": PASS,
            "mutations": [], "query_expected": True,
            "query_rationale": "Sepsis without organ dysfunction"})
        assert r.status_code == 200, r.text
        assert r.json()["planting_count"] == 0
        assert r.json()["query_expected"] is True


# ── scope ────────────────────────────────────────────────────────────────────

class TestScope:

    @pytest.mark.parametrize("specialty", ["Edits", "Denials", "E/M"])
    def test_rubric_and_em_specialties_are_refused(self, client, db, specialty):
        """
        Edits & Denials have no coded key to plant errors in; E/M needs its own
        audit design. Both are refused with the reason, not silently accepted.
        """
        r = client.post("/auditor/batches", json={
            "name": "x", "specialty": specialty, "created_by": "T",
            "auditors": [{"name": "A", "emp_id": "E1"}]})
        assert r.status_code == 400
        assert "cannot be audited" in r.json()["detail"]

    def test_a_chart_with_no_answer_key_is_never_allocated(self, client, db, library):
        """
        There is no truth to plant errors in, so the auditor could only ever be
        measured on restraint.
        """
        db.add(Chart(chart_number="AUDNOKEY", specialty=Specialty.IP_DRG,
                     category="Cardiology", difficulty=Difficulty.INTERMEDIATE,
                     status=ChartStatus.ACTIVE, uploaded_by="t"))
        db.commit()
        batch_id = make_batch(client, charts_per=9)
        allocate(client, batch_id)
        numbers = {p["chart_number"] for p in client.get(
            f"/auditor/batches/{batch_id}/plantings").json()["plantings"]}
        assert "AUDNOKEY" not in numbers


# ── config ───────────────────────────────────────────────────────────────────

class TestConfig:

    def test_defaults_are_the_agreed_numbers(self, client, db):
        c = client.get("/auditor/config").json()
        assert (c["add_weight"], c["revise_weight"], c["delete_weight"]) == (40, 40, 20)
        assert c["over_call_revenue_pct"] == 20
        assert c["query_missed_pct"] == c["query_unnecessary_pct"] == 20
        assert c["pass_threshold"] == 90
        assert c["mix_total"] == 100

    def test_component_weights_must_total_100(self, client, db):
        r = client.put("/auditor/config", json={
            "add_weight": 50, "revise_weight": 40, "delete_weight": 20,
            "updated_by": "T", "passphrase": PASS})
        assert r.status_code == 400
        assert "must total 100" in r.json()["detail"]

    def test_the_mutation_mix_must_total_100(self, client, db):
        r = client.put("/auditor/config", json={
            "mix": {"mix_omit_sdx": 90}, "updated_by": "T", "passphrase": PASS})
        assert r.status_code == 400
        assert "total 100" in r.json()["detail"]

    def test_config_changes_need_the_passphrase(self, client, db):
        r = client.put("/auditor/config", json={
            "pass_threshold": 50, "updated_by": "T", "passphrase": "nope"})
        assert r.status_code == 403
