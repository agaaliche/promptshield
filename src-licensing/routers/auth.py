"""Auth router — register, login, refresh, me."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from database import get_db
from models import RefreshToken, User
from schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# H7: Simple in-memory rate limiter for auth endpoints
_AUTH_RATE: dict[str, list[float]] = {}  # ip/email -> list of timestamps
_AUTH_MAX_ATTEMPTS = 10
_AUTH_WINDOW_SECONDS = 60


def _check_auth_rate_limit(key: str) -> None:
    """Raise 429 if too many auth attempts from this key."""
    now = time.monotonic()
    attempts = _AUTH_RATE.setdefault(key, [])
    # Prune old entries
    while attempts and now - attempts[0] > _AUTH_WINDOW_SECONDS:
        attempts.pop(0)
    if len(attempts) >= _AUTH_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Please wait {_AUTH_WINDOW_SECONDS}s.",
        )
    attempts.append(now)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user account."""
    _check_auth_rate_limit(f"register:{body.email.lower()}")

    # Check for existing email
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
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


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password, return JWT tokens."""
    _check_auth_rate_limit(f"login:{body.email.lower()}")

    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    # H8: Always run verify_password to prevent timing side-channel
    # If user is None, verify against a dummy hash (constant-time rejection)
    _DUMMY_HASH = "$2b$12$LJ3m4ys3Lz0EN8hPEc7ZKOP/R8GSAmGNp0xOAcJqQzFh7L.0A0ANC"  # noqa: S105
    stored_hash = user.hashed_password if user else _DUMMY_HASH
    password_ok = verify_password(body.password, stored_hash)

    if not user or not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    access, expires_in = create_access_token(str(user.id), user.email)
    raw_refresh, refresh_hash, refresh_exp = create_refresh_token(str(user.id))

    # Store hashed refresh token
    db.add(RefreshToken(user_id=user.id, token_hash=refresh_hash, expires_at=refresh_exp))
    await db.flush()

    return TokenResponse(
        access_token=access,
        refresh_token=raw_refresh,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new access + refresh pair."""
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()

    if not rt or rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    # M15: Detect refresh token reuse — if already revoked, revoke ALL tokens
    # for this user (token family compromise)
    if rt.revoked:
        await db.execute(
            select(RefreshToken)
            .where(RefreshToken.user_id == rt.user_id)
        )
        all_tokens = (await db.execute(
            select(RefreshToken).where(RefreshToken.user_id == rt.user_id, RefreshToken.revoked == False)
        )).scalars().all()
        for t in all_tokens:
            t.revoked = True
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions revoked for security.",
        )

    # Rotate refresh token (revoke old, issue new)
    rt.revoked = True
    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one()

    access, expires_in = create_access_token(str(user.id), user.email)
    raw_refresh, new_hash, new_exp = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, token_hash=new_hash, expires_at=new_exp))
    await db.flush()

    return TokenResponse(
        access_token=access,
        refresh_token=raw_refresh,
        expires_in=expires_in,
    )


@router.post("/logout")
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Revoke a refresh token (logout)."""
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked = True
        await db.flush()
    return {"ok": True}


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
