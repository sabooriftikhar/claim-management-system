"""
Test configuration for Phase 1.

Strategy:
  - Use a single session-scoped event loop (one loop for all tests).
  - Use a small QueuePool (pool_size=2) — keeps connections alive across
    tests so asyncpg doesn't need to re-handshake SSL for every request.
  - Dispose the pool once at session end, not between tests.
  - This avoids the Windows ProactorEventLoop + asyncpg SSL teardown bug
    that causes "Event loop is closed" errors.
"""
import asyncio
import pytest
import pytest_asyncio

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import app.core.database as db_module
from app.core.config import settings
from app.main import app


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def test_engine():
    """
    Session-scoped engine with a small pool.
    Replaces the global engine so all in-process DB calls use it.
    Disposed cleanly at session end.
    """
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        echo=False,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    # Patch globals used by get_db()
    original_engine = db_module.engine
    original_factory = db_module.AsyncSessionLocal

    db_module.engine = engine
    db_module.AsyncSessionLocal = session_factory

    yield engine

    # Restore and clean up
    db_module.engine = original_engine
    db_module.AsyncSessionLocal = original_factory
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client(test_engine):
    """Single ASGI client for the whole test session."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac
