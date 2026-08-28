"""
Clearing the chart search returns the page to the state it started in.

The × inside the search box only emptied the text. `hasSearched` stayed true,
so the screen kept its searched layout — with an empty box and the previous
results still listed underneath.

The two layouts differ by more than the list, which is why it was noticeable at
all: Recently Viewed is hidden once a search is running, and Coding Resources
moves from full cards at the foot of the page to a compact strip at the top. So
"I cleared the search" and "I am back where I started" looked like different
screens, and the give-away was where the Resources section had gone.

Read from the source, because the fault is which state a control resets — that
is visible statically, and no amount of rendering would have made it clearer.
"""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages"
       / "CoderHome.tsx").read_text()


def _fn_body(name: str) -> str:
    i = SRC.index("const %s = " % name)
    return SRC[i:SRC.index("\n  }", i)]


def test_the_two_layouts_really_do_differ():
    """
    Guards the guard. If nothing were keyed on hasSearched, resetting it would
    not matter and the test below would be checking a value nobody reads.
    """
    keyed = re.findall(r"\{[^{}\n]*hasSearched[^{}\n]*&& \(", SRC)
    assert len(keyed) >= 3, (
        "expected Recently Viewed and both Resources layouts to depend on "
        "hasSearched; found %d such blocks" % len(keyed))


def test_the_clear_button_calls_the_full_reset():
    """It used to be an inline setQuery('') and nothing else."""
    m = re.search(r"clearInputBtn[^>]*onClick=\{(\w+)\}", SRC)
    assert m, "the clear button in the search box could not be found"
    assert m.group(1) == "clearQuery", (
        "the × calls %s; an inline handler is how this regressed before"
        % m.group(1))


def test_clearing_resets_everything_the_layout_reads():
    body = _fn_body("clearQuery")
    for state in ("setQuery", "setHasSearched", "setResults", "setTotal"):
        assert state in body, "clearQuery does not reset %s" % state


def test_clearing_with_filters_active_re_searches_rather_than_emptying():
    """
    Filters are a separate control. Wiping a specialty the coder never touched
    would be a different surprise, and leaving the old results under an empty
    box is the bug this fixes — so it re-runs on what remains.
    """
    body = _fn_body("clearQuery")
    assert "hasFilters" in body
    assert re.search(r"doSearch\(1,\s*''\)", body), (
        "clearing with filters active must re-run the search on those filters")


def test_the_re_search_passes_the_new_value_rather_than_reading_state():
    """
    setQuery has not landed when clearQuery runs, so a doSearch that read
    `query` back would search for the text that was just cleared.
    """
    i = SRC.index("const doSearch =")
    head = SRC[i:i + 400]
    assert "qOverride" in head, "doSearch cannot be given an explicit query"
    assert "const q = qOverride !== undefined ? qOverride : query" in head
