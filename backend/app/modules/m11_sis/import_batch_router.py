"""SIS Import Batch Router — H64.1.

GET  /sis/imports          — list all batches (paginated, ADMIN only)
GET  /sis/imports/{id}     — batch detail (ADMIN only)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.import_batch_schemas import ImportBatchListOut, ImportBatchOut
from app.modules.m11_sis.import_batch_service import ImportBatchService, ImportBatchServiceError

import_batch_router = APIRouter(tags=["SIS Import Batches"])

_ADMIN = (TenantRole.ADMIN,)


def _err(e: ImportBatchServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"error": e.code, "message": e.message})


@import_batch_router.get("/imports", response_model=ImportBatchListOut)
async def list_import_batches(
    limit:  int = Query(50, ge=1, le=200),
    offset: int = Query(0,  ge=0),
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ImportBatchListOut:
    rows, total = await ImportBatchService.list_batches(db, limit=limit, offset=offset)
    return ImportBatchListOut(
        items=[ImportBatchOut.model_validate(r) for r in rows],
        total=total,
    )


@import_batch_router.get("/imports/{batch_id}", response_model=ImportBatchOut)
async def get_import_batch(
    batch_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ImportBatchOut:
    try:
        batch = await ImportBatchService.get_batch(batch_id, db)
    except ImportBatchServiceError as e:
        raise _err(e)
    return ImportBatchOut.model_validate(batch)
