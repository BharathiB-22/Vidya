"""
M02 AI provider — syllabus generation via Gemini (primary) with Groq fallback.

Safety contract:
  - AI generates: COs, Bloom levels, units, topics, pedagogy, reference search queries.
  - AI must NEVER generate: DOI, ISBN, author names, publisher names, or any
    bibliographic metadata.  The _RefQueryAI schema has no such fields;
    _validate_result checks the parsed output before returning it.
  - Malformed or under-specified AI responses are rejected with typed exceptions.
  - Gemini and Groq clients are imported lazily so the module loads cleanly in tests.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("vidya.m02.ai_provider")

from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.modules.m02_syllabus.formatting import roman
from app.modules.m02_syllabus.models import BloomLevel, RefType


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SyllabusAIError(Exception):
    """Base for all AI provider failures."""


class SyllabusAIBlockedError(SyllabusAIError):
    """Gemini safety filter blocked the response or quota exhausted."""


class SyllabusAIParseError(SyllabusAIError):
    """AI response did not match the expected JSON schema."""


class SyllabusAIValidationError(SyllabusAIError):
    """Response parsed but failed business-rule validation."""


# ---------------------------------------------------------------------------
# IO dataclasses (no ORM dependency)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class POContext:
    id:          str          # UUID as string (avoids UUID import here)
    code:        str          # e.g. PO1, PO2
    description: str


@dataclasses.dataclass
class SyllabusGenerationContext:
    course_id:           str          # UUID as string
    course_code:         str
    course_title:        str
    course_credits:      int
    program_outcomes:    list[POContext]
    custom_instructions: str | None
    # The Course Information header of an official university syllabus. All
    # derived from the `courses` row (see m02/formatting.py), never typed in.
    # The AI writes the syllabus TO this header — units are paced against the
    # contact hours, and practical components appear only if there are practical
    # hours to fill.
    ltp:                 str = "0-0-0"   # "3-1-2"
    contact_hours:       int = 0         # (L + T + P) x 15 weeks
    category:            str = "Core"    # Core | Elective | Lab | Project
    has_practical:       bool = False

    # WHAT KIND of course this is, and therefore WHAT DOCUMENT to write. The single
    # most consequential field in this context: it does not tune the syllabus, it
    # decides whether there is a syllabus at all.
    #
    #   THEORY         a full syllabus, Unit I-IV or I-V
    #   LAB            a lab manual and experiment list — NO theory units
    #   INTERNSHIP     no syllabus. Guidelines, rubric, weekly activities, viva
    #   MINI_PROJECT   no syllabus. Milestones, deliverables, reviews, rubrics
    #   MAJOR_PROJECT  no syllabus. A handbook: proposal, timeline, demo, viva
    #   SEMINAR        no syllabus. Seminar guidelines
    #
    # Defaulting to THEORY is safe and is what every pre-V2.3 caller meant.
    course_type:         str = "THEORY"

    # HOW MANY units the Board asked for — four or five, decided before generation.
    #
    # Five is not a universal format: plenty of AICTE / VTU / autonomous regulations
    # run to four. It is the Board's call, so it is asked for exactly and validated
    # exactly — a five-unit response to a four-unit curriculum is rejected, not
    # trimmed, because trimming would silently drop a fifth of the subject.
    #
    # Ignored by every non-theory type: they have no units.
    unit_count:          int = 5

    # The hours ALREADY ALLOCATED to the unit being regenerated, if any. Section
    # regeneration only (see _build_section_prompt).
    #
    # The Board's hour allocation survives a unit rewrite: the total across the units
    # is the course's taught hours, and letting the model re-pick one unit's hours in
    # isolation would quietly break that total. So the model is told what the unit is
    # taught for and paces its topics to fit.
    unit_hours:          int | None = None

    # The Board's hours for EVERY unit — [10, 8, 12, 10] — chosen before generation.
    #
    # Hours are a teaching decision, not a drafting one: they come out of the
    # timetable and the credit structure, and the model has no way of knowing that
    # Unit III is the heavy one this year. So when the Board states them, the model is
    # told what it is writing to and paces each unit's topics accordingly, and the
    # hours it returns are overwritten with these (see the worker).
    #
    # Empty means "the Board did not say" — the model then paces the units against
    # the contact hours on its own, which is what it has always done.
    unit_hours_plan:     list[int] = dataclasses.field(default_factory=list)

    # Every topic the EARLIER units of this syllabus already teach.
    #
    # A syllabus written unit by unit will, left alone, teach linked lists three times:
    # each unit is a fresh request, and the model has no memory of the last one. So each
    # unit is told what has already been taught and is REJECTED if it repeats any of it
    # — the check is mechanical (ai_provider._validate_units), not a plea in the prompt.
    used_topics:         list[str] = dataclasses.field(default_factory=list)

    # WHERE this unit sits on the course's arc — "foundational", "intermediate",
    # "advanced". Assigned by the outline, which divides the whole course at once and
    # is therefore the only step that can see the progression. A unit told nothing
    # about its level restates the basics, because the basics are what a model reaches
    # for when asked about a subject in isolation.
    unit_level:          str | None = None

    # The units this syllabus ACTUALLY teaches, once they have been written —
    # ["Unit I — Linear Data Structures: Abstract Data Types, ...", ...].
    #
    # Objectives, outcomes and reading are drafted AFTER the units, and this is what
    # they are drafted against. A course outcome written before the syllabus exists is
    # a guess about what the course will teach; written after it, it is a statement
    # about what the course does teach, and the two are not the same document.
    unit_summary:        list[str] = dataclasses.field(default_factory=list)

    # What went wrong LAST time, fed back into the next attempt.
    #
    # A syllabus is regenerated until it is deep enough to publish, and a retry that
    # says nothing about the failure is a retry that reproduces it. This carries the
    # violations — "Unit III has 4 topics" — into the prompt of the next attempt, so
    # the model is fixing a specific fault rather than rolling the dice again.
    retry_feedback:      str | None = None


@dataclasses.dataclass
class SyllabusGenerationResult:
    """
    Validated output from the AI provider.

    WHICH fields are populated depends on `doc_type`:

        THEORY    units[] is the document. document{} is empty.
        LAB       units[] is EMPTY. document{} holds the lab manual — experiments,
                  equipment, software, assessment guidelines.
        the rest  units[] is EMPTY. document{} holds the guidelines / handbook.

    `objectives` and `outcomes` are populated for EVERY type, because every type has
    them: a lab has Lab Outcomes, an internship has Learning Outcomes, and all of
    them map to Programme Outcomes exactly like a theory course's COs do. Storing
    them anywhere other than the normal outcomes relationship would fork the CO-PO
    matrix and the accreditation reports that read it.

    reference_queries contains search terms ONLY — no author names, DOIs, ISBNs,
    or publisher names.  The reference enrichment task (STEP-07) calls CrossRef /
    OpenLibrary using these queries to fetch real bibliographic metadata.
    """
    objectives:        list[str]    # Course Objectives — what the course sets out to teach
    outcomes:          list[dict]   # code, description, bloom_level, suggested_po_codes[], po_mapping_strengths{}
    units:             list[dict]   # unit_number, title, content, topics[], total_hours, pedagogy — THEORY only
    practical_components: list[str] # Practical Components — empty unless the course has P hours
    internal_assessment: list[str]  # CIE suggestions — may legitimately be empty
    reference_queries: list[dict]   # query_str, ref_type
    model_used:        str
    provider_name:     str          # "gemini" | "groq" | "deepseek"
    prompt_hash:       str
    # The type-specific document body. Shape is m02.schemas.DOCUMENT_SCHEMAS[doc_type];
    # empty for THEORY, whose document is its units.
    doc_type:          str  = "THEORY"
    document:          dict = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# Private Pydantic models — Gemini response_schema only
# (never returned to callers; mapped to dicts in SyllabusGenerationResult)
# ---------------------------------------------------------------------------

_VALID_BLOOM = {b.value for b in BloomLevel}
_VALID_REF_TYPES = {r.value for r in RefType}
_VALID_PEDAGOGIES = {"lecture", "lab", "seminar", "case_study", "mixed"}
_VALID_MAPPING_STRENGTHS = {"HIGH", "MEDIUM", "LOW"}


class _TopicAI(BaseModel):
    """One line of a unit — an academic topic as it PRINTS in the regulation.

    These are the bullets under a unit heading, and there are 10-15 of them per unit.

    The floor is THREE characters, not eight. Eight was a crude proxy for "not filler"
    and it was wrong: 'B-Trees', 'Arrays', 'Stack', 'Queue', 'Trees' and 'Hashing' are
    all real headings in a real Anna University syllabus, and every one of them was
    being rejected — taking the whole unit, and eventually the whole syllabus, with it.
    A length cannot tell a topic from a placeholder. `_FILLER_CONCEPTS` names the
    placeholders ('Basics', 'Overview', 'Introduction'), `_is_explanation` catches the
    other failure (a sentence pretending to be a heading), and both judge the words
    rather than counting them.
    """
    title:          str = Field(..., min_length=3)
    description:    str | None = None
    hours_estimate: int | None = Field(default=None, ge=1)
    subtopics:      list[str]  = Field(default_factory=list)
    examples:       list[str]  = Field(default_factory=list)
    lab_reference:  str | None = None


class _COAI(BaseModel):
    """One Course Outcome — and the accreditation data hanging off it.

    NOTHING HERE IS DEFAULTED.

    `bloom_level` and `po_mapping_strengths` are not decoration. They are the CO-PO
    matrix, which is what NBA and NAAC actually read: the Bloom level is the cognitive
    level the university claims to teach at, and the strength is how strongly it claims
    this outcome drives that programme outcome. Both used to be filled in silently when
    the model omitted them — APPLY, and MEDIUM — so a syllabus could reach an approved
    regulation, be locked, and be submitted to an accreditation body carrying claims
    that no academic ever made and no model ever wrote.

    A missing Bloom level is now a FAILED generation, retried. So is a missing strength.
    They are cheap to regenerate and impossible to un-submit.
    """
    code:                  str = Field(..., min_length=1, max_length=20)
    description:           str = Field(..., min_length=15)
    bloom_level:           str
    suggested_po_codes:    list[str] = Field(default_factory=list)
    po_mapping_strengths:  dict[str, str] = Field(default_factory=dict)
    # po_code -> "HIGH" | "MEDIUM" | "LOW" — how strongly this CO supports that PO.

    @model_validator(mode="after")
    def _check_bloom(self) -> _COAI:
        up = (self.bloom_level or "").upper().strip()
        if up not in _VALID_BLOOM:
            raise ValueError(
                f"'{self.code}' has no valid Bloom's level ({self.bloom_level!r}). It is "
                f"the cognitive level this course claims to teach at, it is read by "
                f"NBA and NAAC, and it is not ours to guess. One of: "
                f"{', '.join(sorted(_VALID_BLOOM))}."
            )
        self.bloom_level = up
        return self

    @model_validator(mode="after")
    def _check_mapping_strengths(self) -> _COAI:
        normalized: dict[str, str] = {}
        for po_code in self.suggested_po_codes:
            raw = str(self.po_mapping_strengths.get(po_code, "")).upper().strip()
            if raw not in _VALID_MAPPING_STRENGTHS:
                raise ValueError(
                    f"'{self.code}' claims to support {po_code} but does not say how "
                    f"strongly ({raw or 'nothing'!r}). That figure IS the CO-PO matrix "
                    f"an accreditation body reads. One of: HIGH, MEDIUM, LOW."
                )
            normalized[po_code] = raw
        self.po_mapping_strengths = normalized
        return self


class _UnitAI(BaseModel):
    unit_number: int  = Field(..., ge=1)
    title:       str  = Field(..., min_length=3)

    # The unit's syllabus lines — 10 to 15 of them. THIS is what prints:
    #
    #   UNIT I - INTRODUCTION TO COMPUTER SYSTEMS              (10 Hours)
    #     • Evolution of Computing
    #     • Characteristics of Computer Systems
    #     • Functional Units
    #     • Von Neumann Architecture
    #     • Harvard Architecture
    #     ...
    #
    # The count floor is the single most important constraint in this file. A model
    # asked for "topics" returns four or five and stops; a real AICTE / Anna
    # University / VTU unit runs to 10-15 lines, and a Board that has to write six
    # more per unit by hand is not being helped by the AI at all.
    #
    # Eight here rather than the real floor of ten (MIN_TOPICS_PER_UNIT), on purpose:
    # a nine-topic unit should fail the BUSINESS rule, which says exactly what is
    # wrong with it and how deep a unit has to be, not the schema, which fails with
    # an opaque parse error. Below eight there is nothing worth diagnosing.
    topics:      list[_TopicAI] = Field(..., min_length=8)

    # A prose rendering of the same material, for regulations that print units as a
    # flowing paragraph rather than as bullets. Optional: the topic list is the
    # canonical content, and `content` is derived from it when the model omits it.
    content:     str | None = None

    total_hours: int  = Field(..., ge=1)
    pedagogy:    str  = "lecture"

    @model_validator(mode="after")
    def _check_pedagogy(self) -> _UnitAI:
        if self.pedagogy.lower() not in _VALID_PEDAGOGIES:
            self.pedagogy = "lecture"   # safe fallback; never reject over pedagogy
        else:
            self.pedagogy = self.pedagogy.lower()
        return self

    @model_validator(mode="after")
    def _derive_content_from_topics(self) -> _UnitAI:
        """Keep the prose rendering in step with the topic list.

        The topics ARE the unit. `content` is a second view of the same material,
        so it is composed from them whenever the model does not supply one — that
        way the two can never disagree, and a regulation that prints units as prose
        gets the same syllabus as one that prints bullets.
        """
        text = (self.content or "").strip()
        for bullet in ("•", "‣", "◦"):
            text = text.replace(f"\n{bullet}", ", ").replace(bullet, "")
        text = " ".join(text.split())

        if not text and self.topics:
            text = ", ".join(t.title for t in self.topics) + "."

        self.content = text or None
        return self


class _RefQueryAI(BaseModel):
    """
    A reference search query — search terms ONLY.

    Fields that are intentionally ABSENT (and must stay absent):
      doi, isbn, author, authors, author_name, publisher, year, title (exact).
    Any such field from the AI is stripped by Pydantic's default ignore-extra
    behaviour and then caught by _validate_no_metadata() below.
    """
    query_str: str = Field(..., min_length=5)
    ref_type:  str = "TEXTBOOK"

    @model_validator(mode="after")
    def _check_ref_type(self) -> _RefQueryAI:
        if self.ref_type.upper() not in _VALID_REF_TYPES:
            self.ref_type = "TEXTBOOK"
        else:
            self.ref_type = self.ref_type.upper()
        return self


class _SyllabusAI(BaseModel):
    """One official university syllabus.

    The shape mirrors a real regulation document, in its printed order:

        Course Objectives
        Course Outcomes (CO1..CO5)
        Unit I ... Unit V           <- each with a prose CONTENT block and hours
        Practical Components        (if applicable)
        Internal Assessment         (optional)
        Text Books / Reference Books / Suggested Reading / Web Resources

    The prose fields are plain lines, because that is how a university syllabus
    prints them.
    """
    objectives:           list[str] = Field(default_factory=list)
    outcomes:             list[_COAI]
    units:                list[_UnitAI]
    practical_components: list[str] = Field(default_factory=list)
    internal_assessment:  list[str] = Field(default_factory=list)
    reference_queries:    list[_RefQueryAI]


# ---------------------------------------------------------------------------
# The NON-theory documents
#
# A Board of Studies does not write a syllabus for an internship, and generating
# five units of theory for one is not a cosmetic error — it is a regulation
# promising lectures that nobody will ever deliver, for a student who is not on
# campus to attend them.
#
# So each type gets its own response schema, and the model is asked for the
# document that type actually has. The minimum lengths below are the same argument
# as `_UnitAI.topics`: a model asked for "milestones" returns two and stops, and an
# internship handbook with two milestones is an outline the Board would have to
# write itself — which is the work the AI is here to do.
#
# Every type still carries objectives and outcomes, because every type has them: a
# lab's Lab Outcomes and an internship's Learning Outcomes are Course Outcomes, and
# they map to Programme Outcomes like any other.
# ---------------------------------------------------------------------------

class _ExperimentAI(BaseModel):
    """One experiment of a lab manual — what is actually performed in the room."""
    number:    int = Field(..., ge=1)
    title:     str = Field(..., min_length=8)
    aim:       str | None = None
    procedure: str | None = None
    apparatus: list[str] = Field(default_factory=list)
    hours:     int | None = Field(default=None, ge=1)


class _RubricAI(BaseModel):
    """One row of an evaluation rubric: what is judged, and what it is worth."""
    criterion:  str = Field(..., min_length=3)
    weightage:  int | None = Field(default=None, ge=0, le=100)
    descriptor: str | None = None


class _LabAI(BaseModel):
    """LAB — a Lab Manual. There is no `units` field, deliberately: a laboratory is
    not taught in five units and never was."""
    objectives:            list[str]           = Field(default_factory=list)
    outcomes:              list[_COAI]                                    # the Lab Outcomes
    manual_intro:          str | None          = None
    experiments:           list[_ExperimentAI] = Field(..., min_length=8)
    equipment:             list[str]           = Field(default_factory=list)
    software:              list[str]           = Field(default_factory=list)
    assessment_guidelines: list[str]           = Field(default_factory=list)
    reference_queries:     list[_RefQueryAI]   = Field(default_factory=list)


class _InternshipAI(BaseModel):
    objectives:           list[str]         = Field(default_factory=list)
    outcomes:            list[_COAI]                                    # Learning Outcomes
    guidelines:          list[str]         = Field(..., min_length=5)
    duration:            str | None        = None
    credits:             int | None        = Field(default=None, ge=0)
    evaluation_rubric:   list[_RubricAI]   = Field(..., min_length=3)
    weekly_activities:   list[str]         = Field(..., min_length=4)
    company_requirements: list[str]        = Field(..., min_length=3)
    report_format:       list[str]         = Field(..., min_length=4)
    viva_guidelines:     list[str]         = Field(..., min_length=3)
    reference_queries:   list[_RefQueryAI] = Field(default_factory=list)


class _MiniProjectAI(BaseModel):
    objectives:        list[str]         = Field(default_factory=list)
    outcomes:          list[_COAI]
    guidelines:        list[str]         = Field(..., min_length=5)
    milestones:        list[str]         = Field(..., min_length=4)
    deliverables:      list[str]         = Field(..., min_length=3)
    reviews:           list[str]         = Field(..., min_length=2)
    rubrics:           list[_RubricAI]   = Field(..., min_length=3)
    reference_queries: list[_RefQueryAI] = Field(default_factory=list)


class _MajorProjectAI(BaseModel):
    """MAJOR_PROJECT — the superset of the mini project. It carries a proposal, a
    demonstration and a viva, which a mini project does not."""
    objectives:          list[str]         = Field(default_factory=list)
    outcomes:            list[_COAI]
    handbook:            list[str]         = Field(..., min_length=5)
    proposal_format:     list[str]         = Field(..., min_length=4)
    timeline:            list[str]         = Field(..., min_length=4)
    reviews:             list[str]         = Field(..., min_length=3)
    rubrics:             list[_RubricAI]   = Field(..., min_length=3)
    final_report_format: list[str]         = Field(..., min_length=5)
    demonstration:       list[str]         = Field(..., min_length=2)
    viva:                list[str]         = Field(..., min_length=3)
    reference_queries:   list[_RefQueryAI] = Field(default_factory=list)


class _SeminarAI(BaseModel):
    objectives:          list[str]         = Field(default_factory=list)
    outcomes:            list[_COAI]
    guidelines:          list[str]         = Field(..., min_length=5)
    topic_selection:     list[str]         = Field(..., min_length=3)
    presentation_format: list[str]         = Field(..., min_length=3)
    evaluation_rubric:   list[_RubricAI]   = Field(..., min_length=3)
    deliverables:        list[str]         = Field(..., min_length=2)
    reference_queries:   list[_RefQueryAI] = Field(default_factory=list)


# Course type -> the full-generation response schema. THEORY is the only one that
# yields units; the rest yield a document body.
TYPE_THEORY        = "THEORY"
TYPE_LAB           = "LAB"
TYPE_INTERNSHIP    = "INTERNSHIP"
TYPE_MINI_PROJECT  = "MINI_PROJECT"
TYPE_MAJOR_PROJECT = "MAJOR_PROJECT"
TYPE_SEMINAR       = "SEMINAR"

_TYPE_SCHEMAS: dict[str, type[BaseModel]] = {
    TYPE_THEORY:        _SyllabusAI,
    TYPE_LAB:           _LabAI,
    TYPE_INTERNSHIP:    _InternshipAI,
    TYPE_MINI_PROJECT:  _MiniProjectAI,
    TYPE_MAJOR_PROJECT: _MajorProjectAI,
    TYPE_SEMINAR:       _SeminarAI,
}

# Which keys of each type's response make up its stored `document` body. Must stay
# in step with m02.schemas.DOCUMENT_SCHEMAS — that is what validates the result.
_DOCUMENT_FIELDS: dict[str, tuple[str, ...]] = {
    TYPE_LAB: (
        "manual_intro", "experiments", "equipment", "software",
        "assessment_guidelines",
    ),
    TYPE_INTERNSHIP: (
        "guidelines", "duration", "credits", "evaluation_rubric",
        "weekly_activities", "company_requirements", "report_format",
        "viva_guidelines",
    ),
    TYPE_MINI_PROJECT: (
        "guidelines", "milestones", "deliverables", "reviews", "rubrics",
    ),
    TYPE_MAJOR_PROJECT: (
        "handbook", "proposal_format", "timeline", "reviews", "rubrics",
        "final_report_format", "demonstration", "viva",
    ),
    TYPE_SEMINAR: (
        "guidelines", "topic_selection", "presentation_format",
        "evaluation_rubric", "deliverables",
    ),
}


def normalize_course_type(raw: str | None) -> str:
    """A course's type, defaulting to THEORY.

    THEORY is the right default for an unrecognised or missing type: it is what
    every course was before V2.3, and a syllabus offered where guidelines were
    wanted is a document the Board can see is wrong. The reverse — an unlabelled
    theory course silently getting an internship rubric instead of its units — is
    the failure that would actually reach a student.
    """
    value = (raw or "").upper().strip()
    return value if value in _TYPE_SCHEMAS else TYPE_THEORY


def response_schema_for(ctx: SyllabusGenerationContext) -> type[BaseModel]:
    return _TYPE_SCHEMAS[normalize_course_type(ctx.course_type)]


def _document_from(parsed: BaseModel, course_type: str) -> dict:
    """Pull the type-specific document body out of a parsed response.

    THEORY returns {} — its document is its units, and a stray document body on a
    theory syllabus would be a second, unvalidated home for content that belongs in
    them.
    """
    fields = _DOCUMENT_FIELDS.get(course_type)
    if not fields:
        return {}

    dumped = parsed.model_dump(mode="json")
    return {key: dumped[key] for key in fields if key in dumped}


# ---------------------------------------------------------------------------
# Partial regeneration — one section at a time
#
# The Board should never have to regenerate a whole syllabus because ONE unit came
# out weak. Five units, five COs, a reference list and two prose sections is a lot
# of work to throw away, and much of it will have been hand-edited by the time
# anyone notices the flaw.
#
# So each section has its own response schema, and the provider can be asked for
# just that slice. A regenerated unit is validated to exactly the same depth bar as
# a full generation (`_validate_units`) — otherwise "regenerate this one unit"
# becomes the back door through which a thin unit reaches the document.
# ---------------------------------------------------------------------------

class _UnitOnlyAI(BaseModel):
    unit: _UnitAI


class _ObjectivesOnlyAI(BaseModel):
    objectives: list[str] = Field(..., min_length=3)


class _OutcomesOnlyAI(BaseModel):
    outcomes: list[_COAI] = Field(..., min_length=4)


class _ReferencesOnlyAI(BaseModel):
    reference_queries: list[_RefQueryAI] = Field(..., min_length=4)


class _BooksOnlyAI(BaseModel):
    """Text Books only. Separate from REFERENCES because they are separate printed
    sections, and a Board unhappy with the Text Books has no reason to lose its Web
    Resources along with them."""
    reference_queries: list[_RefQueryAI] = Field(..., min_length=3)


class _PracticalsOnlyAI(BaseModel):
    practical_components: list[str] = Field(..., min_length=6)


_LEVELS = ("foundational", "intermediate", "advanced")


class _PlannedUnitAI(BaseModel):
    """One unit of the OUTLINE: its title, what it covers, and how hard it is.

    The outline is what stops a unit-at-a-time syllabus from becoming five essays on
    the same subject. Written first and in one piece, it decides how the course is
    divided; each unit is then drafted against its own slice of it, knowing what the
    others hold.

    It is an INTERNAL planning step and nothing else. It is never stored, never shown,
    and never editable: the curriculum the Board wrote is the source of truth, and an
    outline that could be edited would be a second one.
    """
    unit_number: int = Field(..., ge=1)
    title:       str = Field(..., min_length=3)
    scope:       str = Field(..., min_length=20)   # what this unit covers, in a line

    # foundational -> intermediate -> advanced. A course is a progression, and the
    # outline is the only step that sees the whole of it: a unit drafted in isolation
    # reaches for the basics whatever number it carries.
    level:       str = "intermediate"

    @model_validator(mode="after")
    def _check_level(self) -> _PlannedUnitAI:
        if (self.level or "").lower().strip() not in _LEVELS:
            self.level = "intermediate"   # never reject a syllabus over an adjective
        else:
            self.level = self.level.lower().strip()
        return self


class _OutlineAI(BaseModel):
    units: list[_PlannedUnitAI]


# What the caller may ask to be rewritten.
SECTION_UNIT       = "UNIT"
SECTION_OBJECTIVES = "OBJECTIVES"
SECTION_OUTCOMES   = "OUTCOMES"
SECTION_REFERENCES = "REFERENCES"
SECTION_BOOKS      = "BOOKS"
SECTION_PRACTICALS = "PRACTICALS"
SECTION_DOCUMENT   = "DOCUMENT"

# INTERNAL. The first step of a theory generation, never a Board-facing "regenerate
# this" — there is nothing in the printed syllabus called an outline. It divides the
# course into its units before any of them is written.
SECTION_OUTLINE    = "OUTLINE"

_SECTION_SCHEMAS = {
    SECTION_UNIT:       _UnitOnlyAI,
    SECTION_OBJECTIVES: _ObjectivesOnlyAI,
    SECTION_OUTCOMES:   _OutcomesOnlyAI,
    SECTION_REFERENCES: _ReferencesOnlyAI,
    SECTION_BOOKS:      _BooksOnlyAI,
    SECTION_PRACTICALS: _PracticalsOnlyAI,
    SECTION_OUTLINE:    _OutlineAI,
}


def section_schema_for(section: str, ctx: SyllabusGenerationContext) -> type[BaseModel]:
    """The response schema for one regenerated section.

    DOCUMENT is the only section whose schema depends on the course: rewriting "the
    document" of a lab means an experiment list, and of a major project a handbook.
    It is the non-theory equivalent of regenerating the units, and the only section
    that applies to a course which has no units at all.
    """
    if section == SECTION_DOCUMENT:
        return response_schema_for(ctx)
    return _SECTION_SCHEMAS[section]


@dataclasses.dataclass
class SectionGenerationResult:
    """One regenerated slice. Only the field for the requested section is filled."""
    section:           str
    unit:              dict | None = None
    units:             list[dict] | None = None   # DOCUMENT regeneration of a THEORY syllabus
    outline:           list[dict] | None = None   # OUTLINE — the planned units
    objectives:        list[str] | None = None
    outcomes:          list[dict] | None = None
    reference_queries: list[dict] | None = None
    practical_components: list[str] | None = None
    document:          dict | None = None
    model_used:        str = ""
    provider_name:     str = ""
    prompt_hash:       str = ""


# ---------------------------------------------------------------------------
# Business-rule validation (runs after Pydantic parse succeeds)
# ---------------------------------------------------------------------------

_METADATA_KEYWORDS = (
    "doi", "isbn", "issn", "author", "publisher",
    "10.", "978", "979",   # DOI prefix and ISBN-13 prefixes
)


def _validate_result(
    parsed: BaseModel,
    ctx: SyllabusGenerationContext,
) -> list[str]:
    """
    Return a list of violation strings.  Empty list = valid.

    Common to every course type:
      1. Minimum 4 COs and 3 objectives.
      2. All bloom_levels are from the approved set.
      3. All suggested_po_codes exist in the context POs.
      4. reference_queries contain no bibliographic metadata keywords.

    Then the type's own checks: five deep units for a theory syllabus, a real
    experiment list for a lab, a document with nothing hollow in it for the rest.
    """
    errors: list[str] = []
    course_type = normalize_course_type(ctx.course_type)
    valid_po_codes = {po.code for po in ctx.program_outcomes}

    # 1. Minimums — every type has objectives and outcomes.
    if len(parsed.outcomes) < 4:
        errors.append(
            f"AI returned {len(parsed.outcomes)} COs; minimum required is 4."
        )
    if len(parsed.objectives) < 3:
        errors.append(
            f"AI returned {len(parsed.objectives)} Course Objectives; minimum required is 3."
        )

    # 2. Bloom levels (already enforced by _COAI validator, but double-check)
    for co in parsed.outcomes:
        if co.bloom_level not in _VALID_BLOOM:
            errors.append(f"CO '{co.code}' has invalid bloom_level '{co.bloom_level}'.")

    # 3. PO code references
    for co in parsed.outcomes:
        unknown = [c for c in co.suggested_po_codes if c not in valid_po_codes]
        if unknown:
            # Warn but don't reject — AI may suggest sensible codes not in the list.
            # The worker filters these out during CO-PO mapping creation, so a
            # hallucinated code silently drops that CO-PO link; log it so a
            # persistent mismatch (e.g. wrong PO codes passed in context) is visible.
            logger.warning(
                "CO '%s' suggested unknown PO code(s) %s; valid codes are %s. "
                "These will be dropped, not mapped.",
                co.code, unknown, sorted(valid_po_codes),
            )

    # 4. Reference queries must not contain bibliographic metadata
    errors.extend(_validate_reference_queries(parsed.reference_queries))

    # 5. Whatever this TYPE of document has to be right about.
    if course_type == TYPE_THEORY:
        errors.extend(_validate_theory(parsed, ctx))
    elif course_type == TYPE_LAB:
        errors.extend(_validate_lab(parsed))
    else:
        errors.extend(_validate_guideline_document(parsed, course_type))

    return errors


def _validate_reference_queries(queries) -> list[str]:
    errors: list[str] = []
    for i, rq in enumerate(queries):
        found = [kw for kw in _METADATA_KEYWORDS if kw in rq.query_str.lower()]
        if found:
            errors.append(
                f"reference_queries[{i}] '{rq.query_str[:60]}' "
                f"appears to contain bibliographic metadata keywords: {found}. "
                "Queries must be search terms only."
            )
    return errors


def _validate_theory(parsed: _SyllabusAI, ctx: SyllabusGenerationContext) -> list[str]:
    """The theory syllabus: the units the BOARD asked for, each with the depth of a
    real regulation."""
    errors: list[str] = []
    wanted = resolve_unit_count(ctx.unit_count)

    # HARD, unlike the count checks in _validate_result: the Board decided this
    # curriculum is taught in `wanted` units, and a syllabus with a different number
    # is not the document it asked for. Nor can it be trimmed to fit — dropping the
    # fifth unit of a five-unit response would drop a fifth of the subject with it.
    # Phrased without the words "minimum required is" precisely so that
    # `_is_soft_violation` does not wave it through.
    if len(parsed.units) != wanted:
        errors.append(
            f"AI returned {len(parsed.units)} units. The Board asked for EXACTLY "
            f"{wanted} — Unit I to Unit {roman(wanted)}."
        )

    # A theory course with no practical hours must not sprout laboratory work. HARD:
    # an invented lab in an official, Board-approved syllabus is a commitment the
    # department cannot staff or timetable.
    if parsed.practical_components and not ctx.has_practical:
        errors.append(
            f"AI returned {len(parsed.practical_components)} practical components "
            f"for {ctx.course_code}, which has no practical hours (L-T-P {ctx.ltp}). "
            "A theory course must not carry laboratory work."
        )

    unit_numbers = [u.unit_number for u in parsed.units]
    if len(unit_numbers) != len(set(unit_numbers)):
        errors.append("Duplicate unit_number values in AI response.")

    # Every unit must have the DEPTH of a real regulation, and none of the filler.
    #
    # These are HARD errors. The whole point of this feature is that a Board of
    # Studies can publish the result with minor editing — a unit reading
    # "Introduction, Basics, Advanced Topics" is worse than no unit at all, because
    # it looks finished. Regenerating costs one AI call; a hollow syllabus in the
    # university handbook costs the institution its credibility, and it is a
    # student who eventually finds it.
    errors.extend(_validate_units(parsed.units))

    return errors


def _validate_lab(parsed: _LabAI) -> list[str]:
    """The lab manual: a real experiment list, and the means to perform it.

    An experiment list is to a lab manual what the topic list is to a theory unit —
    the thing that actually prints, and the thing a model will happily return four
    of. "Experiment 1: Introduction" is the same hollowness as a unit reading
    "Basics", and it fails for the same reason.
    """
    errors: list[str] = []

    titles = [e.title.strip() for e in parsed.experiments]

    if len(titles) < _MIN_EXPERIMENTS:
        errors.append(
            f"The lab manual lists only {len(titles)} experiment(s). A university "
            f"laboratory course runs to {_TARGET_EXPERIMENTS}-{_MAX_EXPERIMENTS} "
            "experiments across the semester; this is an outline, not a manual."
        )

    filler = [t for t in titles if _is_filler(t)]
    if filler:
        errors.append(
            f"The experiment list contains placeholder entries {filler[:5]}. Every "
            "experiment must be a specific procedure a student can perform at a "
            "bench — a reader has to know what they will actually do."
        )

    lowered = [t.lower() for t in titles]
    if len(set(lowered)) < len(lowered):
        dupes = sorted({t for t in lowered if lowered.count(t) > 1})
        errors.append(
            f"The experiment list repeats {dupes[:5]}. A padded list is not a "
            "fuller laboratory."
        )

    # A laboratory with no equipment and no software cannot be run. This is the lab
    # equivalent of a syllabus with no units: the document looks complete and tells
    # the technician nothing.
    if not parsed.equipment and not parsed.software:
        errors.append(
            "The lab manual names neither equipment nor software. A laboratory "
            "course must say what is needed to run it."
        )

    if not parsed.assessment_guidelines:
        errors.append(
            "The lab manual has no assessment guidelines. A laboratory course must "
            "say how the student's work in it is marked."
        )

    return errors


def _validate_guideline_document(parsed: BaseModel, course_type: str) -> list[str]:
    """Internship, Mini Project, Major Project, Seminar.

    Pydantic's min_length has already enforced the counts. What it cannot see is
    HOLLOWNESS: five "guidelines" reading 'Introduction', 'Overview', 'Conclusion'
    satisfy every length bar and say nothing at all. The document these types
    produce IS its prose — there are no units to fall back on — so a filler line
    here is proportionally far more damaging than one in a theory unit.
    """
    errors: list[str] = []

    dumped = parsed.model_dump(mode="json")
    for field in _DOCUMENT_FIELDS.get(course_type, ()):
        value = dumped.get(field)
        if not isinstance(value, list):
            continue                            # duration, credits — scalars

        lines = [str(v).strip() for v in value if isinstance(v, str)]
        filler = [line for line in lines if _is_filler(line)]
        if filler:
            errors.append(
                f"'{field}' contains placeholder lines {filler[:5]}. This document "
                "has no units to carry its meaning — every line of it must say "
                "something a student or supervisor could act on."
            )

        lowered = [line.lower() for line in lines]
        if len(set(lowered)) < len(lowered):
            dupes = sorted({line for line in lowered if lowered.count(line) > 1})
            errors.append(f"'{field}' repeats {dupes[:3]}. A padded list is not a fuller document.")

    return errors


def _normalize_topic(title: str) -> str:
    """A topic reduced to what it MEANS, for comparing one unit's against another's.

    'Doubly Linked Lists', 'Doubly-Linked List' and 'The Doubly Linked List' are one
    topic taught three times, and a syllabus that does that has a hole in it somewhere
    else. Punctuation, articles, case and a trailing plural all go.
    """
    text = re.sub(r"[^a-z0-9 ]+", " ", title.lower())
    words = [w for w in text.split() if w not in _STOPWORDS]
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words)


_STOPWORDS = {"the", "a", "an", "of", "to", "and", "in", "for", "on", "its", "with"}


def _cross_unit_duplicates(units, already_taught: list[str]) -> list[str]:
    """Topics this unit repeats — from an earlier unit, or from another unit here.

    The one failure a unit-at-a-time syllabus is prone to, and the one no amount of
    prompting reliably prevents: each unit is a fresh request, and a model asked about
    data structures will teach the linked list in Unit I, again in Unit II, and once
    more in Unit IV. Caught mechanically, and the offending unit — only that unit — is
    regenerated.
    """
    seen = {_normalize_topic(t): t for t in already_taught}
    errors: list[str] = []

    for unit in units:
        repeats: list[str] = []
        for topic in unit.topics:
            key = _normalize_topic(topic.title)
            if not key:
                continue
            if key in seen:
                repeats.append(f"{topic.title!r} (already taught as {seen[key]!r})")
            else:
                seen[key] = topic.title

        if repeats:
            errors.append(
                f"Unit {unit.unit_number} repeats material the syllabus already "
                f"teaches: {repeats[:5]}. Each unit must carry its OWN ground — a "
                "topic taught twice is a topic missing somewhere else."
            )

    return errors


def _validate_units(units, already_taught: list[str] | None = None) -> list[str]:
    """Depth and substance checks on unit topic lists. Shared with per-unit
    regeneration, which must hold to exactly the same bar as a full generation —
    otherwise 'regenerate this one unit' becomes the back door through which a thin
    unit reaches the document."""
    errors: list[str] = []

    # Nothing may be taught twice — not within a unit, and not across the syllabus.
    errors.extend(_cross_unit_duplicates(units, already_taught or []))

    for unit in units:
        titles = [t.title.strip() for t in unit.topics]

        if len(titles) < MIN_TOPICS_PER_UNIT:
            errors.append(
                f"Unit {unit.unit_number} lists only {len(titles)} topic(s). An "
                f"AICTE / Anna University / VTU unit runs to "
                f"{MIN_TOPICS_PER_UNIT}-{_MAX_TOPICS_PER_UNIT} academic topics; this "
                "is an outline, not a regulation, and the Board would have to write "
                "the rest by hand."
            )

        filler = [t for t in titles if _is_filler(t)]
        if filler:
            errors.append(
                f"Unit {unit.unit_number} contains placeholder topics {filler[:5]}. "
                "Every line must be a specific, teachable topic — a reader has to be "
                "able to tell what will be taught in the room."
            )

        # An EXPLANATION is not a syllabus point. A regulation prints 'Doubly Linked
        # List', not a sentence about what one is — and a Board that has to cut every
        # line down to size before printing has been handed an essay, not a syllabus.
        essays = [t for t in titles if _is_explanation(t)]
        if essays:
            errors.append(
                f"Unit {unit.unit_number} states topics as sentences rather than "
                f"syllabus points: {[t[:60] + '…' for t in essays[:3]]}. A regulation "
                "prints short noun phrases — 'Doubly Linked List', 'Time and Space "
                "Complexity' — never explanations."
            )

        # A model that runs out of ideas repeats itself. Twelve lines that are
        # really six is the same hollowness, wearing a longer coat.
        lowered = [t.lower() for t in titles]
        if len(set(lowered)) < len(lowered):
            dupes = sorted({t for t in lowered if lowered.count(t) > 1})
            errors.append(
                f"Unit {unit.unit_number} repeats topics {dupes[:5]}. "
                "A padded list is not a deeper unit."
            )

    return errors


def _validate_outline(parsed: _OutlineAI, ctx: SyllabusGenerationContext) -> list[str]:
    """The plan, before a single unit is written to it.

    Everything wrong here is wrong five times over afterwards: a duplicated unit title
    is two units teaching the same material, and a unit called 'Introduction' is a
    unit whose topics will be filler however hard the next prompt tries.
    """
    errors: list[str] = []
    wanted = resolve_unit_count(ctx.unit_count)

    if len(parsed.units) != wanted:
        errors.append(
            f"The outline has {len(parsed.units)} units. The Board asked for EXACTLY "
            f"{wanted} — Unit I to Unit {roman(wanted)}."
        )

    titles = [u.title.strip() for u in parsed.units]

    filler = [t for t in titles if _is_filler(t)]
    if filler:
        errors.append(
            f"The outline names units {filler[:3]}. A unit's title is what prints "
            "above it in the regulation — 'Linear Data Structures', not "
            "'Introduction'."
        )

    lowered = [t.lower() for t in titles]
    if len(set(lowered)) < len(lowered):
        errors.append(
            "The outline repeats a unit title. Two units teaching the same material "
            "is a syllabus with a hole in it somewhere else."
        )

    return errors


def _is_filler(title: str) -> bool:
    """Is this line academically empty?

    Exact match on the normalised title, deliberately — 'Applications' alone says
    nothing, while 'Applications of Convolutional Networks' is a real topic, and a
    substring test would throw the second away with the first.
    """
    return title.lower().strip(" .:-") in _FILLER_CONCEPTS


def _is_explanation(title: str) -> bool:
    """Is this a sentence pretending to be a syllabus point?

    Deliberately generous. A real point can be long — 'Applications of Stack and Queue
    in Expression Evaluation' is eight words and perfectly legitimate — so this fires
    only on lines nobody could mistake for a heading: a prose sentence, or one that
    runs past what a printed handbook line holds.
    """
    text = title.strip()
    if len(text) > _MAX_TOPIC_CHARS or len(text.split()) > _MAX_TOPIC_WORDS:
        return True
    # A full stop inside the line means a sentence ended and another began.
    return "." in text.rstrip(".") and not _ABBREVIATION.search(text)


# What a unit is ASKED for, and what it is REJECTED for.
#
# A real AICTE / Anna University / VTU unit runs to 10-15 academic topics. That is
# the shape of the printed regulation, so it is both what the prompt requests and
# where the floor sits: a unit of six topics is an outline wearing a regulation's
# clothes, and the Board would have to write the rest of it by hand — which is the
# exact work the generator exists to do for them.
#
# Below MIN_TOPICS_PER_UNIT the response is rejected and the next provider tried.
# Above _MAX_TOPICS_PER_UNIT nothing is rejected: a broad unit that legitimately
# runs long is a better problem than a thin one, and the Board can delete a line
# far more easily than it can write six.
MIN_TOPICS_PER_UNIT     = 10
_TARGET_TOPICS_PER_UNIT = 12
_MAX_TOPICS_PER_UNIT    = 15

# What a syllabus POINT is, as opposed to an explanation of one. A regulation prints
# 'Time and Space Complexity'; it does not print a sentence about what complexity is.
# Both bounds are deliberately generous — 'Applications of Stack and Queue in
# Expression Evaluation' must survive, and it is eight words and 58 characters.
_MAX_TOPIC_CHARS = 90
_MAX_TOPIC_WORDS = 14

# 'B.Tech.', 'i.e.', 'Dr.' — a full stop that is not the end of a sentence. Without
# this, an abbreviation inside a legitimate topic reads as prose.
_ABBREVIATION = re.compile(r"\b(?:[A-Za-z]\.){2,}|\b[A-Z][a-z]{0,3}\.")

# The unit counts a Board may choose between. Four and five are the formats real
# regulations print; three is not a syllabus and nobody prints Unit VI.
VALID_UNIT_COUNTS = (4, 5)
DEFAULT_UNIT_COUNT = 5


def resolve_unit_count(raw: int | None) -> int:
    """The unit count to generate to. Anything outside 4-5 reads as the default."""
    return raw if raw in VALID_UNIT_COUNTS else DEFAULT_UNIT_COUNT

# A semester of laboratory work — roughly one experiment per teaching week, allowing
# for the introductory session and the final examination.
_MIN_EXPERIMENTS    = 8
_TARGET_EXPERIMENTS = 10
_MAX_EXPERIMENTS    = 14

# Lines that look like syllabus content but say nothing. A unit built from these is
# an outline wearing a regulation's clothes — and it is the dangerous failure,
# because it reads as finished.
#
# Matched EXACTLY against the normalised title, never as a substring: "Applications"
# on its own is filler, "Applications of Convolutional Networks" is a real topic,
# and a substring test would discard the second along with the first.
_FILLER_CONCEPTS = {
    "introduction", "basics", "fundamentals", "overview", "advanced topics",
    "advanced concepts", "components", "concepts", "conclusion", "summary",
    "miscellaneous", "other topics", "applications", "case studies",
    "introduction to the subject", "getting started", "preliminaries",
    "definitions", "terminology", "background", "history", "recent trends",
    "future directions", "further topics", "additional topics", "review",
    "revision", "general concepts", "key concepts", "core concepts",
}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(ctx: SyllabusGenerationContext) -> tuple[str, str]:
    """Build the prompt for ONE official Board of Studies document.

    WHICH document depends on the course's type, and that is the whole point:

        THEORY         a full syllabus, Unit I-V
        LAB            a lab manual and experiment list — and NO theory units
        INTERNSHIP     guidelines, rubric, weekly activities, viva — and NO syllabus
        MINI_PROJECT   milestones, deliverables, reviews, rubrics
        MAJOR_PROJECT  a handbook: proposal, timeline, demonstration, viva
        SEMINAR        seminar guidelines

    Asking a model for "the syllabus" of an internship gets you five units of
    lectures for a student who is not on campus. The system prompt below is shared —
    the register, the honesty about references, the objectives/outcomes split do not
    change with the type — and everything after it is written per type.
    """
    course_type = normalize_course_type(ctx.course_type)

    builder = {
        TYPE_THEORY:        _build_theory_user_prompt,
        TYPE_LAB:           _build_lab_user_prompt,
        TYPE_INTERNSHIP:    _build_internship_user_prompt,
        TYPE_MINI_PROJECT:  _build_mini_project_user_prompt,
        TYPE_MAJOR_PROJECT: _build_major_project_user_prompt,
        TYPE_SEMINAR:       _build_seminar_user_prompt,
    }[course_type]

    return _system_prompt(course_type, ctx.unit_count), builder(ctx)


# What each type's document IS — the one line that tells the model what it is
# writing, injected into the shared system prompt.
#
# THEORY's brief is a template rather than a string: how many units this syllabus
# has is the Board's decision, not a property of theory courses.
_THEORY_BRIEF = (
    "an OFFICIAL COURSE SYLLABUS — Course Objectives, Course Outcomes, EXACTLY "
    "{n} units (Unit I to Unit {r}), and a bibliography"
)

_DOCUMENT_BRIEF: dict[str, str] = {
    TYPE_THEORY: _THEORY_BRIEF,
    TYPE_LAB: (
        "an OFFICIAL LAB MANUAL — Course Objectives, Lab Outcomes, a numbered "
        "EXPERIMENT LIST, the equipment and software the laboratory requires, and "
        "the guidelines by which the student's laboratory work is assessed.\n"
        "\n"
        "A LABORATORY COURSE HAS NO THEORY UNITS. Do not write Unit I. Do not write "
        "Unit II. There are no units in a lab manual and there never were — there "
        "are experiments, performed at a bench, in the order they are performed"
    ),
    TYPE_INTERNSHIP: (
        "the OFFICIAL INTERNSHIP GUIDELINES.\n"
        "\n"
        "AN INTERNSHIP HAS NO SYLLABUS. The Board of Studies does not write one, "
        "because there is nothing to teach in a classroom: the student is inside a "
        "company. Do NOT write units. Do NOT write a topic list. Do NOT write "
        "lectures.\n"
        "\n"
        "What the Board writes instead is the document that governs the internship: "
        "its guidelines, its duration and credits, its learning outcomes, the rubric "
        "the student is evaluated against, the activities expected week by week, "
        "what the host company must provide, how the report is formatted, and how "
        "the viva is conducted"
    ),
    TYPE_MINI_PROJECT: (
        "the OFFICIAL MINI PROJECT GUIDELINES.\n"
        "\n"
        "A MINI PROJECT HAS NO SYLLABUS. Nothing is lectured. Do NOT write units or "
        "topics.\n"
        "\n"
        "The Board writes the document that governs the project across ONE semester: "
        "its guidelines, its milestones, its deliverables, the review points at "
        "which progress is examined, and the rubrics it is marked against"
    ),
    TYPE_MAJOR_PROJECT: (
        "the OFFICIAL MAJOR PROJECT HANDBOOK.\n"
        "\n"
        "A MAJOR PROJECT HAS NO SYLLABUS. Nothing is lectured. Do NOT write units or "
        "topics.\n"
        "\n"
        "The Board writes the handbook that governs a final-year project end to end: "
        "the handbook's rules, the format of the proposal, the timeline, the review "
        "points, the rubrics, the format of the final report, how the work is "
        "demonstrated, and how the viva voce is conducted. This is a larger and more "
        "formal undertaking than a mini project — it carries a proposal, a "
        "demonstration and a viva, which a mini project does not"
    ),
    TYPE_SEMINAR: (
        "the OFFICIAL SEMINAR GUIDELINES.\n"
        "\n"
        "A SEMINAR HAS NO SYLLABUS. Do NOT write units or topics. The Board writes "
        "how the seminar is run: its guidelines, how a student selects a topic, the "
        "format of the presentation, the rubric it is evaluated against, and what "
        "the student must submit"
    ),
}


def _system_prompt(course_type: str, unit_count: int = DEFAULT_UNIT_COUNT) -> str:
    """The register, the honesty and the prohibitions — shared by every type.

    Only the brief changes: what document the Board member sitting at this desk is
    actually writing, and — for a theory syllabus — in how many units.
    """
    n = resolve_unit_count(unit_count)
    brief = _DOCUMENT_BRIEF[course_type]
    if course_type == TYPE_THEORY:
        brief = brief.format(n=n, r=roman(n))

    return (
        "You are a senior member of a university Board of Studies drafting "
        f"{brief}.\n"
        "\n"
        "This is a formal published document. It will be printed in the "
        "regulations handbook, approved by the Board, and issued to faculty and "
        "students as the definitive statement of what this course requires. Write "
        "it in the register of a university regulation: precise, academic, "
        "impersonal prose.\n"
        "\n"
        "It is NOT lecture notes, NOT a study guide, NOT a tutorial, and NOT a "
        "list of bullet-point tips. Do not address the reader. Do not use "
        "conversational or promotional language.\n"
        "\n"
        "OBJECTIVES vs OUTCOMES — these are different things and a real document "
        "carries both. An OBJECTIVE is written from the course's point of view "
        "('To introduce the mathematical foundations of machine learning'). An "
        "OUTCOME is written from the student's ('Apply supervised learning "
        "algorithms to real-world classification problems'). Never restate one as "
        "the other.\n"
        "\n"
        "NEVER emit generic filler. 'Introduction', 'Basics', 'Overview', 'Advanced "
        "Concepts', 'Applications', 'Conclusion' — a line that could belong to any "
        "course in the university belongs in none of them. Every line you write must "
        "be specific enough that a reader knows exactly what is meant. Do not pad by "
        "repeating yourself either: twelve lines that are really six is the same "
        "hollowness in a longer coat.\n"
        "\n"
        "Adapt depth and emphasis to any university framework named in the "
        "instructions (NEP 2020, VTU, autonomous, NBA/NAAC, industry-integrated, "
        "research-oriented). Absent one, apply broadly accepted academic norms.\n"
        "\n"
        "STRICT PROHIBITIONS — these must NEVER appear anywhere in your response:\n"
        "  - Author names, editor names, or any person's name\n"
        "  - DOI numbers (e.g. 10.xxxx/...)\n"
        "  - ISBN or ISSN numbers\n"
        "  - Publisher names (e.g. MIT Press, Springer, Pearson)\n"
        "  - A publication year attached to a reference\n"
        "  - Any specific bibliographic citation\n"
        "You do not know these facts and must not guess them. A document citing a "
        "book that does not exist is worse than one citing none. Emit only plain "
        "SEARCH QUERIES; real bibliographic metadata is fetched afterwards from "
        "CrossRef and OpenLibrary and attached to the document.\n"
        "\n"
        "Return only valid JSON matching the provided schema — no prose outside "
        "the JSON, no markdown fences."
    )


def _po_lines(ctx: SyllabusGenerationContext) -> str:
    return "\n".join(
        f"  {po.code}: {po.description}" for po in ctx.program_outcomes
    ) or "  (no programme outcomes provided)"


def _course_header(ctx: SyllabusGenerationContext) -> str:
    return (
        f"COURSE INFORMATION (fixed by the approved curriculum — do not contradict it):\n"
        f"  Course Code   : {ctx.course_code}\n"
        f"  Course Name   : {ctx.course_title}\n"
        f"  Credits       : {ctx.course_credits}\n"
        f"  L-T-P         : {ctx.ltp}\n"
        f"  Contact Hours : {ctx.contact_hours}\n"
        f"  Category      : {ctx.category}\n"
        f"  Course Type   : {normalize_course_type(ctx.course_type)}\n"
    )


def _custom_clause(ctx: SyllabusGenerationContext) -> str:
    board = (
        f"\nAdditional instructions from the Board: {ctx.custom_instructions}\n"
        if ctx.custom_instructions else ""
    )
    return board + _retry_clause(ctx)


def _syllabus_clause(ctx: SyllabusGenerationContext) -> str:
    """What this course actually teaches, unit by unit.

    Given to every section drafted AFTER the units — the objectives, the outcomes, the
    reading. Without it they are written about the course's TITLE, which is how a
    syllabus ends up with a Course Outcome nothing in it teaches, and a textbook list
    for a subject it does not cover.
    """
    if not ctx.unit_summary:
        return ""
    units = "\n".join(f"  {line}" for line in ctx.unit_summary)
    return f"\nTHE SYLLABUS THIS COURSE TEACHES:\n{units}\n"


def _retry_clause(ctx: SyllabusGenerationContext) -> str:
    """What the LAST attempt got wrong.

    A retry that says nothing about the failure is a retry that reproduces it: the
    model is not lazy, it simply does not know that the unit it wrote was too thin to
    print. Told exactly which unit and exactly how short, it fixes that unit.
    """
    if not ctx.retry_feedback:
        return ""
    return (
        f"\nYOUR PREVIOUS ATTEMPT WAS REJECTED. Fix these faults — do not repeat "
        f"them:\n{ctx.retry_feedback}\n"
    )


def _outcomes_clause(ctx: SyllabusGenerationContext, *, noun: str = "Course Outcomes") -> str:
    """The CO block. Shared by every type — a lab's Lab Outcomes and an internship's
    Learning Outcomes are Course Outcomes, and they map to POs like any other."""
    return (
        f"- outcomes: 5-6 {noun} (CO1, CO2, ...). Each must:\n"
        f"    * begin with an action verb (Apply, Analyse, Design, Implement, Evaluate)\n"
        f"    * be written from the STUDENT's standpoint — what they can do\n"
        f"    * carry a distinct Bloom's level "
        f"(Remember/Understand/Apply/Analyse/Evaluate/Create)\n"
        f"    * list suggested_po_codes using ONLY codes from the PO list above\n"
        f"    * set po_mapping_strengths[code] to HIGH, MEDIUM or LOW for each of "
        f"them — HIGH when the CO is a primary driver of that PO, MEDIUM for a "
        f"partial contribution, LOW for a tangential one. Judge each pair on its "
        f"merits: a real CO-PO matrix is a mixture, so do NOT default everything "
        f"to MEDIUM.\n"
        f"\n"
        f"Programme Outcomes (POs) available for CO mapping:\n"
        f"{_po_lines(ctx)}\n"
    )


def _objectives_clause() -> str:
    return (
        "- objectives: 4-6 Course Objectives. Each is one sentence written from "
        "the course's standpoint, conventionally opening with 'To ...' — "
        "'To introduce the principles of statistical learning theory.'\n"
    )


def _build_theory_user_prompt(ctx: SyllabusGenerationContext) -> str:
    """The full official syllabus: the units the Board asked for, each of real
    regulation depth."""
    custom_clause = _custom_clause(ctx)

    # How many units this syllabus is taught in — the Board's decision, taken before
    # generation. Not a property of theory courses, and never assumed to be five.
    n = resolve_unit_count(ctx.unit_count)
    last = roman(n)

    # The unit hours. When the Board has stated them they are a given, and the model
    # writes each unit TO its hours — that is what a real syllabus does, because the
    # hours come out of the timetable, not out of the drafting. When it has not, the
    # model paces the units against the contact hours itself: a syllabus whose units
    # total 90 hours for a course taught for 45 is not a document a Board could
    # approve.
    plan = _unit_hours_plan(ctx)
    if plan:
        allocation = "\n".join(
            f"    Unit {roman(i + 1)} — {hours} Hours" for i, hours in enumerate(plan)
        )
        hours_clause = (
            f"- HOURS ARE FIXED BY THE BOARD. Return total_hours EXACTLY as given "
            f"below for each unit, and choose how much material each unit carries so "
            f"that it can genuinely be taught in that time:\n"
            f"{allocation}\n"
            f"  (total {sum(plan)} Hours)\n"
        )
    elif ctx.contact_hours:
        hours_clause = (
            f"- The {n} units together must account for approximately "
            f"{ctx.contact_hours} contact hours (this course is taught for "
            f"{ctx.contact_hours} hours across the semester, from its L-T-P of "
            f"{ctx.ltp}). Distribute them across the units in proportion to each "
            f"unit's weight — they need not be equal, but the total must be close to "
            f"{ctx.contact_hours}.\n"
        )
    else:
        hours_clause = "- Assign each unit a realistic teaching-hour total.\n"

    if ctx.has_practical:
        practical_clause = (
            f"- practical_components: this course carries practical hours (L-T-P "
            f"{ctx.ltp}), so it MUST have them. List 8-12 laboratory exercises or "
            f"practical assignments, each one line, in the order they would be "
            f"performed. Write them as a university syllabus does — "
            f"'Implement a multi-layer perceptron and evaluate it on a benchmark "
            f"dataset', not 'Try building a neural net'.\n"
        )
    else:
        practical_clause = (
            "- practical_components: this is a theory course with no practical "
            "hours. Return an EMPTY list. Do not invent laboratory work for a "
            "course that has no laboratory.\n"
        )

    user = (
        f"Draft the official syllabus for the following course.\n"
        f"\n"
        f"{_course_header(ctx)}"
        f"{custom_clause}"
        f"\n"
        f"REQUIREMENTS\n"
        f"\n"
        f"{_objectives_clause()}"
        f"\n"
        f"{_outcomes_clause(ctx)}"
        f"\n"
        f"- units: EXACTLY {n} units, numbered 1 to {n} — they print as Unit I "
        f"through Unit {last}. The Board has decided this course is taught in {n} "
        f"units, and that is not negotiable: do not return {n - 1}, and do not return "
        f"{n + 1}. Divide the course's FULL scope across them in a sensible teaching "
        f"sequence, foundations first. Between them the {n} units must cover the "
        f"whole subject to the depth a {ctx.course_credits}-credit course demands "
        f"— not a survey of it.\n"
        f"\n"
        f"  Each unit must have:\n"
        f"\n"
        f"    * unit_number (1-{n}) and a concise academic title in the register of a "
        f"regulation ('Introduction to Computer Systems', not 'Getting Started').\n"
        f"\n"
        f"    * topics — THE MOST IMPORTANT FIELD IN THIS RESPONSE.\n"
        f"\n"
        f"      {MIN_TOPICS_PER_UNIT} to {_MAX_TOPICS_PER_UNIT} academic topics — that "
        f"is what a real AICTE / Anna University / VTU unit runs to, and these are the "
        f"lines that will be PRINTED in the university's regulation handbook, without "
        f"being rewritten first.\n"
        f"\n"
        f"      {MIN_TOPICS_PER_UNIT} is the FLOOR, not the target: aim for "
        f"{_TARGET_TOPICS_PER_UNIT}. A unit of 2, 3 or 4 topics is NEVER acceptable — "
        f"that is an outline, and the Board would have to write the rest by hand, "
        f"which is the exact work you are here to do for them. A unit with fewer than "
        f"{MIN_TOPICS_PER_UNIT} topics will be REJECTED and the syllabus regenerated.\n"
        f"\n"
        f"{_TOPIC_STYLE}"
        f"\n"
        f"      For each topic give:\n"
        f"        - title: the syllabus point, exactly as it prints — SHORT\n"
        f"        - description: ONE short sentence, for the lecturer planning the "
        f"lesson. It is NOT printed in the regulation.\n"
        f"        - subtopics: up to 3 sub-concepts (omit if there are none)\n"
        f"        - hours_estimate: teaching hours for this topic\n"
        f"\n"
        f"    * content: the same topic titles rendered as one comma-separated line, "
        f"for regulations that print units as a paragraph rather than as bullets. "
        f"Name the same topics, in the same order, and nothing else.\n"
        f"\n"
        f"    * total_hours: this unit's teaching hours\n"
        f"    * pedagogy: lecture/lab/seminar/case_study/mixed\n"
        f"{hours_clause}"
        f"\n"
        f"{practical_clause}"
        f"\n"
        f"{_bibliography_clause()}"
        f"\n"
        f"Return JSON matching the schema exactly."
    )

    return user


# What a syllabus line LOOKS like — the single most copied part of this prompt, and
# the reason the printed document does or does not resemble a university's.
#
# A real regulation prints noun phrases: 'Doubly Linked List', 'Time and Space
# Complexity'. It does not print sentences, and it does not print explanations. A
# model asked for "topics" without being shown this returns either two words of
# nothing ('Introduction') or a paragraph — and a paragraph in a syllabus is as wrong
# as a stub, because the Board would have to cut it down before printing.
_TOPIC_STYLE = (
    "      THIS is what a unit must look like — a real Anna University syllabus:\n"
    "\n"
    "        UNIT I - LINEAR DATA STRUCTURES                    (10 Hours)\n"
    "          Abstract Data Types (ADT)\n"
    "          Time and Space Complexity\n"
    "          List ADT\n"
    "          Array Implementation of Lists\n"
    "          Linked List\n"
    "          Doubly Linked List\n"
    "          Circular Linked List\n"
    "          Stack ADT\n"
    "          Queue ADT\n"
    "          Circular Queue\n"
    "          Applications of Stack\n"
    "          Applications of Queue\n"
    "\n"
    "      NEVER this — an outline, which is what the Board would have to finish "
    "by hand:\n"
    "\n"
    "        UNIT I\n"
    "          Introduction\n"
    "          Components\n"
    "\n"
    "      And NEVER this — an explanation, which is not what a regulation prints:\n"
    "\n"
    "        UNIT I\n"
    "          A linked list is a linear data structure in which elements are "
    "stored in nodes, and each node points to the next one, which allows "
    "insertion in constant time.\n"
    "\n"
    "      Every `title` is a SYLLABUS POINT: a noun phrase of roughly two to six "
    "words, in the register of a regulation. No sentences. No verbs of instruction "
    "('Learn about ...', 'Understand ...'). No explanations, no definitions, no "
    "colons introducing a gloss. If a line would not fit on one printed line of a "
    "handbook, it is too long.\n"
    "\n"
    "      Every line must also be SPECIFIC — something a lecturer could walk into a "
    "room and teach, and a reader could tell apart from any other course in the "
    "university. NEVER emit generic filler: 'Basics', 'Overview', 'Advanced "
    "Concepts', 'Introduction', 'Applications', 'Case Studies', 'Recent Trends'. "
    "Such a topic will be REJECTED and the unit regenerated. Do not pad by repeating "
    "yourself either: twelve lines that are really six is the same hollowness in a "
    "longer coat.\n"
)


def _unit_hours_plan(ctx: SyllabusGenerationContext) -> list[int]:
    """The Board's hours per unit, if they stated them and the list still fits.

    A plan of four hour-figures against a five-unit syllabus is a plan for a different
    syllabus — the Board changed the unit count after setting the hours — and writing
    to it would silently leave Unit V with no hours at all. Ignored rather than
    patched: the model then paces the units against the contact hours, which is the
    honest fallback.
    """
    plan = [h for h in (ctx.unit_hours_plan or []) if isinstance(h, int) and h > 0]
    return plan if len(plan) == resolve_unit_count(ctx.unit_count) else []


def _bibliography_clause(count: str = "8-12") -> str:
    """Text Books, Reference Books, Suggested Reading, Web Resources — as SEARCH
    QUERIES. The model does not know real bibliographic detail and must not guess
    it; CrossRef and OpenLibrary supply the metadata afterwards."""
    return (
        f"- reference_queries: {count} plain search queries across the four "
        f"bibliography sections. Set ref_type to:\n"
        f"    * TEXTBOOK          the primary Text Books      (3-4 queries)\n"
        f"    * REFERENCE         Reference Books             (3-4 queries)\n"
        f"    * SUGGESTED_READING further reading             (1-2 queries)\n"
        f"    * WEB_RESOURCE      online courses, documentation, standards (1-2)\n"
        f"  A query is search terms ONLY.\n"
        f"    VALID  : 'pattern recognition machine learning graduate textbook'\n"
        f"    INVALID: 'Bishop 2006 Springer ISBN 978-0387310732' — NEVER do this.\n"
    )


# ---------------------------------------------------------------------------
# The non-theory documents
# ---------------------------------------------------------------------------

def _build_lab_user_prompt(ctx: SyllabusGenerationContext) -> str:
    """LAB — a lab manual and an experiment list. No theory units."""
    return (
        f"Draft the official LAB MANUAL for the following laboratory course.\n"
        f"\n"
        f"{_course_header(ctx)}"
        f"{_custom_clause(ctx)}"
        f"\n"
        f"This course is a LABORATORY. It has NO theory units and you must not write "
        f"any. What it has is a list of experiments the student performs at a bench, "
        f"the equipment and software needed to perform them, and the rules by which "
        f"the work is marked.\n"
        f"\n"
        f"REQUIREMENTS\n"
        f"\n"
        f"{_objectives_clause()}"
        f"\n"
        f"{_outcomes_clause(ctx, noun='Lab Outcomes')}"
        f"\n"
        f"- manual_intro: 2-4 sentences introducing the laboratory — what it "
        f"practises, and how it relates to the theory the student has been taught.\n"
        f"\n"
        f"- experiments — THE MOST IMPORTANT FIELD IN THIS RESPONSE.\n"
        f"\n"
        f"  {_TARGET_EXPERIMENTS} to {_MAX_EXPERIMENTS} experiments, numbered from 1, "
        f"in the order they are performed across the semester — roughly one per "
        f"teaching week. Fewer than {_MIN_EXPERIMENTS} is not a laboratory course.\n"
        f"\n"
        f"  THIS is what an experiment must look like:\n"
        f"\n"
        f"    1. Implementation of Stack and Queue using Linked Lists\n"
        f"       aim       : To implement stack and queue abstract data types using\n"
        f"                   singly linked lists and analyse their time complexity.\n"
        f"       procedure : Define the node structure; implement push, pop, enqueue\n"
        f"                   and dequeue; test with boundary conditions (empty,\n"
        f"                   single element, overflow); measure operation cost.\n"
        f"       apparatus : C compiler, Linux workstation\n"
        f"       hours     : 3\n"
        f"\n"
        f"  NEVER this:\n"
        f"\n"
        f"    1. Introduction to the Lab\n"
        f"    2. Basic Programs\n"
        f"\n"
        f"  Every experiment must be a specific procedure a student can actually "
        f"carry out. A reader has to know what they will DO at the bench. Give each "
        f"one a title, an aim, a procedure, the apparatus it needs, and its hours.\n"
        f"\n"
        f"- equipment: the hardware, instruments and bench apparatus the laboratory "
        f"requires. Be specific — 'CRO (30 MHz, dual channel)', not 'lab equipment'.\n"
        f"\n"
        f"- software: the tools, compilers, simulators and licences required. Name "
        f"them. Leave EMPTY only if the laboratory genuinely needs no software.\n"
        f"\n"
        f"  A laboratory that names neither equipment nor software cannot be run, and "
        f"such a manual will be REJECTED.\n"
        f"\n"
        f"- assessment_guidelines: 3-5 lines on how the student's laboratory work is "
        f"marked — the split between continuous evaluation, the record/observation "
        f"book, the internal test and the end-semester practical examination, with "
        f"their weightings. Write them as a regulation does.\n"
        f"\n"
        f"{_bibliography_clause('4-8')}"
        f"  For a laboratory, favour lab manuals, practical handbooks and tool "
        f"documentation over theory monographs.\n"
        f"\n"
        f"Return JSON matching the schema exactly. There is no 'units' field and you "
        f"must not invent one."
    )


def _build_internship_user_prompt(ctx: SyllabusGenerationContext) -> str:
    """INTERNSHIP — guidelines, not a syllabus. The student is inside a company."""
    return (
        f"Draft the official INTERNSHIP GUIDELINES for the following course.\n"
        f"\n"
        f"{_course_header(ctx)}"
        f"{_custom_clause(ctx)}"
        f"\n"
        f"AN INTERNSHIP HAS NO SYLLABUS. There is nothing to lecture: the student is "
        f"inside a company, doing work the university does not control. Do NOT write "
        f"units. Do NOT write topics. What the Board of Studies issues is the "
        f"document that GOVERNS the internship — and that is what you are writing.\n"
        f"\n"
        f"REQUIREMENTS\n"
        f"\n"
        f"{_objectives_clause()}"
        f"\n"
        f"{_outcomes_clause(ctx, noun='Learning Outcomes')}"
        f"\n"
        f"- guidelines: 6-10 lines governing the internship — eligibility, how the "
        f"host organisation is approved, the role of the internal and external "
        f"supervisors, attendance and reporting obligations, conduct and "
        f"confidentiality, and what happens if the internship is abandoned or the "
        f"host withdraws.\n"
        f"\n"
        f"- duration: the internship's length as the regulation states it — e.g. "
        f"'8 weeks (minimum 240 hours), undertaken after the Semester VI examinations'. "
        f"An internship's duration is a POLICY decision, not something derivable from "
        f"an L-T-P, which internships do not have.\n"
        f"\n"
        f"- credits: the credits it carries (use {ctx.course_credits} unless the "
        f"Board's instructions say otherwise).\n"
        f"\n"
        f"- evaluation_rubric: 4-6 rows. Each has a criterion, a weightage (percent, "
        f"and they must total 100), and a descriptor of what earns it. Real rubric "
        f"rows: 'Industry supervisor's assessment' (30), 'Weekly progress reports' "
        f"(15), 'Internship report' (25), 'Presentation and viva voce' (20), "
        f"'Professional conduct and attendance' (10).\n"
        f"\n"
        f"- weekly_activities: 6-10 lines saying what the student is expected to do "
        f"week by week — orientation and induction, familiarisation with tools and "
        f"process, assignment to a live task, independent contribution, documentation "
        f"of the work, exit review and handover. Write what actually happens in an "
        f"internship, not a lecture plan.\n"
        f"\n"
        f"- company_requirements: 4-6 lines on what the HOST ORGANISATION must "
        f"provide for the internship to be recognised — a named supervisor, "
        f"work of a technical standard appropriate to the degree, a workplace and the "
        f"tools to do the job, a certificate on completion, and a confidential "
        f"assessment of the student.\n"
        f"\n"
        f"- report_format: 5-8 lines specifying the internship report — title page, "
        f"certificate from the organisation, declaration, acknowledgement, the "
        f"organisation profile, the work undertaken, the outcomes and learning, "
        f"conclusion, references; plus the physical specification (page count, font, "
        f"spacing, binding).\n"
        f"\n"
        f"- viva_guidelines: 4-6 lines on how the viva voce is conducted — who sits "
        f"on the panel, its duration, what the student presents, what the panel "
        f"examines, and how the mark is arrived at.\n"
        f"\n"
        f"{_bibliography_clause('2-4')}"
        f"  For an internship, favour professional practice, technical writing and "
        f"industry-standard references. Leave EMPTY if none is genuinely useful.\n"
        f"\n"
        f"Return JSON matching the schema exactly. There is no 'units' field and you "
        f"must not invent one."
    )


def _build_mini_project_user_prompt(ctx: SyllabusGenerationContext) -> str:
    """MINI_PROJECT — one semester of supervised project work. No syllabus."""
    return (
        f"Draft the official MINI PROJECT GUIDELINES for the following course.\n"
        f"\n"
        f"{_course_header(ctx)}"
        f"{_custom_clause(ctx)}"
        f"\n"
        f"A MINI PROJECT HAS NO SYLLABUS. Nothing is lectured — the student builds "
        f"something under supervision, across ONE semester. Do NOT write units. Do "
        f"NOT write topics. Write the document that governs the project.\n"
        f"\n"
        f"REQUIREMENTS\n"
        f"\n"
        f"{_objectives_clause()}"
        f"\n"
        f"{_outcomes_clause(ctx)}"
        f"\n"
        f"- guidelines: 6-10 lines governing the mini project — team size, how a "
        f"topic is chosen and approved, the supervisor's role, expectations of "
        f"originality, use of third-party code and libraries, and the plagiarism "
        f"policy.\n"
        f"\n"
        f"- milestones: 5-8 lines, in order, across the semester — problem "
        f"identification and literature survey, requirement specification, design, "
        f"implementation, testing, demonstration, report submission. Say WHEN each "
        f"falls (e.g. 'Week 4: design document approved by the supervisor').\n"
        f"\n"
        f"- deliverables: 4-6 lines naming exactly what the student hands in — the "
        f"working artefact, the source code with version history, the project report, "
        f"the demonstration, and any dataset or model produced.\n"
        f"\n"
        f"- reviews: 2-4 review points. Say what is examined at each and what the "
        f"student must present — 'Review I (Week 5): problem statement, literature "
        f"survey and proposed design, presented to the review panel.'\n"
        f"\n"
        f"- rubrics: 4-6 rows. Each has a criterion, a weightage (percent, totalling "
        f"100) and a descriptor. Real rows: 'Problem formulation and literature "
        f"survey' (15), 'Design and technical depth' (25), 'Implementation and "
        f"testing' (25), 'Demonstration' (15), 'Report' (10), 'Viva' (10).\n"
        f"\n"
        f"{_bibliography_clause('2-4')}"
        f"  Favour project methodology, technical writing and domain references. "
        f"Leave EMPTY if none is genuinely useful.\n"
        f"\n"
        f"Return JSON matching the schema exactly. There is no 'units' field and you "
        f"must not invent one."
    )


def _build_major_project_user_prompt(ctx: SyllabusGenerationContext) -> str:
    """MAJOR_PROJECT — the final-year project handbook. No syllabus."""
    return (
        f"Draft the official MAJOR PROJECT HANDBOOK for the following course.\n"
        f"\n"
        f"{_course_header(ctx)}"
        f"{_custom_clause(ctx)}"
        f"\n"
        f"A MAJOR PROJECT HAS NO SYLLABUS. Nothing is lectured. Do NOT write units. "
        f"Do NOT write topics.\n"
        f"\n"
        f"This is the capstone of the degree, and its handbook is correspondingly "
        f"formal: it carries a PROPOSAL, a DEMONSTRATION and a VIVA VOCE, which a "
        f"mini project does not.\n"
        f"\n"
        f"REQUIREMENTS\n"
        f"\n"
        f"{_objectives_clause()}"
        f"\n"
        f"{_outcomes_clause(ctx)}"
        f"\n"
        f"- handbook: 6-10 lines of the handbook's governing rules — team size, how a "
        f"topic is selected and approved, the supervisor's and co-supervisor's roles, "
        f"expectations of originality and novelty, the plagiarism and AI-assistance "
        f"policy, intellectual property, publication expectations, and the "
        f"consequences of failing a review.\n"
        f"\n"
        f"- proposal_format: 4-8 lines specifying the project proposal (synopsis) — "
        f"title, problem statement, literature survey, objectives, proposed "
        f"methodology, expected outcomes, hardware and software requirements, and the "
        f"timeline; plus its length and how it is approved.\n"
        f"\n"
        f"- timeline: 5-8 lines mapping the project across the semester(s) — proposal "
        f"submission and approval, literature survey, design freeze, implementation "
        f"phases, testing and validation, draft report, final demonstration, viva. "
        f"Give the week or month of each.\n"
        f"\n"
        f"- reviews: 3-5 review points. Say what is examined at each, what the student "
        f"presents, and what fraction of the mark it carries — 'Review II "
        f"(Week 10): detailed design and a working prototype of the core module, "
        f"before the departmental review committee.'\n"
        f"\n"
        f"- rubrics: 5-7 rows. Each has a criterion, a weightage (percent, totalling "
        f"100) and a descriptor. Real rows: 'Problem formulation and literature "
        f"survey', 'Novelty and technical depth', 'Design and methodology', "
        f"'Implementation and results', 'Demonstration', 'Report and documentation', "
        f"'Viva voce'.\n"
        f"\n"
        f"- final_report_format: 6-10 lines specifying the report — title page, "
        f"bonafide certificate, declaration, abstract, acknowledgement, table of "
        f"contents, the chapter structure (introduction, literature survey, system "
        f"design, implementation, results and discussion, conclusion and future "
        f"work), references in a named citation style, appendices; plus the physical "
        f"specification (page count, font, spacing, margins, binding, number of "
        f"copies).\n"
        f"\n"
        f"- demonstration: 3-5 lines on how the working project is demonstrated — "
        f"what must run, before whom, under what conditions, and what happens if it "
        f"fails to run on the day.\n"
        f"\n"
        f"- viva: 4-6 lines on the viva voce — the panel (internal and external "
        f"examiners), its duration, what the student presents, the depth to which the "
        f"panel may examine the work, and how the mark is arrived at.\n"
        f"\n"
        f"{_bibliography_clause('2-4')}"
        f"  Favour research methodology, technical writing and domain references. "
        f"Leave EMPTY if none is genuinely useful.\n"
        f"\n"
        f"Return JSON matching the schema exactly. There is no 'units' field and you "
        f"must not invent one."
    )


def _build_seminar_user_prompt(ctx: SyllabusGenerationContext) -> str:
    """SEMINAR — guidelines in place of a syllabus."""
    return (
        f"Draft the official SEMINAR GUIDELINES for the following course.\n"
        f"\n"
        f"{_course_header(ctx)}"
        f"{_custom_clause(ctx)}"
        f"\n"
        f"A SEMINAR HAS NO SYLLABUS. The student researches a topic and presents it; "
        f"nothing is lectured to them. Do NOT write units. Do NOT write topics — the "
        f"student chooses the topic, and prescribing it would defeat the exercise.\n"
        f"\n"
        f"REQUIREMENTS\n"
        f"\n"
        f"{_objectives_clause()}"
        f"\n"
        f"{_outcomes_clause(ctx)}"
        f"\n"
        f"- guidelines: 5-8 lines governing the seminar — the supervisor's role, "
        f"attendance requirements, the schedule of presentations, expectations of "
        f"independent study, and the plagiarism policy.\n"
        f"\n"
        f"- topic_selection: 3-6 lines on how a student selects and gets approval for "
        f"a topic — its currency and relevance to the programme, the requirement that "
        f"it rest on recent peer-reviewed literature, that it not duplicate another "
        f"student's, and the approval deadline.\n"
        f"\n"
        f"- presentation_format: 3-6 lines on the presentation itself — its duration, "
        f"the question-and-answer period, the expected slide structure, and the "
        f"audience before whom it is delivered.\n"
        f"\n"
        f"- evaluation_rubric: 4-6 rows. Each has a criterion, a weightage (percent, "
        f"totalling 100) and a descriptor. Real rows: 'Depth of literature studied' "
        f"(25), 'Technical content and clarity' (25), 'Presentation and delivery' "
        f"(20), 'Handling of questions' (15), 'Written report' (15).\n"
        f"\n"
        f"- deliverables: 2-4 lines naming what the student submits — the slide deck, "
        f"the seminar report, and the list of papers surveyed.\n"
        f"\n"
        f"{_bibliography_clause('2-4')}"
        f"  Favour technical writing, presentation skills and recent survey "
        f"literature. Leave EMPTY if none is genuinely useful.\n"
        f"\n"
        f"Return JSON matching the schema exactly. There is no 'units' field and you "
        f"must not invent one."
    )


def _build_section_prompt(
    ctx: SyllabusGenerationContext,
    section: str,
    *,
    unit_number: int | None = None,
    unit_title: str | None = None,
    unit_scope: str | None = None,
    sibling_units: list[str] | None = None,
    guidance: str | None = None,
) -> tuple[str, str]:
    """Prompt for ONE section of an existing syllabus.

    The system prompt is the same as for a full generation — the register, the
    format and the prohibitions do not change just because we are rewriting a part.

    What changes is context: a regenerated unit is told what the OTHER units cover,
    so it fills its own place in the syllabus instead of drifting into theirs. A
    unit rewritten in isolation is how you end up with two units both teaching cache
    memory.
    """
    course_type = normalize_course_type(ctx.course_type)
    system = _system_prompt(course_type, ctx.unit_count)

    header = _course_header(ctx) + _syllabus_clause(ctx)
    extra = f"\nAdditional instructions from the Board: {guidance}\n" if guidance else ""

    if section == SECTION_OUTLINE:
        # The plan, written before a single unit is. It is what keeps a syllabus
        # drafted unit by unit from becoming N essays on the same subject: the course
        # is divided ONCE, as a whole, and each unit is then written to its own share
        # of it knowing what the others hold.
        n = resolve_unit_count(ctx.unit_count)
        plan = _unit_hours_plan(ctx)
        hours_lines = (
            "\n".join(
                f"    Unit {roman(i + 1)} — {hours} Hours"
                for i, hours in enumerate(plan)
            )
            if plan else "    (the Board has not fixed the hours)"
        )

        user = (
            f"Divide a course into the {n} units it will be taught in. This is the "
            f"PLAN, not the syllabus — no topics yet.\n\n"
            f"{header}"
            f"{_custom_clause(ctx)}\n"
            f"The Board teaches this course in {n} units, with these hours:\n"
            f"{hours_lines}\n\n"
            f"Return EXACTLY {n} units, numbered 1 to {n}, in TEACHING ORDER — "
            f"foundations first, and each unit resting on the ones before it. Between "
            f"them they must cover the WHOLE subject to the depth a "
            f"{ctx.course_credits}-credit course demands, with no overlap between any "
            f"two and no gap left between them.\n\n"
            f"For each unit give:\n"
            f"  - unit_number\n"
            f"  - title: the unit's academic title as it prints in the regulation "
            f"('Linear Data Structures', 'Memory and I/O Organization'). Never "
            f"'Introduction', never 'Advanced Topics', never 'Unit 3'.\n"
            f"  - scope: ONE sentence naming the ground this unit covers, so that the "
            f"unit written from it does not stray into another's. Be concrete — name "
            f"the actual concepts, not 'the fundamentals of the subject'.\n"
            f"  - level: foundational | intermediate | advanced.\n\n"
            f"A COURSE IS A PROGRESSION, not {n} essays on the same subject. Unit I "
            f"rests on nothing and is foundational; each unit after it rests on the "
            f"ones before and reaches further; the last is advanced. A student who has "
            f"finished Unit III must be READY for Unit IV — and must not be taught in "
            f"Unit IV what they were already taught in Unit II. No two units may share "
            f"ground.\n\n"
            f"Weight the units by their hours: a unit taught for 12 hours carries more "
            f"of the subject than one taught for 8.\n"
            f"{_retry_clause(ctx)}\n"
            f"Return JSON: {{\"units\": [ ... ]}}"
        )

    elif section == SECTION_UNIT:
        siblings = "\n".join(f"  - {t}" for t in (sibling_units or [])) or "  (none)"

        # The Board's hour allocation is not the model's to re-decide. The units
        # together total the course's taught hours, and a unit that came back from a
        # rewrite with 15 hours instead of the 10 the Board gave it would silently
        # break that total — so the hours are stated as a constraint and the topics
        # are paced to fit them.
        hours_clause = (
            f"This unit is taught for {ctx.unit_hours} hours, which the Board has "
            f"already decided. Return total_hours = {ctx.unit_hours} and pitch the "
            f"depth of the topics at what can genuinely be taught in that time.\n\n"
            if ctx.unit_hours
            else ""
        )

        # The unit's brief, when it is being written for the first time: its share of
        # the course, decided by the outline. On a REWRITE there is no scope — the
        # unit already exists, and its place in the syllabus is its title.
        scope_clause = (
            f"This unit covers: {unit_scope}\n\n" if unit_scope else ""
        )

        # Where the unit sits on the course's arc. Without it, a unit drafted on its
        # own reaches for the basics whatever number it carries — which is how Unit IV
        # comes back teaching what Unit I already taught.
        level_clause = (
            f"This is a {ctx.unit_level.upper()} unit. "
            + {
                "foundational": "It rests on nothing before it: begin the subject here.",
                "intermediate": "It rests on the units before it. Do not re-teach their "
                                "material — build on it.",
                "advanced":     "It is near the end of the course. Assume everything the "
                                "earlier units taught, and go further than they did.",
            }.get(ctx.unit_level, "")
            + "\n\n"
            if ctx.unit_level else ""
        )

        # What the syllabus ALREADY teaches. The single most important line in this
        # prompt for a unit-at-a-time syllabus: each unit is a fresh request, and a
        # model asked about data structures will teach the linked list in Unit I, again
        # in Unit II, and once more in Unit IV. It is also CHECKED — a unit that
        # repeats any of these is rejected and redrafted.
        taught_clause = ""
        if ctx.used_topics:
            already = "\n".join(f"  - {t}" for t in ctx.used_topics[:60])
            taught_clause = (
                f"ALREADY TAUGHT by the other units of this syllabus. Do NOT teach any "
                f"of it again — a topic taught twice is a topic missing somewhere "
                f"else, and a unit that repeats one will be REJECTED:\n{already}\n\n"
            )

        verb = "Write" if unit_scope else "Rewrite"
        user = (
            f"{verb} ONE unit of an official university syllabus.\n\n{header}\n"
            f"The other units of this syllabus cover:\n{siblings}\n\n"
            f"{verb.upper()} UNIT {unit_number}"
            + (f' — "{unit_title}"' if unit_title else "")
            + ".\n\n"
            f"{scope_clause}"
            f"{level_clause}"
            f"{hours_clause}"
            f"{taught_clause}"
            f"Stay in this unit's lane: do NOT stray into material the other units "
            f"above already teach, and do not leave a gap between them. This unit must "
            f"sit in its own place in the teaching sequence.\n"
            f"{extra}"
            f"{_retry_clause(ctx)}\n"
            f"It must have {MIN_TOPICS_PER_UNIT}-{_MAX_TOPICS_PER_UNIT} specific, "
            f"teachable academic topics — the standard of an AICTE / Anna University / "
            f"VTU regulation, and the lines that will be PRINTED in the handbook. Aim "
            f"for {_TARGET_TOPICS_PER_UNIT}; fewer than {MIN_TOPICS_PER_UNIT} is an "
            f"outline and will be rejected.\n\n"
            f"{_TOPIC_STYLE}\n"
            f"Return JSON: {{\"unit\": {{ ...the unit... }}}}"
        )

    elif section == SECTION_OBJECTIVES:
        user = (
            f"Write the COURSE OBJECTIVES of an official university syllabus.\n\n{header}"
            f"{extra}"
            f"{_retry_clause(ctx)}\n"
            f"4-6 objectives. Each is one sentence written from the COURSE's "
            f"standpoint, conventionally opening with 'To ...' — 'To introduce the "
            f"principles of statistical learning theory.' They say what the course "
            f"sets out to impart, NOT what the student can do afterwards (that is a "
            f"Course Outcome, and is a different section).\n\n"
            f"Write them TO the units above. An objective promising material that no "
            f"unit of this syllabus teaches is a promise the course cannot keep.\n\n"
            f"Return JSON: {{\"objectives\": [\"...\"]}}"
        )

    elif section == SECTION_OUTCOMES:
        po_lines = "\n".join(
            f"  {po.code}: {po.description}" for po in ctx.program_outcomes
        ) or "  (no programme outcomes provided)"
        user = (
            f"Write the COURSE OUTCOMES of an official university syllabus.\n\n{header}\n"
            f"Programme Outcomes available for CO mapping:\n{po_lines}\n"
            f"{extra}"
            f"{_retry_clause(ctx)}\n"
            f"5-6 outcomes (CO1, CO2, ...). Each must begin with an action verb, be "
            f"written from the STUDENT's standpoint (what they can DO on completing "
            f"the course), carry a distinct Bloom's level, list suggested_po_codes "
            f"using only the codes above, and set po_mapping_strengths[code] to HIGH, "
            f"MEDIUM or LOW on the merits of each pair — a real CO-PO matrix is a "
            f"mixture, so do not default everything to MEDIUM.\n\n"
            f"Write them TO the units above: between them the outcomes must account "
            f"for what this syllabus actually teaches. An outcome about material no "
            f"unit covers is one the examination cannot test.\n\n"
            f"Return JSON: {{\"outcomes\": [ ... ]}}"
        )

    elif section == SECTION_REFERENCES:
        user = (
            f"Rewrite the REFERENCE BOOKS, SUGGESTED READING and WEB RESOURCES of an "
            f"existing official document.\n\n{header}"
            f"{extra}\n"
            f"5-8 plain search queries. Set ref_type to REFERENCE (3-4), "
            f"SUGGESTED_READING (1-2) or WEB_RESOURCE (1-2).\n\n"
            f"Do NOT return TEXTBOOK queries. The Text Books are a separate section "
            f"of the printed document and are not being rewritten — leaving them "
            f"alone is the whole reason this is its own request.\n\n"
            f"A query is SEARCH TERMS ONLY. You do not know real bibliographic "
            f"detail and must not guess it — no author names, no ISBNs, no DOIs, no "
            f"publishers, no years. Real metadata is fetched afterwards from CrossRef "
            f"and OpenLibrary using these queries.\n"
            f"  VALID  : 'pattern recognition machine learning graduate textbook'\n"
            f"  INVALID: 'Bishop 2006 Springer ISBN 978-0387310732'\n\n"
            f"Return JSON: {{\"reference_queries\": [ ... ]}}"
        )

    elif section == SECTION_BOOKS:
        user = (
            f"Rewrite the TEXT BOOKS of an existing official document.\n\n{header}"
            f"{extra}\n"
            f"3-5 plain search queries for the PRIMARY TEXT BOOKS of this course — "
            f"the ones a student is expected to own or borrow for the semester, not "
            f"the wider reading. Set ref_type to TEXTBOOK on every one of them.\n\n"
            f"Do NOT return REFERENCE, SUGGESTED_READING or WEB_RESOURCE queries. "
            f"Those are separate sections of the printed document and are not being "
            f"rewritten.\n\n"
            f"A query is SEARCH TERMS ONLY. You do not know real bibliographic detail "
            f"and must not guess it — no author names, no ISBNs, no DOIs, no "
            f"publishers, no years.\n"
            f"  VALID  : 'operating system concepts undergraduate textbook'\n"
            f"  INVALID: 'Silberschatz Galvin 10th edition Wiley'\n\n"
            f"Return JSON: {{\"reference_queries\": [ ... ]}}"
        )

    elif section == SECTION_PRACTICALS:
        user = (
            f"Rewrite the PRACTICAL COMPONENTS of an existing official syllabus.\n\n"
            f"{header}"
            f"{extra}\n"
            f"8-12 laboratory exercises or practical assignments, each one line, in "
            f"the order they would be performed across the semester.\n\n"
            f"Write them as a university syllabus does — 'Implement a multi-layer "
            f"perceptron and evaluate it on a benchmark dataset', not 'Try building a "
            f"neural net'. Every line must be a specific exercise a student can "
            f"actually carry out; a reader has to know what they will DO.\n\n"
            f"Return JSON: {{\"practical_components\": [\"...\"]}}"
        )

    elif section == SECTION_DOCUMENT:
        # The non-theory equivalent of regenerating the units: rewrite the whole
        # type-specific body. The type's full-generation prompt already says exactly
        # what that body is, so it is reused rather than restated — a second,
        # drifting copy of "what a lab manual contains" is how the regenerated
        # document ends up subtly different from the generated one.
        builder = {
            TYPE_THEORY:        _build_theory_user_prompt,
            TYPE_LAB:           _build_lab_user_prompt,
            TYPE_INTERNSHIP:    _build_internship_user_prompt,
            TYPE_MINI_PROJECT:  _build_mini_project_user_prompt,
            TYPE_MAJOR_PROJECT: _build_major_project_user_prompt,
            TYPE_SEMINAR:       _build_seminar_user_prompt,
        }[course_type]
        user = builder(ctx) + (
            f"\n\nThis is a REGENERATION of an existing document. The Board has asked "
            f"for it to be rewritten.{extra}"
        )

    else:
        raise ValueError(f"Unknown section {section!r}")

    return system, user


def _validate_section(parsed, section: str, ctx: SyllabusGenerationContext) -> list[str]:
    """A regenerated section is held to exactly the same bar as a full generation.

    Otherwise "regenerate this one unit" becomes the back door through which a thin
    unit — or a hollow lab manual — reaches the approved document.
    """
    if section == SECTION_OUTLINE:
        return _validate_outline(parsed, ctx)

    if section == SECTION_UNIT:
        # Held to the same bar as a full generation, and to one more: it must not teach
        # what the units around it already teach. `used_topics` carries them — the ones
        # written before it during a fresh generation, or the ones in the other units
        # of the syllabus when the Board asks for a single unit to be redrafted.
        return _validate_units([parsed.unit], ctx.used_topics)

    if section in (SECTION_REFERENCES, SECTION_BOOKS):
        return _validate_reference_queries(parsed.reference_queries)

    if section == SECTION_OUTCOMES:
        valid = {po.code for po in ctx.program_outcomes}
        for co in parsed.outcomes:
            unknown = [c for c in co.suggested_po_codes if c not in valid]
            if unknown:
                logger.warning(
                    "regenerated CO '%s' suggested unknown PO code(s) %s; they will be dropped.",
                    co.code, unknown,
                )
        return []

    if section == SECTION_DOCUMENT:
        # The whole document, so the whole document's validation.
        return _validate_result(parsed, ctx)

    return []


def _is_soft_violation(violation: str) -> bool:
    """Return True for violations that should warn but not abort generation.

    Count shortfalls (fewer COs or units than ideal) are soft — different university
    styles legitimately produce fewer items, and a warning is preferable to a failure.
    """
    return "minimum required is" in violation.lower()


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()


def _full_result(
    raw: Any,
    ctx: SyllabusGenerationContext,
    *,
    provider_name: str,
    model_used: str,
    prompt_hash: str,
    normalize: bool = False,
) -> SyllabusGenerationResult:
    """Parse, validate and map ONE full generation — for any course type.

    Shared by all three providers. They differ only in HOW they call a model (client,
    model name, whether the response needs alias-normalising); everything after the
    bytes come back is identical, and duplicating it three times is how the LAB path
    ends up validated in Gemini and unvalidated in Groq.

    `raw` is the model's JSON string, or an already-normalised dict from a caller
    that ran `_normalize_groq_response` itself.
    """
    course_type = normalize_course_type(ctx.course_type)
    schema      = _TYPE_SCHEMAS[course_type]

    data: Any = _normalize_groq_response(raw) if normalize else raw

    try:
        parsed = (
            schema.model_validate(data)
            if not isinstance(data, str)
            else schema.model_validate_json(data)
        )
    except Exception as exc:
        raise SyllabusAIParseError(
            f"{provider_name} response for a {course_type} course did not match the "
            f"expected schema: {exc}\nRaw response (first 500 chars): {str(raw)[:500]}"
        ) from exc

    violations = _validate_result(parsed, ctx)
    if violations:
        hard = [v for v in violations if not _is_soft_violation(v)]
        soft = [v for v in violations if _is_soft_violation(v)]
        if soft:
            logger.warning("m02.%s: soft violations — proceeding: %s", provider_name, soft)
        if hard:
            raise SyllabusAIValidationError(
                f"{provider_name} AI response failed business-rule validation:\n"
                + "\n".join(f"  - {v}" for v in hard)
            )

    is_theory = course_type == TYPE_THEORY

    return SyllabusGenerationResult(
        doc_type=course_type,
        document=_document_from(parsed, course_type),
        objectives=list(parsed.objectives),
        outcomes=[
            {
                "code":                 co.code,
                "description":          co.description,
                "bloom_level":          co.bloom_level,
                "suggested_po_codes":   co.suggested_po_codes,
                "po_mapping_strengths": co.po_mapping_strengths,
            }
            for co in parsed.outcomes
        ],
        # Units and the theory-only prose sections exist on _SyllabusAI alone. A lab
        # manual has experiments, not units, and asking it for its units would be
        # asking the wrong question of the right document.
        units=[
            {
                "unit_number": u.unit_number,
                "title":       u.title,
                "content":     u.content,
                "topics":      [t.model_dump(exclude_none=True) for t in u.topics],
                "total_hours": u.total_hours,
                "pedagogy":    u.pedagogy,
            }
            for u in parsed.units
        ] if is_theory else [],
        practical_components=(
            list(parsed.practical_components)
            if is_theory and ctx.has_practical else []
        ),
        internal_assessment=list(parsed.internal_assessment) if is_theory else [],
        reference_queries=[
            {"query_str": rq.query_str, "ref_type": rq.ref_type}
            for rq in parsed.reference_queries
        ],
        model_used=model_used,
        provider_name=provider_name,
        prompt_hash=prompt_hash,
    )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Section regeneration — shared across all three providers
#
# The providers differ only in HOW they call a model (client, model name, whether
# the response needs alias-normalising). Everything after that — parse against the
# section schema, validate to the same depth bar as a full generation, map to a
# result — is identical, so it lives here once rather than three times.
# ---------------------------------------------------------------------------

def _section_result(
    raw: str,
    section: str,
    ctx: SyllabusGenerationContext,
    *,
    provider_name: str,
    model_used: str,
    prompt_hash: str,
    normalize: bool = False,
) -> SectionGenerationResult:
    schema = section_schema_for(section, ctx)

    data: Any = raw
    if normalize:
        # Groq and DeepSeek reach for aliases and for lists-of-strings where the
        # schema wants objects. Reuse the same normaliser the full generation path
        # relies on, wrapping single-section payloads so it can find the keys it
        # knows.
        data = _normalize_section_response(raw, section)

    try:
        parsed = (
            schema.model_validate(data)
            if not isinstance(data, str)
            else schema.model_validate_json(data)
        )
    except Exception as exc:
        raise SyllabusAIParseError(
            f"{provider_name} response for section {section} did not match the "
            f"expected schema: {exc}\nRaw (first 400 chars): {str(raw)[:400]}"
        ) from exc

    violations = _validate_section(parsed, section, ctx)
    if violations:
        # No soft/hard split here. A regenerated section is the Board asking for
        # this piece to be BETTER — handing back one that fails the depth bar would
        # be worse than useless, because it looks like the request was honoured.
        raise SyllabusAIValidationError(
            f"{provider_name} regeneration of {section} failed validation:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    result = SectionGenerationResult(
        section=section,
        provider_name=provider_name,
        model_used=model_used,
        prompt_hash=prompt_hash,
    )
    if section == SECTION_OUTLINE:
        result.outline = [
            {"unit_number": u.unit_number, "title": u.title, "scope": u.scope}
            for u in sorted(parsed.units, key=lambda u: u.unit_number)
        ]
    elif section == SECTION_UNIT:
        u = parsed.unit
        result.unit = {
            "unit_number": u.unit_number,
            "title":       u.title,
            "content":     u.content,
            "topics":      [t.model_dump(exclude_none=True) for t in u.topics],
            "total_hours": u.total_hours,
            "pedagogy":    u.pedagogy,
        }
    elif section == SECTION_OBJECTIVES:
        result.objectives = list(parsed.objectives)
    elif section == SECTION_OUTCOMES:
        result.outcomes = [
            {
                "code":                 co.code,
                "description":          co.description,
                "bloom_level":          co.bloom_level,
                "suggested_po_codes":   co.suggested_po_codes,
                "po_mapping_strengths": co.po_mapping_strengths,
            }
            for co in parsed.outcomes
        ]
    elif section in (SECTION_REFERENCES, SECTION_BOOKS):
        result.reference_queries = [
            {"query_str": rq.query_str, "ref_type": rq.ref_type}
            for rq in parsed.reference_queries
        ]
    elif section == SECTION_PRACTICALS:
        result.practical_components = list(parsed.practical_components)
    elif section == SECTION_DOCUMENT:
        course_type = normalize_course_type(ctx.course_type)
        result.document   = _document_from(parsed, course_type)
        result.objectives = list(parsed.objectives)
        result.outcomes   = [
            {
                "code":                 co.code,
                "description":          co.description,
                "bloom_level":          co.bloom_level,
                "suggested_po_codes":   co.suggested_po_codes,
                "po_mapping_strengths": co.po_mapping_strengths,
            }
            for co in parsed.outcomes
        ]
        # THEORY's "document" IS its units, so a DOCUMENT regeneration of a theory
        # syllabus rewrites those. Every other type returns units = None and the
        # service leaves the (empty) unit list alone.
        if course_type == TYPE_THEORY:
            result.units = [
                {
                    "unit_number": u.unit_number,
                    "title":       u.title,
                    "content":     u.content,
                    "topics":      [t.model_dump(exclude_none=True) for t in u.topics],
                    "total_hours": u.total_hours,
                    "pedagogy":    u.pedagogy,
                }
                for u in parsed.units
            ]
    return result


def _normalize_section_response(raw: str, section: str) -> dict:
    """Reshape a single-section payload into what its schema expects.

    A model asked for one unit may return it bare (the unit object itself) rather
    than wrapped in {"unit": ...}; asked for objectives it may return a bare list.
    Both are the right answer in the wrong envelope, and rejecting them would waste
    an AI call over punctuation.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SyllabusAIParseError(
            f"Section response is not valid JSON: {exc}\nRaw: {raw[:300]}"
        ) from exc

    if section == SECTION_OUTLINE:
        # The outline is plain — unit_number, title, scope — so it needs none of the
        # unit normaliser's topic-shaping. Only the envelope may be wrong.
        if isinstance(data, list):
            return {"units": data}
        if isinstance(data, dict) and isinstance(data.get("outline"), list):
            return {"units": data["outline"]}
        return data if isinstance(data, dict) else {"units": []}

    if section == SECTION_UNIT:
        unit = data.get("unit") if isinstance(data, dict) else None
        if unit is None and isinstance(data, dict) and "topics" in data:
            unit = data                     # returned bare
        if unit is None and isinstance(data, dict) and isinstance(data.get("units"), list):
            unit = data["units"][0]         # returned as a one-element list
        # Reuse the full-response normaliser's unit handling by faking a whole doc.
        faked = _normalize_groq_response(json.dumps({"units": [unit or {}]}))
        return {"unit": faked["units"][0]}

    if section == SECTION_DOCUMENT:
        # A whole document, so the whole-response normaliser — and nothing is
        # stripped out afterwards, because every key of it is wanted.
        return _normalize_groq_response(raw)

    if isinstance(data, list):              # a bare list where a wrapper was asked for
        key = {
            SECTION_OBJECTIVES: "objectives",
            SECTION_OUTCOMES:   "outcomes",
            SECTION_REFERENCES: "reference_queries",
            SECTION_BOOKS:      "reference_queries",
            SECTION_PRACTICALS: "practical_components",
        }[section]
        data = {key: data}

    faked = _normalize_groq_response(json.dumps(data))
    if section == SECTION_OBJECTIVES:
        return {"objectives": faked.get("objectives", [])}
    if section == SECTION_OUTCOMES:
        return {"outcomes": faked.get("outcomes", [])}
    if section == SECTION_PRACTICALS:
        return {"practical_components": faked.get("practical_components", [])}
    return {"reference_queries": faked.get("reference_queries", [])}


