from __future__ import annotations

import dataclasses
import hashlib
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.config import settings


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
    outcomes:   list[dict]  # keys: code, description, bloom_level, display_order
    courses:    list[dict]  # keys: code, title, credits, semester, is_elective,
                            #       hours_lecture, hours_tutorial, hours_practical,
                            #       description, prerequisite_codes
    model_used: str
    prompt_hash: str        # SHA-256 of sent prompt — stored in AuditLog


# ---------------------------------------------------------------------------
# Private Pydantic models — used only as Gemini response_schema
# ---------------------------------------------------------------------------

class _OutcomeAI(BaseModel):
    code:          str
    description:   str
    bloom_level:   str   # Remember | Understand | Apply | Analyse | Evaluate | Create
    display_order: int


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
        "You are an expert academic curriculum designer for Indian universities. "
        "You create semester-wise program structures that comply with UGC and AICTE norms: "
        "balanced credit loads per semester, at least 20% elective courses, "
        "course credits between 1 and 6, and acyclic prerequisite chains. "
        "Programme Outcomes must align with NBA/NAAC accreditation criteria. "
        "Return only valid JSON matching the provided schema — no prose, no markdown fences."
    )

    outcomes_clause = ""
    if ctx.existing_outcome_codes:
        codes = ", ".join(ctx.existing_outcome_codes)
        outcomes_clause = (
            f"\nExisting Programme Outcome codes (reuse these, extend if needed): {codes}."
        )

    hint_clause = (
        f"\nAdditional guidance from the Dean: {ctx.prompt_hint}"
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
        f"Hard constraints:\n"
        f"- Distribute {ctx.total_credits} credits across "
        f"{ctx.duration_years * 2} semesters with no semester below 12 or above 30 credits.\n"
        f"- At least 20% of courses must be elective (is_elective: true).\n"
        f"- Each course credit must be between 1 and 6.\n"
        f"- prerequisite_codes must only reference codes of other courses in the same list.\n"
        f"- bloom_level must be exactly one of: "
        f"Remember, Understand, Apply, Analyse, Evaluate, Create.\n"
        f"- Return the full structure as JSON matching the schema exactly."
    )

    return system, user


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------

class GeminiStructureProvider:

    async def generate_structure(
        self,
        ctx: ProgramGenerationContext,
    ) -> ProgramStructureResult:
        # Import deferred so module loads cleanly even if google-genai is absent
        # during test runs that mock this provider entirely.
        from google import genai
        from google.genai import types

        system, user = _build_prompt(ctx)
        phash = _prompt_hash(system, user)

        # Client instantiated per-call — avoids fork-safety issues in Celery workers.
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
            prompt_hash=phash,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_structure_provider() -> ProgramStructureProvider:
    return GeminiStructureProvider()
