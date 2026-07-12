"""Elective papers are independent curriculum courses — pure logic, no DB.

Semester 3 holding Elective 1, Elective 2 and Elective 3 (3 credits each) is
THREE curriculum courses worth 9 credits, because the student takes all three
papers and chooses exactly one alternative inside each. Collapsing every
alternative under one shared name was the bug: it turned three papers into one
and silently dropped 6 credits from the semester.
"""
from app.workers.heavy.program_structure import (
    _basket_key,
    _is_paper_label,
    _paper_sort_key,
    normalize_total_credits,
)


def _alt(name: str | None, credits: int = 3, semester: int = 3) -> dict:
    return {"credits": credits, "semester": semester, "elective_basket_name": name}


class TestPaperLabels:
    def test_recognises_positional_labels(self):
        assert _is_paper_label("Elective 1")
        assert _is_paper_label("elective 12")
        assert _is_paper_label("  Elective 3  ")

    def test_rejects_thematic_names(self):
        assert not _is_paper_label("AI Electives")
        assert not _is_paper_label("Elective")
        assert not _is_paper_label("Elective One")


class TestPaperOrdering:
    def test_numeric_order_not_lexicographic(self):
        # Plain sorting would put "Elective 10" before "Elective 2".
        names = ["Elective 10", "Elective 2", "Elective 1"]
        assert sorted(names, key=_paper_sort_key) == ["Elective 1", "Elective 2", "Elective 10"]

    def test_thematic_names_sort_after_labelled_ones(self):
        names = ["Zebra Electives", "Elective 2", "Alpha Electives"]
        assert sorted(names, key=_paper_sort_key) == [
            "Elective 2", "Alpha Electives", "Zebra Electives",
        ]

    def test_ordering_is_independent_of_course_order(self):
        # Numbering must not depend on which alternative appeared first.
        a = sorted(["Elective 3", "Elective 1", "Elective 2"], key=_paper_sort_key)
        b = sorted(["Elective 2", "Elective 3", "Elective 1"], key=_paper_sort_key)
        assert a == b


class TestPaperGrouping:
    def test_alternatives_of_one_paper_share_a_key(self):
        assert _basket_key(_alt("Elective 1")) == _basket_key(_alt("Elective 1"))

    def test_distinct_papers_do_not_share_a_key(self):
        assert _basket_key(_alt("Elective 1")) != _basket_key(_alt("Elective 2"))

    def test_same_paper_name_in_different_semesters_is_distinct(self):
        assert _basket_key(_alt("Elective 1", semester=3)) != _basket_key(
            _alt("Elective 1", semester=5)
        )

    def test_non_elective_has_no_key(self):
        assert _basket_key(_alt(None)) is None
        assert _basket_key(_alt("   ")) is None


class TestCreditWeighting:
    def test_three_papers_contribute_three_units_not_one(self):
        # 1 core (4cr) + three 3cr papers, each with two alternatives = 13 credits.
        courses = [_alt(None, credits=4)]
        for paper in ("Elective 1", "Elective 2", "Elective 3"):
            courses += [_alt(paper), _alt(paper)]
        residual = normalize_total_credits(courses, 13)
        assert residual == 0, "4 + 3 + 3 + 3 must reach the 13-credit target exactly"

    def test_collapsing_papers_into_one_name_loses_credits(self):
        # The old behaviour: every alternative under one shared name. Six
        # alternatives then count as ONE unit, so the same target is unreachable.
        courses = [_alt(None, credits=4)] + [_alt("Electives") for _ in range(6)]
        residual = normalize_total_credits(courses, 13)
        assert residual != 0, "one collapsed paper cannot supply three papers' credits"

    def test_alternatives_within_a_paper_are_equalised(self):
        courses = [_alt("Elective 1", credits=3), _alt("Elective 1", credits=5)]
        normalize_total_credits(courses, 4)
        assert courses[0]["credits"] == courses[1]["credits"], (
            "alternatives are interchangeable, so they must carry identical credits"
        )
