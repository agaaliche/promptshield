"""promptShield Licensing Server — configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Database ──
    database_url: str = "postgresql+asyncpg://localhost:5432/promptshield"

    # ── JWT ──
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

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
    max_seats_per_subscription: int = 5
    max_machines_per_seat: int = 3
    trial_days: int = 14
    free_trial_allowed: bool = True

    # ── CORS ──
    allowed_origins: list[str] = ["https://promptshield.com", "http://localhost:3000"]

    model_config = {"env_prefix": "PS_", "env_file": ".env"}


settings = Settings()
