from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, field_validator, model_validator

from app.config import settings

logger = logging.getLogger("vidya.m01.ai_provider")


# ---------------------------------------------------------------------------
# IO dataclasses (no ORM dependency — built by service layer from ORM objects)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ProgramGenerationContext:
    degree_type:            str
    department:             str
    duration_years:         int
    total_credits:          int
    prompt_hint:            str | None
    existing_outcome_codes: list[str]   # PO codes already saved; AI reuses + extends
    ai_instructions:        str | None = None  # persisted curriculum design instructions


@dataclasses.dataclass
class ProgramStructureResult:
    outcomes:      list[dict]  # keys: code, description, bloom_level, display_order
    courses:       list[dict]  # keys: code, title, credits, semester, course_type,
                               #       is_elective, hours_lecture, hours_tutorial,
                               #       hours_practical, description, prerequisite_codes
    model_used:    str
    provider_name: str         # "gemini" | "groq" | "deepseek"
    prompt_hash:   str         # SHA-256 of sent prompt — stored in AuditLog


# ---------------------------------------------------------------------------
# Private Pydantic models — used as response schema
# ---------------------------------------------------------------------------

_VALID_BLOOM = frozenset(
    {"Remember", "Understand", "Apply", "Analyse", "Evaluate", "Create"}
)

_VALID_COURSE_TYPES = frozenset(
    {"THEORY", "LAB", "PROJECT", "INTERNSHIP", "SEMINAR"}
)


class _OutcomeAI(BaseModel):
    code:          str
    description:   str
    bloom_level:   str = "Apply"
    display_order: int

    @field_validator("bloom_level", mode="before")
    @classmethod
    def coerce_bloom_level(cls, v: object) -> str:
        """Default to 'Apply' when the field is missing, blank, or unrecognised."""
        s = str(v).strip() if v else ""
        return s if s in _VALID_BLOOM else "Apply"


def _infer_course_type_from_title(title: str) -> str:
    """Best-guess course_type from the title when the AI omits or mistags it.

    Keeps non-final-semester lab pairing and final-semester project/internship
    composition correct even when a provider forgets to set course_type —
    falling back to a blind 'THEORY' default would misclassify any course
    titled e.g. 'Data Structures Lab' and defeat the compliance checks.
    """
    t = title.lower()
    if "internship" in t:
        return "INTERNSHIP"
    if "project" in t:
        return "PROJECT"
    if "lab" in t or "laboratory" in t:
        return "LAB"
    if "seminar" in t:
        return "SEMINAR"
    return "THEORY"


class _CourseAI(BaseModel):
    code:                 str
    title:                str
    credits:              int
    semester:             int
    course_type:          str | None = None   # THEORY|LAB|PROJECT|INTERNSHIP|SEMINAR
    is_elective:          bool
    # Required when is_elective is true — names the elective PAPER this course is
    # one alternative of ("Elective 1", "Elective 2", ...). A semester holds
    # several independent papers; the student takes them all, choosing exactly one
    # alternative inside each. Two courses share this name iff they are
    # alternatives of the same paper.
    elective_basket_name: str | None = None
    hours_lecture:        int
    hours_tutorial:       int
    hours_practical:      int
    description:          str
    prerequisite_codes:   list[str]   # course codes within this program; [] if none

    @model_validator(mode="before")
    @classmethod
    def normalize_code_alias(cls, data: object) -> object:
        """Some providers (and prompt variations) emit 'course_code' instead
        of the expected 'code'. Accept either, normalized to 'code', so a
        provider's field-name choice never fails program generation --
        applies uniformly to every provider since all of them (Gemini
        directly, Groq/DeepSeek via the shared normalizer) validate courses
        through this same model."""
        if isinstance(data, dict) and not data.get("code") and data.get("course_code"):
            data = {**data, "code": data["course_code"]}
        return data

    @model_validator(mode="after")
    def coerce_course_type(self) -> _CourseAI:
        """Infer course_type from title when missing, blank, or unrecognised.

        Deliberately has no non-null default on the field itself — a default
        of "THEORY" would already satisfy Pydantic before this validator runs,
        silently skipping inference for any provider (e.g. Gemini's schema-
        enforced JSON) that omits the field rather than passing it through
        the Groq/DeepSeek text normalizer.
        """
        s = self.course_type.strip().upper() if self.course_type else ""
        self.course_type = s if s in _VALID_COURSE_TYPES else _infer_course_type_from_title(self.title)
        return self


