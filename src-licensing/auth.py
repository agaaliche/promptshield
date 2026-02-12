"""Firebase ID-token verification + FastAPI dependency for current user.

All password hashing and custom JWT logic has been removed — Firebase
handles identity. The licensing server only verifies the ID token that
the frontend obtains via the Firebase client SDK.
"""

from __future__ import annotations

import logging
import uuid

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials as firebase_creds
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import User

logger = logging.getLogger("licensing.auth")
_bearer = HTTPBearer()


# ── Firebase Admin SDK initialisation (once) ────────────────────

def _init_firebase() -> None:
    """Initialise the Firebase Admin SDK if not already done."""
    if firebase_admin._apps:
        return  # already initialised
    if settings.firebase_service_account_path:
        cred = firebase_creds.Certificate(settings.firebase_service_account_path)
    else:
        # Falls back to Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS)
        cred = firebase_creds.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})
    logger.info("Firebase Admin SDK initialised (project=%s)", settings.firebase_project_id)


_init_firebase()


# ── Verify Firebase ID token ───────────────────────────────────

def verify_firebase_token(id_token: str) -> dict:
    """Verify a Firebase ID token and return the decoded claims.

    Raises HTTPException(401) on invalid / expired tokens.
    """
    try:
        decoded = firebase_auth.verify_id_token(id_token, check_revoked=True)
        return decoded
    except firebase_auth.RevokedIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ID token")
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except Exception as exc:
        logger.warning("Firebase token verification failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token verification failed")


# ── FastAPI dependency — get current user from Firebase Bearer token ──

async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate Firebase ID token and return the local User ORM object.

    If the user row does not yet exist (first API call after Firebase
    sign-up), a stub row is created so downstream code always has a User.
    """
    decoded = verify_firebase_token(creds.credentials)
    firebase_uid: str = decoded["uid"]
    email: str = decoded.get("email", "")

    # Look up by firebase_uid first, fall back to email for migration
    result = await db.execute(
        select(User).where(User.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()

    if not user and email:
        # Check if a legacy user row exists with this email
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        user = result.scalar_one_or_none()
        if user:
            # Link existing user to Firebase
            user.firebase_uid = firebase_uid
            await db.flush()

    if not user:
        # Auto-create a new user row on first sign-in
        user = User(
            email=email.lower(),
            firebase_uid=firebase_uid,
            full_name=decoded.get("name"),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    return user
