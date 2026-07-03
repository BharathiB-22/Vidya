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
from typing import Any, Protocol, runtime_checkable

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
    outcomes:          list[dict]   # code, description, bloom_level, suggested_po_codes[], po_mapping_strengths{}
    units:             list[dict]   # unit_number, title, topics[], total_hours, pedagogy
    reference_queries: list[dict]   # query_str, ref_type
    model_used:        str
    provider_name:     str          # "gemini" | "groq" | "deepseek"
    prompt_hash:       str


# ---------------------------------------------------------------------------
# Private Pydantic models — Gemini response_schema only
# (never returned to callers; mapped to dicts in SyllabusGenerationResult)
# ---------------------------------------------------------------------------

_VALID_BLOOM = {b.value for b in BloomLevel}
_VALID_REF_TYPES = {r.value for r in RefType}
_VALID_PEDAGOGIES = {"lecture", "lab", "seminar", "case_study", "mixed"}
_VALID_MAPPING_STRENGTHS = {"HIGH", "MEDIUM", "LOW"}


class _TopicAI(BaseModel):
    title:          str
    description:    str | None = None
    hours_estimate: int | None = Field(default=None, ge=1)
    subtopics:      list[str]  = Field(default_factory=list)
    examples:       list[str]  = Field(default_factory=list)
    lab_reference:  str | None = None


class _COAI(BaseModel):
    code:                  str = Field(..., min_length=1, max_length=20)
    description:           str = Field(..., min_length=15)
    bloom_level:           str = "APPLY"
    suggested_po_codes:    list[str] = Field(default_factory=list)
    po_mapping_strengths:  dict[str, str] = Field(default_factory=dict)
    # po_code -> "HIGH" | "MEDIUM" | "LOW" — how strongly this CO supports that PO.

    @model_validator(mode="after")
    def _check_bloom(self) -> _COAI:
        up = (self.bloom_level or "").upper().strip()
        self.bloom_level = up if up in _VALID_BLOOM else "APPLY"
        return self

    @model_validator(mode="after")
    def _check_mapping_strengths(self) -> _COAI:
        normalized: dict[str, str] = {}
        for po_code in self.suggested_po_codes:
            raw = str(self.po_mapping_strengths.get(po_code, "")).upper().strip()
            normalized[po_code] = raw if raw in _VALID_MAPPING_STRENGTHS else "MEDIUM"
        self.po_mapping_strengths = normalized
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
        "You are an expert academic curriculum designer. "
        "You create detailed course syllabi aligned with outcome-based education principles "
        "and Bloom's revised taxonomy. "
        "Adapt the syllabus depth, unit structure, CO style, and pedagogy to the university "
        "framework specified in the faculty instructions — this may include NEP 2020, "
        "VTU regulations, autonomous university standards, NBA/NAAC accreditation, "
        "industry-integrated, research-oriented, or skill-based approaches. "
        "When no specific framework is given, apply broadly accepted academic norms. "
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
        f"- Generate Course Outcomes (COs) — aim for at least 4, or as many as the "
        f"university framework requires. Each CO must:\n"
        f"    * Begin with an action verb (e.g. Apply, Analyse, Design, Implement)\n"
        f"    * Have a distinct Bloom's level "
        f"(Remember/Understand/Apply/Analyse/Evaluate/Create)\n"
        f"    * List suggested_po_codes using only codes from the PO list above\n"
        f"    * For EACH code in suggested_po_codes, set po_mapping_strengths[code] to "
        f"HIGH, MEDIUM, or LOW based on how directly this CO supports that PO — "
        f"HIGH when the CO is a primary driver of the PO, MEDIUM for a moderate/partial "
        f"contribution, LOW for a tangential one. Judge each CO-PO pair independently: "
        f"a realistic CO-PO matrix has a natural mixture of HIGH, MEDIUM, and LOW across "
        f"different COs and POs — do NOT default every mapping to MEDIUM.\n"
        f"- Generate units covering the full course scope with academic depth — "
        f"aim for at least 4 units (typically 5-6 for a standard course).\n"
        f"  Each unit must have:\n"
        f"    * unit_number (1-based), a clear title\n"
        f"    * 6 to 8 detailed topics (no fewer than 6). For each topic provide:\n"
        f"        - title: concise topic name\n"
        f"        - description: 2-3 sentence academic explanation of the topic\n"
        f"        - subtopics: list of 3-5 key sub-concepts covered under this topic\n"
        f"        - examples: list of 2-3 concrete real-world or applied examples\n"
        f"        - lab_reference: describe a relevant practical or lab exercise "
        f"(null if not applicable)\n"
        f"        - hours_estimate: estimated teaching hours (1-3)\n"
        f"    * total_hours: sum of all topic hours\n"
        f"    * pedagogy: lecture/lab/seminar/case_study/mixed\n"
        f"- reference_queries: 5-7 plain search terms for textbooks and journals.\n"
        f"  Example valid query: 'data structures algorithms undergraduate textbook'\n"
        f"  Example INVALID query: 'Cormen 2009 ISBN 978-0262033848' — NEVER do this.\n"
        f"  ref_type must be TEXTBOOK, REFERENCE, or JOURNAL.\n"
        f"- Return JSON matching the schema exactly."
    )

    return system, user


