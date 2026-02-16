"""Admin router — user management, subscription overrides, metrics."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from config import settings
from database import get_db
from models import LicenseKey, Machine, Subscription, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_EMAILS: set[str] = set(
    e.strip() for e in settings.admin_emails.split(",") if e.strip()
)


def _require_admin(user: User) -> None:
    """Raise 403 if user is not an admin. Use inline in each endpoint."""
    if user.email not in ADMIN_EMAILS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/stats")
async def stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get high-level licensing statistics."""
    _require_admin(user)

    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_subs = (await db.execute(select(func.count(Subscription.id)))).scalar() or 0
    active_subs = (
        await db.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status.in_(["active", "trialing"])
            )
        )
    ).scalar() or 0
    total_machines = (await db.execute(select(func.count(Machine.id)))).scalar() or 0
    active_machines = (
        await db.execute(
            select(func.count(Machine.id)).where(Machine.is_active == True)
        )
    ).scalar() or 0

    return {
        "total_users": total_users,
        "total_subscriptions": total_subs,
        "active_subscriptions": active_subs,
        "total_machines": total_machines,
        "active_machines": active_machines,
    }


@router.get("/users")
async def list_users(
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users with pagination."""
    _require_admin(user)
    limit = min(limit, 200)  # cap to prevent full-table dumps

    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    )
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "created_at": u.created_at.isoformat(),
            "trial_used": u.trial_used,
            # L11: Redact Stripe customer ID from listing (use detail endpoint for full info)
            "has_billing": bool(u.stripe_customer_id),
            "subscription_count": len(u.subscriptions),
            "machine_count": len(u.machines),
        }
        for u in users
    ]


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info for a specific user."""
    _require_admin(user)

    import uuid as _uuid

    try:
        uid = _uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    result = await db.execute(select(User).where(User.id == uid))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": str(target.id),
        "email": target.email,
        "created_at": target.created_at.isoformat(),
        "trial_used": target.trial_used,
        "stripe_customer_id": target.stripe_customer_id,
        "subscriptions": [
            {
                "id": str(s.id),
                "plan": s.plan,
                "status": s.status,
                "seats": s.seats,
                "period_end": s.current_period_end.isoformat() if s.current_period_end else None,
                "created_at": s.created_at.isoformat(),
            }
            for s in target.subscriptions
        ],
        "machines": [
            {
                "id": str(m.id),
                "machine_fingerprint": m.machine_fingerprint[:16] + "...",
                "machine_name": m.machine_name,
                "is_active": m.is_active,
                "last_validated": m.last_validated.isoformat() if m.last_validated else None,
            }
            for m in target.machines
        ],
    }


@router.post("/users/{user_id}/revoke")
async def revoke_user_licenses(
    user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all license keys for a user and deactivate machines."""
    _require_admin(user)

    import uuid as _uuid

    try:
        uid = _uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    result = await db.execute(select(User).where(User.id == uid))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Revoke all license keys
    key_result = await db.execute(select(LicenseKey).where(LicenseKey.user_id == uid))
    keys = key_result.scalars().all()
    for key in keys:
        key.revoked = True

    # Deactivate all machines
    for m in target.machines:
        m.is_active = False

    await db.flush()

    return {
        "ok": True,
        "revoked_keys": len(keys),
        "deactivated_machines": len(target.machines),
    }
