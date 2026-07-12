from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.timetable.dean_scope import (
    assert_dean_owns_department,
    assert_dean_owns_section,
    get_dean_department_ids,
    get_dean_section_ids,
)
from app.core.timetable.schemas import (
    FacultyTimetableOut,
    StudentTimetableOut,
    TimetableCreate,
    TimetableListItem,
    TimetableOut,
    TimetablePeriodCreate,
    TimetablePeriodOut,
    TimetablePeriodUpdate,
    TimetableRejectRequest,
    TimetableSlotCreate,
    TimetableSlotOut,
    TimetableSlotSwap,
    TimetableSlotUpdate,
    TimetableUpdate,
    TimetableTemplateCreate,
    TimetableTemplateListItem,
    TimetableTemplateOut,
    TimetableTemplateUpdate,
)
from app.core.timetable.service import TimetableService, TimetableServiceError

router = APIRouter(tags=["timetable"])


def _err(e: TimetableServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"error": e.code, "message": e.message})


async def _to_out(tt, db: AsyncSession, with_slots: bool = True) -> TimetableOut:
    ctx = await TimetableService.get_section_context(tt.section_id, db)
    slots = await TimetableService.slots_out(tt.id, db) if with_slots else []
    template = await TimetableService.get_template_full(tt.template_id, db)
    return TimetableOut(
        id=tt.id, section_id=tt.section_id, section_name=ctx["section_name"], semester_id=tt.semester_id,
        semester_label=ctx["semester_label"], program_name=ctx["program_name"],
        program_code=ctx.get("program_code"), academic_year=ctx.get("academic_year"),
        status=tt.status, slots=slots, template_id=tt.template_id, template=template,
        created_by_user_id=tt.created_by_user_id,
        submitted_at=tt.submitted_at, reviewed_by_user_id=tt.reviewed_by_user_id, reviewed_at=tt.reviewed_at,
        review_comment=tt.review_comment, published_by_user_id=tt.published_by_user_id,
        published_at=tt.published_at, created_at=tt.created_at, updated_at=tt.updated_at,
    )


async def _to_list_item(tt, db: AsyncSession) -> TimetableListItem:
    ctx = await TimetableService.get_section_context(tt.section_id, db)
    slots = await TimetableService.list_slots(tt.id, db)
    return TimetableListItem(
        id=tt.id, section_id=tt.section_id, section_name=ctx["section_name"], semester_id=tt.semester_id,
        semester_label=ctx["semester_label"], program_name=ctx["program_name"],
        program_code=ctx.get("program_code"), academic_year=ctx.get("academic_year"),
        status=tt.status, slot_count=len(slots), template_id=tt.template_id,
        created_by_user_id=tt.created_by_user_id,
        submitted_at=tt.submitted_at, published_at=tt.published_at, created_at=tt.created_at,
    )


async def _to_template_list_item(tpl, db: AsyncSession) -> TimetableTemplateListItem:
    from sqlalchemy import text as _text

    dept_row = (await db.execute(
        _text("SELECT name FROM acad_departments WHERE id = :id"), {"id": str(tpl.department_id)}
    )).mappings().first()
    periods = await TimetableService.list_periods(tpl.id, db)
    return TimetableTemplateListItem(
        id=tpl.id, department_id=tpl.department_id,
        department_name=dept_row["name"] if dept_row else None,
        name=tpl.name, working_days=tpl.working_days, saturday_mode=tpl.saturday_mode,
        college_start_time=tpl.college_start_time, college_end_time=tpl.college_end_time,
        period_count=len(periods), created_by_user_id=tpl.created_by_user_id,
        created_at=tpl.created_at, updated_at=tpl.updated_at,
    )


# ── Dean: Timetable Templates (Phase 4.1) — fixed two-segment paths,
# registered ahead of the generic "/{timetable_id}" route below, same
# reasoning as "/dean/pending": no collision risk, just readability. ────────

