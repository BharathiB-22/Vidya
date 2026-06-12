"""
M09.6 Assignment Engine — auto-allocation engine.

Pure, deterministic workload balancer.  No AI, no scoring, no side effects:
given a set of work items and a pool of eligible evaluators (each with a known
current active workload), it produces a fair allocation plan.

Kept free of DB / ORM imports so it is trivially unit-testable and reusable.

Fairness model
--------------
We use a greedy least-loaded assignment: items are handed out one at a time to
the evaluator who currently has the smallest projected active load.  Ties are
broken deterministically by the evaluator's position in the input pool so the
result is stable and reproducible (important for tests and for an auditable
allocation).  This converges to an even spread and respects pre-existing load
so a lightly-loaded evaluator catches up before everyone grows together.

This mirrors the "AI advises, humans decide" rule: the plan is a transparent,
explainable suggestion that an Admin/Dean executes; nothing here is opaque.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass


@dataclass(frozen=True)
class AllocationResult:
    """One item-to-evaluator decision in an allocation plan."""
    target_id: str
    evaluator_id: str


def balance_assignments(
    target_ids: list[str],
    evaluator_ids: list[str],
    current_load: dict[str, int] | None = None,
) -> list[AllocationResult]:
    """
    Distribute ``target_ids`` across ``evaluator_ids`` minimising peak load.

    Args:
        target_ids:    work items to allocate (order preserved for determinism).
        evaluator_ids: eligible evaluators (the pool).  Order breaks ties.
        current_load:  optional map evaluator_id -> existing active assignment
                       count.  Missing evaluators default to 0.

    Returns:
        A list of AllocationResult, one per target_id, in input order.

    Raises:
        ValueError: if there are no evaluators but there is work to allocate.
    """
    if not target_ids:
        return []
    if not evaluator_ids:
        raise ValueError("Cannot auto-allocate: evaluator pool is empty.")

    load = dict(current_load or {})

    # Min-heap of (projected_load, tiebreak_index, evaluator_id).
    # tiebreak_index keeps the original pool ordering stable across equal loads.
    heap: list[tuple[int, int, str]] = []
    for idx, ev in enumerate(evaluator_ids):
        heapq.heappush(heap, (int(load.get(ev, 0)), idx, ev))

    # Stable order index per evaluator for re-push tiebreaking.
    order_index = {ev: idx for idx, ev in enumerate(evaluator_ids)}

    plan: list[AllocationResult] = []
    for tid in target_ids:
        cur_load, _, ev = heapq.heappop(heap)
        plan.append(AllocationResult(target_id=tid, evaluator_id=ev))
        heapq.heappush(heap, (cur_load + 1, order_index[ev], ev))

    return plan


def projected_distribution(
    target_count: int,
    evaluator_ids: list[str],
    current_load: dict[str, int] | None = None,
) -> dict[str, int]:
    """
    Preview helper: how many NEW items each evaluator would receive if
    ``target_count`` items were balanced across the pool.  Used by the dry-run
    preview endpoint so an Admin can review before committing.
    """
    fake_targets = [str(i) for i in range(target_count)]
    plan = balance_assignments(fake_targets, evaluator_ids, current_load)
    out: dict[str, int] = {ev: 0 for ev in evaluator_ids}
    for r in plan:
        out[r.evaluator_id] += 1
    return out