@runtime_checkable
class SyllabusProvider(Protocol):
    async def generate_syllabus(
        self,
        ctx: SyllabusGenerationContext,
    ) -> SyllabusGenerationResult: ...

    async def generate_section(
        self,
        ctx: SyllabusGenerationContext,
        section: str,
        **kwargs,
    ) -> SectionGenerationResult: ...


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------

class GeminiSyllabusProvider:

    async def generate_syllabus(
        self,
        ctx: SyllabusGenerationContext,
    ) -> SyllabusGenerationResult:
        # Deferred import — module loads cleanly in tests that mock this provider.
        from google import genai
        from google.genai import types

        system, user = _build_prompt(ctx)
        phash = _prompt_hash(system, user)

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            # The course's TYPE picks the schema: a lab gets asked for experiments,
            # an internship for a rubric, and only a theory course for units.
            response_schema=response_schema_for(ctx).model_json_schema(),
            temperature=0.35,     # lower than M01 — syllabus needs precision
            system_instruction=system,
        )

        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=user,
            config=config,
        )

        raw = getattr(response, "text", None)
        if not raw:
            raise SyllabusAIBlockedError(
                "Gemini returned an empty or blocked response — "
                "check safety filters and API quota."
            )

        return _full_result(
            raw, ctx,
            provider_name="gemini",
            model_used=settings.GEMINI_MODEL,
            prompt_hash=phash,
        )


    async def generate_section(
        self,
        ctx: SyllabusGenerationContext,
        section: str,
        **kwargs,
    ) -> SectionGenerationResult:
        from google import genai
        from google.genai import types

        system, user = _build_section_prompt(ctx, section, **kwargs)
        phash = _prompt_hash(system, user)

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=section_schema_for(section, ctx).model_json_schema(),
            temperature=0.35,
            system_instruction=system,
        )
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL, contents=user, config=config,
        )
        raw = getattr(response, "text", None)
        if not raw:
            raise SyllabusAIBlockedError(
                "Gemini returned an empty or blocked response for a section regeneration."
            )
        return _section_result(
            raw, section, ctx,
            provider_name="gemini", model_used=settings.GEMINI_MODEL, prompt_hash=phash,
        )


