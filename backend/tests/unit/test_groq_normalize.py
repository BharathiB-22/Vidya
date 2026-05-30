"""
Unit tests for _normalize_groq_response.

Uses the exact field shapes observed in live Groq (llama-3.3-70b-versatile)
output — no network calls, no DB, no env vars required.
"""
import json
import os
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("JWT_SECRET", "x")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "placeholder")

from app.modules.m02_syllabus.ai_provider import (
    SyllabusAIParseError,
    SyllabusAIValidationError,
    SyllabusGenerationContext,
    _SyllabusAI,
    _normalize_groq_response,
    _validate_result,
)

# ---------------------------------------------------------------------------
# Fixture 1: original observed Groq response shape (co alias)
# ---------------------------------------------------------------------------

_GROQ_RAW = json.dumps({
    "course_outcomes": [                          # alias: outcomes
        {
            "co": "Apply machine learning algorithms to real-world datasets",  # alias: description
            "bloom_level": "Apply",
            "suggested_po_codes": ["PO1", "PO2"],
            # code intentionally absent -> should become CO1
        },
        {
            "co": "Analyse and evaluate model performance using standard metrics",
            "bloom_level": "Analyse",
            "suggested_po_codes": ["PO3"],
        },
        {
            "co": "Design and implement neural network architectures for classification",
            "bloom_level": "Create",
            "suggested_po_codes": ["PO2"],
        },
        {
            "co": "Understand the theoretical foundations of supervised and unsupervised learning",
            "bloom_level": "Understand",
            "suggested_po_codes": ["PO1"],
        },
    ],
    "units": [
        {
            "unit_number": 1,
            "title": "Introduction to Machine Learning",
            "total_hours": 10,
            "pedagogy": "lecture",
            "topics": [                           # string topics -> objects
                "History and motivation of ML",
                "Types of learning: supervised, unsupervised, reinforcement",
                "Key terminology: features, labels, model, training",
            ],
        },
        {
            "display_order": 2,                   # alias: unit_number (absent)
            "title": "Linear Models",
            "total_hours": 8,
            "pedagogy": "lecture",
            "topics": ["Linear regression", "Logistic regression"],
        },
        {
            # unit_number absent, display_order absent -> sequential (3)
            "title": "Neural Networks",
            "total_hours": 12,
            "pedagogy": "lab",
            "topics": [{"title": "Perceptron"}, {"title": "Backpropagation"}],
        },
        {
            "unit_number": 4,
            "title": "Model Evaluation",
            "total_hours": 6,
            "pedagogy": "seminar",
            "topics": ["Cross-validation", "ROC curves"],
        },
    ],
    "reference_queries": [
        {"query": "machine learning fundamentals textbook", "ref_type": "TEXTBOOK"},   # alias
        {"query": "deep learning neural networks graduate", "ref_type": "REFERENCE"},
        {"query_str": "scikit-learn python machine learning", "ref_type": "TEXTBOOK"}, # canonical
        {"query": "statistical learning theory algorithms", "ref_type": "JOURNAL"},
        {"query": "reinforcement learning markov decision process", "ref_type": "TEXTBOOK"},
    ],
})


# ---------------------------------------------------------------------------
# Fixture 2: observed Groq response using co_statement / co_description aliases
# (the shape that broke generation after the initial normalization commit)
# ---------------------------------------------------------------------------

