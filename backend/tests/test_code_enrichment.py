"""
Joining coded errors to the CMS reference tables.

Two hazards these tests exist for. The section spellings differ between
modules — PracticeLab's enum is PDX where the auditor uses PDx — and matching
case-sensitively returns nothing while raising nothing, which reads as "this
data has no chapters" rather than as a bug. And an environment that never ran
the ingest must get analytics without these axes, never analytics that fail.
"""
import pytest

from models import CodeDescription, PcsCodeAxis
from services.code_enrichment import (ccmcc_label, chapter_label, enrich_codes,
                                      is_licensed_cpt, lookup,
                                      pcs_axis_labels, system_for_section)


@pytest.fixture()
def loaded(db):
    db.add_all([
        CodeDescription(code="N186", code_system="ICD10CM",
                        description="End stage renal disease",
                        short_description="End stage renal disease",
                        chapter="Diseases of the genitourinary system",
                        chapter_no=14, cc_mcc_status="MCC", is_billable=True),
        CodeDescription(code="E119", code_system="ICD10CM",
                        description="Type 2 diabetes mellitus without complications",
                        chapter="Endocrine, nutritional and metabolic diseases",
                        chapter_no=4, cc_mcc_status=None, is_billable=True),
        CodeDescription(code="0DTJ4ZZ", code_system="ICD10PCS",
                        description="Resection of Appendix, Percutaneous "
                                    "Endoscopic Approach", is_billable=True),
        CodeDescription(code="J1885", code_system="HCPCS",
                        description="Injection, ketorolac tromethamine",
                        is_billable=True),
    ])
    db.add(PcsCodeAxis(code="0DTJ4ZZ", section="Medical and Surgical",
                       body_system="Gastrointestinal System",
                       root_operation="Resection", body_part="Appendix",
                       approach="Percutaneous Endoscopic",
                       device="No Device", qualifier="No Qualifier"))
    db.commit()
    return db


class TestSectionSpelling:
    """
    The trap. PracticeLab's GradingSection enum is PDX/SDX; the auditor and the
    codes API say PDx/SDx. A case-sensitive match returns zero diagnosis rows
    and raises nothing.
    """

    @pytest.mark.parametrize("section", ["PDx", "PDX", "pdx", "SDx", "SDX"])
    def test_either_spelling_of_a_diagnosis_section_resolves(self, section):
        assert system_for_section(section) == "ICD10CM"

    def test_procedure_and_cpt_sections_resolve(self):
        assert system_for_section("PCS") == "ICD10PCS"
        assert system_for_section("cpt") == "HCPCS"

    def test_an_enum_member_works_as_well_as_a_string(self):
        from models.practicelab import GradingSection
        assert system_for_section(GradingSection.SDX) == "ICD10CM"
        assert system_for_section(GradingSection.PCS) == "ICD10PCS"

    def test_something_unrecognised_resolves_to_nothing(self):
        assert system_for_section("POA") is None
        assert system_for_section(None) is None

    def test_the_enum_really_does_differ_in_case(self):
        """If this ever stops being true, the fold above can be simplified."""
        from models.practicelab import GradingSection
        assert GradingSection.SDX.name == "SDX"


class TestEnriching:
    def test_it_describes_a_diagnosis_with_its_chapter_and_severity(self, loaded):
        got = enrich_codes(loaded, [("SDX", "N18.6")])
        info = lookup(got, "SDX", "N18.6")
        assert info["description"] == "End stage renal disease"
        assert info["chapter_no"] == 14
        assert info["cc_mcc"] == "MCC"

    def test_the_dot_is_not_a_difference(self, loaded):
        assert lookup(enrich_codes(loaded, [("PDX", "N186")]), "PDX", "N18.6")
        assert lookup(enrich_codes(loaded, [("PDX", "N18.6")]), "PDX", "N186")

    def test_a_procedure_carries_its_seven_axes(self, loaded):
        got = enrich_codes(loaded, [("PCS", "0DTJ4ZZ")])
        axes = pcs_axis_labels(lookup(got, "PCS", "0DTJ4ZZ"))
        assert axes["root_operation"] == "Resection"
        assert axes["approach"] == "Percutaneous Endoscopic"
        assert axes["body_system"] == "Gastrointestinal System"

    def test_many_codes_and_systems_in_one_call(self, loaded):
        got = enrich_codes(loaded, [("SDX", "N18.6"), ("PCS", "0DTJ4ZZ"),
                                    ("CPT", "J1885"), ("PDX", "E11.9")])
        assert len(got) == 4

    def test_an_unknown_code_is_simply_absent(self, loaded):
        got = enrich_codes(loaded, [("SDX", "Z99.99")])
        assert lookup(got, "SDX", "Z99.99") is None

    def test_nothing_loaded_returns_nothing_rather_than_failing(self, db):
        """
        An environment that never ran the ingest gets analytics without these
        axes — never analytics that fail.
        """
        assert enrich_codes(db, [("SDX", "N18.6")]) == {}


class TestLicensedCptIsNeverAsked:
    """
    CPT proper is AMA copyright and absent. Level II codes sit on the same
    line, so the line is drawn on the code's SHAPE, not on the section.
    """

    @pytest.mark.parametrize("code", ["99213", "36415", "3006F", "0075T"])
    def test_a_cpt_code_is_recognised_as_licensed(self, code):
        assert is_licensed_cpt(code) is True

    @pytest.mark.parametrize("code", ["J1885", "G0008", "A4550"])
    def test_a_level_two_code_is_not(self, code):
        assert is_licensed_cpt(code) is False

    def test_a_cpt_line_still_describes_its_level_two_codes(self, loaded):
        got = enrich_codes(loaded, [("CPT", "99213"), ("CPT", "J1885")])
        assert lookup(got, "CPT", "J1885") is not None
        assert lookup(got, "CPT", "99213") is None


class TestTheAxes:
    def test_a_procedure_has_no_icd_chapter(self, loaded):
        """
        None, not "Unknown". Bucketing it would put licensed-CPT blindness and
        genuine gaps in the same pile.
        """
        got = enrich_codes(loaded, [("PCS", "0DTJ4ZZ")])
        assert chapter_label(lookup(got, "PCS", "0DTJ4ZZ")) is None

    def test_a_diagnosis_with_no_severity_reports_neither_not_silence(self, loaded):
        """
        A team missing mostly non-CC secondaries is a different problem from
        one missing MCCs. Collapsing the first into silence hides it.
        """
        got = enrich_codes(loaded, [("SDX", "E11.9")])
        assert ccmcc_label(lookup(got, "SDX", "E11.9")) == "Neither"

    def test_only_diagnoses_carry_a_severity(self, loaded):
        got = enrich_codes(loaded, [("PCS", "0DTJ4ZZ"), ("CPT", "J1885")])
        assert ccmcc_label(lookup(got, "PCS", "0DTJ4ZZ")) is None
        assert ccmcc_label(lookup(got, "CPT", "J1885")) is None

    def test_axes_are_empty_for_a_diagnosis(self, loaded):
        got = enrich_codes(loaded, [("SDX", "N18.6")])
        assert pcs_axis_labels(lookup(got, "SDX", "N18.6")) == {}
