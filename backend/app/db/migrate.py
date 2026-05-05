"""
CLI: python -m app.db.migrate public
     python -m app.db.migrate tenant <schema_name>
     python -m app.db.migrate tenant --all
"""

import os
import re
import sys
import subprocess


def run_alembic(target: str, schema: str | None = None) -> None:
    env = os.environ.copy()
    env["ALEMBIC_TARGET"] = target
    if schema:
        env["TENANT_SCHEMA"] = schema
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
        env=env,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: python -m app.db.migrate public | tenant <schema> | tenant --all")
        sys.exit(1)

    if args[0] == "public":
        print("Running public schema migrations...")
        run_alembic("public")
        print("Done.")

    elif args[0] == "tenant":
        if len(args) < 2:
            print("Usage: python -m app.db.migrate tenant <schema_name> | --all")
            sys.exit(1)

        if args[1] == "--all":
            # Import here to avoid circular at module load
            import asyncio
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text
            from app.config import settings

            async def get_all_schemas():
                engine = create_async_engine(settings.DATABASE_URL)
                async with engine.connect() as conn:
                    result = await conn.execute(
                        text("SELECT schema_name FROM public.tenants WHERE is_active = true")
                    )
                    schemas = [row[0] for row in result]
                await engine.dispose()
                return schemas

            schemas = asyncio.run(get_all_schemas())
            if not schemas:
                print("No active tenants found.")
                return
            for schema in schemas:
                print(f"Migrating tenant schema: {schema}")
                run_alembic("tenant", schema)
            print(f"Done. Migrated {len(schemas)} tenant(s).")

        else:
            schema = args[1]
            if not re.match(r"^tenant_[a-z0-9_]+$", schema):
                print(f"Invalid schema name: {schema}. Must match ^tenant_[a-z0-9_]+$")
                sys.exit(1)
            print(f"Running tenant migrations for schema: {schema}")
            run_alembic("tenant", schema)
            print("Done.")

    else:
        print(f"Unknown target: {args[0]}. Use 'public' or 'tenant'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
