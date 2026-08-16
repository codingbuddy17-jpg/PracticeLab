"""
Load the CMS code sets into this application's database.

    python scripts/ingest_code_sets.py                 # report only
    python scripts/ingest_code_sets.py --write         # and save
    python scripts/ingest_code_sets.py --from-dir DIR --write   # no download

Ports the parsing from the DRGpulse seeder and points the writes here instead,
so this application depends on CMS rather than on another application. The
files are public domain — ICD-10-CM, ICD-10-PCS and HCPCS Level II. CPT is not
included: it is AMA copyright, licensed per user, and this repository is
public.

Deliberately a STANDALONE SCRIPT and never wired into init_db(). That function
runs on every boot, and hanging a multi-megabyte download off it would make
every deploy slow and turn a CMS outage into a failed startup. Run it when a
new edition is published — annually for ICD, quarterly for HCPCS.

--from-dir reads files already on disk instead of downloading. An internal
environment may have no outbound route to cms.gov, and the IT team migrating
this will need a path that does not assume one. It falls back to the tabular
XML and expands the seventh characters itself, which was verified against the
downloaded order file: every code the order file carries is present and every
billable flag agrees.
"""
import argparse
import datetime
import io
import os
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from typing import Iterable, Optional

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

for key in ("STORAGE_ENDPOINT_URL", "STORAGE_ACCESS_KEY", "STORAGE_SECRET_KEY",
            "STORAGE_BUCKET_NAME", "STORAGE_PUBLIC_URL", "MASTER_ADMIN_PASSPHRASE"):
    os.environ.setdefault(key, "x")

from database import Base, SessionLocal, engine  # noqa: E402
# Shared with the auditor analytics, which groups planted errors by chapter.
from services.icd_chapters import CHAPTERS, chapter_for  # noqa: E402,F401
# Shared with the trainer panel, which judges whether a load is still current
# by these same dates. Split, the app could call something stale that the
# ingest thinks is current.
from services.code_editions import fiscal_year  # noqa: E402
from models import CodeDescription, CodeSetVersion, PcsCodeAxis  # noqa: E402

# ── where the files live ─────────────────────────────────────────────────────
#
# Built from TODAY'S DATE rather than written down. A hardcoded list is right
# on the day it is written and silently wrong afterwards: a scheduled run would
# keep fetching the same edition forever while reporting success, which is the
# worst failure available — stale data that looks loaded.
#
# Each list is tried in order and the first that answers wins, so the newest
# edition is preferred and the previous one is the fallback. That also covers
# the window each autumn when the next year exists as a date but not yet as a
# published file.

def cm_urls(today=None) -> list:
    out = []
    fy = fiscal_year(today)
    for year in (fy, fy - 1):
        out.append(f"https://www.cms.gov/files/zip/{year}-code-descriptions-"
                   f"tabular-order-updated-0101{year}.zip")
        out.append(f"https://www.cms.gov/files/zip/{year}-code-descriptions-"
                   f"tabular-order.zip")
    return out


def pcs_code_urls(today=None) -> list:
    """
    The PCS CODES file, which carries the real description of each code.

    Separate from the tables file, and it has to be: the tables define which
    codes EXIST, character by character, but joining those seven axis titles
    together does not produce what CMS calls the code. Joined, 0210083 reads
    "Bypass, Coronary Artery, One Artery, Heart and Great Vessels, Open,
    Zooplastic Tissue, Coronary Artery" — a character-by-character breakdown.
    CMS's own description is "Bypass Coronary Artery, One Artery from Coronary
    Artery with Zooplastic Tissue, Open Approach", which is the sentence a
    coder actually reads.
    """
    out = []
    fy = fiscal_year(today)
    for year in (fy, fy - 1):
        out.append(f"https://www.cms.gov/files/zip/{year}-icd-10-pcs-codes-"
                   f"file-updated-0101{year}.zip")
        out.append(f"https://www.cms.gov/files/zip/{year}-icd-10-pcs-codes-"
                   f"file.zip")
    return out


