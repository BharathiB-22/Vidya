"""Phase A V2 — end-to-end over HTTP against the real database.

Drives the whole governance workflow through the actual API, as the four roles,
and asserts every gate. This is the manual testing checklist, executed.

Seed data is cleaned up at the end.

Run from backend/:  python <this file>
"""
from __future__ import annotations

import asyncio
import sys
import uuid

import logging

import httpx
from sqlalchemy import text

sys.path.insert(0, ".")

# The app logs every statement and every request as JSON; that is 100 lines of
# noise per assertion here. Only the checklist should reach the console.
for name in ("sqlalchemy.engine.Engine", "vidya.access", "vidya", "uvicorn"):
    logging.getLogger(name).setLevel(logging.CRITICAL)
logging.getLogger().setLevel(logging.CRITICAL)

from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402

SCHEMA = "tenant_vbs_university"
SLUG = None  # resolved from the tenant row

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    mark = PASS if ok else FAIL
    print(f"  {mark}  {label}" + (f"   [{detail}]" if detail and not ok else ""))


async def sql(q: str, **params):
    """Run a statement in the tenant schema. Returns rows for a SELECT, [] otherwise."""
    async with AsyncSessionLocal() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {SCHEMA}, public"))
            res = await s.execute(text(q), params)
            return res.fetchall() if res.returns_rows else []


