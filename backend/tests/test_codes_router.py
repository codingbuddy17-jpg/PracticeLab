"""
The code-description endpoints.

Every one of these must behave sensibly against an EMPTY table, because that
is the state of any deployment where nobody has run the ingest yet. The app
worked without descriptions before they existed and must keep working — a
missing description is a quieter screen, never an error.
"""
import pytest

from models import CodeDescription, CodeSetVersion, PcsCodeAxis


@pytest.fixture()
def loaded(db):
    db.add_all([
        CodeDescription(code="J189", code_system="ICD10CM",
                        description="Pneumonia, unspecified organism",
                        short_description="Pneumonia, unsp organism",
                        chapter="Diseases of the respiratory system",
                        chapter_no=10, is_billable=True),
        CodeDescription(code="J18", code_system="ICD10CM",
                        description="Pneumonia, unspecified organism",
                        is_billable=False),
        CodeDescription(code="J1889", code_system="ICD10CM",
                        description="Other pneumonia", is_billable=True),
        CodeDescription(code="0DTJ4ZZ", code_system="ICD10PCS",
                        description="Resection of Appendix, Percutaneous "
                                    "Endoscopic Approach", is_billable=True),
        CodeDescription(code="J1885", code_system="HCPCS",
                        description="Injection, something entirely else",
                        is_billable=True),
    ])
    db.add(PcsCodeAxis(code="0DTJ4ZZ", section="Medical and Surgical",
                       body_system="Gastrointestinal System",
                       root_operation="Resection", body_part="Appendix",
                       approach="Percutaneous Endoscopic",
                       device="No Device", qualifier="No Qualifier"))
    db.commit()
    return db


class TestDescribe:
    def test_it_describes_many_codes_in_one_call(self, client, loaded):
        got = client.get("/codes/describe", params={"codes": "J189,0DTJ4ZZ"})
        assert got.status_code == 200
        found = got.json()["descriptions"]
        assert found["J189"]["description"].startswith("Pneumonia")
        assert found["J189"]["chapter_no"] == 10
        assert "Resection" in found["0DTJ4ZZ"]["description"]

    def test_the_dot_a_coder_types_still_matches(self, client, loaded):
        """Stored without the point; typed with it about half the time."""
        found = client.get("/codes/describe",
                           params={"codes": "J18.9"}).json()["descriptions"]
        assert "J189" in found

    def test_an_unknown_code_is_simply_absent_not_an_error(self, client, loaded):
        got = client.get("/codes/describe", params={"codes": "J189,Z999999"})
        assert got.status_code == 200
        assert set(got.json()["descriptions"]) == {"J189"}

    def test_the_section_picks_the_code_system(self, client, loaded):
        """
        J1885 is a real HCPCS code and looks like a diagnosis. Without the
        section, a dx box could caption itself with a drug injection.
        """
        as_dx = client.get("/codes/describe",
                           params={"codes": "J1885", "section": "SDx"})
        assert as_dx.json()["descriptions"] == {}
        as_hcpcs = client.get("/codes/describe",
                              params={"codes": "J1885", "section": "CPT"})
        assert "entirely else" in \
            as_hcpcs.json()["descriptions"]["J1885"]["description"]

    def test_empty_input_is_answered_not_refused(self, client, loaded):
        assert client.get("/codes/describe",
                          params={"codes": " , "}).json()["descriptions"] == {}

    def test_nothing_loaded_is_a_legal_state(self, client):
        got = client.get("/codes/describe", params={"codes": "J189"})
        assert got.status_code == 200 and got.json()["descriptions"] == {}


class TestSearch:
    def test_it_completes_a_code_someone_has_started(self, client, loaded):
        matches = client.get("/codes/search",
                             params={"prefix": "J18", "section": "SDx"}
                             ).json()["matches"]
        codes = [m["code"] for m in matches]
        assert "J189" in codes and "J1889" in codes
        assert "J1885" not in codes          # HCPCS, wrong section

    def test_billable_codes_come_first(self, client, loaded):
        """A category heading is not something anyone codes to."""
        matches = client.get("/codes/search",
                             params={"prefix": "J18", "section": "SDx"}
                             ).json()["matches"]
        assert matches[0]["billable"] is True
        assert matches[-1]["code"] == "J18"

    def test_one_character_returns_nothing(self, client, loaded):
        """
        Prefix completion, not browsing. "J" is a third of the code set and
        would be a list nobody can use.
        """
        assert client.get("/codes/search", params={"prefix": "J"}
                          ).status_code == 422

    def test_it_does_not_search_descriptions(self, client, loaded):
        """
        Deliberate. Finding a code by typing "pneumonia" answers the coding
        question a graded session exists to ask.
        """
        assert client.get("/codes/search",
                          params={"prefix": "pneumo"}).json()["matches"] == []

    def test_the_limit_is_capped(self, client, loaded):
        assert client.get("/codes/search",
                          params={"prefix": "J1", "limit": 500}
                          ).status_code == 422


