"""
Which edition of each CMS code set is current, and whether what is loaded
still counts as current.

The application cannot refresh itself — the ingest is a script somebody runs
(see the runbook). The failure that creates is silent: nothing errors when the
data is a year old, so a trainer would go on seeing FY2025 descriptions against
FY2026 charts and never be told. This module is what lets a screen say so.

One table, two readers, same as the chapter list: the ingest builds download
URLs from these dates and the trainer panel judges freshness by them. Splitting
them would let the app call something stale that the ingest thinks is current.
"""
import datetime
from typing import Optional

# CMS publication cadence.
#   ICD-10-CM and ICD-10-PCS: annually, effective 1 October (a fiscal year).
#   HCPCS Level II:           quarterly, effective the 1st of Jan/Apr/Jul/Oct.
#   MS-DRG manual:            annually, alongside the ICD sets.
ANNUAL_SYSTEMS = ("ICD10CM", "ICD10PCS")
QUARTERLY_SYSTEMS = ("HCPCS", "HCPCSMOD")

SYSTEM_LABELS = {
    "ICD10CM": "ICD-10-CM diagnoses",
    "ICD10PCS": "ICD-10-PCS procedures",
    "HCPCS": "HCPCS Level II",
    "HCPCSMOD": "HCPCS modifiers",
}


def fiscal_year(today: Optional[datetime.date] = None) -> int:
    """CMS code sets run October to September. October 2025 is FY2026."""
    today = today or datetime.date.today()
    return today.year + 1 if today.month >= 10 else today.year


def current_edition(today: Optional[datetime.date] = None) -> str:
    return "FY%d" % fiscal_year(today)


def quarter_start(today: Optional[datetime.date] = None) -> datetime.date:
    """First day of the quarter `today` falls in."""
    today = today or datetime.date.today()
    return datetime.date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)


def freshness(code_system: str, edition: Optional[str],
              loaded_at: Optional[datetime.datetime],
              today: Optional[datetime.date] = None) -> dict:
    """
    Judge one loaded code set.

    Returns {current, expected, note}. `current` is True only when there is
    positive reason to believe the data is up to date — an unrecognised system
    or a missing date is reported as unknown rather than fine, because the
    whole point of this is to stop silence reading as approval.
    """
    today = today or datetime.date.today()
    expected = current_edition(today)
    label = SYSTEM_LABELS.get(code_system, code_system)

    if not edition and not loaded_at:
        return {"current": False, "expected": expected,
                "note": "%s has never been loaded" % label}

    if code_system in ANNUAL_SYSTEMS:
        # The edition is the signal: it says which year's codes these are,
        # which is what matters. When it was loaded does not.
        if edition == expected:
            return {"current": True, "expected": expected, "note": ""}
        return {"current": False, "expected": expected,
                "note": "%s is %s; CMS published %s on 1 October"
                        % (label, edition or "an unknown edition", expected)}

    if code_system in QUARTERLY_SYSTEMS:
        # The edition string is only the fiscal year, so it cannot distinguish
        # one quarter from the next. The load DATE can: a file loaded before
        # this quarter began cannot contain this quarter's changes.
        if not loaded_at:
            return {"current": False, "expected": expected,
                    "note": "%s has no load date recorded" % label}
        loaded_date = loaded_at.date() if hasattr(loaded_at, "date") else loaded_at
        start = quarter_start(today)
        if loaded_date >= start:
            return {"current": True, "expected": expected, "note": ""}
        return {"current": False, "expected": expected,
                "note": "%s was loaded %s, before the current quarter began on %s"
                        % (label, loaded_date.isoformat(), start.isoformat())}

    return {"current": False, "expected": expected,
            "note": "%s is not a code set this application tracks" % label}
