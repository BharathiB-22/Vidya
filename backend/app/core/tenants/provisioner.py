import asyncio
import os
import re
import unicodedata
from pathlib import Path

from sqlalchemy import text

from app.config import settings
from app.core.auth.models import TenantRole
from app.core.auth.repository import TenantRepository as TenantUserRepository
from app.database import AsyncSessionLocal

# Lock ensures only one tenant is provisioned at a time.
# Alembic env.py reads ALEMBIC_TARGET / TENANT_SCHEMA from os.environ;
# the lock prevents concurrent mutations of those env vars.
_PROVISION_LOCK: asyncio.Lock = asyncio.Lock()

_ALEMBIC_DIR = Path(__file__).resolve().parents[3] / "alembic"


def generate_slug(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    name = name[:50].rstrip("-")
    if not name:
        raise ValueError("Tenant name produces an empty slug after normalization")
    return name


def derive_schema_name(slug: str) -> str:
    return "tenant_" + slug.replace("-", "_")


def _migrate_sync(schema_name: str) -> None:
    from alembic.config import Config
    from alembic import command

    saved_target = os.environ.get("ALEMBIC_TARGET")
    saved_schema = os.environ.get("TENANT_SCHEMA")

    os.environ["ALEMBIC_TARGET"] = "tenant"
    os.environ["TENANT_SCHEMA"] = schema_name

    try:
        cfg = Config()
        cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
        cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        command.upgrade(cfg, "head")
    finally:
        if saved_target is None:
            os.environ.pop("ALEMBIC_TARGET", None)
        else:
            os.environ["ALEMBIC_TARGET"] = saved_target
        if saved_schema is None:
            os.environ.pop("TENANT_SCHEMA", None)
        else:
            os.environ["TENANT_SCHEMA"] = saved_schema


async def run_tenant_migrations(schema_name: str) -> None:
    async with _PROVISION_LOCK:
        await asyncio.to_thread(_migrate_sync, schema_name)


async def seed_admin_user(
    schema_name: str,
    email: str,
    password_hash: str,
    full_name: str,
) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path = {schema_name}, public")
            )
            await TenantUserRepository.create_user(
                email=email,
                password_hash=password_hash,
                role=TenantRole.ADMIN,
                full_name=full_name,
                identifier=None,
                db=session,
            )