# ---------------------------------------------------------------------------
# Groq response normalizer
# ---------------------------------------------------------------------------

def _normalize_groq_response(raw: str) -> dict[str, Any]:
    """
    Map observed Groq output aliases to the canonical _SyllabusAI field names.

    Called ONLY for Groq responses; the Gemini path is untouched.
    Raises SyllabusAIParseError if the raw string is not valid JSON.

    Aliases handled
    ---------------
    Top-level:
      course_outcomes  -> outcomes

    Per CO:
      bloom            -> bloom_level  (Groq sometimes omits the _level suffix)
      co_statement     -> description  (primary observed alias)
      co_description   -> description  (fallback alias)
      statement        -> description  (fallback alias)
      co               -> description  (fallback alias; also used when description is empty string)
      (empty/missing description) -> synthesized from code + bloom_level as last resort
      (missing code)   -> CO1, CO2, …  (stable sequential codes)
      (missing suggested_po_codes) -> []

    Per unit:
      display_order    -> unit_number  (when unit_number absent)
      (missing unit_number) -> sequential 1-based index
      topics[i]: str   -> {"title": str}   (string topics -> topic objects)

    Per reference query:
      query            -> query_str
    """
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SyllabusAIParseError(
            f"Groq response is not valid JSON: {exc}\n"
            f"Raw (first 300 chars): {raw[:300]}"
        ) from exc

    if not isinstance(data, dict):
        raise SyllabusAIParseError(
            f"Groq response is not a JSON object (got {type(data).__name__})."
        )

    # --- top-level key aliases ---
    if "course_outcomes" in data and "outcomes" not in data:
        data["outcomes"] = data.pop("course_outcomes")

    # objectives: Groq/DeepSeek often name it after the printed heading
    for _obj_alias in ("course_objectives", "objectives_list", "aims"):
        if _obj_alias in data and "objectives" not in data:
            data["objectives"] = data.pop(_obj_alias)
            break

    # practical components: several plausible headings
    for _prac_alias in (
        "practicals", "practical_component", "lab_components",
        "laboratory_components", "practical_exercises", "lab_exercises",
    ):
        if _prac_alias in data and "practical_components" not in data:
            data["practical_components"] = data.pop(_prac_alias)
            break

    # internal assessment: several plausible headings
    for _ia_alias in (
        "internal_assessment_suggestions", "assessment", "cie",
        "continuous_internal_evaluation", "internal_assessments",
    ):
        if _ia_alias in data and "internal_assessment" not in data:
            data["internal_assessment"] = data.pop(_ia_alias)
            break

    # These are lists of prose lines. A model that emits [{"description": "..."}]
    # or [{"title": "..."}] instead of ["..."] is saying the same thing in a
    # different shape — flatten rather than reject, so a well-formed syllabus is
    # not thrown away over its container type.
    for _list_key in ("objectives", "practical_components", "internal_assessment"):
        raw_items = data.get(_list_key)
        if not isinstance(raw_items, list):
            data[_list_key] = []
            continue
        flattened: list[str] = []
        for item in raw_items:
            if isinstance(item, str) and item.strip():
                flattened.append(item.strip())
            elif isinstance(item, dict):
                for k in ("description", "text", "title", "objective", "statement"):
                    candidate = str(item.get(k, "")).strip()
                    if candidate:
                        flattened.append(candidate)
                        break
        data[_list_key] = flattened

    # units: Groq sometimes uses course_units, learning_units, unit_breakdown
    for _unit_alias in ("course_units", "learning_units", "unit_breakdown", "unit_list"):
        if _unit_alias in data and "units" not in data:
            data["units"] = data.pop(_unit_alias)
            break

    # reference_queries: Groq sometimes uses references, online_learning_resources, etc.
    for _ref_alias in (
        "online_learning_resources", "references", "bibliography",
        "reading_list", "suggested_references", "resource_list",
    ):
        if _ref_alias in data and "reference_queries" not in data:
            data["reference_queries"] = data.pop(_ref_alias)
            break

    # --- CO normalization ---
    outcomes: list[Any] = data.get("outcomes", [])
    for i, co in enumerate(outcomes):
        if not isinstance(co, dict):
            continue

        # bloom -> bloom_level alias
        if "bloom_level" not in co and "bloom" in co:
            co["bloom_level"] = co.pop("bloom")

        # Map description aliases when the field is absent OR empty/whitespace.
        # Groq sometimes emits description:"" while the real text is in a co_* alias.
        #
        # And when there is NO alias — when the model simply did not write the outcome —
        # nothing is put in its place. There used to be: a synthesized "CO3: demonstrate
        # competency through Apply-level mastery of core concepts", manufactured here to
        # satisfy the schema. It satisfied the schema. It also meant a Course Outcome
        # that no model wrote and no academic chose could reach an approved syllabus, be
        # locked into a regulation, and become the thing a student is examined against —
        # and nobody would ever know it had been invented in a normaliser.
        #
        # An empty description now fails validation (the schema requires 15 characters),
        # the response is rejected, and the outcomes are regenerated. A missing outcome
        # is a failure to be retried, never a blank to be filled.
        if not str(co.get("description", "")).strip():
            for alias in ("co_statement", "co_description", "statement", "co"):
                candidate = str(co.get(alias, "")).strip()
                if candidate:
                    co["description"] = candidate
                    break

        # Always strip remaining alias keys so Pydantic sees no unexpected fields.
        for alias in ("co_statement", "co_description", "statement", "co", "bloom"):
            co.pop(alias, None)
        if not co.get("code"):
            co["code"] = f"CO{i + 1}"
        if "suggested_po_codes" not in co:
            co["suggested_po_codes"] = []

        # po_mapping_strengths aliases. The ALIAS is mapped — a model that put the same
        # answer under a different key gave the answer — but a missing answer is left
        # missing, and the validator then rejects the outcome.
        #
        # It used to be filled with MEDIUM. That figure IS the CO-PO matrix an
        # accreditation body reads: it is the university's claim about how strongly this
        # outcome drives that programme outcome. Manufacturing it here meant NBA and NAAC
        # could be shown a claim that no academic made and no model wrote.
        if "po_mapping_strengths" not in co:
            for alias in ("po_strengths", "mapping_strengths", "po_code_strengths"):
                if alias in co:
                    co["po_mapping_strengths"] = co.pop(alias)
                    break
            else:
                co["po_mapping_strengths"] = {}

    # --- unit normalization ---
    units: list[Any] = data.get("units", [])
    for i, unit in enumerate(units):
        if not isinstance(unit, dict):
            continue

        # unit_number: display_order fallback then sequential
        if not unit.get("unit_number"):
            unit["unit_number"] = unit.pop("display_order", None) or (i + 1)

        # title aliases: unit_name / unit_title / name
        if not str(unit.get("title", "")).strip():
            for alias in ("unit_name", "unit_title", "name"):
                candidate = str(unit.get(alias, "")).strip()
                if candidate:
                    unit["title"] = candidate
                    break
        for alias in ("unit_name", "unit_title", "name"):
            unit.pop(alias, None)

        # total_hours aliases: hours / contact_hours / teaching_hours / duration
        if not unit.get("total_hours"):
            for alias in ("hours", "contact_hours", "teaching_hours", "duration", "lecture_hours"):
                val = unit.pop(alias, None)
                if val is not None:
                    try:
                        unit["total_hours"] = max(1, int(val))
                    except (TypeError, ValueError):
                        pass
                    break
            # last resort: count hours_estimate across topics, or fall back to 6
            if not unit.get("total_hours"):
                raw_for_sum: list[Any] = unit.get("topics", [])
                estimated = sum(
                    int(t.get("hours_estimate", 0))
                    for t in raw_for_sum
                    if isinstance(t, dict) and t.get("hours_estimate")
                )
                unit["total_hours"] = estimated if estimated >= 1 else 6
        else:
            # Ensure it's a positive int (guard against "10 hours" strings)
            try:
                unit["total_hours"] = max(1, int(unit["total_hours"]))
            except (TypeError, ValueError):
                unit["total_hours"] = 6

        # content: the official prose block. A model that put it under a different
        # name, or that emitted a list of concepts instead of a sentence, is saying
        # the same thing — join it rather than fail the whole syllabus over shape.
        if not str(unit.get("content", "")).strip():
            for calias in ("unit_content", "syllabus_content", "description", "body", "text"):
                cand = unit.get(calias)
                if isinstance(cand, list):
                    cand = ", ".join(str(x).strip() for x in cand if str(x).strip())
                cand = str(cand or "").strip()
                if cand:
                    unit["content"] = cand
                    break
        for calias in ("unit_content", "syllabus_content", "body", "text"):
            unit.pop(calias, None)

        # Last resort: compose the prose block from the topic titles. A syllabus
        # whose topics are sound but whose content field went missing is worth
        # saving; the length floor on _UnitAI still rejects it if it is too thin.
        if not str(unit.get("content", "")).strip():
            titles = [
                str(t.get("title", "")).strip()
                for t in unit.get("topics", [])
                if isinstance(t, dict) and str(t.get("title", "")).strip()
            ]
            if titles:
                unit["content"] = ", ".join(titles) + "."

        # topics: strings → {"title": str}; dicts with topic_title/topic_name → title
        raw_topics: list[Any] = unit.get("topics", [])
        normalized_topics = []
        for t in raw_topics:
            if isinstance(t, str):
                normalized_topics.append({"title": t})
            elif isinstance(t, dict):
                if not str(t.get("title", "")).strip():
                    for talias in ("topic_title", "topic_name", "name"):
                        cand = str(t.get(talias, "")).strip()
                        if cand:
                            t["title"] = cand
                            break
                for talias in ("topic_title", "topic_name"):
                    t.pop(talias, None)
                normalized_topics.append(t)
        unit["topics"] = normalized_topics

    # --- reference_queries normalization ---
    ref_queries: list[Any] = data.get("reference_queries", [])
    normalized_rqs = []
    for rq in ref_queries:
        if not isinstance(rq, dict):
            continue
        # query_str aliases: query, search_query, keyword
        if not rq.get("query_str"):
            for rq_alias in ("query", "search_query", "keyword", "title"):
                cand = str(rq.get(rq_alias, "")).strip()
                if cand:
                    rq["query_str"] = cand
                    break
        for rq_alias in ("query", "search_query", "keyword"):
            rq.pop(rq_alias, None)
        # Only keep entries that have a valid query_str after normalization
        if rq.get("query_str"):
            normalized_rqs.append(rq)
    data["reference_queries"] = normalized_rqs

    return data