class _ProgramStructureAI(BaseModel):
    outcomes: list[_OutcomeAI]
    courses:  list[_CourseAI]


# ---------------------------------------------------------------------------
# Provider protocol  (structural typing — no inheritance required)
# ---------------------------------------------------------------------------

@runtime_checkable
class ProgramStructureProvider(Protocol):
    async def generate_structure(
        self,
        ctx: ProgramGenerationContext,
    ) -> ProgramStructureResult: ...


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_prompt(ctx: ProgramGenerationContext) -> tuple[str, str]:
    system = (
        "You are an expert academic curriculum designer. "
        "You create semester-wise program structures following outcome-based education principles "
        "and Bloom's revised taxonomy, with balanced credit loads and acyclic prerequisite chains. "
        "Adapt the structure, credit distribution, elective ratio, and programme outcomes "
        "to the university framework specified in the generation guidance — this may include "
        "NEP 2020, VTU norms, autonomous university models, NBA/NAAC outcome-based frameworks, "
        "industry-integrated, research-oriented, practical-oriented, or skill-based curricula. "
        "When no specific framework is given, apply broadly accepted academic norms. "
        "Return only valid JSON matching the provided schema — no prose, no markdown fences."
    )

    outcomes_clause = ""
    if ctx.existing_outcome_codes:
        codes = ", ".join(ctx.existing_outcome_codes)
        outcomes_clause = (
            f"\nExisting Programme Outcome codes (reuse these, extend if needed): {codes}."
        )

    hint_clause = (
        f"\nUniversity framework / generation guidance: {ctx.prompt_hint}"
        if ctx.prompt_hint else ""
    )

    instructions_clause = (
        f"\nCurriculum design instructions (MANDATORY — follow exactly):\n{ctx.ai_instructions}"
        if ctx.ai_instructions else ""
    )

    user = (
        f"Design a complete program structure for:\n"
        f"  Degree type   : {ctx.degree_type}\n"
        f"  Department    : {ctx.department}\n"
        f"  Duration      : {ctx.duration_years} year(s) "
        f"({ctx.duration_years * 2} semesters)\n"
        f"  Total credits : {ctx.total_credits}\n"
        f"{outcomes_clause}"
        f"{hint_clause}"
        f"{instructions_clause}\n\n"
        f"Guidelines (adapt to the university framework and instructions above):\n"
        f"- Distribute {ctx.total_credits} credits across "
        f"{ctx.duration_years * 2} semesters with balanced per-semester loads.\n"
        f"- Each course credit should typically be between 1 and 6 "
        f"unless the curriculum instructions require otherwise (e.g. projects 2-20 credits).\n"
        f"- Every course must set course_type to exactly one of: "
        f"THEORY, LAB, PROJECT, INTERNSHIP, SEMINAR.\n"
        f"- Realistic semester composition — this is the most common source of unrealistic "
        f"output, follow it precisely. There are {ctx.duration_years * 2} semesters total; "
        f"they fall into exactly three fixed zones — do not invent projects, internships, "
        f"or electives outside these zones:\n"
        f"    * ZONE A — every semester from 1 to {ctx.duration_years * 2 - 2} (core-only): "
        f"generate 5-7 THEORY courses, all with is_elective: false. Identify the 2 (up to 3 "
        f"for longer semesters) most hands-on / practical THEORY courses in that semester — "
        f"typically programming, systems, data structures, databases, software engineering, "
        f"web development, electronics, or other lab-based subjects — and for EACH of those "
        f"add a matching LAB course with course_type LAB whose title is exactly the theory "
        f"course's title + ' Lab' (e.g. 'Computer Systems' -> 'Computer Systems Lab', "
        f"'Programming Fundamentals' -> 'Programming Fundamentals Lab', 'Data Structures' -> "
        f"'Data Structures Lab', 'Database Systems' -> 'Database Systems Lab', 'Software "
        f"Engineering' -> 'Software Engineering Lab', 'Web Development' -> 'Web Development "
        f"Lab'). Purely foundational/non-practical subjects (e.g. Mathematics, Communication "
        f"Skills, Aptitude, humanities, management) must stay THEORY-only — do not invent a "
        f"lab for them. Example realistic Semester 1 for a computing programme (MCA/BCA/"
        f"B.Tech-style): 5 THEORY courses (e.g. Computer Systems, Programming Fundamentals, "
        f"Mathematics, Communication Skills, Aptitude) plus exactly 2 LAB courses pairing the "
        f"practical ones (Computer Systems Lab, Programming Fundamentals Lab). Never generate "
        f"a semester of only THEORY courses with zero labs. NO project, internship, or "
        f"elective course belongs in this zone.\n"
        f"    * ZONE B — semester {ctx.duration_years * 2 - 1} only (core + mini project + "
        f"elective papers): generate 3-5 core THEORY/LAB courses (is_elective: false) "
        f"PLUS exactly one Mini Project course (course_type PROJECT, title containing "
        f"'Mini Project', credits 2-4, is_elective: false) PLUS 2-4 ELECTIVE PAPERS.\n"
        f"      An elective paper is ONE curriculum course. The student takes every paper "
        f"in the semester, choosing exactly one alternative inside each. Three papers of 3 "
        f"credits therefore contribute 9 credits to the semester, not 3.\n"
        f"      Name the papers exactly 'Elective 1', 'Elective 2', 'Elective 3' (and so on) "
        f"and put that name in elective_basket_name. Each paper needs its OWN 2-5 alternative "
        f"courses, and the alternatives of one paper must be a coherent, distinct area from "
        f"the alternatives of the others. Every alternative inside one paper must carry the "
        f"same credits. Example for one semester:\n"
        f"        Elective 1 -> Artificial Intelligence, Machine Learning\n"
        f"        Elective 2 -> Data Mining, Data Science, Business Intelligence\n"
        f"        Elective 3 -> Business Management, Social Media Marketing\n"
        f"      Do NOT put every alternative under a single shared name — that would collapse "
        f"three papers into one and lose two thirds of the elective credits. Every elective "
        f"course MUST set is_elective: true and a non-empty elective_basket_name; every "
        f"non-elective course MUST leave elective_basket_name null.\n"
        f"    * ZONE C — semester {ctx.duration_years * 2} (final, internship + major "
        f"project only): contains ONLY exactly one PROJECT course (title containing 'Major "
        f"Project', credits 6-20, is_elective: false) and exactly one INTERNSHIP course "
        f"(title containing 'Internship', is_elective: false) — no THEORY, LAB, SEMINAR, or "
        f"elective courses in this zone.\n"
        f"- prerequisite_codes must only reference codes of other courses in the same list.\n"
        f"- bloom_level must be exactly one of: "
        f"Remember, Understand, Apply, Analyse, Evaluate, Create.\n"
        f"- Return the full structure as JSON matching the schema exactly."
    )

    return system, user


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()


