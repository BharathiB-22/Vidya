"""
Unit tests for M01 ai_provider — pure-Python, no DB, no real API calls.
"""
from __future__ import annotations

import contextlib
import json
import sys
import types as types_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.modules.m01_program_advisor.ai_provider import (
    DeepSeekStructureProvider,
    GroqStructureProvider,
    GeminiStructureProvider,
    FallbackStructureProvider,
    ProgramGenerationContext,
    ProgramStructureResult,
    _CourseAI,
    _ProgramStructureAI,
    _build_prompt,
    _infer_course_type_from_title,
    _normalize_groq_structure,
    _prompt_hash,
    get_structure_provider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx() -> ProgramGenerationContext:
    return ProgramGenerationContext(
        degree_type="BTech",
        department="Computer Science",
        duration_years=4,
        total_credits=160,
        prompt_hint=None,
        existing_outcome_codes=[],
    )


_VALID_GROQ_JSON = """{
    "outcomes": [
        {"code": "PO1", "description": "Apply computing concepts", "bloom_level": "Apply", "display_order": 1}
    ],
    "courses": [
        {
            "code": "CS101", "title": "Intro to CS", "credits": 4,
            "semester": 1, "is_elective": false,
            "hours_lecture": 3, "hours_tutorial": 1, "hours_practical": 2,
            "description": "Foundational CS course.",
            "prerequisite_codes": []
        }
    ]
}"""


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------

def test_get_structure_provider_returns_groq_by_default():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings:
        mock_settings.AI_PROVIDER = "groq"
        provider = get_structure_provider()
    assert isinstance(provider, GroqStructureProvider)


def test_get_structure_provider_returns_gemini_when_configured():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings:
        mock_settings.AI_PROVIDER = "gemini"
        provider = get_structure_provider()
    assert isinstance(provider, GeminiStructureProvider)


def test_get_structure_provider_returns_fallback_when_configured():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings:
        mock_settings.AI_PROVIDER = "fallback"
        provider = get_structure_provider()
    assert isinstance(provider, FallbackStructureProvider)


def test_get_structure_provider_raises_on_unknown():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings:
        mock_settings.AI_PROVIDER = "nonexistent"
        with pytest.raises(ValueError, match="Unknown AI_PROVIDER"):
            get_structure_provider()


# ---------------------------------------------------------------------------
# Prompt schema contract
#
# Gemini is handed the canonical schema out-of-band, as response_schema on
# GenerateContentConfig. Groq and DeepSeek have no such mechanism — json_object
# mode buys valid JSON and nothing about its shape — so they must be handed the
# SAME schema inside the prompt. Both paths must derive it from
# _ProgramStructureAI, never from a hand-copy that can drift.
# ---------------------------------------------------------------------------

class TestPromptSchemaContract:

    def test_openai_compatible_prompt_embeds_the_canonical_schema(self):
        _, user = _build_prompt(_make_ctx(), include_schema=True)
        schema = _ProgramStructureAI.model_json_schema()

        # the schema in the prompt is the real one, parsed back out of it
        start = user.index("{", user.index("RESPONSE SCHEMA"))
        embedded = json.loads(user[start:user.rindex("}", start, user.index("Schema rules")) + 1])
        assert embedded == schema

        # and the fields the providers kept getting wrong are named explicitly
        assert '"outcomes"' in user and '"courses"' in user
        for field in ("course_type", "is_elective", "elective_basket_name",
                      "hours_lecture", "hours_practical", "prerequisite_codes"):
            assert field in user

    def test_gemini_prompt_is_unchanged_by_the_schema_clause(self):
        """Gemini gets the schema as response_schema, so its prompt — and the
        prompt_hash written to the AuditLog — must not move."""
        _, gemini_user = _build_prompt(_make_ctx())
        _, oai_user = _build_prompt(_make_ctx(), include_schema=True)

        assert "RESPONSE SCHEMA" not in gemini_user
        assert oai_user.startswith(gemini_user)   # schema is purely additive

    def test_both_openai_providers_send_an_identical_schema(self):
        """Groq and DeepSeek must be held to the same contract as each other."""
        groq = GroqStructureProvider()
        deepseek = DeepSeekStructureProvider()
        assert groq.base_url != deepseek.base_url          # only the endpoint differs
        # both inherit the one generate_structure, so the prompt cannot diverge
        assert (GroqStructureProvider.generate_structure
                is DeepSeekStructureProvider.generate_structure)

    def test_prompt_hash_covers_the_embedded_schema(self):
        """The audited hash must be of the prompt actually sent, not of a
        schema-less variant."""
        system, gemini_user = _build_prompt(_make_ctx())
        _, oai_user = _build_prompt(_make_ctx(), include_schema=True)
        assert _prompt_hash(system, gemini_user) != _prompt_hash(system, oai_user)


# ---------------------------------------------------------------------------
# Normalizer tests
# ---------------------------------------------------------------------------

def test_normalize_canonical_keys_unchanged():
    data = _normalize_groq_structure(_VALID_GROQ_JSON)
    assert "outcomes" in data
    assert "courses" in data


def test_normalize_program_outcomes_alias():
    raw = ('{"program_outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}],'
           ' "courses": [{"code": "CS101", "title": "Intro", "credits": 3, "semester": 1, "is_elective": false}]}')
    data = _normalize_groq_structure(raw)
    assert "outcomes" in data
    assert "program_outcomes" not in data


def test_normalize_course_list_alias():
    raw = ('{"outcomes": [], "course_list": '
           '[{"code": "CS101", "title": "Intro", "credits": 3, "semester": 1, "is_elective": false}]}')
    data = _normalize_groq_structure(raw)
    assert "courses" in data
    assert "course_list" not in data
    assert data["courses"][0]["code"] == "CS101"


def test_normalize_prerequisite_aliases():
    raw = ('{"outcomes": [], "courses": ['
           '{"code": "CS101", "title": "Intro", "credits": 3, "semester": 1, "is_elective": false},'
           '{"code": "CS201", "title": "Data Structures", "credits": 4, "semester": 2,'
           ' "is_elective": false, "prerequisites": ["CS101"], "hours_practical": 0}]}')
    data = _normalize_groq_structure(raw)
    assert data["courses"][1]["prerequisite_codes"] == ["CS101"]
    assert "prerequisites" not in data["courses"][1]


def test_normalize_hours_practical_alias():
    raw = ('{"outcomes": [], "courses": [{"code": "CS101", "title": "Intro Lab", "credits": 2,'
           ' "semester": 1, "is_elective": false, "hours_lab": 3, "prerequisite_codes": []}]}')
    data = _normalize_groq_structure(raw)
    assert data["courses"][0]["hours_practical"] == 3
    assert "hours_lab" not in data["courses"][0]


def test_normalize_display_order_alias():
    raw = ('{"outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "order": 2}],'
           ' "courses": [{"code": "CS101", "title": "Intro", "credits": 3, "semester": 1, "is_elective": false}]}')
    data = _normalize_groq_structure(raw)
    assert data["outcomes"][0]["display_order"] == 2
    assert "order" not in data["outcomes"][0]


def test_normalize_raises_on_invalid_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        _normalize_groq_structure("not json at all")


def test_normalize_raises_when_no_courses_recognisable():
    """A response carrying no courses at all must fail loudly, not return an
    empty structure — an empty program would otherwise be persisted as a
    successful generation, and the fallback chain would never try the next
    provider."""
    with pytest.raises(ValueError, match="no recognisable courses"):
        _normalize_groq_structure('{"outcomes": [], "courses": []}')


def test_normalize_programme_outcomes_british_spelling():
    """programme_outcomes (British) must map to outcomes."""
    raw = ('{"programme_outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}],'
           ' "courses": [{"code": "CS101", "title": "Intro", "credits": 3, "semester": 1, "is_elective": false}]}')
    data = _normalize_groq_structure(raw)
    assert "outcomes" in data
    assert "programme_outcomes" not in data
    assert len(data["outcomes"]) == 1


def test_normalize_course_name_to_title():
    """courses[].name must be renamed to title."""
    raw = '{"outcomes": [], "courses": [{"code": "CS101", "name": "Intro to CS", "credits": 4, "semester": 1, "is_elective": false, "description": "Intro.", "prerequisite_codes": []}]}'
    data = _normalize_groq_structure(raw)
    assert data["courses"][0]["title"] == "Intro to CS"
    assert "name" not in data["courses"][0]


def test_normalize_semester_inferred_from_code():
    """Missing semester is inferred from first digit of course code."""
    raw = '{"outcomes": [], "courses": [{"code": "CS501", "title": "Algorithms", "credits": 4, "is_elective": false, "description": "Advanced.", "prerequisite_codes": []}]}'
    data = _normalize_groq_structure(raw)
    assert data["courses"][0]["semester"] == 5


def test_normalize_semester_inferred_defaults_to_1_for_zero():
    """A code like CS001 (first digit 0) should yield semester 1, not 0."""
    raw = '{"outcomes": [], "courses": [{"code": "CS001", "title": "Intro", "credits": 3, "is_elective": false, "description": "Intro.", "prerequisite_codes": []}]}'
    data = _normalize_groq_structure(raw)
    assert data["courses"][0]["semester"] == 1


def test_normalize_description_synthesised_from_title():
    """Missing description is generated from title."""
    raw = '{"outcomes": [], "courses": [{"code": "CS301", "title": "Data Structures", "credits": 4, "semester": 3, "is_elective": false, "prerequisite_codes": []}]}'
    data = _normalize_groq_structure(raw)
    assert "description" in data["courses"][0]
    assert "Data Structures" in data["courses"][0]["description"]


def test_normalize_exact_failure_shape():
    """
    Regression test for the exact shape that caused the production failure:
      - programme_outcomes (British spelling)
      - courses[].name instead of title
      - missing semester (to be inferred from code CS501 -> 5)
      - missing description (to be synthesised from name/title)
    All fields the schema requires must be present after normalisation.
    """
    raw = """{
        "programme_outcomes": [
            {"code": "PO1", "description": "Apply algorithms", "bloom_level": "Apply", "display_order": 1},
            {"code": "PO2", "description": "Design systems", "bloom_level": "Create", "display_order": 2}
        ],
        "courses": [
            {
                "code": "CS501",
                "name": "Advanced Algorithms",
                "credits": 4,
                "is_elective": false,
                "hours_lecture": 3,
                "hours_tutorial": 1,
                "hours_practical": 0,
                "prerequisite_codes": ["CS301"]
            },
            {
                "code": "CS502",
                "name": "Compiler Design",
                "credits": 3,
                "is_elective": false,
                "hours_lecture": 3,
                "hours_tutorial": 0,
                "hours_practical": 2,
                "prerequisite_codes": []
            }
        ]
    }"""
    data = _normalize_groq_structure(raw)

    # top-level
    assert "outcomes" in data
    assert "programme_outcomes" not in data

    # every course has the required fields
    for c in data["courses"]:
        assert "title" in c, f"missing title in {c}"
        assert "name" not in c, f"name not removed from {c}"
        assert "semester" in c, f"missing semester in {c}"
        assert c["semester"] > 0, f"semester must be positive in {c}"
        assert "description" in c, f"missing description in {c}"
        assert c["description"], f"description is empty in {c}"
        assert "prerequisite_codes" in c

    # semester inference: CS501 -> 5, CS502 -> 5
    assert data["courses"][0]["semester"] == 5
    assert data["courses"][1]["semester"] == 5

    # title came from name
    assert data["courses"][0]["title"] == "Advanced Algorithms"
    assert data["courses"][1]["title"] == "Compiler Design"

    # description was synthesised
    assert "Advanced Algorithms" in data["courses"][0]["description"]
    assert "Compiler Design" in data["courses"][1]["description"]


def test_normalize_program_structure_wrapper_flat_courses():
    """program_structure wrapper with flat courses list is unwrapped correctly."""
    raw = """{
        "program_structure": {
            "outcomes": [
                {"code": "PO1", "description": "Apply CS", "bloom_level": "Apply", "display_order": 1}
            ],
            "courses": [
                {
                    "code": "CS101", "title": "Intro to CS", "credits": 4,
                    "semester": 1, "is_elective": false,
                    "hours_lecture": 3, "hours_tutorial": 1, "hours_practical": 0,
                    "description": "Foundation course.", "prerequisite_codes": []
                }
            ]
        }
    }"""
    data = _normalize_groq_structure(raw)
    assert "program_structure" not in data
    assert "outcomes" in data
    assert "courses" in data
    assert len(data["courses"]) == 1
    assert data["courses"][0]["title"] == "Intro to CS"


def test_normalize_program_structure_wrapper_semester_wise():
    """
    program_structure wrapper with semester-wise semesters list is flattened.
    Semester number is injected from semester_number into each course.
    """
    raw = """{
        "program_structure": {
            "programme_outcomes": [
                {"code": "PO1", "description": "Apply CS", "bloom_level": "Apply", "display_order": 1}
            ],
            "semesters": [
                {
                    "semester_number": 1,
                    "courses": [
                        {"code": "CS101", "name": "Intro to CS", "credits": 4, "is_elective": false,
                         "hours_lecture": 3, "hours_tutorial": 1, "hours_practical": 0,
                         "prerequisite_codes": []}
                    ]
                },
                {
                    "semester_number": 2,
                    "courses": [
                        {"code": "CS201", "name": "Data Structures", "credits": 4, "is_elective": false,
                         "hours_lecture": 3, "hours_tutorial": 1, "hours_practical": 2,
                         "prerequisite_codes": ["CS101"]}
                    ]
                }
            ]
        }
    }"""
    data = _normalize_groq_structure(raw)

    assert "program_structure" not in data
    assert "semesters" not in data
    assert "outcomes" in data
    assert len(data["courses"]) == 2

    c1, c2 = data["courses"]
    assert c1["semester"] == 1
    assert c2["semester"] == 2
    assert c1["title"] == "Intro to CS"
    assert c2["title"] == "Data Structures"
    assert "description" in c1 and c1["description"]
    assert "description" in c2 and c2["description"]


def test_normalize_nested_production_payload():
    """
    Regression test for the exact production payload shape from the Celery log:
      - top-level program_structure wrapper
      - programme_outcomes (British spelling) inside the wrapper
      - semester-wise semesters list (not a flat courses list)
      - each course has name instead of title, no description, no semester field
    All schema-required fields must be present after normalisation.
    """
    raw = """{
        "program_structure": {
            "programme_outcomes": [
                {"code": "PO1", "description": "Apply fundamental computing concepts to solve problems",
                 "bloom_level": "Apply", "display_order": 1},
                {"code": "PO2", "description": "Design and implement efficient algorithms",
                 "bloom_level": "Create", "display_order": 2}
            ],
            "semesters": [
                {
                    "semester_number": 1,
                    "courses": [
                        {"code": "CS101", "name": "Introduction to Programming", "credits": 4,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 1,
                         "hours_practical": 2, "prerequisite_codes": []},
                        {"code": "MATH101", "name": "Engineering Mathematics I", "credits": 4,
                         "is_elective": false, "hours_lecture": 4, "hours_tutorial": 0,
                         "hours_practical": 0, "prerequisite_codes": []}
                    ]
                },
                {
                    "semester_number": 5,
                    "courses": [
                        {"code": "CS501", "name": "Advanced Algorithms", "credits": 4,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 1,
                         "hours_practical": 0, "prerequisite_codes": ["CS301"]},
                        {"code": "CS502", "name": "Compiler Design", "credits": 3,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 0,
                         "hours_practical": 2, "prerequisite_codes": []}
                    ]
                }
            ]
        }
    }"""
    data = _normalize_groq_structure(raw)

    # wrapper removed
    assert "program_structure" not in data
    assert "semesters" not in data

    # outcomes extracted and British alias resolved
    assert "outcomes" in data
    assert "programme_outcomes" not in data
    assert len(data["outcomes"]) == 2

    # all 4 courses flattened
    assert len(data["courses"]) == 4

    # semester numbers preserved from semester_number
    semesters = [c["semester"] for c in data["courses"]]
    assert semesters == [1, 1, 5, 5]

    # every course meets schema requirements
    for c in data["courses"]:
        assert "title" in c,       f"missing title: {c}"
        assert "name" not in c,    f"name not removed: {c}"
        assert "semester" in c,    f"missing semester: {c}"
        assert c["semester"] > 0,  f"invalid semester: {c}"
        assert "description" in c, f"missing description: {c}"
        assert c["description"],   f"empty description: {c}"
        assert "prerequisite_codes" in c

    # spot-check title and description synthesis
    cs101 = next(c for c in data["courses"] if c["code"] == "CS101")
    assert cs101["title"] == "Introduction to Programming"
    assert "Introduction to Programming" in cs101["description"]

    cs501 = next(c for c in data["courses"] if c["code"] == "CS501")
    assert cs501["title"] == "Advanced Algorithms"
    assert cs501["semester"] == 5


def test_normalize_missing_outcomes_synthesises_four_fallbacks():
    """When outcomes are absent, 4 fallback POs must be synthesised."""
    raw = """{
        "program_structure": {
            "semesters": [
                {
                    "semester_number": 1,
                    "courses": [
                        {"code": "CS101", "name": "Intro to CS", "credits": 4,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 1,
                         "hours_practical": 0, "prerequisite_codes": []}
                    ]
                }
            ]
        }
    }"""
    data = _normalize_groq_structure(raw, department="Computer Science", degree_type="BCA")

    assert "outcomes" in data
    assert len(data["outcomes"]) >= 4
    for o in data["outcomes"]:
        assert "code" in o
        assert "description" in o and o["description"]
        assert "bloom_level" in o
        assert "display_order" in o
    # at least one outcome references the discipline
    descs = " ".join(o["description"] for o in data["outcomes"])
    assert "Computer Science" in descs or "BCA" in descs


def test_normalize_semester_wise_courses_key():
    """
    semester_wise_courses (new Groq variant) must be flattened identically to semesters.
    Shape: {"program_structure": {"semester_wise_courses": [{"semester": N, "courses": [...]}]}}
    """
    raw = """{
        "program_structure": {
            "programme_outcomes": [
                {"code": "PO1", "description": "Apply computing concepts to solve problems",
                 "bloom_level": "Apply", "display_order": 1}
            ],
            "semester_wise_courses": [
                {
                    "semester": 1,
                    "courses": [
                        {"code": "CS101", "name": "Intro to CS", "credits": 4,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 1,
                         "hours_practical": 0, "prerequisite_codes": []},
                        {"code": "MATH101", "name": "Engineering Maths I", "credits": 4,
                         "is_elective": false, "hours_lecture": 4, "hours_tutorial": 0,
                         "hours_practical": 0, "prerequisite_codes": []}
                    ]
                },
                {
                    "semester": 3,
                    "courses": [
                        {"code": "CS301", "name": "Data Structures", "credits": 4,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 1,
                         "hours_practical": 2, "prerequisite_codes": ["CS101"]}
                    ]
                }
            ]
        }
    }"""
    data = _normalize_groq_structure(raw)

    # wrapper and semester_wise_courses key removed
    assert "program_structure" not in data
    assert "semester_wise_courses" not in data
    assert "semesters" not in data

    # 3 courses flattened
    assert len(data["courses"]) == 3

    # semester injected from parent "semester" key
    sems = [c["semester"] for c in data["courses"]]
    assert sems == [1, 1, 3]

    # name → title
    for c in data["courses"]:
        assert "title" in c
        assert "name" not in c
        assert "description" in c and c["description"]


def test_normalize_semester_wise_courses_exact_failure_shape():
    """
    Regression test for the exact Groq response shape that triggered the
    'ValidationError: courses Field required' production error:
      program_structure wrapper + semester_wise_courses list with 'semester' key.
    After normalisation _ProgramStructureAI must validate cleanly.
    """
    from app.modules.m01_program_advisor.ai_provider import _ProgramStructureAI

    raw = """{
        "program_structure": {
            "semester_wise_courses": [
                {
                    "semester": 1,
                    "courses": [
                        {"code": "BCA101", "name": "Problem Solving using C", "credits": 4,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 1,
                         "hours_practical": 2, "prerequisite_codes": []},
                        {"code": "BCA102", "name": "Mathematics for Computing", "credits": 4,
                         "is_elective": false, "hours_lecture": 4, "hours_tutorial": 0,
                         "hours_practical": 0, "prerequisite_codes": []}
                    ]
                },
                {
                    "semester": 2,
                    "courses": [
                        {"code": "BCA201", "name": "Object Oriented Programming", "credits": 4,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 1,
                         "hours_practical": 2, "prerequisite_codes": ["BCA101"]},
                        {"code": "BCA202", "name": "Digital Electronics", "credits": 3,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 0,
                         "hours_practical": 0, "prerequisite_codes": []}
                    ]
                }
            ]
        }
    }"""
    data = _normalize_groq_structure(raw, department="Computer Applications", degree_type="BCA")

    # structure unwrapped
    assert "program_structure" not in data
    assert "semester_wise_courses" not in data

    # fallback outcomes synthesised (no outcomes in payload)
    assert len(data["outcomes"]) >= 4
    descs = " ".join(o["description"] for o in data["outcomes"])
    assert "Computer Applications" in descs or "BCA" in descs

    # 4 courses flattened with correct semesters
    assert len(data["courses"]) == 4
    assert [c["semester"] for c in data["courses"]] == [1, 1, 2, 2]

    # every course satisfies _CourseAI requirements
    for c in data["courses"]:
        assert "title" in c and c["title"]
        assert "name" not in c
        assert "description" in c and c["description"]
        assert "prerequisite_codes" in c

    # end-to-end Pydantic validation must pass
    parsed = _ProgramStructureAI.model_validate(data)
    assert len(parsed.courses) == 4
    assert len(parsed.outcomes) >= 4


def test_normalize_missing_outcomes_no_context():
    """Fallback outcomes must be valid even without department/degree_type."""
    raw = ('{"outcomes": null, "courses": [{"code": "CS101", "title": "Intro",'
           ' "credits": 3, "semester": 1, "is_elective": false}]}')
    data = _normalize_groq_structure(raw)
    assert len(data["outcomes"]) >= 4
    for o in data["outcomes"]:
        assert o["code"]
        assert o["description"]
        assert o["bloom_level"]


def test_normalize_missing_outcomes_exact_failure_shape():
    """
    Regression test for the exact production failure:
      program_structure wrapper + semesters list with NO outcomes key at all.
    After normalisation the document must satisfy _ProgramStructureAI
    (outcomes required, min 4).
    """
    raw = """{
        "program_structure": {
            "semesters": [
                {
                    "semester_number": 1,
                    "courses": [
                        {"code": "BCA101", "name": "Problem Solving using C", "credits": 4,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 1,
                         "hours_practical": 2, "prerequisite_codes": []},
                        {"code": "BCA102", "name": "Mathematics for Computing", "credits": 4,
                         "is_elective": false, "hours_lecture": 4, "hours_tutorial": 0,
                         "hours_practical": 0, "prerequisite_codes": []}
                    ]
                },
                {
                    "semester_number": 5,
                    "courses": [
                        {"code": "BCA501", "name": "Artificial Intelligence", "credits": 4,
                         "is_elective": false, "hours_lecture": 3, "hours_tutorial": 1,
                         "hours_practical": 2, "prerequisite_codes": ["BCA301"]},
                        {"code": "BCA502", "name": "Cloud Computing", "credits": 3,
                         "is_elective": true, "hours_lecture": 3, "hours_tutorial": 0,
                         "hours_practical": 2, "prerequisite_codes": []}
                    ]
                }
            ]
        }
    }"""
    data = _normalize_groq_structure(raw, department="Computer Applications", degree_type="BCA")

    # wrapper removed, outcomes synthesised
    assert "program_structure" not in data
    assert "semesters" not in data
    assert len(data["outcomes"]) >= 4

    # all required outcome fields present
    for o in data["outcomes"]:
        assert o.get("code")
        assert o.get("description")
        assert o.get("bloom_level")
        assert isinstance(o.get("display_order"), int)

    # 4 courses flattened with correct semesters and synthesised fields
    assert len(data["courses"]) == 4
    sem_values = [c["semester"] for c in data["courses"]]
    assert sem_values == [1, 1, 5, 5]
    for c in data["courses"]:
        assert "title" in c
        assert "description" in c and c["description"]

    # discipline referenced in at least one outcome
    descs = " ".join(o["description"] for o in data["outcomes"])
    assert "Computer Applications" in descs or "BCA" in descs


# ---------------------------------------------------------------------------
# Credit clamping
# ---------------------------------------------------------------------------

def test_normalize_credits_over_max_clamped():
    """Credits > 6 must be clamped to 6."""
    raw = """{
        "outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}],
        "courses": [
            {"code": "BCA602", "title": "Advanced Topics", "credits": 8,
             "semester": 6, "is_elective": false,
             "hours_lecture": 3, "hours_tutorial": 1, "hours_practical": 2,
             "description": "Advanced course.", "prerequisite_codes": []}
        ]
    }"""
    data = _normalize_groq_structure(raw)
    assert data["courses"][0]["credits"] == 6


def test_normalize_credits_under_min_clamped():
    """Credits < 1 must be clamped to 1."""
    raw = """{
        "outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}],
        "courses": [
            {"code": "CS101", "title": "Intro", "credits": 0,
             "semester": 1, "is_elective": false,
             "hours_lecture": 1, "hours_tutorial": 0, "hours_practical": 0,
             "description": "Intro course.", "prerequisite_codes": []}
        ]
    }"""
    data = _normalize_groq_structure(raw)
    assert data["courses"][0]["credits"] == 1


def test_normalize_credits_in_range_unchanged():
    """Credits within [1, 6] must not be modified."""
    raw = """{
        "outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}],
        "courses": [
            {"code": "CS301", "title": "Algorithms", "credits": 4,
             "semester": 3, "is_elective": false,
             "hours_lecture": 3, "hours_tutorial": 1, "hours_practical": 0,
             "description": "Algorithms course.", "prerequisite_codes": []}
        ]
    }"""
    data = _normalize_groq_structure(raw)
    assert data["courses"][0]["credits"] == 4


def test_normalize_credits_clamped_passes_pydantic():
    """Credits=8 clamped to 6 must allow _ProgramStructureAI validation to succeed."""
    raw = """{
        "outcomes": [{"code": "PO1", "description": "Apply computing", "bloom_level": "Apply", "display_order": 1}],
        "courses": [
            {"code": "BCA602", "title": "Advanced Topics", "credits": 8,
             "semester": 6, "is_elective": false,
             "hours_lecture": 3, "hours_tutorial": 1, "hours_practical": 2,
             "description": "Advanced course.", "prerequisite_codes": []}
        ]
    }"""
    data = _normalize_groq_structure(raw)
    parsed = _ProgramStructureAI.model_validate(data)
    assert parsed.courses[0].credits == 6


# ---------------------------------------------------------------------------
# course_type inference — labs paired with theory, project/internship credits
# ---------------------------------------------------------------------------

def _course_kwargs(**overrides):
    base = dict(
        code="CS501", title="Data Structures", credits=4, semester=5,
        is_elective=False, hours_lecture=3, hours_tutorial=1, hours_practical=0,
        description="x", prerequisite_codes=[],
    )
    base.update(overrides)
    return base


class TestInferCourseTypeFromTitle:

    def test_lab_keyword(self):
        assert _infer_course_type_from_title("Data Structures Lab") == "LAB"

    def test_laboratory_keyword(self):
        assert _infer_course_type_from_title("Physics Laboratory") == "LAB"

    def test_project_keyword(self):
        assert _infer_course_type_from_title("Major Project") == "PROJECT"

    def test_internship_keyword(self):
        assert _infer_course_type_from_title("Industrial Internship") == "INTERNSHIP"

    def test_seminar_keyword(self):
        assert _infer_course_type_from_title("Technical Seminar") == "SEMINAR"

    def test_default_is_theory(self):
        assert _infer_course_type_from_title("Data Structures") == "THEORY"


class TestCourseAICourseTypeValidator:

    def test_explicit_valid_type_preserved(self):
        c = _CourseAI(**_course_kwargs(title="Compiler Design", course_type="THEORY"))
        assert c.course_type == "THEORY"

    def test_missing_type_inferred_from_lab_title(self):
        c = _CourseAI(**_course_kwargs(title="Data Structures Lab"))
        assert c.course_type == "LAB"

    def test_invalid_type_falls_back_to_title_inference(self):
        c = _CourseAI(**_course_kwargs(title="Major Project", course_type="NOT_A_TYPE"))
        assert c.course_type == "PROJECT"

    def test_missing_type_non_lab_title_defaults_theory(self):
        c = _CourseAI(**_course_kwargs(title="Discrete Mathematics"))
        assert c.course_type == "THEORY"


class TestCourseAICodeAlias:
    """Regression coverage: the AI sometimes emits 'course_code' instead of
    the expected 'code' -- generation must not fail because of this alias,
    for either provider path (Gemini validates directly through _CourseAI;
    Groq/DeepSeek validate the same model after the text normalizer)."""

    def test_course_code_alias_accepted(self):
        kwargs = _course_kwargs(title="Operating Systems")
        kwargs.pop("code")
        c = _CourseAI(course_code="CS201", **kwargs)
        assert c.code == "CS201"

    def test_code_takes_precedence_when_both_present(self):
        kwargs = _course_kwargs(title="Operating Systems", code="CS201")
        c = _CourseAI(course_code="IGNORED", **kwargs)
        assert c.code == "CS201"

    def test_missing_both_code_and_course_code_still_raises(self):
        kwargs = _course_kwargs(title="Operating Systems")
        kwargs.pop("code")
        with pytest.raises(ValidationError):
            _CourseAI(**kwargs)


class TestNormalizeCourseTypeAndCreditRange:

    def test_lab_title_without_course_type_tagged_lab(self):
        raw = """{
            "outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}],
            "courses": [
                {"code": "CS502", "title": "Data Structures Lab", "credits": 2,
                 "semester": 5, "is_elective": false,
                 "hours_lecture": 0, "hours_tutorial": 0, "hours_practical": 4,
                 "description": "Lab course.", "prerequisite_codes": []}
            ]
        }"""
        data = _normalize_groq_structure(raw)
        assert data["courses"][0]["course_type"] == "LAB"

    def test_project_credits_not_clamped_to_six(self):
        """A 10-credit Major Project must not be clamped down to the theory-course max of 6."""
        raw = """{
            "outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}],
            "courses": [
                {"code": "CS800", "title": "Major Project", "credits": 10,
                 "semester": 8, "is_elective": false,
                 "hours_lecture": 0, "hours_tutorial": 0, "hours_practical": 20,
                 "description": "Capstone project.", "prerequisite_codes": []}
            ]
        }"""
        data = _normalize_groq_structure(raw)
        assert data["courses"][0]["course_type"] == "PROJECT"
        assert data["courses"][0]["credits"] == 10

    def test_project_credits_above_twenty_clamped(self):
        raw = """{
            "outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}],
            "courses": [
                {"code": "CS801", "title": "Internship", "credits": 25,
                 "semester": 8, "is_elective": false,
                 "hours_lecture": 0, "hours_tutorial": 0, "hours_practical": 30,
                 "description": "Internship.", "prerequisite_codes": []}
            ]
        }"""
        data = _normalize_groq_structure(raw)
        assert data["courses"][0]["credits"] == 20

    def test_theory_course_still_clamped_to_six(self):
        raw = """{
            "outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}],
            "courses": [
                {"code": "CS502", "title": "Advanced Algorithms", "credits": 9,
                 "semester": 5, "is_elective": false,
                 "hours_lecture": 4, "hours_tutorial": 1, "hours_practical": 0,
                 "description": "Theory course.", "prerequisite_codes": []}
            ]
        }"""
        data = _normalize_groq_structure(raw)
        assert data["courses"][0]["course_type"] == "THEORY"
        assert data["courses"][0]["credits"] == 6


# ---------------------------------------------------------------------------
# Provider response-shape regressions
#
# Groq and DeepSeek do not agree with each other, with Gemini, or with
# themselves between runs: the wrapper key, the semester-group key and the
# course field names all vary per sample at temperature 0.4. Every payload
# below was captured from a live call. The normalizer must land all of them on
# the canonical schema without knowing which provider sent them.
# ---------------------------------------------------------------------------

class TestProviderShapeRegressions:

    def _validate(self, raw: str) -> _ProgramStructureAI:
        data = _normalize_groq_structure(
            raw, provider="test", department="Computer Applications", degree_type="MCA"
        )
        return _ProgramStructureAI.model_validate(data)

    def test_deepseek_program_wrapper_with_course_code(self):
        """DeepSeek's live shape: a 'program' wrapper (never unwrapped by the old
        normalizer, which only knew 'program_structure') and 'course_code'."""
        raw = """{
            "program": {
                "degree_type": "MCA",
                "department": "Computer Applications",
                "duration_years": 2,
                "total_credits": 88,
                "semesters": [
                    {
                        "semester_number": 1,
                        "courses": [
                            {"course_code": "MCA101", "title": "Computer Systems",
                             "course_type": "THEORY", "credits": 4, "is_elective": false,
                             "elective_basket_name": null, "prerequisite_codes": []},
                            {"course_code": "MCA102", "title": "Computer Systems Lab",
                             "course_type": "LAB", "credits": 2, "is_elective": false,
                             "elective_basket_name": null, "prerequisite_codes": []}
                        ]
                    }
                ]
            }
        }"""
        parsed = self._validate(raw)
        assert [c.code for c in parsed.courses] == ["MCA101", "MCA102"]
        assert [c.semester for c in parsed.courses] == [1, 1]
        assert [c.course_type for c in parsed.courses] == ["THEORY", "LAB"]

    def test_groq_unknown_wrapper_and_semester_key(self):
        """Groq's live shape varies per sample. This one has NO wrapper the code
        has ever seen and calls the semester list 'semester_wise_structure' —
        the harvester must still find the courses by walking the document."""
        raw = """{
            "program_name": "MCA",
            "department": "Computer Applications",
            "duration": "2 years",
            "total_credits": 88,
            "semester_wise_structure": [
                {
                    "semester": 1,
                    "courses": [
                        {"code": "MCA101", "title": "Programming Fundamentals",
                         "credits": 4, "course_type": "THEORY", "is_elective": false,
                         "prerequisite_codes": []}
                    ]
                },
                {
                    "semester": 4,
                    "courses": [
                        {"code": "MCA401", "title": "Major Project", "credits": 12,
                         "course_type": "PROJECT", "is_elective": false,
                         "prerequisite_codes": []}
                    ]
                }
            ]
        }"""
        parsed = self._validate(raw)
        assert len(parsed.courses) == 2
        assert parsed.courses[0].semester == 1
        assert parsed.courses[1].semester == 4
        # a 12-credit project must not be clamped to the theory maximum of 6
        assert parsed.courses[1].credits == 12

    def test_course_title_alias(self):
        raw = """{
            "courses": [
                {"course_code": "CS101", "course_title": "Data Structures",
                 "credits": 4, "semester": 3, "is_elective": false}
            ]
        }"""
        parsed = self._validate(raw)
        assert parsed.courses[0].title == "Data Structures"
        assert parsed.courses[0].code == "CS101"

    def test_missing_is_elective_defaults_to_core(self):
        """is_elective is required by the schema but routinely omitted; a course
        with no elective signal at all is core, not a validation failure."""
        raw = '{"courses": [{"code": "CS101", "title": "Intro", "credits": 3, "semester": 1}]}'
        parsed = self._validate(raw)
        assert parsed.courses[0].is_elective is False
        assert parsed.courses[0].elective_basket_name is None

    def test_missing_credits_defaults_by_course_type(self):
        raw = '{"courses": [{"code": "CS102", "title": "Physics Lab", "semester": 1}]}'
        parsed = self._validate(raw)
        assert parsed.courses[0].course_type == "LAB"
        assert parsed.courses[0].credits == 2

    def test_elective_basket_nested_as_options(self):
        """Alternatives nested under a paper inherit the paper's name and are
        electives by construction, even with no is_elective flag on them."""
        raw = """{
            "semesters": [
                {
                    "sem": 3,
                    "core_courses": [
                        {"code": "MCA301", "title": "Cloud Computing", "credits": 4}
                    ],
                    "electives": [
                        {"basket_name": "Elective 1", "options": [
                            {"code": "MCA311", "title": "Artificial Intelligence", "credits": 3},
                            {"code": "MCA312", "title": "Machine Learning", "credits": 3}
                        ]},
                        {"basket_name": "Elective 2", "options": [
                            {"code": "MCA321", "title": "Data Mining", "credits": 3}
                        ]}
                    ]
                }
            ]
        }"""
        parsed = self._validate(raw)
        by_code = {c.code: c for c in parsed.courses}

        assert by_code["MCA301"].is_elective is False
        assert by_code["MCA301"].elective_basket_name is None

        for code in ("MCA311", "MCA312", "MCA321"):
            assert by_code[code].is_elective is True
            assert by_code[code].semester == 3

        # the two papers stay distinct — collapsing them loses a paper's credits
        assert by_code["MCA311"].elective_basket_name == "Elective 1"
        assert by_code["MCA312"].elective_basket_name == "Elective 1"
        assert by_code["MCA321"].elective_basket_name == "Elective 2"

    def test_elective_course_type_sets_is_elective(self):
        raw = """{
            "courses": [
                {"code": "CS390", "title": "Advanced Topics", "credits": 3,
                 "semester": 3, "category": "Elective"}
            ]
        }"""
        parsed = self._validate(raw)
        assert parsed.courses[0].is_elective is True
        assert parsed.courses[0].course_type == "THEORY"

    def test_string_values_and_markdown_fence(self):
        """Fenced JSON, string-typed numbers, 'Semester 3', and L/T/P hour keys."""
        raw = """```json
        {
            "courses": [
                {"Course Code": "IT301", "Course Title": "Database Systems",
                 "Credits": "4", "Semester": "Semester 3", "L": "3", "T": "1", "P": "2"}
            ]
        }
        ```"""
        parsed = self._validate(raw)
        c = parsed.courses[0]
        assert (c.code, c.title) == ("IT301", "Database Systems")
        assert c.credits == 4
        assert c.semester == 3
        assert (c.hours_lecture, c.hours_tutorial, c.hours_practical) == (3, 1, 2)

    def test_duplicate_course_codes_deduplicated(self):
        """A provider emitting both a flat list and a semester-grouped one would
        otherwise produce duplicate codes, which collide on the courses table's
        unique constraint and corrupt the worker's code->id map."""
        raw = """{
            "courses": [
                {"code": "CS101", "title": "Intro", "credits": 3, "semester": 1}
            ],
            "semesters": [
                {"semester": 1, "courses": [
                    {"code": "CS101", "title": "Intro", "credits": 3}
                ]}
            ]
        }"""
        parsed = self._validate(raw)
        assert [c.code for c in parsed.courses] == ["CS101"]

    def test_self_referencing_prerequisite_dropped(self):
        raw = """{
            "courses": [
                {"code": "CS201", "title": "Data Structures", "credits": 4, "semester": 2,
                 "prerequisite_codes": ["CS201", "CS101", "PHANTOM99"]},
                {"code": "CS101", "title": "Intro", "credits": 3, "semester": 1}
            ]
        }"""
        parsed = self._validate(raw)
        cs201 = next(c for c in parsed.courses if c.code == "CS201")
        # self-reference and the code of a course that does not exist are both gone
        assert cs201.prerequisite_codes == ["CS101"]

    def test_outcomes_aliased_and_bloom_synonyms(self):
        raw = """{
            "programme_outcomes": [
                {"po_code": "PO1", "statement": "Analyse computing problems",
                 "bloom": "Analyze", "order": 1},
                {"po_code": "PO2", "statement": "Build software systems",
                 "bloom": "Synthesis", "order": 2}
            ],
            "courses": [{"code": "CS101", "title": "Intro", "credits": 3, "semester": 1}]
        }"""
        parsed = self._validate(raw)
        assert [o.code for o in parsed.outcomes] == ["PO1", "PO2"]
        # American spelling and the pre-revision Bloom name resolve, not collapse to Apply
        assert parsed.outcomes[0].bloom_level == "Analyse"
        assert parsed.outcomes[1].bloom_level == "Create"

    def test_bare_outcome_strings(self):
        raw = """{
            "outcomes": ["Apply engineering knowledge", "Communicate effectively"],
            "courses": [{"code": "CS101", "title": "Intro", "credits": 3, "semester": 1}]
        }"""
        parsed = self._validate(raw)
        assert len(parsed.outcomes) == 2
        assert parsed.outcomes[0].code == "PO1"
        assert parsed.outcomes[1].code == "PO2"


# ---------------------------------------------------------------------------
# GroqStructureProvider — mocked API call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_groq_provider_returns_result_on_valid_response():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = _VALID_GROQ_JSON

    with (
        patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings,
        patch("openai.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_settings.GROQ_API_KEY = "test-key"
        mock_settings.GROQ_MODEL = "llama-3.3-70b-versatile"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai_cls.return_value = mock_client

        provider = GroqStructureProvider()
        result = await provider.generate_structure(_make_ctx())

    assert isinstance(result, ProgramStructureResult)
    assert result.model_used == "llama-3.3-70b-versatile"
    assert len(result.outcomes) == 1
    assert len(result.courses) == 1
    assert result.prompt_hash  # non-empty


@pytest.mark.asyncio
async def test_groq_provider_raises_when_key_missing():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings:
        mock_settings.GROQ_API_KEY = ""
        provider = GroqStructureProvider()
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            await provider.generate_structure(_make_ctx())


# ---------------------------------------------------------------------------
# FallbackStructureProvider — chain is Gemini → Groq → DeepSeek
# ---------------------------------------------------------------------------

def _fallback_with_stubs(**results):
    """FallbackStructureProvider whose chain is three stubs. Each kwarg is either
    a ProgramStructureResult to return or an Exception to raise."""
    provider = FallbackStructureProvider()
    stubs = {}
    for name in ("gemini", "groq", "deepseek"):
        stub = AsyncMock()
        outcome = results.get(name)
        stub.generate_structure = AsyncMock(
            side_effect=outcome if isinstance(outcome, Exception) else None,
            return_value=outcome if isinstance(outcome, ProgramStructureResult) else None,
        )
        stubs[name] = stub
    provider._chain = [(name, stubs[name]) for name in ("gemini", "groq", "deepseek")]
    return provider, stubs


def _result(provider_name: str, model: str) -> ProgramStructureResult:
    return ProgramStructureResult(
        outcomes=[], courses=[], model_used=model,
        provider_name=provider_name, prompt_hash="abc",
    )


@pytest.mark.asyncio
async def test_fallback_uses_gemini_first():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as s:
        s.AI_GEMINI_ENABLED = s.AI_GROQ_ENABLED = s.AI_DEEPSEEK_ENABLED = True
        s.GEMINI_API_KEY = s.GROQ_API_KEY = s.DEEPSEEK_API_KEY = "test-key"

        provider, stubs = _fallback_with_stubs(
            gemini=_result("gemini", "gemini-2.0-flash")
        )
        result = await provider.generate_structure(_make_ctx())

    assert result.provider_name == "gemini"
    stubs["gemini"].generate_structure.assert_called_once()
    stubs["groq"].generate_structure.assert_not_called()
    stubs["deepseek"].generate_structure.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_switches_to_groq_on_gemini_quota_error():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as s:
        s.AI_GEMINI_ENABLED = s.AI_GROQ_ENABLED = s.AI_DEEPSEEK_ENABLED = True
        s.GEMINI_API_KEY = s.GROQ_API_KEY = s.DEEPSEEK_API_KEY = "test-key"

        provider, stubs = _fallback_with_stubs(
            gemini=Exception("resource_exhausted: quota exceeded"),
            groq=_result("groq", "llama-3.3-70b-versatile"),
        )
        result = await provider.generate_structure(_make_ctx())

    assert result.provider_name == "groq"
    stubs["gemini"].generate_structure.assert_called_once()
    stubs["groq"].generate_structure.assert_called_once()
    stubs["deepseek"].generate_structure.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_reaches_deepseek_when_gemini_and_groq_fail():
    """The exact production situation: Gemini out of quota, Groq returning a
    shape that fails to normalise. DeepSeek must still carry the generation."""
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as s:
        s.AI_GEMINI_ENABLED = s.AI_GROQ_ENABLED = s.AI_DEEPSEEK_ENABLED = True
        s.GEMINI_API_KEY = s.GROQ_API_KEY = s.DEEPSEEK_API_KEY = "test-key"

        provider, stubs = _fallback_with_stubs(
            gemini=Exception("429 resource_exhausted"),
            groq=ValueError("groq response did not match the expected schema"),
            deepseek=_result("deepseek", "deepseek-chat"),
        )
        result = await provider.generate_structure(_make_ctx())

    assert result.provider_name == "deepseek"
    stubs["deepseek"].generate_structure.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_skips_providers_without_a_key():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as s:
        s.AI_GEMINI_ENABLED = s.AI_GROQ_ENABLED = s.AI_DEEPSEEK_ENABLED = True
        s.GEMINI_API_KEY = ""            # not configured — must be skipped, not called
        s.GROQ_API_KEY = s.DEEPSEEK_API_KEY = "test-key"

        provider, stubs = _fallback_with_stubs(
            groq=_result("groq", "llama-3.3-70b-versatile")
        )
        result = await provider.generate_structure(_make_ctx())

    assert result.provider_name == "groq"
    stubs["gemini"].generate_structure.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_raises_when_every_provider_fails():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as s:
        s.AI_GEMINI_ENABLED = s.AI_GROQ_ENABLED = s.AI_DEEPSEEK_ENABLED = True
        s.GEMINI_API_KEY = s.GROQ_API_KEY = s.DEEPSEEK_API_KEY = "test-key"

        provider, _ = _fallback_with_stubs(
            gemini=Exception("quota"),
            groq=ValueError("bad schema"),
            deepseek=ValueError("bad schema"),
        )
        with pytest.raises(RuntimeError, match="All AI providers failed"):
            await provider.generate_structure(_make_ctx())


# ---------------------------------------------------------------------------
# DeepSeekStructureProvider — mocked API call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deepseek_provider_normalizes_its_program_wrapper():
    """End-to-end through the provider: DeepSeek's live 'program' wrapper shape
    must reach ProgramStructureResult without a schema error."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = """{
        "program": {
            "semesters": [
                {"semester_number": 1, "courses": [
                    {"course_code": "MCA101", "title": "Computer Systems",
                     "course_type": "THEORY", "credits": 4, "is_elective": false,
                     "prerequisite_codes": []}
                ]}
            ]
        }
    }"""

    with (
        patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings,
        patch("openai.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_settings.DEEPSEEK_API_KEY = "test-key"
        mock_settings.DEEPSEEK_MODEL = "deepseek-chat"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai_cls.return_value = mock_client

        result = await DeepSeekStructureProvider().generate_structure(_make_ctx())

    assert result.provider_name == "deepseek"
    assert len(result.courses) == 1
    assert result.courses[0]["code"] == "MCA101"
    assert result.courses[0]["semester"] == 1
    # outcomes absent from the payload → fallback POs, never an empty list
    assert len(result.outcomes) >= 4


@contextlib.contextmanager
def _stub_genai(raw_text: str):
    """Stand in for the google-genai SDK, which GeminiStructureProvider imports
    lazily inside generate_structure. Returns `raw_text` as the model's reply."""
    response = MagicMock()
    response.text = raw_text

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(return_value=response)

    genai = MagicMock()
    genai.Client = MagicMock(return_value=client)

    google = types_mod.ModuleType("google")
    google.genai = genai
    with patch.dict(sys.modules, {
        "google": google,
        "google.genai": genai,
        "google.genai.types": MagicMock(),
    }):
        yield


@pytest.mark.asyncio
async def test_gemini_provider_normalizes_a_wrapped_response():
    """The regression this suite exists for.

    response_schema is a request, not a guarantee: Gemini is perfectly capable of
    wrapping the payload in "program" and grouping courses under semesters, and it
    does. Validating its text straight against _ProgramStructureAI — which is what
    used to happen, Gemini being the one provider that skipped the normalizer —
    turned that into `ValidationError: courses Field required` and, since Gemini
    leads the fallback chain, failed generation on curriculum data that was
    entirely valid. Gemini goes through the same normalizer as everyone else now.
    """
    raw = """{
        "program": {
            "semesters": [
                {"semester_number": 3, "courses": [
                    {"course_code": "MCA301", "course_title": "Data Structures",
                     "course_type": "THEORY", "credits": 4,
                     "hours_lecture": 3, "hours_tutorial": 1, "hours_practical": 0,
                     "prerequisites": []}
                ]}
            ]
        },
        "program_outcomes": [
            {"po_code": "PO1", "statement": "Apply computing knowledge.",
             "bloom_level": "Analyze"}
        ]
    }"""

    with (
        patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings,
        _stub_genai(raw),
    ):
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"

        result = await GeminiStructureProvider().generate_structure(_make_ctx())

    assert result.provider_name == "gemini"
    assert len(result.courses) == 1

    course = result.courses[0]
    assert course["code"] == "MCA301"              # course_code → code
    assert course["title"] == "Data Structures"    # course_title → title
    assert course["semester"] == 3                 # inherited from the semester group
    # Academic requirements survive normalization untouched.
    assert (course["hours_lecture"], course["hours_tutorial"],
            course["hours_practical"]) == (3, 1, 0)
    assert course["credits"] == 4

    # program_outcomes → outcomes, po_code → code, statement → description,
    # and "Analyze" resolves to the canonical Bloom spelling rather than defaulting.
    assert [o["code"] for o in result.outcomes] == ["PO1"]
    assert result.outcomes[0]["bloom_level"] == "Analyse"


@pytest.mark.asyncio
async def test_gemini_provider_passes_canonical_response_through_unchanged():
    """Normalizing Gemini must not cost a well-behaved response anything: a payload
    already matching response_schema has to survive byte-for-byte."""
    courses = [{
        "code": "CS101", "title": "Discrete Mathematics", "credits": 4,
        "semester": 1, "course_type": "THEORY", "is_elective": False,
        "elective_basket_name": None, "hours_lecture": 3, "hours_tutorial": 1,
        "hours_practical": 0, "description": "Sets, logic and graphs.",
        "prerequisite_codes": [],
    }]
    outcomes = [{
        "code": "PO1", "description": "Evaluate engineering designs.",
        "bloom_level": "Evaluate", "display_order": 1,
    }]

    with (
        patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings,
        _stub_genai(json.dumps({"outcomes": outcomes, "courses": courses})),
    ):
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"

        result = await GeminiStructureProvider().generate_structure(_make_ctx())

    assert result.courses == courses
    assert result.outcomes == outcomes


@pytest.mark.asyncio
async def test_deepseek_provider_raises_when_key_missing():
    with patch("app.modules.m01_program_advisor.ai_provider.settings") as mock_settings:
        mock_settings.DEEPSEEK_API_KEY = ""
        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
            await DeepSeekStructureProvider().generate_structure(_make_ctx())