# ---------------------------------------------------------------------------
# Groq implementation (OpenAI-compatible API)
# ---------------------------------------------------------------------------

class GroqSyllabusProvider:
    """Groq llama-3.3-70b-versatile via the OpenAI-compatible API."""

    async def generate_syllabus(
        self,
        ctx: SyllabusGenerationContext,
    ) -> SyllabusGenerationResult:
        if not settings.GROQ_API_KEY:
            raise SyllabusAIError(
                "GROQ_API_KEY is not configured — cannot use Groq fallback. "
                "Set GROQ_API_KEY in your .env file."
            )

        # Deferred import — keeps module loadable without openai installed in tests.
        from openai import AsyncOpenAI

        system, user = _build_prompt(ctx)
        phash = _prompt_hash(system, user)

        client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
        )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise SyllabusAIBlockedError("Groq returned an empty response.")

        # Normalize Groq-specific field aliases before schema validation.
        # _normalize_groq_response raises SyllabusAIParseError on bad JSON.
        normalized = _normalize_groq_response(raw)
        logger.debug("Groq normalized payload keys: %s", list(normalized.keys()))

        return _full_result(
            normalized, ctx,
            provider_name="groq",
            model_used=settings.GROQ_MODEL,
            prompt_hash=phash,
        )


    async def generate_section(
        self,
        ctx: SyllabusGenerationContext,
        section: str,
        **kwargs,
    ) -> SectionGenerationResult:
        if not settings.GROQ_API_KEY:
            raise SyllabusAIError("GROQ_API_KEY is not configured.")
        from openai import AsyncOpenAI

        system, user = _build_section_prompt(ctx, section, **kwargs)
        phash = _prompt_hash(system, user)

        client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0.35,
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise SyllabusAIBlockedError("Groq returned an empty response for a section.")
        return _section_result(
            raw, section, ctx,
            provider_name="groq", model_used=settings.GROQ_MODEL, prompt_hash=phash,
            normalize=True,
        )


