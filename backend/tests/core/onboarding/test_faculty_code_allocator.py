"""Faculty-code allocator tests — ERP Onboarding Phase 1.5."""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.onboarding.faculty_code_allocator import FacultyCodeAllocator

_engine = create_async_engine(
    settings.DATABASE_URL, echo=False, connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def test_format_code():
    assert FacultyCodeAllocator.format_code("FAC", 1) == "FAC0001"
    assert FacultyCodeAllocator.format_code("FAC", 42) == "FAC0042"
    assert FacultyCodeAllocator.format_code("scafac", 7) == "SCAFAC0007"


@pytest.mark.asyncio
async def test_allocate_contiguous(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            codes = await FacultyCodeAllocator.allocate_codes(s, count=3)
    assert codes == ["FAC0001", "FAC0002", "FAC0003"]


@pytest.mark.asyncio
async def test_allocate_resumes_across_calls(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            first = await FacultyCodeAllocator.allocate_codes(s, count=2)
            second = await FacultyCodeAllocator.allocate_codes(s, count=2)
    assert first == ["FAC0001", "FAC0002"]
    assert second == ["FAC0003", "FAC0004"]


@pytest.mark.asyncio
async def test_seed_from_existing(test_tenant_a):
    """Counter advances past the highest existing faculty_code on seed."""
    schema = test_tenant_a["schema_name"]
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            uid = "11111111-1111-1111-1111-111111111111"
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, 'x@t.edu', 'x', 'FACULTY', 'X', true)"
            ), {"id": uid})
            await s.execute(text(
                "INSERT INTO sis_faculty_profiles (user_id, faculty_code, is_active, lifecycle_status) "
                "VALUES (:id, 'FAC0009', true, 'ACTIVE')"
            ), {"id": uid})
            await FacultyCodeAllocator.seed_counter_from_existing(s)
            nxt = await FacultyCodeAllocator.allocate_codes(s, count=1)
    assert nxt == ["FAC0010"]


@pytest.mark.asyncio
async def test_concurrent_allocations_are_gap_free(test_tenant_a):
    """20 concurrent single-code allocations → 20 unique, contiguous codes."""
    schema = test_tenant_a["schema_name"]

    async def _one():
        async with _Session() as s:
            async with s.begin():
                await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
                return (await FacultyCodeAllocator.allocate_codes(s, count=1))[0]

    results = await asyncio.gather(*[_one() for _ in range(20)])
    assert len(set(results)) == 20
    seqs = sorted(int(c[3:]) for c in results)
    assert seqs == list(range(1, 21))
