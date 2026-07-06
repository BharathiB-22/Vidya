"""My Subjects / Subject Details — service layer (student self-service).

Reuses MarksRepository.get_student_marks_raw for the internal-marks breakdown
(no new marks query) and the latest DEAN_APPROVED/DEAN_LOCKED Syllabus for
units/course-outcomes.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth.models import User
from app.modules.m11_sis.marks_repository import MarksRepository
from app.modules.m11_sis.marks_schemas import StudentComponentView, StudentCourseMarks
from app.modules.m11_sis.models import SisFacultyProfile
from app.modules.m11_sis.student_academic_repository import (
    get_student_course_row,
    get_student_enrolled_courses_raw,
)
from app.modules.m11_sis.student_subjects_schemas import (
    MySubjectsOut,
    MySubjectSummary,
    SubjectCourseOutcomeOut,
    SubjectDetailOut,
    SubjectFacultyInfo,
    SyllabusUnitOut,
)
from app.modules.m02_syllabus.models import Syllabus, SyllabusStatus


async def _faculty_lookup(
    faculty_user_ids: set[UUID], db: AsyncSession
) -> dict[UUID, dict]:
    """Bulk-resolve faculty_user_id -> {name, designation, email, phone, office_location, photo_url}."""
    if not faculty_user_ids:
        return {}

    users_result = await db.execute(select(User).where(User.id.in_(faculty_user_ids)))
    users_by_id = {u.id: u for u in users_result.scalars().all()}

    profiles_result = await db.execute(
        select(SisFacultyProfile).where(SisFacultyProfile.user_id.in_(faculty_user_ids))
    )
    profiles_by_id = {p.user_id: p for p in profiles_result.scalars().all()}

    out: dict[UUID, dict] = {}
    for fid in faculty_user_ids:
        user = users_by_id.get(fid)
        profile = profiles_by_id.get(fid)
        out[fid] = {
            "name": user.full_name if user else "",
            "email": user.email if user else None,
            "designation": profile.designation if profile else None,
            "phone": profile.phone if profile else None,
            "office_location": profile.office_location if profile else None,
            "photo_url": profile.photo_url if profile else None,
        }
    return out


class StudentSubjectsService:

    @staticmethod
    async def get_my_subjects(
        student_id: UUID, db: AsyncSession, semester_id: UUID | None = None
    ) -> MySubjectsOut:
        user = (await db.execute(select(User).where(User.id == student_id))).scalar_one_or_none()
        student_name = user.full_name if user else ""

        from sqlalchemy import text
        usn_row = (await db.execute(
            text("SELECT usn FROM sis_student_profiles WHERE user_id = :uid"),
            {"uid": str(student_id)},
        )).one_or_none()
        usn = usn_row[0] if usn_row else None

        rows = await get_student_enrolled_courses_raw(student_id, db, semester_id=semester_id)

        # Rows are ordered per-course with PRIMARY faculty first; keep the first row per course.
        seen_courses: set[UUID] = set()
        deduped: list[dict] = []
        for row in rows:
            if row["course_id"] in seen_courses:
                continue
            seen_courses.add(row["course_id"])
            deduped.append(row)

        faculty_ids = {r["faculty_user_id"] for r in deduped if r.get("faculty_user_id")}
        faculty_map = await _faculty_lookup(faculty_ids, db)

        subjects = [
            MySubjectSummary(
                course_id=row["course_id"],
                course_code=row["course_code"],
                course_title=row["course_title"],
                credits=row["credits"],
                semester=row["semester"],
                course_type=row.get("course_type"),
                is_elective=row["is_elective"],
                section_id=row["section_id"],
                section_name=row["section_name"],
                faculty_user_id=row.get("faculty_user_id"),
                faculty_name=faculty_map.get(row["faculty_user_id"], {}).get("name") if row.get("faculty_user_id") else None,
                faculty_designation=faculty_map.get(row["faculty_user_id"], {}).get("designation") if row.get("faculty_user_id") else None,
                syllabus_id=row.get("syllabus_id"),
                syllabus_status=row.get("syllabus_status"),
            )
            for row in deduped
        ]

        return MySubjectsOut(
            student_id=student_id,
            student_name=student_name,
            usn=usn,
            semester_id=semester_id,
            subjects=subjects,
        )

    @staticmethod
    async def get_subject_detail(student_id: UUID, course_id: UUID, db: AsyncSession) -> SubjectDetailOut | None:
        row = await get_student_course_row(student_id, course_id, db)
        if row is None:
            return None

        faculty: SubjectFacultyInfo | None = None
        if row.get("faculty_user_id"):
            faculty_map = await _faculty_lookup({row["faculty_user_id"]}, db)
            info = faculty_map.get(row["faculty_user_id"])
            if info:
                faculty = SubjectFacultyInfo(
                    user_id=row["faculty_user_id"],
                    name=info["name"],
                    designation=info["designation"],
                    email=info["email"],
                    phone=info["phone"],
                    office_location=info["office_location"],
                    photo_url=info["photo_url"],
                )

        syllabus_result = await db.execute(
            select(Syllabus)
            .where(
                Syllabus.course_id == course_id,
                Syllabus.status.in_([SyllabusStatus.DEAN_APPROVED, SyllabusStatus.DEAN_LOCKED]),
            )
            .options(selectinload(Syllabus.units), selectinload(Syllabus.outcomes))
            .order_by(Syllabus.version.desc())
            .limit(1)
        )
        syllabus = syllabus_result.scalars().first()

        units: list[SyllabusUnitOut] = []
        course_outcomes: list[SubjectCourseOutcomeOut] = []
        syllabus_id = syllabus_version = syllabus_status = None
        if syllabus is not None:
            syllabus_id = syllabus.id
            syllabus_version = syllabus.version
            syllabus_status = syllabus.status.value
            units = [
                SyllabusUnitOut(unit_number=u.unit_number, title=u.title, hours=u.total_hours)
                for u in sorted(syllabus.units, key=lambda u: u.unit_number)
            ]
            course_outcomes = [
                SubjectCourseOutcomeOut(
                    code=co.code,
                    description=co.description,
                    bloom_level=co.bloom_level.value if co.bloom_level else None,
                    display_order=co.display_order,
                )
                for co in sorted(syllabus.outcomes, key=lambda co: co.display_order)
            ]

        internal_marks = await StudentSubjectsService._get_internal_marks_for_course(
            student_id, course_id, row["section_id"], row["section_name"], row["course_code"], row["course_title"], db
        )

        return SubjectDetailOut(
            course_id=row["course_id"],
            course_code=row["course_code"],
            course_title=row["course_title"],
            credits=row["credits"],
            semester=row["semester"],
            course_type=row.get("course_type"),
            is_elective=row["is_elective"],
            description=row.get("description"),
            hours_lecture=row.get("hours_lecture"),
            hours_tutorial=row.get("hours_tutorial"),
            hours_practical=row.get("hours_practical"),
            section_id=row["section_id"],
            section_name=row["section_name"],
            faculty=faculty,
            syllabus_id=syllabus_id,
            syllabus_version=syllabus_version,
            syllabus_status=syllabus_status,
            units=units,
            course_outcomes=course_outcomes,
            internal_marks=internal_marks,
        )

    @staticmethod
    async def _get_internal_marks_for_course(
        student_id: UUID,
        course_id: UUID,
        section_id: UUID,
        section_name: str,
        course_code: str,
        course_title: str,
        db: AsyncSession,
    ) -> StudentCourseMarks | None:
        raw = await MarksRepository.get_student_marks_raw(student_id, db)
        course_rows = [r for r in raw if r["course_id"] == course_id]
        if not course_rows:
            return None

        components: list[StudentComponentView] = []
        total_obtained = Decimal(0)
        total_max = Decimal(0)
        has_marks = False
        for r in course_rows:
            components.append(StudentComponentView(
                component_id=r["component_id"],
                component_type=r["component_type"],
                name=r["component_name"],
                max_marks=Decimal(str(r["max_marks"])),
                weightage=Decimal(str(r["weightage"])) if r.get("weightage") else None,
                due_date=r.get("due_date"),
                display_order=r.get("display_order"),
                status=r["component_status"],
                marks_obtained=Decimal(str(r["marks_obtained"])) if r.get("marks_obtained") is not None else None,
                remarks=r.get("remarks"),
            ))
            total_max += Decimal(str(r["max_marks"]))
            if r.get("marks_obtained") is not None:
                total_obtained += Decimal(str(r["marks_obtained"]))
                has_marks = True

        return StudentCourseMarks(
            course_id=course_id,
            course_code=course_code,
            course_title=course_title,
            section_id=section_id,
            section_name=section_name,
            total_marks_obtained=total_obtained if has_marks else None,
            total_max_marks=total_max if total_max > 0 else None,
            components=components,
        )
