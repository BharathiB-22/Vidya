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

class _SlideContentAI(BaseModel):
    bullets:      list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    image_hint:   str | None = None
    code_snippet: str | None = None


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
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(ctx: KitGenerationContext) -> tuple[str, str]:
    system = (
        "You are an expert academic curriculum designer for Indian universities. "
        "You create complete, unit-level teaching kits aligned with NBA/NAAC "
        "accreditation standards and Bloom's revised taxonomy.\n\n"
        "WHAT TO GENERATE:\n"
        f"  1. Slides: minimum {ctx.min_slides} slides covering all unit topics progressively.\n"
        "     Each slide: slide_number (1-based), title, content (bullets + key_concepts), "
        "speaker_notes, bloom_level, co_reference.\n"
        f"  2. Quizlets: minimum {ctx.min_quizlets} questions (recommend 5).\n"
        "     Each quizlet: question_number (1-based), question_text, question_type "
        "(MCQ or SHORT_ANSWER), options (MCQ only), answer_key (dict), "
        "answer_explanation, bloom_level, co_reference.\n"
        "  3. Assignments: 2-4 tasks (CLASSWORK, HOMEWORK, or CASE_STUDY).\n"
        "     Each: assignment_number, title, assignment_type, question_text, "
        "complexity_level, current_events_toggle, model_answer, rubric (3+ criteria), "
        "bloom_level, co_reference.\n"
        "  4. Teaching plan: weekly breakdown — week, topic, objectives, activities, "
        "hours, co_references.\n"
        "  5. Lesson plans: one session per topic — session, week, duration_minutes, "
        "topic, objectives, opening_activity, main_content, closing_activity, "
        "materials_needed, bloom_levels, co_references.\n"
        "  6. Resources: 4-6 supplemental references — title, resource_type "
        "(video/article/book_chapter/website/tool), url (optional), description.\n\n"
        "STRICT PROHIBITIONS:\n"
        "  - answer_key values MUST ONLY appear in quizlet answer_key fields.\n"
        "  - NEVER embed quiz answers, answer keys, or correct-answer notations "
        "in slide bullets, key_concepts, image_hint, or speaker_notes.\n"
        "  - Do not include author names, DOIs, ISBNs, or publisher names in resources.\n"
        "  - For MCQ: answer_key must be {\"correct\": \"A\"} (or B/C/D).\n"
        "  - For SHORT_ANSWER: answer_key must be "
        "{\"answer_points\": [\"point1\", \"point2\"]}.\n\n"
        "Return only valid JSON matching the provided schema — no prose, no markdown fences."
    )

    topic_lines = "\n".join(f"    - {t}" for t in ctx.unit_topics) or "    (no topics listed)"
    co_lines = "\n".join(
        f"    {co.code} [{co.bloom_level}]: {co.description}"
        for co in ctx.cos
    ) or "    (no COs provided)"

    custom_clause = (
        f"\nAdditional faculty instructions:\n  {ctx.custom_instructions}"
        if ctx.custom_instructions else ""
    )
    tone_str = ctx.tone or "academic"

    user = (
        f"Generate a complete teaching kit for Unit {ctx.unit_number} of:\n"
        f"  Course Code  : {ctx.course_code}\n"
        f"  Course Title : {ctx.course_title}\n"
        f"  Complexity   : {ctx.complexity_level}\n"
        f"  Tone         : {tone_str}\n\n"
        f"Unit Details:\n"
        f"  Unit Number : {ctx.unit_number}\n"
        f"  Unit Title  : {ctx.unit_title}\n"
        f"  Topics      :\n{topic_lines}\n\n"
        f"Course Outcomes (use co_reference field to map slides/quizlets/assignments to COs):\n"
        f"{co_lines}\n\n"
        f"Requirements:\n"
        f"- Slides: minimum {ctx.min_slides}. "
        f"First slide: unit overview. Last slide: summary + next steps.\n"
        f"- Quizlets: minimum {ctx.min_quizlets} (target 5). Mix MCQ and SHORT_ANSWER.\n"
        f"  * MCQ: 4 options labelled A/B/C/D; answer_key: {{\"correct\": \"<label>\"}}.\n"
        f"  * SHORT_ANSWER: answer_key: {{\"answer_points\": [\"key point 1\", ...]}}.\n"
        f"  * CRITICAL: Do NOT put any answer content in slides — answers in answer_key only.\n"
        f"- Assignments: 2-4 tasks. Include at least 1 CLASSWORK and 1 HOMEWORK.\n"
        f"  * Each assignment needs model_answer and a rubric with at least 3 criteria.\n"
        f"  * Set current_events_toggle to true only if question benefits from current affairs.\n"
        f"- Teaching plan: weekly schedule covering all topics (1+ weeks per major topic).\n"
        f"- Lesson plans: one session entry per unique topic.\n"
        f"- Resources: 4-6 items. No author names, DOIs, ISBNs, or publisher names.\n"
        f"{custom_clause}\n"
        f"Return JSON matching the schema exactly."
    )

    return system, user


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()


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

