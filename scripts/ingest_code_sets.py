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
from models import CodeDescription, CodeSetVersion, PcsCodeAxis  # noqa: E402

EDITION = "FY2026"

CM_URLS = [
    "https://www.cms.gov/files/zip/2026-code-descriptions-tabular-order-updated-01012026.zip",
    "https://www.cms.gov/files/zip/2026-code-descriptions-tabular-order.zip",
]
# HCPCS Level II is republished QUARTERLY, so the newest is tried first and the
# list walks back — an internal environment mid-quarter should still find one.
HCPCS_URLS = [
    "https://www.cms.gov/files/zip/january-2026-alpha-numeric-hcpcs-file.zip",
    "https://www.cms.gov/files/zip/october-2025-alpha-numeric-hcpcs-file.zip",
    "https://www.cms.gov/files/zip/july-2025-alpha-numeric-hcpcs-file.zip",
]
# MS-DRG Definitions Manual, for Appendix C — the published CC/MCC list.
# Newest first; the version number moves each October.
DRG_URLS = [
    "https://www.cms.gov/files/zip/icd-10-ms-drg-definitions-manual-files-v43.zip",
    "https://www.cms.gov/files/zip/icd-10-ms-drg-definitions-manual-files-v42.zip",
]
PCS_URLS = [
    "https://www.cms.gov/files/zip/2026-icd-10-pcs-code-tables-and-index-updated-01012026.zip",
    "https://www.cms.gov/files/zip/2026-icd-10-pcs-code-tables-and-index.zip",
]


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

    # ── ICD-10-CM ────────────────────────────────────────────────────────────
    print("\nICD-10-CM")
    order = codes = tabular = None
    if src:
        order = _local(src, "order", ".txt")
        codes = _local(src, "codes", ".txt")
        if not order:
            tabular = _local(src, "tabular", ".xml")
    else:
        blob = _download(CM_URLS)
        order = _from_zip(blob, "order", ".txt") if blob else None
        codes = _from_zip(blob, "codes", ".txt") if blob else None
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
    if cm_rows:
        billable = sum(1 for r in cm_rows if r["is_billable"])
        chapters = len({r["chapter_no"] for r in cm_rows if r["chapter_no"]})
        print(f"  {len(cm_rows):,} codes  ({billable:,} billable, "
              f"{len(cm_rows) - billable:,} headers) across {chapters} chapters")
        unmapped = [r["code"] for r in cm_rows if not r["chapter_no"]]
        if unmapped:
            print(f"  {len(unmapped)} without a chapter, e.g. {unmapped[:5]}")
    else:
        print("  no source found — skipped")

    # ── CC / MCC severity, from the MS-DRG manual ────────────────────────────
    #
    # Stamped onto the CM rows rather than kept apart: it is a property of the
    # diagnosis code, and every reader that wants it already has the code.
    if cm_rows:
        print("\nCC / MCC (MS-DRG Appendix C)")
        if src:
            appendix = _local(src, "appendix_c", ".txt")
        else:
            blob = _download(DRG_URLS)
            appendix = _from_zip(blob, "appendix_c", ".txt") if blob else None
        severity = parse_cc_mcc(appendix) if appendix else {}
        if severity:
            for row in cm_rows:
                row["cc_mcc_status"] = severity.get(row["code"])
            stamped = sum(1 for r in cm_rows if r.get("cc_mcc_status"))
            mcc = sum(1 for r in cm_rows if r.get("cc_mcc_status") == "MCC")
            print(f"  {stamped:,} codes carry a severity "
                  f"({mcc:,} MCC, {stamped - mcc:,} CC)")
            # The MS-DRG manual moves each October and the CM code set each
            # October too, but they are not published together — so the
            # appendix on hand is often a version behind. Naming the drift is
            # better than a number that looks authoritative and is a year old.
            known = {r["code"] for r in cm_rows}
            orphans = [c for c in severity if c not in known]
            if orphans:
                print(f"  {len(orphans)} severity codes are not in this CM "
                      f"edition, e.g. {sorted(orphans)[:4]} — the MS-DRG "
                      f"manual is from a different year.")
        else:
            print("  no source found — skipped, codes load without severity")

    # ── ICD-10-PCS ───────────────────────────────────────────────────────────
    print("\nICD-10-PCS")
    if src:
        pcs_xml = _local(src, "tables", ".xml")
    else:
        blob = _download(PCS_URLS)
        pcs_xml = _from_zip(blob, "tables", ".xml") if blob else None
    pcs_rows, pcs_axes = parse_pcs(pcs_xml) if pcs_xml else ([], [])
    if pcs_rows:
        ops = len({a["root_operation"] for a in pcs_axes if a["root_operation"]})
        print(f"  {len(pcs_rows):,} valid codes across {ops} root operations")
    else:
        print("  no source found — skipped")

    # ── HCPCS Level II ───────────────────────────────────────────────────────
    print("\nHCPCS Level II")
    if src:
        hc_txt = _local(src, "anweb", ".txt")
    else:
        blob = _download(HCPCS_URLS)
        hc_txt = _from_zip(blob, "anweb", ".txt") if blob else None
    hcpcs_rows, mod_rows = parse_hcpcs(hc_txt) if hc_txt else ([], [])
    if hcpcs_rows or mod_rows:
        live = sum(1 for r in hcpcs_rows if r["is_billable"])
        print(f"  {len(hcpcs_rows):,} codes ({live:,} current, "
              f"{len(hcpcs_rows) - live:,} terminated) "
              f"and {len(mod_rows):,} modifiers")
    else:
        print("  no source found — skipped")

    if not cm_rows and not pcs_rows and not hcpcs_rows:
        print("\nnothing to load")
        return 1

    if not args.write:
        print("\ndry run — nothing saved. Pass --write to load.")
        return 0

    # The code tables may not exist yet: nothing creates them but create_all()
    # on app startup, and an IT team standing up a new environment will
    # reasonably load reference data before first boot. create_all() only adds
    # tables that are missing, so this is safe to run against a live schema.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        for system, rows in (("ICD10CM", cm_rows), ("ICD10PCS", pcs_rows),
                             ("HCPCS", hcpcs_rows), ("HCPCSMOD", mod_rows)):
            if not rows:
                continue
            # Replaced wholesale rather than merged: an edition is a set, and
            # codes are DELETED between editions as well as added. Merging
            # would leave retired codes behind looking current.
            db.query(CodeDescription).filter(
                CodeDescription.code_system == system).delete()
            db.bulk_insert_mappings(CodeDescription, rows)
            db.add(CodeSetVersion(code_system=system, edition=EDITION,
                                  row_count=len(rows), loaded_by=args.loaded_by,
                                  source_url=None if src else "cms.gov"))
        if pcs_axes:
            db.query(PcsCodeAxis).delete()
            db.bulk_insert_mappings(PcsCodeAxis, pcs_axes)
        db.commit()
        total = len(cm_rows) + len(pcs_rows) + len(hcpcs_rows) + len(mod_rows)
        print(f"\nloaded {total:,} codes")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