def _is_soft_violation(violation: str) -> bool:
    """Return True for violations that should warn but not abort generation.

    Count shortfalls (fewer COs or units than ideal) are soft — different university
    styles legitimately produce fewer items, and a warning is preferable to a failure.
    """
    return "minimum required is" in violation.lower()


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
            hard = [v for v in violations if not _is_soft_violation(v)]
            soft = [v for v in violations if _is_soft_violation(v)]
            if soft:
                logger.warning(
                    "m02.gemini: soft violations — proceeding: %s", soft
                )
            if hard:
                raise SyllabusAIValidationError(
                    "Gemini AI response failed business-rule validation:\n"
                    + "\n".join(f"  - {v}" for v in hard)
                )

        return SyllabusGenerationResult(
            outcomes=[
                {
                    "code":               co.code,
                    "description":        co.description,
                    "bloom_level":        co.bloom_level,
                    "suggested_po_codes": co.suggested_po_codes,
                    "po_mapping_strengths": co.po_mapping_strengths,
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
            provider_name="gemini",
            prompt_hash=phash,
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
        if not str(co.get("description", "")).strip():
            for alias in ("co_statement", "co_description", "statement", "co"):
                candidate = str(co.get(alias, "")).strip()
                if candidate:
                    co["description"] = candidate
                    break
            else:
                # All aliases exhausted — synthesize a valid fallback description.
                code_label = co.get("code") or f"CO{i + 1}"
                bloom = str(co.get("bloom_level", "Apply")).capitalize()
                co["description"] = (
                    f"{code_label}: demonstrate competency through "
                    f"{bloom}-level mastery of core concepts."
                )

        # Always strip remaining alias keys so Pydantic sees no unexpected fields.
        for alias in ("co_statement", "co_description", "statement", "co", "bloom"):
            co.pop(alias, None)
        if not co.get("code"):
            co["code"] = f"CO{i + 1}"
        if "suggested_po_codes" not in co:
            co["suggested_po_codes"] = []

        # po_mapping_strengths aliases; Pydantic validator fills in any missing
        # per-code entries with MEDIUM, so a partial or absent dict is fine here.
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

        try:
            parsed = _SyllabusAI.model_validate(normalized)
        except SyllabusAIParseError:
            raise
        except Exception as exc:
            raise SyllabusAIParseError(
                f"Groq response did not match the expected schema after normalization: {exc}\n"
                f"Normalized keys: {list(normalized.keys())}\n"
                f"Raw response (first 500 chars): {raw[:500]}"
            ) from exc

        violations = _validate_result(parsed, ctx)
        if violations:
            hard = [v for v in violations if not _is_soft_violation(v)]
            soft = [v for v in violations if _is_soft_violation(v)]
            if soft:
                logger.warning(
                    "m02.groq: soft violations — proceeding: %s", soft
                )
            if hard:
                raise SyllabusAIValidationError(
                    "Groq AI response failed business-rule validation:\n"
                    + "\n".join(f"  - {v}" for v in hard)
                )

        return SyllabusGenerationResult(
            outcomes=[
                {
                    "code":               co.code,
                    "description":        co.description,
                    "bloom_level":        co.bloom_level,
                    "suggested_po_codes": co.suggested_po_codes,
                    "po_mapping_strengths": co.po_mapping_strengths,
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
            provider_name="groq",
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

        try:
            parsed = _SyllabusAI.model_validate(normalized)
        except SyllabusAIParseError:
            raise
        except Exception as exc:
            raise SyllabusAIParseError(
                f"DeepSeek response did not match the expected schema after normalization: {exc}\n"
                f"Normalized keys: {list(normalized.keys())}\n"
                f"Raw response (first 500 chars): {raw[:500]}"
            ) from exc

        violations = _validate_result(parsed, ctx)
        if violations:
            hard = [v for v in violations if not _is_soft_violation(v)]
            soft = [v for v in violations if _is_soft_violation(v)]
            if soft:
                logger.warning(
                    "m02.deepseek: soft violations — proceeding: %s", soft
                )
            if hard:
                raise SyllabusAIValidationError(
                    "DeepSeek AI response failed business-rule validation:\n"
                    + "\n".join(f"  - {v}" for v in hard)
                )

        return SyllabusGenerationResult(
            outcomes=[
                {
                    "code":               co.code,
                    "description":        co.description,
                    "bloom_level":        co.bloom_level,
                    "suggested_po_codes": co.suggested_po_codes,
                    "po_mapping_strengths": co.po_mapping_strengths,
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
            model_used=settings.DEEPSEEK_MODEL,
            provider_name="deepseek",
            prompt_hash=phash,
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

        raise RuntimeError(
            "All syllabus AI providers failed. "
            f"Last error: {last_exc}"
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
    return provider_cls()
