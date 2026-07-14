"""Course type normalization — pure logic, no database.

The enum decides which official document the Board produces, so a wrong
normalization is a wrong document, not a wrong label. These tests pin the two
things that actually cost something: that a synonym never reaches the Pydantic
validator, and that a bare 'PROJECT' lands on the right side of the
mini/major split.
"""
import pytest

from app.modules.m01_program_advisor.course_types import (
    COURSE_TYPE_SYNONYMS,
    normalize_course_type,
    squash,
)
from app.modules.m01_program_advisor.models import CourseType
from app.modules.m01_program_advisor.schemas import CourseCreate


class TestSquash:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("MAJOR_PROJECT", "MAJORPROJECT"),
            ("Major Project", "MAJORPROJECT"),
            ("major-project", "MAJORPROJECT"),
            ("  mini project  ", "MINIPROJECT"),
            ("Theory", "THEORY"),
            ("", ""),
        ],
    )
    def test_ignores_case_spaces_underscores_hyphens(self, raw, expected):
        assert squash(raw) == expected


class TestCanonicalValuesSurvive:
    @pytest.mark.parametrize("member", list(CourseType))
    def test_every_enum_value_normalizes_to_itself(self, member):
        assert normalize_course_type(member.value, title="Anything") is member


class TestSynonyms:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("PRACTICAL", CourseType.LAB),
            ("Practical Lab", CourseType.LAB),
            ("LABORATORY", CourseType.LAB),
            ("theory lab", CourseType.LAB),
            ("THEORY", CourseType.THEORY),
            ("INTERNSHIP", CourseType.INTERNSHIP),
            ("SEMINAR", CourseType.SEMINAR),
            ("MAJOR PROJECT", CourseType.MAJOR_PROJECT),
            ("MINI PROJECT", CourseType.MINI_PROJECT),
            ("MINOR PROJECT", CourseType.MINI_PROJECT),
            ("mini-project", CourseType.MINI_PROJECT),
            ("Capstone", CourseType.MAJOR_PROJECT),
            ("Dissertation", CourseType.MAJOR_PROJECT),
        ],
    )
    def test_maps_ai_synonyms_to_canonical(self, raw, expected):
        # Title is deliberately unhelpful: the synonym alone must carry it.
        assert normalize_course_type(raw, title="Some Course") is expected

    def test_table_is_closed_under_its_own_output(self):
        """Every value the table produces is a real enum member."""
        for canonical in COURSE_TYPE_SYNONYMS.values():
            assert CourseType(canonical)

    def test_table_keys_are_stored_squashed(self):
        """A key with a space or hyphen would never be looked up."""
        for key in COURSE_TYPE_SYNONYMS:
            assert key == squash(key)


class TestNoLegacyProjectSurvives:
    """The enum is the single source of truth. compliance.py mirrors it as plain
    strings (it is deliberately ORM-free), so the mirror is pinned here — a value
    added to CourseType without updating compliance would otherwise be a rule that
    silently stops matching, which is exactly how 'PROJECT' rotted.
    """

    def test_project_is_not_a_course_type(self):
        with pytest.raises(ValueError):
            CourseType("PROJECT")

    def test_compliance_project_types_match_the_enum(self):
        from app.modules.m01_program_advisor import compliance

        assert compliance.PROJECT_TYPES == {
            CourseType.MINI_PROJECT.value,
            CourseType.MAJOR_PROJECT.value,
        }
        assert compliance.PROJECT_OR_INTERNSHIP_TYPES == {
            CourseType.MINI_PROJECT.value,
            CourseType.MAJOR_PROJECT.value,
            CourseType.INTERNSHIP.value,
        }

    def test_every_mirrored_constant_is_a_real_enum_value(self):
        from app.modules.m01_program_advisor import compliance

        mirrored = {
            compliance.TYPE_THEORY, compliance.TYPE_LAB,
            compliance.TYPE_INTERNSHIP, compliance.TYPE_MINI_PROJECT,
            compliance.TYPE_MAJOR_PROJECT, compliance.TYPE_SEMINAR,
        }
        assert mirrored == {member.value for member in CourseType}


