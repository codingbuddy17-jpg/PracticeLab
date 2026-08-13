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
        assert body["component_basis"] == "pooled findings over plantings"

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