# ---------------------------------------------------------------------------
# Fallback helpers
# ---------------------------------------------------------------------------

_QUOTA_SIGNALS = (
    "resource_exhausted",
    "429",
    "quota",
    "rate_limit",
    "rate limit",
    "too many requests",
)


def _is_gemini_quota_error(exc: Exception) -> bool:
    """Return True when the exception indicates a Gemini quota / rate-limit hit."""
    msg = str(exc).lower()
    return any(s in msg for s in _QUOTA_SIGNALS)


class DeepSeekSyllabusProvider:
    """DeepSeek-V3 via the OpenAI-compatible API."""

    async def generate_syllabus(
        self,
        ctx: SyllabusGenerationContext,
    ) -> SyllabusGenerationResult:
        if not settings.DEEPSEEK_API_KEY:
            raise SyllabusAIError(
                "DEEPSEEK_API_KEY is not configured — cannot use DeepSeek. "
                "Set DEEPSEEK_API_KEY in your .env file."
            )

        from openai import AsyncOpenAI

        system, user = _build_prompt(ctx)
        phash = _prompt_hash(system, user)

        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )

        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
        )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise SyllabusAIBlockedError("DeepSeek returned an empty response.")

        normalized = _normalize_groq_response(raw)
        logger.debug("DeepSeek normalized payload keys: %s", list(normalized.keys()))

        return _full_result(
            normalized, ctx,
            provider_name="deepseek",
            model_used=settings.DEEPSEEK_MODEL,
            prompt_hash=phash,
        )


    async def generate_section(
        self,
        ctx: SyllabusGenerationContext,
        section: str,
        **kwargs,
    ) -> SectionGenerationResult:
        if not settings.DEEPSEEK_API_KEY:
            raise SyllabusAIError("DEEPSEEK_API_KEY is not configured.")
        from openai import AsyncOpenAI

        system, user = _build_section_prompt(ctx, section, **kwargs)
        phash = _prompt_hash(system, user)

        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0.35,
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise SyllabusAIBlockedError("DeepSeek returned an empty response for a section.")
        return _section_result(
            raw, section, ctx,
            provider_name="deepseek", model_used=settings.DEEPSEEK_MODEL, prompt_hash=phash,
            normalize=True,
        )


