"""
Content-Disposition headers that survive real-world names.

HTTP headers are latin-1. Anything outside that range — an em dash, a curly
quote, an accented letter, any non-Western script — raises UnicodeEncodeError
when the response is encoded, AFTER the handler has returned successfully. The
result is a 500 with a traceback that points at the web server rather than at
the name that caused it, and it fires only for the subset of records whose
names happen to contain one.

A batch called "Wave 3 — Northeast" was enough to make its report download
fail every time while every other batch worked.

The fix is RFC 6266: an ASCII-only `filename` that any client can read, plus a
UTF-8 `filename*` carrying the real thing for clients that support it.
"""
import re
from urllib.parse import quote

_UNSAFE = re.compile(r'[^A-Za-z0-9._-]+')

# Punctuation that has a plain ASCII equivalent — worth keeping legible rather
# than collapsing to underscores.
_TRANSLITERATE = str.maketrans({
    "—": "-", "–": "-", "―": "-",
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "…": "...", " ": " ",
})


def safe_filename(name: str, fallback: str = "download") -> str:
    """An ASCII, filesystem- and header-safe version of a user-supplied name."""
    if not name:
        return fallback
    ascii_name = name.translate(_TRANSLITERATE)
    ascii_name = ascii_name.encode("ascii", "ignore").decode("ascii")
    ascii_name = _UNSAFE.sub("_", ascii_name).strip("._-")
    # Long names produce unwieldy downloads and can trip path limits.
    return (ascii_name[:80] or fallback)


def content_disposition(filename: str, fallback: str = "download") -> dict:
    """
    Headers for an attachment download.

    Pass the raw, unsanitised name — sanitising is this function's job, and
    doing it at the call site is how the crash got in.
    """
    ascii_name = safe_filename(filename, fallback)
    utf8_name = quote(filename or fallback, safe="")
    return {
        "Content-Disposition":
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
    }