def _build_result(parsed: _KitAI, model_used: str, prompt_hash: str) -> KitGenerationResult:
    return KitGenerationResult(
        slides=[
            SlideAI(
                slide_number=s.slide_number,
                title=s.title,
                content=s.content.model_dump(exclude_none=True),
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
            response_schema=_KitAI.model_json_schema(),
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

        violations = _validate_result(parsed, ctx)
        if violations:
            raise CourseKitAIValidationError(
                "Gemini AI response failed business-rule validation:\n"
                + "\n".join(f"  - {v}" for v in violations)
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
      content (str)          -> {"bullets": [str]}  (wrapped if plain string)

    Per quizlet:
      answer / correct_answer        -> answer_key (wrapped to dict if string)
      options: list[str]             -> list of {label, text} objects

    Per assignment:
      task                  -> title
      solution              -> model_answer
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

    for alias in ("weekly_plan", "course_schedule"):
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

    # --- slide normalization ---
    for i, slide in enumerate(data.get("slides", [])):
        if not isinstance(slide, dict):
            continue
        if not slide.get("slide_number"):
            slide["slide_number"] = i + 1
        # If content is a plain string, wrap it as bullets
        if isinstance(slide.get("content"), str):
            slide["content"] = {"bullets": [slide["content"]]}
        elif not isinstance(slide.get("content"), dict):
            slide["content"] = {}

    # --- quizlet normalization ---
    for i, q in enumerate(data.get("quizlets", [])):
        if not isinstance(q, dict):
            continue
        if not q.get("question_number"):
            q["question_number"] = i + 1
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
        # Normalize MCQ options: list[str] → list[{label, text}]
        options: list[Any] = q.get("options", [])
        normalised_options: list[Any] = []
        for j, opt in enumerate(options):
            if isinstance(opt, str):
                normalised_options.append(
                    {"label": chr(ord("A") + j), "text": opt}
                )
            else:
                normalised_options.append(opt)
        q["options"] = normalised_options

    # --- assignment normalization ---
    for i, asgn in enumerate(data.get("assignments", [])):
        if not isinstance(asgn, dict):
            continue
        if not asgn.get("assignment_number"):
            asgn["assignment_number"] = i + 1
        if "task" in asgn and "title" not in asgn:
            asgn["title"] = asgn.pop("task")
        if "solution" in asgn and "model_answer" not in asgn:
            asgn["model_answer"] = asgn.pop("solution")
        # Groq returns rubric as a flat dict; _RubricAI expects list[{criterion,...}]
        rubric = asgn.get("rubric")
        if isinstance(rubric, dict):
            asgn["rubric"] = [
                {"criterion": str(v), "description": "", "max_marks": 5}
                for v in rubric.values() if v
            ]

    # --- teaching_plan list-field normalization: Groq returns str, model expects list[str] ---
    for week in data.get("teaching_plan", []):
        if not isinstance(week, dict):
            continue
        for field in ("objectives", "activities", "co_references"):
            val = week.get(field)
            if isinstance(val, str):
                week[field] = [val] if val else []

    # --- lesson_plans list-field normalization: Groq returns str, model expects list[str] ---
    for session in data.get("lesson_plans", []):
        if not isinstance(session, dict):
            continue
        for field in ("objectives", "materials_needed", "bloom_levels", "co_references"):
            val = session.get(field)
            if isinstance(val, str):
                session[field] = [val] if val else []

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

        violations = _validate_result(parsed, ctx)
        if violations:
            raise CourseKitAIValidationError(
                "Groq AI kit response failed business-rule validation:\n"
                + "\n".join(f"  - {v}" for v in violations)
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
