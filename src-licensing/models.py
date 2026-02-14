"""SQLAlchemy ORM models for the licensing database."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Users ──────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False, index=True)
    firebase_uid = Column(String(128), unique=True, nullable=True, index=True)
    hashed_password = Column(String(128), nullable=True)  # nullable — Firebase users don't have local passwords
    full_name = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    trial_used = Column(Boolean, default=False)  # track if free trial was consumed

    # Stripe
    stripe_customer_id = Column(String(64), nullable=True, unique=True)

    # Relations
    subscriptions = relationship("Subscription", back_populates="user", lazy="selectin")
    machines = relationship("Machine", back_populates="user", lazy="selectin")
    refresh_tokens = relationship("RefreshToken", back_populates="user", lazy="selectin")


# ── Subscriptions ──────────────────────────────────────────────


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    stripe_subscription_id = Column(String(64), unique=True, nullable=True)
    plan = Column(SAEnum("free_trial", "pro", name="plan_type"), nullable=False)
    status = Column(
        SAEnum("active", "trialing", "past_due", "canceled", "expired", name="sub_status"),
        nullable=False,
        default="active",
    )
    seats = Column(Integer, default=1)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="subscriptions")


# ── Machines (hardware-bound activations) ──────────────────────


class Machine(Base):
    __tablename__ = "machines"
    __table_args__ = (UniqueConstraint("user_id", "machine_fingerprint", name="uq_user_machine"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    machine_fingerprint = Column(String(128), nullable=False, index=True)
    machine_name = Column(String(200), nullable=True)
    activated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_validated = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="machines")


# ── License Keys (offline activation) ──────────────────────────


class LicenseKey(Base):
    __tablename__ = "license_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    machine_fingerprint = Column(String(128), nullable=False)
    key_blob = Column(Text, nullable=False)
    issued_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)


# ── Refresh Tokens ─────────────────────────────────────────────


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(128), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)

    user = relationship("User", back_populates="refresh_tokens")


# ── Trial Machine Lockout (S3) ─────────────────────────────────
# Track which machines have already consumed a trial, preventing
# trial abuse via multiple Firebase accounts on the same hardware.


class TrialMachine(Base):
    __tablename__ = "trial_machines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_fingerprint = Column(String(128), nullable=False, unique=True, index=True)
    first_trial_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    user_email = Column(String(320), nullable=True)  # informational only
