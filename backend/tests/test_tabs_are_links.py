"""
Every module's tab bar must be links, not buttons.

A tab rendered as `<button onClick={() => navigate(...)}>` looks identical and
behaves identically for a plain click — and gives the browser nothing to act
on. Cmd/Ctrl-click, middle-click, "Open in new tab", "Copy link address" and
the Back button all do nothing or the wrong thing.

The Assessment module has always done this properly; PracticeLab and Auditor
had not, and a trainer found it. Static assertions, because the frontend has no
test runner and adding one would be a new dependency — they pin intent.
"""
import pathlib
import re

PAGES = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages")

MODULES = {
    "Assessment": PAGES / "assessment" / "AssessmentHome.tsx",
    "Auditor": PAGES / "TrainerAuditor.tsx",
    "PracticeLab": PAGES / "TrainerPracticeLab.tsx",
}


def _tab_render_block(src: str) -> str:
    """
    The JSX that renders the tab bar.

    Anchored on `.map(t => (`, with the opening paren: that is the render form.
    `TABS.map(t => t.key)` builds an array of keys and is not a tab bar — my
    first version of this test matched it and reported a false failure.
    """
    m = re.search(r"(TABS|tabs)\.map\(t => \((.{0,700})", src, re.S)
    return m.group(2) if m else ""


class TestEveryTabBarUsesLinks:
    def test_the_tab_list_renders_links(self):
        for name, path in MODULES.items():
            block = _tab_render_block(path.read_text())
            assert block, "%s: no tab render block found" % name
            assert "<Link" in block, (
                "%s renders its tabs as something other than a Link, so they "
                "cannot be opened in a new tab" % name)
            assert "<button" not in block, (
                "%s still has a button in its tab list" % name)

    def test_no_tab_navigates_from_an_onclick(self):
        """
        The specific shape that looks right and is not: the href is missing, so
        the browser has nothing to open.

        Scoped to the tab bar. A Back control is legitimately a button — it is
        an action, not a destination — and flagging it would have taught the
        next reader to delete this test.
        """
        for name, path in MODULES.items():
            block = _tab_render_block(path.read_text())
            offenders = re.findall(r"<button[^>]{0,200}onClick=\{\(\) => navigate\(",
                                   block, re.S)
            assert not offenders, (
                "%s navigates from a button's onClick — use a Link" % name)


class TestTheAddressBarNamesWhatIsOnScreen:
    def test_each_module_reads_its_view_from_the_url(self):
        for name, path in MODULES.items():
            src = path.read_text()
            assert ("useParams" in src or "useSearchParams" in src), (
                "%s keeps its current view in component state only, so it "
                "cannot be linked to" % name)

    def test_a_practicelab_batch_is_addressable(self):
        """
        Not just the tab: the thing a trainer actually wants to send someone.
        """
        src = MODULES["PracticeLab"].read_text()
        assert "searchParams.get('batch')" in src
        assert "&batch=${id}" in src, "opening a batch does not reach the URL"

class TestAnalyticsSubTabsAreAddressableToo:
    """
    The module tabs were made linkable first; the ~20 analytics views inside
    them were not, so a trainer could send "Analytics" but not "Analytics →
    E/M" — and Back left the module rather than returning to the previous view.

    PracticeLab additionally remembered the last view in localStorage, which
    survives a reload but cannot be sent to anyone. The URL now wins over it.
    """
    SUBTABBED = {
        "Auditor": PAGES / "auditor" / "AuditAnalytics.tsx",
        "PracticeLab": PAGES / "practicelab" / "PLAnalyticsView.tsx",
        "Assessment": PAGES / "assessment" / "AnalyticsView.tsx",
    }

    def test_each_reads_its_view_from_the_url(self):
        for name, path in self.SUBTABBED.items():
            src = path.read_text()
            assert "useSearchParams" in src, "%s keeps its analytics view in state only" % name
            assert "'view'" in src or '"view"' in src, "%s has no ?view= parameter" % name

    def test_each_renders_those_tabs_as_links(self):
        import re
        for name, path in self.SUBTABBED.items():
            src = path.read_text()
            m = re.search(r"TABS\.map\(t => \((.{0,260})", src, re.S)
            assert m, "%s: no tab render block" % name
            assert "<Link" in m.group(1), (
                "%s renders analytics tabs as something other than a Link" % name)

    def test_practicelab_scoring_config_is_addressable(self):
        """
        It used to show while the address bar still named the tab you opened it
        from, so a copied link went elsewhere and a refresh changed the page.
        """
        src = (PAGES / "TrainerPracticeLab.tsx").read_text()
        assert "view=scoring-config" in src