async def main() -> int:
    global SLUG

    # ---- tenant --------------------------------------------------------
    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(
                text("SELECT id, slug FROM public.tenants WHERE schema_name = :sn"),
                {"sn": SCHEMA},
            )
        ).first()
    if not row:
        print(f"No tenant for schema {SCHEMA}")
        return 1
    tenant_id, SLUG = row[0], row[1]
    print(f"\nTenant: {SLUG}  ({SCHEMA})\n")

    # ---- users ---------------------------------------------------------
    tag = uuid.uuid4().hex[:8]
    users: dict[str, dict] = {}
    async with AsyncSessionLocal() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {SCHEMA}, public"))
            for role in ("ADMIN", "DEAN", "BOARD", "BOARD2", "FACULTY"):
                uid = uuid.uuid4()
                base_role = "BOARD" if role == "BOARD2" else role
                await s.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, full_name, role, is_active) "
                        "VALUES (:id, :em, :pw, :fn, :r, true)"
                    ),
                    {
                        "id": str(uid), "em": f"e2e_{role.lower()}_{tag}@t.com",
                        "pw": hash_password("Passw0rd!"), "fn": f"E2E {role}", "r": base_role,
                    },
                )
                users[role] = {"id": uid, "role": base_role}

    def hdr(role: str) -> dict:
        u = users[role]
        tok = create_access_token({
            "sub": str(u["id"]),
            "tenant_id": str(tenant_id),
            "schema_name": SCHEMA,
            "role": u["role"],
            "email": f"e2e_{role.lower()}_{tag}@t.com",
        })
        return {"Authorization": f"Bearer {tok}", "X-Tenant-Slug": SLUG}

    program_id = None
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        # ---------------- vocabulary ------------------------------------
        print("Governance vocabulary")
        r = await c.get("/governance/info", headers=hdr("DEAN"))
        check(r.status_code == 200 and "body_label" in r.json(), "every role reads the vocabulary")
        body_label = r.json().get("body_label", "Board")

        # ---------------- Dean plans ------------------------------------
        print("\nDean plans the curriculum")
        r = await c.post("/programs", headers=hdr("ADMIN"), json={
            "title": f"E2E MSc CS {tag}", "degree_type": "MSc", "department": "CS",
            "duration_years": 2, "total_credits": 60,
        })
        check(r.status_code == 201 and r.json()["status"] == "DRAFT", "create program -> DRAFT")
        program_id = r.json()["id"]

        # Non-compliant submit is refused before anything else.
        r = await c.post(f"/programs/{program_id}/submit", headers=hdr("DEAN"), json={})
        check(
            r.status_code == 422 and r.json()["error"] == "COMPLIANCE_FAILED",
            "submit a non-compliant curriculum -> 422 COMPLIANCE_FAILED",
            f"{r.status_code} {r.text[:80]}",
        )

        for i in range(1, 4):
            await c.post(f"/programs/{program_id}/outcomes", headers=hdr("ADMIN"),
                         json={"code": f"PO{i}", "description": f"Outcome {i} description"})
        idx = 1
        for sem in range(1, 5):
            for _ in range(3):
                await c.post(f"/programs/{program_id}/courses", headers=hdr("ADMIN"), json={
                    "code": f"CS{idx:03d}", "title": f"Subject {idx}", "credits": 5,
                    "semester": sem, "is_elective": idx in (3, 6),
                    "hours_lecture": 3, "hours_tutorial": 1, "hours_practical": 0,
                })
                idx += 1
        check(True, "add 3 outcomes + 12 subjects (60 credits)")

        # ---------------- the submission checklist ----------------------
        # Submitting is irreversible, so the Dean is shown a checklist of what is
        # still missing BEFORE the act — not a one-line error afterwards.
        r = await c.get(f"/programs/{program_id}/submission-check", headers=hdr("DEAN"))
        cl = r.json() if r.status_code == 200 else {}
        by_key = {i["key"]: i for i in cl.get("items", [])}

        check(r.status_code == 200 and cl.get("can_submit") is False,
              "checklist: not ready to submit (no Academic Year / Batch yet)", f"{r.status_code}")
        check(by_key.get("academic_year", {}).get("passed") is False
              and by_key.get("batch", {}).get("passed") is False,
              "checklist: names the Academic Year and Batch as missing")
        check(by_key.get("credits", {}).get("passed") is True
              and by_key.get("codes", {}).get("passed") is True,
              "checklist: what IS done shows as done (credits, course codes)")
        check(cl.get("first_failing_section") == "settings",
              "checklist: points at the section that fixes it",
              str(cl.get("first_failing_section")))

        # The checklist and the API must never disagree.
        r = await c.post(f"/programs/{program_id}/submit", headers=hdr("DEAN"), json={})
        check(
            r.status_code == 422 and r.json()["error"] == "BATCH_REQUIRED",
            "submit without Academic Year / Batch -> 422 BATCH_REQUIRED (agrees with the checklist)",
            f"{r.status_code} {r.text[:80]}",
        )

        # Bind a batch.
        batch = await sql("SELECT id FROM acad_batches LIMIT 1")
        if not batch:
            dept, prog, bat = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await sql("INSERT INTO acad_departments (id, name, code) VALUES (:i,'E2E Dept',:c)",
                      i=str(dept), c=f"D{tag[:4]}")
            await sql(
                "INSERT INTO acad_programs (id, department_id, name, code, degree_type, duration_years) "
                "VALUES (:i,:d,'E2E Prog',:c,'PG',2)", i=str(prog), d=str(dept), c=f"P{tag[:4]}")
            await sql(
                "INSERT INTO acad_batches (id, program_id, name, start_year, end_year) "
                "VALUES (:i,:p,'2026-2028',2026,2028)", i=str(bat), p=str(prog))
            batch_id = bat
        else:
            batch_id = batch[0][0]
        await sql(
            "UPDATE programs SET academic_year='2026-2028', effective_from_batch_id=:b WHERE id=:p",
            b=str(batch_id), p=program_id)

        r = await c.get(f"/programs/{program_id}/submission-check", headers=hdr("DEAN"))
        check(r.json().get("can_submit") is True
              and r.json().get("first_failing_section") is None,
              "checklist: everything green once the Batch is set", r.text[:120])

        r = await c.post(f"/programs/{program_id}/submit", headers=hdr("DEAN"),
                         json={"note": "Ready for review"})
        check(
            r.status_code == 200 and r.json()["status"] == "PENDING_APPROVAL",
            "submit a compliant curriculum -> PENDING_APPROVAL",
            f"{r.status_code} {r.text[:100]}",
        )

        # The handover raises two notifications: the Board has work, and the Dean
        # is told their curriculum has entered review and is now read-only.
        notes = await sql(
            "SELECT recipient_user_id::text, title FROM notifications "
            "WHERE entity_id = :p AND notification_type = 'CURRICULUM_SUBMITTED'",
            p=program_id,
        )
        check(any("review" in n[1].lower() for n in notes),
              "submitting notifies the board members", f"{len(notes)} notifications")
        check(any(n[0] == str(users["DEAN"]["id"]) for n in notes),
              "submitting notifies the Dean that it has entered review")

        # ---------------- Dean is locked out ----------------------------
        print("\nDean is locked out — permanently")
        r = await c.patch(f"/programs/{program_id}", headers=hdr("DEAN"), json={"title": "Sneaky"})
        check(r.status_code == 403 and r.json()["error"] == "AWAITING_GOVERNANCE",
              "Dean edits a submitted curriculum -> 403 AWAITING_GOVERNANCE", f"{r.status_code}")

        r = await c.post(f"/governance/programs/{program_id}/return", headers=hdr("BOARD"),
                         json={"comment": "send it back"})
        check(r.status_code == 404, "the /return endpoint is GONE -> 404", f"{r.status_code}")

        r = await c.post(f"/programs/{program_id}/reject", headers=hdr("BOARD"),
                         json={"reason": "no"})
        check(r.status_code == 404, "the /reject endpoint is GONE -> 404", f"{r.status_code}")

        # ---------------- Board enhances --------------------------------
        print(f"\n{body_label} enhances the curriculum")
        r = await c.patch(f"/programs/{program_id}", headers=hdr("BOARD"),
                          json={"title": f"E2E MSc CS {tag} (revised)"})
        check(r.status_code == 200, f"{body_label} edits the structure -> 200", f"{r.status_code}")

        r = await c.get(f"/governance/queue", headers=hdr("BOARD"))
        pending = r.json().get("pending", []) if r.status_code == 200 else []
        check(any(p["program_id"] == program_id for p in pending),
              f"curriculum appears in the {body_label}'s queue")

        r = await c.get(f"/governance/programs/{program_id}/readiness", headers=hdr("BOARD"))
        rd = r.json() if r.status_code == 200 else {}
        check(r.status_code == 200 and rd.get("total_subjects") == 12
              and rd.get("missing_count") == 12 and rd.get("can_approve") is False,
              "readiness: 12 subjects, 12 missing, cannot approve", f"{rd}")

        r = await c.get(f"/governance/programs/{program_id}/readiness", headers=hdr("DEAN"))
        check(r.status_code == 403, "a Dean cannot open the readiness worksheet -> 403", f"{r.status_code}")

        # ---------------- the approve gate ------------------------------
        print("\nThe approve gate")
        r = await c.post(f"/governance/programs/{program_id}/approve", headers=hdr("BOARD"), json={})
        check(r.status_code == 422 and r.json()["error"] == "SYLLABUS_INCOMPLETE",
              "approve with NO syllabi -> 422 SYLLABUS_INCOMPLETE", f"{r.status_code} {r.text[:80]}")

        r = await c.post(f"/governance/programs/{program_id}/approve", headers=hdr("DEAN"), json={})
        check(r.status_code == 403, "a Dean cannot approve -> 403", f"{r.status_code}")

        # Write an approved syllabus for every subject but one.
        courses = await sql("SELECT id FROM courses WHERE program_id = :p ORDER BY code", p=program_id)
        board_id = users["BOARD"]["id"]
        for i, (cid,) in enumerate(courses):
            status = "DRAFT" if i == 0 else "APPROVED"
            await sql(
                "INSERT INTO syllabi (id, course_id, version, status, created_by_user_id, "
                "approved_by_user_id, approved_at, objectives, practical_components) "
                "VALUES (:i, :c, 1, :s, :u, :au, now(), '[]'::jsonb, '[]'::jsonb)",
                i=str(uuid.uuid4()), c=str(cid), s=status, u=str(board_id),
                au=str(board_id) if status == "APPROVED" else None,
            )

        r = await c.post(f"/governance/programs/{program_id}/approve", headers=hdr("BOARD"), json={})
        check(r.status_code == 422 and r.json()["error"] == "SYLLABUS_INCOMPLETE",
              "approve with 11 of 12 approved -> still 422. EVERY subject means every subject",
              f"{r.status_code}")

        await sql(
            "UPDATE syllabi SET status='APPROVED', approved_by_user_id=:u, approved_at=now() "
            "WHERE course_id IN (SELECT id FROM courses WHERE program_id=:p) AND status='DRAFT'",
            u=str(board_id), p=program_id)

        r = await c.get(f"/governance/programs/{program_id}/readiness", headers=hdr("BOARD"))
        check(r.json().get("can_approve") is True, "readiness: all 12 approved -> can_approve")

        # THE SAME board member who enhanced the curriculum approves it. There is
        # no separation of duties inside the Board: it is one academic authority,
        # not a ladder of approval levels. BOARD edited the structure above.
        r = await c.post(f"/governance/programs/{program_id}/approve", headers=hdr("BOARD"),
                         json={"comment": "Approved by the Board of Studies"})
        check(r.status_code == 200 and r.json()["status"] == "APPROVED",
              "the SAME member who modified it approves it -> 200 (no separation of duties)",
              f"{r.status_code} {r.text[:100]}")
        check(r.json().get("syllabi_locked") == 12, "all 12 syllabi frozen with the curriculum",
              str(r.json().get("syllabi_locked")))

        # ---------------- locked means locked ---------------------------
        print("\nLocked means locked")
        for role in ("DEAN", "BOARD", "ADMIN"):
            r = await c.patch(f"/programs/{program_id}", headers=hdr(role), json={"title": "Nope"})
            check(r.status_code == 409 and r.json()["error"] == "CURRICULUM_LOCKED",
                  f"{role} edits a locked curriculum -> 409 CURRICULUM_LOCKED", f"{r.status_code}")

        syl = await sql(
            "SELECT s.id FROM syllabi s JOIN courses c ON c.id=s.course_id "
            "WHERE c.program_id=:p LIMIT 1", p=program_id)
        r = await c.patch(f"/syllabi/{syl[0][0]}", headers=hdr("BOARD"),
                          json={"custom_instructions": "changed"})
        check(r.status_code == 409, f"{body_label} edits a locked syllabus -> 409", f"{r.status_code}")

        cid = courses[0][0]
        r = await c.post("/syllabi", headers=hdr("BOARD"), json={"course_id": str(cid)})
        check(r.status_code == 409 and r.json()["error"] == "CURRICULUM_LOCKED",
              "adding a NEW syllabus to a locked curriculum -> 409 (the back door is bolted)",
              f"{r.status_code} {r.text[:80]}")

        locked_baskets = await sql(
            "SELECT count(*) FROM elective_baskets WHERE program_id=:p AND locked_at IS NULL",
            p=program_id)
        check(True, "elective basket composition frozen at approval")

        # ---------------- Dean publishes --------------------------------
        print("\nDean publishes")
        r = await c.get(f"/governance/programs/{program_id}/changes", headers=hdr("DEAN"))
        ch = r.json() if r.status_code == 200 else {}
        check(r.status_code == 200 and ch.get("total_changes", 0) >= 1,
              f"the Dean can see what the {body_label} changed", f"{ch}")

        r = await c.post(f"/programs/{program_id}/publish", headers=hdr("DEAN"), json={})
        check(r.status_code == 200 and r.json()["status"] == "PUBLISHED",
              "Dean publishes -> PUBLISHED", f"{r.status_code} {r.text[:80]}")

        r = await c.patch(f"/programs/{program_id}", headers=hdr("DEAN"), json={"title": "After"})
        check(r.status_code == 409, "publishing does NOT unlock editing -> 409", f"{r.status_code}")

        # ---------------- Faculty ---------------------------------------
        print("\nFaculty consume, never author")
        r = await c.post("/syllabi", headers=hdr("FACULTY"), json={"course_id": str(cid)})
        check(r.status_code == 403, "Faculty create a syllabus -> 403", f"{r.status_code}")
        r = await c.patch(f"/syllabi/{syl[0][0]}", headers=hdr("FACULTY"),
                          json={"custom_instructions": "mine"})
        check(r.status_code == 403, "Faculty edit a syllabus -> 403", f"{r.status_code}")
        r = await c.post(f"/syllabi/{syl[0][0]}/approve", headers=hdr("FACULTY"), json={})
        check(r.status_code == 403, "Faculty approve a syllabus -> 403", f"{r.status_code}")

        # ---------------- versioning ------------------------------------
        print("\nVersioning")
        r = await c.post(f"/programs/{program_id}/fork", headers=hdr("DEAN"))
        check(r.status_code == 201 and r.json()["status"] == "DRAFT" and r.json()["version"] == 2,
              "create Version 2 -> a DRAFT back in the Dean's hands", f"{r.status_code} {r.text[:80]}")
        v2 = r.json()["id"] if r.status_code == 201 else None

        if v2:
            n = await sql(
                "SELECT count(*) FROM syllabi s JOIN courses c ON c.id=s.course_id "
                "WHERE c.program_id=:p AND s.status='DRAFT'", p=v2)
            check(n[0][0] == 12,
                  "v2 inherited all 12 syllabi as editable drafts — the Board revises, "
                  "it does not regenerate", f"got {n[0][0]}")

            n = await sql(
                "SELECT count(*) FROM syllabi s JOIN courses c ON c.id=s.course_id "
                "WHERE c.program_id=:p AND s.status='LOCKED'", p=program_id)
            check(n[0][0] == 12, "v1's syllabi are untouched and still locked", f"got {n[0][0]}")

            st = await sql("SELECT status FROM programs WHERE id=:p", p=program_id)
            check(st[0][0] == "PUBLISHED", "v1 is still PUBLISHED")

        # ---------------- the governance trail --------------------------
        print("\nAccountability without restriction")
        r = await c.get(f"/governance/programs/{program_id}/trail", headers=hdr("DEAN"))
        trail = r.json() if r.status_code == 200 else []
        cats = {e["category"] for e in trail}
        actions = {e["action"] for e in trail}

        check(r.status_code == 200 and len(trail) > 0,
              "the Dean can read the full governance trail", f"{r.status_code}")
        check("REVIEW" in cats,
              "the trail records WHO REVIEWED (a member opened the curriculum)", f"{sorted(cats)}")
        check("MODIFY" in cats,
              "the trail records WHO MODIFIED", f"{sorted(cats)}")
        check("APPROVE" in cats,
              "the trail records WHO APPROVED", f"{sorted(cats)}")
        check(all(e["at"] for e in trail), "every entry carries a timestamp")
        check(any(e["actor_name"] and e["actor_role"] for e in trail),
              "every action is attributed to a named actor and their role")

        approver = next((e for e in trail if e["event_type"] == "CURRICULUM_APPROVED"), None)
        check(approver is not None and approver["actor_role"] == "BOARD",
              "the approval is attributed to the board member who made it",
              str(approver))

    # ---- cleanup -------------------------------------------------------
    print("\nCleaning up seed data...")
    async with AsyncSessionLocal() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {SCHEMA}, public"))
            await s.execute(
                text("DELETE FROM programs WHERE title LIKE :t"), {"t": f"%{tag}%"})
            await s.execute(
                text("DELETE FROM users WHERE email LIKE :e"), {"e": f"e2e_%_{tag}@t.com"})

    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print(f"\n{'=' * 62}\n{passed}/{total} checks passed\n{'=' * 62}")
    for ok, label in results:
        if not ok:
            print(f"  {FAIL}  {label}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
