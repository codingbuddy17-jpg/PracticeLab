"""
Assert every frontend specialty list agrees with the backend Specialty enum.

Specialty values are duplicated across several frontend files with no shared
source of truth, so adding one to the enum silently leaves dropdowns stale —
which is exactly what happened with Surgery / ED Single Path.
"""
import re, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
BE, FE = REPO / "backend", REPO / "frontend/src"

fails = []
def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if detail and not cond: print(f"        {detail}")
    if not cond: fails.append(label)

# ── backend truth ──
charts = (BE / "models/charts.py").read_text()
enum_block = charts.split("class Specialty")[1].split("SPECIALTY_PREFIX")[0]
be_specialties = set(re.findall(r'=\s*"([^"]+)"', enum_block))
be_prefix = dict(re.findall(r'"([A-Z]+)":\s*Specialty\.(\w+)', charts))
print(f"backend enum ({len(be_specialties)}): {sorted(be_specialties)}\n")

def arr_after(text, marker):
    """Slice the array literal after `marker`. Anchors on '= [' so a
    `Specialty[]` type annotation isn't mistaken for the array itself."""
    i = text.index(marker)
    seg = text[i:i + 800]
    start = seg.index("= [") + 2
    seg = seg[start: seg.index("]", start) + 1]
    return set(re.findall(r"'([^']+)'", seg))

def union_after(text, marker):
    i = text.index(marker)
    seg = text[i:i + 600]
    return set(re.findall(r"\|\s*'([^']+)'", seg))

types_ts = (FE / "types/index.ts").read_text()
shared_ts = (FE / "pages/practicelab/shared.ts").read_text()
pla_tsx = (FE / "pages/practicelab/PLAnalyticsView.tsx").read_text()
theme_ts = (FE / "theme.ts").read_text()

print("1. SPECIALTY LISTS MATCH THE ENUM")
targets = {
    "types/index.ts SPECIALTIES": arr_after(types_ts, "export const SPECIALTIES"),
    "practicelab/shared.ts SPECIALTIES": arr_after(shared_ts, "export const SPECIALTIES"),
    "PLAnalyticsView SPECIALTIES": arr_after(pla_tsx, "const SPECIALTIES"),
}
for name, vals in targets.items():
    missing, extra = be_specialties - vals, vals - be_specialties
    check(f"{name} ({len(vals)})", not missing and not extra,
          f"missing={sorted(missing)} extra={sorted(extra)}")

print("\n2. Specialty TYPE UNION")
union = union_after(types_ts, "export type Specialty")
missing = be_specialties - union
check(f"type union ({len(union)})", not missing, f"missing={sorted(missing)}")

print("\n3. SPECIALTY_COLORS covers every specialty")
colors = set(re.findall(r"^\s*'([^']+)':\s*\{", theme_ts, re.M))
missing = be_specialties - colors
check(f"theme.ts colours ({len(colors)})", not missing, f"missing={sorted(missing)}")

print("\n4. PREFIX MAPS AGREE (chart numbering)")
seg = types_ts[types_ts.index("SPECIALTY_PREFIX"):]
seg = seg[seg.index("{"): seg.index("}") + 1]
fe_prefix = dict(re.findall(r"'([A-Z]+)':\s*'([^']+)'", seg))
be_prefix_vals = {}
name_to_val = dict(re.findall(r'(\w+)\s*=\s*"([^"]+)"', enum_block))
for pre, member in be_prefix.items():
    be_prefix_vals[pre] = name_to_val.get(member, member)
check(f"same prefixes ({len(fe_prefix)} vs {len(be_prefix_vals)})",
      set(fe_prefix) == set(be_prefix_vals),
      f"be_only={sorted(set(be_prefix_vals)-set(fe_prefix))} fe_only={sorted(set(fe_prefix)-set(be_prefix_vals))}")
for pre in sorted(set(fe_prefix) & set(be_prefix_vals)):
    if fe_prefix[pre] != be_prefix_vals[pre]:
        check(f"prefix {pre} maps consistently", False,
              f"fe={fe_prefix[pre]!r} be={be_prefix_vals[pre]!r}")

print("\n" + ("ALL IN SYNC" if not fails else f"{len(fails)} MISMATCH(ES)"))
sys.exit(1 if fails else 0)
