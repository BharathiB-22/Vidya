"""Run migration 0027ten on all active tenant schemas."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = "postgresql+asyncpg://vidya:vidya_dev@localhost:5530/vidya?ssl=disable"

UPGRADE_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS acad_program_id UUID REFERENCES acad_programs(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS ix_users_acad_program_id ON users (acad_program_id)",
]

async def main():
    engine = create_async_engine(DB_URL, echo=False)
    async with engine.connect() as conn:
        # Get active tenant schemas
        result = await conn.execute(
            text("SELECT slug, schema_name FROM public.tenants WHERE status = 'ACTIVE'")
        )
        tenants = result.fetchall()
        print(f"Found {len(tenants)} active tenant(s)")

    for row in tenants:
        slug, schema = row[0], row[1]
        print(f"\nMigrating tenant: {slug} ({schema})")
        async with engine.connect() as conn:
            await conn.execute(text(f"SET search_path = {schema}, public"))
            for sql in UPGRADE_SQL:
                print(f"  Running: {sql[:60]}…")
                await conn.execute(text(sql))
            await conn.commit()
            print(f"  Done.")

    await engine.dispose()
    print("\nMigration complete.")

asyncio.run(main())
