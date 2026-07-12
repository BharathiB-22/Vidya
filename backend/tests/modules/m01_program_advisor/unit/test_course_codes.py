"""Course code generation — pure logic, no database.

A code is {PREFIX}{semester}{NN}: MCA301, MCA302, ... The Dean never types one,
so the generator has to be right about gaps, normalisation and overflow.
"""
import pytest

from app.modules.m01_program_advisor.course_codes import (
    format_course_code,
    next_free_code,
    normalise_prefix,
)


class TestNormalisePrefix:
    @pytest.mark.parametrize(
        "degree_type,expected",
        [
            ("MCA", "MCA"),
            ("mca", "MCA"),
            ("B.Tech", "BTECH"),
            ("b tech", "BTECH"),
            ("B-Tech", "BTECH"),
            ("M.Sc.", "MSC"),
            ("BCA", "BCA"),
        ],
    )
    def test_strips_punctuation_and_uppercases(self, degree_type, expected):
        assert normalise_prefix(degree_type) == expected

    def test_empty_degree_type_yields_empty_prefix(self):
        assert normalise_prefix("") == ""
        assert normalise_prefix(None) == ""


class TestFormatCourseCode:
    def test_pads_sequence_to_two_digits(self):
        assert format_course_code("MCA", 3, 1) == "MCA301"
        assert format_course_code("MCA", 3, 9) == "MCA309"

    def test_sequence_beyond_99_is_not_truncated(self):
        # A program with >99 courses in one semester must still get a valid code.
        assert format_course_code("MCA", 3, 100) == "MCA3100"

    def test_semester_is_concatenated_not_fixed_width(self):
        # Nothing assumes a single-digit semester: Sem 10 is a real thing.
        assert format_course_code("MCA", 10, 1) == "MCA1001"


class TestNextFreeCode:
    def test_first_code_when_program_is_empty(self):
        assert next_free_code("MCA", 3, set()) == "MCA301"

    def test_continues_the_sequence(self):
        taken = {"MCA301", "MCA302", "MCA303", "MCA304", "MCA305"}
        assert next_free_code("MCA", 3, taken) == "MCA306"

    def test_fills_a_gap_left_by_a_deleted_course(self):
        # MCA302 was removed; the next choice reuses it rather than skipping.
        taken = {"MCA301", "MCA303"}
        assert next_free_code("MCA", 3, taken) == "MCA302"

    def test_codes_from_other_semesters_do_not_block(self):
        taken = {"MCA201", "MCA202", "MCA401"}
        assert next_free_code("MCA", 3, taken) == "MCA301"

    def test_is_semester_agnostic(self):
        assert next_free_code("BCA", 2, {"BCA201"}) == "BCA202"
        assert next_free_code("MBA", 1, set()) == "MBA101"
        assert next_free_code("MCA", 10, set()) == "MCA1001"

    def test_normalised_prefix_produces_expected_code(self):
        assert next_free_code(normalise_prefix("B.Tech"), 5, set()) == "BTECH501"

    def test_empty_prefix_is_refused(self):
        # Better to fail loudly than mint "301" as a course code.
        with pytest.raises(ValueError, match="degree prefix"):
            next_free_code("", 3, set())

    def test_exhaustion_raises_rather_than_looping_forever(self):
        taken = {format_course_code("MCA", 3, s) for s in range(1, 1000)}
        with pytest.raises(ValueError, match="Exhausted"):
            next_free_code("MCA", 3, taken)
