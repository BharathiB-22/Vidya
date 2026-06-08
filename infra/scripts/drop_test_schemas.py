"""Drop broken test schemas so the test suite can recreate them cleanly."""
import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal

async def drop():
    async with AsyncSessionLocal() as s:
        async with s.begin():
            await s.execute(text("DROP SCHEMA IF EXISTS tenant_test_a CASCADE"))
            await s.execute(text("DROP SCHEMA IF EXISTS tenant_test_b CASCADE"))
            print("Dropped tenant_test_a and tenant_test_b")

asyncio.run(drop())
