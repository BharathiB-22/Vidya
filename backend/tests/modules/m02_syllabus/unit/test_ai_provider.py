"""
Unit tests for _normalize_groq_response in M02 AI provider.
Exercises alias mapping and empty-description fallback logic without hitting any API.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.modules.m02_syllabus.ai_provider import (
    SyllabusAIParseError,
    _COAI,
    _normalize_groq_response,
)

# ---------------------------------------------------------------------------
# Shared fixtures — minimal valid units and reference_queries so normalizer
# passes without needing a full _SyllabusAI parse in every test.
# ---------------------------------------------------------------------------

_UNITS = [
    {
        "unit_number": i,
        "title": f"Unit {i}",
        "total_hours": 6,
        "pedagogy": "lecture",
        "topics": [{"title": "Topic A"}],
    }
    for i in range(1, 5)
]

_REFS = [{"query_str": "machine learning textbook", "ref_type": "TEXTBOOK"}]


def _raw(outcomes: list[dict]) -> str:
    return json.dumps({"outcomes": outcomes, "units": _UNITS, "reference_queries": _REFS})


# ---------------------------------------------------------------------------
# description normalization
# ---------------------------------------------------------------------------

def test_empty_description_falls_back_to_co_alias():
    """description:'' should be replaced by the 'co' alias when co has content."""
    raw = _raw([{
        "code": "CO1",
        "description": "",
        "co": "Apply neural networks to solve classification problems effectively",
        "bloom_level": "APPLY",
        "suggested_po_codes": [],
    }])
    result = _normalize_groq_response(raw)
    co = result["outcomes"][0]
    assert co["description"] == "Apply neural networks to solve classification problems effectively"
    assert "co" not in co


def test_missing_description_filled_from_co_statement():
    """Absent description key should be filled from co_statement."""
    raw = _raw([{
        "code": "CO2",
        "co_statement": "Design algorithms for data-intensive applications at scale",
        "bloom_level": "CREATE",
        "suggested_po_codes": [],
    }])
    result = _normalize_groq_response(raw)
    co = result["outcomes"][0]
    assert co["description"] == "Design algorithms for data-intensive applications at scale"
    assert "co_statement" not in co


def test_description_alias_priority_co_statement_before_co():
    """co_statement should take priority over the generic 'co' alias."""
    raw = _raw([{
        "code": "CO1",
        "description": "",
        "co_statement": "Analyse security vulnerabilities using penetration testing frameworks",
        "co": "Should not be used",
        "bloom_level": "ANALYSE",
        "suggested_po_codes": [],
    }])
    result = _normalize_groq_response(raw)
    co = result["outcomes"][0]
    assert co["description"] == "Analyse security vulnerabilities using penetration testing frameworks"


def test_an_empty_outcome_is_never_invented():
    """When every alias is empty, NOTHING is put in the outcome's place.

    The normaliser used to manufacture one — "CO3: demonstrate competency through
    Analyse-level mastery of core concepts" — so that the response would satisfy the
    schema. It did satisfy the schema. It also meant a Course Outcome that no model
    wrote and no academic chose could reach an approved syllabus, be locked into a
    regulation, and become the thing a student is examined against, with nobody ever
    knowing it had been invented in a normaliser.

    An empty outcome is a FAILED generation, to be retried. It is not a blank to fill.
    """
    raw = _raw([{
        "code": "CO3",
        "description": "",
        "co": "   ",          # whitespace only
        "co_statement": "",
        "bloom_level": "ANALYSE",
        "suggested_po_codes": [],
    }])
    result = _normalize_groq_response(raw)
    co = result["outcomes"][0]

    assert not str(co.get("description", "")).strip()
    assert co["code"] == "CO3"

    # And it does not survive validation: the schema wants a real outcome, so the whole
    # response is rejected and regenerated rather than saved with a hollow one.
    with pytest.raises(ValidationError):
        _COAI.model_validate(co)


def test_a_missing_outcome_is_never_invented():
    """No description key and no alias keys → nothing is fabricated for it either."""
    raw = _raw([{
        "code": "CO4",
        "bloom_level": "EVALUATE",
        "suggested_po_codes": ["PO1"],
    }])
    result = _normalize_groq_response(raw)
    co = result["outcomes"][0]

    assert not str(co.get("description", "")).strip()
    with pytest.raises(ValidationError):
        _COAI.model_validate(co)


def test_valid_description_unchanged():
    """A description meeting the min_length requirement must not be modified."""
    description = "Apply deep learning techniques to solve real-world computer vision problems."
    raw = _raw([{
        "code": "CO1",
        "description": description,
        "bloom_level": "APPLY",
        "suggested_po_codes": [],
    }])
    result = _normalize_groq_response(raw)
    assert result["outcomes"][0]["description"] == description


# ---------------------------------------------------------------------------
# bloom alias
# ---------------------------------------------------------------------------

def test_bloom_alias_renamed_to_bloom_level():
    """'bloom' key should be renamed to 'bloom_level' and original key removed."""
    raw = _raw([{
        "code": "CO1",
        "description": "Apply machine learning techniques to classify real-world datasets.",
        "bloom": "APPLY",
        "suggested_po_codes": [],
    }])
    result = _normalize_groq_response(raw)
    co = result["outcomes"][0]
    assert "bloom_level" in co
    assert co["bloom_level"] == "APPLY"
    assert "bloom" not in co


def test_bloom_level_wins_over_bloom_alias():
    """When both 'bloom' and 'bloom_level' are present, 'bloom_level' is kept."""
    raw = _raw([{
        "code": "CO1",
        "description": "Evaluate model performance using cross-validation and statistical tests.",
        "bloom_level": "EVALUATE",
        "bloom": "REMEMBER",
        "suggested_po_codes": [],
    }])
    result = _normalize_groq_response(raw)
    co = result["outcomes"][0]
    assert co["bloom_level"] == "EVALUATE"
    assert "bloom" not in co


# ---------------------------------------------------------------------------
# course_outcomes alias
# ---------------------------------------------------------------------------

def test_course_outcomes_key_renamed_to_outcomes():
    """Top-level 'course_outcomes' should be renamed to 'outcomes'."""
    data = {
        "course_outcomes": [{
            "code": "CO1",
            "description": "Apply data structures to implement efficient algorithms efficiently.",
            "bloom_level": "APPLY",
            "suggested_po_codes": [],
        }],
        "units": _UNITS,
        "reference_queries": _REFS,
    }
    result = _normalize_groq_response(json.dumps(data))
    assert "outcomes" in result
    assert "course_outcomes" not in result
    assert len(result["outcomes"]) == 1


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------

def test_invalid_json_raises_parse_error():
    with pytest.raises(SyllabusAIParseError, match="not valid JSON"):
        _normalize_groq_response("{not: json}")


def test_non_object_json_raises_parse_error():
    with pytest.raises(SyllabusAIParseError, match="not a JSON object"):
        _normalize_groq_response('["just", "an", "array"]')
