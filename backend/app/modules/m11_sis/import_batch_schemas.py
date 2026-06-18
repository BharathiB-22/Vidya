"""SIS Import Batch — H64.1 / P1.4 Pydantic schemas.

ImportBatchOut is validated from raw-SQL dicts (schema-adaptive reads via
SELECT *).  Academic context fields are Optional so that pre-0054ten databases
return None rather than crashing.
"""
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
    source_filename: Optional[str] = None
    total_records:  int
    success_count:  int
    failed_count:   int
    is_rolled_back: bool
    rolled_back_by: Optional[UUID] = None
    rolled_back_at: Optional[datetime] = None
    # P1.4: academic context — None on pre-0054ten databases or older batches
    program_id:    Optional[UUID] = None
    program_name:  Optional[str] = None
    batch_id:      Optional[UUID] = None
    batch_name:    Optional[str] = None
    semester_id:   Optional[UUID] = None
    semester_name: Optional[str] = None
    section_id:    Optional[UUID] = None
    section_name:  Optional[str] = None

    # Accepts both plain dicts (raw SQL rows) and ORM objects.
    model_config = {"from_attributes": True}


class ImportBatchListOut(BaseModel):
    items: list[ImportBatchOut]
    total: int


class RollbackOut(BaseModel):
    batch_id:       UUID
    batch_ref:      str
    rolled_back_at: Optional[datetime] = None
    message:        str
