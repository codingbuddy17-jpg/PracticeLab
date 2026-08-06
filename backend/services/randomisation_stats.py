"""
Compute randomisation quality stats for a batch of per-coder item sets.
Used by both assessment generation and chart allocation cycles.

Stats schema stored in randomisation_stats JSON column:
{
  "avg_uniqueness_pct": 87.5,     # avg % of each coder's set unique to them alone
  "pool_utilisation_pct": 60.0,   # % of available pool actually used
  "total_pool": 15,
  "total_used": 9,
  "coder_count": 3,
  "items_per_coder": 4,
  "per_coder": [
    {
      "name": "Alice",
      "uniqueness_pct": 100.0,
      "shared_items": []           # list of item ids shared with at least one other coder
    },
    ...
  ],
  "top_overlaps": [                # worst overlapping pairs, capped at 5
    {"coder_a": "Alice", "coder_b": "Bob", "shared_count": 1, "overlap_pct": 25.0}
  ]
}
"""
import json
from typing import Dict, List, Any, Set, Optional


def compute_randomisation_stats(
    coder_sets: Dict[str, Set[Any]],   # {coder_name: set of item ids}
    pool_size: int,
) -> Dict[str, Any]:
    if not coder_sets:
        return {}

    coder_names = list(coder_sets.keys())
    n = len(coder_names)
    items_per_coder = len(next(iter(coder_sets.values()))) if coder_sets else 0

    # pool utilisation
    all_used: Set[Any] = set()
    for s in coder_sets.values():
        all_used |= s
    pool_util = round(len(all_used) / pool_size * 100, 1) if pool_size else 0.0

    # per-coder uniqueness: items not shared with ANY other coder
    per_coder_stats = []
    for name in coder_names:
        my_set = coder_sets[name]
        others_union: Set[Any] = set()
        for other_name, other_set in coder_sets.items():
            if other_name != name:
                others_union |= other_set
        shared_items = list(my_set & others_union)
        unique_count = len(my_set) - len(shared_items)
        uniqueness_pct = round(unique_count / len(my_set) * 100, 1) if my_set else 100.0
        per_coder_stats.append({
            "name": name,
            "uniqueness_pct": uniqueness_pct,
            "shared_items": shared_items,
        })

    avg_uniqueness = round(
        sum(c["uniqueness_pct"] for c in per_coder_stats) / n, 1
    ) if n else 0.0

    # pairwise overlaps — find worst offenders (cap at 5 pairs)
    overlaps = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = coder_names[i], coder_names[j]
            shared = coder_sets[a] & coder_sets[b]
            if shared:
                overlaps.append({
                    "coder_a": a,
                    "coder_b": b,
                    "shared_count": len(shared),
                    "overlap_pct": round(len(shared) / items_per_coder * 100, 1) if items_per_coder else 0.0,
                })
    overlaps.sort(key=lambda x: x["shared_count"], reverse=True)
    top_overlaps = overlaps[:5]

    return {
        "avg_uniqueness_pct": avg_uniqueness,
        "pool_utilisation_pct": pool_util,
        "total_pool": pool_size,
        "total_used": len(all_used),
        "coder_count": n,
        "items_per_coder": items_per_coder,
        "per_coder": per_coder_stats,
        "top_overlaps": top_overlaps,
    }


def parse_stats(value) -> Optional[Dict[str, Any]]:
    """
    Stored randomisation stats, always as a dict.

    The model declares Column(JSON) but the migration created the column as
    TEXT, so Postgres hands the value back as a JSON *string* while SQLite
    deserialises it. Anything reading the stored column therefore got an object
    in tests and a string in production.

    The cost was silent: the frontend does `stats.avg_uniqueness_pct` on it, and
    on a string that is `undefined`, so the card rendered a dash and an empty
    per-coder table — which reads as "no overlap" rather than "no data". The
    POST responses return the in-memory dict and were always right, which is why
    generation and the sessions screen disagreed about the same assessment.

    Parse on read rather than migrating the column: existing rows hold both
    shapes, so the reader has to cope with both regardless.
    """
    if value is None or isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None