_GROQ_RAW_CO_STATEMENT = json.dumps({
    "course_outcomes": [
        {
            "co_id": "CO1",
            "co_statement": "Apply machine learning algorithms to real-world datasets",
            "co_description": "Students will apply supervised and unsupervised ML techniques",
            "bloom_level": "Apply",
            "suggested_po_codes": ["PO1", "PO2"],
            # code intentionally absent -> should become CO1
        },
        {
            "co_id": "CO2",
            "co_statement": "Analyse and evaluate model performance using standard metrics",
            "co_description": "Students will use ROC, F1, and cross-validation",
            "bloom_level": "Analyse",
            "suggested_po_codes": ["PO3"],
        },
        {
            "co_id": "CO3",
            "co_statement": "Design neural network architectures for classification",
            "co_description": "Students will implement CNNs and MLPs",
            "bloom_level": "Create",
            "suggested_po_codes": ["PO2"],
        },
        {
            "co_id": "CO4",
            "co_statement": "Understand theoretical foundations of supervised learning",
            "co_description": "Students will explain bias-variance tradeoff and regularisation",
            "bloom_level": "Understand",
            "suggested_po_codes": ["PO1"],
        },
    ],
    "units": [
        {
            "unit_number": 1,
            "title": "Introduction to Machine Learning",
            "total_hours": 10,
            "pedagogy": "lecture",
            "topics": ["History of ML", "Types of learning", "Key terminology"],
        },
        {
            "unit_number": 2,
            "title": "Linear Models",
            "total_hours": 8,
            "pedagogy": "lecture",
            "topics": ["Linear regression", "Logistic regression"],
        },
        {
            "unit_number": 3,
            "title": "Neural Networks",
            "total_hours": 12,
            "pedagogy": "lab",
            "topics": ["Perceptron", "Backpropagation"],
        },
        {
            "unit_number": 4,
            "title": "Model Evaluation",
            "total_hours": 6,
            "pedagogy": "seminar",
            "topics": ["Cross-validation", "ROC curves"],
        },
    ],
    "reference_queries": [
        {"query": "machine learning fundamentals textbook", "ref_type": "TEXTBOOK"},
        {"query": "deep learning neural networks", "ref_type": "REFERENCE"},
        {"query": "scikit-learn python", "ref_type": "TEXTBOOK"},
        {"query": "statistical learning theory", "ref_type": "JOURNAL"},
        {"query": "reinforcement learning markov", "ref_type": "TEXTBOOK"},
    ],
})


# ---------------------------------------------------------------------------
# Tests — Fixture 1 (co alias)
# ---------------------------------------------------------------------------

def test_normalize_top_level_key():
    result = _normalize_groq_response(_GROQ_RAW)
    assert "outcomes" in result
    assert "course_outcomes" not in result


def test_normalize_co_description_alias():
    result = _normalize_groq_response(_GROQ_RAW)
    for co in result["outcomes"]:
        assert "description" in co, f"CO missing description: {co}"
        assert "co" not in co


def test_normalize_co_codes_filled():
    result = _normalize_groq_response(_GROQ_RAW)
    codes = [co["code"] for co in result["outcomes"]]
    assert codes == ["CO1", "CO2", "CO3", "CO4"]


def test_normalize_string_topics_become_objects():
    result = _normalize_groq_response(_GROQ_RAW)
    unit1 = result["units"][0]
    for topic in unit1["topics"]:
        assert isinstance(topic, dict), f"Expected dict, got {type(topic)}"
        assert "title" in topic


def test_normalize_dict_topics_preserved():
    result = _normalize_groq_response(_GROQ_RAW)
    unit3 = result["units"][2]
    assert unit3["topics"] == [{"title": "Perceptron"}, {"title": "Backpropagation"}]


def test_normalize_unit_number_from_display_order():
    result = _normalize_groq_response(_GROQ_RAW)
    unit2 = result["units"][1]
    assert unit2["unit_number"] == 2
    assert "display_order" not in unit2


def test_normalize_unit_number_sequential_fallback():
    result = _normalize_groq_response(_GROQ_RAW)
    unit3 = result["units"][2]
    assert unit3["unit_number"] == 3


def test_normalize_query_str_alias():
    result = _normalize_groq_response(_GROQ_RAW)
    for rq in result["reference_queries"]:
        assert "query_str" in rq, f"reference query missing query_str: {rq}"
        assert "query" not in rq


def test_full_pydantic_validation_passes():
    normalized = _normalize_groq_response(_GROQ_RAW)
    parsed = _SyllabusAI.model_validate(normalized)
    assert len(parsed.outcomes) == 4
    assert len(parsed.units) == 4
    assert len(parsed.reference_queries) == 5
    assert all(co.code.startswith("CO") for co in parsed.outcomes)
    assert all(
        isinstance(t.title, str) and t.title
        for u in parsed.units
        for t in u.topics
    )


def test_invalid_json_raises_parse_error():
    with pytest.raises(SyllabusAIParseError, match="not valid JSON"):
        _normalize_groq_response("not json at all {{{")


def test_non_object_json_raises_parse_error():
    with pytest.raises(SyllabusAIParseError, match="not a JSON object"):
        _normalize_groq_response("[1, 2, 3]")


# ---------------------------------------------------------------------------
# Tests — Fixture 2 (co_statement / co_description aliases)
# ---------------------------------------------------------------------------

