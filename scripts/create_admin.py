#!/usr/bin/env python3
"""Create an admin user for the PayShield dashboard."""

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main():
    try:
        from store.postgres import get_async_session
        from store.models import User
        from sqlalchemy import select
    except ImportError as e:
        logger.error(f"Required packages not installed: {e}")
        sys.exit(1)

    username = os.environ.get("ADMIN_USERNAME", "admin")
    role = os.environ.get("ADMIN_ROLE", "admin")

    async for session in get_async_session():
        try:
            result = await session.execute(select(User).where(User.username == username))
            existing = result.scalar_one_or_none()

            if existing:
                logger.info(f"Admin user '{username}' already exists.")
            else:
                import hashlib
                password = os.environ.get("ADMIN_PASSWORD", "payshield-admin-2026")
                hashed = hashlib.sha256(password.encode()).hexdigest()

                user = User(username=username, password_hash=hashed, role=role, is_active=True)
                session.add(user)
                await session.commit()
                logger.info(f"Admin user '{username}' created with role '{role}'.")
        finally:
            await session.close()


if __name__ == "__main__":
    asyncio.run(main())
