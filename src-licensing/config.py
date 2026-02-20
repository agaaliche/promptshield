"""promptShield Licensing Server — configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    # ── Database ──
    database_url: str = "postgresql+asyncpg://localhost:5432/promptshield"

    # ── JWT (kept for backward compat but no longer used for auth) ──
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # ── Firebase ──
    firebase_project_id: str = "promptshield-6d5cd"
    firebase_service_account_path: str = ""  # path to service-account JSON; empty = use ADC

    # ── Ed25519 keys (base64-encoded) ──
    ed25519_private_key_b64: str = ""
    ed25519_public_key_b64: str = ""

    # ── Stripe ──
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_monthly: str = ""  # $14/mo price object

    # ── App config ──
    frontend_url: str = "https://app.promptshield.com"
    license_validity_days: int = 35  # offline keys valid for 35 days
    trial_license_validity_days: int = 15  # trial blobs valid only 1 day past trial end
    max_seats_per_subscription: int = 5
    max_machines_per_seat: int = 3
    trial_days: int = 14
    free_trial_allowed: bool = True

    # ── CORS ──
    allowed_origins: list[str] = ["https://promptshield.com", "http://localhost:3000"]

    # Admin
    admin_emails: str = ""  # comma-separated list of admin emails

    # Logging
    log_format: str = "text"  # "json" for structured Cloud Run / GCP logs
    log_level: str = "INFO"   # DEBUG, INFO, WARNING, ERROR

    # Dev mode
    dev_mode: bool = False
    allow_default_secret: bool = False

    model_config = {"env_prefix": "PS_", "env_file": str(_ENV_FILE)}


settings = Settings()

# ── Startup validation ─────────────────────────────────────────

def validate_settings() -> None:
    """Raise on dangerous default values."""
    if settings.jwt_secret in ("CHANGE-ME-IN-PRODUCTION", ""):
        if not settings.allow_default_secret:
            raise RuntimeError(
                "CRITICAL: PS_JWT_SECRET is not configured. "
                "Set the PS_JWT_SECRET environment variable before starting the server. "
                "Set PS_ALLOW_DEFAULT_SECRET=1 only for local development."
            )
    if not settings.ed25519_private_key_b64:
        if not settings.allow_default_secret:
            raise RuntimeError(
                "CRITICAL: PS_ED25519_PRIVATE_KEY_B64 is not set. "
                "Run 'python generate_keys.py' to generate a keypair."
            )
