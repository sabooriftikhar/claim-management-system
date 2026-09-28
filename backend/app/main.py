from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.database import engine, Base, get_db


# ── Rate limiter (module-level so routers can import it) ──────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[])


# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown logic.
    - Tables are managed by Alembic migrations in production.
    - In development we create them here for convenience so the app
      boots without running `alembic upgrade head` manually.
    - Bootstrap admin is seeded on every startup (idempotent).
    """
    if settings.APP_ENV == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Seed the bootstrap admin on every startup
    from app.core.seed import ensure_bootstrap_admin
    async for db in get_db():
        await ensure_bootstrap_admin(db)
        break

    yield
    await engine.dispose()


# ── App instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Claims Management System",
    description="Production-grade claims platform — portfolio project by Abdul Saboor.",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Attach the rate limiter to the app state so SlowAPI can find it
app.state.limiter = limiter


# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,          # needed for httpOnly cookie refresh token
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception handlers ────────────────────────────────────────────────────────
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def global_500_handler(request: Request, exc: Exception):
    """Catch-all — never expose tracebacks to the client."""
    import logging
    logging.getLogger("cms").exception("Unhandled exception on %s", request.url)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": "An unexpected error occurred."},
    )


# ── Routers — registered here as each phase is built ─────────────────────────
# Phase 1 ✅
from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router

# Phase 2 ✅
from app.modules.claims.router import router as claims_router

app.include_router(auth_router,   prefix="/auth",   tags=["Auth"])
app.include_router(users_router,  prefix="/users",  tags=["Users"])
app.include_router(claims_router, prefix="/claims", tags=["Claims"])

# Phase 3+ ✅
from app.modules.documents.router import router as documents_router
from app.modules.reviews.router import router as reviews_router
from app.modules.notifications.router import router as notifications_router
from app.modules.admin.router import router as admin_router

app.include_router(documents_router,     prefix="/claims",        tags=["Documents"])
app.include_router(reviews_router,       prefix="/claims",        tags=["Reviews"])
app.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
app.include_router(admin_router)


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"], summary="Liveness check")
async def health():
    """
    Returns service version and environment.
    Used by Render's health-check and any uptime monitor.
    """
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
    }


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"], include_in_schema=False)
async def root():
    return {"message": "CMS API is running. Visit /docs for the API reference."}
