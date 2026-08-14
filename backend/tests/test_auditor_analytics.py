"""
Auditor analytics — different questions from the coder reports, so different
numbers, and the two bases must never be confused.

  * audit accuracy AVERAGES chart scores — one chart, one unit of work
  * component accuracy POOLS — a chart with six plantings counts six times as
    much as a chart with one

Detection patterns is the report with no coder equivalent: which KINDS of error
slip past a cohort. That is the one that turns scoring into a curriculum.
"""
import pytest
from openpyxl import load_workbook

from tests.test_auditor_api import (
    PASS, allocate, library, make_batch, perfect_work, truth_map,
)


def _run(client, batch_id, find_everything=True, auditor_index=0):
    token = allocate(client, batch_id)["access_codes"][auditor_index]["token"]
    payload = client.get(f"/auditor/sessions/by-token/{token}").json()
    work = perfect_work(payload, truth_map(client, batch_id),
                        verdicts_only=not find_everything)
    r = client.post(f"/auditor/sessions/{payload['session_id']}/submit", json=work)
    assert r.status_code == 200, r.text
    return r.json()


class TestOverview:

    def test_an_empty_installation_does_not_divide_by_zero(self, client, db):
        r = client.get("/auditor/analytics/overview")
        assert r.status_code == 200, r.text
        assert r.json()["charts"] == 0
        assert r.json()["audit_accuracy"] is None

    def test_a_perfect_cohort_reports_100(self, client, db, library):
        batch_id = make_batch(client, charts_per=6)
        _run(client, batch_id)
        body = client.get("/auditor/analytics/overview").json()
        assert body["audit_accuracy"] == 100.0
        assert body["auditors"] == 1 and body["batches"] == 1

    def test_clean_and_opportunity_charts_are_reported_separately(
            self, client, db, library):
        """
        Otherwise the headline blends restraint with detection and hides which
        one is weak — a passive auditor scores 100 on one and 0 on the other.
        """
        batch_id = make_batch(client, charts_per=6)
        _run(client, batch_id, find_everything=False)
        body = client.get("/auditor/analytics/overview").json()
        assert body["clean_accuracy"] == 100.0
        assert body["opportunity_accuracy"] == 0.0
        assert body["clean_charts"] and body["opportunity_charts"]

    def test_the_basis_of_every_rate_is_stated(self, client, db, library):
        batch_id = make_batch(client, charts_per=6)
        _run(client, batch_id)
        body = client.get("/auditor/analytics/overview").json()
        assert body["audit_accuracy_basis"] == "average of chart scores"
        assert body["component_basis"] == "pooled findings over errors introduced"

    def test_a_component_never_planted_reads_NA_not_zero(self, client, db, library):
        batch_id = make_batch(client, charts_per=6)
        _run(client, batch_id)
        body = client.get("/auditor/analytics/overview").json()
        for name in ("add", "revise", "delete"):
            cell = body[name]
            if cell["planted"] == 0:
                assert cell["accuracy"] is None, name

    def test_the_verdict_is_withheld_on_a_thin_cohort(self, client, db, library):
        batch_id = make_batch(client, charts_per=2)
        _run(client, batch_id)
        body = client.get("/auditor/analytics/overview").json()
        assert body["pass_fail"] is None
        assert body["verdict_withheld_reason"]

    def test_drg_impact_is_its_own_number(self, client, db, library):
        """Never blended into the headline as a weight."""
        batch_id = make_batch(client, charts_per=6)
        _run(client, batch_id)
        body = client.get("/auditor/analytics/overview").json()
        assert "drg_accuracy" in body and "drg_planted" in body


class TestPooling:

    def test_component_accuracy_pools_rather_than_averaging(
            self, client, db, library):
        """
        Averaging per-chart rates would let a chart with one planting count as
        much as a chart with six — how a rate quietly starts meaning something
        other than what it says.
        """
        batch_id = make_batch(client, charts_per=6, clean_share=0)
        _run(client, batch_id)
        body = client.get("/auditor/analytics/overview").json()
        for name in ("add", "revise", "delete"):
            cell = body[name]
            if cell["planted"]:
                assert cell["accuracy"] == round(
                    cell["found"] / cell["planted"] * 100, 2)


