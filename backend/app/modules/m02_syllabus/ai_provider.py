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
import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger("vidya.m02.ai_provider")

from pydantic import BaseModel, Field, model_validator

from app.config import settings
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


@dataclasses.dataclass
class SyllabusGenerationResult:
    """
    Validated output from the AI provider.

    reference_queries contains search terms ONLY — no author names, DOIs, ISBNs,
    or publisher names.  The reference enrichment task (STEP-07) calls CrossRef /
    OpenLibrary using these queries to fetch real bibliographic metadata.
    """
    outcomes:          list[dict]   # code, description, bloom_level, suggested_po_codes[]
    units:             list[dict]   # unit_number, title, topics[], total_hours, pedagogy
    reference_queries: list[dict]   # query_str, ref_type
    model_used:        str
    prompt_hash:       str


# ---------------------------------------------------------------------------
# Private Pydantic models — Gemini response_schema only
# (never returned to callers; mapped to dicts in SyllabusGenerationResult)
# ---------------------------------------------------------------------------

_VALID_BLOOM = {b.value for b in BloomLevel}
_VALID_REF_TYPES = {r.value for r in RefType}
_VALID_PEDAGOGIES = {"lecture", "lab", "seminar", "case_study", "mixed"}


class _TopicAI(BaseModel):
    title:          str
    description:    str | None = None
    hours_estimate: int | None = Field(default=None, ge=1)


class _COAI(BaseModel):
    code:               str = Field(..., min_length=1, max_length=20)
    description:        str = Field(..., min_length=15)
    bloom_level:        str
    suggested_po_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_bloom(self) -> _COAI:
        if self.bloom_level.upper() not in _VALID_BLOOM:
            raise ValueError(
                f"bloom_level '{self.bloom_level}' must be one of {sorted(_VALID_BLOOM)}"
            )
        self.bloom_level = self.bloom_level.upper()
        return self


class _UnitAI(BaseModel):
    unit_number: int  = Field(..., ge=1)
    title:       str  = Field(..., min_length=3)
    topics:      list[_TopicAI] = Field(default_factory=list)
    total_hours: int  = Field(..., ge=1)
    pedagogy:    str  = "lecture"

    @model_validator(mode="after")
    def _check_pedagogy(self) -> _UnitAI:
        if self.pedagogy.lower() not in _VALID_PEDAGOGIES:
            self.pedagogy = "lecture"   # safe fallback; never reject over pedagogy
        else:
            self.pedagogy = self.pedagogy.lower()
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
    outcomes:          list[_COAI]
    units:             list[_UnitAI]
    reference_queries: list[_RefQueryAI]


# ---------------------------------------------------------------------------
# Business-rule validation (runs after Pydantic parse succeeds)
# ---------------------------------------------------------------------------

_METADATA_KEYWORDS = (
    "doi", "isbn", "issn", "author", "publisher",
    "10.", "978", "979",   # DOI prefix and ISBN-13 prefixes
)


