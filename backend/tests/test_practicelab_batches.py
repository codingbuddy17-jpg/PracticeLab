"""
Integration tests for PracticeLab batch creation and chart allocation.

Covers:
  - POST /practicelab/batches         — create batch
  - POST /practicelab/batches/{id}/run-allocation — allocate charts
  - Chart randomisation: Fisher-Yates per coder, no repeats across cycles
  - Manual chart assignment
  - Edge cases: no charts available, closed batch
"""
import pytest
from conftest import seed_charts, make_batch, make_chart

PASSPHRASE = "test-passphrase"


def create_batch_via_api(client, db, specialty="IP-DRG", coder_names=None,
                         charts_per_coder=3):
    # `or` would treat an explicit [] as "not supplied" and substitute the
    # default three, so a test asking for an empty batch silently got a full
    # one. Distinguish None (use the default) from [] (genuinely no coders).
    if coder_names is None:
        coder_names = ["Alice", "Bob", "Charlie"]
    payload = {
        "name": "Test Batch",
        "specialty": specialty,
        "categories": [],
        "difficulties": [],
        "charts_per_coder": charts_per_coder,
        "coders": [{"name": n, "emp_id": f"E{i}"} for i, n in enumerate(coder_names)],
        "created_by": "trainer",
        "use_weighted": True,
        "use_dpo": False,
        "is_direct_assignment": False,
    }
    r = client.post("/practicelab/batches", json=payload)
    return r


class TestBatchCreation:
    def test_create_batch_returns_200(self, client, db):
        seed_charts(db, specialty="IP-DRG", count=10)
        r = create_batch_via_api(client, db)
        assert r.status_code == 200

    def test_batch_has_id(self, client, db):
        seed_charts(db, count=10)
        data = create_batch_via_api(client, db).json()
        assert "id" in data or "batch_id" in data

    def test_batch_with_no_coders_is_rejected(self, client, db):
        """
        A batch needs at least one coder at creation; more can be added later
        via /batches/{id}/coders.

        This assertion was always correct but never actually ran — the helper
        treated an explicit [] as "not supplied" and substituted three coders,
        so the request under test was never coderless.
        """
        seed_charts(db, count=10)
        r = create_batch_via_api(client, db, coder_names=[])
        assert r.status_code == 400
        assert "coder" in str(r.json()["detail"]).lower()

    def test_coders_can_still_be_added_after_creation(self, client, db):
        seed_charts(db, count=10)
        batch_id = create_batch_via_api(client, db).json().get("batch_id")
        r = client.post(f"/practicelab/batches/{batch_id}/coders",
                        json={"coders": [{"name": "Late Joiner", "emp_id": "E99"}]})
        assert r.status_code == 200
        assert "Late Joiner" in r.json()["added"]

    def test_both_scoring_disabled_returns_400(self, client, db):
        seed_charts(db, count=10)
        payload = {
            "name": "Bad Batch", "specialty": "IP-DRG",
            "categories": [], "difficulties": [], "charts_per_coder": 3,
            "coders": [{"name": "Alice", "emp_id": "E1"}],
            "created_by": "trainer", "use_weighted": False, "use_dpo": False,
            "is_direct_assignment": False,
        }
        r = client.post("/practicelab/batches", json=payload)
        assert r.status_code == 400

    def test_dpo_is_allowed_for_eligible_op_batch(self, client, db):
        seed_charts(db, specialty="Surgery", count=2)
        payload = {
            "name": "OP Batch", "specialty": "Surgery",
            "categories": [], "difficulties": [], "charts_per_coder": 1,
            "coders": [{"name": "Alice", "emp_id": "E1"}],
            "created_by": "trainer", "use_weighted": False, "use_dpo": True,
            "is_direct_assignment": False,
        }
        r = client.post("/practicelab/batches", json=payload)
        assert r.status_code == 200
        batch_id = r.json().get("id") or r.json().get("batch_id")
        created = client.get(f"/practicelab/batches/{batch_id}").json()
        assert created["use_weighted"] is False
        assert created["use_dpo"] is True

    def test_dpo_is_forced_off_for_non_dpo_specialty(self, client, db):
        seed_charts(db, specialty="ED Profee", count=2)
        payload = {
            "name": "EDP Batch", "specialty": "ED Profee",
            "categories": [], "difficulties": [], "charts_per_coder": 1,
            "coders": [{"name": "Alice", "emp_id": "E1"}],
            "created_by": "trainer", "use_weighted": False, "use_dpo": True,
            "is_direct_assignment": False,
        }
        r = client.post("/practicelab/batches", json=payload)
        assert r.status_code == 200
        batch_id = r.json().get("id") or r.json().get("batch_id")
        created = client.get(f"/practicelab/batches/{batch_id}").json()
        assert created["use_weighted"] is True
        assert created["use_dpo"] is False

    def test_batch_list_returns_created_batch(self, client, db):
        seed_charts(db, count=10)
        create_batch_via_api(client, db)
        r = client.get("/practicelab/batches")
        assert r.status_code == 200
        assert len(r.json()) >= 1