def test_co_statement_maps_to_description():
    """co_statement is the primary observed alias — must become description."""
    result = _normalize_groq_response(_GROQ_RAW_CO_STATEMENT)
    for co in result["outcomes"]:
        assert "description" in co, f"CO missing description: {co}"
        assert "co_statement" not in co, f"co_statement not removed: {co}"


def test_co_description_alias_removed():
    """co_description is a redundant alias — must be removed after co_statement wins."""
    result = _normalize_groq_response(_GROQ_RAW_CO_STATEMENT)
    for co in result["outcomes"]:
        assert "co_description" not in co, f"co_description not removed: {co}"


def test_co_id_does_not_become_description():
    """co_id must not bleed into description; code should be filled from co_id or sequential."""
    result = _normalize_groq_response(_GROQ_RAW_CO_STATEMENT)
    for co in result["outcomes"]:
        # description must be the human-readable statement, not the co_id string
        assert not co["description"].startswith("CO"), (
            f"description looks like a CO ID, not a statement: {co['description']}"
        )


def test_co_statement_codes_filled():
    """Codes absent in fixture — normalizer must fill CO1..CO4 sequentially."""
    result = _normalize_groq_response(_GROQ_RAW_CO_STATEMENT)
    codes = [co["code"] for co in result["outcomes"]]
    assert codes == ["CO1", "CO2", "CO3", "CO4"]


def test_co_statement_full_pydantic_validation_passes():
    """End-to-end: normalized co_statement shape validates through _SyllabusAI."""
    normalized = _normalize_groq_response(_GROQ_RAW_CO_STATEMENT)
    parsed = _SyllabusAI.model_validate(normalized)
    assert len(parsed.outcomes) == 4
    assert len(parsed.units) == 4
    assert len(parsed.reference_queries) == 5
    assert all(co.code.startswith("CO") for co in parsed.outcomes)
    # description must be long enough (>= 15 chars per _COAI schema)
    assert all(len(co.description) >= 15 for co in parsed.outcomes)


def test_four_units_pass_validation():
    """_validate_result accepts 4 units — matches service compliance threshold (BUG-002 fix)."""
    normalized = _normalize_groq_response(_GROQ_RAW)
    parsed = _SyllabusAI.model_validate(normalized)
    assert len(parsed.units) == 4

    ctx = SyllabusGenerationContext(
        course_id="00000000-0000-0000-0000-000000000001",
        course_code="CS101",
        course_title="Programming in C",
        course_credits=4,
        program_outcomes=[],
        custom_instructions=None,
    )
    violations = _validate_result(parsed, ctx)
    unit_violations = [v for v in violations if "unit" in v.lower()]
    assert unit_violations == [], f"4 units should pass validation; got: {unit_violations}"


def test_description_present_takes_priority():
    """If description is already present, co_statement must not overwrite it."""
    raw = json.dumps({
        "outcomes": [
            {
                "description": "Existing correct description with enough length",
                "co_statement": "Should be ignored",
                "bloom_level": "Apply",
                "code": "CO1",
                "suggested_po_codes": [],
            },
        ],
        "units": [
            {"unit_number": i, "title": f"Unit {i}", "total_hours": 6,
             "pedagogy": "lecture", "topics": [f"Topic {i}"]}
            for i in range(1, 5)
        ],
        "reference_queries": [
            {"query_str": f"search term {i} textbook undergraduate", "ref_type": "TEXTBOOK"}
            for i in range(1, 6)
        ],
    })
    result = _normalize_groq_response(raw)
    assert result["outcomes"][0]["description"] == "Existing correct description with enough length"
    assert "co_statement" not in result["outcomes"][0]


# ---------------------------------------------------------------------------
# Tests — unit title aliases (BUG-002 second root cause)
# Groq sometimes emits unit_name / unit_title / name instead of title.
# ---------------------------------------------------------------------------

def _make_unit_name_payload(title_field: str) -> str:
    """Build a minimal valid Groq payload where units use the given title alias."""
    return json.dumps({
        "outcomes": [
            {"code": f"CO{i}", "description": f"Students will demonstrate competency in area {i} through applied learning.",
             "bloom_level": "Apply", "suggested_po_codes": []}
            for i in range(1, 5)
        ],
        "units": [
            {title_field: f"Unit {i} Title", "unit_number": i, "total_hours": 6,
             "pedagogy": "lecture", "topics": [f"Topic {i}"]}
            for i in range(1, 5)
        ],
        "reference_queries": [
            {"query_str": f"programming fundamentals textbook {i}", "ref_type": "TEXTBOOK"}
            for i in range(1, 6)
        ],
    })


