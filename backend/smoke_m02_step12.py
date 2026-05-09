"""
Smoke tests for STEP-12: M02 syllabus export task.
Run from backend/:  python smoke_m02_step12.py
"""
import sys, os, io, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL",   "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",      "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",     "dummy_secret_for_smoke_test_only_32ch!")
os.environ.setdefault("S3_ENDPOINT",    "http://localhost:9000")
os.environ.setdefault("S3_BUCKET",      "dummy")
os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("ENVIRONMENT",    "development")

# ---------------------------------------------------------------------------
# 1. Import guard
# ---------------------------------------------------------------------------
from app.workers.heavy.syllabus_export import (
    export_syllabus,
    _generate_pdf,
    _generate_docx,
    _generate_json,
    _s3_put_object,
)
print("PASS 1: syllabus_export module imports cleanly")

# ---------------------------------------------------------------------------
# 2. Task name + Celery registration
# ---------------------------------------------------------------------------
assert export_syllabus.name == "app.workers.heavy.export_syllabus", (
    f"Wrong task name: {export_syllabus.name}"
)
from app.workers.celery_app import celery_app
assert "app.workers.heavy.syllabus_export" in celery_app.conf.include, (
    "syllabus_export not in celery_app include list"
)
print("PASS 2: task name correct + Celery autodiscovery registered")

# ---------------------------------------------------------------------------
# 3. Heavy queue routing applies
# ---------------------------------------------------------------------------
routes = celery_app.conf.task_routes
assert "app.workers.heavy.*" in routes
assert routes["app.workers.heavy.*"]["queue"] == "celery-heavy"
print("PASS 3: routes to celery-heavy queue")

# ---------------------------------------------------------------------------
# 4. Build minimal fake ORM objects for generator tests
# ---------------------------------------------------------------------------
import uuid
from types import SimpleNamespace
from datetime import datetime, timezone

def _po(code, desc="Programme outcome desc", order=1):
    return SimpleNamespace(
        id=uuid.uuid4(), code=code, description=desc, bloom_level="APPLY",
        display_order=order,
    )

def _mapping(po_id, strength="HIGH"):
    from app.modules.m02_syllabus.models import MappingStrength
    return SimpleNamespace(
        po_id=po_id,
        mapping_strength=MappingStrength.HIGH if strength == "HIGH" else MappingStrength.MEDIUM,
        justification="Test justification",
    )

def _co(code, desc, bloom_val, order, mappings=None):
    from app.modules.m02_syllabus.models import BloomLevel
    return SimpleNamespace(
        id=uuid.uuid4(), code=code, description=desc,
        bloom_level=BloomLevel.APPLY,
        display_order=order,
        mappings=mappings or [],
    )

def _unit(num, title, hours=12, topics=None, pedagogy="Lecture"):
    return SimpleNamespace(
        id=uuid.uuid4(), unit_number=num, title=title,
        total_hours=hours,
        topics=topics or [
            {"title": "Introduction", "sub_topics": ["Basics", "Overview"]},
            {"title": "Advanced topics"},
        ],
        pedagogy=pedagogy,
        bloom_summary={"APPLY": 3, "UNDERSTAND": 2},
    )

def _ref(title, ref_type_val="TEXTBOOK", confirmed=True, doi=None, isbn=None):
    from app.modules.m02_syllabus.models import RefType, RefSource
    return SimpleNamespace(
        id=uuid.uuid4(), title=title,
        authors=["Author A", "Author B"],
        year=2023,
        ref_type=SimpleNamespace(value=ref_type_val),
        source=SimpleNamespace(value="CROSSREF"),
        doi=doi, isbn=isbn, url=None, publisher="Test Publisher",
        is_confirmed=confirmed,
    )

from app.modules.m02_syllabus.models import SyllabusStatus

pos  = [_po("PO1", "Analyse", 1), _po("PO2", "Design", 2), _po("PO3", "Evaluate", 3)]
co1  = _co("CO1", "Understand fundamentals",    "UNDERSTAND", 1)
co2  = _co("CO2", "Apply algorithms",           "APPLY",      2)
co3  = _co("CO3", "Evaluate system designs",    "EVALUATE",   3)
co4  = _co("CO4", "Create novel solutions",     "CREATE",     4)

# Add CO-PO mappings
co1.mappings = [_mapping(pos[0].id, "HIGH"), _mapping(pos[1].id, "MEDIUM")]
co2.mappings = [_mapping(pos[1].id, "HIGH"), _mapping(pos[2].id, "HIGH")]
co3.mappings = [_mapping(pos[2].id, "MEDIUM")]
co4.mappings = []

units = [
    _unit(1, "Introduction to Computing"),
    _unit(2, "Data Structures"),
    _unit(3, "Algorithm Design"),
    _unit(4, "System Design and Architecture", pedagogy="Flipped Classroom"),
]
refs  = [
    _ref("Introduction to Algorithms",    "TEXTBOOK", confirmed=True,  isbn="978-0-262-033848"),
    _ref("Design Patterns",               "REFERENCE", confirmed=True, doi="10.1234/test"),
    _ref("Journal of Computer Science",   "JOURNAL",  confirmed=True),
    _ref("Unconfirmed AI Reference",      "TEXTBOOK", confirmed=False),
]

syllabus = SimpleNamespace(
    id=uuid.uuid4(),
    course_id=uuid.uuid4(),
    version=2,
    status=SyllabusStatus.FACULTY_APPROVED,
    approved_at=datetime.now(timezone.utc),
    locked_at=None,
    ai_model="gemini-1.5-pro",
    outcomes=[co1, co2, co3, co4],
    units=units,
    references=refs,
)