def pcs_urls(today=None) -> list:
    out = []
    fy = fiscal_year(today)
    for year in (fy, fy - 1):
        out.append(f"https://www.cms.gov/files/zip/{year}-icd-10-pcs-code-"
                   f"tables-and-index-updated-0101{year}.zip")
        out.append(f"https://www.cms.gov/files/zip/{year}-icd-10-pcs-code-"
                   f"tables-and-index.zip")
    return out


def hcpcs_urls(today=None) -> list:
    """
    HCPCS is republished QUARTERLY and named for the quarter's first month, so
    the candidates walk back through five quarters — enough that a run early in
    a new quarter still finds the previous one.
    """
    today = today or datetime.date.today()
    quarters = ["january", "april", "july", "october"]
    q = (today.month - 1) // 3
    year = today.year
    out = []
    for _ in range(5):
        out.append(f"https://www.cms.gov/files/zip/{quarters[q]}-{year}-"
                   f"alpha-numeric-hcpcs-file.zip")
        q -= 1
        if q < 0:
            q, year = 3, year - 1
    return out


def drg_urls(today=None) -> list:
    """
    MS-DRG Definitions Manual, for Appendix C — the published CC/MCC list.
    The version number tracks the fiscal year: FY2026 is v43.
    """
    fy = fiscal_year(today)
    return [f"https://www.cms.gov/files/zip/icd-10-ms-drg-definitions-manual-"
            f"files-v{year - 1983}.zip" for year in (fy, fy - 1)]


EDITION = f"FY{fiscal_year()}"


def _download(urls: Iterable[str]) -> Optional[bytes]:
    import urllib.request
    for url in urls:
        try:
            print(f"  downloading {url.rsplit('/', 1)[-1]} ...")
            with urllib.request.urlopen(url, timeout=180) as r:
                return r.read()
        except Exception as exc:
            print(f"    failed: {exc}")
    return None


def _from_zip(blob: bytes, contains: str, ext: str) -> Optional[bytes]:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            low = name.lower()
            if contains in low and low.endswith(ext):
                return z.read(name)
    return None


def _local(directory: pathlib.Path, contains: str, ext: str) -> Optional[bytes]:
    for path in sorted(directory.rglob(f"*{ext}")):
        if contains in path.name.lower():
            return path.read_bytes()
    return None


# ── parsers ──────────────────────────────────────────────────────────────────

def parse_cm(order_bytes: bytes, code_bytes: Optional[bytes]) -> list[dict]:
    """
    The CMS order file is fixed-width: code at 6:13, a billable flag at 14, the
    short description from 16. The separate codes file carries the long
    description, which is the one worth showing; the short one is the fallback.
    """
    long_desc: dict[str, str] = {}
    if code_bytes:
        for line in code_bytes.decode("utf-8", "ignore").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                long_desc[parts[0].strip().upper()] = parts[1].strip()

    out = []
    for line in order_bytes.decode("utf-8", "ignore").splitlines():
        if len(line) < 16:
            continue
        code = line[6:13].strip().upper()
        if not code:
            continue
        short = line[16:77].strip()
        number, title = chapter_for(code)
        out.append({
            "code_system": "ICD10CM",
            "code": code,
            "description": long_desc.get(code, short),
            "short_description": short[:120] or None,
            "chapter": title,
            "chapter_no": number,
            "is_billable": line[14] == "1",
            "edition": EDITION,
        })
    return out