def test_unit_name_alias_maps_to_title():
    """unit_name -> title (exact alias observed in BUG-002 Celery logs)."""
    raw = _make_unit_name_payload("unit_name")
    result = _normalize_groq_response(raw)
    for unit in result["units"]:
        assert "title" in unit, f"unit missing title after normalization: {unit}"
        assert unit["title"].startswith("Unit ")
        assert "unit_name" not in unit


def test_unit_title_alias_maps_to_title():
    """unit_title -> title."""
    raw = _make_unit_name_payload("unit_title")
    result = _normalize_groq_response(raw)
    for unit in result["units"]:
        assert "title" in unit
        assert "unit_title" not in unit


def test_name_alias_maps_to_title():
    """name -> title (lowest-priority alias)."""
    raw = _make_unit_name_payload("name")
    result = _normalize_groq_response(raw)
    for unit in result["units"]:
        assert "title" in unit
        assert "name" not in unit


def test_unit_name_pydantic_validates():
    """Full pipeline: unit_name payload normalizes and passes _SyllabusAI validation."""
    raw = _make_unit_name_payload("unit_name")
    normalized = _normalize_groq_response(raw)
    parsed = _SyllabusAI.model_validate(normalized)
    assert len(parsed.units) == 4
    assert all(len(u.title) >= 3 for u in parsed.units)


def test_existing_title_not_overwritten_by_unit_name():
    """If title is already present, unit_name must not overwrite it."""
    units = [
        {"title": "Correct Title", "unit_name": "Should Be Ignored",
         "unit_number": 1, "total_hours": 6, "pedagogy": "lecture", "topics": []},
    ] + [
        {"unit_number": i, "title": f"Unit {i}", "total_hours": 6,
         "pedagogy": "lecture", "topics": []}
        for i in range(2, 5)
    ]
    raw = json.dumps({
        "outcomes": [
            {"code": f"CO{i}", "description": f"Demonstrate competency in area {i} through applied work.",
             "bloom_level": "Apply", "suggested_po_codes": []}
            for i in range(1, 5)
        ],
        "units": units,
        "reference_queries": [
            {"query_str": f"c programming textbook {i}", "ref_type": "TEXTBOOK"}
            for i in range(1, 6)
        ],
    })
    result = _normalize_groq_response(raw)
    assert result["units"][0]["title"] == "Correct Title"
    assert "unit_name" not in result["units"][0]


# ---------------------------------------------------------------------------
# Tests — total_hours aliases (BUG-002 third root cause)
# Groq sometimes uses hours / contact_hours / teaching_hours instead of total_hours.
# ---------------------------------------------------------------------------

def _make_hours_alias_payload(hours_field: str, hours_value: Any = 10) -> str:
    return json.dumps({
        "outcomes": [
            {"code": f"CO{i}", "description": f"Demonstrate competency in area {i} through applied work.",
             "bloom_level": "Apply", "suggested_po_codes": []}
            for i in range(1, 5)
        ],
        "units": [
            {"unit_number": i, "title": f"Unit {i}", hours_field: hours_value,
             "pedagogy": "lecture", "topics": [f"Topic {i}"]}
            for i in range(1, 5)
        ],
        "reference_queries": [
            {"query_str": f"programming textbook {i}", "ref_type": "TEXTBOOK"}
            for i in range(1, 6)
        ],
    })


def test_hours_alias_maps_to_total_hours():
    """hours -> total_hours."""
    raw = _make_hours_alias_payload("hours", 8)
    result = _normalize_groq_response(raw)
    for unit in result["units"]:
        assert unit.get("total_hours") == 8, f"expected total_hours=8, got: {unit}"
        assert "hours" not in unit


def test_contact_hours_alias_maps_to_total_hours():
    """contact_hours -> total_hours."""
    raw = _make_hours_alias_payload("contact_hours", 12)
    result = _normalize_groq_response(raw)
    for unit in result["units"]:
        assert unit.get("total_hours") == 12


def test_teaching_hours_alias_maps_to_total_hours():
    """teaching_hours -> total_hours."""
    raw = _make_hours_alias_payload("teaching_hours", 10)
    result = _normalize_groq_response(raw)
    for unit in result["units"]:
        assert unit.get("total_hours") == 10


