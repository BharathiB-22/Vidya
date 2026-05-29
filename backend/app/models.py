"""
Central SQLAlchemy model registry.

Importing this module registers all ORM model classes in Base.metadata before
any database operation is attempted.  Celery workers need this because they
do not go through the FastAPI startup import chain that transitively imports
all module routers (and thus all models).

Import order follows the cross-module FK dependency graph so that SQLAlchemy's
eager FK resolution (when it occurs) always finds the referenced table:

  core.auth  (users)
  → m_academics  (acad_programs)
  → m01          (courses, program_outcomes)
  → m02          (syllabi)
  → m03 / m05 / m06  (course_kits, learning_packages, lab_assignments)
  → m07 / m08 / m09 / m10  (intra-module FKs only, order irrelevant)
"""

# Public-schema models: Tenant, PlatformUser, User, RefreshToken, OTPCode …
import app.core.auth.models  # noqa: F401

# Legacy tenant-schema models (_legacy_academic_*): self-contained FKs
import app.core.onboarding.models  # noqa: F401

# m_academics must precede m01 — programs.acad_program_id → acad_programs.id
import app.modules.m_academics.models  # noqa: F401

# m01 must precede m02 — syllabi.course_id → courses.id
#                         co_po_mappings.po_id → program_outcomes.id
import app.modules.m01_program_advisor.models  # noqa: F401

# m02 must precede m03, m05, m06 — *.syllabus_id → syllabi.id
import app.modules.m02_syllabus.models  # noqa: F401

import app.modules.m03_course_kit.models  # noqa: F401
import app.modules.m05_learning_materials.models  # noqa: F401
import app.modules.m06_labs_evaluator.models  # noqa: F401

# m07-m10: intra-module FKs only; cross-module ordering not required
import app.modules.m07_research_supervision.models  # noqa: F401
import app.modules.m08_exam_setter.models  # noqa: F401
import app.modules.m09_paper_admin.models  # noqa: F401
import app.modules.m10_bell_curve.models  # noqa: F401