class TestChartAllocation:
    def _setup(self, client, db, chart_count=10, coders=None, charts_per_coder=3):
        charts = seed_charts(db, specialty="IP-DRG", count=chart_count)
        r = create_batch_via_api(client, db, coder_names=coders or ["Alice", "Bob", "Charlie"],
                                 charts_per_coder=charts_per_coder)
        batch_id = r.json().get("id") or r.json().get("batch_id")
        return batch_id, charts

    def test_run_allocation_returns_200(self, client, db):
        batch_id, _ = self._setup(client, db)
        r = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                        json={"run_by": "trainer", "notes": "Cycle 1"})
        assert r.status_code == 200

    def test_allocation_assigns_correct_chart_count(self, client, db):
        batch_id, _ = self._setup(client, db, chart_count=10, charts_per_coder=3)
        data = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                           json={"run_by": "trainer"}).json()
        # Each of 3 coders gets 3 charts
        assignments = data.get("assignments", [])
        for assignment in assignments:
            assert assignment["chart_count"] == 3

    def test_randomisation_stats_in_allocation_response(self, client, db):
        batch_id, _ = self._setup(client, db)
        data = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                           json={"run_by": "trainer"}).json()
        stats = data.get("randomisation_stats")
        assert stats is not None
        assert "avg_uniqueness_pct" in stats

    def test_no_chart_repeats_per_coder_across_cycles(self, client, db):
        """Charts assigned in cycle 1 should NOT appear in cycle 2 for the same coder."""
        batch_id, _ = self._setup(client, db, chart_count=20, charts_per_coder=3)
        cycle1 = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                             json={"run_by": "trainer"}).json()
        cycle2 = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                             json={"run_by": "trainer"}).json()

        def chart_ids_for_coder(cycle_data, coder_name):
            for a in cycle_data.get("assignments", []):
                if a.get("coder_name") == coder_name:
                    return set(a.get("chart_ids", []))
            return set()

        for coder in ["Alice", "Bob", "Charlie"]:
            c1 = chart_ids_for_coder(cycle1, coder)
            c2 = chart_ids_for_coder(cycle2, coder)
            if c1 and c2:  # only check if both cycles assigned this coder
                overlap = c1 & c2
                assert not overlap, \
                    f"{coder} got same charts in both cycles: {overlap}"

    def test_short_pool_allocates_what_it_can_and_warns(self, client, db):
        """
        A pool smaller than requested is not an error. Ten coders where three
        get fewer charts is still a runnable batch, so allocation assigns what
        exists and reports a per-coder warning. Failing the whole cycle would
        be worse than the shortfall.
        """
        seed_charts(db, specialty="IP-DRG", count=2)
        r = create_batch_via_api(client, db, coder_names=["Alice"], charts_per_coder=5)
        batch_id = r.json().get("id") or r.json().get("batch_id")
        r2 = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                         json={"run_by": "trainer"})
        assert r2.status_code == 200
        body = r2.json()
        assert body["assigned"]["Alice"] == 2, "assign every chart available"
        assert body["warnings"], "a short allocation must say so"
        assert "Alice" in body["warnings"][0]

    def test_short_allocation_warning_is_persisted_on_the_cycle(self, client, db):
        """
        The warning used to exist only as a toast, so a cycle that shorted
        coders was indistinguishable from a clean one afterwards.
        """
        seed_charts(db, specialty="IP-DRG", count=2)
        r = create_batch_via_api(client, db, coder_names=["Alice"], charts_per_coder=5)
        batch_id = r.json().get("id") or r.json().get("batch_id")
        client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                    json={"run_by": "trainer"})

        cycles = client.get(f"/practicelab/batches/{batch_id}").json()["allocation_cycles"]
        assert cycles[-1]["warnings"], "the shortfall must survive the page reload"

    def test_empty_pool_is_still_an_error(self, client, db):
        """Nothing to allocate is a genuine failure, unlike a partial pool."""
        r = create_batch_via_api(client, db, coder_names=["Alice"], charts_per_coder=5)
        batch_id = r.json().get("id") or r.json().get("batch_id")
        r2 = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                         json={"run_by": "trainer"})
        assert r2.status_code == 400

    def test_manual_chart_allocation(self, client, db):
        charts = seed_charts(db, specialty="IP-DRG", count=10)
        r = create_batch_via_api(client, db, coder_names=["Alice", "Bob"], charts_per_coder=2)
        batch_id = r.json().get("id") or r.json().get("batch_id")
        manual_ids = [charts[0].id, charts[1].id, charts[2].id, charts[3].id]
        r2 = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                         json={"run_by": "trainer", "manual_chart_ids": manual_ids})
        assert r2.status_code == 200

    def test_allocation_cycle_persisted(self, client, db):
        batch_id, _ = self._setup(client, db)
        client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                    json={"run_by": "trainer"})
        r = client.get(f"/practicelab/batches/{batch_id}")
        assert r.status_code == 200
        data = r.json()
        cycles = data.get("allocation_cycles", [])
        assert len(cycles) >= 1

    def test_randomisation_stats_saved_on_cycle(self, client, db):
        batch_id, _ = self._setup(client, db)
        client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                    json={"run_by": "trainer"})
        data = client.get(f"/practicelab/batches/{batch_id}").json()
        for cycle in data.get("allocation_cycles", []):
            if "randomisation_stats" in cycle:
                assert cycle["randomisation_stats"] is not None
                return
        pytest.skip("No cycles with randomisation_stats found")


