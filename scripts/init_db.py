#!/usr/bin/env python3
"""Bootstrap script: Initialize the PayShield database tables."""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main():
    from store.postgres import init_db, close_db

    logger.info("Initializing database schema...")
    await init_db()
    logger.info("Database tables created successfully.")
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