@router.post("/templates", response_model=TimetableTemplateOut, status_code=201)
async def create_template(
    body: TimetableTemplateCreate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableTemplateOut:
    try:
        await assert_dean_owns_department(current_user.user_id, body.department_id, db)
        tpl = await TimetableService.create_template(
            body.department_id, body.name, body.working_days, body.saturday_mode,
            body.college_start_time, body.college_end_time, current_user.user_id, db,
        )
        return await TimetableService.get_template_full(tpl.id, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.get("/templates", response_model=list[TimetableTemplateListItem])
async def list_templates(
    department_id: UUID | None = Query(None),
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[TimetableTemplateListItem]:
    try:
        if department_id is not None:
            await assert_dean_owns_department(current_user.user_id, department_id, db)
            department_ids = [department_id]
        else:
            department_ids = await get_dean_department_ids(current_user.user_id, db)
        rows = await TimetableService.list_templates(department_ids, db)
        return [await _to_template_list_item(tpl, db) for tpl in rows]
    except TimetableServiceError as e:
        raise _err(e)


@router.get("/templates/{template_id}", response_model=TimetableTemplateOut)
async def get_template(
    template_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableTemplateOut:
    tpl = await TimetableService.get_template(template_id, db)
    if tpl is None:
        raise HTTPException(404, detail={"error": "NOT_FOUND", "message": "Template not found."})
    try:
        await assert_dean_owns_department(current_user.user_id, tpl.department_id, db)
    except TimetableServiceError as e:
        raise _err(e)
    return await TimetableService.get_template_full(template_id, db)


@router.patch("/templates/{template_id}", response_model=TimetableTemplateOut)
async def update_template(
    template_id: UUID,
    body: TimetableTemplateUpdate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableTemplateOut:
    tpl = await TimetableService.get_template(template_id, db)
    if tpl is None:
        raise HTTPException(404, detail={"error": "NOT_FOUND", "message": "Template not found."})
    try:
        await assert_dean_owns_department(current_user.user_id, tpl.department_id, db)
        await TimetableService.update_template(template_id, body.model_dump(exclude_unset=True), db)
        return await TimetableService.get_template_full(template_id, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    tpl = await TimetableService.get_template(template_id, db)
    if tpl is None:
        raise HTTPException(404, detail={"error": "NOT_FOUND", "message": "Template not found."})
    try:
        await assert_dean_owns_department(current_user.user_id, tpl.department_id, db)
        await TimetableService.delete_template(template_id, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.post("/templates/{template_id}/periods", response_model=TimetablePeriodOut, status_code=201)
async def add_period(
    template_id: UUID,
    body: TimetablePeriodCreate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetablePeriodOut:
    tpl = await TimetableService.get_template(template_id, db)
    if tpl is None:
        raise HTTPException(404, detail={"error": "NOT_FOUND", "message": "Template not found."})
    try:
        await assert_dean_owns_department(current_user.user_id, tpl.department_id, db)
        period = await TimetableService.add_period(template_id, body, db)
        return TimetablePeriodOut.model_validate(period)
    except TimetableServiceError as e:
        raise _err(e)


@router.patch("/templates/{template_id}/periods/{period_id}", response_model=TimetablePeriodOut)
async def update_period(
    template_id: UUID,
    period_id: UUID,
    body: TimetablePeriodUpdate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetablePeriodOut:
    tpl = await TimetableService.get_template(template_id, db)
    if tpl is None:
        raise HTTPException(404, detail={"error": "NOT_FOUND", "message": "Template not found."})
    try:
        await assert_dean_owns_department(current_user.user_id, tpl.department_id, db)
        period = await TimetableService.update_period(period_id, body.model_dump(exclude_unset=True), db)
        return TimetablePeriodOut.model_validate(period)
    except TimetableServiceError as e:
        raise _err(e)


@router.delete("/templates/{template_id}/periods/{period_id}", status_code=204)
async def delete_period(
    template_id: UUID,
    period_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    tpl = await TimetableService.get_template(template_id, db)
    if tpl is None:
        raise HTTPException(404, detail={"error": "NOT_FOUND", "message": "Template not found."})
    try:
        await assert_dean_owns_department(current_user.user_id, tpl.department_id, db)
        await TimetableService.delete_period(period_id, db)
    except TimetableServiceError as e:
        raise _err(e)


# ── Dean: create + list — ownership correction: Dean is the academic
# authority for the class timetable end-to-end (create, assign faculty/
# subject/room, save draft, review, publish). Admin no longer creates or
# manages timetables. Department isolation (Phase 4.1): a Dean only sees/
# manages sections belonging to a program they govern. (Fixed paths,
# no collision risk.) ────────────────────────────────────────────────────────

@router.post("", response_model=TimetableOut, status_code=201)
async def create_timetable(
    body: TimetableCreate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableOut:
    try:
        await assert_dean_owns_section(current_user.user_id, body.section_id, db)
        tt = await TimetableService.create(
            body.section_id, body.semester_id, current_user.user_id, db, template_id=body.template_id,
        )
        return await _to_out(tt, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.get("", response_model=list[TimetableListItem])
async def list_timetables(
    section_id: UUID | None = Query(None),
    semester_id: UUID | None = Query(None),
    status: str | None = Query(None),
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[TimetableListItem]:
    section_ids = await get_dean_section_ids(current_user.user_id, db)
    rows = await TimetableService.list(db, section_id, semester_id, status, section_ids=section_ids)
    return [await _to_list_item(tt, db) for tt in rows]


# ── Dean: pending queue (fixed two-segment path, registered ahead of the
# generic "/{timetable_id}" below purely for readability — no collision risk
# since it has two path segments) ────────────────────────────────────────────

@router.get("/dean/pending", response_model=list[TimetableListItem])
async def list_pending_timetables(
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[TimetableListItem]:
    section_ids = await get_dean_section_ids(current_user.user_id, db)
    rows = await TimetableService.list(db, status="PENDING_REVIEW", section_ids=section_ids)
    return [await _to_list_item(tt, db) for tt in rows]


# ── Student / Faculty: single-segment fixed paths — MUST be registered
# before the generic "/{timetable_id}" route below, otherwise FastAPI would
# match "/me"/"/mine" as timetable_id="me"/"mine" instead. ────────────────────

@router.get("/me", response_model=StudentTimetableOut | None)
async def get_my_timetable(
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> StudentTimetableOut | None:
    result = await TimetableService.get_student_timetable(current_user.user_id, db)
    if result is None:
        return None
    return StudentTimetableOut(**result)


@router.get("/mine", response_model=FacultyTimetableOut)
async def get_my_faculty_timetable(
    current_user: CurrentUser = Depends(require_roles(TenantRole.FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> FacultyTimetableOut:
    slots = await TimetableService.get_faculty_timetable(current_user.user_id, db)
    return FacultyTimetableOut(slots=slots)


# ── Dean: generic detail + mutation routes (all "/{timetable_id}...") ────────

@router.get("/{timetable_id}", response_model=TimetableOut)
async def get_timetable(
    timetable_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableOut:
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
    except TimetableServiceError as e:
        raise _err(e)
    return await _to_out(tt, db)


@router.post("/{timetable_id}/slots", response_model=TimetableSlotOut, status_code=201)
async def add_slot(
    timetable_id: UUID,
    body: TimetableSlotCreate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableSlotOut:
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        slot = await TimetableService.add_slot(timetable_id, body, db)
        return await TimetableService.slot_out(slot, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.patch("/{timetable_id}", response_model=TimetableOut)
async def update_timetable(
    timetable_id: UUID,
    body: TimetableUpdate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableOut:
    """Re-point a draft timetable at a different schedule template."""
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        updated = await TimetableService.set_template(timetable_id, body.template_id, db)
    except TimetableServiceError as e:
        raise _err(e)
    return await _to_out(updated, db)


@router.post("/{timetable_id}/slots/swap", response_model=list[TimetableSlotOut])
async def swap_slots(
    timetable_id: UUID,
    body: TimetableSlotSwap,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[TimetableSlotOut]:
    """Exchange the day/period of two slots. Declared before the `{slot_id}`
    routes so "swap" is never parsed as a slot id."""
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        slots = await TimetableService.swap_slots(timetable_id, body.slot_a_id, body.slot_b_id, db)
        return [await TimetableService.slot_out(s, db) for s in slots]
    except TimetableServiceError as e:
        raise _err(e)


@router.patch("/{timetable_id}/slots/{slot_id}", response_model=TimetableSlotOut)
async def update_slot(
    timetable_id: UUID,
    slot_id: UUID,
    body: TimetableSlotUpdate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableSlotOut:
    """Move a slot to another day/period, or change its faculty, room or remarks."""
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        slot = await TimetableService.update_slot(timetable_id, slot_id, body, db)
        return await TimetableService.slot_out(slot, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.delete("/{timetable_id}/slots/{slot_id}", status_code=204)
async def delete_slot(
    timetable_id: UUID,
    slot_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        await TimetableService.delete_slot(timetable_id, slot_id, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.delete("/{timetable_id}", status_code=204)
async def delete_timetable(
    timetable_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    """Delete a timetable and its slots. Refused once PUBLISHED. Removes no
    programme, semester, course, faculty or assignment record."""
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        await TimetableService.delete_timetable(timetable_id, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.post("/{timetable_id}/submit", response_model=TimetableOut)
async def submit_timetable(
    timetable_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableOut:
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        tt = await TimetableService.submit(timetable_id, db)
        return await _to_out(tt, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.post("/{timetable_id}/publish", response_model=TimetableOut)
async def publish_timetable(
    timetable_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableOut:
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        tt = await TimetableService.publish(timetable_id, current_user.user_id, db)
        return await _to_out(tt, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.post("/{timetable_id}/approve", response_model=TimetableOut)
async def approve_timetable(
    timetable_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableOut:
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        tt = await TimetableService.approve(timetable_id, current_user.user_id, db)
        return await _to_out(tt, db)
    except TimetableServiceError as e:
        raise _err(e)


@router.post("/{timetable_id}/reject", response_model=TimetableOut)
async def reject_timetable(
    timetable_id: UUID,
    body: TimetableRejectRequest,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TimetableOut:
    tt = await TimetableService.get(timetable_id, db)
    if tt is None:
        raise HTTPException(404, detail={"error": "TIMETABLE_NOT_FOUND", "message": "Timetable not found."})
    try:
        await assert_dean_owns_section(current_user.user_id, tt.section_id, db)
        tt = await TimetableService.reject(timetable_id, current_user.user_id, body.comment, db)
        return await _to_out(tt, db)
    except TimetableServiceError as e:
        raise _err(e)
