"""STEP-01 smoke tests — M03 config + StorageEntityType."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app.config import settings
from app.core.storage.models import StorageEntityType

errors = []

# 1. M03 config keys present with correct defaults
assert settings.M03_MIN_SLIDES_PER_UNIT == 8,      "M03_MIN_SLIDES_PER_UNIT default wrong"
assert settings.M03_MIN_QUIZLETS_PER_UNIT == 2,    "M03_MIN_QUIZLETS_PER_UNIT default wrong"
assert settings.M03_DEFAULT_COMPLEXITY == "UG",     "M03_DEFAULT_COMPLEXITY default wrong"

# 2. COURSE_KIT_EXPORT present in StorageEntityType
assert hasattr(StorageEntityType, "COURSE_KIT_EXPORT"), "COURSE_KIT_EXPORT missing"
assert StorageEntityType.COURSE_KIT_EXPORT == "course_kit_export"

# 3. Legacy COURSE_KIT still present (not renamed)
assert hasattr(StorageEntityType, "COURSE_KIT"), "COURSE_KIT was accidentally removed"

# 4. MIME whitelist contains course_kit_export
wl = settings.STORAGE_MIME_WHITELIST
assert "course_kit_export" in wl, "course_kit_export missing from MIME whitelist"
assert "application/pdf" in wl["course_kit_export"]
assert "application/vnd.openxmlformats-officedocument.presentationml.presentation" in wl["course_kit_export"]

# 5. M03 module package importable
import app.modules.m03_course_kit  # noqa: F401

print("STEP-01: all 5 assertions passed.")
