from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, field_validator

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


@dataclasses.dataclass
class ProgramStructureResult:
    outcomes:      list[dict]  # keys: code, description, bloom_level, display_order
    courses:       list[dict]  # keys: code, title, credits, semester, is_elective,
                               #       hours_lecture, hours_tutorial, hours_practical,
                               #       description, prerequisite_codes
    model_used:    str
    provider_name: str         # "gemini" | "groq" | "deepseek"
    prompt_hash:   str         # SHA-256 of sent prompt — stored in AuditLog


# ---------------------------------------------------------------------------
# Private Pydantic models — used as response schema
# ---------------------------------------------------------------------------

_VALID_BLOOM = frozenset(
    {"Remember", "Understand", "Apply", "Analyse", "Evaluate", "Create"}
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


class _CourseAI(BaseModel):
    code:               str
    title:              str
    credits:            int
    semester:           int
    is_elective:        bool
    hours_lecture:      int
    hours_tutorial:     int
    hours_practical:    int
    description:        str
    prerequisite_codes: list[str]   # course codes within this program; [] if none


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

    user = (
        f"Design a complete program structure for:\n"
        f"  Degree type   : {ctx.degree_type}\n"
        f"  Department    : {ctx.department}\n"
        f"  Duration      : {ctx.duration_years} year(s) "
        f"({ctx.duration_years * 2} semesters)\n"
        f"  Total credits : {ctx.total_credits}\n"
        f"{outcomes_clause}"
        f"{hint_clause}\n\n"
        f"Guidelines (adapt to the university framework and generation guidance above):\n"
        f"- Distribute {ctx.total_credits} credits across "
        f"{ctx.duration_years * 2} semesters with balanced per-semester loads.\n"
        f"- Include an appropriate mix of core and elective courses; "
        f"mark elective courses with is_elective: true.\n"
        f"- Each course credit should typically be between 1 and 6 "
        f"unless the framework requires otherwise.\n"
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

        # clamp credits to [1, 6]
        raw_credits = c.get("credits")
        if isinstance(raw_credits, (int, float)):
            clamped = max(1, min(6, int(raw_credits)))
            if clamped != int(raw_credits):
                logger.warning(
                    "%s course %r: credits %s out of range [1, 6], clamped to %d.",
                    provider, c.get("code", "?"), raw_credits, clamped,
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
