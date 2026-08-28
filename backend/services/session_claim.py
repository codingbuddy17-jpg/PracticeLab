"""
One device at a time on a practice or audit session.

The access code is the whole credential, so anyone holding it could open the
same session — a coder's code opened on a second machine while the first was
mid-chart, and both were live.

A hard single-use lock is the obvious fix and the wrong one on its own: a
closed tab, a flat battery or a browser that clears storage would strand
someone with no way back in, and the trainer would be reissuing codes all day.

So the claim EXPIRES. The first device to open holds the session; a different
device is refused while that claim is fresh, and may take it over once it has
gone quiet. The same mechanism answers both halves of the problem — the idle
timeout is what makes the exclusive claim safe to enforce.

Nothing is destroyed when a claim lapses. Drafts are written on a timer and on
every chart change, and stay exactly where they were; re-entering the access
code re-claims the session with the work still there. Losing a claim costs the
holder the need to type the code again, which is the point.

The saving is also the heartbeat, so the timer is not a nicety: without it a
coder on one long inpatient chart could work past the window and have the claim
go stale while they were still in it.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

# How long a session may sit untouched before another device may take it over.
# An hour is the figure the owner asked for. It is deliberately far longer than
# a page load and far shorter than a working day: long enough that reading a
# chart, taking a call or a lunch break does not lose the claim, short enough
# that a machine left logged in overnight does not hold one until morning.
IDLE_MINUTES = 60


def _aware(value):
    """Timestamps come back naive from SQLite and aware from PostgreSQL."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_stale(last_seen, now=None) -> bool:
    """True when a claim has gone quiet long enough to be taken over."""
    seen = _aware(last_seen)
    if seen is None:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - seen) > timedelta(minutes=IDLE_MINUTES)


def check(active_device: str, last_seen, device: str, now=None):
    """
    May `device` work this session?

    Returns the device that now holds it, or raises 409 with something the
    coder can act on. An empty `device` is treated as a fresh claim rather than
    refused, so an older client that sends nothing still works — it simply gets
    no protection, which is where everything was before this existed.
    """
    now = now or datetime.now(timezone.utc)
    if not device:
        return active_device
    if not active_device or active_device == device or is_stale(last_seen, now):
        return device

    minutes = max(1, int((now - _aware(last_seen)).total_seconds() // 60))
    # What to DO, and nothing about how long the lock lasts. Naming the window
    # invites waiting it out instead of closing the other tab, and it is the
    # one instruction that helps somebody using a code that is not theirs.
    raise HTTPException(
        status_code=409,
        detail=(
            "This access code is already open on another device, active "
            f"{minutes} minute(s) ago. Close it there and try again."
        ),
    )
