"""SIS Import Batch — H64.1 Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ImportBatchOut(BaseModel):
    id:             UUID
    batch_ref:      str
    imported_by:    UUID
    imported_at:    datetime
    record_type:    str
    total_records:  int
    success_count:  int
    failed_count:   int
    is_rolled_back: bool
    rolled_back_by: Optional[UUID]
    rolled_back_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ImportBatchListOut(BaseModel):
    items: list[ImportBatchOut]
    total: int


class RollbackOut(BaseModel):
    batch_id:       UUID
    batch_ref:      str
    rolled_back_at: Optional[datetime]
    message:        str
