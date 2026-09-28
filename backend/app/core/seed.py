"""
seed.py — Startup seeds and demo data generator.

Two functions:
  ensure_bootstrap_admin(db)   — idempotent; called every startup.
  seed_demo_data(db)           — called only by the CLI seed script.

Admin bootstrap logic:
  1. If abdulsabooriftikhar3718@gmail.com doesn't exist → create with admin role.
  2. If it exists but role != admin → promote to admin.
  3. If already admin → no-op.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.modules.users.models import User
from app.shared.enums import UserRole

logger = logging.getLogger(__name__)

BOOTSTRAP_ADMIN_EMAIL    = "abdulsabooriftikhar3718@gmail.com"
BOOTSTRAP_ADMIN_NAME     = "Abdul Saboor (Admin)"
BOOTSTRAP_ADMIN_PASSWORD = "Admin@CMS2024!"


async def ensure_bootstrap_admin(db: AsyncSession) -> None:
    """
    Idempotent — safe to call on every startup.
    Ensures abdulsabooriftikhar3718@gmail.com is an active admin.
    """
    result = await db.execute(
        select(User).where(User.email == BOOTSTRAP_ADMIN_EMAIL)
    )
    admin = result.scalar_one_or_none()

    if admin is None:
        # First ever run — create the account
        admin = User(
            email=BOOTSTRAP_ADMIN_EMAIL,
            hashed_password=hash_password(BOOTSTRAP_ADMIN_PASSWORD),
            full_name=BOOTSTRAP_ADMIN_NAME,
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        logger.info("✅ Bootstrap admin created: %s", BOOTSTRAP_ADMIN_EMAIL)
    elif admin.role != UserRole.admin:
        # Account exists but was demoted — re-promote
        admin.role = UserRole.admin
        db.add(admin)
        await db.commit()
        logger.info("✅ Bootstrap admin role restored for: %s", BOOTSTRAP_ADMIN_EMAIL)
    else:
        logger.info("✅ Bootstrap admin already OK: %s", BOOTSTRAP_ADMIN_EMAIL)


# ── Demo data (CLI only) ──────────────────────────────────────────────────────

DEMO_USERS = [
    {"email": "adjuster1@demo.com",  "full_name": "Sarah Adjuster",  "role": UserRole.adjuster, "password": "Demo@1234"},
    {"email": "adjuster2@demo.com",  "full_name": "Mark Reviewer",   "role": UserRole.adjuster, "password": "Demo@1234"},
    {"email": "claimant1@demo.com",  "full_name": "Alice Johnson",   "role": UserRole.claimant, "password": "Demo@1234"},
    {"email": "claimant2@demo.com",  "full_name": "Bob Williams",    "role": UserRole.claimant, "password": "Demo@1234"},
    {"email": "claimant3@demo.com",  "full_name": "Carol Martinez",  "role": UserRole.claimant, "password": "Demo@1234"},
]


async def seed_demo_data(db: AsyncSession) -> None:
    """
    Creates demo users if they don't already exist.
    Safe to run multiple times.
    """
    from app.modules.claims.models import Claim
    from app.shared.enums import ClaimStatus, ClaimType

    created_users = []
    for u_data in DEMO_USERS:
        result = await db.execute(select(User).where(User.email == u_data["email"]))
        existing = result.scalar_one_or_none()
        if existing is None:
            user = User(
                email=u_data["email"],
                hashed_password=hash_password(u_data["password"]),
                full_name=u_data["full_name"],
                role=u_data["role"],
                is_active=True,
            )
            db.add(user)
            created_users.append(user)
            logger.info("  Created demo user: %s (%s)", u_data["email"], u_data["role"].value)
        else:
            created_users.append(existing)

    await db.flush()

    # Fetch claimants for claim creation
    claimants = [u for u in created_users if u.role == UserRole.claimant]
    if not claimants:
        await db.commit()
        return

    SAMPLE_CLAIMS = [
        {"title": "Damaged laptop screen",        "type": ClaimType.warranty,          "amount": 450.00,  "status": ClaimStatus.submitted},
        {"title": "Missing shipment - Order #882","type": ClaimType.damaged_shipment,   "amount": 230.00,  "status": ClaimStatus.under_review},
        {"title": "Water damage reimbursement",   "type": ClaimType.reimbursement,      "amount": 1200.00, "status": ClaimStatus.approved},
        {"title": "Defective keyboard",           "type": ClaimType.warranty,          "amount": 95.00,   "status": ClaimStatus.rejected},
        {"title": "Wrong item delivered",         "type": ClaimType.damaged_shipment,   "amount": 320.00,  "status": ClaimStatus.info_requested},
        {"title": "Phone screen cracked",         "type": ClaimType.warranty,          "amount": 280.00,  "status": ClaimStatus.submitted},
        {"title": "Travel delay reimbursement",   "type": ClaimType.reimbursement,      "amount": 870.00,  "status": ClaimStatus.under_review},
        {"title": "Broken monitor on delivery",   "type": ClaimType.damaged_shipment,   "amount": 650.00,  "status": ClaimStatus.approved},
        {"title": "Software license refund",      "type": ClaimType.reimbursement,      "amount": 120.00,  "status": ClaimStatus.closed},
        {"title": "Power adapter failure",        "type": ClaimType.warranty,          "amount": 75.00,   "status": ClaimStatus.submitted},
    ]

    for i, c_data in enumerate(SAMPLE_CLAIMS):
        claimant = claimants[i % len(claimants)]
        claim = Claim(
            claimant_id=claimant.id,
            title=c_data["title"],
            claim_type=c_data["type"],
            amount=c_data["amount"],
            status=c_data["status"],
            description=f"Demo claim: {c_data['title']}. This is sample data for portfolio demonstration.",
            incident_date=datetime(2024, 1, 15 + i, tzinfo=timezone.utc),
        )
        db.add(claim)
        logger.info("  Created demo claim: %s [%s]", c_data["title"], c_data["status"].value)

    await db.commit()
    logger.info("✅ Demo data seeded successfully.")
