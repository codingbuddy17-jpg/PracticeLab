"""
The code-set ingest — parsing only, no download and no database.

These are pure functions over bytes, which is the point: the fiddly part of
this job is reading CMS's formats correctly, and that can be tested without a
network or a schema.
"""
import importlib.util
import pathlib

import pytest

_SCRIPT = (pathlib.Path(__file__).resolve().parents[2]
           / "scripts" / "ingest_code_sets.py")


@pytest.fixture(scope="module")
def ingest():
    spec = importlib.util.spec_from_file_location("ingest_code_sets", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestChapters:
    """
    Chapters are resolved by code RANGE, not first letter.

    Two chapters share a letter with another: C00-D49 is Neoplasms while
    D50-D89 is Blood, and H00-H59 is Eye while H60-H95 is Ear. A letter-keyed
    map has to fudge those together, which destroys the distinction a chapter
    analytics axis exists to draw.
    """

    @pytest.mark.parametrize("code,number,word", [
        ("A419", 1, "infectious"),
        ("C349", 2, "Neoplasms"),
        ("D509", 3, "blood"),          # same letter as Neoplasms, different chapter
        ("E119", 4, "Endocrine"),
        ("H409", 7, "eye"),
        ("H903", 8, "ear"),            # same letter as Eye, different chapter
        ("I500", 9, "circulatory"),
        ("J189", 10, "respiratory"),
        ("O800", 15, "Pregnancy"),
        ("S72001A", 19, "Injury"),
        ("Z9889", 21, "Factors"),
    ])
    def test_a_code_lands_in_its_chapter(self, ingest, code, number, word):
        got_no, got_title = ingest.chapter_for(code)
        assert got_no == number, f"{code} -> chapter {got_no}, expected {number}"
        assert word.lower() in (got_title or "").lower()

    def test_the_two_split_letters_do_not_collide(self, ingest):
        """The whole reason for range matching."""
        assert ingest.chapter_for("C801")[0] != ingest.chapter_for("D649")[0]
        assert ingest.chapter_for("H353")[0] != ingest.chapter_for("H611")[0]

    def test_letter_suffixed_categories_are_not_dropped(self, ingest):
        """
        CMS has added categories such as QA0. "A" sorts above "9", so a Q99
        ceiling silently drops them — they arrived with no chapter at all.
        """
        number, title = ingest.chapter_for("QA001")
        assert number == 17 and title

    def test_something_unrecognisable_returns_nothing_rather_than_guessing(
            self, ingest):
        assert ingest.chapter_for("")[0] is None
        assert ingest.chapter_for("??")[0] is None


class TestCmOrderFile:
    """Fixed-width: code at 6:13, billable flag at 14, short description from 16."""

    def _line(self, order, code, billable, desc):
        return f"{order:>5} {code:<7} {billable} {desc}"

    def test_it_reads_codes_flags_and_descriptions(self, ingest):
        order = "\n".join([
            self._line(1, "A00", "0", "Cholera"),
            self._line(2, "A000", "1", "Cholera due to Vibrio cholerae"),
        ]).encode()
        rows = ingest.parse_cm(order, None)
        assert [r["code"] for r in rows] == ["A00", "A000"]
        assert rows[0]["is_billable"] is False      # a category, not codeable
        assert rows[1]["is_billable"] is True
        assert rows[0]["chapter_no"] == 1

    def test_the_long_description_wins_when_supplied(self, ingest):
        order = self._line(1, "A000", "1", "Cholera d/t V cholerae").encode()
        long = b"A000    Cholera due to Vibrio cholerae 01, biovar cholerae"
        rows = ingest.parse_cm(order, long)
        assert rows[0]["description"].endswith("biovar cholerae")
        # the short one is kept too — it is what fits in a narrow column
        assert rows[0]["short_description"] == "Cholera d/t V cholerae"


class TestPcsTables:
    """
    PCS is defined as tables: characters 1-3 fix the table, and each row
    enumerates valid values for 4-7. Every permitted combination is a real
    code, and nothing else is.
    """

    XML = b"""<ICD10PCS.tabular>
      <pcsTable>
        <axis pos="1"><label code="0">Medical and Surgical</label></axis>
        <axis pos="2"><label code="D">Gastrointestinal System</label></axis>
        <axis pos="3"><label code="T">Resection</label></axis>
        <pcsRow>
          <axis pos="4"><label code="J">Appendix</label></axis>
          <axis pos="5"><label code="0">Open</label><label code="4">Percutaneous Endoscopic</label></axis>
          <axis pos="6"><label code="Z">No Device</label></axis>
          <axis pos="7"><label code="Z">No Qualifier</label></axis>
        </pcsRow>
      </pcsTable>
    </ICD10PCS.tabular>"""

    def test_it_expands_every_valid_combination(self, ingest):
        rows, axes = ingest.parse_pcs(self.XML)
        assert {r["code"] for r in rows} == {"0DTJ0ZZ", "0DTJ4ZZ"}
        assert all(len(r["code"]) == 7 for r in rows)

    def test_each_code_keeps_its_seven_titles(self, ingest):
        _rows, axes = ingest.parse_pcs(self.XML)
        one = [a for a in axes if a["code"] == "0DTJ4ZZ"][0]
        assert one["root_operation"] == "Resection"
        assert one["body_part"] == "Appendix"
        assert one["approach"] == "Percutaneous Endoscopic"
        assert one["body_system"] == "Gastrointestinal System"

    def test_the_description_reads_the_way_a_coder_reads_the_code(self, ingest):
        rows, _axes = ingest.parse_pcs(self.XML)
        text = [r for r in rows if r["code"] == "0DTJ4ZZ"][0]["description"]
        for part in ("Resection", "Appendix", "Percutaneous Endoscopic"):
            assert part in text

    def test_an_incomplete_table_is_skipped_rather_than_half_read(self, ingest):
        broken = b"""<ICD10PCS.tabular><pcsTable>
          <axis pos="1"><label code="0">Medical and Surgical</label></axis>
          <pcsRow><axis pos="4"><label code="J">Appendix</label></axis></pcsRow>
        </pcsTable></ICD10PCS.tabular>"""
        rows, axes = ingest.parse_pcs(broken)
        assert rows == [] and axes == []


class TestCmTabularFallback:
    """
    The tabular XML is the fallback when there is no route to cms.gov.

    It gives S72.001 once with a <sevenChrDef> listing A, B, C… and expects the
    reader to combine them, where the order file ships the combinations already
    made. Not expanding them cost about a third of all billable codes —
    overwhelmingly injury and obstetric, which is most of what a trauma chart
    contains. Verified against the downloaded order file: with expansion, every
    code the order file carries is present and every billable flag agrees.
    """

    XML = b"""<ICD10CM.tabular><chapter><section>
      <diag><name>E11</name><desc>Type 2 diabetes mellitus</desc>
        <diag><name>E11.9</name><desc>Type 2 diabetes without complications</desc></diag>
      </diag>
    </section></chapter></ICD10CM.tabular>"""

    def test_a_parent_is_a_header_and_a_leaf_is_billable(self, ingest):
        rows = {r["code"]: r for r in ingest.parse_cm_xml(self.XML)}
        assert rows["E11"]["is_billable"] is False
        assert rows["E119"]["is_billable"] is True

    def test_the_dot_is_stripped_so_lookups_match_what_users_type(self, ingest):
        rows = {r["code"] for r in ingest.parse_cm_xml(self.XML)}
        assert "E119" in rows and "E11.9" not in rows


class TestSeventhCharacterExpansion:
    """
    The gap that made the offline path useless for trauma and obstetrics.
    """

    XML = b"""<ICD10CM.tabular><chapter><section>
      <diag><name>S72.00</name><desc>Fracture of unspecified part of neck of femur</desc>
        <sevenChrDef>
          <extension char="A">initial encounter for closed fracture</extension>
          <extension char="B">initial encounter for open fracture type I</extension>
          <extension char="D">subsequent encounter</extension>
        </sevenChrDef>
        <diag><name>S72.001</name><desc>Fracture of unspecified part of neck of right femur</desc></diag>
      </diag>
    </section></chapter></ICD10CM.tabular>"""

    def test_the_seventh_character_is_expanded(self, ingest):
        codes = {r["code"] for r in ingest.parse_cm_xml(self.XML)}
        assert {"S72001A", "S72001B", "S72001D"} <= codes

    def test_the_stem_becomes_a_header_because_nobody_codes_to_it(self, ingest):
        rows = {r["code"]: r for r in ingest.parse_cm_xml(self.XML)}
        assert rows["S72001"]["is_billable"] is False
        assert rows["S72001A"]["is_billable"] is True

    def test_the_extension_meaning_joins_the_description(self, ingest):
        rows = {r["code"]: r for r in ingest.parse_cm_xml(self.XML)}
        assert rows["S72001A"]["description"].endswith(
            "initial encounter for closed fracture")
        assert "right femur" in rows["S72001A"]["description"]

    def test_a_definition_applies_to_the_whole_subtree_beneath_it(self, ingest):
        """S72.00 holds the definition; S72.001 beneath it inherits."""
        codes = {r["code"] for r in ingest.parse_cm_xml(self.XML)}
        assert "S72001A" in codes, "the child did not inherit the definition"

    def test_short_stems_are_padded_with_the_placeholder(self, ingest):
        """ICD-10-CM uses X to hold a position, so E08.32 + '1' is E0832X1."""
        xml = b"""<ICD10CM.tabular><chapter><section>
          <diag><name>E08.32</name><desc>Diabetes with retinopathy</desc>
            <sevenChrDef><extension char="1">right eye</extension></sevenChrDef>
          </diag>
        </section></chapter></ICD10CM.tabular>"""
        codes = {r["code"] for r in ingest.parse_cm_xml(xml)}
        assert "E0832X1" in codes


class TestHcpcsLevelTwo:
    """
    The CMS ANWEB fixed-width file: code at 1-5, sequence at 6-10, long
    description at 12-91, short at 92-119, termination date at 285-292.
    """

    def _rec(self, code, seq, long_desc, short="", term=""):
        # 5 code + 5 sequence + 1 record type, then the description at 12.
        line = f"{code:>5}{seq:0>5}3{long_desc:<80}{short:<28}"
        line = line.ljust(284) + f"{term:<8}"
        return line

    def test_it_reads_codes_and_their_descriptions(self, ingest):
        raw = "\n".join([
            self._rec("J1885", 1, "Injection, ketorolac tromethamine, per 15 mg",
                      "Ketorolac tromethamine inj"),
        ]).encode("latin-1")
        codes, mods = ingest.parse_hcpcs(raw)
        assert [c["code"] for c in codes] == ["J1885"]
        assert codes[0]["description"].startswith("Injection, ketorolac")
        assert codes[0]["short_description"] == "Ketorolac tromethamine inj"
        assert mods == []

    def test_a_description_split_across_records_is_joined_back(self, ingest):
        """
        CMS wraps at eighty columns and repeats the code. Keeping one record
        per code truncated modifier TC to its seventh fragment, which reads as
        a sentence about portable x-ray suppliers and nothing about TC.
        """
        raw = "\n".join([
            self._rec("TC", 1, "Technical component; a charge may be made for",
                      "Technical component"),
            self._rec("TC", 2, "the technical component alone"),
        ]).encode("latin-1")
        _codes, mods = ingest.parse_hcpcs(raw)
        assert mods[0]["description"] == (
            "Technical component; a charge may be made for "
            "the technical component alone")

    def test_fragments_are_joined_in_sequence_not_file_order(self, ingest):
        raw = "\n".join([
            self._rec("GA", 2, "second half"),
            self._rec("GA", 1, "first half"),
        ]).encode("latin-1")
        _codes, mods = ingest.parse_hcpcs(raw)
        assert mods[0]["description"] == "first half second half"

    def test_two_character_entries_are_modifiers_not_codes(self, ingest):
        """
        The file right-justifies both into the same column. A modifier box is
        the least self-explanatory field on the form, so they are worth keeping
        — but they are not codes and must not appear in code completion.
        """
        raw = "\n".join([
            self._rec("A4550", 1, "Surgical trays", "Surgical trays"),
            self._rec("LT", 1, "Left side", "Left side"),
        ]).encode("latin-1")
        codes, mods = ingest.parse_hcpcs(raw)
        assert [c["code"] for c in codes] == ["A4550"]
        assert [m["code"] for m in mods] == ["LT"]
        assert mods[0]["code_system"] == "HCPCSMOD"

    def test_a_terminated_code_keeps_its_description_but_is_not_billable(
            self, ingest):
        """
        Dropping it would render as "unrecognised" against a code someone
        typed, when the truth is "real, but retired".
        """
        raw = self._rec("Q4100", 1, "Skin substitute, nos", "Skin sub nos",
                        term="20231231").encode("latin-1")
        codes, _mods = ingest.parse_hcpcs(raw)
        assert codes[0]["is_billable"] is False
        assert codes[0]["description"] == "Skin substitute, nos"

    def test_the_dates_are_read_from_the_first_record_only(self, ingest):
        """Continuation records are blank past the description."""
        raw = "\n".join([
            self._rec("Q4100", 1, "Skin substitute", "Skin sub", term="20231231"),
            self._rec("Q4100", 2, "of some kind"),
        ]).encode("latin-1")
        codes, _mods = ingest.parse_hcpcs(raw)
        assert codes[0]["is_billable"] is False

    def test_the_file_is_latin_one_not_utf_eight(self, ingest):
        raw = self._rec("A4550", 1, "Tray, 45\xb0 angle", "Tray").encode("latin-1")
        codes, _mods = ingest.parse_hcpcs(raw)
        assert "45" in codes[0]["description"]


class TestCcMccAppendix:
    """
    Appendix C Part 1 of the MS-DRG Definitions Manual. Parts 2 and 3 are
    conditional on facts this app does not hold — discharge status, and the DRG
    the chart groups to — and flattening them in would produce a list that
    disagrees with the manual in exactly the cases a trainer would query.
    """

    TXT = b"""Appendix C is a list of all of the codes...

Appendix C Part 1: List of CC and Major CC Codes
 I10 Dx  Lev PDX Exclusions   ICD-10-CM Description
 A000    CC  0002:3 codes     Cholera due to Vibrio cholerae
 A021    MCC 0005:60 codes    Salmonella sepsis
 N179    CC  0011:2 codes     Acute kidney failure

Appendix C Part 2: Major CC only for patients discharged alive
 J9601   MCC 0099:1 codes     Acute respiratory failure with hypoxia
"""

    def test_it_reads_the_severity_of_each_code(self, ingest):
        got = ingest.parse_cc_mcc(self.TXT)
        assert got["A000"] == "CC"
        assert got["A021"] == "MCC"
        assert got["N179"] == "CC"

    def test_part_two_is_not_read(self, ingest):
        """Major CC only for patients discharged alive — a fact we lack."""
        assert "J9601" not in ingest.parse_cc_mcc(self.TXT)

    def test_the_column_header_is_not_mistaken_for_a_code(self, ingest):
        got = ingest.parse_cc_mcc(self.TXT)
        assert "I10" not in got and "DX" not in got

    def test_the_preamble_before_part_one_is_skipped(self, ingest):
        assert ingest.parse_cc_mcc(b"CC and MCC are explained here\n") == {}

    def test_codes_are_stored_the_way_they_are_looked_up(self, ingest):
        """Bare, no decimal point — matching how the code tables store them."""
        got = ingest.parse_cc_mcc(
            b"Appendix C Part 1:\n N17.9   CC  0011:2 codes  Acute kidney\n")
        assert got == {"N179": "CC"}
