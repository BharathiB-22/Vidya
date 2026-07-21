"""Course code generation — pure logic, no database.

A code is {PREFIX}{semester}{NN}: MCA301, MCA302, ... The Dean never types one,
so the generator has to be right about gaps, normalisation and overflow.
"""
import pytest

from app.modules.m01_program_advisor.course_codes import (
    ProgramCodePrefixError,
    assign_course_codes,
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

    def test_a_full_semester_raises_rather_than_lying_about_itself(self):
        """The 100th course in a semester would be MCA1100 — a code whose first
        digit no longer identifies the semester. Refuse it instead of minting it."""
        taken = {format_course_code("MCA", 3, s) for s in range(1, 100)}
        with pytest.raises(ValueError, match="already holds 99 courses"):
            next_free_code("MCA", 3, taken)

    def test_the_99th_course_is_still_fine(self):
        taken = {format_course_code("MCA", 3, s) for s in range(1, 99)}
        assert next_free_code("MCA", 3, taken) == "MCA399"

    def test_the_semester_is_always_the_first_digit(self):
        # The contract the whole format exists for.
        for semester in range(1, 10):
            code = next_free_code("MCA", semester, set())
            assert code == f"MCA{semester}01"
            assert code[len("MCA")] == str(semester)


class TestAssignCourseCodes:
    """The AI's codes are opaque temp keys. These are the real ones."""

    def _ai_courses(self):
        # What a real MCA run actually returned: CS-prefixed, numbered straight
        # through the programme with no regard for the semester boundary.
        return [
            {"code": "CS501", "title": "Computer Systems", "semester": 1,
             "prerequisite_codes": []},
            {"code": "CS502", "title": "Python Programming", "semester": 1,
             "prerequisite_codes": []},
            {"code": "CS506", "title": "Database Systems", "semester": 2,
             "prerequisite_codes": ["CS501"]},
            {"code": "CS510", "title": "Computer Networks", "semester": 3,
             "prerequisite_codes": ["CS506"]},
        ]

    def test_codes_are_reassigned_per_semester_from_the_prefix(self):
        courses = self._ai_courses()
        assign_course_codes(courses, "MCA", set())
        assert [c["code"] for c in courses] == ["MCA101", "MCA102", "MCA201", "MCA301"]

    def test_returns_the_map_prerequisites_are_resolved_through(self):
        courses = self._ai_courses()
        mapping = assign_course_codes(courses, "MCA", set())
        assert mapping == {
            "CS501": "MCA101", "CS502": "MCA102",
            "CS506": "MCA201", "CS510": "MCA301",
        }
        # The AI's prerequisite edges survive the rename — the whole point of the map.
        db_ms = courses[2]
        assert [mapping[pc] for pc in db_ms["prerequisite_codes"]] == ["MCA101"]

    def test_existing_human_codes_are_not_reused(self):
        courses = self._ai_courses()
        assign_course_codes(courses, "MCA", {"MCA101", "MCA201"})
        assert [c["code"] for c in courses] == ["MCA102", "MCA103", "MCA202", "MCA301"]

    def test_input_order_is_preserved(self):
        """course_creates and new_courses are zipped positionally — reordering the
        list in place would silently attach every prerequisite to the wrong course."""
        courses = self._ai_courses()
        titles = [c["title"] for c in courses]
        assign_course_codes(courses, "MCA", set())
        assert [c["title"] for c in courses] == titles

    def test_duplicate_ai_codes_get_distinct_real_codes(self):
        courses = [
            {"code": "CS501", "title": "A", "semester": 1},
            {"code": "CS501", "title": "B", "semester": 1},
        ]
        mapping = assign_course_codes(courses, "MCA", set())
        assert [c["code"] for c in courses] == ["MCA101", "MCA102"]
        # Ambiguous: the first claims the map rather than the last silently winning.
        assert mapping == {"CS501": "MCA101"}

    def test_no_prefix_is_refused_rather_than_guessed(self):
        with pytest.raises(ProgramCodePrefixError):
            assign_course_codes([{"code": "CS501", "semester": 1}], "", set())

    def test_numbering_restarts_every_semester(self):
        """The regression this whole format exists to prevent: numbering must NOT
        run on across the programme (MCA101..MCA115), because then the code cannot
        say which semester its course belongs to."""
        courses = [
            {"code": f"CS{i}", "semester": sem}
            for sem, count in ((1, 6), (2, 4), (3, 3), (4, 2))
            for i in range(count)
        ]
        assign_course_codes(courses, "MCA", set())

        by_semester: dict[int, list[str]] = {}
        for c in courses:
            by_semester.setdefault(c["semester"], []).append(c["code"])

        assert by_semester[1] == ["MCA101", "MCA102", "MCA103", "MCA104", "MCA105", "MCA106"]
        assert by_semester[2] == ["MCA201", "MCA202", "MCA203", "MCA204"]
        assert by_semester[3] == ["MCA301", "MCA302", "MCA303"]
        # The one that was actually wrong in the database: MCA120/MCA121, not MCA401/2.
        assert by_semester[4] == ["MCA401", "MCA402"]