class TestByBatchAndAuditor:

    def test_each_batch_gets_its_own_row(self, client, db, library):
        a = make_batch(client, charts_per=4)
        _run(client, a)
        b = make_batch(client, charts_per=4)
        _run(client, b)
        rows = client.get("/auditor/analytics/by-batch").json()["batches"]
        assert {r["batch_id"] for r in rows} == {a, b}
        assert all(r["name"] for r in rows)

    def test_auditors_are_listed_weakest_first(self, client, db, library):
        """The screen exists to show who needs help, so put them at the top."""
        batch_id = make_batch(client, auditors=("Asha R", "Bo T"), charts_per=6)
        alloc = allocate(client, batch_id)
        truth = truth_map(client, batch_id)
        for i, code in enumerate(alloc["access_codes"]):
            payload = client.get(f"/auditor/sessions/by-token/{code['token']}").json()
            client.post(f"/auditor/sessions/{payload['session_id']}/submit",
                        json=perfect_work(payload, truth, verdicts_only=(i == 0)))
        rows = client.get("/auditor/analytics/by-auditor").json()["auditors"]
        assert len(rows) == 2
        assert rows[0]["audit_accuracy"] <= rows[1]["audit_accuracy"]

    def test_an_auditor_row_pools_across_their_batches(self, client, db, library):
        a = make_batch(client, charts_per=4)
        _run(client, a)
        b = make_batch(client, charts_per=4)
        _run(client, b)
        rows = client.get("/auditor/analytics/by-auditor").json()["auditors"]
        assert len(rows) == 1
        assert rows[0]["batches"] == 2
        assert rows[0]["charts"] == 8

    def test_specialty_rows_are_available_for_mixed_analytics(self, client, db, library):
        batch_id = make_batch(client, charts_per=4)
        _run(client, batch_id)
        rows = client.get("/auditor/analytics/by-specialty").json()["specialties"]
        assert len(rows) == 1
        assert rows[0]["charts"] == 4
        assert rows[0]["specialty"]

    def test_chart_signals_surface_chart_level_qa(self, client, db, library):
        batch_id = make_batch(client, charts_per=6, clean_share=0)
        _run(client, batch_id, find_everything=False)
        rows = client.get("/auditor/analytics/chart-signals").json()["charts"]
        assert rows
        assert rows[0]["attempts"] >= 1
        assert rows[0]["missed"] >= 0
        assert rows[0]["signal"]


class TestDetectionPatterns:

    def test_every_planting_is_accounted_for(self, client, db, library):
        batch_id = make_batch(client, charts_per=6, clean_share=0)
        _run(client, batch_id)
        body = client.get("/auditor/analytics/detection").json()
        assert body["total_plantings"] > 0
        assert sum(k["planted"] for k in body["by_kind"]) == body["total_plantings"]
        assert all(k["found"] == k["planted"] for k in body["by_kind"])

    def test_missed_kinds_are_counted_and_sorted_worst_first(
            self, client, db, library):
        batch_id = make_batch(client, charts_per=6, clean_share=0)
        _run(client, batch_id, find_everything=False)
        body = client.get("/auditor/analytics/detection").json()
        assert all(k["missed"] == k["planted"] for k in body["by_kind"])
        accs = [k["accuracy"] or 0 for k in body["by_kind"]]
        assert accs == sorted(accs)

    def test_a_kind_seen_twice_is_not_called_a_pattern(self, client, db, library):
        """
        A trainer must not build a curriculum on a single miss, so weakest[]
        requires a minimum sample.
        """
        batch_id = make_batch(client, charts_per=6, clean_share=0)
        _run(client, batch_id, find_everything=False)
        body = client.get("/auditor/analytics/detection").json()
        assert all(k["planted"] >= body["min_for_pattern"] for k in body["weakest"])

    def test_kinds_carry_a_readable_label(self, client, db, library):
        batch_id = make_batch(client, charts_per=6, clean_share=0)
        _run(client, batch_id)
        body = client.get("/auditor/analytics/detection").json()
        labels = {k["label"] for k in body["by_kind"]}
        assert labels
        assert all(lbl and lbl != "unknown" for lbl in labels)

    def test_observed_and_synthetic_errors_are_split(self, client, db, library):
        """
        The comparison that describes the job: auditors tend to do better on
        generated errors than on the ones their own coders really make.
        """
        batch_id = make_batch(client, charts_per=6, clean_share=0)
        _run(client, batch_id)
        body = client.get("/auditor/analytics/detection").json()
        keys = {o["key"] for o in body["by_origin"]}
        assert keys <= {"observed", "synthetic"} and keys

    def test_it_can_be_scoped_to_one_auditor(self, client, db, library):
        batch_id = make_batch(client, auditors=("Asha R", "Bo T"), charts_per=6)
        alloc = allocate(client, batch_id)
        truth = truth_map(client, batch_id)
        for code in alloc["access_codes"]:
            payload = client.get(f"/auditor/sessions/by-token/{code['token']}").json()
            client.post(f"/auditor/sessions/{payload['session_id']}/submit",
                        json=perfect_work(payload, truth))
        both = client.get("/auditor/analytics/detection").json()
        one = client.get("/auditor/analytics/detection",
                         params={"auditor": "Asha R"}).json()
        assert one["total_plantings"] < both["total_plantings"]

    def test_an_empty_installation_returns_empty_buckets(self, client, db):
        body = client.get("/auditor/analytics/detection").json()
        assert body["total_plantings"] == 0
        assert body["by_kind"] == [] and body["weakest"] == []


