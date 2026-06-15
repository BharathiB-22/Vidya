"""USN allocator tests — Phase 1 / Step 1.

Two layers:

* Pure-unit  — USN string formatting, normalisation, and argument validation.
                No database access.
* Integration — atomic block reservation against a real PostgreSQL tenant
                schema.  Proves sequential contiguity, per-(school/year/program)
                reset, and — critically — that concurrent allocations on the
                same triple never overlap, never duplicate, and leave no gaps.

The integration tests require a live database (the ON CONFLICT ... RETURNING
row-lock semantics cannot be modelled on SQLite).  The `test_tenant_a` fixture
(tests/conftest.py) provisions a fresh tenant schema by running Alembic to head,
which includes migration 0050ten.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.onboarding.usn_allocator import UsnAllocator, UsnAllocatorError

# A generously sized pool: the concurrency test fans out more workers than the
# default pool would allow, and each worker holds a connection while contending
# on the counter row lock.
_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=30,
    max_overflow=10,
    connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _alloc(
    schema: str,
    *,
    school_code: str,
    admission_year: int,
    program_code: str,
    count: int,
) -> int:
    """Reserve a block in its own session/transaction; return the start seq."""
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await UsnAllocator.allocate_block(
                s,
                school_code=school_code,
                admission_year=admission_year,
                program_code=program_code,
                count=count,
            )


# ===========================================================================
# Pure-unit — formatting & validation (no DB)
# ===========================================================================

def test_format_usn_matches_spec():
    assert UsnAllocator.format_usn("SCA", 2026, "MCA", 1) == "SCA26MCA001"
    assert UsnAllocator.format_usn("SCA", 2026, "BCA", 2) == "SCA26BCA002"
    assert UsnAllocator.format_usn("SOM", 2026, "MBA", 12) == "SOM26MBA012"


def test_format_usn_normalises_case_and_whitespace():
    assert UsnAllocator.format_usn("  sca ", 2026, " mca", 5) == "SCA26MCA005"


def test_format_usn_two_digit_year_suffix():
    assert UsnAllocator.format_usn("SCA", 2026, "MCA", 1) == "SCA26MCA001"
    assert UsnAllocator.format_usn("SCA", 2099, "MCA", 1) == "SCA99MCA001"
    assert UsnAllocator.format_usn("SCA", 2007, "MCA", 1) == "SCA07MCA001"


def test_format_usn_custom_width():
    assert UsnAllocator.format_usn("SCA", 2026, "MCA", 7, width=4) == "SCA26MCA0007"


def test_format_usn_seq_wider_than_width_not_truncated():
    assert UsnAllocator.format_usn("SCA", 2026, "MCA", 1234) == "SCA26MCA1234"


def test_format_usn_rejects_bad_args():
    with pytest.raises(UsnAllocatorError):
        UsnAllocator.format_usn("", 2026, "MCA", 1)
    with pytest.raises(UsnAllocatorError):
        UsnAllocator.format_usn("SCA", 2026, "", 1)
    with pytest.raises(UsnAllocatorError):
        UsnAllocator.format_usn("SCA", 2026, "MCA", 0)


async def test_allocate_block_rejects_non_positive_count():
    # count is validated before any DB access, so db=None is safe here.
    with pytest.raises(UsnAllocatorError):
        await UsnAllocator.allocate_block(
            None, school_code="SCA", admission_year=2026, program_code="MCA", count=0
        )


# ===========================================================================
# Integration — atomic reservation (real DB tenant schema)
# ===========================================================================

@pytest.mark.asyncio
async def test_sequential_blocks_are_contiguous(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    first  = await _alloc(schema, school_code="SCA", admission_year=2026, program_code="MCA", count=10)
    second = await _alloc(schema, school_code="SCA", admission_year=2026, program_code="MCA", count=10)
    assert first == 1
    assert second == 11


@pytest.mark.asyncio
async def test_sequence_resets_per_program(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    mca = await _alloc(schema, school_code="SCA", admission_year=2026, program_code="MCA", count=3)
    bca = await _alloc(schema, school_code="SCA", admission_year=2026, program_code="BCA", count=3)
    assert mca == 1
    assert bca == 1  # independent counter — starts fresh


@pytest.mark.asyncio
async def test_sequence_resets_per_admission_year(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    y2026 = await _alloc(schema, school_code="SCA", admission_year=2026, program_code="MCA", count=3)
    y2027 = await _alloc(schema, school_code="SCA", admission_year=2027, program_code="MCA", count=3)
    assert y2026 == 1
    assert y2027 == 1


@pytest.mark.asyncio
async def test_single_unit_allocations(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    seqs = []
    for _ in range(5):
        seqs.append(
            await _alloc(schema, school_code="SCA", admission_year=2026, program_code="MCA", count=1)
        )
    assert seqs == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_allocate_usns_returns_formatted_contiguous(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            usns = await UsnAllocator.allocate_usns(
                s, school_code="som", admission_year=2026, program_code="mba", count=3
            )
    assert usns == ["SOM26MBA001", "SOM26MBA002", "SOM26MBA003"]


@pytest.mark.asyncio
async def test_concurrent_allocation_is_atomic(test_tenant_a):
    """The core guarantee: N concurrent reservations of the same triple yield
    contiguous, non-overlapping, gap-free, duplicate-free sequence numbers."""
    schema = test_tenant_a["schema_name"]
    n_workers = 20
    per_worker = 5
    total = n_workers * per_worker

    starts = await asyncio.gather(*[
        _alloc(schema, school_code="SCA", admission_year=2026, program_code="MCA", count=per_worker)
        for _ in range(n_workers)
    ])

    all_nums: list[int] = []
    for st in starts:
        all_nums.extend(range(st, st + per_worker))

    assert len(all_nums) == total                       # everyone got their block
    assert len(set(all_nums)) == total                  # no number issued twice
    assert sorted(all_nums) == list(range(1, total + 1))  # contiguous & gap-free from 1

    # Each worker's block must itself be contiguous and disjoint from the others
    blocks = sorted(starts)
    for i in range(1, len(blocks)):
        assert blocks[i] == blocks[i - 1] + per_worker


@pytest.mark.asyncio
async def test_concurrent_allocation_isolated_across_triples(test_tenant_a):
    """Concurrent allocations on *different* triples must not interfere — each
    independent counter still starts at 1."""
    schema = test_tenant_a["schema_name"]

    results = await asyncio.gather(
        _alloc(schema, school_code="SCA", admission_year=2026, program_code="MCA", count=4),
        _alloc(schema, school_code="SCA", admission_year=2026, program_code="BCA", count=4),
        _alloc(schema, school_code="SOM", admission_year=2026, program_code="MBA", count=4),
        _alloc(schema, school_code="SCA", admission_year=2027, program_code="MCA", count=4),
    )
    assert results == [1, 1, 1, 1]
