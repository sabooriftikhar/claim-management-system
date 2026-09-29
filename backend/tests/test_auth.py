"""
Phase 1 auth tests — session-scoped client, NullPool engine, unique emails per run.
All 20 tests cover: register, login, protected routes, RBAC, refresh, rotation, logout.
"""
import time
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ── Helpers ───────────────────────────────────────────────────────────────────
def ue(prefix: str = "u") -> str:
    """Unique email per call."""
    return f"{prefix}_{int(time.time() * 1000)}@example.com"


async def do_register(client: AsyncClient, email: str, pw: str = "Secure123") -> dict:
    r = await client.post("/auth/register", json={
        "email": email, "password": pw, "full_name": "Test User"
    })
    assert r.status_code == 201, r.text
    return r.json()


async def do_login(client: AsyncClient, email: str, pw: str = "Secure123") -> dict:
    r = await client.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────
async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────────────────────────────────────
async def test_register_success(client: AsyncClient):
    data = await do_register(client, ue("reg"))
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "claimant"
    assert "hashed_password" not in data["user"]


async def test_register_sets_refresh_cookie(client: AsyncClient):
    r = await client.post("/auth/register", json={
        "email": ue("ck"), "password": "Secure123", "full_name": "Cookie",
    })
    assert r.status_code == 201
    assert "refresh_token" in r.cookies


async def test_register_duplicate_email(client: AsyncClient):
    email = ue("dup")
    await do_register(client, email)
    r = await client.post("/auth/register", json={
        "email": email, "password": "Secure123", "full_name": "Dup",
    })
    assert r.status_code == 409


async def test_register_no_uppercase(client: AsyncClient):
    r = await client.post("/auth/register", json={
        "email": ue("wu"), "password": "nouppercase1", "full_name": "Weak",
    })
    assert r.status_code == 422


async def test_register_no_digit(client: AsyncClient):
    r = await client.post("/auth/register", json={
        "email": ue("nd"), "password": "NoDigitPass", "full_name": "ND",
    })
    assert r.status_code == 422


async def test_register_too_short(client: AsyncClient):
    r = await client.post("/auth/register", json={
        "email": ue("sh"), "password": "Ab1", "full_name": "Short",
    })
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────
async def test_login_success(client: AsyncClient):
    email = ue("li")
    await do_register(client, email)
    data = await do_login(client, email)
    assert "access_token" in data
    assert "refresh_token" in client.cookies


async def test_login_wrong_password(client: AsyncClient):
    email = ue("wp")
    await do_register(client, email)
    r = await client.post("/auth/login", json={"email": email, "password": "WrongPass9"})
    assert r.status_code == 401


async def test_login_unknown_email(client: AsyncClient):
    r = await client.post("/auth/login", json={
        "email": "nobody_xyz_never@example.com", "password": "Secure123",
    })
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Protected endpoints & RBAC
# ─────────────────────────────────────────────────────────────────────────────
async def test_get_me_authenticated(client: AsyncClient):
    email = ue("me")
    await do_register(client, email)
    data = await do_login(client, email)
    r = await client.get("/users/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == email
    assert r.json()["role"] == "claimant"


async def test_get_me_unauthenticated(client: AsyncClient):
    # Remove auth header by not passing one
    r = await client.get("/users/me")
    assert r.status_code == 401


async def test_auth_me_alias(client: AsyncClient):
    email = ue("am")
    await do_register(client, email)
    data = await do_login(client, email)
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert r.status_code == 200
    assert r.json()["email"] == email


async def test_invalid_token_rejected(client: AsyncClient):
    r = await client.get("/users/me", headers={"Authorization": "Bearer bogustoken"})
    assert r.status_code == 401


async def test_list_users_forbidden_for_claimant(client: AsyncClient):
    email = ue("rb")
    await do_register(client, email)
    data = await do_login(client, email)
    r = await client.get("/users", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Token refresh & rotation
# ─────────────────────────────────────────────────────────────────────────────
async def test_refresh_token(client: AsyncClient):
    email = ue("rf")
    await do_register(client, email)
    await do_login(client, email)

    r = await client.post("/auth/refresh")
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()
    assert "refresh_token" in r.cookies


async def test_refresh_without_cookie(client: AsyncClient):
    """A client with no cookie must get 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as fresh:
        r = await fresh.post("/auth/refresh")
        assert r.status_code == 401


async def test_refresh_token_rotation(client: AsyncClient):
    """After rotation, the old refresh token must be rejected."""
    email = ue("rot")
    await do_register(client, email)
    await do_login(client, email)
    old_cookie = client.cookies.get("refresh_token")

    r = await client.post("/auth/refresh")
    assert r.status_code == 200

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"refresh_token": old_cookie},
    ) as c2:
        r2 = await c2.post("/auth/refresh")
        assert r2.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────────────────────────────────────
async def test_logout_success(client: AsyncClient):
    email = ue("lo")
    await do_register(client, email)
    data = await do_login(client, email)

    r = await client.post("/auth/logout", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert r.status_code == 200
    assert r.json()["message"] == "Logged out successfully."


async def test_refresh_after_logout_fails(client: AsyncClient):
    """Refresh token must be revoked after logout."""
    email = ue("ral")
    await do_register(client, email)
    data = await do_login(client, email)
    rt_cookie = client.cookies.get("refresh_token")

    await client.post("/auth/logout", headers={"Authorization": f"Bearer {data['access_token']}"})

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"refresh_token": rt_cookie},
    ) as c2:
        r = await c2.post("/auth/refresh")
        assert r.status_code == 401
