"""
A search box must not disappear as a result of searching.

PracticeLab gated its whole filter bar — status tabs, search field and all — on
`batches.length > 0`. But `batches` is the SERVER-filtered list, so a query
matching no batch NAME unmounted the search box that created the query. Direct
assignments arrive from a different call and are not server filtered, so they
kept rendering: rows on screen, no search field, and the empty-state "Clear
search" button absent because the list was not empty. The only way out was
reloading the page.

The auditor screen had the milder version: the field never hid, but there was
no clear affordance at all — not on the field, not in the empty state.

Both are the same rule. The control that creates a state has to remain
available to undo it. These read the source because the fault is structural —
what a component is gated on — and that is visible statically.
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"

PL = FRONTEND / "pages" / "practicelab" / "HomeView.tsx"
AUD = FRONTEND / "pages" / "auditor" / "AuditBatches.tsx"


def test_practicelab_filter_bar_is_not_gated_on_the_filtered_result():
    src = PL.read_text()
    assert "{batches.length > 0 && (" not in src, (
        "the filter bar is gated on the server-filtered list again — a search "
        "matching no batch name will unmount its own search box")
    # A live query must keep the bar up whatever the result set looks like.
    assert "!!search?.trim()" in src


def test_both_screens_offer_a_way_to_clear_a_search():
    for path in (PL, AUD):
        src = path.read_text()
        assert "setSearch('')" in src, "%s has no way to clear its search" % path.name
        # Once on the field itself, and once in the empty state — the empty
        # state alone is not enough, because the list is not always empty.
        assert src.count("setSearch('')") >= 2, (
            "%s clears its search in only one place; it needs the field "
            "affordance AND the empty-state action" % path.name)
