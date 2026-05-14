"""
Smoke tests for STEP-05: M03 AI Provider Protocol + providers.

Run from backend/:
    $env:PYTHONPATH="."
    $env:DATABASE_URL="postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya"
    $env:JWT_SECRET="test"
    $env:GROQ_API_KEY="test"
    python smoke_m03_step05.py
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("AI_PROVIDER", "groq")

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        FAIL += 1


# ---------------------------------------------------------------------------
# Import check
# ---------------------------------------------------------------------------
print("\n--- Import ---")
try:
    from app.modules.m03_course_kit.ai_provider import (
        CourseKitAIError,
        CourseKitAIBlockedError,
        CourseKitAIParseError,
        CourseKitAIValidationError,
        COContext,
        KitGenerationContext,
        SlideAI,
        QuizletAI,
        AssignmentAI,
        KitGenerationResult,
        CourseKitProvider,
        GeminiCourseKitProvider,
        GroqCourseKitProvider,
        FallbackCourseKitProvider,
        get_kit_provider,
        _KitAI,
        _validate_result,
        _normalize_groq_kit_response,
        _scan_slide_answer_leak,
    )
    check("Module imports cleanly (no DB/AI SDK needed at import time)", True)
except Exception as exc:
    check(f"Module import failed: {exc}", False)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------
print("\n--- Exception hierarchy ---")
check("CourseKitAIBlockedError is-a CourseKitAIError",
      issubclass(CourseKitAIBlockedError, CourseKitAIError))
check("CourseKitAIParseError is-a CourseKitAIError",
      issubclass(CourseKitAIParseError, CourseKitAIError))
check("CourseKitAIValidationError is-a CourseKitAIError",
      issubclass(CourseKitAIValidationError, CourseKitAIError))

# ---------------------------------------------------------------------------
# Protocol check
# ---------------------------------------------------------------------------
print("\n--- Protocol (runtime_checkable) ---")
check("GeminiCourseKitProvider satisfies CourseKitProvider",
      isinstance(GeminiCourseKitProvider(), CourseKitProvider))
check("GroqCourseKitProvider satisfies CourseKitProvider",
      isinstance(GroqCourseKitProvider(), CourseKitProvider))
check("FallbackCourseKitProvider satisfies CourseKitProvider",
      isinstance(FallbackCourseKitProvider(), CourseKitProvider))

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
print("\n--- Factory (get_kit_provider) ---")
import app.config as _cfg_mod

orig_provider = _cfg_mod.settings.AI_PROVIDER

_cfg_mod.settings.AI_PROVIDER = "groq"
check("get_kit_provider('groq') returns GroqCourseKitProvider",
      isinstance(get_kit_provider(), GroqCourseKitProvider))

_cfg_mod.settings.AI_PROVIDER = "gemini"
check("get_kit_provider('gemini') returns GeminiCourseKitProvider",
      isinstance(get_kit_provider(), GeminiCourseKitProvider))

_cfg_mod.settings.AI_PROVIDER = "fallback"
check("get_kit_provider('fallback') returns FallbackCourseKitProvider",
      isinstance(get_kit_provider(), FallbackCourseKitProvider))

_cfg_mod.settings.AI_PROVIDER = orig_provider

# ---------------------------------------------------------------------------
# IO dataclasses
# ---------------------------------------------------------------------------
print("\n--- IO dataclasses ---")

co = COContext(code="CO1", description="Understand fundamentals", bloom_level="UNDERSTAND")
check("COContext instantiation", co.code == "CO1" and co.bloom_level == "UNDERSTAND")

ctx = KitGenerationContext(
    kit_id="abc",
    unit_number=1,
    unit_title="Introduction to Python",
    unit_topics=["Variables", "Loops"],
    course_code="CS101",
    course_title="Programming Fundamentals",
    complexity_level="UG",
    tone="academic",
    custom_instructions=None,
    cos=[co],
    min_slides=8,
    min_quizlets=2,
)
check("KitGenerationContext instantiation", ctx.unit_number == 1 and ctx.min_slides == 8)

# ---------------------------------------------------------------------------
# _validate_result — valid minimal kit
# ---------------------------------------------------------------------------
print("\n--- _validate_result: valid minimal kit ---")

def _make_valid_kit(n_slides: int = 8, n_quizlets: int = 2) -> _KitAI:
    from app.modules.m03_course_kit.ai_provider import (
        _KitAI, _SlideAI, _SlideContentAI, _QuizletAI, _QuizletOptionAI,
        _AssignmentAI, _TeachingWeekAI, _LessonSessionAI, _ResourceItemAI,
    )
    slides = [
        _SlideAI(
            slide_number=i + 1,
            title=f"Slide {i + 1}",
            content=_SlideContentAI(bullets=["Point A", "Point B"], key_concepts=["concept"]),
            speaker_notes="Notes here",
        )
        for i in range(n_slides)
    ]
    quizlets = [
        _QuizletAI(
            question_number=i + 1,
            question_text=f"What is concept {i + 1}?",
            question_type="MCQ",
            options=[
                _QuizletOptionAI(label="A", text="Option A"),
                _QuizletOptionAI(label="B", text="Option B"),
                _QuizletOptionAI(label="C", text="Option C"),
                _QuizletOptionAI(label="D", text="Option D"),
            ],
            answer_key={"correct": "A"},
        )
        for i in range(n_quizlets)
    ]
    assignments = [
        _AssignmentAI(
            assignment_number=1,
            title="Classwork Task",
            assignment_type="CLASSWORK",
            question_text="Describe the main concepts covered in this unit.",
            complexity_level="UG",
        )
    ]
    teaching_plan = [
        _TeachingWeekAI(week=1, topic="Introduction", hours=3)
    ]
    lesson_plans = [
        _LessonSessionAI(session=1, week=1, topic="Introduction")
    ]
    resources = [
        _ResourceItemAI(title="Python Docs", resource_type="website")
    ]
    return _KitAI(
        slides=slides,
        quizlets=quizlets,
        assignments=assignments,
        teaching_plan=teaching_plan,
        lesson_plans=lesson_plans,
        resources=resources,
    )


valid_kit = _make_valid_kit()
violations = _validate_result(valid_kit, ctx)
check("Valid minimal kit: no violations", len(violations) == 0)

# ---------------------------------------------------------------------------
# _validate_result — too few slides
# ---------------------------------------------------------------------------
print("\n--- _validate_result: violations ---")

short_slides_kit = _make_valid_kit(n_slides=3, n_quizlets=2)
violations = _validate_result(short_slides_kit, ctx)
check("Too few slides detected", any("slides" in v for v in violations))

short_quizlets_kit = _make_valid_kit(n_slides=8, n_quizlets=1)
violations = _validate_result(short_quizlets_kit, ctx)
check("Too few quizlets detected", any("quizlets" in v for v in violations))

# ---------------------------------------------------------------------------
# Safety contract: answer-key leakage into slide content
# ---------------------------------------------------------------------------
print("\n--- Safety contract: answer_key leakage ---")

from app.modules.m03_course_kit.ai_provider import _SlideAI, _SlideContentAI

clean_slide = _SlideAI(
    slide_number=1,
    title="Variables in Python",
    content=_SlideContentAI(
        bullets=["Variables hold data", "Use descriptive names"],
        key_concepts=["variable", "assignment"],
    ),
)
check("Clean slide: no leakage detected", len(_scan_slide_answer_leak([clean_slide])) == 0)

leaky_slide = _SlideAI(
    slide_number=2,
    title="Quiz Review",
    content=_SlideContentAI(
        bullets=["Correct answer: A is the right option", "answer key: A=True"],
        key_concepts=["quiz answer"],
    ),
)
check("Leaky slide: answer_key leak detected",
      len(_scan_slide_answer_leak([leaky_slide])) > 0)

# ---------------------------------------------------------------------------
# Groq normalizer
# ---------------------------------------------------------------------------
print("\n--- Groq normalizer ---")

import json

# Test 1: top-level alias normalisation
groq_aliased = json.dumps({
    "slide_deck": [{"slide_number": 1, "title": "Intro", "content": {"bullets": []}}],
    "quiz_questions": [
        {
            "question_number": 1,
            "question_text": "What is a variable?",
            "question_type": "MCQ",
            "options": ["A number", "A name for data", "A loop", "A function"],
            "answer": "B",
            "answer_explanation": "Variables are named storage.",
        }
    ],
    "tasks": [
        {
            "assignment_number": 1,
            "title": "Task One",
            "assignment_type": "CLASSWORK",
            "question_text": "Describe variables in Python.",
        }
    ],
})
normalized = _normalize_groq_kit_response(groq_aliased)
check("Groq normalizer: slide_deck becomes slides", "slides" in normalized)
check("Groq normalizer: quiz_questions becomes quizlets", "quizlets" in normalized)
check("Groq normalizer: tasks becomes assignments", "assignments" in normalized)

# Test 2: answer string becomes dict
quizlet = normalized["quizlets"][0]
check("Groq normalizer: answer string becomes answer_key dict",
      isinstance(quizlet.get("answer_key"), dict))
check("Groq normalizer: answer_key has 'correct' key",
      "correct" in quizlet.get("answer_key", {}))

# Test 3: MCQ options list[str] becomes list[{label, text}]
opts = quizlet.get("options", [])
check("Groq normalizer: string options become {label, text} dicts",
      all(isinstance(o, dict) and "label" in o and "text" in o for o in opts))
check("Groq normalizer: option labels are A/B/C/D",
      [o["label"] for o in opts] == ["A", "B", "C", "D"])

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"STEP-05 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL — fix issues above before committing.")
    sys.exit(1)
else:
    print("ALL PASS — STEP-05 smoke tests green.")