class TestBareProjectIsResolvedByTitle:
    """The prompt asks for `course_type PROJECT` on a MINI project, and providers
    emit bare PROJECT for both kinds. The title is the only thing that knows —
    same rule migration 0086ten used to split the legacy rows.
    """

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Mini Project", CourseType.MINI_PROJECT),
            ("Mini Project Work", CourseType.MINI_PROJECT),
            ("Minor Project", CourseType.MINI_PROJECT),
            ("Major Project", CourseType.MAJOR_PROJECT),
            ("Project Work", CourseType.MAJOR_PROJECT),
            ("Capstone Project", CourseType.MAJOR_PROJECT),
        ],
    )
    def test_project_splits_on_title(self, title, expected):
        assert normalize_course_type("PROJECT", title=title) is expected

    def test_major_project_is_the_default_when_title_is_silent(self):
        # The traceback's exact input. MAJOR_PROJECT because its handbook is the
        # superset: correcting down loses nothing, the reverse drops the viva.
        assert normalize_course_type("PROJECT", title="") is CourseType.MAJOR_PROJECT


class TestTitleInference:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Data Structures Lab", CourseType.LAB),
            ("Compiler Design Laboratory", CourseType.LAB),
            ("Industry Internship", CourseType.INTERNSHIP),
            ("Technical Seminar", CourseType.SEMINAR),
            ("Mini Project", CourseType.MINI_PROJECT),
            ("Operating Systems", CourseType.THEORY),
        ],
    )
    def test_falls_back_to_title_when_type_is_missing(self, title, expected):
        assert normalize_course_type(None, title=title) is expected

    def test_mini_project_lab_is_a_project_not_a_lab(self):
        """Order matters: a lab manual is not what a project owes."""
        assert normalize_course_type(None, title="Mini Project Lab") is CourseType.MINI_PROJECT

    def test_unrecognised_type_still_reads_the_title(self):
        assert normalize_course_type("BLAH", title="DBMS Lab") is CourseType.LAB


class TestFallback:
    def test_unreadable_course_defaults_to_theory(self):
        assert normalize_course_type("BLAH", title="Quantum Widgets") is CourseType.THEORY

    def test_missing_everything_defaults_to_theory(self):
        assert normalize_course_type(None, title="") is CourseType.THEORY

    def test_default_none_leaves_the_type_unset(self):
        assert normalize_course_type(None, title="", default=None) is None

    @pytest.mark.parametrize("junk", [123, [], {}, object()])
    def test_non_string_input_does_not_explode(self, junk):
        assert normalize_course_type(junk, title="Operating Systems") is CourseType.THEORY


class TestReachesCourseCreateCleanly:
    """The point of the exercise: the synonym never sees the enum validator."""

    @pytest.mark.parametrize(
        "ai_type,title,expected",
        [
            ("PROJECT", "Major Project", CourseType.MAJOR_PROJECT),
            ("PROJECT", "Mini Project", CourseType.MINI_PROJECT),
            ("PRACTICAL", "DBMS Lab", CourseType.LAB),
            ("THEORY", "Operating Systems", CourseType.THEORY),
        ],
    )
    def test_course_create_accepts_normalized_ai_output(self, ai_type, title, expected):
        course = CourseCreate(
            code="MCA401",
            title=title,
            credits=4,
            semester=4,
            course_type=normalize_course_type(ai_type, title=title),
        )
        assert course.course_type is expected

    def test_raw_ai_output_would_have_failed(self):
        """Guards the premise — if CourseCreate ever accepts 'PROJECT' on its own,
        this normalizer is no longer the thing standing between the AI and the DB.
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CourseCreate(
                code="MCA401", title="Major Project", credits=4, semester=4,
                course_type="PROJECT",
            )