class TestPcsAxes:
    def test_it_breaks_a_code_into_its_seven_characters(self, client, loaded):
        got = client.get("/codes/pcs/0DTJ4ZZ").json()
        assert got["valid"] is True
        assert got["root_operation"] == "Resection"
        assert got["approach"] == "Percutaneous Endoscopic"

    def test_absence_from_the_table_means_the_code_is_not_real(self, client,
                                                               loaded):
        """
        PCS only exists in the combinations the CMS tables define, so a
        well-formed string that is not here is not a code.
        """
        got = client.get("/codes/pcs/0DTJ9ZZ").json()
        assert got["valid"] is False


class TestStatus:
    def test_it_says_nothing_is_loaded_rather_than_looking_broken(self, client):
        got = client.get("/codes/status").json()
        assert got["any"] is False and got["loaded"] == []

    def test_it_reports_the_edition_that_is_in_use(self, client, db):
        db.add(CodeSetVersion(code_system="ICD10CM", edition="FY2026",
                              row_count=98186, source_url="https://cms.gov"))
        db.commit()
        got = client.get("/codes/status").json()
        assert got["any"] is True
        assert got["loaded"][0]["edition"] == "FY2026"
        assert got["loaded"][0]["row_count"] == 98186


class TestEveryCodeRowIsWiredForDescriptions:
    """
    Every place the auditor screen renders a code row must be handed the
    lookup, or that section silently shows no descriptions while the others do.

    This is not hypothetical: the PDx row shipped without it. The edit that
    added the prop to the other call sites did not match the PDx one, nothing
    failed, and principal diagnoses — the single most important code on an
    inpatient chart — were the one section with no description. A partly wired
    screen is worse than an unwired one, because it reads as "no description
    exists for this code".
    """

    import pathlib
    SRC = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
           / "pages" / "AuditSession.tsx")

    def test_every_row_component_receives_the_lookup(self):
        src = self.SRC.read_text()
        import re
        # Each JSX element from its tag to the closing "/>", so the check sees
        # the whole call rather than one line of it.
        for tag in ("PdxRow", "LineRow"):
            for call in re.findall(r"<%s\b[^>]*?/>" % tag, src, re.S):
                assert "describe=" in call, \
                    "<%s ...> renders codes without the description lookup" % tag

    def test_the_lookup_covers_the_codes_being_added_too(self):
        """A code the auditor types as a missing line needs it just as much."""
        src = self.SRC.read_text()
        assert "code={f.correct_value || ''}" in src

    def test_the_coder_form_is_wired_for_its_three_code_fields(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
               / "pages" / "PracticeSession.tsx").read_text()
        assert src.count("<CodeSays") >= 3, \
            "PDx, secondary diagnoses and PCS each need a description line"


class TestSuggestionsAreOfferedInTheFormPeopleType:
    """
    The suggestion list is built from the code tables, which store codes
    without the decimal point. Offering `M180` was legal — grading strips the
    point before comparing — but taking it with Tab then drew a format warning,
    because the shape check required the dot on anything longer than three
    characters while the form said "dot optional".

    Two things were wrong and both are fixed: the check now means what the form
    says, and the list offers `M18.0`, which is how the answer key writes it.

    Static assertions, since the frontend has no test runner and adding one
    would be a new dependency. They pin intent, not behaviour.
    """

    import pathlib
    SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"

    def test_the_dot_really_is_optional_in_the_shape_check(self):
        src = (self.SRC / "codeFormat.ts").read_text()
        assert r"const DX = /^[A-TV-Z][0-9][0-9A-Z](\.?[0-9A-Z]{1,4})?$/" in src, \
            "the diagnosis pattern must accept J189 as well as J18.9"

    def test_the_suggestion_list_dots_the_code_before_offering_it(self):
        src = (self.SRC / "CodeSuggest.tsx".join(["components/", ""])).read_text()
        # Displayed, clicked and keyboard-selected all go through the same
        # formatting — one of the three being missed is the whole bug.
        assert src.count("withDot(") >= 3

    def test_only_diagnoses_get_a_dot(self):
        """PCS and HCPCS have no decimal point; adding one makes a non-code."""
        src = (self.SRC / "codeFormat.ts").read_text()
        assert "if (system && system !== 'ICD10CM') return bare" in src


class TestRowsWithADescriptionAlignToTheInput:
    """
    The description line made the code column the tallest thing in its row, so
    a row that centred its children pushed the POA select and the remove button
    down against it. Anything sharing a row with a description aligns to the
    top instead.
    """

    import pathlib
    SRC = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
           / "pages" / "PracticeSession.tsx")

    def test_no_row_carrying_a_description_is_centre_aligned(self):
        import re
        src = self.SRC.read_text()
        for m in re.finditer(r"<div key=\{i\} style=\{\{ display: 'flex'[^}]*\}\}>", src):
            row = src[m.start():m.start() + 1400]
            if "CodeSays" in row:
                assert "alignItems: 'center'" not in m.group(0), \
                    "a row with a description line must align to the top"
