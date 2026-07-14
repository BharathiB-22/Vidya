from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import re
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


# Equivalent spellings of the six canonical levels: American spelling, the
# gerund forms models like to emit, and the original (pre-revision) Bloom names.
# Without these, a perfectly good "Analyze"/"Applying"/"Synthesis" silently
# collapses to "Apply" and the outcome's cognitive level is lost.
_BLOOM_SYNONYMS = {
    "remember":      "Remember",
    "remembering":   "Remember",
    "knowledge":     "Remember",
    "understand":    "Understand",
    "understanding": "Understand",
    "comprehension": "Understand",
    "apply":         "Apply",
    "applying":      "Apply",
    "application":   "Apply",
    "analyse":       "Analyse",
    "analyze":       "Analyse",
    "analysing":     "Analyse",
    "analyzing":     "Analyse",
    "analysis":      "Analyse",
    "evaluate":      "Evaluate",
    "evaluating":    "Evaluate",
    "evaluation":    "Evaluate",
    "create":        "Create",
    "creating":      "Create",
    "synthesis":     "Create",
}


class _OutcomeAI(BaseModel):
    code:          str
    description:   str
    bloom_level:   str = "Apply"
    display_order: int

    @field_validator("bloom_level", mode="before")
    @classmethod
    def coerce_bloom_level(cls, v: object) -> str:
        """Accept any equivalent spelling of a Bloom level; default to 'Apply'
        when the field is missing, blank, or genuinely unrecognised.

        Applies to every provider — Gemini validates through this model directly,
        Groq/DeepSeek reach it through the shared normalizer — so a provider's
        choice of 'Analyze' over 'Analyse' never costs an outcome its level.
        """
        s = str(v).strip() if v else ""
        if s in _VALID_BLOOM:
            return s
        return _BLOOM_SYNONYMS.get(s.lower(), "Apply")


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
    def normalize_identity_aliases(cls, data: object) -> object:
        """Some providers (and prompt variations) emit 'course_code'/'course_title'
        instead of the expected 'code'/'title'. Accept either, normalized to the
        canonical name, so a provider's field-name choice never fails program
        generation.

        A last-resort safety net only: every provider now reaches this model
        through the shared normalizer, which resolves a far wider alias set
        before validation ever runs. It stays because this model is also
        constructed directly in tests and by any future caller.
        """
        if not isinstance(data, dict):
            return data
        for canonical, alias in (("code", "course_code"), ("title", "course_title")):
            if not data.get(canonical) and data.get(alias):
                data = {**data, canonical: data[alias]}
        return data

    @model_validator(mode="after")
    def coerce_course_type(self) -> _CourseAI:
        """Infer course_type from title when missing, blank, or unrecognised.

        Deliberately has no non-null default on the field itself — a default of
        "THEORY" would already satisfy Pydantic before this validator runs,
        silently skipping inference for any course that omits the field, and
        misclassifying e.g. 'Data Structures Lab' as THEORY.
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

def _canonical_schema_clause() -> str:
    """The response contract, for providers that cannot be handed a schema
    out-of-band.

    Gemini is passed the canonical schema as `response_schema` on
    GenerateContentConfig. The OpenAI-compatible providers have no equivalent —
    `response_format={"type": "json_object"}` guarantees *syntactically* valid
    JSON and nothing at all about its shape. Left to themselves they invent one
    per call: a "program" wrapper, a "program_structure" wrapper, semester-grouped
    course lists, course_code vs code, and no programme outcomes or contact hours
    whatsoever.

    So they get the very same schema, serialised into the prompt. This is the
    single source of truth for both paths — it is generated from
    _ProgramStructureAI, not transcribed from it, so the two can never drift.

    Neither mechanism is a guarantee, only a request — response_schema no more
    than a prompt. Every provider's response, Gemini's included, is therefore put
    through the normalizer before validation; see _parse_structure.
    """
    schema = json.dumps(_ProgramStructureAI.model_json_schema(), indent=2, sort_keys=True)
    return (
        "\n\nRESPONSE SCHEMA — return a single JSON object conforming EXACTLY to this "
        "JSON Schema:\n"
        f"{schema}\n\n"
        "Schema rules (these override any other formatting assumption):\n"
        "- The top-level object has EXACTLY two keys: \"outcomes\" and \"courses\". "
        "Do NOT wrap them in \"program\", \"program_structure\", \"curriculum\", or any "
        "other container.\n"
        "- \"courses\" is ONE FLAT ARRAY of every course in the programme. Do NOT group "
        "courses by semester — each course carries its own \"semester\" integer instead.\n"
        "- Use these exact field names on every course: code, title, credits, semester, "
        "course_type, is_elective, elective_basket_name, hours_lecture, hours_tutorial, "
        "hours_practical, description, prerequisite_codes. Not course_code, not "
        "course_title, not name.\n"
        "- Every course must set hours_lecture, hours_tutorial and hours_practical to "
        "realistic weekly contact hours (a 4-credit theory course is typically 3-1-0; a "
        "2-credit lab 0-0-4; a project 0-0-8+). Never omit them and never leave them 0 "
        "for a course that is actually taught.\n"
        "- Every course must have a one-to-two sentence \"description\" of its content.\n"
        "- \"outcomes\" is REQUIRED and must contain 6-12 programme outcomes, each with "
        "code (PO1, PO2, ...), description, bloom_level, and display_order. Do not return "
        "an empty outcomes array.\n"
        "- Return raw JSON only — no markdown fences, no commentary."
    )


def _build_prompt(
    ctx: ProgramGenerationContext,
    *,
    include_schema: bool = False,
) -> tuple[str, str]:
    """Build the (system, user) prompt.

    `include_schema` appends the canonical schema to the user message, for
    providers that cannot receive it out-of-band. Gemini leaves it off — it gets
    the same schema as `response_schema` instead — so its prompt, and therefore
    its audited prompt_hash, is unchanged.
    """
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
        f"      AN ELECTIVE PAPER IS NOT A COURSE. It is a SLOT in the curriculum — a "
        f"choice the student makes. Nobody teaches a subject called 'Elective 1', and no "
        f"student sits an examination in it. Do NOT emit a course whose title is "
        f"'Elective 1', 'Elective 2', 'Professional Elective' or anything of that kind; "
        f"such a course will be DISCARDED.\n"
        f"      A paper exists ONLY as the elective_basket_name on its alternatives, and "
        f"the alternatives are the courses. Name the papers exactly 'Elective 1', "
        f"'Elective 2', 'Elective 3' (and so on) in elective_basket_name. Each paper needs "
        f"its OWN 2-5 alternative courses, each a REAL SUBJECT with a real title, and the "
        f"alternatives of one paper must be a coherent, distinct area from the alternatives "
        f"of the others. Every alternative inside one paper must carry the same credits.\n"
        f"      The student takes every paper in the semester, choosing exactly one "
        f"alternative inside each. Three papers of 3 credits therefore contribute 9 credits "
        f"to the semester, not 3. Example for one semester — note that the ONLY courses "
        f"emitted are the subjects on the right:\n"
        f"        elective_basket_name 'Elective 1' -> Artificial Intelligence, "
        f"Machine Learning\n"
        f"        elective_basket_name 'Elective 2' -> Data Mining, Data Science, "
        f"Business Intelligence\n"
        f"        elective_basket_name 'Elective 3' -> Business Management, "
        f"Social Media Marketing\n"
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

    if include_schema:
        user += _canonical_schema_clause()

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


# --- key canonicalisation --------------------------------------------------
#
# Providers disagree about field naming in every dimension at once: separator
# (course_title / courseTitle / "Course Title"), vocabulary (title / name /
# subject_name), and nesting depth. Matching keys literally means every new
# provider spelling is a fresh production failure. So keys are compared in a
# canonical form -- lowercase, alphanumerics only -- and looked up in an alias
# table keyed by that form. 'course_title', 'courseTitle' and 'Course Title'
# all canonicalise to 'coursetitle' and resolve to the same schema field.

def _canon(key: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


# alias (canonical form) -> canonical _CourseAI field
_COURSE_FIELD_ALIASES: dict[str, str] = {
    # code
    "code": "code", "coursecode": "code", "subjectcode": "code",
    "papercode": "code", "courseid": "code",
    # title
    "title": "title", "coursetitle": "title", "name": "title",
    "coursename": "title", "subjectname": "title", "subjecttitle": "title",
    "papertitle": "title", "papername": "title",
    # credits
    "credits": "credits", "credit": "credits", "creditpoints": "credits",
    "coursecredits": "credits", "creditvalue": "credits", "numberofcredits": "credits",
    # semester
    "semester": "semester", "semesternumber": "semester", "sem": "semester",
    "semno": "semester", "semesterno": "semester", "term": "semester",
    # course type
    "coursetype": "course_type", "type": "course_type", "subjecttype": "course_type",
    "coursecategory": "course_type", "category": "course_type",
    "componenttype": "course_type",
    # elective flag + basket
    "iselective": "is_elective", "elective": "is_elective", "isoptional": "is_elective",
    "electivebasketname": "elective_basket_name",
    "electivebasket": "elective_basket_name",
    "basketname": "elective_basket_name", "basket": "elective_basket_name",
    "electivegroup": "elective_basket_name",
    "electivepaper": "elective_basket_name",
    "electivename": "elective_basket_name",
    # contact hours
    "hourslecture": "hours_lecture", "lecturehours": "hours_lecture",
    "lecture": "hours_lecture", "l": "hours_lecture",
    "hourstutorial": "hours_tutorial", "tutorialhours": "hours_tutorial",
    "tutorial": "hours_tutorial", "t": "hours_tutorial",
    "hourspractical": "hours_practical", "practicalhours": "hours_practical",
    "hourslab": "hours_practical", "labhours": "hours_practical",
    "practical": "hours_practical", "p": "hours_practical",
    # description
    "description": "description", "desc": "description", "summary": "description",
    "coursedescription": "description", "overview": "description",
    # prerequisites
    "prerequisitecodes": "prerequisite_codes",
    "prerequisitecoursecodes": "prerequisite_codes",
    "prerequisites": "prerequisite_codes", "prerequisite": "prerequisite_codes",
    "prereqs": "prerequisite_codes", "prereq": "prerequisite_codes",
}

# alias (canonical form) -> canonical _OutcomeAI field
_OUTCOME_FIELD_ALIASES: dict[str, str] = {
    "code": "code", "pocode": "code", "outcomecode": "code",
    "programoutcomecode": "code",
    "description": "description", "statement": "description",
    "outcome": "description", "outcomestatement": "description",
    "outcomedescription": "description", "text": "description", "desc": "description",
    "bloomlevel": "bloom_level", "bloom": "bloom_level",
    "bloomtaxonomy": "bloom_level", "bloomstaxonomylevel": "bloom_level",
    "taxonomylevel": "bloom_level", "cognitivelevel": "bloom_level",
    "displayorder": "display_order", "order": "display_order",
    "sequence": "display_order", "index": "display_order",
    "sno": "display_order", "serialnumber": "display_order",
}

# Keys whose value is a list of course objects.
_COURSE_LIST_KEYS = frozenset({
    "courses", "courselist", "programcourses", "programmecourses", "coursedetails",
    "subjects", "subjectlist", "papers", "corecourses", "compulsorycourses",
    # elective containers — courses found under these are electives by construction
    "electives", "electivecourses", "electiveoptions", "electivechoices",
    "options", "alternatives", "choices",
})
_ELECTIVE_LIST_KEYS = frozenset({
    "electives", "electivecourses", "electiveoptions", "electivechoices",
    "options", "alternatives", "choices",
})

# Keys whose value is a list of programme-outcome objects.
_OUTCOME_LIST_KEYS = frozenset({
    "outcomes", "outcomeslist", "programoutcomes", "programmeoutcomes",
    "programoutcomeslist", "pos",
})

# Keys carrying the semester number on a semester-group object.
_SEMESTER_NUMBER_KEYS = ("semesternumber", "semester", "sem", "semesterno", "semno", "term")

# Keys carrying the elective paper name on a basket-group object.
_BASKET_NAME_KEYS = ("electivebasketname", "basketname", "basket", "electivegroup",
                     "electivepaper", "electivename", "papername")

# Keys identifying a course object (as opposed to a group/wrapper object).
_COURSE_IDENTITY_KEYS = frozenset({
    "code", "coursecode", "subjectcode", "papercode", "courseid",
    "title", "coursetitle", "name", "coursename", "subjectname", "subjecttitle",
})

# A course_type value that really means "this course is an elective".
_ELECTIVE_TYPE_WORDS = frozenset({
    "elective", "electives", "optional", "openelective",
    "professionalelective", "departmentelective", "electivecourse",
})

# Credits to assume when a provider omits them entirely — a course with no
# credits cannot be persisted at all, and a type-appropriate guess that the
# worker's credit rebalance will then adjust beats failing the whole generation.
_DEFAULT_CREDITS = {
    "THEORY": 3, "LAB": 2, "PROJECT": 6, "INTERNSHIP": 4, "SEMINAR": 1,
}

_MAX_HARVEST_DEPTH = 8


def _remap(d: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    """Add canonical field names to `d`, resolved from `aliases`.

    An exact canonical key already present always wins; an alias only fills a
    field that is absent or empty. Unrecognised keys are left untouched (Pydantic
    ignores them) so nothing is lost if a provider carries extra metadata.
    """
    out: dict[str, Any] = dict(d)
    for key, value in d.items():
        target = aliases.get(_canon(key))
        if target is None or target == key:
            continue
        if value in (None, ""):
            continue
        # `out.get(target) is False` must survive: `False in (None, "", [], {})`
        # is False, so an explicit is_elective=false is never overwritten.
        if out.get(target) in (None, "", [], {}):
            out[target] = value
    return out


# --- value coercion --------------------------------------------------------

def _as_int(value: object, default: int = 0) -> int:
    """First integer found in the value. Handles 3, 3.0, "3", "Semester 3"."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"-?\d+", str(value or ""))
    return int(m.group()) if m else default