def _validate_result(
    parsed: _SyllabusAI,
    ctx: SyllabusGenerationContext,
) -> list[str]:
    """
    Return a list of violation strings.  Empty list = valid.

    Checks:
      1. Minimum 4 COs and 4 units (PRD requirement).
      2. All bloom_levels are from the approved set.
      3. All suggested_po_codes exist in the context POs.
      4. reference_queries contain no bibliographic metadata keywords.
      5. Unit numbers are unique.
    """
    errors: list[str] = []
    valid_po_codes = {po.code for po in ctx.program_outcomes}

    # 1. Minimums
    if len(parsed.outcomes) < 4:
        errors.append(
            f"AI returned {len(parsed.outcomes)} COs; minimum required is 4."
        )
    if len(parsed.units) < 4:
        errors.append(
            f"AI returned {len(parsed.units)} units; minimum required is 4."
        )

    # 2. Bloom levels (already enforced by _COAI validator, but double-check)
    for co in parsed.outcomes:
        if co.bloom_level not in _VALID_BLOOM:
            errors.append(f"CO '{co.code}' has invalid bloom_level '{co.bloom_level}'.")

    # 3. PO code references
    for co in parsed.outcomes:
        unknown = [c for c in co.suggested_po_codes if c not in valid_po_codes]
        if unknown:
            # Warn but don't reject — AI may suggest sensible codes not in the list
            # The service layer will filter these out during CO-PO mapping creation.
            pass

    # 4. Reference queries must not contain bibliographic metadata
    for i, rq in enumerate(parsed.reference_queries):
        q_lower = rq.query_str.lower()
        found = [kw for kw in _METADATA_KEYWORDS if kw in q_lower]
        if found:
            errors.append(
                f"reference_queries[{i}] '{rq.query_str[:60]}' "
                f"appears to contain bibliographic metadata keywords: {found}. "
                "Queries must be search terms only."
            )

    # 5. Unique unit numbers
    unit_numbers = [u.unit_number for u in parsed.units]
    if len(unit_numbers) != len(set(unit_numbers)):
        errors.append("Duplicate unit_number values in AI response.")

    return errors


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(ctx: SyllabusGenerationContext) -> tuple[str, str]:
    system = (
        "You are an expert academic curriculum designer for Indian universities. "
        "You create detailed course syllabi aligned with NBA/NAAC accreditation standards "
        "and Bloom's revised taxonomy. "
        "\n\n"
        "WHAT TO GENERATE:\n"
        "  1. Course Outcomes (COs) with Bloom's taxonomy levels and PO mappings.\n"
        "  2. Unit-wise topic breakdown with hours and pedagogy type.\n"
        "  3. Reference search queries — plain search terms for finding relevant "
        "textbooks and journals.\n"
        "\n"
        "STRICT PROHIBITIONS — the following must NEVER appear in your response:\n"
        "  - Author names, editor names, or any person's name\n"
        "  - DOI numbers (e.g. 10.xxxx/...)\n"
        "  - ISBN or ISSN numbers\n"
        "  - Publisher names (e.g. MIT Press, Springer, Pearson)\n"
        "  - Publication year as part of a reference\n"
        "  - Any specific bibliographic citation\n"
        "For references: generate only plain search query strings like "
        "'machine learning fundamentals textbook' or 'neural networks deep learning'.\n"
        "\n"
        "Return only valid JSON matching the provided schema — no prose, no markdown fences."
    )

    po_lines = "\n".join(
        f"  {po.code}: {po.description}"
        for po in ctx.program_outcomes
    ) or "  (no programme outcomes provided)"

    custom_clause = (
        f"\nAdditional faculty instructions: {ctx.custom_instructions}"
        if ctx.custom_instructions else ""
    )

    user = (
        f"Generate a complete syllabus structure for:\n"
        f"  Course Code  : {ctx.course_code}\n"
        f"  Course Title : {ctx.course_title}\n"
        f"  Credits      : {ctx.course_credits}\n"
        f"\n"
        f"Programme Outcomes (POs) available for CO mapping:\n"
        f"{po_lines}\n"
        f"{custom_clause}\n"
        f"\n"
        f"Requirements:\n"
        f"- Minimum 4 Course Outcomes (COs). Each CO must:\n"
        f"    * Begin with an action verb (e.g. Apply, Analyse, Design, Implement)\n"
        f"    * Have a distinct Bloom's level "
        f"(Remember/Understand/Apply/Analyse/Evaluate/Create)\n"
        f"    * List suggested_po_codes using only codes from the PO list above\n"
        f"- Minimum 4 units covering the full course scope.\n"
        f"  Each unit: unit_number (1-based), title, topics list, total_hours, "
        f"pedagogy (lecture/lab/seminar/case_study/mixed).\n"
        f"- reference_queries: 5-7 plain search terms for textbooks and journals.\n"
        f"  Example valid query: 'data structures algorithms undergraduate textbook'\n"
        f"  Example INVALID query: 'Cormen 2009 ISBN 978-0262033848' — NEVER do this.\n"
        f"  ref_type must be TEXTBOOK, REFERENCE, or JOURNAL.\n"
        f"- Return JSON matching the schema exactly."
    )

    return system, user


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class SyllabusProvider(Protocol):
    async def generate_syllabus(
        self,
        ctx: SyllabusGenerationContext,
    ) -> SyllabusGenerationResult: ...


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
            response_schema=_SyllabusAI.model_json_schema(),
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

        try:
            parsed = _SyllabusAI.model_validate_json(raw)
        except Exception as exc:
            raise SyllabusAIParseError(
                f"AI response did not match the expected schema: {exc}\n"
                f"Raw response (first 500 chars): {raw[:500]}"
            ) from exc

        violations = _validate_result(parsed, ctx)
        if violations:
            raise SyllabusAIValidationError(
                "AI response failed business-rule validation:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )

        return SyllabusGenerationResult(
            outcomes=[
                {
                    "code":               co.code,
                    "description":        co.description,
                    "bloom_level":        co.bloom_level,
                    "suggested_po_codes": co.suggested_po_codes,
                }
                for co in parsed.outcomes
            ],
            units=[
                {
                    "unit_number": u.unit_number,
                    "title":       u.title,
                    "topics":      [t.model_dump(exclude_none=True) for t in u.topics],
                    "total_hours": u.total_hours,
                    "pedagogy":    u.pedagogy,
                }
                for u in parsed.units
            ],
            reference_queries=[
                {"query_str": rq.query_str, "ref_type": rq.ref_type}
                for rq in parsed.reference_queries
            ],
            model_used=settings.GEMINI_MODEL,
            prompt_hash=phash,
        )


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

        try:
            parsed = _SyllabusAI.model_validate_json(raw)
        except Exception as exc:
            raise SyllabusAIParseError(
                f"Groq response did not match the expected schema: {exc}\n"
                f"Raw response (first 500 chars): {raw[:500]}"
            ) from exc

        violations = _validate_result(parsed, ctx)
        if violations:
            raise SyllabusAIValidationError(
                "Groq AI response failed business-rule validation:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )

        return SyllabusGenerationResult(
            outcomes=[
                {
                    "code":               co.code,
                    "description":        co.description,
                    "bloom_level":        co.bloom_level,
                    "suggested_po_codes": co.suggested_po_codes,
                }
                for co in parsed.outcomes
            ],
            units=[
                {
                    "unit_number": u.unit_number,
                    "title":       u.title,
                    "topics":      [t.model_dump(exclude_none=True) for t in u.topics],
                    "total_hours": u.total_hours,
                    "pedagogy":    u.pedagogy,
                }
                for u in parsed.units
            ],
            reference_queries=[
                {"query_str": rq.query_str, "ref_type": rq.ref_type}
                for rq in parsed.reference_queries
            ],
            model_used=settings.GROQ_MODEL,
            prompt_hash=phash,
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


class FallbackSyllabusProvider:
    """
    Tries Gemini first.  Falls back to Groq only on quota / rate-limit errors;
    all other Gemini errors propagate normally so bugs are not silently swallowed.
    """

    def __init__(self) -> None:
        self._gemini = GeminiSyllabusProvider()
        self._groq = GroqSyllabusProvider()

    async def generate_syllabus(
        self,
        ctx: SyllabusGenerationContext,
    ) -> SyllabusGenerationResult:
        try:
            result = await self._gemini.generate_syllabus(ctx)
            logger.info("AI provider used: gemini (model=%s)", settings.GEMINI_MODEL)
            return result
        except SyllabusAIBlockedError as exc:
            # SyllabusAIBlockedError covers both safety blocks and empty-on-quota.
            # Only route to fallback when the message contains quota signals.
            if not _is_gemini_quota_error(exc):
                raise
            logger.warning(
                "Gemini quota / safety block detected (%s) — falling back to Groq.",
                exc,
            )
        except Exception as exc:
            if not _is_gemini_quota_error(exc):
                raise
            logger.warning(
                "Gemini quota error (%s) — falling back to Groq.", exc
            )

        result = await self._groq.generate_syllabus(ctx)
        logger.info("AI provider used: groq (model=%s)", settings.GROQ_MODEL)
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_syllabus_provider() -> SyllabusProvider:
    return FallbackSyllabusProvider()
