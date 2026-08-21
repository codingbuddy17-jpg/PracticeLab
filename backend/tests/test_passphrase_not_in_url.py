"""
The master passphrase must not have to travel in the query string.

It is the one shared credential gating chart retirement, key deletion,
force-close and the question bank — and fifteen endpoints declared it as
`passphrase: str = Query(...)`, so every use wrote it into server, proxy and
CDN access logs. The answer-key export was worse: the frontend opened it as a
URL, so the credential also entered browser history.

Rewriting fifteen signatures across three modules is the riskier change, so a
single middleware accepts the value from a header and hands it on. The query
parameter still works — anything not yet migrated keeps functioning — but
nothing has to use it.
"""
from conftest import make_chart
from models import AnswerKey, Specialty
from tests.test_auditor_api import PASS

HEADER = "X-Admin-Passphrase"


def _keyed(db):
    chart = make_chart(db, specialty="IP-DRG")
    db.add(AnswerKey(chart_id=chart.id, specialty=Specialty.IP_DRG,
                     pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[], cpt=[],
                     entered_by="t"))
    db.commit()
    return chart


class TestTheHeaderIsAccepted:
    def test_a_gated_endpoint_accepts_the_header(self, client, db):
        _keyed(db)
        r = client.get("/practicelab/answer-key/export", headers={HEADER: PASS})
        assert r.status_code == 200, r.text

    def test_the_query_parameter_still_works(self, client, db):
        """Nothing is broken for a call site that has not been migrated."""
        _keyed(db)
        r = client.get("/practicelab/answer-key/export",
                       params={"passphrase": PASS})
        assert r.status_code == 200, r.text

    def test_a_wrong_header_is_refused(self, client, db):
        _keyed(db)
        r = client.get("/practicelab/answer-key/export", headers={HEADER: "wrong"})
        assert r.status_code in (400, 403), r.status_code

    def test_no_credential_at_all_is_refused(self, client, db):
        _keyed(db)
        r = client.get("/practicelab/answer-key/export")
        assert r.status_code in (400, 403, 422), r.status_code

    def test_the_query_parameter_wins_when_both_are_sent(self, client, db):
        """
        The shim must not override an explicit parameter — otherwise a stale
        header in some client could silently replace the value a caller meant.
        """
        _keyed(db)
        r = client.get("/practicelab/answer-key/export",
                       params={"passphrase": "wrong"}, headers={HEADER: PASS})
        assert r.status_code in (400, 403), r.status_code


class TestTheFrontendStopsPuttingItInTheUrl:
    def test_the_answer_key_export_is_no_longer_opened_as_a_url(self):
        """
        window.open cannot carry a header, so this one had to change shape:
        it fetches with the header and saves the blob. That is what keeps the
        credential out of browser history.
        """
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
               / "api" / "practicelabApi.ts").read_text()
        assert "URLSearchParams({ passphrase })" not in src, (
            "the passphrase is still being built into an export URL")

    def test_no_api_module_puts_it_in_a_query_string(self):
        """
        Per FILE, not per call: one migrated export in a module full of query
        parameters would read as done. Both export helpers and every axios call
        site now send it as a header.
        """
        import pathlib
        api = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "api"
        offenders = []
        for f in sorted(api.glob("*.ts")):
            for n, line in enumerate(f.read_text().split("\n"), 1):
                if "passphrase" not in line or "adminAuth" in line:
                    continue
                if "params:" in line or "URLSearchParams" in line:
                    offenders.append("%s:%d %s" % (f.name, n, line.strip()[:70]))
        assert offenders == [], (
            "the master passphrase is still going into a query string:\n  "
            + "\n  ".join(offenders))