class FallbackSyllabusProvider:
    """
    Tries Gemini → Groq → DeepSeek in order, stopping at first success.
    Any exception from a provider causes the next provider to be tried.
    """

    def __init__(self) -> None:
        self._chain: list[tuple[str, object]] = [
            ("gemini",   GeminiSyllabusProvider()),
            ("groq",     GroqSyllabusProvider()),
            ("deepseek", DeepSeekSyllabusProvider()),
        ]

    def _is_available(self, name: str) -> bool:
        if name == "gemini":
            return settings.AI_GEMINI_ENABLED and bool(settings.GEMINI_API_KEY)
        if name == "groq":
            return settings.AI_GROQ_ENABLED and bool(settings.GROQ_API_KEY)
        if name == "deepseek":
            return settings.AI_DEEPSEEK_ENABLED and bool(settings.DEEPSEEK_API_KEY)
        return False

    async def generate_syllabus(
        self,
        ctx: SyllabusGenerationContext,
    ) -> SyllabusGenerationResult:
        last_exc: Exception | None = None

        for name, provider in self._chain:
            if not self._is_available(name):
                logger.debug("M02 provider=%s skipped (disabled or key not set).", name)
                continue
            try:
                result = await provider.generate_syllabus(ctx)  # type: ignore[union-attr]
                logger.info("provider=%s model=%s", name, result.model_used)
                return result
            except Exception as exc:
                logger.warning(
                    "provider=%s failed (%s: %s) — trying next provider.",
                    name, type(exc).__name__, exc,
                )
                last_exc = exc

        # A quality failure is re-raised WITH ITS TYPE, not flattened into a
        # RuntimeError: the retry above this one only regenerates a document that was
        # too thin to publish, and it cannot tell that apart from a dead API key if
        # every failure arrives as the same exception.
        if isinstance(last_exc, (SyllabusAIValidationError, SyllabusAIParseError)):
            raise last_exc

        raise RuntimeError(
            "All syllabus AI providers failed. "
            f"Last error: {last_exc}"
        ) from last_exc


    async def generate_section(
        self,
        ctx: SyllabusGenerationContext,
        section: str,
        **kwargs,
    ) -> SectionGenerationResult:
        last_exc: Exception | None = None
        for name, provider in self._chain:
            if not self._is_available(name):
                continue
            try:
                result = await provider.generate_section(ctx, section, **kwargs)
                logger.info("section=%s provider=%s model=%s", section, name, result.model_used)
                return result
            except Exception as exc:
                logger.warning(
                    "section=%s provider=%s failed (%s: %s) — trying next provider.",
                    section, name, type(exc).__name__, exc,
                )
                last_exc = exc

        if isinstance(last_exc, (SyllabusAIValidationError, SyllabusAIParseError)):
            raise last_exc

        raise RuntimeError(
            f"All syllabus AI providers failed to regenerate {section}. Last error: {last_exc}"
        ) from last_exc


