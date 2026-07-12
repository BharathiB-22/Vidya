"""The 'published curriculum course' predicate — pure SQL-shape assertions, no DB.

Academic Ownership counts a course only once its programme is PUBLISHED and, if
the course is a choice inside an elective paper, once that paper is published.
Getting this wrong is silent: the dashboard simply reports the wrong number of
courses, and every one of them as vacant.
"""
from app.modules.m_academics.curriculum_scope import published_course_sql


def test_requires_the_programme_to_be_published():
    sql = published_course_sql()
    assert "programs" in sql
    assert "'PUBLISHED'" in sql


def test_approved_is_not_enough():
    # An APPROVED programme is still editable; publishing is what commits it.
    assert "APPROVED" not in published_course_sql()


def test_excludes_choices_inside_a_draft_elective_paper():
    sql = published_course_sql()
    assert "elective_baskets" in sql
    assert "'DRAFT'" in sql
    assert "NOT EXISTS" in sql


def test_uses_the_given_course_alias():
    sql = published_course_sql("c2")
    assert "c2.program_id" in sql
    assert "c2.elective_basket_id" in sql
    assert "c.program_id" not in sql


def test_needs_no_other_table_in_scope():
    # Half the ownership queries reach courses through subject_assignments and
    # have no `programs` alias to hang a status filter on. The predicate must
    # correlate on courses.program_id itself, via EXISTS, or it cannot be applied
    # to them — which is how an assignment could drag an unpublished course back
    # into a roster the catalog branch had already excluded.
    sql = published_course_sql()
    assert "EXISTS (" in sql
    assert "p_cs.id = c.program_id" in sql


def test_is_a_bare_boolean_expression_callers_can_and_together():
    sql = published_course_sql().strip()
    assert not sql.upper().startswith(("AND", "WHERE", "OR"))


def test_ordinary_course_needs_no_elective_paper():
    # NOT EXISTS over a NULL elective_basket_id is true, so a non-elective course
    # passes without joining elective_baskets. Written as "not attached to a draft
    # paper", never as "attached to a published paper".
    sql = published_course_sql()
    assert "IS NOT NULL" not in sql
    assert "eb_cs.status = 'PUBLISHED'" not in sql