def test_missing_total_hours_falls_back_to_default():
    """When total_hours and all aliases are absent, a positive default is used."""
    raw = json.dumps({
        "outcomes": [
            {"code": f"CO{i}", "description": f"Demonstrate competency in area {i} through applied work.",
             "bloom_level": "Apply", "suggested_po_codes": []}
            for i in range(1, 5)
        ],
        "units": [
            {"unit_number": i, "title": f"Unit {i}", "pedagogy": "lecture",
             "topics": [f"Topic {i}"]}   # no total_hours, no alias
            for i in range(1, 5)
        ],
        "reference_queries": [
            {"query_str": f"programming textbook {i}", "ref_type": "TEXTBOOK"}
            for i in range(1, 6)
        ],
    })
    result = _normalize_groq_response(raw)
    for unit in result["units"]:
        assert unit.get("total_hours", 0) >= 1, f"total_hours must be >= 1, got: {unit}"


def test_hours_alias_full_pydantic_validation():
    """End-to-end: hours alias normalizes and passes _SyllabusAI validation."""
    raw = _make_hours_alias_payload("hours", 10)
    normalized = _normalize_groq_response(raw)
    parsed = _SyllabusAI.model_validate(normalized)
    assert len(parsed.units) == 4
    assert all(u.total_hours >= 1 for u in parsed.units)


# ---------------------------------------------------------------------------
# Tests — top-level key aliases for units and reference_queries
# ---------------------------------------------------------------------------

def test_course_units_alias_maps_to_units():
    """course_units -> units at top level."""
    raw = json.dumps({
        "outcomes": [
            {"code": f"CO{i}", "description": f"Apply learning in domain area {i} with practical depth.",
             "bloom_level": "Apply", "suggested_po_codes": []}
            for i in range(1, 5)
        ],
        "course_units": [
            {"unit_number": i, "title": f"Unit {i}", "total_hours": 6,
             "pedagogy": "lecture", "topics": []}
            for i in range(1, 5)
        ],
        "reference_queries": [
            {"query_str": f"textbook {i}", "ref_type": "TEXTBOOK"}
            for i in range(1, 6)
        ],
    })
    result = _normalize_groq_response(raw)
    assert "units" in result
    assert "course_units" not in result
    assert len(result["units"]) == 4


def test_online_learning_resources_alias_maps_to_reference_queries():
    """online_learning_resources -> reference_queries at top level."""
    raw = json.dumps({
        "outcomes": [
            {"code": f"CO{i}", "description": f"Apply learning in domain area {i} with practical depth.",
             "bloom_level": "Apply", "suggested_po_codes": []}
            for i in range(1, 5)
        ],
        "units": [
            {"unit_number": i, "title": f"Unit {i}", "total_hours": 6,
             "pedagogy": "lecture", "topics": []}
            for i in range(1, 5)
        ],
        "online_learning_resources": [
            {"query_str": f"programming resource {i}", "ref_type": "TEXTBOOK"}
            for i in range(1, 4)
        ],
    })
    result = _normalize_groq_response(raw)
    assert "reference_queries" in result
    assert "online_learning_resources" not in result
    assert len(result["reference_queries"]) == 3


def test_topic_title_alias_in_unit():
    """topic_title inside a unit's topics dict -> title."""
    raw = json.dumps({
        "outcomes": [
            {"code": f"CO{i}", "description": f"Apply learning in domain area {i} with practical depth.",
             "bloom_level": "Apply", "suggested_po_codes": []}
            for i in range(1, 5)
        ],
        "units": [
            {"unit_number": 1, "title": "Intro to C", "total_hours": 8, "pedagogy": "lecture",
             "topics": [
                 {"topic_title": "Variables and Types", "description": "Basic C types"},
                 {"topic_title": "Control Flow", "description": "if/else/loops"},
             ]},
        ] + [
            {"unit_number": i, "title": f"Unit {i}", "total_hours": 6,
             "pedagogy": "lecture", "topics": []}
            for i in range(2, 5)
        ],
        "reference_queries": [
            {"query_str": f"c programming textbook {i}", "ref_type": "TEXTBOOK"}
            for i in range(1, 6)
        ],
    })
    result = _normalize_groq_response(raw)
    for topic in result["units"][0]["topics"]:
        assert "title" in topic, f"topic missing title: {topic}"
        assert "topic_title" not in topic
