"""
M03 AI provider — course kit generation via Gemini (primary) with Groq fallback.

Safety contract:
  - AI generates: slides (content, speaker_notes), quizlets (questions + answer_key),
    assignments (question_text, model_answer, rubric), teaching_plan, lesson_plans, resources.
  - CRITICAL: answer_key values MUST ONLY appear in the quizlets output.
    They must NEVER be embedded in slide bullets, key_concepts, image_hint, or speaker_notes.
  - The prompt explicitly prohibits answer_key leakage into slide content.
  - _validate_result() scans for obvious leakage patterns as a safety net.
  - Malformed or under-specified AI responses are rejected with typed exceptions.
  - Gemini and Groq clients are imported lazily so the module loads cleanly in tests.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("vidya.m03.ai_provider")

from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.modules.m03_course_kit.models import BloomLevel, QuizletType, AssignmentType, ComplexityLevel


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CourseKitAIError(Exception):
    """Base for all M03 AI provider failures."""


class CourseKitAIBlockedError(CourseKitAIError):
    """Gemini safety filter blocked the response or quota exhausted."""


class CourseKitAIParseError(CourseKitAIError):
    """AI response did not match the expected JSON schema."""


class CourseKitAIValidationError(CourseKitAIError):
    """Response parsed but failed business-rule or safety validation."""


# ---------------------------------------------------------------------------
# IO dataclasses (no ORM dependency)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class COContext:
    code:        str   # e.g. CO1, CO2
    description: str   # full CO statement
    bloom_level: str   # e.g. APPLY, ANALYSE


@dataclasses.dataclass
class KitGenerationContext:
    kit_id:              str              # UUID as string
    unit_number:         int
    unit_title:          str
    unit_topics:         list[str]        # topic titles from the approved syllabus unit
    course_code:         str
    course_title:        str
    complexity_level:    str              # "UG" | "PG"
    tone:                str | None
    custom_instructions: str | None
    cos:                 list[COContext]  # approved COs for CO mapping guidance
    min_slides:          int              # from settings.M03_MIN_SLIDES_PER_UNIT
    min_quizlets:        int              # from settings.M03_MIN_QUIZLETS_PER_UNIT


@dataclasses.dataclass
class SlideAI:
    slide_number:  int
    title:         str
    content:       dict[str, Any]   # {bullets, key_concepts, image_hint, code_snippet}
    speaker_notes: str | None
    bloom_level:   str | None
    co_reference:  str | None


@dataclasses.dataclass
class QuizletAI:
    question_number:    int
    question_text:      str
    question_type:      str             # MCQ | SHORT_ANSWER
    options:            list[dict]      # [{label, text}] — MCQ only
    answer_key:         dict[str, Any]  # {"correct": "A"} or {"answer_points": [...]}
    answer_explanation: str | None
    bloom_level:        str | None
    co_reference:       str | None


@dataclasses.dataclass
class AssignmentAI:
    assignment_number:     int
    title:                 str
    assignment_type:       str              # CLASSWORK | HOMEWORK | CASE_STUDY
    question_text:         str
    complexity_level:      str              # UG | PG
    current_events_toggle: bool
    model_answer:          str | None
    rubric:                list[dict]       # [{criterion, description, max_marks}]
    bloom_level:           str | None
    co_reference:          str | None


@dataclasses.dataclass
class KitGenerationResult:
    """
    Validated, provider-neutral output from the AI kit generator.

    The answer_key fields on quizlets are always populated (NOT NULL contract from DB).
    They are never present in slide content — enforced by prompt + _validate_result.
    """
    slides:        list[SlideAI]
    quizlets:      list[QuizletAI]
    assignments:   list[AssignmentAI]
    teaching_plan: list[dict]   # TeachingPlanWeek-shaped dicts
    lesson_plans:  list[dict]   # LessonPlanSession-shaped dicts
    resources:     list[dict]   # ResourceItem-shaped dicts
    model_used:    str
    prompt_hash:   str


# ---------------------------------------------------------------------------
# Enum sets for validation
# ---------------------------------------------------------------------------

_VALID_BLOOM           = {b.value for b in BloomLevel}
_VALID_QUIZ_TYPES      = {q.value for q in QuizletType}
_VALID_ASSIGNMENT_TYPES = {a.value for a in AssignmentType}
_VALID_COMPLEXITY      = {c.value for c in ComplexityLevel}


# ---------------------------------------------------------------------------
# Private Pydantic models — Gemini response_schema + Groq parse target
# (never returned to callers; mapped to dataclasses in KitGenerationResult)
# ---------------------------------------------------------------------------

_VALID_SLIDE_TYPES = frozenset({
    # Original types
    "TITLE", "CONCEPT", "DEFINITION", "EXAMPLE",
    "CODE", "DIAGRAM", "ACTIVITY", "SUMMARY", "QUIZ",
    # Enhanced instructional types (stored in JSONB content.slide_type — no DB change)
    "OBJECTIVES", "WORKED_EXAMPLE", "COMMON_MISTAKES", "TOPIC_SUMMARY",
})

# Map slide title keywords → inferred slide_type used when AI omits the field.
# ORDER MATTERS: more specific patterns must precede generic catch-alls.
_SLIDE_TYPE_KEYWORDS: list[tuple[str, str]] = [
    # TITLE
    ("overview",       "TITLE"),
    ("introducti",     "TITLE"),
    # TOPIC_SUMMARY (specific — must precede generic "summary"/"recap")
    ("topic summar",   "TOPIC_SUMMARY"),
    ("topic recap",    "TOPIC_SUMMARY"),
    # SUMMARY (unit-level; generic catch-alls follow specifics)
    ("unit recap",     "SUMMARY"),
    ("unit summary",   "SUMMARY"),
    ("summary",        "SUMMARY"),
    ("recap",          "SUMMARY"),      # generic: "Recap and Review" → SUMMARY
    # QUIZ
    ("quiz",           "QUIZ"),
    ("assessment",     "QUIZ"),
    # ACTIVITY
    ("activity",       "ACTIVITY"),
    ("exercise",       "ACTIVITY"),
    # DIAGRAM
    ("diagram",        "DIAGRAM"),
    ("chart",          "DIAGRAM"),
    # CODE
    ("code",           "CODE"),
    ("implement",      "CODE"),
    # WORKED_EXAMPLE (specific — must precede generic "example")
    ("worked example", "WORKED_EXAMPLE"),
    ("step-by-step",   "WORKED_EXAMPLE"),
    # EXAMPLE (generic)
    ("example",        "EXAMPLE"),
    ("case study",     "EXAMPLE"),
    # DEFINITION
    ("definition",     "DEFINITION"),
    ("terminolog",     "DEFINITION"),
    # OBJECTIVES
    ("objective",      "OBJECTIVES"),
    ("learning goal",  "OBJECTIVES"),
    # COMMON_MISTAKES
    ("mistake",        "COMMON_MISTAKES"),
    ("pitfall",        "COMMON_MISTAKES"),
    ("common error",   "COMMON_MISTAKES"),
    ("anti-pattern",   "COMMON_MISTAKES"),
]

# Aliases Groq uses for the enhanced slide types — normalized in _normalize_groq_kit_response.
_GROQ_SLIDE_TYPE_ALIASES: dict[str, str] = {
    "LEARNING_OBJECTIVES": "OBJECTIVES",
    "LEARNING OBJECTIVES":  "OBJECTIVES",
    "OBJECTIVE":            "OBJECTIVES",
    "LEARNING_OBJECTIVE":   "OBJECTIVES",
    "WORKED EXAMPLE":       "WORKED_EXAMPLE",
    "WORKED-EXAMPLE":       "WORKED_EXAMPLE",
    "STEP_BY_STEP":         "WORKED_EXAMPLE",
    "STEP BY STEP":         "WORKED_EXAMPLE",
    "MISTAKES":             "COMMON_MISTAKES",
    "ERRORS":               "COMMON_MISTAKES",
    "PITFALLS":             "COMMON_MISTAKES",
    "ANTI_PATTERNS":        "COMMON_MISTAKES",
    "ANTI-PATTERNS":        "COMMON_MISTAKES",
    "COMMON_ERRORS":        "COMMON_MISTAKES",
    "TOPIC_RECAP":          "TOPIC_SUMMARY",
    "TOPIC SUMMARY":        "TOPIC_SUMMARY",
    "TOPIC RECAP":          "TOPIC_SUMMARY",
    "MINI_SUMMARY":         "TOPIC_SUMMARY",
}


def _infer_slide_type(slide_number: int, title: str, has_code: bool) -> str:
    """Return the best-guess slide type when the AI did not supply one."""
    if slide_number == 1:
        return "TITLE"
    if has_code:
        return "CODE"
    tl = title.lower()
    for keyword, stype in _SLIDE_TYPE_KEYWORDS:
        if keyword in tl:
            return stype
    return "CONCEPT"


class _SlideContentAI(BaseModel):
    slide_type:         str | None = None   # TITLE|CONCEPT|DEFINITION|EXAMPLE|CODE|DIAGRAM|ACTIVITY|SUMMARY|QUIZ
    bullets:            list[str]  = Field(default_factory=list)
    key_concepts:       list[str]  = Field(default_factory=list)
    definitions:        list[str]  = Field(default_factory=list)
    examples:           list[str]  = Field(default_factory=list)
    image_hint:         str | None = None
    code_snippet:       str | None = None
    diagram_prompt:     str | None = None
    classroom_activity: str | None = None
    teaching_notes:     str | None = None
    student_summary:    str | None = None

    @model_validator(mode="after")
    def _normalise_slide_type(self) -> _SlideContentAI:
        if self.slide_type:
            up = self.slide_type.upper()
            self.slide_type = up if up in _VALID_SLIDE_TYPES else None
        return self


class _SlideAI(BaseModel):
    slide_number:  int             = Field(..., ge=1)
    title:         str             = Field(..., min_length=2)
    content:       _SlideContentAI = Field(default_factory=_SlideContentAI)
    speaker_notes: str | None      = None
    bloom_level:   str | None      = None
    co_reference:  str | None      = None

    @model_validator(mode="after")
    def _normalise_bloom(self) -> _SlideAI:
        if self.bloom_level:
            up = self.bloom_level.upper()
            self.bloom_level = up if up in _VALID_BLOOM else None
        return self


class _QuizletOptionAI(BaseModel):
    label: str = Field(..., min_length=1, max_length=4)
    text:  str = Field(..., min_length=1)


class _QuizletAI(BaseModel):
    question_number:    int                    = Field(..., ge=1)
    question_text:      str                    = Field(..., min_length=10)
    question_type:      str                    = "MCQ"
    options:            list[_QuizletOptionAI] = Field(default_factory=list)
    answer_key:         dict[str, Any]         = Field(default_factory=dict)
    answer_explanation: str | None             = None
    bloom_level:        str | None             = None
    co_reference:       str | None             = None

    @model_validator(mode="after")
    def _normalise_enums(self) -> _QuizletAI:
        up = self.question_type.upper()
        self.question_type = up if up in _VALID_QUIZ_TYPES else "MCQ"
        if self.bloom_level:
            ub = self.bloom_level.upper()
            self.bloom_level = ub if ub in _VALID_BLOOM else None
        return self


class _RubricAI(BaseModel):
    criterion:  str = Field(..., min_length=2)
    description: str = ""
    max_marks:  int = Field(default=5, ge=1)


class _AssignmentAI(BaseModel):
    assignment_number:     int            = Field(..., ge=1)
    title:                 str            = Field(..., min_length=3)
    assignment_type:       str            = "CLASSWORK"
    question_text:         str            = Field(..., min_length=10)
    complexity_level:      str            = "UG"
    current_events_toggle: bool           = False
    model_answer:          str | None     = None
    rubric:                list[_RubricAI] = Field(default_factory=list)
    bloom_level:           str | None     = None
    co_reference:          str | None     = None

    @model_validator(mode="after")
    def _normalise_enums(self) -> _AssignmentAI:
        ua = self.assignment_type.upper()
        self.assignment_type = ua if ua in _VALID_ASSIGNMENT_TYPES else "CLASSWORK"
        uc = self.complexity_level.upper()
        self.complexity_level = uc if uc in _VALID_COMPLEXITY else "UG"
        if self.bloom_level:
            ub = self.bloom_level.upper()
            self.bloom_level = ub if ub in _VALID_BLOOM else None
        return self


class _TeachingWeekAI(BaseModel):
    week:          int       = Field(..., ge=1)
    topic:         str       = Field(..., min_length=2)
    objectives:    list[str] = Field(default_factory=list)
    activities:    list[str] = Field(default_factory=list)
    hours:         int       = Field(..., ge=1)
    co_references: list[str] = Field(default_factory=list)


class _LessonSessionAI(BaseModel):
    session:          int       = Field(..., ge=1)
    week:             int       = Field(..., ge=1)
    duration_minutes: int       = Field(default=60, ge=30)
    topic:            str       = Field(..., min_length=2)
    objectives:       list[str] = Field(default_factory=list)
    opening_activity: str | None = None
    main_content:     str       = ""
    closing_activity: str | None = None
    materials_needed: list[str] = Field(default_factory=list)
    bloom_levels:     list[str] = Field(default_factory=list)
    co_references:    list[str] = Field(default_factory=list)


class _ResourceItemAI(BaseModel):
    title:         str       = Field(..., min_length=2)
    resource_type: str       = "article"
    url:           str | None = None
    description:   str | None = None


class _KitAI(BaseModel):
    slides:        list[_SlideAI]
    quizlets:      list[_QuizletAI]
    assignments:   list[_AssignmentAI]
    teaching_plan: list[_TeachingWeekAI]  = Field(default_factory=list)
    lesson_plans:  list[_LessonSessionAI] = Field(default_factory=list)
    resources:     list[_ResourceItemAI]  = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Safety scan patterns — answer_key leakage into slide content
# ---------------------------------------------------------------------------

_ANSWER_LEAK_TERMS = (
    "answer_key",       # literal field name leaked into content text
    "answer key:",      # explicit heading notation
    "correct answer:",  # explicit answer annotation in slide text
    "key: {",           # JSON-like pattern accidentally embedded
)


def _scan_slide_answer_leak(slides: list[_SlideAI]) -> list[str]:
    """Return violation strings for any slide whose text embeds answer-key patterns."""
    violations: list[str] = []
    for slide in slides:
        combined_texts = [slide.title]
        combined_texts.extend(slide.content.bullets)
        combined_texts.extend(slide.content.key_concepts)
        combined_texts.extend(slide.content.definitions)
        combined_texts.extend(slide.content.examples)
        if slide.content.classroom_activity:
            combined_texts.append(slide.content.classroom_activity)
        if slide.content.teaching_notes:
            combined_texts.append(slide.content.teaching_notes)
        if slide.speaker_notes:
            combined_texts.append(slide.speaker_notes)

        haystack = " ".join(combined_texts).lower()
        found = [t for t in _ANSWER_LEAK_TERMS if t in haystack]
        if found:
            violations.append(
                f"Slide {slide.slide_number} '{slide.title[:50]}' appears to contain "
                f"answer-key content (matched: {found}). "
                "Answer keys must appear only in quizlet answer_key fields."
            )
    return violations


# ---------------------------------------------------------------------------
# Business-rule validation
# ---------------------------------------------------------------------------

def _validate_result(parsed: _KitAI, ctx: KitGenerationContext) -> list[str]:
    """
    Return a list of violation strings.  Empty list = valid.

    Checks:
      1. Minimum slide count (settings.M03_MIN_SLIDES_PER_UNIT).
      2. Minimum quizlet count (settings.M03_MIN_QUIZLETS_PER_UNIT).
      3. Slide numbers unique and 1-based.
      4. Question numbers unique and 1-based.
      5. Assignment numbers unique and 1-based.
      6. All bloom_levels are from the approved set (or None).
      7. MCQ quizlets have at least 2 options and a non-empty answer_key.
      8. Safety scan: no answer-key content embedded in slide text.
    """
    errors: list[str] = []

    # 1. Slide minimum
    if len(parsed.slides) < ctx.min_slides:
        errors.append(
            f"AI returned {len(parsed.slides)} slides; "
            f"minimum required is {ctx.min_slides} (M03_MIN_SLIDES_PER_UNIT)."
        )

    # 2. Quizlet minimum
    if len(parsed.quizlets) < ctx.min_quizlets:
        errors.append(
            f"AI returned {len(parsed.quizlets)} quizlets; "
            f"minimum required is {ctx.min_quizlets} (M03_MIN_QUIZLETS_PER_UNIT)."
        )

    # 3. Unique slide numbers
    slide_nums = [s.slide_number for s in parsed.slides]
    if len(slide_nums) != len(set(slide_nums)):
        errors.append("Duplicate slide_number values in AI response.")

    # 4. Unique question numbers
    q_nums = [q.question_number for q in parsed.quizlets]
    if len(q_nums) != len(set(q_nums)):
        errors.append("Duplicate question_number values in AI quizlets.")

    # 5. Unique assignment numbers
    a_nums = [a.assignment_number for a in parsed.assignments]
    if len(a_nums) != len(set(a_nums)):
        errors.append("Duplicate assignment_number values in AI assignments.")

    # 6. MCQ options + answer_key non-empty
    for q in parsed.quizlets:
        if q.question_type == "MCQ":
            if len(q.options) < 2:
                errors.append(
                    f"Quizlet {q.question_number} is MCQ but has fewer than 2 options."
                )
            if not q.answer_key:
                errors.append(
                    f"Quizlet {q.question_number} has an empty answer_key. "
                    "answer_key must never be empty (DB NOT NULL constraint)."
                )

    # 7. Safety: no answer-key leakage into slide content
    leak_violations = _scan_slide_answer_leak(parsed.slides)
    errors.extend(leak_violations)

    return errors


# ---------------------------------------------------------------------------
# Post-parse salvage — recovers from common AI formatting issues
# ---------------------------------------------------------------------------

def _salvage_parsed_kit(parsed: _KitAI) -> list[str]:
    """
    Repair common AI formatting issues in _KitAI after Pydantic parsing.

    Mutates parsed in-place; returns warning strings for the caller to log.
    Handles:
      - Duplicate slide / quizlet / assignment numbers → deduplicate then renumber
      - MCQ with empty answer_key → default to first option label (or "A")
    """
    warns: list[str] = []

    # Deduplicate + renumber slides
    seen: set[int] = set()
    kept_slides: list[_SlideAI] = []
    for s in parsed.slides:
        if s.slide_number in seen:
            warns.append(
                f"Dropped duplicate slide_number={s.slide_number} ('{s.title[:40]}')"
            )
        else:
            seen.add(s.slide_number)
            kept_slides.append(s)
    parsed.slides = kept_slides
    for i, s in enumerate(parsed.slides, 1):
        s.slide_number = i

    # Deduplicate + renumber quizlets
    seen = set()
    kept_qs: list[_QuizletAI] = []
    for q in parsed.quizlets:
        if q.question_number in seen:
            warns.append(f"Dropped duplicate question_number={q.question_number}")
        else:
            seen.add(q.question_number)
            kept_qs.append(q)
    parsed.quizlets = kept_qs
    for i, q in enumerate(parsed.quizlets, 1):
        q.question_number = i

    # Deduplicate + renumber assignments
    seen = set()
    kept_as: list[_AssignmentAI] = []
    for a in parsed.assignments:
        if a.assignment_number in seen:
            warns.append(f"Dropped duplicate assignment_number={a.assignment_number}")
        else:
            seen.add(a.assignment_number)
            kept_as.append(a)
    parsed.assignments = kept_as
    for i, a in enumerate(parsed.assignments, 1):
        a.assignment_number = i

    # Fix empty MCQ answer_key — default to first option label
    for q in parsed.quizlets:
        if q.question_type == "MCQ" and not q.answer_key:
            first_label = q.options[0].label if q.options else "A"
            q.answer_key = {"correct": first_label}
            warns.append(
                f"Quizlet {q.question_number}: inferred answer_key "
                f"{{'correct': {first_label!r}}} (AI omitted answer_key)."
            )

    return warns


# ---------------------------------------------------------------------------
# Soft-violation classifier
# ---------------------------------------------------------------------------

def _is_soft_violation(violation: str) -> bool:
    """
    Return True when a validation violation is recoverable.

    Soft violations → log a warning and proceed with generation.
    Hard violations (zero slides or zero quizlets from AI) → raise.
    """
    vl = violation.lower()
    # Count shortfalls: accept fewer items than the ideal minimum
    if vl.startswith("ai returned") and "minimum" in vl:
        return True
    # Answer-key safety scan: warn but preserve the slide content
    if "appears to contain answer-key content" in vl:
        return True
    # MCQ structural issues: handled by salvage; soft if still present
    if "fewer than 2 options" in vl or "empty answer_key" in vl:
        return True
    # Duplicate numbers: fixed by salvage; soft if somehow still present
    if "duplicate" in vl:
        return True
    return False


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(ctx: KitGenerationContext) -> tuple[str, str]:
    """
    Build a quality-focused prompt for a 10-slide lecture deck.

    Design principle: depth over breadth.  Each slide covers one instructional
    purpose well.  Speaker notes carry the detailed faculty script so visible
    slide content stays clean and editable.

    Token budget target: ≤8 000 output tokens (safe for Groq free tier).
    """
    topic_list = ", ".join(ctx.unit_topics) if ctx.unit_topics else "all unit topics"

    system = (
        "You are an expert academic curriculum designer for Indian universities. "
        "You create complete, unit-level teaching kits aligned with NBA/NAAC "
        "accreditation standards and Bloom's revised taxonomy.\n\n"

        "GENERATE EXACTLY 10 SLIDES in this fixed order:\n"
        "  Slide 1  : TITLE          — unit overview and scope\n"
        "  Slide 2  : OBJECTIVES     — measurable learning outcomes (Bloom-tagged)\n"
        "  Slide 3  : CONCEPT        — primary concept: how it works and why it matters\n"
        "  Slide 4  : DEFINITION     — key terms with formal definitions\n"
        "  Slide 5  : WORKED_EXAMPLE — named, step-by-step real-world scenario\n"
        "  Slide 6  : CODE           — annotated code (use DIAGRAM if no programming)\n"
        "  Slide 7  : COMMON_MISTAKES — anti-patterns with corrections\n"
        "  Slide 8  : ACTIVITY       — timed classroom task\n"
        "  Slide 9  : QUIZ           — 2-3 visible checkpoint questions on the slide\n"
        "  Slide 10 : SUMMARY        — unit recap and next steps\n\n"

        "CONTENT RULES — apply to every slide:\n"
        "  bullets       : 4-6 complete sentences — each a teaching point, not a fragment\n"
        "  key_concepts  : 3-5 critical terms (slides 3-6 especially)\n"
        "  definitions   : formal 'Term: definition' entries (required on slides 4 and 3)\n"
        "  teaching_notes: 2-3 sentences — a misconception to address + a discussion prompt\n"
        "  student_summary: 1-2 sentences the student should walk away understanding\n"
        "  bloom_level   : one of REMEMBER / UNDERSTAND / APPLY / ANALYSE / EVALUATE / CREATE\n"
        "  co_reference  : one or more CO codes, e.g. 'CO1' or 'CO1, CO2'\n"
        "  speaker_notes : 120-200 word faculty delivery script per slide —\n"
        "    what to say verbatim, timing guidance, likely student questions with brief answers,\n"
        "    connection to previous/next slide, and one pacing cue\n\n"

        "PER SLIDE TYPE — additional requirements:\n\n"

        "TITLE slide:\n"
        "  bullets: 3-4 sentences describing what this unit covers and its industry relevance\n"
        "  key_concepts: 4-5 major themes of the unit\n"
        "  student_summary: 'By the end of this unit you will be able to [unit outcome].'\n\n"

        "OBJECTIVES slide:\n"
        "  bullets: 4-5 items, each starting with a Bloom verb\n"
        "    (Identify / Explain / Apply / Analyse / Evaluate / Create)\n"
        "  bloom_level: highest level targeted in this unit\n"
        "  co_reference: all COs addressed in the unit\n\n"

        "CONCEPT slide:\n"
        "  bullets: 5-6 sentences explaining the primary concept clearly\n"
        "  key_concepts: the 4-5 terms that define this concept\n"
        "  definitions: 2-3 formal definitions of terms introduced here\n"
        "  diagram_prompt: one-sentence description for a diagram if it aids understanding\n\n"

        "DEFINITION slide:\n"
        "  definitions: 5-6 entries in 'Term: formal definition' format\n"
        "  key_concepts: the terms being defined\n"
        "  bullets: 1-2 sentences linking these terms as a coherent vocabulary set\n\n"

        "WORKED_EXAMPLE slide:\n"
        "  title: MUST start with 'Worked Example: ' then a named real scenario\n"
        "  examples: 4-5 steps, each 'Step N: [action]'\n"
        "  bullets: expected output or result of the example\n"
        "  student_summary: state the outcome plainly\n\n"

        "CODE slide:\n"
        "  code_snippet: minimum 10 well-commented lines in the subject language\n"
        "  bullets: 4-5 annotation lines, e.g. 'Line 3: opens a file handle using with'\n"
        "  teaching_notes: 2 specific syntax errors students commonly make here\n\n"

        "COMMON_MISTAKES slide:\n"
        "  bullets: 6-8 items — alternate wrong then correct for each mistake:\n"
        "    'Wrong: [what students do]'\n"
        "    'Correct: [right approach]'\n"
        "  teaching_notes: cognitive root cause of the most critical mistake\n\n"

        "ACTIVITY slide:\n"
        "  classroom_activity: '[N min] Method: step-by-step instructions. Expected output.'\n"
        "  bullets: 4-5 facilitator instructions (what the TEACHER does)\n"
        "  teaching_notes: what to do if students finish early or get stuck\n\n"

        "QUIZ slide:\n"
        "  bullets: 2-3 checkpoint questions written out in full as visible questions on the slide\n"
        "    Do NOT include answers on the slide face\n"
        "  teaching_notes: brief answer guide for faculty (2-3 sentences per question)\n"
        "  student_summary: 'Attempt these before checking the answer key.'\n\n"

        "SUMMARY slide:\n"
        "  bullets: 5-6 unit-wide takeaways starting with 'Key point:'\n"
        "  key_concepts: all major terms from the unit\n"
        "  co_reference: all COs covered in this unit\n"
        "  examples: 2-3 real-world applications of what was learned\n"
        "  student_summary: one assessment preparation tip\n\n"

        "QUIZLETS (separate from the QUIZ slide — for the assessment bank):\n"
        f"  Generate minimum {ctx.min_quizlets} questions. Mix MCQ and SHORT_ANSWER.\n"
        "  MCQ: 4 options A/B/C/D; answer_key: {\"correct\": \"<label>\"}.\n"
        "  SHORT_ANSWER: answer_key: {\"answer_points\": [\"key point 1\", \"key point 2\"]}.\n"
        "  CRITICAL: answer_key MUST NOT appear anywhere in slide content.\n\n"

        "ASSIGNMENTS: 2-4 tasks (at least 1 CLASSWORK and 1 HOMEWORK).\n"
        "  Each needs model_answer and rubric with 3+ criteria.\n\n"

        "TEACHING PLAN: 1 row per major topic — week, topic, objectives, activities, "
        "hours, co_references.\n"
        "LESSON PLANS: 1 session per major topic.\n"
        "RESOURCES: 4-6 references. No author names, DOIs, or ISBNs.\n\n"

        "JSON STRUCTURE — strictly flat, no nesting by topic:\n"
        "  {\"slides\": [...10 slides...], \"quizlets\": [...], \"assignments\": [...],\n"
        "   \"teaching_plan\": [...], \"lesson_plans\": [...], \"resources\": [...]}\n"
        "Return only valid JSON. No prose. No markdown fences."
    )

    # ── User prompt ──────────────────────────────────────────────────────────

    co_lines = "\n".join(
        f"  {co.code} [{co.bloom_level}]: {co.description}"
        for co in ctx.cos
    ) or "  (no COs provided)"

    custom_clause = (
        f"\nAdditional faculty instructions: {ctx.custom_instructions}"
        if ctx.custom_instructions else ""
    )
    tone_str = ctx.tone or "academic"

    user = (
        f"Generate a complete teaching kit for Unit {ctx.unit_number} of:\n"
        f"  Course Code  : {ctx.course_code}\n"
        f"  Course Title : {ctx.course_title}\n"
        f"  Unit Title   : {ctx.unit_title}\n"
        f"  Complexity   : {ctx.complexity_level}\n"
        f"  Tone         : {tone_str}\n\n"
        f"Topics covered in this unit:\n"
        f"  {topic_list}\n\n"
        f"Course Outcomes (use co_reference to map each slide/quizlet/assignment):\n"
        f"{co_lines}\n\n"
        f"SLIDE REQUIREMENTS:\n"
        f"- Generate exactly 10 slides following the numbered order in the system prompt.\n"
        f"- Every slide must have non-empty bullets, bloom_level, co_reference,\n"
        f"  teaching_notes, student_summary, and speaker_notes.\n"
        f"- Slide 5 title MUST start with 'Worked Example: '.\n"
        f"- Slide 6 MUST include code_snippet with 10+ lines if the subject involves\n"
        f"  programming; otherwise use DIAGRAM with diagram_prompt.\n"
        f"- Slide 7 bullets MUST alternate Wrong/Correct pairs.\n"
        f"- Slide 9 bullets MUST be full written-out questions (no answers on slide face).\n\n"
        f"QUIZLETS & ASSIGNMENTS:\n"
        f"- Quizlets: minimum {ctx.min_quizlets}. Mix MCQ and SHORT_ANSWER.\n"
        f"  MCQ: 4 options A/B/C/D; answer_key: {{\"correct\": \"<label>\"}}.\n"
        f"  SHORT_ANSWER: answer_key: {{\"answer_points\": [\"point 1\", ...]}}.\n"
        f"  NEVER embed answers in slide content.\n"
        f"- Assignments: 2-4 tasks. At least 1 CLASSWORK and 1 HOMEWORK.\n"
        f"  Each needs model_answer and rubric with 3+ criteria.\n"
        f"- Teaching plan: 1+ row per major topic.\n"
        f"- Lesson plans: 1 session per major topic.\n"
        f"- Resources: 4-6 items. No author names, DOIs, or ISBNs.\n"
        f"{custom_clause}\n"
        f"Return JSON matching the schema exactly."
    )

    return system, user


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()


def _gemini_safe_schema(schema: dict) -> dict:
    """Recursively remove 'additionalProperties' from a JSON Schema dict.

    The Gemini API rejects schemas that contain additionalProperties (even
    when set to false).  Pydantic v2 includes it by default.  Stripping it
    is safe because Gemini enforces its own structural constraints.
    """
    schema.pop("additionalProperties", None)
    for key in ("properties", "$defs", "definitions"):
        val = schema.get(key)
        if isinstance(val, dict):
            for sub in val.values():
                if isinstance(sub, dict):
                    _gemini_safe_schema(sub)
    items = schema.get("items")
    if isinstance(items, dict):
        _gemini_safe_schema(items)
    return schema


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class CourseKitProvider(Protocol):
    async def generate_kit(
        self,
        ctx: KitGenerationContext,
    ) -> KitGenerationResult: ...


# ---------------------------------------------------------------------------
# Shared result builder — converts _KitAI → KitGenerationResult
# ---------------------------------------------------------------------------

def _enrich_slide_content(slide: _SlideAI) -> dict[str, Any]:
    """Return the content dict for a slide, applying slide_type inference if needed."""
    content = slide.content
    if not content.slide_type:
        content.slide_type = _infer_slide_type(
            slide_number=slide.slide_number,
            title=slide.title,
            has_code=bool(content.code_snippet),
        )
    return content.model_dump(exclude_none=True)


def _build_result(parsed: _KitAI, model_used: str, prompt_hash: str) -> KitGenerationResult:
    return KitGenerationResult(
        slides=[
            SlideAI(
                slide_number=s.slide_number,
                title=s.title,
                content=_enrich_slide_content(s),
                speaker_notes=s.speaker_notes,
                bloom_level=s.bloom_level,
                co_reference=s.co_reference,
            )
            for s in parsed.slides
        ],
        quizlets=[
            QuizletAI(
                question_number=q.question_number,
                question_text=q.question_text,
                question_type=q.question_type,
                options=[o.model_dump() for o in q.options],
                answer_key=q.answer_key,
                answer_explanation=q.answer_explanation,
                bloom_level=q.bloom_level,
                co_reference=q.co_reference,
            )
            for q in parsed.quizlets
        ],
        assignments=[
            AssignmentAI(
                assignment_number=a.assignment_number,
                title=a.title,
                assignment_type=a.assignment_type,
                question_text=a.question_text,
                complexity_level=a.complexity_level,
                current_events_toggle=a.current_events_toggle,
                model_answer=a.model_answer,
                rubric=[r.model_dump() for r in a.rubric],
                bloom_level=a.bloom_level,
                co_reference=a.co_reference,
            )
            for a in parsed.assignments
        ],
        teaching_plan=[w.model_dump() for w in parsed.teaching_plan],
        lesson_plans=[ls.model_dump() for ls in parsed.lesson_plans],
        resources=[r.model_dump(exclude_none=True) for r in parsed.resources],
        model_used=model_used,
        prompt_hash=prompt_hash,
    )


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------

class GeminiCourseKitProvider:

    async def generate_kit(
        self,
        ctx: KitGenerationContext,
    ) -> KitGenerationResult:
        # Deferred import — module loads cleanly in tests that mock this provider.
        from google import genai
        from google.genai import types

        system, user = _build_prompt(ctx)
        phash = _prompt_hash(system, user)

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_gemini_safe_schema(_KitAI.model_json_schema()),
            temperature=0.35,
            system_instruction=system,
        )

        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=user,
            config=config,
        )

        raw = getattr(response, "text", None)
        if not raw:
            raise CourseKitAIBlockedError(
                "Gemini returned an empty or blocked response — "
                "check safety filters and API quota."
            )

        try:
            parsed = _KitAI.model_validate_json(raw)
        except Exception as exc:
            raise CourseKitAIParseError(
                f"Gemini response did not match the expected schema: {exc}\n"
                f"Raw response (first 500 chars): {raw[:500]}"
            ) from exc

        salvage_warns = _salvage_parsed_kit(parsed)
        if salvage_warns:
            logger.warning(
                "m03.gemini: salvaged %d issue(s): %s", len(salvage_warns), salvage_warns
            )

        if not parsed.slides:
            raise CourseKitAIValidationError(
                "Gemini returned 0 valid slides after normalization; "
                "cannot commit a course kit without content."
            )

        violations = _validate_result(parsed, ctx)
        if violations:
            hard = [v for v in violations if not _is_soft_violation(v)]
            soft = [v for v in violations if _is_soft_violation(v)]
            if soft:
                logger.warning(
                    "m03.gemini: soft violations — proceeding with %d slides, "
                    "%d quizlets: %s",
                    len(parsed.slides), len(parsed.quizlets), soft,
                )
            if hard:
                raise CourseKitAIValidationError(
                    "Gemini AI response failed business-rule validation:\n"
                    + "\n".join(f"  - {v}" for v in hard)
                )

        return _build_result(parsed, settings.GEMINI_MODEL, phash)


# ---------------------------------------------------------------------------
# Groq response normalizer
# ---------------------------------------------------------------------------

def _normalize_groq_kit_response(raw: str) -> dict[str, Any]:
    """
    Map observed Groq output aliases to canonical _KitAI field names.

    Called ONLY for Groq responses; the Gemini path is untouched.
    Raises CourseKitAIParseError if the raw string is not valid JSON.

    Defensive contract
    ------------------
    - Never raises TypeError or AttributeError on malformed AI output.
    - null / non-list collections are coerced to [].
    - Non-dict items within slides / quizlets / assignments are silently dropped.
    - Quizlets without question_text (and no recognised alias) are dropped.
    - Assignments without title AND question_text are dropped.
    - options: null / non-list → [] before iteration (fixes TypeError).
    - Returns a dict safe to pass to _KitAI.model_validate().

    Aliases handled
    ---------------
    Top-level:
      slide_deck / slides_list / presentation_slides  -> slides
      quiz_questions / questions / quiz_items         -> quizlets
      tasks / exercises / assessment_tasks            -> assignments
      weekly_plan / course_schedule                   -> teaching_plan
      sessions / class_sessions                       -> lesson_plans
      references / study_materials                    -> resources

    Per slide:
      content (str/list)     -> {"bullets": [...]}
    Per quizlet:
      question/prompt/text   -> question_text
      answer/correct_answer  -> answer_key  (string → {"correct": ...})
      options: list[str]     -> list[{label, text}]
    Per assignment:
      task                   -> title
      question/prompt        -> question_text
      solution               -> model_answer
    """
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CourseKitAIParseError(
            f"Groq kit response is not valid JSON: {exc}\n"
            f"Raw (first 300 chars): {raw[:300]}"
        ) from exc

    if not isinstance(data, dict):
        raise CourseKitAIParseError(
            f"Groq kit response is not a JSON object (got {type(data).__name__})."
        )

    # --- flatten nested topic-slides structure ---
    # Groq sometimes returns {"topics": [{"topic_name": "...", "slides": [...]}]}
    # when the prompt has a per-topic checklist.  Flatten to a top-level slides list.
    if "topics" in data and not isinstance(data.get("slides"), list):
        all_topic_slides: list[dict] = []
        for topic_block in (data.get("topics") or []):
            if isinstance(topic_block, dict):
                topic_slide_list = topic_block.get("slides") or []
                if isinstance(topic_slide_list, list):
                    all_topic_slides.extend(
                        s for s in topic_slide_list if isinstance(s, dict)
                    )
        if all_topic_slides:
            data["slides"] = all_topic_slides
            logger.debug(
                "m03.normalizer: flattened %d slides from nested topic structure",
                len(all_topic_slides),
            )

    # --- top-level key aliases ---
    for alias in ("slide_deck", "slides_list", "presentation_slides"):
        if alias in data and "slides" not in data:
            data["slides"] = data.pop(alias)
            break

    for alias in ("quiz_questions", "questions", "quiz_items"):
        if alias in data and "quizlets" not in data:
            data["quizlets"] = data.pop(alias)
            break

    for alias in ("tasks", "exercises", "assessment_tasks"):
        if alias in data and "assignments" not in data:
            data["assignments"] = data.pop(alias)
            break

    for alias in (
        "weekly_plan", "course_schedule", "teaching_schedule",
        "weekly_teaching_plan", "course_plan", "schedule",
        "unit_schedule", "weekly_schedule",
    ):
        if alias in data and "teaching_plan" not in data:
            data["teaching_plan"] = data.pop(alias)
            break

    for alias in ("sessions", "class_sessions"):
        if alias in data and "lesson_plans" not in data:
            data["lesson_plans"] = data.pop(alias)
            break

    for alias in ("references", "study_materials"):
        if alias in data and "resources" not in data:
            data["resources"] = data.pop(alias)
            break

    # Coerce null / non-list top-level collections to [] so iteration never crashes.
    for _field in ("slides", "quizlets", "assignments", "teaching_plan", "lesson_plans", "resources"):
        if not isinstance(data.get(_field), list):
            data[_field] = []

    # --- slide normalization ---
    valid_slides: list[dict] = []
    for i, slide in enumerate(data["slides"]):
        if not isinstance(slide, dict):
            logger.warning("m03.normalizer: dropped non-dict slide at index %d", i)
            continue
        if not slide.get("slide_number"):
            slide["slide_number"] = i + 1
        # Ensure title meets _SlideAI min_length=2
        title = slide.get("title")
        if not title or len(str(title)) < 2:
            slide["title"] = f"Slide {i + 1}"
        # Normalize content to a dict (Groq returns str, list, or dict)
        content = slide.get("content")
        if isinstance(content, str):
            slide["content"] = {"bullets": [content]}
        elif isinstance(content, list):
            slide["content"] = {"bullets": [str(x) for x in content if x]}
        elif not isinstance(content, dict):
            slide["content"] = {}
        content_dict = slide["content"]

        # bullets: str → list[str], coerce items to str
        bv = content_dict.get("bullets")
        if isinstance(bv, str):
            content_dict["bullets"] = [bv] if bv else []
        elif not isinstance(bv, list):
            content_dict["bullets"] = []
        content_dict["bullets"] = [str(b) for b in content_dict["bullets"] if b]

        # Hoist bullets from slide-level — Groq often places them outside the content object.
        # Also handle common aliases (points, body_points, slide_points, learning_points).
        if not content_dict.get("bullets"):
            for _bkey in ("bullets", "points", "body_points", "slide_points",
                          "learning_points", "content_points", "teaching_points",
                          "slide_body", "body"):
                _bval = slide.get(_bkey)
                if _bval is None:
                    continue
                if isinstance(_bval, str) and _bval.strip():
                    content_dict["bullets"] = [_bval.strip()]
                elif isinstance(_bval, list):
                    content_dict["bullets"] = [str(x) for x in _bval if x]
                if content_dict.get("bullets"):
                    break

        # key_concepts: str → list[str]
        kc = content_dict.get("key_concepts")
        if isinstance(kc, str):
            content_dict["key_concepts"] = [kc] if kc else []
        elif not isinstance(kc, list):
            content_dict["key_concepts"] = []
        # Hoist slide-level key_concepts when Groq puts them outside the content object
        slide_kc = slide.get("key_concepts")
        if slide_kc is not None and not content_dict.get("key_concepts"):
            if isinstance(slide_kc, str):
                content_dict["key_concepts"] = [slide_kc] if slide_kc else []
            elif isinstance(slide_kc, list):
                content_dict["key_concepts"] = slide_kc

        # definitions / examples: str → list[str] or hoist from slide-level
        for fld in ("definitions", "examples"):
            val = content_dict.get(fld)
            if isinstance(val, str):
                content_dict[fld] = [val] if val else []
            elif not isinstance(val, list):
                content_dict[fld] = []
            slide_val = slide.get(fld)
            if slide_val is not None and not content_dict.get(fld):
                if isinstance(slide_val, str):
                    content_dict[fld] = [slide_val] if slide_val else []
                elif isinstance(slide_val, list):
                    content_dict[fld] = slide_val

        # slide_type: hoist from slide-level if Groq puts it outside content
        if "slide_type" not in content_dict:
            for alias in ("slide_type", "type", "slide_category", "category"):
                val = slide.get(alias)
                if val and isinstance(val, str):
                    content_dict["slide_type"] = val.upper()
                    break

        # Normalize Groq aliases for enhanced slide types to canonical values.
        raw_st = content_dict.get("slide_type")
        if isinstance(raw_st, str):
            content_dict["slide_type"] = _GROQ_SLIDE_TYPE_ALIASES.get(
                raw_st.upper(), raw_st.upper()
            )

        # Title-based slide_type correction.
        # Groq sometimes assigns the wrong type (e.g., CODE for a WORKED_EXAMPLE
        # slide).  Override only when the title strongly signals a specific type.
        _title_lower = slide.get("title", "").lower()
        if _title_lower.startswith("worked example") or "worked example:" in _title_lower:
            content_dict["slide_type"] = "WORKED_EXAMPLE"
        elif "common mistake" in _title_lower or "mistakes:" in _title_lower:
            content_dict["slide_type"] = "COMMON_MISTAKES"
        elif "checkpoint" in _title_lower or _title_lower.startswith("quiz"):
            content_dict["slide_type"] = "QUIZ"

        # Hoist content-level fields that Groq places at the slide level instead
        # of inside the nested content dict.
        for _cf in (
            "teaching_notes", "student_summary", "classroom_activity",
            "code_snippet", "diagram_prompt", "image_hint",
        ):
            if not content_dict.get(_cf):
                _sv = slide.get(_cf)
                if isinstance(_sv, str) and _sv.strip():
                    content_dict[_cf] = _sv.strip()

        valid_slides.append(slide)
    data["slides"] = valid_slides

    # --- quizlet normalization ---
    valid_quizlets: list[dict] = []
    for i, q in enumerate(data["quizlets"]):
        if not isinstance(q, dict):
            logger.warning("m03.normalizer: dropped non-dict quizlet at index %d", i)
            continue
        if not q.get("question_number"):
            q["question_number"] = i + 1
        # Normalise question_text aliases before the required-field check
        for alias in ("question", "prompt", "text"):
            if alias in q and "question_text" not in q:
                q["question_text"] = q.pop(alias)
                break
        if not q.get("question_text"):
            logger.warning(
                "m03.normalizer: dropped quizlet %d — no question_text", i
            )
            continue
        # Normalize answer_key: string or alternative key names → dict
        if "answer_key" not in q:
            for alias in ("answer", "correct_answer", "correct"):
                if alias in q:
                    raw_ans = q.pop(alias)
                    q["answer_key"] = (
                        {"correct": raw_ans}
                        if not isinstance(raw_ans, dict)
                        else raw_ans
                    )
                    break
        # Normalize MCQ options: null / non-list → [], list[str] → list[{label, text}]
        # KEY FIX: q.get("options", []) returns None when key exists with null value.
        # Use `or []` to handle both missing-key and explicit-null cases.
        options = q.get("options") or []
        if not isinstance(options, list):
            options = []
        normalised_options: list[Any] = []
        for j, opt in enumerate(options):
            if isinstance(opt, str):
                normalised_options.append(
                    {"label": chr(ord("A") + j), "text": opt}
                )
            elif isinstance(opt, dict) and opt.get("text"):
                normalised_options.append(opt)
            # else: skip malformed option entry silently
        q["options"] = normalised_options
        # Ensure MCQ has a non-empty answer_key after all alias normalisation
        q_type = (q.get("question_type") or "MCQ").upper()
        if q_type == "MCQ" and not q.get("answer_key"):
            if normalised_options:
                first = normalised_options[0]
                label = first.get("label", "A") if isinstance(first, dict) else "A"
                q["answer_key"] = {"correct": label}
            else:
                q["answer_key"] = {"correct": "A"}
        valid_quizlets.append(q)
    data["quizlets"] = valid_quizlets

    # --- assignment normalization ---
    valid_assignments: list[dict] = []
    for i, asgn in enumerate(data["assignments"]):
        if not isinstance(asgn, dict):
            logger.warning("m03.normalizer: dropped non-dict assignment at index %d", i)
            continue
        if not asgn.get("assignment_number"):
            asgn["assignment_number"] = i + 1
        if "task" in asgn and "title" not in asgn:
            asgn["title"] = asgn.pop("task")
        if "solution" in asgn and "model_answer" not in asgn:
            asgn["model_answer"] = asgn.pop("solution")
        # Normalize question_text aliases
        for alias in ("question", "prompt", "description"):
            if alias in asgn and "question_text" not in asgn:
                asgn["question_text"] = asgn.pop(alias)
                break
        # Skip only if both title AND question_text are absent
        if not asgn.get("title") and not asgn.get("question_text"):
            logger.warning(
                "m03.normalizer: dropped assignment %d — no title or question_text", i
            )
            continue
        # Ensure title meets _AssignmentAI min_length=3
        if not asgn.get("title") or len(str(asgn.get("title", ""))) < 3:
            asgn["title"] = str(asgn.get("question_text", ""))[:50] or f"Assignment {i + 1}"
        # Ensure question_text exists (fall back to title)
        if not asgn.get("question_text"):
            asgn["question_text"] = str(asgn.get("title", ""))
        # Groq returns rubric as a flat dict OR a list with aliased keys;
        # _RubricAI expects list[{criterion, description, max_marks}]
        rubric = asgn.get("rubric")
        if isinstance(rubric, dict):
            asgn["rubric"] = [
                {"criterion": str(v), "description": "", "max_marks": 5}
                for v in rubric.values() if v
            ]
        elif isinstance(rubric, list):
            for item in rubric:
                if not isinstance(item, dict):
                    continue
                # "criteria" → "criterion"
                if "criteria" in item and "criterion" not in item:
                    item["criterion"] = item.pop("criteria")
                # "weight" (0.0–1.0) → "max_marks" (int)
                if "weight" in item and "max_marks" not in item:
                    try:
                        item["max_marks"] = max(1, round(float(item.pop("weight")) * 10))
                    except (TypeError, ValueError):
                        item.pop("weight", None)
                        item["max_marks"] = 5
                # ensure description exists
                item.setdefault("description", "")
        elif rubric is not None:
            asgn["rubric"] = []
        valid_assignments.append(asgn)
    data["assignments"] = valid_assignments

    # --- teaching_plan list-field normalization ---
    valid_tp: list[dict] = []
    for week in data["teaching_plan"]:
        if not isinstance(week, dict):
            continue
        for fld in ("objectives", "activities"):
            val = week.get(fld)
            if isinstance(val, str):
                week[fld] = [val] if val else []
            elif not isinstance(val, list):
                week[fld] = []
        # co_references: split "CO1, CO3" → ["CO1", "CO3"]
        val = week.get("co_references")
        if isinstance(val, str):
            week["co_references"] = [v.strip() for v in val.split(",") if v.strip()]
        elif not isinstance(val, list):
            week["co_references"] = []
        valid_tp.append(week)
    data["teaching_plan"] = valid_tp

    # --- teaching_plan fallback: synthesise from slides if AI omitted it ---
    if not data["teaching_plan"] and data["slides"]:
        slides = data["slides"]
        chunk = max(1, len(slides) // 4)  # ~4 weeks; at least 1 slide/week
        for week_num, start in enumerate(range(0, len(slides), chunk), 1):
            group = slides[start: start + chunk]
            topic = group[0].get("title", f"Week {week_num} Topics") if group else f"Week {week_num}"
            objectives = []
            for sl in group:
                content = sl.get("content") or {}
                bullets = content.get("bullets") or []
                if isinstance(bullets, list):
                    objectives.extend(b for b in bullets[:2] if isinstance(b, str))
            data["teaching_plan"].append({
                "week": week_num,
                "topic": topic,
                "objectives": objectives[:3],
                "activities": [],
                "hours": 3,
                "co_references": [],
            })
        logger.info(
            "m03.normalizer: teaching_plan was empty — synthesised %d week(s) from slides",
            len(data["teaching_plan"]),
        )

    # --- lesson_plans list-field normalization ---
    valid_lp: list[dict] = []
    for lp_i, session in enumerate(data["lesson_plans"]):
        if not isinstance(session, dict):
            continue
        # 'week' is required by _LessonSessionAI; Groq sometimes omits it.
        if not session.get("week"):
            session["week"] = lp_i + 1
        if not session.get("session"):
            session["session"] = lp_i + 1
        for fld in ("objectives", "materials_needed"):
            val = session.get(fld)
            if isinstance(val, str):
                session[fld] = [val] if val else []
            elif not isinstance(val, list):
                session[fld] = []
        # bloom_levels and co_references: split comma-separated strings
        for fld in ("bloom_levels", "co_references"):
            val = session.get(fld)
            if isinstance(val, str):
                session[fld] = [v.strip() for v in val.split(",") if v.strip()]
            elif not isinstance(val, list):
                session[fld] = []
        valid_lp.append(session)
    data["lesson_plans"] = valid_lp

    # --- resources normalization ---
    # Groq sometimes returns resources as a flat list of strings instead of dicts.
    raw_resources = data.get("resources") or []
    valid_resources: list[dict] = []
    for res in raw_resources:
        if isinstance(res, dict):
            valid_resources.append(res)
        elif isinstance(res, str) and res.strip():
            valid_resources.append({"title": res.strip(), "resource_type": "article"})
    data["resources"] = valid_resources

    return data


# ---------------------------------------------------------------------------
# Groq implementation (OpenAI-compatible API)
# ---------------------------------------------------------------------------

class GroqCourseKitProvider:
    """Groq llama-3.3-70b-versatile via the OpenAI-compatible API."""

    async def generate_kit(
        self,
        ctx: KitGenerationContext,
    ) -> KitGenerationResult:
        if not settings.GROQ_API_KEY:
            raise CourseKitAIError(
                "GROQ_API_KEY is not configured — cannot use Groq provider. "
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
                {"role": "user",   "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
        )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise CourseKitAIBlockedError("Groq returned an empty response.")

        # Normalise Groq-specific field aliases before schema validation.
        normalized = _normalize_groq_kit_response(raw)
        logger.debug("Groq kit normalized payload keys: %s", list(normalized.keys()))

        try:
            parsed = _KitAI.model_validate(normalized)
        except CourseKitAIParseError:
            raise
        except Exception as exc:
            raise CourseKitAIParseError(
                f"Groq kit response did not match the expected schema after normalization: {exc}\n"
                f"Normalized keys: {list(normalized.keys())}\n"
                f"Raw response (first 500 chars): {raw[:500]}"
            ) from exc

        salvage_warns = _salvage_parsed_kit(parsed)
        if salvage_warns:
            logger.warning(
                "m03.groq: salvaged %d issue(s): %s", len(salvage_warns), salvage_warns
            )

        if not parsed.slides:
            raise CourseKitAIValidationError(
                "Groq returned 0 valid slides after normalization; "
                "cannot commit a course kit without content."
            )

        violations = _validate_result(parsed, ctx)
        if violations:
            hard = [v for v in violations if not _is_soft_violation(v)]
            soft = [v for v in violations if _is_soft_violation(v)]
            if soft:
                logger.warning(
                    "m03.groq: soft violations — proceeding with %d slides, "
                    "%d quizlets: %s",
                    len(parsed.slides), len(parsed.quizlets), soft,
                )
            if hard:
                raise CourseKitAIValidationError(
                    "Groq AI kit response failed business-rule validation:\n"
                    + "\n".join(f"  - {v}" for v in hard)
                )

        return _build_result(parsed, settings.GROQ_MODEL, phash)


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


class FallbackCourseKitProvider:
    """
    Tries Gemini first.  Falls back to Groq only on quota / rate-limit errors;
    all other Gemini errors propagate normally so bugs are not silently swallowed.
    """

    def __init__(self) -> None:
        self._gemini = GeminiCourseKitProvider()
        self._groq   = GroqCourseKitProvider()

    async def generate_kit(
        self,
        ctx: KitGenerationContext,
    ) -> KitGenerationResult:
        try:
            result = await self._gemini.generate_kit(ctx)
            logger.info("M03 AI provider used: gemini (model=%s)", settings.GEMINI_MODEL)
            return result
        except CourseKitAIBlockedError as exc:
            if not _is_gemini_quota_error(exc):
                raise
            logger.warning(
                "M03 Gemini quota / safety block (%s) — falling back to Groq.", exc
            )
        except Exception as exc:
            if not _is_gemini_quota_error(exc):
                raise
            logger.warning(
                "M03 Gemini quota error (%s) — falling back to Groq.", exc
            )

        result = await self._groq.generate_kit(ctx)
        logger.info("M03 AI provider used: groq (model=%s)", settings.GROQ_MODEL)
        return result


# ---------------------------------------------------------------------------
# Factory — driven by settings.AI_PROVIDER
# ---------------------------------------------------------------------------

_PROVIDER_MAP: dict[str, type] = {
    "gemini":   GeminiCourseKitProvider,
    "groq":     GroqCourseKitProvider,
    "fallback": FallbackCourseKitProvider,
}


def get_kit_provider() -> CourseKitProvider:
    provider_cls = _PROVIDER_MAP.get(settings.AI_PROVIDER)
    if provider_cls is None:
        raise ValueError(
            f"Unknown AI_PROVIDER '{settings.AI_PROVIDER}'. "
            f"Must be one of: {sorted(_PROVIDER_MAP)}"
        )
    return provider_cls()