def parse_cm_xml(xml_bytes: bytes) -> list[dict]:
    """
    The CM tabular XML, for when there is no route to cms.gov.

    Codes nest: A00 contains A00.0 and so on. A <diag> with children is a
    category nobody codes to; a leaf is billable — the same distinction the
    order file's flag makes, derived from the shape instead.

    The seventh character is expanded here rather than left out. The XML gives
    S72.001 once, with a <sevenChrDef> listing A, B, C…, and expects the reader
    to combine them; the order file ships the combinations already made. Not
    expanding cost about a third of all billable codes — overwhelmingly injury
    and obstetric, which is to say most of what a trauma chart contains.

    A definition applies to the whole subtree beneath it, so it is carried down
    and overridden where a deeper one appears. Codes shorter than six
    characters are padded with X, which is the placeholder ICD-10-CM itself
    uses to hold the position.
    """
    root = ET.fromstring(xml_bytes)
    out: list[dict] = []
    seen: set = set()

    def emit(code: str, desc: str, billable: bool):
        code = code.replace(".", "").upper()
        if not code or code in seen:
            return
        seen.add(code)
        number, title = chapter_for(code)
        out.append({
            "code_system": "ICD10CM", "code": code, "description": desc,
            "short_description": desc[:120] or None,
            "chapter": title, "chapter_no": number,
            "is_billable": billable, "edition": EDITION,
        })

    def extensions_of(diag):
        node = diag.find("sevenChrDef")
        if node is None:
            return None
        found = [(e.get("char", "").strip(), (e.text or "").strip())
                 for e in node.findall("extension")]
        return [(c, t) for c, t in found if c] or None

    def walk(node, inherited):
        for diag in node.findall("diag"):
            name = (diag.findtext("name") or "").strip()
            desc = (diag.findtext("desc") or "").strip()
            children = diag.findall("diag")
            # A definition lower in the tree replaces the one above it.
            seven = extensions_of(diag) or inherited

            if name:
                if children:
                    emit(name, desc, billable=False)
                elif seven:
                    # The stem is a category once a seventh character is
                    # required — nobody codes to S72.001 itself.
                    emit(name, desc, billable=False)
                    stem = name.replace(".", "").upper().ljust(6, "X")
                    for char, meaning in seven:
                        emit(f"{stem}{char}",
                             f"{desc}, {meaning}" if meaning else desc,
                             billable=True)
                else:
                    emit(name, desc, billable=True)
            walk(diag, seven)

    for chapter in root.findall(".//chapter"):
        for section in chapter.findall("section"):
            walk(section, None)
        walk(chapter, None)
    return out


