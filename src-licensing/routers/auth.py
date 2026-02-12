"""Auth router — Firebase token sync + user info.

Identity is managed entirely by Firebase. This router provides:

  POST /auth/sync — Sync the Firebase user with the local database
                     (creates user + trial subscription on first call).
  GET  /auth/me   — Return the current authenticated user profile.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import Subscription, User
from config import settings
from schemas import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sync", response_model=UserResponse)
async def sync(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync the Firebase user with the local database.

    Called by the frontend after a successful Firebase sign-in / sign-up.
    If this is the first time we see this user, ``get_current_user``
    will have already created the User row. Here we only need to
    provision the free-trial subscription when appropriate.
    """
    # Auto-create free trial subscription for new users
    if settings.free_trial_allowed and not user.trial_used:
        now = datetime.now(timezone.utc)
        trial_sub = Subscription(
            user_id=user.id,
            plan="free_trial",
            status="trialing",
            seats=1,
            trial_end=now + timedelta(days=settings.trial_days),
            current_period_start=now,
            current_period_end=now + timedelta(days=settings.trial_days),
        )
        db.add(trial_sub)
        user.trial_used = True
        await db.flush()
        await db.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        trial_used=user.trial_used,
        created_at=user.created_at,
    )


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    """Return the current authenticated user."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        trial_used=user.trial_used,
        created_at=user.created_at,
    )