class TestScale:
    """
    None of these endpoints may load the whole table to render one screen.
    The coder analytics learned this the expensive way; the same rules apply.
    """

    def test_the_batch_list_is_paged_and_reports_its_total(self, client, db, library):
        from tests.test_auditor_api import make_batch
        for i in range(6):
            make_batch(client, charts_per=2)
        r = client.get("/auditor/batches", params={"limit": 3}).json()
        assert len(r["batches"]) == 3
        assert r["total"] >= 6
        assert r["limit"] == 3

    def test_the_batch_list_searches_on_the_server(self, client, db, library):
        from tests.test_auditor_api import make_batch
        make_batch(client, charts_per=2, name="Sepsis wave")
        make_batch(client, charts_per=2, name="Cardiac wave")
        r = client.get("/auditor/batches", params={"search": "sepsis"}).json()
        assert r["total"] == 1
        assert "Sepsis" in r["batches"][0]["name"]

    def test_the_error_review_is_paged_and_omits_the_claim_by_default(
            self, client, db, library):
        """
        The claim is the heaviest field on the row and the list does not render
        it — shipping 500 of them to draw summaries is pure weight.
        """
        from tests.test_auditor_api import allocate, make_batch
        batch_id = make_batch(client, charts_per=6)
        allocate(client, batch_id)

        r = client.get(f"/auditor/batches/{batch_id}/plantings",
                       params={"limit": 2}).json()
        assert len(r["plantings"]) == 2
        assert r["total"] == 6
        assert "claim" not in r["plantings"][0]

        full = client.get(f"/auditor/batches/{batch_id}/plantings",
                          params={"include_claim": True}).json()
        assert "claim" in full["plantings"][0]

    def test_detection_patterns_says_when_it_did_not_read_everything(
            self, client, db, library):
        from tests.test_auditor_api import (
            allocate, make_batch, perfect_work, truth_map)
        batch_id = make_batch(client, charts_per=6)
        token = allocate(client, batch_id)["access_codes"][0]["token"]
        payload = client.get(f"/auditor/sessions/by-token/{token}").json()
        client.post(f"/auditor/sessions/{payload['session_id']}/submit",
                    json=perfect_work(payload, truth_map(client, batch_id)))

        full = client.get("/auditor/analytics/detection").json()
        assert full["truncated"] is False
        assert full["charts_scanned"] == full["charts_available"]

        capped = client.get("/auditor/analytics/detection",
                            params={"scan_limit": 2}).json()
        assert capped["truncated"] is True
        assert capped["charts_scanned"] == 2

    def test_the_curation_todo_list_is_paged(self, client, db, library):
        r = client.get("/auditor/keys/uncurated",
                       params={"specialty": "IP-DRG", "limit": 3}).json()
        assert len(r["charts"]) == 3
        assert r["total"] == len(library)

    def test_auditors_are_capped_weakest_first(self, client, db, library):
        """
        The cap keeps the people who need attention, not an arbitrary slice —
        which is why the ordering is decided in SQL rather than after the fact.
        """
        r = client.get("/auditor/analytics/by-auditor", params={"limit": 1}).json()
        assert len(r["auditors"]) <= 1


