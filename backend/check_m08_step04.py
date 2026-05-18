"""STEP-04..06 smoke test — blooms_analyser, paper_sealer, question_generator."""

# ---- STEP-04: Bloom's analyser ----
from app.modules.m08_exam_setter.blooms_analyser import (
    compute_actual_distribution,
    check_compliance,
    BLOOM_LEVELS,
)

# All 6 levels present
assert len(BLOOM_LEVELS) == 6

# compute_actual_distribution: basic
questions = [
    {"bloom_level": "REMEMBER",   "marks": 20},
    {"bloom_level": "UNDERSTAND", "marks": 20},
    {"bloom_level": "APPLY",      "marks": 20},
    {"bloom_level": "ANALYSE",    "marks": 20},
    {"bloom_level": "EVALUATE",   "marks": 10},
    {"bloom_level": "CREATE",     "marks": 10},
]
dist = compute_actual_distribution(questions)
assert abs(dist["REMEMBER"]   - 20.0) < 0.5
assert abs(dist["UNDERSTAND"] - 20.0) < 0.5
assert abs(dist["APPLY"]      - 20.0) < 0.5
assert abs(dist["EVALUATE"]   - 10.0) < 0.5
assert abs(dist["CREATE"]     - 10.0) < 0.5

# empty questions → all zeros
empty = compute_actual_distribution([])
assert all(v == 0.0 for v in empty.values())

# check_compliance: within tolerance
requested = {lvl: v for lvl, v in zip(BLOOM_LEVELS, [20,20,20,20,10,10])}
actual    = {lvl: v for lvl, v in zip(BLOOM_LEVELS, [20,20,20,20,10,10])}
report = check_compliance(requested, actual, tolerance=5.0)
assert report.compliance_ok is True
assert len(report.violations) == 0

# check_compliance: exceeds tolerance
actual_bad = {lvl: v for lvl, v in zip(BLOOM_LEVELS, [40,10,20,20,5,5])}
report_bad = check_compliance(requested, actual_bad, tolerance=5.0)
assert report_bad.compliance_ok is False
assert len(report_bad.violations) > 0

# violations serialise
vlist = report_bad.to_violations_list()
assert all("level" in v and "delta_pct" in v for v in vlist)

print("STEP-04 (blooms_analyser): OK")

# ---- STEP-06: Paper sealer ----
from app.modules.m08_exam_setter.paper_sealer import seal, unseal

data = {
    "questions": [{"id": "q1", "text": "What is RAM?", "marks": 5}],
    "model_answers": [{"id": "q1", "answer": "Random Access Memory"}],
}

encrypted, key_ref = seal(data)
assert isinstance(encrypted, bytes)
assert len(encrypted) > 0
assert key_ref == "EXAM_FERNET_KEY"

recovered = unseal(encrypted, key_ref)
assert recovered["questions"][0]["text"] == "What is RAM?"
assert recovered["model_answers"][0]["answer"] == "Random Access Memory"

print("STEP-06 (paper_sealer): OK")

# ---- STEP-05: Question generator structure ----
from app.modules.m08_exam_setter.question_generator import (
    _mock_questions,
    _normalise_question,
    _build_prompt,
)

units = [
    {"unit_no": 1, "title": "Introduction to Python", "topics": ["variables", "loops"]},
    {"unit_no": 2, "title": "Functions",               "topics": ["def", "return"]},
]
bloom_targets = {"REMEMBER": 20, "UNDERSTAND": 20, "APPLY": 30, "ANALYSE": 20, "EVALUATE": 10, "CREATE": 0}
fmt           = {"mcq_count": 2, "short_count": 2, "long_count": 1, "problem_count": 0}
total_marks   = 29  # 2*2 + 2*5 + 1*10

mock_qs = _mock_questions(units, fmt, bloom_targets, total_marks)
assert len(mock_qs) == 5  # 2+2+1+0

for q in mock_qs:
    assert "bloom_level"   in q
    assert "question_type" in q
    assert "question_text" in q
    assert "marks"         in q
    assert "model_answer"  in q
    assert "set_membership" in q
    assert "marking_scheme" in q
    # MCQ must have options
    if q["question_type"] == "MCQ":
        assert q["options"] is not None
        assert q["correct_option"] is not None
    # Non-MCQ must not have options
    else:
        assert q["options"] is None

# Normalise a raw dict
raw = {
    "unit_number":   1,
    "bloom_level":   "apply",
    "question_type": "short answer",
    "question_text": "Explain recursion.",
    "marks":         5,
    "model_answer":  "A function calling itself...",
    "marking_scheme": [{"criterion":"Clarity","marks":3,"description":"Clear explanation"}],
    "set_membership": ["A","B"],
}
norm = _normalise_question(raw)
assert norm["bloom_level"]   == "APPLY"
assert norm["question_type"] == "SHORT_ANSWER"

# Prompt builder produces non-empty string
prompt = _build_prompt(units, bloom_targets, fmt, total_marks, "Focus on practical questions.")
assert len(prompt) > 100
assert "REMEMBER" in prompt or "apply" in prompt.lower()

print("STEP-05 (question_generator): OK")
print("All STEP-04..06 assertions passed.")