class TestBatchClosure:
    def test_close_batch(self, client, db):
        seed_charts(db, count=10)
        r = create_batch_via_api(client, db)
        batch_id = r.json().get("id") or r.json().get("batch_id")
        r2 = client.post(f"/practicelab/batches/{batch_id}/close",
                         json={"closed_by": "trainer"})
        assert r2.status_code == 200

    def test_allocation_on_closed_batch_fails(self, client, db):
        seed_charts(db, count=10)
        r = create_batch_via_api(client, db)
        batch_id = r.json().get("id") or r.json().get("batch_id")
        client.post(f"/practicelab/batches/{batch_id}/close",
                    json={"closed_by": "trainer"})
        r2 = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                         json={"run_by": "trainer"})
        assert r2.status_code == 400


class TestBatchListPaging:
    """
    The list loaded every batch on entry. Fine at a few dozen, not at a few
    thousand — and a search that only looks at what is already loaded stops
    working exactly when the list gets big enough to need it.
    """

    def _mk(self, client, name, direct=False):
        r = client.post("/practicelab/batches", json={
            "name": name, "specialty": "IP-DRG", "categories": [], "difficulties": [],
            "charts_per_coder": 1, "coders": [{"name": "A", "emp_id": "E1"}],
            "created_by": "trainer", "is_direct_assignment": direct,
        })
        assert r.status_code == 200, r.text
        return r.json()["batch_id"]

    def test_newest_first(self, client):
        """Ties on created_at are broken by id, so batches created inside the
        same second still have one stable order — without that, paging can show
        a row twice and skip another."""
        for n in ("Oldest", "Middle", "Newest"):
            self._mk(client, n)
        names = [b["name"] for b in client.get("/practicelab/batches").json()]
        assert names == ["Newest", "Middle", "Oldest"]

    def test_limit_and_offset_walk_the_list(self, client):
        for n in ("B1", "B2", "B3"):
            self._mk(client, n)
        first = client.get("/practicelab/batches", params={"limit": 2}).json()
        second = client.get("/practicelab/batches", params={"limit": 2, "offset": 2}).json()
        assert len(first) == 2 and len(second) == 1
        assert {b["name"] for b in first} | {b["name"] for b in second} == {"B1", "B2", "B3"}

    def test_total_count_header_is_the_unpaged_total(self, client):
        """A page cannot say how many rows there were — the header must."""
        for n in ("B1", "B2", "B3"):
            self._mk(client, n)
        r = client.get("/practicelab/batches", params={"limit": 1})
        assert len(r.json()) == 1
        assert r.headers["X-Total-Count"] == "3"

    def test_search_reaches_past_the_loaded_page(self, client):
        """
        The point of server-side search: "Sepsis" must find the batch even when
        it is nowhere near the first page.
        """
        for i in range(30):
            self._mk(client, f"Filler {i}")
        self._mk(client, "Sepsis Wave 1")
        for i in range(30):
            self._mk(client, f"Later Filler {i}")

        r = client.get("/practicelab/batches", params={"search": "sepsis", "limit": 25})
        assert [b["name"] for b in r.json()] == ["Sepsis Wave 1"]
        assert r.headers["X-Total-Count"] == "1"

    def test_search_is_case_insensitive_and_partial(self, client):
        self._mk(client, "IP-DRG June Wave")
        assert len(client.get("/practicelab/batches", params={"search": "JUNE"}).json()) == 1
        assert len(client.get("/practicelab/batches", params={"search": "wav"}).json()) == 1

    def test_search_matches_the_creator(self, client):
        self._mk(client, "Some Batch")
        assert len(client.get("/practicelab/batches", params={"search": "trainer"}).json()) == 1

    def test_paging_keeps_batches_and_direct_assignments_apart(self, client):
        """Each list pages independently, so one cannot crowd out the other."""
        self._mk(client, "Formal One")
        self._mk(client, "Direct One", direct=True)
        formal = client.get("/practicelab/batches")
        direct = client.get("/practicelab/batches", params={"direct_only": True})
        assert [b["name"] for b in formal.json()] == ["Formal One"]
        assert [b["name"] for b in direct.json()] == ["Direct One"]
        assert formal.headers["X-Total-Count"] == "1"

    def test_no_limit_still_returns_everything(self, client):
        """Existing callers pass no limit and must be unaffected."""
        for n in ("B1", "B2", "B3"):
            self._mk(client, n)
        assert len(client.get("/practicelab/batches").json()) == 3