# ---------------------------------------------------------------------------
# OpenAI-compatible response normalizer (shared by Groq and DeepSeek)
# ---------------------------------------------------------------------------

def _infer_semester(code: str) -> int:
    """
    Extract semester from the first digit sequence in a course code.
    CS501 -> 5, MATH201 -> 2, PHY101 -> 1, CS1001 -> 1.
    Returns 1 when no usable digit is found.
    """
    import re
    m = re.search(r"(\d+)", code)
    if m:
        first_digit = int(m.group(1)[0])
        return first_digit if first_digit > 0 else 1
    return 1


def _synthesise_fallback_outcomes(
    department: str = "",
    degree_type: str = "",
) -> list[dict[str, Any]]:
    """Return 4 generic programme outcomes when the provider omits them entirely."""
    discipline = f"{degree_type} {department}".strip() or "the discipline"
    return [
        {
            "code": "PO1",
            "description": (
                f"Apply core {discipline} knowledge and principles "
                "to analyse and solve domain-specific problems."
            ),
            "bloom_level": "Apply",
            "display_order": 1,
        },
        {
            "code": "PO2",
            "description": (
                f"Design and implement effective {discipline} solutions "
                "using modern tools and methodologies."
            ),
            "bloom_level": "Create",
            "display_order": 2,
        },
        {
            "code": "PO3",
            "description": (
                "Evaluate technical solutions critically against quality, "
                "ethical, and sustainability criteria."
            ),
            "bloom_level": "Evaluate",
            "display_order": 3,
        },
        {
            "code": "PO4",
            "description": (
                "Communicate findings effectively and collaborate "
                "in multidisciplinary team environments."
            ),
            "bloom_level": "Understand",
            "display_order": 4,
        },
    ]


