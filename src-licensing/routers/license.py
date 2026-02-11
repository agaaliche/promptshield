"""License router — activate, validate, offline key, machines."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from config import settings
from crypto import create_license_blob
from database import get_db
from models import LicenseKey, Machine, Subscription, User
from schemas import (
    ActivateRequest,
    LicenseResponse,
    LicenseStatusResponse,
    MachineResponse,
    OfflineKeyRequest,
    ValidateRequest,
)

router = APIRouter(prefix="/license", tags=["license"])


def _get_active_subscription(user: User) -> Subscription | None:
    """Return the most recent active/trialing subscription."""
    for sub in sorted(user.subscriptions, key=lambda s: s.created_at, reverse=True):
        if sub.status in ("active", "trialing"):
            return sub
    return None


def _check_subscription(user: User) -> Subscription:
    """Raise 403 if user has no active subscription."""
    sub = _get_active_subscription(user)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active subscription. Please subscribe at https://promptshield.com",
        )
    # Check expiry for trials
    if sub.status == "trialing" and sub.trial_end and sub.trial_end < datetime.now(timezone.utc):
        sub.status = "expired"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trial has expired")
    return sub


@router.post("/activate", response_model=LicenseResponse)
async def activate(
    body: ActivateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Activate a license on a new machine.

    Binds the subscription to a hardware fingerprint. Returns a signed
    license blob for offline use.
    """
    sub = _check_subscription(user)

    # Count existing active machines
    active_machines = [m for m in user.machines if m.is_active]
    max_machines = sub.seats * settings.max_machines_per_seat

    # Check if already activated on this machine
    existing = next(
        (m for m in active_machines if m.machine_fingerprint == body.machine_fingerprint),
        None,
    )

    if existing:
        # Re-activation on same machine — just refresh the license
        existing.last_validated = datetime.now(timezone.utc)
    else:
        # New machine
        if len(active_machines) >= max_machines:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Machine limit reached ({max_machines}). Deactivate a machine first.",
            )
        machine = Machine(
            user_id=user.id,
            machine_fingerprint=body.machine_fingerprint,
            machine_name=body.machine_name,
            last_validated=datetime.now(timezone.utc),
        )
        db.add(machine)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.license_validity_days)

    blob = create_license_blob(
        email=user.email,
        plan=sub.plan,
        seats=sub.seats,
        machine_fingerprint=body.machine_fingerprint,
        issued_at=now,
        expires_at=expires,
    )

    # Store the key
    db.add(LicenseKey(
        user_id=user.id,
        machine_fingerprint=body.machine_fingerprint,
        key_blob=blob,
        expires_at=expires,
    ))
    await db.flush()

    return LicenseResponse(
        license_blob=blob,
        expires_at=expires,
        plan=sub.plan,
        seats=sub.seats,
        machine_fingerprint=body.machine_fingerprint,
    )


@router.post("/validate", response_model=LicenseResponse)
async def validate(
    body: ValidateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Monthly heartbeat — validate subscription is still active and refresh license.

    Called by the desktop app every 30 days.
    """
    sub = _check_subscription(user)

    # Verify machine is activated
    machine = next(
        (m for m in user.machines if m.machine_fingerprint == body.machine_fingerprint and m.is_active),
        None,
    )
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Machine not activated. Please activate first.",
        )

    machine.last_validated = datetime.now(timezone.utc)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.license_validity_days)

    blob = create_license_blob(
        email=user.email,
        plan=sub.plan,
        seats=sub.seats,
        machine_fingerprint=body.machine_fingerprint,
        issued_at=now,
        expires_at=expires,
    )

    db.add(LicenseKey(
        user_id=user.id,
        machine_fingerprint=body.machine_fingerprint,
        key_blob=blob,
        expires_at=expires,
    ))
    await db.flush()

    return LicenseResponse(
        license_blob=blob,
        expires_at=expires,
        plan=sub.plan,
        seats=sub.seats,
        machine_fingerprint=body.machine_fingerprint,
    )


@router.post("/offline-key", response_model=LicenseResponse)
async def generate_offline_key(
    body: OfflineKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an offline license key for manual entry in the desktop app.

    User copies this from the web dashboard when they can't connect online.
    """
    sub = _check_subscription(user)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.license_validity_days)

    blob = create_license_blob(
        email=user.email,
        plan=sub.plan,
        seats=sub.seats,
        machine_fingerprint=body.machine_fingerprint,
        issued_at=now,
        expires_at=expires,
    )

    db.add(LicenseKey(
        user_id=user.id,
        machine_fingerprint=body.machine_fingerprint,
        key_blob=blob,
        expires_at=expires,
    ))
    await db.flush()

    return LicenseResponse(
        license_blob=blob,
        expires_at=expires,
        plan=sub.plan,
        seats=sub.seats,
        machine_fingerprint=body.machine_fingerprint,
    )


@router.get("/status", response_model=LicenseStatusResponse)
async def license_status(user: User = Depends(get_current_user)):
    """Check current license/subscription status."""
    sub = _get_active_subscription(user)
    if not sub:
        return LicenseStatusResponse(valid=False, message="No active subscription")

    # Determine days remaining
    if sub.current_period_end:
        days = (sub.current_period_end - datetime.now(timezone.utc)).days
    elif sub.trial_end:
        days = (sub.trial_end - datetime.now(timezone.utc)).days
    else:
        days = None

    return LicenseStatusResponse(
        valid=sub.status in ("active", "trialing"),
        plan=sub.plan,
        expires_at=sub.current_period_end or sub.trial_end,
        seats=sub.seats,
        days_remaining=days,
        message="Active" if sub.status in ("active", "trialing") else sub.status,
    )


@router.get("/machines", response_model=list[MachineResponse])
async def list_machines(user: User = Depends(get_current_user)):
    """List all activated machines for the current user."""
    return [
        MachineResponse(
            id=m.id,
            machine_fingerprint=m.machine_fingerprint,
            machine_name=m.machine_name,
            activated_at=m.activated_at,
            last_validated=m.last_validated,
            is_active=m.is_active,
        )
        for m in user.machines
    ]


@router.delete("/machines/{machine_id}")
async def deactivate_machine(
    machine_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a machine to free up a seat."""
    import uuid as _uuid
    machine = next(
        (m for m in user.machines if str(m.id) == machine_id),
        None,
    )
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    machine.is_active = False
    await db.flush()
    return {"ok": True, "message": "Machine deactivated"}
