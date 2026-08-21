"""
No React hook may sit below an early return.

React error #310 — "rendered more hooks than during the previous render" — is
what happens when a component bails out with `if (loading) return ...` before
reaching a `useMemo`. The first render runs the hooks above the return; the
next runs those plus the ones below, and React throws. The component is
replaced by an error boundary.

Two of these were live in production at once:

  * the assessment Question Signals tab, which crashed and took the whole
    analytics view down with it — Matrix and Coder became unreachable
  * the IP/OP answer key editor, which I broke myself by adding four
    description lookups below its `if (loading)` guard, and did not notice
    because I never opened the screen

Both were found by clicking, not by reading, and neither the type checker nor
2,600 tests said a word. This test reads the source: a component's hooks must
all appear before its first early return.
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"

HOOK = re.compile(r"^\s{0,6}(?:const|let)\s.*=\s*use(?:Memo|State|Effect|Callback|Ref|Pagination|CodeDescriptions|SearchParams|Params|Navigate)\s*\(")
# A component-level bail-out: `if (...) return <jsx>` or `return null`, at the
# indentation of a function body rather than nested inside a callback.
EARLY_RETURN = re.compile(r"^  if \(.*\)\s*return\s*(?:<|null|$)|^  if \(.*\)\s*\{\s*$")
# Where a new function starts at the top level. Hooks reset per function, so
# the scan does — including CUSTOM hooks, whose names are lower-case. Missing
# those made this test report a false failure on a helper defined below a
# component that returns early, which is a different and legal thing.
COMPONENT = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:function\s+\w+|const\s+\w+\s*=\s*(?:\(|function))")


def _offenders(path: pathlib.Path):
    out, returned_at = [], None
    for n, line in enumerate(path.read_text().split("\n"), 1):
        if COMPONENT.match(line):
            returned_at = None
            continue
        if returned_at is None and EARLY_RETURN.match(line) and "return" in line:
            # Only a real bail-out, not `if (x) { setState(...) }`
            if "return" in line:
                returned_at = n
            continue
        if returned_at and HOOK.match(line):
            out.append((n, returned_at, line.strip()[:60]))
    return out


def test_no_hook_sits_below_an_early_return():
    bad = []
    for path in sorted(SRC.rglob("*.tsx")):
        for hook_line, ret_line, text in _offenders(path):
            bad.append("%s:%d — hook after the early return on line %d: %s"
                       % (path.relative_to(SRC), hook_line, ret_line, text))
    assert bad == [], (
        "React hooks below an early return crash with error #310 as soon as "
        "the early branch is taken on one render and not the next:\n  "
        + "\n  ".join(bad))
