"""
Demo seed script — creates Demo University tenant with faculty/dean/admin users.

Idempotent: safe to run multiple times.

Usage (from backend/):
  python seed_demo.py

Users created:
  admin@demo-university.edu   / Demo1234!  (ADMIN)
  faculty@demo-university.edu / Demo1234!  (FACULTY)
  dean@demo-university.edu    / Demo1234!  (DEAN)

Tenant slug: demo-university
"""

import asyncio
import sys
from pathlib import Path

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.core.auth.models import TenantRole
from app.core.auth.repository import PublicRepository, TenantRepository as TenantUserRepository
from app.core.auth.security import hash_password
from app.core.tenants.provisioner import (
    derive_schema_name,
    generate_slug,
    run_tenant_migrations,
)
from app.core.tenants.repository import TenantRepository
from app.core.auth.models import TenantStatus

TENANT_NAME = "Demo University"
ADMIN_PASSWORD = "Demo1234!"

USERS = [
    {"email": "faculty@demo-university.edu", "password": "Demo1234!", "full_name": "Demo Faculty",  "role": TenantRole.FACULTY},
    {"email": "dean@demo-university.edu",    "password": "Demo1234!", "full_name": "Demo Dean",     "role": TenantRole.DEAN},
]


async def seed():
    slug = generate_slug(TENANT_NAME)
    schema_name = derive_schema_name(slug)

    print(f"Tenant slug:   {slug}")
    print(f"Schema name:   {schema_name}")

    async with AsyncSessionLocal() as db:
        existing = await PublicRepository.get_tenant_by_slug(slug, db)

    if existing:
        print(f"Tenant '{slug}' already exists (id={existing.id}) — skipping provisioning.")
    else:
        print("Creating tenant record …")
        async with AsyncSessionLocal() as db:
            from app.core.tenants.repository import TenantRepository
            tenant = await TenantRepository.create_tenant(
                name=TENANT_NAME,
                slug=slug,
                schema_name=schema_name,
                db=db,
            )
            await db.commit()
            tenant_id = tenant.id

        print(f"Running migrations for schema {schema_name} …")
        await run_tenant_migrations(schema_name)

        print("Seeding admin user …")
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await db.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
                await TenantUserRepository.create_user(
                    email="admin@demo-university.edu",
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role=TenantRole.ADMIN,
                    full_name="Demo Admin",
                    identifier=None,
                    db=db,
                )

        async with AsyncSessionLocal() as db:
            from app.core.tenants.repository import TenantRepository
            await TenantRepository.update_tenant(
                tenant_id,
                {"status": TenantStatus.ACTIVE, "is_active": True},
                db,
            )
            await db.commit()

        print("Tenant provisioned and activated.")

    print("Seeding additional demo users …")
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
            for u in USERS:
                existing_user = await TenantUserRepository.get_user_by_email(u["email"], db)
                if existing_user:
                    print(f"  {u['email']} already exists — skipping.")
                    continue
                await TenantUserRepository.create_user(
                    email=u["email"],
                    password_hash=hash_password(u["password"]),
                    role=u["role"],
                    full_name=u["full_name"],
                    identifier=None,
                    db=db,
                )
                print(f"  Created {u['role'].value}: {u['email']}")

    print("\nDone. Demo credentials:")
    print("  Slug:    demo-university")
    print("  Admin:   admin@demo-university.edu   / Demo1234!")
    print("  Faculty: faculty@demo-university.edu / Demo1234!")
    print("  Dean:    dean@demo-university.edu    / Demo1234!")


if __name__ == "__main__":
    asyncio.run(seed())
