"""
STEP-17 smoke: M08 test suite — 75 tests, 0 failures.
Run: python check_m08_step17.py
"""
import subprocess, sys, os

env = {**os.environ,
       "PYTHONPATH": str(__import__("pathlib").Path(__file__).parent),
       "DATABASE_URL": "postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya",
       "REDIS_URL": "redis://localhost:6379/0",
       "JWT_SECRET": "1889a2bea7f4c026f5b6922687e67b4a72c47780076bf12c0233b8e1f9624cca",
       "ENVIRONMENT": "development"}

result = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/modules/m08_exam_setter/test_unit.py", "-q", "--no-header"],
    env=env
)
assert result.returncode == 0, f"Tests failed (exit {result.returncode})"
print("STEP-17 smoke: PASSED")
