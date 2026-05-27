"""
Unit tests for M01 ai_provider — pure-Python, no DB, no real API calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m01_program_advisor.ai_provider import (
    GroqStructureProvider,
    GeminiStructureProvider,
    FallbackStructureProvider,
    ProgramGenerationContext,
    ProgramStructureResult,
    _normalize_groq_structure,
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
# Normalizer tests
# ---------------------------------------------------------------------------

def test_normalize_canonical_keys_unchanged():
    data = _normalize_groq_structure(_VALID_GROQ_JSON)
    assert "outcomes" in data
    assert "courses" in data


def test_normalize_program_outcomes_alias():
    raw = '{"program_outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}], "courses": []}'
    data = _normalize_groq_structure(raw)
    assert "outcomes" in data
    assert "program_outcomes" not in data


def test_normalize_course_list_alias():
    raw = '{"outcomes": [], "course_list": []}'
    data = _normalize_groq_structure(raw)
    assert "courses" in data
    assert "course_list" not in data


def test_normalize_prerequisite_aliases():
    raw = '{"outcomes": [], "courses": [{"prerequisites": ["CS101"], "hours_practical": 0}]}'
    data = _normalize_groq_structure(raw)
    assert data["courses"][0]["prerequisite_codes"] == ["CS101"]
    assert "prerequisites" not in data["courses"][0]


def test_normalize_hours_practical_alias():
    raw = '{"outcomes": [], "courses": [{"hours_lab": 3, "prerequisite_codes": []}]}'
    data = _normalize_groq_structure(raw)
    assert data["courses"][0]["hours_practical"] == 3
    assert "hours_lab" not in data["courses"][0]


def test_normalize_display_order_alias():
    raw = '{"outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "order": 2}], "courses": []}'
    data = _normalize_groq_structure(raw)
    assert data["outcomes"][0]["display_order"] == 2
    assert "order" not in data["outcomes"][0]


def test_normalize_raises_on_invalid_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        _normalize_groq_structure("not json at all")


def test_normalize_programme_outcomes_british_spelling():
    """programme_outcomes (British) must map to outcomes."""
    raw = '{"programme_outcomes": [{"code": "PO1", "description": "x", "bloom_level": "Apply", "display_order": 1}], "courses": []}'
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
    raw = '{"outcomes": null, "courses": []}'
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
    import json
    from app.modules.m01_program_advisor.ai_provider import _ProgramStructureAI
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
# FallbackStructureProvider — Groq quota triggers Gemini fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_uses_groq_first():
    groq_result = ProgramStructureResult(
        outcomes=[], courses=[], model_used="llama-3.3-70b-versatile", prompt_hash="abc"
    )

    provider = FallbackStructureProvider()
    provider._groq = AsyncMock()
    provider._groq.generate_structure = AsyncMock(return_value=groq_result)
    provider._gemini = AsyncMock()

    result = await provider.generate_structure(_make_ctx())

    provider._groq.generate_structure.assert_called_once()
    provider._gemini.generate_structure.assert_not_called()
    assert result.model_used == "llama-3.3-70b-versatile"


@pytest.mark.asyncio
async def test_fallback_switches_to_gemini_on_quota_error():
    gemini_result = ProgramStructureResult(
        outcomes=[], courses=[], model_used="gemini-2.0-flash", prompt_hash="def"
    )

    provider = FallbackStructureProvider()
    provider._groq = AsyncMock()
    provider._groq.generate_structure = AsyncMock(
        side_effect=Exception("resource_exhausted: quota exceeded")
    )
    provider._gemini = AsyncMock()
    provider._gemini.generate_structure = AsyncMock(return_value=gemini_result)

    result = await provider.generate_structure(_make_ctx())

    provider._groq.generate_structure.assert_called_once()
    provider._gemini.generate_structure.assert_called_once()
    assert result.model_used == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_fallback_does_not_swallow_non_quota_groq_errors():
    provider = FallbackStructureProvider()
    provider._groq = AsyncMock()
    provider._groq.generate_structure = AsyncMock(
        side_effect=ValueError("schema validation failed")
    )
    provider._gemini = AsyncMock()

    with pytest.raises(ValueError, match="schema validation failed"):
        await provider.generate_structure(_make_ctx())

    provider._gemini.generate_structure.assert_not_called()
