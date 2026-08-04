"""
Timezone normalisation for stored timestamps.

Postgres returns timezone-aware datetimes for DateTime(timezone=True); SQLite
returns naive ones. Code that compares a stored timestamp against
datetime.now(timezone.utc) therefore works in production and raises
TypeError under SQLite — which is why the assessment session layer could
never be tested, and why its expiry rules had never been verified.

Route every stored timestamp through as_utc() before it meets "now".
"""
from datetime import datetime, timezone
from typing import Optional


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Return dt as timezone-aware UTC. Naive values are read as UTC, which
    is what they were written as."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