def _normalize_openai_compatible_structure(
    raw: str,
    provider: str = "openai-compatible",
    *,
    department: str = "",
    degree_type: str = "",
) -> dict[str, Any]:
    """
    Normalise JSON from any OpenAI-compatible provider (Groq, DeepSeek, etc.).

    Handles common response shape variations:
      - {"program_structure": {...}}  wrapper unwrap
      - semester-wise course lists  (semesters / semester_wise_courses)
      - top-level key aliases       (programme_outcomes, program_courses, …)
      - missing outcomes            → synthesise 4 fallback POs
      - missing bloom_level         → "Apply"  (also enforced by _OutcomeAI validator)
      - missing / aliased course fields
    """
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{provider} response is not valid JSON: {exc}\n"
            f"Raw (first 300 chars): {raw[:300]}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"{provider} response is not a JSON object (got {type(data).__name__})."
        )

    # --- unwrap program_structure wrapper ---
    if "program_structure" in data and isinstance(data["program_structure"], dict):
        data = data["program_structure"]

    # --- flatten semester-wise courses ---
    _sem_key = None
    if "semesters" in data and "courses" not in data:
        _sem_key = "semesters"
    elif "semester_wise_courses" in data and "courses" not in data:
        _sem_key = "semester_wise_courses"

    if _sem_key is not None:
        flat: list[Any] = []
        for sem in data.pop(_sem_key):
            if not isinstance(sem, dict):
                continue
            sem_num = sem.get("semester_number") or sem.get("semester") or 1
            for c in sem.get("courses", []):
                if isinstance(c, dict) and not c.get("semester"):
                    c["semester"] = int(sem_num)
                flat.append(c)
        data["courses"] = flat

    # --- top-level key aliases ---
    for alias in ("programme_outcomes", "program_outcomes"):
        if alias in data and "outcomes" not in data:
            data["outcomes"] = data.pop(alias)
            break
    for alias in ("program_courses", "course_list"):
        if alias in data and "courses" not in data:
            data["courses"] = data.pop(alias)
            break

    # --- synthesise fallback outcomes when provider omits them ---
    if not data.get("outcomes"):
        logger.warning(
            "%s response has no outcomes — synthesising 4 fallback POs "
            "(department=%r, degree_type=%r).",
            provider, department, degree_type,
        )
        data["outcomes"] = _synthesise_fallback_outcomes(department, degree_type)

    # --- outcome normalization ---
    for i, o in enumerate(data.get("outcomes", [])):
        if not isinstance(o, dict):
            continue
        if "display_order" not in o:
            o["display_order"] = o.pop("order", i + 1)
        # Ensure bloom_level is present — _OutcomeAI validator will default it to "Apply"
        if not o.get("bloom_level"):
            o["bloom_level"] = "Apply"

    # --- course normalization ---
    for c in data.get("courses", []):
        if not isinstance(c, dict):
            continue

        # name -> title
        if "title" not in c and "name" in c:
            c["title"] = c.pop("name")

        # course_type aliases and inference — resolved before the credit clamp
        # below, since PROJECT/INTERNSHIP courses use a wider credit range.
        if "course_type" not in c:
            for alias in ("type", "courseType", "course_category"):
                if alias in c:
                    c["course_type"] = c.pop(alias)
                    break
        raw_type = str(c.get("course_type") or "").strip().upper()
        c["course_type"] = (
            raw_type if raw_type in _VALID_COURSE_TYPES
            else _infer_course_type_from_title(str(c.get("title", "")))
        )

        # clamp credits — [2, 20] for project/internship, [1, 6] otherwise.
        # The floor is 2, not 6: a mini-project is legitimately worth 2 credits,
        # and clamping it up to 6 would inflate the semester's total.
        raw_credits = c.get("credits")
        if isinstance(raw_credits, (int, float)):
            is_project_or_internship = c["course_type"] in ("PROJECT", "INTERNSHIP")
            lo, hi = (2, 20) if is_project_or_internship else (1, 6)
            clamped = max(lo, min(hi, int(raw_credits)))
            if clamped != int(raw_credits):
                logger.warning(
                    "%s course %r: credits %s out of range [%d, %d], clamped to %d.",
                    provider, c.get("code", "?"), raw_credits, lo, hi, clamped,
                )
                c["credits"] = clamped

        # infer semester from course code when absent
        if not c.get("semester"):
            c["semester"] = _infer_semester(str(c.get("code", "")))

        # synthesise description when absent
        if not c.get("description"):
            label = c.get("title") or c.get("code", "this course")
            c["description"] = f"Course covering topics in {label}."

        # prerequisite_codes aliases
        if "prerequisite_codes" not in c:
            for alias in ("prerequisites", "prerequisite_course_codes", "prereqs"):
                if alias in c:
                    c["prerequisite_codes"] = c.pop(alias)
                    break
            c.setdefault("prerequisite_codes", [])

        # hours aliases and defaults
        if "hours_practical" not in c:
            for alias in ("hours_lab", "lab_hours", "practical_hours"):
                if alias in c:
                    c["hours_practical"] = c.pop(alias)
                    break
            c.setdefault("hours_practical", 0)
        c.setdefault("hours_lecture", 0)
        c.setdefault("hours_tutorial", 0)

    return data


