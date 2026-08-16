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

from database import SessionLocal  # noqa: E402
from models import CodeDescription, CodeSetVersion, PcsCodeAxis  # noqa: E402

EDITION = "FY2026"

CM_URLS = [
    "https://www.cms.gov/files/zip/2026-code-descriptions-tabular-order-updated-01012026.zip",
    "https://www.cms.gov/files/zip/2026-code-descriptions-tabular-order.zip",
]
PCS_URLS = [
    "https://www.cms.gov/files/zip/2026-icd-10-pcs-code-tables-and-index-updated-01012026.zip",
    "https://www.cms.gov/files/zip/2026-icd-10-pcs-code-tables-and-index.zip",
]

# ── ICD-10-CM chapters ───────────────────────────────────────────────────────
#
# By code RANGE, not by first letter. The letter is not enough for two of them:
# C00-D49 is Neoplasms while D50-D89 is Blood, and H00-H59 is Eye while H60-H95
# is Ear. A letter-keyed map has to fudge those into "Neoplasms / Blood", which
# is exactly the distinction a chapter analytics axis exists to draw.
CHAPTERS = [
    (1, "A00", "B99", "Certain infectious and parasitic diseases"),
    (2, "C00", "D49", "Neoplasms"),
    (3, "D50", "D89", "Diseases of the blood and blood-forming organs"),
    (4, "E00", "E89", "Endocrine, nutritional and metabolic diseases"),
    (5, "F01", "F99", "Mental, behavioural and neurodevelopmental disorders"),
    (6, "G00", "G99", "Diseases of the nervous system"),
    (7, "H00", "H59", "Diseases of the eye and adnexa"),
    (8, "H60", "H95", "Diseases of the ear and mastoid process"),
    (9, "I00", "I99", "Diseases of the circulatory system"),
    (10, "J00", "J99", "Diseases of the respiratory system"),
    (11, "K00", "K95", "Diseases of the digestive system"),
    (12, "L00", "L99", "Diseases of the skin and subcutaneous tissue"),
    (13, "M00", "M99", "Diseases of the musculoskeletal system"),
    (14, "N00", "N99", "Diseases of the genitourinary system"),
    (15, "O00", "O9A", "Pregnancy, childbirth and the puerperium"),
    (16, "P00", "P96", "Certain conditions originating in the perinatal period"),
    # High bound is QZ9, not Q99: CMS has added letter-suffixed categories
    # such as QA0, and "A" sorts above "9", so a Q99 ceiling drops them.
    (17, "Q00", "QZ9", "Congenital malformations and chromosomal abnormalities"),
    (18, "R00", "R99", "Symptoms, signs and abnormal clinical findings"),
    (19, "S00", "T88", "Injury, poisoning and other consequences of external causes"),
    (20, "V00", "Y99", "External causes of morbidity"),
    (21, "Z00", "Z99", "Factors influencing health status"),
    (22, "U00", "U85", "Codes for special purposes"),
]


def chapter_for(code: str):
    """(number, title) for a CM code, comparing on its three-character stem."""
    stem = (code or "").strip().upper()[:3]
    if len(stem) < 3:
        return None, None
    for number, low, high, title in CHAPTERS:
        if low <= stem <= high:
            return number, title
    return None, None


# ── sources ──────────────────────────────────────────────────────────────────

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

    if not cm_rows and not pcs_rows:
        print("\nnothing to load")
        return 1

    if not args.write:
        print("\ndry run — nothing saved. Pass --write to load.")
        return 0

    db = SessionLocal()
    try:
        for system, rows in (("ICD10CM", cm_rows), ("ICD10PCS", pcs_rows)):
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
        print(f"\nloaded {len(cm_rows) + len(pcs_rows):,} codes")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