def parse_pcs(xml_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """
    PCS is positional and defined as tables: characters 1-3 fix the table, and
    each row enumerates the valid values for 4-7. Every combination the rows
    permit is a real code — and nothing else is, which is what makes this
    worth storing rather than deriving.

    Returns (descriptions, axes) for the same set of codes.
    """
    root = ET.fromstring(xml_bytes)
    descriptions, axes = [], []
    seen: set = set()

    for table in root.findall(".//pcsTable"):
        head: dict[str, tuple] = {}
        for axis in table.findall("axis"):
            pos = axis.get("pos")
            labels = axis.findall("label")
            if pos in ("1", "2", "3") and labels:
                head[pos] = (labels[0].get("code", ""), (labels[0].text or "").strip())
        if not all(p in head for p in ("1", "2", "3")):
            continue
        (c1, t1), (c2, t2), (c3, t3) = head["1"], head["2"], head["3"]

        for row in table.findall("pcsRow"):
            per_pos: dict[str, list] = {}
            for axis in row.findall("axis"):
                per_pos[axis.get("pos")] = [
                    (l.get("code", ""), (l.text or "").strip())
                    for l in axis.findall("label")
                ]
            for c4, t4 in per_pos.get("4", [("?", "")]):
                for c5, t5 in per_pos.get("5", [("?", "")]):
                    for c6, t6 in per_pos.get("6", [("Z", "No Device")]):
                        for c7, t7 in per_pos.get("7", [("Z", "No Qualifier")]):
                            code = f"{c1}{c2}{c3}{c4}{c5}{c6}{c7}"
                            if len(code) != 7 or code in seen:
                                continue
                            seen.add(code)
                            # The description IS the seven titles, which is how
                            # a coder reads the code.
                            text = ", ".join(p for p in (t3, t4, t2, t5, t6, t7) if p)
                            descriptions.append({
                                "code_system": "ICD10PCS", "code": code,
                                "description": text, "short_description": text[:120],
                                "chapter": None, "chapter_no": None,
                                "is_billable": True, "edition": EDITION,
                            })
                            axes.append({
                                "code": code, "section": t1, "body_system": t2,
                                "root_operation": t3, "body_part": t4,
                                "approach": t5, "device": t6, "qualifier": t7,
                                "edition": EDITION,
                            })
    return descriptions, axes


# ── load ─────────────────────────────────────────────────────────────────────

def parse_pcs_descriptions(txt_bytes: bytes) -> dict:
    """
    The PCS codes file: a seven-character code, whitespace, then its
    description. Returns {code: description}.
    """
    out: dict = {}
    for line in txt_bytes.decode("latin-1", "ignore").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        code = parts[0].strip().upper()
        if len(code) == 7 and parts[1].strip():
            out[code] = parts[1].strip()
    return out


def parse_hcpcs(txt_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """
    HCPCS Level II, from the CMS ANWEB fixed-width file.

    Per the CMS record layout: code at 1-5, long description at 12-91, short
    description at 92-119, termination date at 285-292. The file is latin-1,
    not UTF-8, and its line lengths vary, so every field is sliced defensively.

    Two kinds of row come back, because the file holds two kinds of thing. A
    five-character entry is a code; a two-character one is a MODIFIER, which
    the file right-justifies into the same column. Modifiers are the reason
    this is worth parsing beyond CPT-adjacent descriptions — a modifier box is
    the least self-explanatory field on the form, and nothing else in this app
    could say what 25 or 59 means.

    Terminated codes are kept but not marked billable. The description is still
    the right thing to show against a code someone typed — saying nothing would
    read as "unrecognised" when the truth is "real, but retired".

    Nothing here is CPT. Level II is the letter-prefixed set (A-V) and is
    public domain; the five-digit numeric codes are AMA copyright and are not
    in this file.
    """
    # A long description does not fit in eighty columns, so CMS SPLITS it across
    # several records for the same code, numbered in the sequence field at 6-10.
    # Taking one record per code silently truncates: modifier TC runs to seven
    # of them, and reading only the last leaves "suppliers will then be used to
    # build customary and prevailing profiles" as the whole meaning of the
    # modifier. Fragments are joined back in sequence order.
    grouped: dict = {}
    order: list = []
    for line in txt_bytes.decode("latin-1", "ignore").splitlines():
        if len(line) < 92:
            continue
        code = line[0:5].strip().upper()
        if not code:
            continue
        seq_raw = line[5:10].strip()
        seq = int(seq_raw) if seq_raw.isdigit() else 0
        if code not in grouped:
            grouped[code] = {"parts": [], "short": "", "terminated": False}
            order.append(code)
        entry = grouped[code]
        entry["parts"].append((seq, line[11:91].strip()))
        # The short description and the dates ride on the first record; later
        # fragments repeat the code and carry continuation text only.
        if not entry["short"]:
            entry["short"] = line[91:119].strip()
            entry["terminated"] = (bool(line[284:292].strip())
                                   if len(line) >= 292 else False)

    codes: list = []
    modifiers: list = []
    for code in order:
        entry = grouped[code]
        joined = " ".join(text for _seq, text in sorted(entry["parts"]) if text)
        joined = re.sub(r"\s+", " ", joined).strip()
        if not joined and not entry["short"]:
            continue
        row = {
            "code": code,
            "description": joined or entry["short"],
            "short_description": entry["short"][:120] or None,
            "chapter": None,
            "chapter_no": None,
            "is_billable": not entry["terminated"],
            "edition": EDITION,
        }
        if len(code) == 5 and code[0].isalpha():
            row["code_system"] = "HCPCS"
            codes.append(row)
        elif len(code) == 2:
            row["code_system"] = "HCPCSMOD"
            modifiers.append(row)
    return codes, modifiers


def parse_cc_mcc(txt_bytes: bytes) -> dict:
    """
    Appendix C Part 1 of the MS-DRG Definitions Manual: every code that acts as
    a CC or an MCC as a secondary diagnosis.

    Returns {code: "CC" | "MCC"}.

    PART 1 ONLY, and the parse stops when Part 2 begins. Part 2 codes are a
    Major CC only for patients discharged alive and Part 3 codes are excluded
    within particular DRGs — both are conditional on facts this application
    does not hold, and flattening them into "MCC" would produce a list that
    disagrees with the manual in exactly the cases a trainer would query.

    Whether a CC actually counts also depends on the principal diagnosis, which
    is why this is used to WARN on a trainer's label rather than to correct it.
    """
    out: dict = {}
    started = False
    for line in txt_bytes.decode("latin-1", "ignore").splitlines():
        stripped = line.strip()
        if not started:
            if stripped.startswith("Appendix C Part 1"):
                started = True
            continue
        if stripped.startswith("Appendix C Part 2") or \
                stripped.startswith("Appendix C Part 3"):
            break
        parts = stripped.split()
        if len(parts) < 2 or parts[1] not in ("CC", "MCC"):
            continue
        code = parts[0].upper().replace(".", "")
        # The header row reads "I10 Dx Lev PDX ..." — "Dx" is not a severity,
        # so it never reaches here, but a code must still look like one.
        if len(code) >= 3 and code[0].isalpha():
            out[code] = parts[1]
    return out


def _insert_many(db, model, rows: list) -> None:
    """
    Insert rows as multi-row INSERT statements.

    Not `bulk_insert_mappings`, which issues an executemany — and psycopg2's
    executemany is one round trip PER ROW. Against a local SQLite file that is
    invisible; against a managed database in another region it is fatal. The
    first production run sat for sixteen minutes without writing a row, with
    the server idle-in-transaction waiting on the client: 98,000 sequential
    round trips at Oregon latency is hours, not minutes.

    Batching into one statement per few hundred rows turns that into a few
    hundred round trips.
    """
    if not rows:
        return
    table = model.__table__
    columns = [c.name for c in table.columns if c.name != "id"]
    # Rows are dicts built by the parsers and do not all carry every key —
    # cc_mcc_status is only set when the MS-DRG appendix was loaded. A
    # multi-row VALUES takes its column list from the first row, so they are
    # squared off first rather than silently misaligning.
    shaped = [{c: row.get(c) for c in columns} for row in rows]
    # Bound-parameter ceilings: SQLite's is 999 on older builds, PostgreSQL's
    # is 65535. Sized to stay under the lower one wherever this runs.
    per_row = max(1, len(columns))
    chunk = max(1, (900 if db.get_bind().dialect.name == "sqlite" else 30000)
                // per_row)
    for i in range(0, len(shaped), chunk):
        db.execute(table.insert().values(shaped[i:i + chunk]))


def _write(db, system: str, rows: list, edition_note: str, loaded_by: str,
           source_url) -> None:
    """
    Replace one code set wholesale.

    Not merged: an edition is a SET, and codes are deleted between editions as
    well as added. Merging would leave retired codes behind looking current.
    """
    db.query(CodeDescription).filter(
        CodeDescription.code_system == system).delete()
    _insert_many(db, CodeDescription, rows)
    db.add(CodeSetVersion(code_system=system, edition=edition_note,
                          row_count=len(rows), loaded_by=loaded_by,
                          source_url=source_url))
    db.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="save; otherwise report only")
    ap.add_argument("--from-dir", type=str, default=None,
                    help="read CMS files from a directory instead of downloading")
    ap.add_argument("--loaded-by", default="ingest script")
    args = ap.parse_args()

    src = pathlib.Path(args.from_dir).expanduser() if args.from_dir else None
    if src and not src.is_dir():
        print(f"not a directory: {src}")
        return 2

    print(f"ICD-10-CM / ICD-10-PCS {EDITION}"
          f"{' from ' + str(src) if src else ' from cms.gov'}")

    db = None
    if args.write:
        # The code tables may not exist yet: nothing creates them but
        # create_all() on app startup, and an IT team standing up a new
        # environment will reasonably load reference data before first boot.
        # create_all() only adds missing tables, so this is safe against a
        # live schema.
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
    source_url = None if src else "cms.gov"
    loaded = 0

    # Each code set is parsed, written and then RELEASED before the next one
    # starts. Holding all four at once peaked at 522 MB, which is above the
    # 512 MB a Render Starter instance has — so the obvious way to run this,
    # in a shell on the API service, would have taken the API down with it.
    # One at a time peaks at roughly the largest single set.
    try:
        # ── ICD-10-CM ────────────────────────────────────────────────────────
        print("\nICD-10-CM")
        order = codes = tabular = None
        if src:
            order = _local(src, "order", ".txt")
            codes = _local(src, "codes", ".txt")
            if not order:
                tabular = _local(src, "tabular", ".xml")
        else:
            blob = _download(cm_urls())
            order = _from_zip(blob, "order", ".txt") if blob else None
            codes = _from_zip(blob, "codes", ".txt") if blob else None
            del blob
        if order:
            cm_rows = parse_cm(order, codes)
        elif tabular:
            print("  no order file — reading the tabular XML instead")
            cm_rows = parse_cm_xml(tabular)
            print("  seventh characters expanded from the XML's own definitions.\n"
                  "  Checked against the CMS order file: every code the order file\n"
                  "  carries is present, and the billable flag agrees on all of\n"
                  "  them. A downloaded edition is still preferable when there is a\n"
                  "  route to cms.gov, since a file on disk is only as current as\n"
                  "  the day it was fetched.")
        else:
            cm_rows = []
        del order, codes, tabular

        if cm_rows:
            billable = sum(1 for r in cm_rows if r["is_billable"])
            chapters = len({r["chapter_no"] for r in cm_rows if r["chapter_no"]})
            print(f"  {len(cm_rows):,} codes  ({billable:,} billable, "
                  f"{len(cm_rows) - billable:,} headers) across {chapters} chapters")
            unmapped = [r["code"] for r in cm_rows if not r["chapter_no"]]
            if unmapped:
                print(f"  {len(unmapped)} without a chapter, e.g. {unmapped[:5]}")

            # ── CC / MCC severity ────────────────────────────────────────────
            #
            # Stamped onto the CM rows rather than kept apart: it is a property
            # of the diagnosis code, and every reader that wants it has the code.
            print("\nCC / MCC (MS-DRG Appendix C)")
            if src:
                appendix = _local(src, "appendix_c", ".txt")
            else:
                blob = _download(drg_urls())
                appendix = _from_zip(blob, "appendix_c", ".txt") if blob else None
                del blob
            severity = parse_cc_mcc(appendix) if appendix else {}
            del appendix
            if severity:
                for row in cm_rows:
                    row["cc_mcc_status"] = severity.get(row["code"])
                stamped = sum(1 for r in cm_rows if r.get("cc_mcc_status"))
                mcc = sum(1 for r in cm_rows if r.get("cc_mcc_status") == "MCC")
                print(f"  {stamped:,} codes carry a severity "
                      f"({mcc:,} MCC, {stamped - mcc:,} CC)")
                # The MS-DRG manual and the CM code set both move each October
                # but are not published together, so the appendix on hand is
                # often a version behind. Naming the drift beats a number that
                # looks authoritative and is a year old.
                known = {r["code"] for r in cm_rows}
                orphans = [c for c in severity if c not in known]
                if orphans:
                    print(f"  {len(orphans)} severity codes are not in this CM "
                          f"edition, e.g. {sorted(orphans)[:4]} — the MS-DRG "
                          f"manual is from a different year.")
                del known, severity
            else:
                print("  no source found — skipped, codes load without severity")

            loaded += len(cm_rows)
            if db:
                _write(db, "ICD10CM", cm_rows, EDITION, args.loaded_by, source_url)
        else:
            print("  no source found — skipped")
        del cm_rows

        # ── ICD-10-PCS ───────────────────────────────────────────────────────
        print("\nICD-10-PCS")
        if src:
            pcs_xml = _local(src, "tables", ".xml")
        else:
            blob = _download(pcs_urls())
            pcs_xml = _from_zip(blob, "tables", ".xml") if blob else None
            del blob
        pcs_rows, pcs_axes = parse_pcs(pcs_xml) if pcs_xml else ([], [])
        del pcs_xml

        # Real descriptions, where the tables only give an axis breakdown.
        # The seven axis titles still matter — they are what names WHICH
        # character a planted error changed — so the axes table keeps them.
        if pcs_rows:
            if src:
                pcs_txt = _local(src, "pcs_codes", ".txt")
            else:
                blob = _download(pcs_code_urls())
                pcs_txt = _from_zip(blob, "pcs_codes", ".txt") if blob else None
                del blob
            described = parse_pcs_descriptions(pcs_txt) if pcs_txt else {}
            del pcs_txt
            if described:
                hit = 0
                for row in pcs_rows:
                    text = described.get(row["code"])
                    if text:
                        row["description"] = text
                        hit += 1
                print(f"  {hit:,} carry CMS's own description")
                if hit < len(pcs_rows):
                    print(f"  {len(pcs_rows) - hit:,} fall back to the axis "
                          f"breakdown — not in the codes file")
                del described
            else:
                print("  no codes file — descriptions are the axis breakdown, "
                      "which reads as a list of characters rather than a "
                      "procedure")

        if pcs_rows:
            ops = len({a["root_operation"] for a in pcs_axes if a["root_operation"]})
            print(f"  {len(pcs_rows):,} valid codes across {ops} root operations")
            loaded += len(pcs_rows)
            if db:
                _write(db, "ICD10PCS", pcs_rows, EDITION, args.loaded_by, source_url)
                db.query(PcsCodeAxis).delete()
                _insert_many(db, PcsCodeAxis, pcs_axes)
                db.commit()
        else:
            print("  no source found — skipped")
        del pcs_rows, pcs_axes

        # ── HCPCS Level II ───────────────────────────────────────────────────
        print("\nHCPCS Level II")
        if src:
            hc_txt = _local(src, "anweb", ".txt")
        else:
            blob = _download(hcpcs_urls())
            hc_txt = _from_zip(blob, "anweb", ".txt") if blob else None
            del blob
        hcpcs_rows, mod_rows = parse_hcpcs(hc_txt) if hc_txt else ([], [])
        del hc_txt
        if hcpcs_rows or mod_rows:
            live = sum(1 for r in hcpcs_rows if r["is_billable"])
            print(f"  {len(hcpcs_rows):,} codes ({live:,} current, "
                  f"{len(hcpcs_rows) - live:,} terminated) "
                  f"and {len(mod_rows):,} modifiers")
            loaded += len(hcpcs_rows) + len(mod_rows)
            if db:
                if hcpcs_rows:
                    _write(db, "HCPCS", hcpcs_rows, EDITION, args.loaded_by,
                           source_url)
                if mod_rows:
                    _write(db, "HCPCSMOD", mod_rows, EDITION, args.loaded_by,
                           source_url)
        else:
            print("  no source found — skipped")

        if not loaded:
            print("\nnothing to load")
            return 1
        if not db:
            print("\ndry run — nothing saved. Pass --write to load.")
            return 0
        print(f"\nloaded {loaded:,} codes")
        return 0
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