# ---------------------------------------------------------------------------
# What the Board is watching
#
# A generation takes minutes and makes ten AI calls. A spinner for the whole of it is
# what makes this feel like "a button that asks a machine for a syllabus" — the thing
# the product must never feel like. So the job says what it is doing, in the words a
# Board member would use, and never in ours: no sections, no schemas, no JSON, no
# provider names, no retry counts.
#
# The phase is a machine-readable key; the message is what a human reads. The message
# is written HERE, next to the work, rather than being reconstructed in the frontend
# from a status code — the two would drift, and the one that would drift is the one the
# Board reads.
# ---------------------------------------------------------------------------

PHASE_READING    = "READING"
PHASE_OUTLINE    = "OUTLINE"
PHASE_UNIT       = "UNIT"
PHASE_OBJECTIVES = "OBJECTIVES"
PHASE_OUTCOMES   = "OUTCOMES"
PHASE_REFERENCES = "REFERENCES"
PHASE_SAVING     = "SAVING"
PHASE_READY      = "READY"


# ---------------------------------------------------------------------------
# The theory syllabus, written ONE UNIT AT A TIME
#
# A Board of Studies does not draft a syllabus in a single breath, and neither should
# the generator. Asked for the whole thing at once, a model spends its attention on
# the shape of the document — five units, some outcomes, a reading list — and Unit IV
# comes back with three topics because by then it has run out of care. That is the
# single failure this workflow exists to remove.
#
# So the course is written the way a Board writes it:
#
#     1. OUTLINE     divide the course into its units, once, as a whole
#     2. UNIT I      write it, validate it, regenerate it if it is thin
#     3. UNIT II     ... and so on, each told what the others hold
#     4. OBJECTIVES  written to the units that now exist
#     5. OUTCOMES    the same — an outcome must be about material a unit teaches
#     6. READING     the same
#
# Each step is validated on its own, and a step that fails its bar is retried on its
# own (RetryingSyllabusProvider) rather than costing the syllabus around it. Nothing
# is written to the database until every step has passed: the caller assembles the
# whole document in memory, and the worker persists it in one transaction. A Board
# that opens a generated syllabus finds it finished, or finds that generation failed.
# It never finds Unit IV half-written and its own name on the approval.
# ---------------------------------------------------------------------------

