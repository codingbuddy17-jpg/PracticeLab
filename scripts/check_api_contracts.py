"""
Two mechanical API checks, both prompted by bugs that reached production:

1. ROUTE SHADOWING — FastAPI matches in registration order, so a parameterised
   route registered before a static sibling swallows it. /em/answer-key/template
   was parsed as a chart_id and 422'd; the endpoint had never once run.

2. UI -> API CONTRACT — every path the frontend calls must exist on the backend.
   The answer-key upload posted specialty="OP", which is not a Specialty value,
   so it 400'd for every specialty; and coder lookups hit paths that had moved.

Run: python3 scripts/check_api_contracts.py
"""
import os
import re
import sys
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
BE = REPO / "backend"
FE = REPO / "frontend" / "src"

failures = []


def fail(msg):
    failures.append(msg)
    print(f"  FAIL  {msg}")


def ok(msg):
    print(f"  PASS  {msg}")


# ── 1. Route shadowing ──────────────────────────────────────────────────────

# [^"\']* not + — a router with its own prefix registers its root as @router.get("")
ROUTE_RE = re.compile(r'@router\.(get|post|put|delete|patch)\(\s*["\']([^"\']*)["\']')


def check_shadowing():
    print("1. ROUTE SHADOWING (parameterised route registered before a static sibling)")
    clean = True
    for path in sorted(BE.rglob("routers/**/*.py")):
        routes = [(m.group(1), m.group(2), m.start())
                  for m in ROUTE_RE.finditer(path.read_text())]
        # group by method — only same-method routes can shadow each other
        by_method = {}
        for method, route, pos in routes:
            by_method.setdefault(method, []).append((route, pos))

        for method, entries in by_method.items():
            for i, (route, pos) in enumerate(entries):
                if "{" not in route:
                    continue
                prefix = route.split("{")[0]
                depth = route.count("/")
                for later_route, later_pos in entries[i + 1:]:
                    if "{" in later_route:
                        continue
                    if later_route.startswith(prefix) and later_route.count("/") == depth:
                        fail(f"{path.relative_to(REPO)}: {method.upper()} {later_route} "
                             f"is shadowed by {route} registered earlier")
                        clean = False
    if clean:
        ok("no static route is shadowed by an earlier parameterised one")


# ── 2. UI -> API contract ───────────────────────────────────────────────────

CALL_RE = re.compile(r"""api\.(get|post|put|delete|patch)\(\s*[`'"]([^`'"]+)[`'"]""")
OPEN_RE = re.compile(r"""(?:VITE_API_URL \|\| '/api'\})([^`'"]+)""")


def frontend_calls():
    calls = set()
    for path in FE.rglob("*.ts*"):
        text = path.read_text()
        for m in CALL_RE.finditer(text):
            calls.add((m.group(1), m.group(2), str(path.relative_to(REPO))))
        for m in OPEN_RE.finditer(text):
            calls.add(("get", m.group(1), str(path.relative_to(REPO))))
    return calls


def backend_routes():
    """Prefix each sub-router's paths with the prefix its aggregator applies."""
    prefixes = {}
    for agg in BE.rglob("routers/*.py"):
        text = agg.read_text()
        m = re.search(r'APIRouter\(prefix=["\']([^"\']+)["\']', text)
        if m:
            prefixes[agg.stem] = m.group(1)

    routes = set()
    for path in sorted(BE.rglob("routers/**/*.py")):
        text = path.read_text()
        # A router may declare its own prefix rather than inherit one from an
        # aggregator (routers/resources.py does this) — prefer the local one.
        local = re.search(r'APIRouter\(prefix=["\']([^"\']+)["\']', text)
        if local:
            prefix = local.group(1)
        elif path.parent.name == "routers":
            prefix = prefixes.get(path.stem, "")
        else:
            prefix = prefixes.get(path.parent.name.replace("_pkg", ""), "")
        for m in ROUTE_RE.finditer(text):
            routes.add((m.group(1), prefix + m.group(2)))
    return routes


def normalise(p: str) -> str:
    """Collapse path params and template literals so shapes can be compared."""
    p = p.split("?")[0].rstrip("/")
    p = re.sub(r"\$\{[^}]+\}", "{}", p)
    p = re.sub(r"\{[^}]+\}", "{}", p)
    return p


def check_contract():
    print("\n2. UI -> API CONTRACT (every path the frontend calls exists)")
    backend = {(m, normalise(r)) for m, r in backend_routes()}
    missing = []
    for method, call, where in sorted(frontend_calls()):
        n = normalise(call)
        if not n.startswith("/"):
            continue
        if (method, n) in backend:
            continue
        # aggregator prefixes vary; accept a unique suffix match
        if any(b.endswith(n) and m == method for m, b in backend):
            continue
        missing.append((method.upper(), call, where))

    if not missing:
        ok(f"all {len(frontend_calls())} frontend calls resolve to a backend route")
    else:
        for method, call, where in missing:
            fail(f"{method} {call}  — called from {where}, no matching backend route")


if __name__ == "__main__":
    check_shadowing()
    check_contract()
    print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} ISSUE(S)"))
    sys.exit(1 if failures else 0)