_TRUTHY = frozenset({"true", "yes", "y", "1", "elective", "optional"})


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in _TRUTHY


_NO_PREREQ_WORDS = frozenset({"", "none", "nil", "na", "n/a", "-", "null", "no prerequisites"})


def _as_code_list(value: object) -> list[str]:
    """Course codes out of any of: null, "", "None", "CS101, CS102",
    ["CS101"], [{"code": "CS101"}]."""
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        if value.strip().lower() in _NO_PREREQ_WORDS:
            return []
        return [p.strip() for p in re.split(r"[,;/]|\band\b", value) if p.strip()]
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, list):
        return []

    codes: list[str] = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("code") or item.get("course_code") or item.get("title")
        if item is None or str(item).strip().lower() in _NO_PREREQ_WORDS:
            continue
        codes.append(str(item).strip())
    return codes


def _load_json(raw: str, provider: str) -> Any:
    """Parse the provider's message content, tolerating markdown fences and any
    prose a model wraps around the JSON despite being told not to."""
    text = (raw or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Salvage the outermost JSON value from surrounding prose.
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(
        f"{provider} response is not valid JSON.\n"
        f"Raw (first 300 chars): {raw[:300]}"
    )


# --- structural harvesting -------------------------------------------------
#
# Rather than reaching into known paths ("program_structure" -> "semesters"),
# walk the document and pick up course/outcome objects wherever they sit. This
# is what makes {"program": {"semesters": [...]}}, {"program_structure":
# {"semester_wise_courses": [...]}} and a bare {"courses": [...]} the same
# problem, and what stops the next unseen wrapper key from being an outage.
# Semester number and elective-paper name are inherited from the enclosing
# group when the course object does not carry them itself.

def _looks_like_course(node: dict[str, Any]) -> bool:
    """True for a leaf course object; False for a group/wrapper that *contains*
    courses (a semester, an elective basket, the root)."""
    keys = {_canon(k) for k in node}
    if keys & _COURSE_LIST_KEYS:
        return False          # it holds courses, so it is not one
    return bool(keys & _COURSE_IDENTITY_KEYS)


def _group_value(node: dict[str, Any], keys: tuple[str, ...]) -> Any:
    by_canon = {_canon(k): k for k in node}
    for key in keys:
        if key in by_canon:
            return node[by_canon[key]]
    return None


def _harvest_courses(
    node: Any,
    semester: int | None = None,
    basket: str | None = None,
    elective: bool = False,
    found: list[dict[str, Any]] | None = None,
    depth: int = 0,
) -> list[dict[str, Any]]:
    """Collect every course object in the document, each with the semester and
    elective-paper context inherited from the group that contained it."""
    if found is None:
        found = []
    if depth > _MAX_HARVEST_DEPTH:
        return found

    if isinstance(node, list):
        for item in node:
            _harvest_courses(item, semester, basket, elective, found, depth + 1)
        return found

    if not isinstance(node, dict):
        return found

    # Context this group contributes to the courses beneath it.
    sem_value = _group_value(node, _SEMESTER_NUMBER_KEYS)
    if isinstance(sem_value, (int, float, str)):
        n = _as_int(sem_value, 0)
        if 0 < n <= 20:
            semester = n

    basket_value = _group_value(node, _BASKET_NAME_KEYS)
    if isinstance(basket_value, str) and basket_value.strip():
        basket = basket_value.strip()

    for key, value in node.items():
        canon = _canon(key)

        if canon in _OUTCOME_LIST_KEYS:
            continue

        # {"semesters": {"1": [...], "2": [...]}} / {"semester_1": [...]}
        sem_match = re.fullmatch(r"(?:semester|sem|term)?(\d{1,2})", canon)

        if canon in _COURSE_LIST_KEYS or (sem_match and isinstance(value, list)):
            child_sem = int(sem_match.group(1)) if sem_match else semester
            child_elective = elective or canon in _ELECTIVE_LIST_KEYS
            for item in value if isinstance(value, list) else []:
                if not isinstance(item, dict):
                    continue
                if _looks_like_course(item):
                    found.append({
                        "raw": item,
                        "semester": child_sem,
                        "basket": basket,
                        "elective": child_elective,
                    })
                else:
                    # e.g. an elective basket object nested inside "electives"
                    _harvest_courses(item, child_sem, basket, child_elective,
                                     found, depth + 1)
            continue

        if isinstance(value, (dict, list)):
            _harvest_courses(value, semester, basket, elective, found, depth + 1)

    return found


def _harvest_outcomes(
    node: Any,
    found: list[Any] | None = None,
    depth: int = 0,
) -> list[Any]:
    """Collect every programme-outcome object in the document, at any depth."""
    if found is None:
        found = []
    if depth > _MAX_HARVEST_DEPTH:
        return found

    if isinstance(node, list):
        for item in node:
            _harvest_outcomes(item, found, depth + 1)
        return found

    if not isinstance(node, dict):
        return found

    for key, value in node.items():
        canon = _canon(key)
        if canon in _COURSE_LIST_KEYS:
            continue
        if canon in _OUTCOME_LIST_KEYS and isinstance(value, list):
            found.extend(value)
            continue
        if isinstance(value, (dict, list)):
            _harvest_outcomes(value, found, depth + 1)

    return found


# --- per-object normalisation ----------------------------------------------

def _synthesise_code(title: str, semester: int, index: int) -> str:
    initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", title))[:3].upper()
    return f"{initials or 'GEN'}{semester}{index:02d}"


def _normalize_course(
    entry: dict[str, Any],
    index: int,
    provider: str,
) -> dict[str, Any] | None:
    """One harvested course object -> a dict satisfying every _CourseAI field.
    Returns None for an object too empty to be a course at all."""
    c = _remap(entry["raw"], _COURSE_FIELD_ALIASES)

    title = str(c.get("title") or "").strip()
    code = str(c.get("code") or "").strip()
    if not title and not code:
        logger.warning("%s: dropped course entry with neither code nor title: %r",
                       provider, entry["raw"])
        return None

    # course_type first — it decides the credit range and the credit default.
    raw_type = str(c.get("course_type") or "").strip()
    type_means_elective = _canon(raw_type) in _ELECTIVE_TYPE_WORDS
    course_type = raw_type.upper()
    if course_type not in _VALID_COURSE_TYPES:
        course_type = _infer_course_type_from_title(title or code)

    semester = _as_int(c.get("semester"), 0)
    if not 0 < semester <= 20:
        semester = entry["semester"] or _infer_semester(code)

    if not title:
        title = code
    if not code:
        code = _synthesise_code(title, semester, index)
        logger.warning("%s: course %r had no code — synthesised %r.",
                       provider, title, code)

    # An ABSENT credits field falls back to a type-appropriate default; a
    # credits field the provider actually set is trusted and merely clamped into
    # range. The two must not be conflated -- an explicit 0 is a provider getting
    # the value wrong (clamp it to the 1-credit floor), not a provider staying
    # silent (where a 3-credit theory course is the better guess).
    raw_credits = c.get("credits")
    credits = -1 if raw_credits in (None, "") else _as_int(raw_credits, -1)
    if credits < 0:
        credits = _DEFAULT_CREDITS.get(course_type, 3)
        logger.warning("%s: course %r has no usable credits — defaulted to %d for %s.",
                       provider, code, credits, course_type)
    lo, hi = (2, 20) if course_type in ("PROJECT", "INTERNSHIP") else (1, 6)
    clamped = max(lo, min(hi, credits))
    if clamped != credits:
        logger.warning("%s: course %r credits %d out of range [%d, %d], clamped to %d.",
                       provider, code, credits, lo, hi, clamped)
        credits = clamped

    # An elective is anything the provider flagged, typed, or filed under a paper.
    basket = str(c.get("elective_basket_name") or "").strip() or (entry["basket"] or "")
    is_elective = _as_bool(
        c.get("is_elective"),
        default=entry["elective"] or type_means_elective or bool(basket),
    )
    if not is_elective:
        basket = ""   # a basket name is meaningless on a core course

    description = str(c.get("description") or "").strip()
    if not description:
        description = f"Course covering topics in {title}."

    prerequisite_codes = [
        p for p in _as_code_list(c.get("prerequisite_codes"))
        if p.upper() != code.upper()      # a course is never its own prerequisite
    ]

    return {
        "code":                 code,
        "title":                title,
        "credits":              credits,
        "semester":             semester,
        "course_type":          course_type,
        "is_elective":          is_elective,
        "elective_basket_name": basket or None,
        "hours_lecture":        max(0, _as_int(c.get("hours_lecture"), 0)),
        "hours_tutorial":       max(0, _as_int(c.get("hours_tutorial"), 0)),
        "hours_practical":      max(0, _as_int(c.get("hours_practical"), 0)),
        "description":          description,
        "prerequisite_codes":   prerequisite_codes,
    }


def _normalize_outcome(outcome: Any, index: int) -> dict[str, Any] | None:
    """One harvested outcome (object, or a bare statement string) -> a dict
    satisfying every _OutcomeAI field. Returns None when there is no statement."""
    if isinstance(outcome, str):
        outcome = {"description": outcome}
    if not isinstance(outcome, dict):
        return None

    o = _remap(outcome, _OUTCOME_FIELD_ALIASES)

    description = str(o.get("description") or "").strip()
    if not description:
        return None

    display_order = _as_int(o.get("display_order"), index + 1) or index + 1

    code = str(o.get("code") or "").strip()
    if not code or code.isdigit():   # a bare "1" is an index, not a PO code
        code = f"PO{display_order}"

    return {
        "code":          code,
        "description":   description,
        # _OutcomeAI.coerce_bloom_level resolves spelling variants and defaults.
        "bloom_level":   str(o.get("bloom_level") or "").strip(),
        "display_order": display_order,
    }


def _normalize_ai_structure(
    raw: str,
    provider: str = "ai",
    *,
    department: str = "",
    degree_type: str = "",
) -> dict[str, Any]:
    """
    Normalise JSON from ANY provider (Gemini, Groq, DeepSeek, …) into the
    canonical _ProgramStructureAI shape: {"outcomes": [...], "courses": [...]}.

    Nothing here is keyed on which provider sent the payload — the same pass runs
    for all of them, and it is the *shape* of the document that is interpreted:

      - any wrapper depth        {"program": {...}}, {"program_structure": {...}}, …
      - semester-grouped courses  semesters / semester_wise_courses / {"1": [...]}
      - elective baskets          courses nested under a paper, inheriting its name
      - field-name variants       course_title→title, course_code→code, name→title,
                                  prerequisites→prerequisite_codes, lab_hours→…
      - missing required fields   code, credits, semester, is_elective, description
      - missing outcomes          → 4 synthesised fallback POs

    Every course returned is guaranteed to carry every field _CourseAI requires,
    so a provider's field-naming or nesting choice can no longer fail generation.
    """
    document = _load_json(raw, provider)

    if isinstance(document, list):
        document = {"courses": document}     # a bare course array
    if not isinstance(document, dict):
        raise ValueError(
            f"{provider} response is not a JSON object (got {type(document).__name__})."
        )

    # --- courses ---
    courses: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, entry in enumerate(_harvest_courses(document)):
        course = _normalize_course(entry, index, provider)
        if course is None:
            continue
        # Duplicate codes break the worker's code→id map and the DB's unique
        # constraint. A course can be harvested twice when a provider emits both
        # a flat list and a semester-grouped one; first occurrence wins.
        if course["code"].upper() in seen_codes:
            logger.warning("%s: dropped duplicate course code %r (%r).",
                           provider, course["code"], course["title"])
            continue
        seen_codes.add(course["code"].upper())
        courses.append(course)

    if not courses:
        raise ValueError(
            f"{provider} response contains no recognisable courses.\n"
            f"Raw (first 500 chars): {raw[:500]}"
        )

    # A prerequisite pointing at a course that does not exist in this program is
    # dropped by the worker anyway; drop it here so the audited AI output and the
    # persisted structure agree.
    for course in courses:
        course["prerequisite_codes"] = [
            p for p in course["prerequisite_codes"] if p.upper() in seen_codes
        ]

    # --- outcomes ---
    outcomes: list[dict[str, Any]] = []
    for index, raw_outcome in enumerate(_harvest_outcomes(document)):
        outcome = _normalize_outcome(raw_outcome, index)
        if outcome is not None:
            outcomes.append(outcome)

    if not outcomes:
        logger.warning(
            "%s response has no outcomes — synthesising 4 fallback POs "
            "(department=%r, degree_type=%r).",
            provider, department, degree_type,
        )
        outcomes = _synthesise_fallback_outcomes(department, degree_type)

    logger.info("%s: normalised %d courses, %d outcomes.",
                provider, len(courses), len(outcomes))

    return {"outcomes": outcomes, "courses": courses}


# Old names kept as aliases for existing callers and tests.
_normalize_openai_compatible_structure = _normalize_ai_structure
_normalize_groq_structure = _normalize_ai_structure


def _parse_structure(
    raw: str,
    *,
    provider: str,
    label: str,
    department: str = "",
    degree_type: str = "",
) -> _ProgramStructureAI:
    """Raw provider text -> validated _ProgramStructureAI. The ONLY parse path.

    Every provider goes through the normalizer, including Gemini. Gemini is given
    the canonical schema as `response_schema`, but that is a request, not a
    guarantee: it is free to wrap the payload ({"program": {"semesters": [...]}}),
    group courses by semester, or rename fields, and it does. Validating its text
    directly against _ProgramStructureAI — as this used to — turned any such
    equivalent-but-different shape into `ValidationError: courses Field required`
    and, since Gemini leads the fallback chain, failed generation outright even
    though the curriculum data was entirely present and valid.

    The normalizer is shape-driven and provider-agnostic, and it is a no-op on
    input that is already canonical, so routing every provider through it costs a
    conforming response nothing and rescues a non-conforming one.
    """
    normalized = _normalize_ai_structure(
        raw,
        provider=provider,
        department=department,
        degree_type=degree_type,
    )
    try:
        return _ProgramStructureAI.model_validate(normalized)
    except Exception as exc:
        raise ValueError(
            f"{label} response did not match the expected schema: {exc}\n"
            f"Raw response (first 500 chars): {raw[:500]}"
        ) from exc


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

        parsed = _parse_structure(
            raw,
            provider="gemini",
            label="Gemini",
            department=ctx.department,
            degree_type=ctx.degree_type,
        )

        return ProgramStructureResult(
            outcomes=[o.model_dump() for o in parsed.outcomes],
            courses=[c.model_dump() for c in parsed.courses],
            model_used=settings.GEMINI_MODEL,
            provider_name="gemini",
            prompt_hash=phash,
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible providers (Groq, DeepSeek)
#
# Identical pipeline, different endpoint: both are handed the canonical schema
# in the prompt (they have no response_schema equivalent), both go through the
# same provider-agnostic normalizer, and both land on _ProgramStructureAI. The
# provider only supplies its endpoint, key and model — nothing about how a
# response is interpreted may vary per provider, which is what stopped the
# Groq/DeepSeek shapes being handled and stopped them being caught.
# ---------------------------------------------------------------------------

class _OpenAICompatibleStructureProvider:

    name:          str = ""   # provider_name recorded in the AuditLog
    label:         str = ""   # human-facing name used in error messages
    base_url:      str = ""
    key_setting:   str = ""
    model_setting: str = ""

    async def generate_structure(
        self,
        ctx: ProgramGenerationContext,
    ) -> ProgramStructureResult:
        api_key = getattr(settings, self.key_setting, "")
        if not api_key:
            raise ValueError(
                f"{self.key_setting} is not configured. Set it in your .env file."
            )
        model = getattr(settings, self.model_setting, "")

        from openai import AsyncOpenAI

        # include_schema: the canonical _ProgramStructureAI schema goes in the
        # prompt, since these APIs cannot be given it out-of-band the way Gemini
        # can. The prompt_hash therefore covers the schema actually sent.
        system, user = _build_prompt(ctx, include_schema=True)
        phash = _prompt_hash(system, user)

        client = AsyncOpenAI(api_key=api_key, base_url=self.base_url)

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise ValueError(f"{self.label} returned an empty response.")

        parsed = _parse_structure(
            raw,
            provider=self.name,
            label=self.label,
            department=ctx.department,
            degree_type=ctx.degree_type,
        )

        return ProgramStructureResult(
            outcomes=[o.model_dump() for o in parsed.outcomes],
            courses=[c.model_dump() for c in parsed.courses],
            model_used=model,
            provider_name=self.name,
            prompt_hash=phash,
        )


class GroqStructureProvider(_OpenAICompatibleStructureProvider):
    """Groq llama-3.3-70b-versatile via the OpenAI-compatible API."""

    name          = "groq"
    label         = "Groq"
    base_url      = "https://api.groq.com/openai/v1"
    key_setting   = "GROQ_API_KEY"
    model_setting = "GROQ_MODEL"


class DeepSeekStructureProvider(_OpenAICompatibleStructureProvider):
    """DeepSeek-V3 via the OpenAI-compatible API."""

    name          = "deepseek"
    label         = "DeepSeek"
    base_url      = "https://api.deepseek.com"
    key_setting   = "DEEPSEEK_API_KEY"
    model_setting = "DEEPSEEK_MODEL"


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
