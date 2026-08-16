"""
Answer-key codes checked against the loaded CMS tables.

The distinction these tests exist to protect: "checked, all found" and "not
checked because nothing is loaded" are different claims. Conflating them tells
a trainer their file was verified when nothing verified it, which is worse than
saying nothing.
"""
import pytest

from models import CodeDescription, PcsCodeAxis
from services.code_check import entries_from_key_row, unknown_codes


@pytest.fixture()
def loaded(db):
    db.add_all([
        CodeDescription(code="J189", code_system="ICD10CM",
                        description="Pneumonia", is_billable=True),
        CodeDescription(code="E119", code_system="ICD10CM",
                        description="Type 2 diabetes", is_billable=True),
        CodeDescription(code="0DTJ4ZZ", code_system="ICD10PCS",
                        description="Resection of Appendix", is_billable=True),
        CodeDescription(code="0DTJ9ZZ", code_system="ICD10PCS",
                        description="A description without a table row",
                        is_billable=True),
        CodeDescription(code="J1885", code_system="HCPCS",
                        description="Ketorolac", is_billable=True),
        CodeDescription(code="LT", code_system="HCPCSMOD",
                        description="Left side", is_billable=True),
    ])
    db.add(PcsCodeAxis(code="0DTJ4ZZ", section="Medical and Surgical",
                       body_system="Gastrointestinal System",
                       root_operation="Resection", body_part="Appendix",
                       approach="Percutaneous Endoscopic",
                       device="No Device", qualifier="No Qualifier"))
    db.commit()
    return db


class TestNotLoaded:
    def test_nothing_loaded_reports_not_checked_not_all_clear(self, db):
        """
        None, not []. An empty list would render as "we looked and your file is
        fine", which is a claim nothing here is entitled to make.
        """
        assert unknown_codes(db, [("IP001", "PDx", "J189")]) is None


class TestChecking:
    def test_a_real_code_is_not_reported(self, loaded):
        assert unknown_codes(loaded, [("IP001", "PDx", "J189")]) == []

    def test_a_well_formed_code_that_does_not_exist_is_reported(self, loaded):
        """
        The whole point. J18.99 passes every shape check there is.
        """
        out = unknown_codes(loaded, [("IP001", "PDx", "J1899")])
        assert [(r["chart"], r["code"]) for r in out] == [("IP001", "J1899")]

    def test_the_dot_a_trainer_types_is_not_a_difference(self, loaded):
        assert unknown_codes(loaded, [("IP001", "PDx", "J18.9")]) == []

    def test_a_code_from_the_wrong_system_does_not_count_as_found(self, loaded):
        """J1885 is real HCPCS and is not a diagnosis."""
        out = unknown_codes(loaded, [("IP001", "SDx", "J1885")])
        assert out and out[0]["code"] == "J1885"

    def test_pcs_needs_a_table_row_not_just_a_description(self, loaded):
        """
        PCS is only real in the combinations the tables define. A description
        alone is not enough — that is exactly the check the PCS tables exist for.
        """
        assert unknown_codes(loaded, [("IP001", "PCS", "0DTJ4ZZ")]) == []
        out = unknown_codes(loaded, [("IP001", "PCS", "0DTJ9ZZ")])
        assert out and out[0]["code"] == "0DTJ9ZZ"

    def test_hcpcs_modifiers_are_checked(self, loaded):
        assert unknown_codes(loaded, [("OP001", "Modifier", "LT")]) == []
        out = unknown_codes(loaded, [("OP001", "Modifier", "ZQ")])
        assert out and out[0]["code"] == "ZQ"

    def test_blank_codes_are_not_findings(self, loaded):
        assert unknown_codes(loaded, [("IP001", "SDx", ""),
                                      ("IP001", "SDx", "   ")]) == []

    def test_the_report_is_capped(self, loaded):
        entries = [("IP%03d" % i, "PDx", "Q%04d" % i) for i in range(60)]
        assert len(unknown_codes(loaded, entries)) == 25


class TestCptIsNotJudged:
    """
    CPT descriptions are AMA copyright and this app does not carry them, so it
    has no basis for calling a five-digit numeric code wrong. Reporting every
    CPT code as unknown would bury the real findings; silently passing them
    while claiming to have checked would be worse.
    """

    def test_a_numeric_cpt_code_is_left_alone(self, loaded):
        assert unknown_codes(loaded, [("OP001", "CPT", "20610")]) == []

    def test_a_category_two_cpt_code_is_left_alone(self, loaded):
        assert unknown_codes(loaded, [("OP001", "CPT", "3006F")]) == []

    def test_a_numeric_modifier_is_left_alone(self, loaded):
        """25 and 59 are CPT modifiers — AMA's, not in the HCPCS file."""
        assert unknown_codes(loaded, [("OP001", "Modifier", "59")]) == []

    def test_a_level_two_hcpcs_code_on_a_cpt_line_is_still_checked(self, loaded):
        """J1885 is not CPT, so this app can and should judge it."""
        assert unknown_codes(loaded, [("OP001", "CPT", "J1885")]) == []
        out = unknown_codes(loaded, [("OP001", "CPT", "J9999")])
        assert out and out[0]["code"] == "J9999"


class TestFlatteningAKeyRow:
    def test_every_code_on_the_row_is_offered_for_checking(self):
        row = {
            "pdx_code": "J18.9",
            "sdx": [{"code": "E11.9", "poa": "Y"}],
            "pcs": [{"code": "0DTJ4ZZ"}],
            "cpt": [{"code": "20610", "modifier": "LT, 59", "units": 1}],
        }
        got = list(entries_from_key_row("IP001", row))
        assert ("IP001", "PDx", "J18.9") in got
        assert ("IP001", "SDx", "E11.9") in got
        assert ("IP001", "PCS", "0DTJ4ZZ") in got
        assert ("IP001", "CPT", "20610") in got
        # Two modifiers in one cell is the normal way trainers write them.
        assert ("IP001", "Modifier", "LT") in got
        assert ("IP001", "Modifier", "59") in got

    def test_a_sparse_row_does_not_break_it(self):
        assert list(entries_from_key_row("IP001", {})) == [("IP001", "PDx", None)]
