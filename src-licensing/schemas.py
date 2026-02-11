"""Pydantic schemas for request/response validation."""

from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# ── Auth ───────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    trial_used: bool
    created_at: datetime


# ── License ────────────────────────────────────────────────────

class ActivateRequest(BaseModel):
    machine_fingerprint: str = Field(min_length=16, max_length=128)
    machine_name: str | None = None


class ValidateRequest(BaseModel):
    machine_fingerprint: str = Field(min_length=16, max_length=128)


class OfflineKeyRequest(BaseModel):
    machine_fingerprint: str = Field(min_length=16, max_length=128)


class LicenseResponse(BaseModel):
    license_blob: str
    expires_at: datetime
    plan: str
    seats: int
    machine_fingerprint: str


class LicenseStatusResponse(BaseModel):
    valid: bool
    plan: str | None = None
    expires_at: datetime | None = None
    seats: int | None = None
    days_remaining: int | None = None
    message: str = ""


# ── Machines ───────────────────────────────────────────────────

class MachineResponse(BaseModel):
    id: uuid.UUID
    machine_fingerprint: str
    machine_name: str | None
    activated_at: datetime
    last_validated: datetime | None
    is_active: bool


# ── Billing ────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str = "pro"  # "pro" or "free_trial"
    success_url: str = "https://promptshield.com/billing/success"
    cancel_url: str = "https://promptshield.com/billing/cancel"


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class SubscriptionResponse(BaseModel):
    id: str
    plan: str
    status: str
    seats: int
    current_period_start: datetime | None
    current_period_end: datetime | None
    trial_end: datetime | None
    created_at: datetime | None = None


class BillingPortalResponse(BaseModel):
    portal_url: str
