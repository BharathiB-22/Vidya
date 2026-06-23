"""Governance Directory schemas — P1.9A.

Read-only informational view of academic leadership (Deans) and
examination governance (Board Members).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DeptInfo(BaseModel):
    id: UUID
    name: str
    code: str


class GovernanceDeanItem(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    designation: Optional[str] = None
    department: Optional[DeptInfo] = None
    responsibilities: list[str] = []
    is_active: bool


class GovernanceBoardItem(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    designation: Optional[str] = None
    department: Optional[DeptInfo] = None
    is_active: bool


class GovernanceDeanListResponse(BaseModel):
    total: int
    items: list[GovernanceDeanItem]


class GovernanceBoardListResponse(BaseModel):
    total: int
    items: list[GovernanceBoardItem]
