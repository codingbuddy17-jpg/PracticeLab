"""
Every specialty must be tellable from every other at a glance.

The palette had grown by addition and four specialties had landed inside a 20
degree arc of blue-violet — E/M, IP-DRG, Edits and ED Single Path, the closest
pair 4 degrees apart. IP-DRG and Edits shared a chip fill outright, and the
"Direct" type chip was byte for byte the Edits chip.

Absolute colour distance is the wrong measure for these: the fills are all pale
tints, so they sit close together in Lab whatever their hue. What the eye uses
to separate a pale chip from another pale chip is HUE, so that is what this
asserts.
"""
import math
import re
from pathlib import Path

import pytest

THEME = Path(__file__).resolve().parents[2] / "frontend" / "src" / "theme.ts"

MIN_HUE_GAP = 18.0      # degrees; the palette ships with 24
MIN_CONTRAST = 4.5      # text on its own fill, and white on the solid colour


def _srgb(hex6):
    v = [int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in v]


def _lab(hex6):
    r, g, b = _srgb(hex6)
    x = (r * .4124 + g * .3576 + b * .1805) / .95047
    y = r * .2126 + g * .7152 + b * .0722
    z = (r * .0193 + g * .1192 + b * .9505) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    x, y, z = f(x), f(y), f(z)
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def _hue(hex6):
    _, a, b = _lab(hex6)
    return math.degrees(math.atan2(b, a)) % 360


def _contrast(a, b):
    la = sum(c * w for c, w in zip(_srgb(a), (.2126, .7152, .0722)))
    lb = sum(c * w for c, w in zip(_srgb(b), (.2126, .7152, .0722)))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + .05) / (lo + .05)


def _palette():
    src = THEME.read_text()
    block = src[src.index("SPECIALTY_COLORS"):]
    block = block[:block.index("\n}")]
    out = {}
    for m in re.finditer(r"'([^']+)':\s*\{\s*bg:\s*'#([0-9a-fA-F]{6})'.*?light:\s*'#([0-9a-fA-F]{6})'", block):
        out[m.group(1)] = (m.group(2).lower(), m.group(3).lower())
    return out


def test_the_palette_parses():
    """Guards the guard — a regex that matches nothing would pass everything."""
    pal = _palette()
    assert len(pal) >= 10, "found %d specialties; the palette shape changed" % len(pal)


def test_no_two_specialties_share_a_colour():
    pal = _palette()
    for field, idx in (("bg", 0), ("light", 1)):
        seen = {}
        for name, vals in pal.items():
            seen.setdefault(vals[idx], []).append(name)
        clashes = {v: n for v, n in seen.items() if len(n) > 1}
        assert not clashes, "identical %s: %s" % (field, clashes)


def test_every_specialty_is_a_distinct_hue():
    pal = _palette()
    hues = sorted((_hue(bg), name) for name, (bg, _) in pal.items())
    tight = []
    for i in range(len(hues)):
        a, b = hues[i], hues[(i + 1) % len(hues)]
        d = abs(a[0] - b[0]) % 360
        d = min(d, 360 - d)
        if d < MIN_HUE_GAP:
            tight.append("%s / %s only %.0f deg apart" % (a[1], b[1], d))
    assert not tight, "; ".join(tight)


@pytest.mark.parametrize("which", ["on its own fill", "as white on the solid colour"])
def test_every_specialty_chip_is_readable(which):
    for name, (bg, light) in _palette().items():
        got = _contrast(bg, light) if which == "on its own fill" else _contrast(bg, "ffffff")
        assert got >= MIN_CONTRAST, "%s %s is only %.2f:1" % (name, which, got)


def test_the_type_chip_does_not_use_a_specialty_colour():
    """
    "Direct" marks a kind of work, not a specialty, so it must not draw from
    the specialty hue space — there is no eleventh hue to spare, and any added
    specialty would collide with it. It is neutral and outlined instead.
    """
    home = THEME.parent / "pages" / "practicelab" / "HomeView.tsx"
    src = home.read_text()
    assert "typeChip" in src, "the Direct chip no longer uses the neutral type style"
    used = set()
    for bg, light in _palette().values():
        used.add("#" + bg)
        used.add("#" + light)
    style = re.search(r"typeChip:\{(.*?)\},", src, re.S)
    assert style, "typeChip style not found"
    for colour in re.findall(r"#[0-9a-fA-F]{6}", style.group(1)):
        assert colour.lower() not in used, "the type chip reuses specialty colour %s" % colour
