"""
Whether a loaded code set still counts as current.

The application cannot refresh itself, so the failure mode is silence: nothing
errors when the data is a year old. Every rule here exists so a screen can say
something instead.

The governing principle is that only positive evidence counts as current. An
unknown system, a missing date, a set never loaded — all report NOT current,
because this exists to stop silence reading as approval.
"""
import datetime

from services.code_editions import (current_edition, fiscal_year, freshness,
                                    quarter_start)


class TestTheFiscalYear:
    def test_it_turns_over_on_the_first_of_october(self):
        assert fiscal_year(datetime.date(2026, 9, 30)) == 2026
        assert fiscal_year(datetime.date(2026, 10, 1)) == 2027

    def test_the_edition_string_matches_what_the_ingest_writes(self):
        assert current_edition(datetime.date(2026, 8, 17)) == "FY2026"
        assert current_edition(datetime.date(2026, 10, 2)) == "FY2027"


class TestQuarters:
    def test_the_quarter_start_is_the_first_of_its_month(self):
        assert quarter_start(datetime.date(2026, 8, 17)) == datetime.date(2026, 7, 1)
        assert quarter_start(datetime.date(2026, 1, 1)) == datetime.date(2026, 1, 1)
        assert quarter_start(datetime.date(2026, 12, 31)) == datetime.date(2026, 10, 1)


class TestAnnualSets:
    """
    ICD-10-CM and ICD-10-PCS are judged on their EDITION, not their load date.
    The edition says which year's codes these are, which is the thing that
    matters; a fresh load of last year's file is still last year's codes.
    """

    TODAY = datetime.date(2026, 8, 17)

    def test_the_current_edition_is_current(self):
        got = freshness("ICD10CM", "FY2026",
                        datetime.datetime(2026, 1, 5), self.TODAY)
        assert got["current"] is True and got["note"] == ""

    def test_last_year_s_edition_is_flagged_however_recently_it_was_loaded(self):
        got = freshness("ICD10CM", "FY2025",
                        datetime.datetime(2026, 8, 16), self.TODAY)
        assert got["current"] is False
        assert "FY2025" in got["note"] and "FY2026" in got["note"]

    def test_the_day_after_the_first_of_october_the_bar_moves(self):
        """FY2026 is current in September and stale in October."""
        september = freshness("ICD10PCS", "FY2026", None,
                              datetime.date(2026, 9, 30))
        october = freshness("ICD10PCS", "FY2026", None,
                            datetime.date(2026, 10, 1))
        assert september["current"] is True
        assert october["current"] is False
        assert october["expected"] == "FY2027"

    def test_an_unknown_edition_is_not_given_the_benefit_of_the_doubt(self):
        got = freshness("ICD10CM", None, datetime.datetime(2026, 8, 16),
                        self.TODAY)
        assert got["current"] is False


class TestQuarterlySets:
    """
    HCPCS is republished quarterly, but the edition string only carries the
    fiscal year — it cannot tell one quarter from the next. The load DATE can:
    a file loaded before this quarter began cannot hold this quarter's changes.
    """

    TODAY = datetime.date(2026, 8, 17)      # Q3, began 1 July

    def test_a_load_inside_the_current_quarter_is_current(self):
        got = freshness("HCPCS", "FY2026", datetime.datetime(2026, 7, 2),
                        self.TODAY)
        assert got["current"] is True

    def test_a_load_from_last_quarter_is_flagged(self):
        got = freshness("HCPCS", "FY2026", datetime.datetime(2026, 6, 30),
                        self.TODAY)
        assert got["current"] is False
        assert "2026-07-01" in got["note"]

    def test_the_boundary_day_itself_counts_as_current(self):
        got = freshness("HCPCSMOD", "FY2026", datetime.datetime(2026, 7, 1),
                        self.TODAY)
        assert got["current"] is True

    def test_the_right_year_is_not_enough(self):
        """January's file in August is eight months of changes behind."""
        got = freshness("HCPCS", "FY2026", datetime.datetime(2026, 1, 15),
                        self.TODAY)
        assert got["current"] is False

    def test_no_load_date_is_reported_rather_than_assumed_fine(self):
        got = freshness("HCPCS", "FY2026", None, self.TODAY)
        assert got["current"] is False and "load date" in got["note"]


class TestNothingLoaded:
    def test_a_set_that_was_never_loaded_says_so_plainly(self):
        got = freshness("ICD10CM", None, None, datetime.date(2026, 8, 17))
        assert got["current"] is False
        assert "never been loaded" in got["note"]

    def test_an_unrecognised_system_is_not_called_current(self):
        got = freshness("SNOMED", "FY2026", datetime.datetime(2026, 8, 1),
                        datetime.date(2026, 8, 17))
        assert got["current"] is False


class TestTheEndpointReportsIt:
    def test_an_empty_installation_needs_attention(self, client):
        body = client.get("/codes/status").json()
        assert body["any"] is False
        assert body["needs_attention"] is True
        # Named explicitly rather than merely absent: listing only what IS
        # loaded makes a half-loaded installation look complete.
        assert {m["code_system"] for m in body["missing"]} == {
            "ICD10CM", "ICD10PCS", "HCPCS", "HCPCSMOD"}

    def test_a_partial_load_still_needs_attention(self, client, db):
        from models import CodeSetVersion
        from services.code_editions import current_edition
        db.add(CodeSetVersion(code_system="ICD10CM", edition=current_edition(),
                              row_count=98186))
        db.commit()
        body = client.get("/codes/status").json()
        assert body["any"] is True
        assert body["needs_attention"] is True
        assert body["loaded"][0]["current"] is True
        assert {m["code_system"] for m in body["missing"]} == {
            "ICD10PCS", "HCPCS", "HCPCSMOD"}

    def test_a_stale_edition_is_reported_with_a_readable_reason(self, client, db):
        from models import CodeSetVersion
        db.add(CodeSetVersion(code_system="ICD10CM", edition="FY2019",
                              row_count=71932))
        db.commit()
        row = client.get("/codes/status").json()["loaded"][0]
        assert row["current"] is False
        assert "FY2019" in row["note"]
        assert row["label"] == "ICD-10-CM diagnoses"
