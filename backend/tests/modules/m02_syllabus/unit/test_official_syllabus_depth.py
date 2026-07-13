"""The AI must produce a PUBLISHABLE syllabus, not an outline.

The premise of the official-syllabus feature is that what comes out is a document a
Board of Studies can put its name to with minor editing. An outline that *looks*
finished is worse than an obvious failure — it reaches the regulation handbook and
nobody notices until a student does. So the checks below are HARD errors: a thin
unit is rejected and regenerated, never published.

The old generator produced units like:

    UNIT I
      • Introduction
      • Components

A real AICTE / Anna University / VTU unit runs to 12-20 specific, teachable topics.
These tests are what stand between the two.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.m02_syllabus.ai_provider import (
    MIN_TOPICS_PER_UNIT,
    SECTION_OBJECTIVES,
    SECTION_OUTCOMES,
    SECTION_REFERENCES,
    SECTION_UNIT,
    POContext,
    SyllabusGenerationContext,
    _SyllabusAI,
    _UnitOnlyAI,
    _build_prompt,
    _build_section_prompt,
    _is_soft_violation,
    _validate_result,
    _validate_section,
)

# A real unit: 14 specific, teachable topics — the depth a regulation actually
# prints, and the exact example the Board asked for.
RICH_TOPICS = [
    "Evolution of Computing",
    "Characteristics of Computer Systems",
    "Functional Units",
    "Von Neumann Architecture",
    "Harvard Architecture",
    "CPU Organization",
    "Instruction Cycle",
    "Memory Hierarchy",
    "Cache Memory",
    "Secondary Storage",
    "Input-Output Organization",
    "Performance Evaluation",
    "Benchmarking",
    "Modern Applications",
]


def _ctx(has_practical: bool = False) -> SyllabusGenerationContext:
    return SyllabusGenerationContext(
        course_id="x",
        course_code="MCA201",
        course_title="Computer Organization and Architecture",
        course_credits=4,
        program_outcomes=[POContext(id="1", code="PO1", description="Apply computing knowledge")],
        custom_instructions=None,
        ltp="3-1-2" if has_practical else "3-1-0",
        contact_hours=60,
        category="Core",
        has_practical=has_practical,
    )


def _unit(n: int, topics: list[str] | None = None) -> dict:
    """A real unit of a real syllabus.

    Each unit's topics are its OWN — suffixed by unit number when the caller does not
    supply them. Five units all teaching 'Cache Memory' is not a syllabus with five
    units, it is one unit printed five times, and the generator now rejects it
    (_cross_unit_duplicates). The fixture must not describe a document the product
    refuses to produce.
    """
    if topics is None:
        topics = [f"{t} in Unit {n}" for t in RICH_TOPICS]
    return {
        "unit_number": n,
        "title": f"Unit {n}",
        "topics": [{"title": t} for t in topics],
        "total_hours": 12,
        "pedagogy": "lecture",
    }


def _payload(**overrides) -> dict:
    base = {
        "objectives": [
            "To introduce the principles of computer organization.",
            "To develop an understanding of processor datapaths.",
            "To examine the memory hierarchy.",
            "To expose students to multicore architectures.",
        ],
        "outcomes": [
            {
                "code": f"CO{i}",
                "description": "Apply the principles of computer organization to real systems",
                "bloom_level": "APPLY",
            }
            for i in range(1, 6)
        ],
        "units": [_unit(i) for i in range(1, 6)],
        "practical_components": [],
        "internal_assessment": ["Two internal tests of 50 marks each, averaged to 20."],
        "reference_queries": [
            {"query_str": "computer organization architecture textbook", "ref_type": "TEXTBOOK"},
        ],
    }
    base.update(overrides)
    return base


def _hard_errors(data: dict, ctx: SyllabusGenerationContext | None = None) -> list[str]:
    """Violations that abort generation, as opposed to warnings that let it through."""
    parsed = _SyllabusAI.model_validate(data)
    return [v for v in _validate_result(parsed, ctx or _ctx()) if not _is_soft_violation(v)]


# ---------------------------------------------------------------------------
# Depth — the whole point of the feature
# ---------------------------------------------------------------------------

def test_a_publication_ready_syllabus_is_accepted():
    assert len(RICH_TOPICS) >= 12, "the fixture must itself meet the bar it tests"
    assert _hard_errors(_payload()) == []


def test_the_two_bullet_unit_cannot_survive():
    """The exact shape the old generator produced."""
    with pytest.raises(ValidationError):
        _SyllabusAI.model_validate(
            _payload(units=[_unit(1, ["Introduction", "Components"])]
                     + [_unit(i) for i in range(2, 6)])
        )


@pytest.mark.parametrize("count", [2, 3, 4, 7])
def test_a_unit_with_too_few_topics_is_rejected(count):
    """2, 3 or 4 topics is NEVER a unit. Below the floor the Board would have to write
    the rest by hand — which is exactly the work the AI is here to do for them."""
    with pytest.raises(ValidationError):
        _SyllabusAI.model_validate(
            _payload(units=[_unit(1, RICH_TOPICS[:count])] + [_unit(i) for i in range(2, 6)])
        )


def test_a_ten_topic_unit_is_allowed():
    """Ten is the floor a real regulation sits on (V2.4 — it was eight).

    A unit of eight or nine topics still reads as an outline next to an AICTE / Anna
    University / VTU unit, and the Board would be writing the rest of it by hand —
    which is the work the generator exists to do for them. Ten to fifteen is the shape
    of the printed document, so ten is where the floor belongs.
    """
    assert MIN_TOPICS_PER_UNIT == 10
    errors = _hard_errors(
        _payload(units=[_unit(1, RICH_TOPICS[:10])] + [_unit(i) for i in range(2, 6)])
    )
    assert errors == []


def test_a_nine_topic_unit_is_rejected():
    """The floor moved in V2.4, and a unit that used to squeak through no longer does.

    Nine topics parses — the schema tolerates it deliberately, so the BUSINESS rule
    gets to say what is wrong with it rather than the model failing with an opaque
    schema error — and is then rejected on depth.
    """
    errors = _hard_errors(
        _payload(units=[_unit(1, RICH_TOPICS[:9])] + [_unit(i) for i in range(2, 6)])
    )
    assert any("lists only 9 topic(s)" in e for e in errors)


def test_a_unit_of_pure_filler_is_rejected():
    """Enough lines to clear the count floor, but every one of them says nothing.

    This is the failure mode that matters most, because it LOOKS finished. A reader
    cannot tell what will be taught in the room — and neither can the lecturer who
    has to teach it.
    """
    filler = [
        "Introduction", "Fundamentals", "Overview", "Components", "Concepts",
        "Applications", "Case Studies", "Advanced Topics", "Conclusion",
        "Miscellaneous", "Other Topics", "Preliminaries", "Recent Trends",
        "Future Directions",
    ]
    errors = _hard_errors(_payload(units=[_unit(1, filler)] + [_unit(i) for i in range(2, 6)]))
    assert any("placeholder topics" in e for e in errors)


def test_a_padded_unit_is_rejected():
    """A model that runs out of ideas repeats itself. Fourteen lines that are really
    seven is the same hollowness in a longer coat."""
    padded = RICH_TOPICS[:7] + RICH_TOPICS[:7]
    errors = _hard_errors(_payload(units=[_unit(1, padded)] + [_unit(i) for i in range(2, 6)]))
    assert any("repeats topics" in e for e in errors)


def test_a_real_topic_that_merely_contains_a_filler_word_is_kept():
    """'Applications' alone is filler. 'Applications of Convolutional Networks' is a
    real topic. The filler check matches exact titles, never substrings — otherwise
    it would throw away half a good syllabus."""
    topics = RICH_TOPICS[:13] + ["Applications of Pipelining in Modern Processors"]
    assert _hard_errors(_payload(units=[_unit(1, topics)] + [_unit(i) for i in range(2, 6)])) == []


def test_the_syllabus_has_the_units_the_board_asked_for():
    """V2.4: four or five, and the Board decides which — before generation.

    The count is not a property of theory courses (plenty of real regulations run to
    four); it is a decision, carried on the syllabus row. What the validator enforces
    is that the AI honoured it — a five-unit response to a four-unit curriculum is
    rejected rather than trimmed, because trimming would drop a fifth of the subject.
    """
    five = _ctx()                                   # the default
    four = _ctx()
    four.unit_count = 4

    for count in (4, 6):
        errors = _hard_errors(_payload(units=[_unit(i) for i in range(1, count + 1)]), five)
        assert any("asked for EXACTLY 5" in e for e in errors), count

    for count in (3, 5):
        errors = _hard_errors(_payload(units=[_unit(i) for i in range(1, count + 1)]), four)
        assert any("asked for EXACTLY 4" in e for e in errors), count

    # And each is accepted when it is what was asked for.
    assert _hard_errors(_payload(units=[_unit(i) for i in range(1, 5)]), four) == []
    assert _hard_errors(_payload(), five) == []


def test_a_theory_course_is_not_given_laboratory_work():
    """An invented lab in an approved syllabus is a commitment the department can
    neither staff nor timetable."""
    errors = _hard_errors(_payload(practical_components=["Implement a cache simulator"]))
    assert any("no practical hours" in e for e in errors)


def test_the_prose_rendering_is_derived_from_the_topics():
    """`content` is a second view of the SAME material, so the two can never disagree:
    a regulation that prints paragraphs and one that prints bullets get the same
    syllabus."""
    parsed = _SyllabusAI.model_validate(_payload())
    content = parsed.units[0].content
    assert content
    for topic in RICH_TOPICS:
        assert topic in content


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

def test_the_prompt_demands_a_regulation():
    system, user = _build_prompt(_ctx())
    combined = system + user

    # It must show the model the target — a real unit of a real regulation...
    assert "Doubly Linked List" in combined
    assert "10 to 15 academic topics" in combined
    assert "NEVER acceptable" in combined      # 2, 3 or 4 topics
    assert "EXACTLY 5 units" in combined

    # ...and BOTH anti-patterns it must never produce: the stub, and the essay.
    assert "NEVER this" in combined
    assert "SYLLABUS POINT" in combined
    assert "No sentences" in combined

    assert "WEB_RESOURCE" in combined

    # The safety contract must survive every rewrite: the AI never invents
    # bibliographic detail.
    assert "ISBN" in combined
    assert "NEVER do this" in combined


def test_the_prompt_asks_for_the_unit_count_the_board_chose():
    """Four units means Unit I to Unit IV — in the brief, in the requirement, and in
    the numbering. A prompt that says 'five' anywhere while the Board asked for four is
    a prompt that will get five."""
    ctx = _ctx()
    ctx.unit_count = 4
    system, user = _build_prompt(ctx)

    assert "EXACTLY 4 units (Unit I to Unit IV)" in system
    assert "EXACTLY 4 units, numbered 1 to 4" in user
    assert "Unit I through Unit IV" in user
    assert "five" not in user.lower()


def test_practical_components_are_demanded_only_when_the_course_has_lab_hours():
    _, user = _build_prompt(_ctx(has_practical=True))
    assert "it MUST have them" in user

    _, user = _build_prompt(_ctx(has_practical=False))
    assert "Return an EMPTY list" in user


# ---------------------------------------------------------------------------
# Per-section regeneration
#
# The Board should never have to regenerate a whole syllabus because ONE unit came
# out weak. But a regenerated section must be held to exactly the same bar as a full
# generation — otherwise "regenerate this one unit" becomes the back door through
# which a thin unit reaches the published document.
# ---------------------------------------------------------------------------

def test_a_regenerated_unit_is_held_to_the_same_depth_bar():
    # A thin unit cannot get in through the regeneration door either.
    with pytest.raises(ValidationError):
        _UnitOnlyAI.model_validate({"unit": _unit(3, RICH_TOPICS[:4])})

    filler = _UnitOnlyAI.model_validate(
        {"unit": _unit(3, ["Introduction"] * 2 + RICH_TOPICS[:12])}
    )
    errors = _validate_section(filler, SECTION_UNIT, _ctx())
    assert errors

    good = _UnitOnlyAI.model_validate({"unit": _unit(3)})
    assert _validate_section(good, SECTION_UNIT, _ctx()) == []


def test_a_regenerated_unit_is_told_what_the_other_units_teach():
    """A unit rewritten in isolation is how you end up with two of them teaching cache
    memory. It has to know its neighbours to stay in its own lane."""
    _, user = _build_section_prompt(
        _ctx(),
        SECTION_UNIT,
        unit_number=3,
        unit_title="Processor Design",
        sibling_units=["Unit 1: Introduction to Computer Systems", "Unit 4: Memory Systems"],
    )
    assert "Unit 1: Introduction to Computer Systems" in user
    assert "Unit 4: Memory Systems" in user
    assert "do NOT stray into material the other units above already teach" in user
    assert "10-15 specific, teachable academic topics" in user


def test_board_guidance_reaches_the_model():
    _, user = _build_section_prompt(
        _ctx(), SECTION_UNIT, unit_number=2,
        guidance="Go deeper on cache coherence; this currently overlaps Unit IV.",
    )
    assert "Go deeper on cache coherence" in user


def test_each_section_prompt_asks_for_its_own_section():
    _, objectives = _build_section_prompt(_ctx(), SECTION_OBJECTIVES)
    assert "COURSE OBJECTIVES" in objectives
    # The objectives/outcomes distinction is the one models most often collapse.
    assert "NOT what the student can do afterwards" in objectives

    _, outcomes = _build_section_prompt(_ctx(), SECTION_OUTCOMES)
    assert "COURSE OUTCOMES" in outcomes
    assert "po_mapping_strengths" in outcomes

    _, refs = _build_section_prompt(_ctx(), SECTION_REFERENCES)
    assert "SEARCH TERMS ONLY" in refs
    assert "no ISBNs" in refs


def test_regenerated_references_still_may_not_invent_bibliography():
    """The safety contract holds on every path into the syllabus, not just the main
    one. A fabricated ISBN in a published regulation is a citation to a book that
    does not exist."""
    from app.modules.m02_syllabus.ai_provider import _ReferencesOnlyAI

    bad = _ReferencesOnlyAI.model_validate({
        "reference_queries": [
            {"query_str": "Bishop 2006 Springer ISBN 978-0387310732", "ref_type": "TEXTBOOK"},
            {"query_str": "pattern recognition machine learning", "ref_type": "TEXTBOOK"},
            {"query_str": "deep learning textbook", "ref_type": "REFERENCE"},
            {"query_str": "neural networks course", "ref_type": "WEB_RESOURCE"},
        ]
    })
    errors = _validate_section(bad, SECTION_REFERENCES, _ctx())
    assert any("bibliographic metadata" in e for e in errors)
