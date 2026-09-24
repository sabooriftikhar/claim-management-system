
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

async def main():
    from app.core.database import engine, Base, AsyncSessionLocal
    from app.core.seed import ensure_bootstrap_admin, seed_demo_data

    logging.info("🌱 Starting seed...")

    # Create tables if they don't exist (development convenience)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await ensure_bootstrap_admin(db)
        await seed_demo_data(db)

    logging.info("🎉 Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