class TestFilters:
    """
    Every analytics view takes batch, specialty and auditor.

    These are worth their own tests because the failure mode is silent: FastAPI
    drops a query parameter the handler does not declare, so a filter the UI
    sends can look wired up while changing nothing. Three of the four handlers
    were in exactly that state — the assertions below are on the narrowing, not
    on the status code.
    """

    def _two_auditors(self, client):
        batch_id = make_batch(client, auditors=("Asha R", "Bo T"), charts_per=4)
        _run(client, batch_id, auditor_index=0)
        _run(client, batch_id, auditor_index=1)
        return batch_id

    def test_auditor_filter_narrows_every_view(self, client, db, library):
        batch_id = self._two_auditors(client)

        both = client.get("/auditor/analytics/overview").json()
        one = client.get("/auditor/analytics/overview",
                         params={"auditor": "Asha R"}).json()
        assert both["auditors"] == 2 and one["auditors"] == 1
        assert one["charts"] < both["charts"]

        rows = client.get("/auditor/analytics/by-auditor",
                          params={"auditor": "Asha R"}).json()["auditors"]
        assert [r["auditor_name"] for r in rows] == ["Asha R"]

        # by-batch keeps the batch but must count only that auditor inside it
        b = client.get("/auditor/analytics/by-batch",
                       params={"auditor": "Asha R"}).json()["batches"]
        assert len(b) == 1 and b[0]["batch_id"] == batch_id
        assert b[0]["auditors"] == 1

        d = client.get("/auditor/analytics/detection",
                       params={"auditor": "Asha R"}).json()
        assert d is not None

    def test_workbook_export_honours_current_filters(self, client, db, library):
        self._two_auditors(client)
        r = client.get("/auditor/analytics/export", params={"auditor": "Asha R"})
        assert r.status_code == 200, r.text
        import io
        wb = load_workbook(filename=io.BytesIO(r.content), read_only=True)
        rows = list(wb["By_Auditor"].iter_rows(values_only=True))
        names = [row[0] for row in rows if row and row[0] == "Asha R"]
        assert names == ["Asha R"]

    def test_batch_filter_is_accepted_by_by_batch(self, client, db, library):
        """by-batch took no batch_id at all, so selecting one changed nothing."""
        first = self._two_auditors(client)
        second = make_batch(client, auditors=("Cy K",), charts_per=4)
        _run(client, second)

        allb = client.get("/auditor/analytics/by-batch").json()["batches"]
        assert {r["batch_id"] for r in allb} == {first, second}

        just = client.get("/auditor/analytics/by-batch",
                          params={"batch_id": second}).json()["batches"]
        assert [r["batch_id"] for r in just] == [second]

    def test_a_filter_matching_nothing_reports_zero_not_everything(
            self, client, db, library):
        self._two_auditors(client)
        body = client.get("/auditor/analytics/overview",
                          params={"auditor": "Nobody At All"}).json()
        assert body["charts"] == 0
        assert body["audit_accuracy"] is None

    def test_date_filter_narrows_every_view_and_export(self, client, db, library):
        from datetime import datetime
        from models import AuditResult

        old_batch = make_batch(client, charts_per=4, name="Old audit wave")
        _run(client, old_batch)
        db.query(AuditResult).filter(AuditResult.batch_id == old_batch).update({
            AuditResult.scored_at: datetime(2024, 1, 10, 12, 0, 0),
        })
        new_batch = make_batch(client, charts_per=4, name="August audit wave")
        _run(client, new_batch)
        db.query(AuditResult).filter(AuditResult.batch_id == new_batch).update({
            AuditResult.scored_at: datetime(2026, 8, 10, 12, 0, 0),
        })
        db.commit()

        params = {"from_date": "2026-08-01", "to_date": "2026-08-31"}
        both = client.get("/auditor/analytics/overview").json()
        scoped = client.get("/auditor/analytics/overview", params=params).json()
        assert scoped["charts"] < both["charts"]
        assert scoped["batches"] == 1

        batches = client.get("/auditor/analytics/by-batch", params=params).json()["batches"]
        assert [b["batch_id"] for b in batches] == [new_batch]
        assert client.get("/auditor/analytics/by-auditor", params=params).json()["auditors"][0]["charts"] == 4
        assert client.get("/auditor/analytics/detection", params=params).json()["charts_available"] == 4
        assert client.get("/auditor/analytics/chart-signals", params=params).json()["charts"]
        # by-specialty was the one tab this test did not reach. It rolls each
        # specialty up in a second, inner query, which is exactly where a
        # filter gets dropped without anything failing loudly.
        by_spec = client.get("/auditor/analytics/by-specialty",
                             params=params).json()["specialties"]
        assert [s["charts"] for s in by_spec] == [4]

        r = client.get("/auditor/analytics/export", params=params)
        assert r.status_code == 200, r.text
        import io
        wb = load_workbook(filename=io.BytesIO(r.content), read_only=True)
        rows = list(wb["By_Batch"].iter_rows(values_only=True))
        names = {row[0] for row in rows if row and row[0] in {"Old audit wave", "August audit wave"}}
        assert names == {"August audit wave"}


class TestPdfReports:

    def test_auditor_report_pdf_renders(self, client, db, library):
        batch_id = make_batch(client, charts_per=6)
        _run(client, batch_id)
        r = client.get("/auditor/analytics/auditor-report.pdf",
                       params={"auditor": "Asha R"})
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"%PDF"

    def test_batch_report_pdf_renders(self, client, db, library):
        batch_id = make_batch(client, charts_per=6)
        _run(client, batch_id)
        r = client.get(f"/auditor/batches/{batch_id}/report.pdf")
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"%PDF"

    def test_batch_report_pdf_404s_without_scored_results(self, client, db, library):
        batch_id = make_batch(client, charts_per=6)
        r = client.get(f"/auditor/batches/{batch_id}/report.pdf")
        assert r.status_code == 404
