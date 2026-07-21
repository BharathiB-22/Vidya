"""
Unit tests for the async AI generation lifecycle:
  1. VidyaTask.on_failure reverts entity status via _revert_* kwargs.
  2. stale_task_cleanup marks FAILED and reverts entity status via payload.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Test 1: VidyaTask.on_failure reverts entity status
# ---------------------------------------------------------------------------

def test_on_failure_reverts_entity_status():
    """
    When a task fails with _revert_* kwargs, on_failure must:
      - mark the task_job FAILED
      - UPDATE the entity table to the revert status
    """
    from app.workers.base_task import VidyaTask

    task = VidyaTask()
    task.name = "test_task"

    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_begin = MagicMock()
    mock_begin.__enter__ = lambda s: s
    mock_begin.__exit__ = MagicMock(return_value=False)
    mock_conn.begin.return_value = mock_begin

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn

    with patch("app.workers.base_task._get_sync_engine", return_value=mock_engine):
        task.on_failure(
            exc=ValueError("Groq error"),
            task_id="fake-task-id",
            args=(),
            kwargs={
                "job_id":         "aaaaaaaa-0000-0000-0000-000000000001",
                "_revert_table":  "programs",
                "_revert_pk":     "bbbbbbbb-0000-0000-0000-000000000002",
                "_revert_schema": "tenant_demo_university",
                "_revert_status": "GENERATION_FAILED",
            },
            einfo=None,
        )

    # engine.connect() must be called at least twice: once for _write_status, once for _revert
    assert mock_engine.connect.call_count >= 2

    # Extract all SQL strings that were executed
    executed_sqls = [
        str(c.args[0])
        for c in mock_conn.execute.call_args_list
        if c.args
    ]

    # At least one call must UPDATE the entity table
    revert_calls = [s for s in executed_sqls if "tenant_demo_university.programs" in s]
    assert revert_calls, (
        f"Expected a revert UPDATE on tenant_demo_university.programs, "
        f"got SQL calls: {executed_sqls}"
    )


# ---------------------------------------------------------------------------
# Test 2: stale_task_cleanup marks FAILED and reverts entity status
# ---------------------------------------------------------------------------

def test_stale_task_cleanup_reverts_entity():
    """
    stale_task_cleanup must:
      - UPDATE task_job status to FAILED
      - UPDATE entity table to GENERATION_FAILED via the revert key in payload
    """
    from app.workers.heavy.stale_task_cleanup import stale_task_cleanup

    stale_row = MagicMock()
    stale_row.id = "cccccccc-0000-0000-0000-000000000003"
    stale_row.status = "RUNNING"
    stale_row.payload = {
        "program_id": "dddddddd-0000-0000-0000-000000000004",
        "schema_name": "tenant_demo",
        "revert": {
            "table":  "programs",
            "pk":     "dddddddd-0000-0000-0000-000000000004",
            "schema": "tenant_demo",
            "status": "GENERATION_FAILED",
        },
    }

    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_begin = MagicMock()
    mock_begin.__enter__ = lambda s: s
    mock_begin.__exit__ = MagicMock(return_value=False)
    mock_conn.begin.return_value = mock_begin
    mock_conn.execute.return_value.fetchall.return_value = [stale_row]

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn

    with (
        patch("sqlalchemy.create_engine", return_value=mock_engine),
        patch("app.config.settings"),
    ):
        result = stale_task_cleanup()

    assert result == {"cleaned": 1}

    executed_sqls = [
        str(c.args[0])
        for c in mock_conn.execute.call_args_list
        if c.args
    ]

    # Must UPDATE task_jobs to FAILED
    job_failed_calls = [s for s in executed_sqls if "task_jobs" in s and "FAILED" in s]
    assert job_failed_calls, f"Expected task_jobs UPDATE to FAILED, got: {executed_sqls}"

    # Must revert entity table
    entity_revert_calls = [s for s in executed_sqls if "tenant_demo.programs" in s]
    assert entity_revert_calls, f"Expected entity revert SQL, got: {executed_sqls}"
