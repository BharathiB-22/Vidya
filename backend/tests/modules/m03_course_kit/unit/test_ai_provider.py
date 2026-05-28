"""
Unit tests for M03 AI provider helpers — pure functions, no DB, no network.

Covers:
  - _SlideContentAI: field parsing and defaults for all rich content fields
  - _infer_slide_type: inference fallback when AI omits slide_type
  - _enrich_slide_content: ensures slide_type is always present after enrichment
  - _scan_slide_answer_leak: covers all text fields including new enriched ones
  - _validate_result: end-to-end validation catches leakage + counts
  - _salvage_parsed_kit: deduplication and MCQ answer_key repair
  - _is_soft_violation: classifier for recoverable validation violations
"""
from __future__ import annotations

import pytest

from app.modules.m03_course_kit.ai_provider import (
    COContext,
    KitGenerationContext,
    _KitAI,
    _SlideAI,
    _SlideContentAI,
    _QuizletAI,
    _AssignmentAI,
    _enrich_slide_content,
    _infer_slide_type,
    _scan_slide_answer_leak,
    _validate_result,
    _build_result,
    _salvage_parsed_kit,
    _is_soft_violation,
    _VALID_SLIDE_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(**overrides) -> KitGenerationContext:
    defaults = dict(
        kit_id="kit-001",
        unit_number=1,
        unit_title="Introduction",
        unit_topics=["Topic A", "Topic B"],
        course_code="CS101",
        course_title="Intro to CS",
        complexity_level="UG",
        tone="academic",
        custom_instructions=None,
        cos=[COContext(code="CO1", description="Understand basics", bloom_level="UNDERSTAND")],
        min_slides=2,
        min_quizlets=1,
    )
    defaults.update(overrides)
    return KitGenerationContext(**defaults)


def _make_slide(
    slide_number: int = 1,
    title: str = "Test Slide",
    **content_kwargs,
) -> _SlideAI:
    content = _SlideContentAI(**content_kwargs)
    return _SlideAI(slide_number=slide_number, title=title, content=content)


def _make_mcq(question_number: int = 1) -> _QuizletAI:
    return _QuizletAI(
        question_number=question_number,
        question_text="What is the capital of France?",
        question_type="MCQ",
        options=[
            {"label": "A", "text": "Berlin"},
            {"label": "B", "text": "Paris"},
        ],
        answer_key={"correct": "B"},
        answer_explanation="Paris is the capital.",
    )


def _make_assignment(assignment_number: int = 1) -> _AssignmentAI:
    return _AssignmentAI(
        assignment_number=assignment_number,
        title="Write a short essay",
        assignment_type="HOMEWORK",
        question_text="Explain the concept in 200 words.",
        complexity_level="UG",
        rubric=[{"criterion": "Clarity", "description": "Clear argument", "max_marks": 5}],
    )


# ---------------------------------------------------------------------------
# _SlideContentAI: field parsing
# ---------------------------------------------------------------------------

class TestSlideContentAI:

    def test_all_rich_fields_accepted(self):
        c = _SlideContentAI(
            slide_type="CONCEPT",
            bullets=["Point A", "Point B"],
            key_concepts=["Term1"],
            definitions=["Term1 is defined as X"],
            examples=["Real-world example Y"],
            code_snippet="print('hello')",
            diagram_prompt="Draw a flowchart showing A → B",
            classroom_activity="In pairs, discuss X for 5 minutes",
            teaching_notes="Start with a question to engage students",
            student_summary="This slide covers the basics of X",
        )
        assert c.slide_type == "CONCEPT"
        assert len(c.bullets) == 2
        assert len(c.definitions) == 1
        assert len(c.examples) == 1
        assert c.code_snippet == "print('hello')"
        assert c.classroom_activity is not None
        assert c.teaching_notes is not None
        assert c.student_summary is not None

    def test_defaults_for_missing_fields(self):
        c = _SlideContentAI()
        assert c.slide_type is None
        assert c.bullets == []
        assert c.key_concepts == []
        assert c.definitions == []
        assert c.examples == []
        assert c.code_snippet is None
        assert c.diagram_prompt is None
        assert c.classroom_activity is None
        assert c.teaching_notes is None
        assert c.student_summary is None

    def test_slide_type_normalised_to_uppercase(self):
        c = _SlideContentAI(slide_type="concept")
        assert c.slide_type == "CONCEPT"

    def test_invalid_slide_type_becomes_none(self):
        c = _SlideContentAI(slide_type="LECTURE")
        assert c.slide_type is None

    def test_all_valid_slide_types_accepted(self):
        for st in _VALID_SLIDE_TYPES:
            c = _SlideContentAI(slide_type=st)
            assert c.slide_type == st

    def test_model_dump_includes_populated_fields(self):
        c = _SlideContentAI(
            slide_type="CODE",
            bullets=["Step 1"],
            code_snippet="x = 1",
        )
        d = c.model_dump(exclude_none=True)
        assert d["slide_type"] == "CODE"
        assert d["bullets"] == ["Step 1"]
        assert d["code_snippet"] == "x = 1"
        # Empty lists are included
        assert "key_concepts" in d

    def test_model_dump_excludes_none_fields(self):
        c = _SlideContentAI(bullets=["A"])
        d = c.model_dump(exclude_none=True)
        assert "slide_type" not in d
        assert "code_snippet" not in d
        assert "classroom_activity" not in d


# ---------------------------------------------------------------------------
# _infer_slide_type
# ---------------------------------------------------------------------------

class TestInferSlideType:

    def test_slide_number_1_is_title(self):
        assert _infer_slide_type(1, "Introduction", False) == "TITLE"

    def test_has_code_returns_code(self):
        assert _infer_slide_type(3, "Variables", True) == "CODE"

    def test_summary_keyword(self):
        assert _infer_slide_type(5, "Unit Summary", False) == "SUMMARY"

    def test_recap_keyword(self):
        assert _infer_slide_type(10, "Recap and Review", False) == "SUMMARY"

    def test_quiz_keyword(self):
        assert _infer_slide_type(8, "Quiz Time", False) == "QUIZ"

    def test_activity_keyword(self):
        assert _infer_slide_type(6, "Group Activity", False) == "ACTIVITY"

    def test_diagram_keyword(self):
        assert _infer_slide_type(4, "System Diagram", False) == "DIAGRAM"

    def test_example_keyword(self):
        assert _infer_slide_type(3, "Example: File I/O", False) == "EXAMPLE"

    def test_definition_keyword(self):
        assert _infer_slide_type(2, "Definitions", False) == "DEFINITION"

    def test_default_is_concept(self):
        assert _infer_slide_type(3, "Deep Dive into Memory", False) == "CONCEPT"

    def test_slide_1_overrides_code(self):
        # slide_number=1 wins over has_code
        assert _infer_slide_type(1, "Welcome", True) == "TITLE"


# ---------------------------------------------------------------------------
# _enrich_slide_content
# ---------------------------------------------------------------------------

class TestEnrichSlideContent:

    def test_slide_type_preserved_when_provided(self):
        slide = _make_slide(slide_number=2, title="Key Concepts", slide_type="DEFINITION")
        d = _enrich_slide_content(slide)
        assert d["slide_type"] == "DEFINITION"

    def test_slide_type_inferred_when_missing(self):
        slide = _make_slide(slide_number=1, title="Unit Overview")
        d = _enrich_slide_content(slide)
        assert d["slide_type"] == "TITLE"

    def test_slide_type_inferred_from_code_presence(self):
        slide = _make_slide(slide_number=3, title="Variables", code_snippet="x = 42")
        d = _enrich_slide_content(slide)
        assert d["slide_type"] == "CODE"

    def test_all_rich_fields_in_dump(self):
        slide = _make_slide(
            slide_number=2,
            title="The Stack",
            slide_type="CONCEPT",
            bullets=["B1", "B2"],
            definitions=["Stack: LIFO data structure"],
            examples=["Call stack in function execution"],
            classroom_activity="Draw a stack with 3 elements",
            teaching_notes="Emphasise LIFO order with a physical stack of books",
            student_summary="A stack is like a pile of plates",
        )
        d = _enrich_slide_content(slide)
        assert d["slide_type"] == "CONCEPT"
        assert d["definitions"] == ["Stack: LIFO data structure"]
        assert d["examples"] == ["Call stack in function execution"]
        assert d["classroom_activity"] == "Draw a stack with 3 elements"
        assert d["teaching_notes"] == "Emphasise LIFO order with a physical stack of books"
        assert d["student_summary"] == "A stack is like a pile of plates"


# ---------------------------------------------------------------------------
# _scan_slide_answer_leak
# ---------------------------------------------------------------------------

class TestScanSlideAnswerLeak:

    def test_no_violations_for_clean_slide(self):
        slide = _make_slide(
            bullets=["Lists are ordered", "Sets are unordered"],
            key_concepts=["list", "set"],
        )
        assert _scan_slide_answer_leak([slide]) == []

    def test_detects_leak_in_bullets(self):
        slide = _make_slide(bullets=["The answer_key is B"])
        violations = _scan_slide_answer_leak([slide])
        assert len(violations) == 1
        assert "answer_key" in violations[0].lower() or "answer-key" in violations[0].lower()

    def test_detects_leak_in_key_concepts(self):
        slide = _make_slide(key_concepts=["correct answer: B"])
        violations = _scan_slide_answer_leak([slide])
        assert len(violations) == 1

    def test_detects_leak_in_definitions(self):
        slide = _make_slide(definitions=["The answer key: {correct: A}"])
        violations = _scan_slide_answer_leak([slide])
        assert len(violations) == 1

    def test_detects_leak_in_examples(self):
        slide = _make_slide(examples=["For example, the correct answer: C is wrong"])
        violations = _scan_slide_answer_leak([slide])
        assert len(violations) == 1

    def test_detects_leak_in_classroom_activity(self):
        slide = _make_slide(classroom_activity="Check answer_key before discussing")
        violations = _scan_slide_answer_leak([slide])
        assert len(violations) == 1

    def test_detects_leak_in_teaching_notes(self):
        slide = _make_slide(teaching_notes="Tell students the correct answer: A")
        violations = _scan_slide_answer_leak([slide])
        assert len(violations) == 1

    def test_detects_leak_in_speaker_notes(self):
        slide = _make_slide()
        slide_with_notes = slide.model_copy(update={"speaker_notes": "answer_key is here"})
        violations = _scan_slide_answer_leak([slide_with_notes])
        assert len(violations) == 1

    def test_accumulates_multiple_slides(self):
        s1 = _make_slide(slide_number=1, bullets=["answer_key leaked"])
        s2 = _make_slide(slide_number=2, bullets=["clean slide"])
        violations = _scan_slide_answer_leak([s1, s2])
        assert len(violations) == 1  # only s1


# ---------------------------------------------------------------------------
# _validate_result
# ---------------------------------------------------------------------------

class TestValidateResult:

    def _make_kit_ai(self, slides, quizlets, assignments=None) -> _KitAI:
        return _KitAI(
            slides=slides,
            quizlets=quizlets,
            assignments=assignments or [],
        )

    def test_valid_kit_passes(self):
        ctx = _make_ctx(min_slides=2, min_quizlets=1)
        kit = self._make_kit_ai(
            slides=[_make_slide(1), _make_slide(2)],
            quizlets=[_make_mcq(1)],
        )
        errors = _validate_result(kit, ctx)
        assert errors == []

    def test_too_few_slides_is_error(self):
        ctx = _make_ctx(min_slides=3, min_quizlets=1)
        kit = self._make_kit_ai(
            slides=[_make_slide(1)],
            quizlets=[_make_mcq(1)],
        )
        errors = _validate_result(kit, ctx)
        assert any("slides" in e.lower() for e in errors)

    def test_too_few_quizlets_is_error(self):
        ctx = _make_ctx(min_slides=1, min_quizlets=2)
        kit = self._make_kit_ai(
            slides=[_make_slide(1)],
            quizlets=[_make_mcq(1)],
        )
        errors = _validate_result(kit, ctx)
        assert any("quizlet" in e.lower() for e in errors)

    def test_duplicate_slide_numbers_is_error(self):
        ctx = _make_ctx(min_slides=1, min_quizlets=0)
        kit = self._make_kit_ai(
            slides=[_make_slide(1), _make_slide(1)],
            quizlets=[],
        )
        errors = _validate_result(kit, ctx)
        assert any("duplicate" in e.lower() for e in errors)

    def test_answer_key_in_definitions_is_error(self):
        ctx = _make_ctx(min_slides=1, min_quizlets=0)
        slide = _make_slide(definitions=["The answer_key for question 1 is B"])
        kit = self._make_kit_ai(slides=[slide], quizlets=[])
        errors = _validate_result(kit, ctx)
        assert any("answer" in e.lower() for e in errors)

    def test_mcq_missing_options_is_error(self):
        ctx = _make_ctx(min_slides=1, min_quizlets=1)
        bad_mcq = _QuizletAI(
            question_number=1,
            question_text="Which is correct?",
            question_type="MCQ",
            options=[{"label": "A", "text": "Only one option"}],
            answer_key={"correct": "A"},
        )
        kit = self._make_kit_ai(slides=[_make_slide(1)], quizlets=[bad_mcq])
        errors = _validate_result(kit, ctx)
        assert any("option" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# _build_result: integration smoke
# ---------------------------------------------------------------------------

class TestBuildResult:

    def test_build_result_enriches_slide_type(self):
        kit = _KitAI(
            slides=[
                _make_slide(1, "Overview"),
                _make_slide(2, "Core Concepts"),
            ],
            quizlets=[_make_mcq(1)],
            assignments=[_make_assignment(1)],
        )
        result = _build_result(kit, model_used="test-model", prompt_hash="abc123")
        # Slide 1 should get TITLE inferred
        assert result.slides[0].content.get("slide_type") == "TITLE"
        # Slide 2 gets CONCEPT by default
        assert result.slides[1].content.get("slide_type") == "CONCEPT"

    def test_build_result_preserves_explicit_slide_type(self):
        kit = _KitAI(
            slides=[
                _make_slide(2, "Live Coding Demo", slide_type="CODE", code_snippet="x=1"),
            ],
            quizlets=[_make_mcq(1)],
            assignments=[],
        )
        result = _build_result(kit, model_used="test-model", prompt_hash="abc123")
        assert result.slides[0].content.get("slide_type") == "CODE"

    def test_build_result_includes_definitions_and_examples(self):
        kit = _KitAI(
            slides=[
                _make_slide(
                    1, "Intro",
                    definitions=["Def A"],
                    examples=["Ex 1"],
                    classroom_activity="Group discussion",
                    student_summary="You learned X",
                )
            ],
            quizlets=[_make_mcq(1)],
            assignments=[],
        )
        result = _build_result(kit, model_used="test-model", prompt_hash="abc123")
        c = result.slides[0].content
        assert c["definitions"] == ["Def A"]
        assert c["examples"] == ["Ex 1"]
        assert c["classroom_activity"] == "Group discussion"
        assert c["student_summary"] == "You learned X"


# ---------------------------------------------------------------------------
# _salvage_parsed_kit
# ---------------------------------------------------------------------------

class TestSalvageParsedKit:

    def test_no_changes_on_clean_kit(self):
        kit = _KitAI(
            slides=[_make_slide(1), _make_slide(2)],
            quizlets=[_make_mcq(1)],
            assignments=[],
        )
        warns = _salvage_parsed_kit(kit)
        assert warns == []
        assert len(kit.slides) == 2
        assert kit.slides[0].slide_number == 1
        assert kit.slides[1].slide_number == 2

    def test_deduplicates_slides_keeps_first(self):
        kit = _KitAI(
            slides=[_make_slide(1, "First"), _make_slide(1, "Duplicate")],
            quizlets=[_make_mcq(1)],
            assignments=[],
        )
        warns = _salvage_parsed_kit(kit)
        assert len(kit.slides) == 1
        assert kit.slides[0].title == "First"
        assert any("duplicate" in w.lower() for w in warns)

    def test_renumbers_slides_sequentially_after_dedup(self):
        kit = _KitAI(
            slides=[_make_slide(3, "Concept Slide"), _make_slide(7, "Summary Slide")],
            quizlets=[_make_mcq(1)],
            assignments=[],
        )
        _salvage_parsed_kit(kit)
        assert kit.slides[0].slide_number == 1
        assert kit.slides[1].slide_number == 2

    def test_deduplicates_quizlets(self):
        kit = _KitAI(
            slides=[_make_slide(1)],
            quizlets=[_make_mcq(1), _make_mcq(1)],
            assignments=[],
        )
        warns = _salvage_parsed_kit(kit)
        assert len(kit.quizlets) == 1
        assert any("duplicate" in w.lower() for w in warns)

    def test_renumbers_quizlets_sequentially(self):
        kit = _KitAI(
            slides=[_make_slide(1)],
            quizlets=[_make_mcq(5), _make_mcq(9)],
            assignments=[],
        )
        _salvage_parsed_kit(kit)
        assert kit.quizlets[0].question_number == 1
        assert kit.quizlets[1].question_number == 2

    def test_fixes_mcq_empty_answer_key_uses_first_option(self):
        mcq = _QuizletAI(
            question_number=1,
            question_text="Which is the capital?",
            question_type="MCQ",
            options=[{"label": "A", "text": "Berlin"}, {"label": "B", "text": "Paris"}],
            answer_key={},
        )
        kit = _KitAI(slides=[_make_slide(1)], quizlets=[mcq], assignments=[])
        warns = _salvage_parsed_kit(kit)
        assert kit.quizlets[0].answer_key == {"correct": "A"}
        assert any("inferred" in w.lower() or "answer_key" in w.lower() for w in warns)

    def test_fixes_mcq_empty_answer_key_no_options(self):
        mcq = _QuizletAI(
            question_number=1,
            question_text="Which is correct?",
            question_type="MCQ",
            options=[],
            answer_key={},
        )
        kit = _KitAI(slides=[_make_slide(1)], quizlets=[mcq], assignments=[])
        _salvage_parsed_kit(kit)
        assert kit.quizlets[0].answer_key == {"correct": "A"}

    def test_short_answer_empty_answer_key_not_modified(self):
        sa = _QuizletAI(
            question_number=1,
            question_text="Explain the concept in 2-3 sentences.",
            question_type="SHORT_ANSWER",
            options=[],
            answer_key={},
        )
        kit = _KitAI(slides=[_make_slide(1)], quizlets=[sa], assignments=[])
        warns = _salvage_parsed_kit(kit)
        assert kit.quizlets[0].answer_key == {}
        assert warns == []

    def test_mcq_with_valid_answer_key_not_overwritten(self):
        kit = _KitAI(
            slides=[_make_slide(1)],
            quizlets=[_make_mcq(1)],
            assignments=[],
        )
        original_key = kit.quizlets[0].answer_key.copy()
        _salvage_parsed_kit(kit)
        assert kit.quizlets[0].answer_key == original_key


# ---------------------------------------------------------------------------
# _is_soft_violation
# ---------------------------------------------------------------------------

class TestIsSoftViolation:

    def test_min_slide_count_is_soft(self):
        assert _is_soft_violation(
            "AI returned 5 slides; minimum required is 8 (M03_MIN_SLIDES_PER_UNIT)."
        )

    def test_min_quizlet_count_is_soft(self):
        assert _is_soft_violation(
            "AI returned 1 quizlets; minimum required is 2 (M03_MIN_QUIZLETS_PER_UNIT)."
        )

    def test_answer_leak_is_soft(self):
        assert _is_soft_violation(
            "Slide 3 'Introduction' appears to contain answer-key content (matched: ['answer_key'])."
        )

    def test_duplicate_slide_numbers_is_soft(self):
        assert _is_soft_violation("Duplicate slide_number values in AI response.")

    def test_duplicate_question_numbers_is_soft(self):
        assert _is_soft_violation("Duplicate question_number values in AI quizlets.")

    def test_mcq_empty_answer_key_is_soft(self):
        assert _is_soft_violation(
            "Quizlet 2 has an empty answer_key. "
            "answer_key must never be empty (DB NOT NULL constraint)."
        )

    def test_mcq_insufficient_options_is_soft(self):
        assert _is_soft_violation(
            "Quizlet 1 is MCQ but has fewer than 2 options."
        )

    def test_empty_string_is_hard(self):
        assert not _is_soft_violation("")

    def test_generic_critical_error_is_hard(self):
        assert not _is_soft_violation("Some unknown critical error occurred.")
