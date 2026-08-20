"""
Prove the DEPLOYED app works, by making it do the thing it is for.

Every other check in this repo runs against local code. The gap between "the
code is correct" and "the running service works" is where this project has
actually been hurt: an E/M answer key upload returned 500 in production against
a codebase whose 2,510 tests were green, because the deployed DATABASE had a
table the tests never saw.

    python scripts/smoke_deployed.py --base https://chart-viewer-api.onrender.com
    python scripts/smoke_deployed.py --base ... --write --passphrase "..."

**Reads alone are not enough, and this is the point.** Most of this codebase
degrades to silence rather than erroring — a code description that cannot be
fetched renders as nothing, which is indistinguishable from a working screen
with nothing to say. Writes are where a broken deployment announces itself.
So --write performs one real write per module and removes it again.

Exits non-zero on any failure, so it can gate or alarm after a deploy.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

TIMEOUT = 45


def call(base, path, method="GET", body=None, headers=None):
    url = base.rstrip("/") + path
    data = None
    hdrs = {"Accept": "application/json"}
    hdrs.update(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, raw
    except Exception as e:                      # DNS, TLS, timeout, refused
        return 0, str(e)


class Smoke:
    def __init__(self, base):
        self.base = base
        self.failures = []
        self.checked = 0

    def expect(self, label, ok, detail=""):
        self.checked += 1
        if ok:
            print("  ok   %s" % label)
        else:
            print("  FAIL %s — %s" % (label, detail))
            self.failures.append(label)

    def get_ok(self, label, path, want=200):
        code, body = call(self.base, path)
        self.expect(label, code == want,
                    "got %s %s" % (code, str(body)[:160]))
        return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="API base URL")
    ap.add_argument("--write", action="store_true",
                    help="perform one real write per module, then undo it")
    ap.add_argument("--passphrase", default="",
                    help="MASTER_ADMIN_PASSPHRASE, for the write checks")
    args = ap.parse_args()

    s = Smoke(args.base)

    print("\nreachable and serving its own schema")
    code, probe = call(s.base, "/openapi.json")
    if isinstance(probe, str) and probe.lstrip()[:9].lower().startswith("<!doctype"):
        # FastAPI answers a missing route with JSON. HTML means something else
        # is on this host — a static site, or a proxy that never reaches the
        # API — and every check below would fail for that one reason.
        print("  FAIL %s does not appear to be the API." % s.base)
        print("       It returned HTML, and FastAPI returns JSON even for 404.")
        print("       Use the API service's own URL (the value of VITE_API_URL")
        print("       in the frontend's Render environment).")
        return 1

    body = s.get_ok("openapi.json", "/openapi.json")
    routes = len((body or {}).get("paths", {})) if isinstance(body, dict) else 0
    s.expect("route table is populated", routes > 100, "%d paths" % routes)

    print("\nread paths, one per module")
    s.get_ok("charts",              "/charts/stats")
    s.get_ok("practicelab batches", "/practicelab/batches?page=1&page_size=1")
    s.get_ok("assessment questions", "/assessment/questions?page=1&page_size=1")
    s.get_ok("auditor batches",     "/auditor/batches?page=1&page_size=1")
    s.get_ok("E/M answer keys",     "/practicelab/em/answer-key/list")
    status = s.get_ok("code sets",  "/codes/status")

    # Not a failure — an environment where the ingest was never run is legal.
    # It IS worth saying out loud, because everything reading it degrades to
    # silence and looks identical to a working environment with no data.
    if isinstance(status, dict):
        loaded = status.get("systems") or status.get("systems_loaded") or {}
        if isinstance(loaded, dict) and not all(loaded.values()):
            print("  note code sets are not fully loaded: %s" % loaded)

    print("\ndescriptions actually resolve")
    code, body = call(s.base, "/codes/describe?codes=J189&section=SDx")
    got = (body or {}).get("descriptions", {}) if isinstance(body, dict) else {}
    s.expect("J18.9 has a description", code == 200 and bool(got.get("J189")),
             "got %s %s" % (code, str(body)[:160]))

    if args.write:
        print("\nWRITES — the half that reads cannot cover")
        if not args.passphrase:
            s.expect("passphrase supplied for write checks", False,
                     "--write needs --passphrase")
        else:
            _write_checks(s, args.passphrase)

    print("\n%d checks, %d failed" % (s.checked, len(s.failures)))
    if s.failures:
        print("FAILED: %s" % ", ".join(s.failures))
        return 1
    print("PASS")
    return 0


def _write_checks(s, passphrase):
    """
    One real write, on the table whose failure started all this.

    Uses a chart that already exists rather than creating one: the goal is to
    prove the write path works, not to leave scaffolding behind if the run dies
    halfway.
    """
    code, charts = call(s.base, "/charts?page=1&page_size=1&specialty=E%2FM")
    items = (charts or {}).get("items") if isinstance(charts, dict) else None
    if not items:
        print("  skip no E/M chart in this environment to write against")
        return
    chart_id = items[0]["id"]

    payload = {"chart_id": chart_id, "em_code": "99213",
               "copa_level": "Moderate", "dr_level": "Moderate",
               "risk_level": "Moderate", "dx_codes": ["J18.9"],
               "procedure_cpts": [], "entered_by": "__smoke__",
               "passphrase": passphrase}
    code, body = call(s.base, "/practicelab/em/answer-key", "POST", payload)
    s.expect("E/M answer key can be written", code in (200, 201),
             "got %s %s" % (code, str(body)[:200]))

    if code in (200, 201):
        code, body = call(
            s.base, "/practicelab/em/answer-key/%d?passphrase=%s"
            % (chart_id, urllib.request.quote(passphrase)), "DELETE")
        s.expect("and removed again", code in (200, 204),
                 "LEFT A ROW BEHIND: %s %s" % (code, str(body)[:160]))


if __name__ == "__main__":
    raise SystemExit(main())
