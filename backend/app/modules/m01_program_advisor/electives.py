"""What an elective basket IS — and what it must never become.

An elective basket is a curriculum SLOT: "Elective 1, semester 3, 3 credits". The
student takes exactly one subject from it, so the slot contributes its credits once,
whichever subject that is. The subjects inside it — Artificial Intelligence, Data
Mining, Cloud Computing — are real courses: each has a code, a syllabus, a lecturer
and an examination.

The slot has none of those things. It is not taught, it is not examined, and nobody
sits it. It exists in `elective_baskets`, and nowhere else.

Yet the system had two of them living in `courses`:

    MCA305  "Elective 1"   THEORY   semester 3   -- inside basket "Elective 1"
    MCA308  "Elective 2"   THEORY   semester 3   -- inside basket "Elective 2"

They came from the curriculum generator, whose prompt told the model that "an
elective paper is ONE curriculum course" while also asking it for the paper's
alternatives — so it produced both, and the ingest saved both. The damage is not
cosmetic: a placeholder carries a course code, takes a course type, is handed its own
official syllabus to generate, and stands in the approve gate blocking the curriculum
until a Board approves a syllabus for a subject that does not exist.

This module is the single definition of that mistake, so that every path which
creates or renames a course — the AI ingest, the Dean's Add Course form, a rename,
adding a choice to a basket — refuses it in the same words. One rule, one place: a
guard that lives in four copies is a guard that will disagree with itself.
"""
from __future__ import annotations

import re

# "Elective", "Elective 1", "Elective-2", "Elective: 3", "Professional Elective III",
# "Open Elective 2", "Programme Elective", "Departmental Elective IV", "Core Elective".
#
# Anchored, and matched against the WHOLE title: this must catch the slot and nothing
# else. "Elective 1" is a slot; "Machine Learning" is a subject; and — the case that
# decides how strict the pattern may be — "Elective Course on Cryptography" is a
# subject too, however oddly named, so a substring test would have been wrong.
_SLOT_TITLE = re.compile(
    r"""^\s*
        (?:professional|open|program(?:me)?|department(?:al)?|core|discipline)?
        \s*
        elective
        \s*
        (?:paper|basket|slot|group)?
        \s*
        [-–:.#]?
        \s*
        (?:\d+|[ivxIVX]+)?
        \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_basket_placeholder(title: str | None, basket_name: str | None = None) -> bool:
    """Is this course title really the name of a SLOT?

    Two ways to be one, and a curriculum needs both caught:

      1. The title is a generic elective label — "Elective 2", "Professional
         Elective", "Open Elective III". No university teaches a subject by that name.

      2. The title is exactly the name of the basket the course sits in. A basket
         named "Data Science Elective" holding a course called "Data Science Elective"
         is the same mistake wearing a better disguise, and the pattern above will not
         catch it.
    """
    text = (title or "").strip()
    if not text:
        return False

    if _SLOT_TITLE.match(text):
        return True

    basket = (basket_name or "").strip()
    return bool(basket) and text.casefold() == basket.casefold()


# What the Dean or the Board is told when they try to create one. It names the mistake
# and the thing they actually wanted, because "invalid title" would leave them
# retyping the same word with a different number.
PLACEHOLDER_MESSAGE = (
    "An elective basket is a curriculum slot, not a subject — nobody teaches a course "
    "called {title!r}, and no student sits an examination in it. Create the basket "
    "(Elective 1, semester N, its credits), then add the real subjects a student may "
    "choose from inside it: Artificial Intelligence, Data Mining, Cloud Computing."
)


def placeholder_message(title: str | None) -> str:
    return PLACEHOLDER_MESSAGE.format(title=(title or "").strip())
