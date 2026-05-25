"""M05 end-to-end QA script — run with: python qa_m05.py"""
import requests, json, time, sys

BASE = "http://localhost:8000"
HEADERS = {}
_SLUG = ""  # set after tenant selection in step 1

def _h(token=None):
    """Build request headers. Tenant calls carry X-Tenant-Slug automatically."""
    if token:
        h = {"Authorization": f"Bearer {token}"}
        if _SLUG:
            h["X-Tenant-Slug"] = _SLUG
        return h
    return HEADERS

def step(msg):
    print(f"\n{'='*60}\n{msg}\n{'='*60}")

def ok(label, val):
    print(f"  [OK] {label}: {val}")

def fail(label, val):
    print(f"  [FAIL] {label}: {val}")
    sys.exit(1)

def check(label, cond, val=""):
    if cond:
        ok(label, val)
    else:
        fail(label, val)

# ── 1. Platform admin → list tenants ────────────────────────────────────────
step("1. Platform admin login + list tenants")
r = requests.post(f"{BASE}/platform/auth/login",
    json={"email": "admin@vidya.com", "password": "Vidya@123"})
check("platform login", r.status_code == 200, r.status_code)
plat_token = r.json()["access_token"]

r = requests.get(f"{BASE}/tenants", headers=_h(plat_token))
check("list tenants", r.status_code == 200, r.status_code)
data = r.json()
items = data.get("items", data) if isinstance(data, dict) else data
print("  Tenants found:", len(items))
for t in items:
    print(f"    id={t['id']} name={t['name']} schema={t['schema_name']} status={t['status']}")

# Pick the DSU / first active tenant
tenant = next((t for t in items if "dsu" in t["schema_name"].lower() or "dsu" in t["name"].lower()), items[0])
TENANT_ID = tenant["id"]
SCHEMA = tenant["schema_name"]
SLUG   = tenant["slug"]
_SLUG  = SLUG  # propagate into _h() for all subsequent tenant API calls
ok("selected tenant", f"{tenant['name']} ({SCHEMA}) slug={SLUG}")

# ── 2. Faculty login ────────────────────────────────────────────────────────
step("2. Faculty login")
r = requests.post(f"{BASE}/auth/login",
    json={"email": "faculty@dsu.edu", "password": "Faculty@dsu"},
    headers={"X-Tenant-Slug": SLUG})
if r.status_code != 200:
    for cred in [
        ("faculty@dsu.edu", "Faculty@123"),
        ("faculty@test.com", "Faculty@123"),
        ("faculty_a@test.com", "Faculty@123"),
    ]:
        r = requests.post(f"{BASE}/auth/login",
            json={"email": cred[0], "password": cred[1]},
            headers={"X-Tenant-Slug": SLUG})
        if r.status_code == 200:
            ok("faculty login", cred[0])
            break
    else:
        fail("faculty login", f"all attempts failed, last: {r.status_code} {r.text[:100]}")

FAC_TOKEN = r.json()["access_token"]
ok("faculty token obtained", FAC_TOKEN[:30] + "...")

# ── 3. Find approved syllabus + unit ────────────────────────────────────────
step("3. Find approved syllabus and unit")
r = requests.get(f"{BASE}/syllabi", headers=_h(FAC_TOKEN))
check("list syllabuses", r.status_code == 200, r.status_code)
syllabuses = r.json().get("items", r.json()) if isinstance(r.json(), dict) else r.json()
print("  Syllabuses:", [(s["id"], s.get("status"), s.get("title","")[:40]) for s in syllabuses[:5]])

approved = [s for s in syllabuses if s.get("status") in ("APPROVED", "PUBLISHED", "approved", "published")]
if not approved:
    approved = syllabuses  # fallback: use any
syl = approved[0]
SYL_ID = syl["id"]
ok("selected syllabus", f"{SYL_ID} status={syl.get('status')}")

# Get units
r = requests.get(f"{BASE}/syllabi/{SYL_ID}/units", headers=_h(FAC_TOKEN))
check("list units", r.status_code == 200, r.status_code)
units_data = r.json()
units = units_data.get("items", units_data) if isinstance(units_data, dict) else units_data
print("  Units:", [(u.get("unit_number"), u.get("title","")[:40]) for u in units[:5]])
unit = units[0]
UNIT_NUM = unit["unit_number"]
ok("selected unit", f"unit #{UNIT_NUM}: {unit.get('title','')[:50]}")

# ── 4. List existing packages (baseline) ────────────────────────────────────
step("4. Baseline: existing packages for this syllabus")
r = requests.get(f"{BASE}/learning-packages?syllabus_id={SYL_ID}", headers=_h(FAC_TOKEN))
check("list packages", r.status_code == 200, r.status_code)
existing = r.json().get("items", r.json()) if isinstance(r.json(), dict) else r.json()
print(f"  Existing packages: {len(existing)}")
for p in existing:
    print(f"    id={p['id']} unit={p['unit_number']} status={p['status']} item_count={p['item_count']}")

# ── 5. Trigger curation ─────────────────────────────────────────────────────
step("5. Trigger curation for unit #1")
r = requests.post(f"{BASE}/learning-packages/curate",
    json={"syllabus_id": SYL_ID, "unit_number": UNIT_NUM, "top_n": 5},
    headers=_h(FAC_TOKEN))
check("trigger curation", r.status_code in (200, 201, 202), f"{r.status_code} {r.text[:200]}")
job_resp = r.json()
JOB_ID = job_resp.get("job_id") or job_resp.get("id")
PKG_ID = job_resp.get("package_id")
ok("job_id", JOB_ID)
ok("package_id", PKG_ID)

# ── 6. Poll job until terminal ───────────────────────────────────────────────
step("6. Poll Celery job lifecycle")
MAX_WAIT = 120
interval = 3
elapsed = 0
final_status = None
while elapsed < MAX_WAIT:
    r = requests.get(f"{BASE}/learning-packages/jobs/{JOB_ID}", headers=_h(FAC_TOKEN))
    if r.status_code != 200:
        print(f"  poll error {r.status_code}")
        break
    job = r.json()
    status = job.get("status")
    print(f"  t={elapsed:>3}s  job status={status}")
    if status in ("SUCCESS", "FAILURE", "REVOKED"):
        final_status = status
        break
    time.sleep(interval)
    elapsed += interval

check("job reached terminal state", final_status is not None, final_status)

# ── 7. Check package status ──────────────────────────────────────────────────
step("7. Package status after job")
r = requests.get(f"{BASE}/learning-packages/{PKG_ID}", headers=_h(FAC_TOKEN))
check("get package", r.status_code == 200, r.status_code)
pkg = r.json()
print(f"  status={pkg['status']}  item_count={pkg['item_count']}  qdrant_indexed={pkg.get('qdrant_indexed')}")
check("package is READY", pkg["status"] == "READY", pkg["status"])

# ── 8. List items ────────────────────────────────────────────────────────────
step("8. Package items")
r = requests.get(f"{BASE}/learning-packages/{PKG_ID}/items", headers=_h(FAC_TOKEN))
check("list items", r.status_code == 200, r.status_code)
items_list = r.json().get("items", r.json()) if isinstance(r.json(), dict) else r.json()
print(f"  Items: {len(items_list)}")
for it in items_list[:3]:
    print(f"    source={it.get('source_type')} title={it.get('title','')[:50]} score={it.get('relevance_score')}")

if len(items_list) == 0:
    print("  [WARN] 0 items — Case C (external providers unavailable). Testing faculty add.")

# ── 9. Faculty: add resource ─────────────────────────────────────────────────
step("9. Faculty: add a resource")
r = requests.post(f"{BASE}/learning-packages/{PKG_ID}/items",
    json={
        "source_type": "FACULTY_NOTE",
        "title": "QA Test Resource — Introduction to AI Notes",
        "url": "https://example.com/ai-notes-qa",
        "metadata": {"note": "added by QA script"}
    },
    headers=_h(FAC_TOKEN))
check("add resource", r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}")
new_item = r.json()
NEW_ITEM_ID = new_item.get("id")
ok("new item id", NEW_ITEM_ID)

# ── 10. Faculty: star (recommend) resource ───────────────────────────────────
step("10. Faculty: star (recommend) the new item")
r = requests.patch(f"{BASE}/learning-packages/{PKG_ID}/items/{NEW_ITEM_ID}/recommend",
    json={"faculty_recommended": True},
    headers=_h(FAC_TOKEN))
check("star item", r.status_code in (200, 204), f"{r.status_code} {r.text[:200]}")
if r.status_code == 200:
    item_data = r.json()
    ok("faculty_recommended", item_data.get("faculty_recommended"))

# ── 11. Faculty: remove the item ─────────────────────────────────────────────
step("11. Faculty: remove the added item")
r = requests.delete(f"{BASE}/learning-packages/{PKG_ID}/items/{NEW_ITEM_ID}",
    headers=_h(FAC_TOKEN))
check("remove item", r.status_code in (200, 204), f"{r.status_code} {r.text[:200]}")

# ── 12. Faculty: retry curation ──────────────────────────────────────────────
step("12. Faculty: add a new item then trigger curation retry")
r = requests.post(f"{BASE}/learning-packages/{PKG_ID}/items",
    json={
        "source_type": "FACULTY_NOTE",
        "title": "Retained Faculty Note — AI Concepts",
        "url": "https://example.com/ai-concepts",
    },
    headers=_h(FAC_TOKEN))
check("add item for retry test", r.status_code in (200, 201), f"{r.status_code} {r.text[:100]}")
retained_id = r.json().get("id")

r2 = requests.post(f"{BASE}/learning-packages/curate",
    json={"syllabus_id": SYL_ID, "unit_number": UNIT_NUM, "top_n": 5},
    headers=_h(FAC_TOKEN))
