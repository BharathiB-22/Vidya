"""Deck palette and type scale, as data.

These were locals inside `_generate_pptx` and `sz=` literals at ~40 call sites,
which made "what colour is a summary slide" and "how big is a body bullet"
unanswerable without reading every renderer. A generator cannot be swapped for
another (M03 phase 2) while its design language lives in its function body.

Colours are RGBColor because every consumer is a pptx renderer; a second
generator that is not pptx should read `.as_hex()` rather than have this module
pretend to be format-neutral before there is a second format.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from pptx.dml.color import RGBColor


def _hex(value: str) -> RGBColor:
    h = value.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


@dataclass(frozen=True)
class Palette:
    # Structure
    navy:       RGBColor = _hex("0F2044")   # cover background, header bars
    accent:     RGBColor = _hex("2563EB")   # tenant-overridable — key concepts
    teal:       RGBColor = _hex("0891B2")   # examples, activities, resources
    green:      RGBColor = _hex("057850")   # objectives, summaries, definitions
    orange:     RGBColor = _hex("92400E")   # quizzes, common mistakes

    # Type
    white:      RGBColor = _hex("FFFFFF")
    text:       RGBColor = _hex("1E293B")   # dark slate
    grey:       RGBColor = _hex("64748B")   # secondary text
    muted:      RGBColor = _hex("94A3B8")   # cover meta text
    light_grey: RGBColor = _hex("F1F5F9")   # table alternate rows, fills

    # Code
    code_bg:    RGBColor = _hex("1E293B")
    code_text:  RGBColor = _hex("E2E8F0")
    code_gutter: RGBColor = _hex("0F172A")
    line_no:    RGBColor = _hex("64748B")

    # Right / wrong pairs
    wrong:      RGBColor = _hex("991B1B")
    wrong_bg:   RGBColor = _hex("FEF2F2")
    right:      RGBColor = _hex("065535")
    right_bg:   RGBColor = _hex("F0FDF4")

    # Diagram
    node_fill:   RGBColor = _hex("EFF6FF")
    node_border: RGBColor = _hex("2563EB")
    node_text:   RGBColor = _hex("1E293B")
    edge:        RGBColor = _hex("64748B")
    edge_label:  RGBColor = _hex("64748B")


@dataclass(frozen=True)
class TypeScale:
    """Point sizes. One place to answer "is a body bullet bigger than a caption".

    Kept to the sizes the deck actually uses today rather than an idealised
    scale — this lands as a refactor, not a redesign.
    """
    cover_title:    int = 36
    cover_code:     int = 20
    cover_meta:     int = 12
    slide_title:    int = 24
    slide_subtitle: int = 9
    section_label:  int = 9
    chip:           int = 8
    lead:           int = 15
    body:           int = 14
    body_tight:     int = 13
    caption:        int = 11
    table:          int = 10
    footnote:       int = 10
    code:           int = 10


@dataclass(frozen=True)
class Theme:
    palette: Palette = Palette()
    type: TypeScale = TypeScale()

    @classmethod
    def for_tenant(cls, primary_color: str | None) -> "Theme":
        """The tenant's brand colour replaces the accent, and nothing else.

        Deliberately narrow: the accent is the only colour whose meaning is
        "this institution". The green of a summary and the red of a mistake are
        semantic, and a tenant whose brand is red must not turn every correct
        answer red.
        """
        theme = cls()
        if not primary_color:
            return theme
        candidate = primary_color.strip()
        if not (candidate.startswith("#") and len(candidate) == 7):
            return theme
        try:
            accent = _hex(candidate)
        except ValueError:
            return theme
        return replace(theme, palette=replace(theme.palette, accent=accent))