course = SimpleNamespace(
    id=uuid.uuid4(),
    program_id=uuid.uuid4(),
    code="CS301",
    title="Data Structures and Algorithms",
    credits=4,
    semester=3,
    hours_lecture=3,
    hours_tutorial=1,
    hours_practical=0,
    description="Core CS course covering algorithms and data structures.",
)

print("PASS 4: fake ORM objects built")

# ---------------------------------------------------------------------------
# 5. JSON export — structure + confirmed refs only
# ---------------------------------------------------------------------------
json_buf = io.BytesIO()
_generate_json(json_buf, syllabus, course, pos)
json_buf.seek(0)
doc = json.loads(json_buf.read().decode("utf-8"))

assert "export_metadata"  in doc, "Missing export_metadata"
assert "course"           in doc, "Missing course"
assert "course_outcomes"  in doc, "Missing course_outcomes"
assert "co_po_matrix"     in doc, "Missing co_po_matrix"
assert "units"            in doc, "Missing units"
assert "references"       in doc, "Missing references"

assert doc["export_metadata"]["version"] == 2
assert doc["export_metadata"]["status"]  == "FACULTY_APPROVED"
assert doc["course"]["code"]             == "CS301"
assert len(doc["course_outcomes"])       == 4
assert len(doc["co_po_matrix"]["program_outcomes"]) == 3
assert len(doc["units"])                 == 4

# Only confirmed refs exported
confirmed_count = sum(1 for r in refs if r.is_confirmed)
assert len(doc["references"]) == confirmed_count, (
    f"Expected {confirmed_count} confirmed refs, got {len(doc['references'])}"
)

# CO-PO mappings present
mappings_list = doc["co_po_matrix"]["mappings"]
assert len(mappings_list) == 4
co1_entry = next(m for m in mappings_list if m["co_code"] == "CO1")
assert len(co1_entry["po_mappings"]) == 2

print(f"PASS 5: JSON export correct ({confirmed_count} confirmed refs, CO-PO matrix present)")

# ---------------------------------------------------------------------------
# 6. PDF export — produces non-empty bytes
# ---------------------------------------------------------------------------
try:
    pdf_buf = io.BytesIO()
    _generate_pdf(pdf_buf, syllabus, course, pos)
    pdf_buf.seek(0)
    pdf_bytes = pdf_buf.read()
    assert len(pdf_bytes) > 1000, f"PDF too small: {len(pdf_bytes)} bytes"
    assert pdf_bytes[:4] == b"%PDF", "PDF magic bytes missing"
    print(f"PASS 6: PDF export produces valid PDF ({len(pdf_bytes)} bytes)")
except ImportError as e:
    print(f"SKIP 6: reportlab not installed — {e}")

# ---------------------------------------------------------------------------
# 7. DOCX export — produces non-empty bytes (OOXML zip)
# ---------------------------------------------------------------------------
try:
    docx_buf = io.BytesIO()
    _generate_docx(docx_buf, syllabus, course, pos)
    docx_buf.seek(0)
    docx_bytes = docx_buf.read()
    assert len(docx_bytes) > 1000, f"DOCX too small: {len(docx_bytes)} bytes"
    assert docx_bytes[:2] == b"PK", "DOCX zip magic bytes missing"
    print(f"PASS 7: DOCX export produces valid DOCX ({len(docx_bytes)} bytes)")
except ImportError as e:
    print(f"SKIP 7: python-docx not installed — {e}")

# ---------------------------------------------------------------------------
# 8. Export eligibility: ADMIN_LOCKED also passes
# ---------------------------------------------------------------------------
locked_syllabus = SimpleNamespace(**vars(syllabus))
locked_syllabus.status   = SyllabusStatus.ADMIN_LOCKED
locked_syllabus.locked_at = datetime.now(timezone.utc)
locked_syllabus.approved_at = None

json_buf2 = io.BytesIO()
_generate_json(json_buf2, locked_syllabus, course, pos)
json_buf2.seek(0)
doc2 = json.loads(json_buf2.read().decode("utf-8"))
assert doc2["export_metadata"]["status"] == "ADMIN_LOCKED"
print("PASS 8: ADMIN_LOCKED syllabus exports correctly")

# ---------------------------------------------------------------------------
# 9. Unconfirmed refs excluded from all exports
# ---------------------------------------------------------------------------
unconfirmed_only_syllabus = SimpleNamespace(**vars(syllabus))
unconfirmed_only_syllabus.references = [_ref("AI Unconfirmed", confirmed=False)]

json_buf3 = io.BytesIO()
_generate_json(json_buf3, unconfirmed_only_syllabus, course, pos)
json_buf3.seek(0)
doc3 = json.loads(json_buf3.read().decode("utf-8"))
assert doc3["references"] == [], "Unconfirmed refs must not appear in export"
print("PASS 9: unconfirmed references excluded from export")

# ---------------------------------------------------------------------------
# 10. AuditEventType has SYLLABUS_EXPORT_COMPLETED and SYLLABUS_EXPORT_FAILED
# ---------------------------------------------------------------------------
from app.core.audit_log.models import AuditEventType
assert hasattr(AuditEventType, "SYLLABUS_EXPORT_COMPLETED")
assert hasattr(AuditEventType, "SYLLABUS_EXPORT_FAILED")
print("PASS 10: SYLLABUS_EXPORT_COMPLETED and SYLLABUS_EXPORT_FAILED exist in AuditEventType")

print("\nAll smoke tests passed. STEP-12 export task is correct.")
