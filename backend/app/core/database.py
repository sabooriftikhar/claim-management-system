from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


# ── Engine ───────────────────────────────────────────────────────────────────
# echo=True in development prints all SQL — set to False in production
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,          # detects stale connections before using them
    pool_size=10,                # max persistent connections in the pool
    max_overflow=20,             # extra connections beyond pool_size allowed briefly
)

# ── Session factory ──────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,      # don't invalidate objects after commit
    autoflush=False,
    autocommit=False,
)


# ── Base model ───────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """All SQLAlchemy ORM models inherit from this."""
    pass


# ── Dependency ───────────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    FastAPI dependency — yields an async DB session per request,
    commits on success, rolls back on exception, always closes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
