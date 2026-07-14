"""Course type normalization — the boundary between what an AI *says* and what
the curriculum is allowed to *store*.

Why this exists
---------------
`CourseType` (models.py) is a closed set of six values, and it is not cosmetic:
the type decides which official document the Board of Studies produces (a theory
syllabus, a lab manual, an internship rubric, a project handbook, seminar
guidelines) and — since Phase A — who owns that document, the Board or the Dean.

A language model does not know that. Asked for a curriculum it will happily
return "PROJECT", "Practical", "Laboratory", "Major Project", "mini-project",
each of which is a perfectly reasonable English answer and none of which is a
member of the enum. Reaching `CourseCreate` those become a Pydantic
ValidationError, and one unrecognised word fails an entire program generation
run that was otherwise correct.

So AI vocabulary is translated into curriculum vocabulary HERE, once, before
`CourseCreate(...)` is constructed. Downstream of this function every
course_type is a canonical `CourseType` and nothing else needs to know that
synonyms ever existed.

This is deliberately NOT a validator on `CourseCreate` itself. The API accepts
courses from humans too (POST /programs/{id}/courses), and a human sending an
invalid type through the UI should still get a 422 telling them so, rather than
having the server quietly guess. The guessing is a concession to the AI, and it
stays on the AI's side of the wall.

The ambiguity of "PROJECT"
--------------------------
There is no PROJECT in the enum; there is MINI_PROJECT and MAJOR_PROJECT, and
they are different documents (see CourseType's docstring). But the structure
prompt still asks the model for `course_type PROJECT` on a mini project, and
providers emit bare "PROJECT" for both kinds regardless of what they are asked.

The word alone therefore cannot decide the type — the TITLE does, which is the
same call migration 0086ten made when it split the existing PROJECT rows:

    title reads "mini"/"minor"  ->  MINI_PROJECT
    everything else             ->  MAJOR_PROJECT

MAJOR_PROJECT is the honest default: its handbook is the superset (proposal,
demonstration, viva), so a Board correcting a major project down to a mini one
loses nothing, while the reverse silently drops the viva and the proposal from a
document a student is examined against.
"""

from __future__ import annotations

import logging
import re

from app.modules.m01_program_advisor.models import CourseType

logger = logging.getLogger("vidya.m01.course_types")

__all__ = [
    "COURSE_TYPE_SYNONYMS",
    "normalize_course_type",
    "squash",
]


def squash(value: str) -> str:
    """Reduce a type string to its comparable core: letters and digits, uppercase.

    Spaces, underscores and hyphens carry no meaning here — 'Major Project',
    'MAJOR_PROJECT' and 'major-project' are the same answer typed three ways —
    so they are removed rather than enumerated as three separate synonyms.
    """
    return re.sub(r"[^A-Z0-9]", "", value.upper())


# The bare word a model uses when it has not been told the curriculum
# distinguishes the two project documents. Resolved by title, never stored.
_AMBIGUOUS_PROJECT = "PROJECT"

# Titles that make a "PROJECT" a MINI_PROJECT. 'minor' is included because it is
# what several Indian universities call the same thing, and models mirror it.
_MINI_PROJECT_TITLE = re.compile(r"\bmini|\bminor", re.IGNORECASE)


# ---------------------------------------------------------------------------
# The synonym table. Keys are squash()ed, so an entry covers every spacing and
# punctuation variant of itself: 'MAJORPROJECT' matches 'Major Project',
# 'major_project' and 'major-project' alike.
#
# EXTENDING THIS: when a provider invents a new word for an existing type, add
# the squashed form here and it is handled everywhere the AI writes a course.
# Do NOT add a key that maps to a type it is not — a wrong type is a wrong
# official document, which is worse than the ValidationError it replaces.
# ---------------------------------------------------------------------------
COURSE_TYPE_SYNONYMS: dict[str, str] = {
    # -- canonical values, so the table is closed under its own output --------
    "THEORY":            CourseType.THEORY.value,
    "LAB":               CourseType.LAB.value,
    "INTERNSHIP":        CourseType.INTERNSHIP.value,
    "MINIPROJECT":       CourseType.MINI_PROJECT.value,
    "MAJORPROJECT":      CourseType.MAJOR_PROJECT.value,
    "SEMINAR":           CourseType.SEMINAR.value,

    # -- theory --------------------------------------------------------------
    "CORE":              CourseType.THEORY.value,
    "CORETHEORY":        CourseType.THEORY.value,
    "LECTURE":           CourseType.THEORY.value,

    # -- laboratory ----------------------------------------------------------
    # 'THEORY LAB' and 'PRACTICAL LAB' are LAB: the noun is the lab, and the
    # document owed is an experiment list, not five units of lectures.
    "LABORATORY":        CourseType.LAB.value,
    "PRACTICAL":         CourseType.LAB.value,
    "PRACTICALS":        CourseType.LAB.value,
    "PRACTICALLAB":      CourseType.LAB.value,
    "THEORYLAB":         CourseType.LAB.value,
    "LABPRACTICAL":      CourseType.LAB.value,
    "PRACTICUM":         CourseType.LAB.value,

    # -- project -------------------------------------------------------------
    # Bare PROJECT is intentionally NOT resolved here; see _AMBIGUOUS_PROJECT.
    "MINORPROJECT":      CourseType.MINI_PROJECT.value,
    "PROJECTMINI":       CourseType.MINI_PROJECT.value,
    "MINIPROJECTWORK":   CourseType.MINI_PROJECT.value,
    "MAJORPROJECTWORK":  CourseType.MAJOR_PROJECT.value,
    "CAPSTONE":          CourseType.MAJOR_PROJECT.value,
    "CAPSTONEPROJECT":   CourseType.MAJOR_PROJECT.value,
    "DISSERTATION":      CourseType.MAJOR_PROJECT.value,
    "THESIS":            CourseType.MAJOR_PROJECT.value,
    "PROJECTWORK":       CourseType.MAJOR_PROJECT.value,

    # -- internship ----------------------------------------------------------
    "INDUSTRIALTRAINING":  CourseType.INTERNSHIP.value,
    "INDUSTRYINTERNSHIP":  CourseType.INTERNSHIP.value,
    "FIELDWORK":           CourseType.INTERNSHIP.value,
    "APPRENTICESHIP":      CourseType.INTERNSHIP.value,

    # -- seminar -------------------------------------------------------------
    "TECHNICALSEMINAR":  CourseType.SEMINAR.value,
    "SEMINARS":          CourseType.SEMINAR.value,
}