# Keep old name as alias for backward compatibility with any external callers.
_normalize_groq_structure = _normalize_openai_compatible_structure


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------

class GeminiStructureProvider:

    async def generate_structure(
        self,
        ctx: ProgramGenerationContext,
    ) -> ProgramStructureResult:
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Set it in your .env file."
            )

        from google import genai
        from google.genai import types

        system, user = _build_prompt(ctx)
        phash = _prompt_hash(system, user)

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_ProgramStructureAI.model_json_schema(),
            temperature=0.4,
            system_instruction=system,
        )

        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=user,
            config=config,
        )

        raw = getattr(response, "text", None)
        if not raw:
            raise ValueError(
                "Gemini returned an empty or blocked response — "
                "check safety filters and API quota."
            )

        parsed = _ProgramStructureAI.model_validate_json(raw)

        return ProgramStructureResult(
            outcomes=[o.model_dump() for o in parsed.outcomes],
            courses=[c.model_dump() for c in parsed.courses],
            model_used=settings.GEMINI_MODEL,
            provider_name="gemini",
            prompt_hash=phash,
        )


# ---------------------------------------------------------------------------
# Groq provider (OpenAI-compatible API)
# ---------------------------------------------------------------------------

class GroqStructureProvider:
    """Groq llama-3.3-70b-versatile via the OpenAI-compatible API."""

    async def generate_structure(
        self,
        ctx: ProgramGenerationContext,
    ) -> ProgramStructureResult:
        if not settings.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not configured. Set it in your .env file."
            )

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
            temperature=0.4,
        )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise ValueError("Groq returned an empty response.")

        normalized = _normalize_openai_compatible_structure(
            raw,
            provider="groq",
            department=ctx.department,
            degree_type=ctx.degree_type,
        )

        try:
            parsed = _ProgramStructureAI.model_validate(normalized)
        except Exception as exc:
            raise ValueError(
                f"Groq response did not match the expected schema: {exc}\n"
                f"Raw response (first 500 chars): {raw[:500]}"
            ) from exc

        return ProgramStructureResult(
            outcomes=[o.model_dump() for o in parsed.outcomes],
            courses=[c.model_dump() for c in parsed.courses],
            model_used=settings.GROQ_MODEL,
            provider_name="groq",
            prompt_hash=phash,
        )