async def generate_theory_syllabus(
    provider: SyllabusProvider,
    ctx: SyllabusGenerationContext,
    *,
    on_progress: Callable[[str, str], Awaitable[None]] | None = None,
    on_unit: Callable[[dict], Awaitable[None]] | None = None,
) -> SyllabusGenerationResult:
    """Draft one complete theory syllabus, a unit at a time.

    Only THEORY. A lab manual, an internship's guidelines and a project handbook have
    no units to write one at a time, and they keep the single-call path they have
    always had — see `_build_prompt` and the course-type schemas.

    `on_progress(phase, message)` is told what is happening, in the words the Board
    reads: "Generating Unit II…". `on_unit(unit)` is handed each unit the moment it
    passes validation, so the caller can SAVE it — a unit that has been written and
    checked is work worth keeping, and a run that dies at Unit V should not throw away
    the four good units before it. Neither callback may change what is generated; they
    watch and they persist.
    """
    n = resolve_unit_count(ctx.unit_count)
    plan = _unit_hours_plan(ctx)

    async def progress(phase: str, message: str) -> None:
        if on_progress:
            await on_progress(phase, message)

    # 1. THE OUTLINE — how the course divides.
    #
    # Internal, always. It is never stored, never shown and never editable: the
    # curriculum the Board wrote is the source of truth, and an editable outline would
    # be a second one. It exists so the units do not overlap.
    await progress(PHASE_OUTLINE, "Preparing academic outline…")
    outline_result = await provider.generate_section(ctx, SECTION_OUTLINE)
    outline = outline_result.outline or []

    # 2. THE UNITS — one at a time, each knowing what the ones before it taught.
    units: list[dict] = []
    taught: list[str] = []      # every topic the syllabus already carries

    for index, planned in enumerate(outline[:n]):
        number = planned["unit_number"]
        await progress(PHASE_UNIT, f"Generating Unit {roman(number)}…")

        unit_ctx = dataclasses.replace(
            ctx,
            # The Board's hours for THIS unit. The model writes the unit to them; it
            # does not choose them, and the worker stamps them again afterwards.
            unit_hours=plan[index] if index < len(plan) else None,
            # Where it sits on the arc of the course, from the outline. Without this a
            # unit drafted alone reaches for the basics whatever number it carries.
            unit_level=planned.get("level"),
            # And everything already taught. This is CHECKED, not merely asked: a unit
            # that repeats an earlier topic is rejected and redrafted (see
            # _cross_unit_duplicates), and only this unit is — the others are untouched.
            used_topics=list(taught),
        )

        result = await provider.generate_section(
            unit_ctx,
            SECTION_UNIT,
            unit_number=number,
            unit_title=planned["title"],
            unit_scope=planned["scope"],
            sibling_units=[
                f"Unit {roman(u['unit_number'])}: {u['title']} — {u['scope']}"
                for u in outline
                if u["unit_number"] != number
            ],
        )

        unit = dict(result.unit or {})
        # The unit's PLACE in the syllabus is the outline's, not the model's. Asked to
        # write Unit III, a model will occasionally number it 1 — and a syllabus with
        # two Unit Is fails to save at all (syllabus_units has a uniqueness
        # constraint), which would throw away the four good units around it.
        unit["unit_number"] = number

        await progress(PHASE_UNIT, f"Validating Unit {roman(number)}…")
        # It is ALREADY validated — the provider rejected and redrafted it until it
        # passed. Saying so is not theatre: this is the step the Board most needs to
        # believe happened, and it is the reason they will never be handed Unit III
        # with three topics in it.

        units.append(unit)
        taught.extend(t["title"] for t in unit.get("topics", []))

        if on_unit:
            await on_unit(unit)      # written, checked, and now safe on disk

    # What the syllabus now actually teaches — the brief for everything that follows.
    written_ctx = dataclasses.replace(
        ctx,
        unit_summary=[
            f"Unit {roman(u['unit_number'])} — {u['title']}: "
            + ", ".join(t["title"] for t in u.get("topics", [])[:12])
            for u in units
        ],
    )

    # 3. OBJECTIVES, OUTCOMES and the READING — written to the units, not to the title.
    await progress(PHASE_OBJECTIVES, "Creating Course Objectives…")
    objectives_result = await provider.generate_section(written_ctx, SECTION_OBJECTIVES)

    await progress(PHASE_OUTCOMES, "Creating Course Outcomes…")
    outcomes_result   = await provider.generate_section(written_ctx, SECTION_OUTCOMES)

    await progress(PHASE_REFERENCES, "Creating Reference Books…")

    # Text Books and the wider reading are two printed sections and two requests, for
    # the same reason the Board can regenerate them separately: they answer different
    # questions, and one list of eight mixed queries is reliably four good textbooks
    # and four vague web resources.
    books_result = await provider.generate_section(written_ctx, SECTION_BOOKS)
    refs_result  = await provider.generate_section(written_ctx, SECTION_REFERENCES)

    practicals: list[str] = []
    if ctx.has_practical:
        practicals_result = await provider.generate_section(written_ctx, SECTION_PRACTICALS)
        practicals = list(practicals_result.practical_components or [])

    return SyllabusGenerationResult(
        doc_type=TYPE_THEORY,
        document={},
        objectives=list(objectives_result.objectives or []),
        outcomes=list(outcomes_result.outcomes or []),
        units=units,
        practical_components=practicals,
        # No Internal Assessment. The CIE pattern is a regulation-wide rule, and a
        # syllabus that states its own version of it is one more chance to contradict
        # the university's own.
        internal_assessment=[],
        reference_queries=(
            list(books_result.reference_queries or [])
            + list(refs_result.reference_queries or [])
        ),
        model_used=outcomes_result.model_used,
        provider_name=outcomes_result.provider_name,
        # The outline's hash. Every other call in this syllabus descends from it, and
        # one hash on the audit record has to stand for the document as a whole.
        prompt_hash=outline_result.prompt_hash,
    )


# ---------------------------------------------------------------------------
# Retry — a thin syllabus is regenerated, not saved
#
# The Board must never be handed a unit with three topics and asked to write the
# other nine. That is the work the generator exists to do, and a document that
# arrives half-written is worse than one that failed outright: it looks finished.
#
# So a response that fails the depth bar is not a result, it is an attempt. The
# violations are fed back into the next attempt — a retry that says nothing about the
# failure is a retry that reproduces it — and only a response that passes is ever
# returned to the worker, which is the only thing that writes to the database.
#
# When every attempt fails the job fails, loudly, and nothing is saved. The Board sees
# "generation failed, try again", which is true, rather than a hollow syllabus, which
# is a lie.
# ---------------------------------------------------------------------------

MAX_GENERATION_ATTEMPTS = 3


class RetryingSyllabusProvider:
    """Wraps any provider and retries it until the document is deep enough to print.

    Only QUALITY failures are retried — a response that parsed but was too thin, too
    generic, or the wrong shape. A missing API key or a blocked prompt is not going to
    fix itself on the second attempt, so it is raised immediately rather than burning
    two more calls to reach the same place.
    """

    def __init__(self, inner: SyllabusProvider) -> None:
        self._inner = inner

    async def generate_syllabus(
        self,
        ctx: SyllabusGenerationContext,
    ) -> SyllabusGenerationResult:
        return await self._attempt(
            lambda c: self._inner.generate_syllabus(c), ctx, what="syllabus",
        )

    async def generate_section(
        self,
        ctx: SyllabusGenerationContext,
        section: str,
        **kwargs,
    ) -> SectionGenerationResult:
        return await self._attempt(
            lambda c: self._inner.generate_section(c, section, **kwargs),
            ctx,
            what=f"section {section}",
        )

    async def _attempt(self, call, ctx: SyllabusGenerationContext, *, what: str):
        # The feedback is written onto a COPY of the context. The caller's ctx is not
        # ours to mutate, and a stale "your last attempt was rejected" leaking into an
        # unrelated later call would be a genuinely baffling bug to find.
        attempt_ctx = dataclasses.replace(ctx)
        last_exc: SyllabusAIError | None = None

        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            try:
                return await call(attempt_ctx)
            except (SyllabusAIValidationError, SyllabusAIParseError) as exc:
                last_exc = exc
                attempt_ctx.retry_feedback = str(exc)
                logger.warning(
                    "m02: %s failed the quality bar on attempt %d/%d — regenerating. %s",
                    what, attempt, MAX_GENERATION_ATTEMPTS, exc,
                )

        raise SyllabusAIValidationError(
            f"The {what} could not be generated to publishable depth after "
            f"{MAX_GENERATION_ATTEMPTS} attempts, so nothing was saved. Last failure:\n"
            f"{last_exc}"
        ) from last_exc


# ---------------------------------------------------------------------------
# Factory — driven by settings.AI_PROVIDER
# ---------------------------------------------------------------------------

_PROVIDER_MAP: dict[str, type] = {
    "gemini":   GeminiSyllabusProvider,
    "groq":     GroqSyllabusProvider,
    "deepseek": DeepSeekSyllabusProvider,
    "fallback": FallbackSyllabusProvider,
}


def get_syllabus_provider() -> SyllabusProvider:
    provider_cls = _PROVIDER_MAP.get(settings.AI_PROVIDER)
    if provider_cls is None:
        raise ValueError(
            f"Unknown AI_PROVIDER '{settings.AI_PROVIDER}'. "
            f"Must be one of: {sorted(_PROVIDER_MAP)}"
        )
    # Every provider is retried on a quality failure, including the fallback chain:
    # three models each returning a four-topic unit is three failures, not a result.
    return RetryingSyllabusProvider(provider_cls())
