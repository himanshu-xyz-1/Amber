#!/usr/bin/env python3
"""
Amber SRE Machine API Key Generator.
Generates cryptographically random API keys for monitoring platforms
and target cloud integrations, saving the SHA-256 hash in PostgreSQL.
"""

import asyncio
import hashlib
import secrets
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from backend.app.core.database import AsyncSessionLocal, engine, Base
from backend.app.models.user import User, UserRole


async def generate_key(name: str, role: str = "SRE"):
    raw_key = f"amb_live_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        user = User(
            email=f"{name.lower().replace(' ', '_')}@service.amber.internal",
            full_name=name,
            role=UserRole[role.upper()],
            api_key_hash=key_hash,
            is_active=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    print("=" * 60)
    print("🔑 AMBER MACHINE API KEY GENERATED")
    print("=" * 60)
    print(f"Service Identity: {user.full_name} ({user.role.value})")
    print(f"Identity ID:      {user.id}")
    print(f"Secret API Key:   {raw_key}")
    print("-" * 60)
    print("⚠️  SAVE THIS KEY NOW! It will not be shown again.")
    print("    Stored in database as SHA-256 hash:", key_hash)
    print("=" * 60)


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Production Monitoring Agent"
    role = sys.argv[2] if len(sys.argv) > 2 else "SRE"
    asyncio.run(generate_key(name, role))