# ---------------------------------------------------------------------------
# DeepSeek provider (OpenAI-compatible API)
# ---------------------------------------------------------------------------

class DeepSeekStructureProvider:
    """DeepSeek-V3 via the OpenAI-compatible API."""

    async def generate_structure(
        self,
        ctx: ProgramGenerationContext,
    ) -> ProgramStructureResult:
        if not settings.DEEPSEEK_API_KEY:
            raise ValueError(
                "DEEPSEEK_API_KEY is not configured. Set it in your .env file."
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
                {"role": "user",   "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise ValueError("DeepSeek returned an empty response.")

        normalized = _normalize_openai_compatible_structure(
            raw,
            provider="deepseek",
            department=ctx.department,
            degree_type=ctx.degree_type,
        )

        try:
            parsed = _ProgramStructureAI.model_validate(normalized)
        except Exception as exc:
            raise ValueError(
                f"DeepSeek response did not match the expected schema: {exc}\n"
                f"Raw response (first 500 chars): {raw[:500]}"
            ) from exc

        return ProgramStructureResult(
            outcomes=[o.model_dump() for o in parsed.outcomes],
            courses=[c.model_dump() for c in parsed.courses],
            model_used=settings.DEEPSEEK_MODEL,
            provider_name="deepseek",
            prompt_hash=phash,
        )


# ---------------------------------------------------------------------------
# Fallback provider — Gemini → Groq → DeepSeek
# ---------------------------------------------------------------------------

class FallbackStructureProvider:
    """
    Tries providers in priority order: Gemini → Groq → DeepSeek.

    Each provider is attempted if:
      - its AI_*_ENABLED flag is True, AND
      - its API key is configured.

    Any exception from a provider causes the next provider to be tried.
    Raises RuntimeError only if every enabled+configured provider fails.
    """

    def __init__(self) -> None:
        self._chain: list[tuple[str, ProgramStructureProvider]] = [
            ("gemini",   GeminiStructureProvider()),
            ("groq",     GroqStructureProvider()),
            ("deepseek", DeepSeekStructureProvider()),
        ]

    def _is_available(self, name: str) -> bool:
        if name == "gemini":
            return settings.AI_GEMINI_ENABLED and bool(settings.GEMINI_API_KEY)
        if name == "groq":
            return settings.AI_GROQ_ENABLED and bool(settings.GROQ_API_KEY)
        if name == "deepseek":
            return settings.AI_DEEPSEEK_ENABLED and bool(settings.DEEPSEEK_API_KEY)
        return False

    async def generate_structure(
        self,
        ctx: ProgramGenerationContext,
    ) -> ProgramStructureResult:
        last_exc: Exception | None = None

        for name, provider in self._chain:
            if not self._is_available(name):
                logger.debug("M01 provider=%s skipped (disabled or key not set).", name)
                continue

            try:
                result = await provider.generate_structure(ctx)
                logger.info("provider=%s model=%s", name, result.model_used)
                return result
            except Exception as exc:
                logger.warning(
                    "provider=%s failed (%s: %s) — trying next provider.",
                    name, type(exc).__name__, exc,
                )
                last_exc = exc

        raise RuntimeError(
            "All AI providers failed. Program generation could not be completed. "
            f"Last error: {last_exc}"
        ) from last_exc


# ---------------------------------------------------------------------------
# Factory — driven by settings.AI_PROVIDER
# ---------------------------------------------------------------------------

_PROVIDER_MAP: dict[str, type] = {
    "gemini":   GeminiStructureProvider,
    "groq":     GroqStructureProvider,
    "deepseek": DeepSeekStructureProvider,
    "fallback": FallbackStructureProvider,
}


def get_structure_provider() -> ProgramStructureProvider:
    provider_cls = _PROVIDER_MAP.get(settings.AI_PROVIDER)
    if provider_cls is None:
        raise ValueError(
            f"Unknown AI_PROVIDER '{settings.AI_PROVIDER}'. "
            f"Must be one of: {sorted(_PROVIDER_MAP)}"
        )
    return provider_cls()