def _infer_from_title(title: str) -> CourseType | None:
    """Last resort: read the type off the title.

    Mirrors ai_provider._infer_course_type_from_title, but resolves to the
    canonical six rather than the AI's five — the AI layer's 'PROJECT' does not
    exist down here.

    Order matters: 'Mini Project Lab' is a project, and checking 'lab' first
    would hand it an experiment list instead of milestones and reviews.
    """
    t = title.lower()
    if "internship" in t:
        return CourseType.INTERNSHIP
    if "project" in t:
        return (
            CourseType.MINI_PROJECT
            if _MINI_PROJECT_TITLE.search(t)
            else CourseType.MAJOR_PROJECT
        )
    if "lab" in t or "laboratory" in t or "practical" in t:
        return CourseType.LAB
    if "seminar" in t:
        return CourseType.SEMINAR
    return None


def _resolve_project(title: str) -> CourseType:
    """Which project document does a bare 'PROJECT' owe? Decided by the title —
    the same rule migration 0086ten used to split the legacy rows."""
    return (
        CourseType.MINI_PROJECT
        if _MINI_PROJECT_TITLE.search(title)
        else CourseType.MAJOR_PROJECT
    )


def normalize_course_type(
    raw: object,
    *,
    title: str = "",
    default: CourseType | None = CourseType.THEORY,
) -> CourseType | None:
    """Translate whatever the AI called this course into a canonical `CourseType`.

    Case-insensitive, and blind to spaces, underscores and hyphens. Resolution
    order, first hit wins:

        1. a known synonym (or a canonical value)      'Practical'    -> LAB
        2. bare 'PROJECT', disambiguated by title      'Mini Project' -> MINI_PROJECT
        3. the title, when the type is missing/unknown 'DBMS Lab'     -> LAB
        4. `default`

    Args:
        raw:     the provider's course_type. Anything: str, None, junk.
        title:   the course title. Carries the answer when `raw` is bare
                 'PROJECT', absent, or a word nobody has seen before — pass it
                 whenever it is available, which at the persistence boundary is
                 always.
        default: what an unreadable course is, when even the title is silent.
                 THEORY, because that is what an untyped course has always been
                 and it is the one type whose document (a syllabus) a Board is
                 certain to review before it approves anything. Pass None to
                 leave it unset instead.

    Returns a `CourseType`, or None only if `default` is None and nothing matched.
    """
    text = str(raw).strip() if raw is not None else ""
    key = squash(text)

    if key:
        if key == _AMBIGUOUS_PROJECT:
            resolved = _resolve_project(title)
            logger.debug(
                "m01.course_type: bare 'PROJECT' resolved to %s by title %r",
                resolved.value, title,
            )
            return resolved

        canonical = COURSE_TYPE_SYNONYMS.get(key)
        if canonical is not None:
            if key != canonical:
                logger.debug(
                    "m01.course_type: normalized %r -> %s", text, canonical,
                )
            return CourseType(canonical)

    inferred = _infer_from_title(title) if title else None
    if inferred is not None:
        logger.info(
            "m01.course_type: %s course_type %r; inferred %s from title %r",
            "missing" if not key else "unrecognised",
            text, inferred.value, title,
        )
        return inferred

    if key:
        logger.warning(
            "m01.course_type: unrecognised course_type %r for title %r; "
            "falling back to %s. Add it to COURSE_TYPE_SYNONYMS if it recurs.",
            text, title, default.value if default else None,
        )
    return default
