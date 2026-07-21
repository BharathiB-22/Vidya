"""Text measurement for slide layout.

WHY A FONT FILE SHIPS NEXT TO THIS MODULE
-----------------------------------------
python-pptx writes XML; it never lays text out. PowerPoint does that when the
deck is opened — and a PowerPoint text box does not clip. Text that does not fit
renders straight through whatever sits beneath it. So a generator that stacks
blocks down a slide must know how tall a string will be BEFORE it places the next
one, or the deck silently overlaps in front of a lecture hall.

The decks render in Calibri: the generator never sets a font name, so PowerPoint
applies its default theme font. Calibri is proprietary and cannot ship here.
Carlito was drawn to be metric-compatible with it — every glyph has the same
advance width — and is OFL-licensed (see fonts/OFL.txt). Measuring with Carlito
therefore returns exactly the widths PowerPoint will use for Calibri; this was
verified against C:\\Windows\\Fonts\\calibri.ttf and calibrib.ttf, which agree to
the point on every sample tried, regular and bold.

The same equivalence is why LibreOffice substitutes Carlito for Calibri, so the
measurements hold there too.

If the font cannot be loaded, every function here falls back to a crude
character-width estimate rather than raising: a slightly wrong deck beats a
failed export job.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("vidya.m03.presentation.metrics")

_FONT_DIR = Path(__file__).parent / "fonts"
_FACES = {False: _FONT_DIR / "Carlito-Regular.ttf", True: _FONT_DIR / "Carlito-Bold.ttf"}

# Measure at a large reference size and scale linearly. TrueType advance widths
# are proportional to em size; going through one large size keeps the hinter from
# quantising small sizes into visibly wrong answers.
_REF_PX = 200

# A python-pptx text box insets its text by 0.1" on each side (PowerPoint's
# default). Text wraps against that inner edge, not the box edge — measuring
# against the full width is how a "fitting" line ends up one word too long.
TEXTBOX_H_INSET_IN = 0.2

# Fallback only: average glyph width as a fraction of font size. This is the old
# `_wrapped_lines` constant, kept for the no-font path.
_FALLBACK_CHAR_RATIO = 0.55


@lru_cache(maxsize=4)
def _face(bold: bool):
    """The PIL font at the reference size, or None if unavailable."""
    try:
        from PIL import ImageFont
        return ImageFont.truetype(str(_FACES[bold]), _REF_PX)
    except Exception:
        logger.warning(
            "m03.metrics: %s unavailable — falling back to estimated text widths; "
            "slide layout will be approximate.", _FACES[bold].name,
        )
        return None


@lru_cache(maxsize=1)
def _line_ratio() -> float:
    """Single-line height as a multiple of font size.

    PowerPoint spaces single-spaced lines by the font's hhea ascent + descent +
    lineGap. For Calibri/Carlito that is ~1.22em. Read it from the font rather
    than hardcoding, and fall back to 1.22 if the table cannot be read.
    """
    try:
        from fontTools.ttLib import TTFont
        with TTFont(str(_FACES[False]), lazy=True) as ttf:
            hhea, head = ttf["hhea"], ttf["head"]
            return (hhea.ascent - hhea.descent + hhea.lineGap) / head.unitsPerEm
    except Exception:
        return 1.22


def text_width_in(text: str, pt: float, *, bold: bool = False) -> float:
    """Rendered width of `text` in inches at `pt`, on one unwrapped line."""
    if not text:
        return 0.0
    face = _face(bold)
    if face is None:
        return len(text) * pt * _FALLBACK_CHAR_RATIO / 72.0
    # getlength returns px at _REF_PX; scale to pt, then pt -> inches at 72pt/in.
    return face.getlength(text) * (pt / _REF_PX) / 72.0


def line_height_in(pt: float) -> float:
    """Height of one single-spaced line at `pt`, in inches."""
    return pt * _line_ratio() / 72.0


def wrap(text: str, width_in: float, pt: float, *, bold: bool = False,
         inset: bool = True) -> list[str]:
    """Break `text` into the lines PowerPoint will break it into.

    `width_in` is the TEXT BOX width; the default text inset is subtracted unless
    `inset=False` (e.g. when measuring against a bare region rather than a box).

    A token wider than the whole line — a URL, a long identifier, a chemical name
    — is hard-split rather than allowed to overhang, which is what PowerPoint
    itself does.
    """
    text = (text or "").strip()
    if not text:
        return []
    usable = max(0.3, width_in - (TEXTBOX_H_INSET_IN if inset else 0.0))

    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if text_width_in(candidate, pt, bold=bold) <= usable:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        # The word alone may still not fit — hard-split it.
        while text_width_in(word, pt, bold=bold) > usable:
            cut = len(word)
            while cut > 1 and text_width_in(word[:cut], pt, bold=bold) > usable:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def wrapped_lines(text: str, width_in: float, pt: float, *, bold: bool = False) -> int:
    """How many lines `text` wraps to. Drop-in replacement for the old
    `_wrapped_lines` estimate, but measured rather than guessed."""
    return max(1, len(wrap(text, width_in, pt, bold=bold)))


def block_height_in(text: str, width_in: float, pt: float, *, bold: bool = False,
                    padding_in: float = 0.0) -> float:
    """Height a wrapped paragraph occupies, in inches, including the text box's
    own 0.05" top and bottom insets."""
    n = wrapped_lines(text, width_in, pt, bold=bold)
    return n * line_height_in(pt) + 0.1 + padding_in


def fit_font_size(text: str, width_in: float, height_in: float, *,
                  max_pt: float, min_pt: float = 7.0, bold: bool = False) -> float:
    """Largest size in [min_pt, max_pt] at which `text` wraps inside the box.

    Returns `min_pt` when nothing fits — the caller has already decided the box
    size, and shrinking below legibility is the lesser evil against overflow.
    """
    pt = max_pt
    while pt > min_pt:
        n = wrapped_lines(text, width_in, pt, bold=bold)
        if n * line_height_in(pt) + 0.06 <= height_in:
            return pt
        pt -= 0.5
    return min_pt