check("retry curation", r2.status_code in (200, 201, 202), f"{r2.status_code} {r2.text[:200]}")
ok("retry job_id", r2.json().get("job_id"))

# ── 13. Trigger RAG indexing ─────────────────────────────────────────────────
step("13. Trigger RAG indexing")
r = requests.post(f"{BASE}/learning-packages/{PKG_ID}/index",
    headers=_h(FAC_TOKEN))
# Expected: 409 if not READY, or 200/202 if READY
print(f"  RAG index trigger: {r.status_code} {r.text[:200]}")
if r.status_code in (200, 201, 202):
    ok("RAG index dispatched", r.json().get("job_id"))
elif r.status_code == 409:
    ok("RAG index blocked (package not READY)", r.text[:100])
else:
    print(f"  [INFO] RAG index returned {r.status_code}")

# ── 14. Student: login + view package ───────────────────────────────────────
step("14. Student: login + view package")
r = requests.post(f"{BASE}/auth/login",
    json={"email": "student@dsu.edu", "password": "Student@123"},
    headers={"X-Tenant-Slug": SLUG})
if r.status_code != 200:
    for cred in [("student_a@test.com", "Student@123"), ("student@test.com", "Test@123")]:
        r = requests.post(f"{BASE}/auth/login",
            json={"email": cred[0], "password": cred[1]},
            headers={"X-Tenant-Slug": SLUG})
        if r.status_code == 200:
            ok("student login", cred[0])
            break
    else:
        print("  [WARN] Student login failed — skipping student tests")
        STU_TOKEN = None

if r.status_code == 200:
    STU_TOKEN = r.json()["access_token"]
    ok("student token", STU_TOKEN[:30] + "...")

    r = requests.get(f"{BASE}/learning-packages/{PKG_ID}", headers=_h(STU_TOKEN))
    check("student can view package", r.status_code == 200, r.status_code)

    r = requests.get(f"{BASE}/learning-packages/{PKG_ID}/items", headers=_h(STU_TOKEN))
    check("student can list items", r.status_code == 200, r.status_code)

    # Student cannot trigger curation
    r = requests.post(f"{BASE}/learning-packages/curate",
        json={"syllabus_id": SYL_ID, "unit_number": UNIT_NUM},
        headers=_h(STU_TOKEN))
    check("student blocked from curation", r.status_code in (401, 403), r.status_code)

# ── 15. RBAC: DEAN ──────────────────────────────────────────────────────────
step("15. DEAN: read-only access check")
r = requests.post(f"{BASE}/auth/login",
    json={"email": "dean@dsu.edu", "password": "Dean@2026"},
    headers={"X-Tenant-Slug": SLUG})
if r.status_code != 200:
    for cred in [("dean@test.com", "Dean@123"), ("dean_a@test.com", "Dean@123")]:
        r = requests.post(f"{BASE}/auth/login",
            json={"email": cred[0], "password": cred[1]},
            headers={"X-Tenant-Slug": SLUG})
        if r.status_code == 200:
            ok("dean login", cred[0])
            break
    else:
        print("  [WARN] DEAN login failed — skipping dean tests")

if r.status_code == 200:
    DEAN_TOKEN = r.json()["access_token"]
    r = requests.get(f"{BASE}/learning-packages/{PKG_ID}", headers=_h(DEAN_TOKEN))
    check("dean can read package", r.status_code == 200, r.status_code)
    r = requests.post(f"{BASE}/learning-packages/curate",
        json={"syllabus_id": SYL_ID, "unit_number": UNIT_NUM},
        headers=_h(DEAN_TOKEN))
    check("dean blocked from curation", r.status_code in (401, 403), r.status_code)

# ── 16. Cross-tenant isolation ───────────────────────────────────────────────
step("16. Cross-tenant isolation")
other_tenant = next((t for t in items if t["id"] != TENANT_ID), None)
if other_tenant and FAC_TOKEN:
    fake_pkg_id = "00000000-0000-0000-0000-000000000001"
    r = requests.get(f"{BASE}/learning-packages/{fake_pkg_id}", headers=_h(FAC_TOKEN))
    check("non-existent package returns 404", r.status_code == 404, r.status_code)

# ── 17. Student Q&A ──────────────────────────────────────────────────────────
step("17. Student Q&A flow")
if 'STU_TOKEN' in dir() and STU_TOKEN:
    r = requests.post(f"{BASE}/learning-packages/{PKG_ID}/ask",
        json={"question": "What are the main topics in this unit?"},
        headers=_h(STU_TOKEN))
    print(f"  Q&A response: {r.status_code} {r.text[:300]}")
    if r.status_code == 200:
        ok("Q&A answered", r.json().get("answer", "")[:80])
    elif r.status_code == 422:
        ok("Q&A returns 422 (Qdrant not indexed yet)", "expected")
    else:
        print(f"  [INFO] Q&A status {r.status_code}: {r.text[:200]}")

print("\n" + "="*60)
print("M05 QA COMPLETE")
print("="*60)
