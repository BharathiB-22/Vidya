"""Validation Report schemas — H64.8."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Severity = Literal["ERROR", "WARNING", "INFO"]


class ValidationItem(BaseModel):
    id:     UUID
    detail: str


class CheckResult(BaseModel):
    check_id:    str
    label:       str
    description: str
    severity:    Severity
    count:       int
    items:       list[ValidationItem]  # up to MAX_ITEMS each


class ValidationReportOut(BaseModel):
    generated_at:  datetime
    total_issues:  int
    checks:        list[CheckResult]
