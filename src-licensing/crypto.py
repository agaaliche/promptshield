"""Ed25519 signing & license blob creation/verification.

License blob format:
    base64(payload_json) + "." + base64(Ed25519_signature)

The server holds the PRIVATE key (signs).
The desktop app ships with the PUBLIC key only (verifies).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from nacl.encoding import RawEncoder
from nacl.signing import SigningKey, VerifyKey

from config import settings


def _get_signing_key() -> SigningKey:
    """Load Ed25519 private key from config (base64)."""
    raw = base64.b64decode(settings.ed25519_private_key_b64)
    return SigningKey(raw, encoder=RawEncoder)


def _get_verify_key() -> VerifyKey:
    """Load Ed25519 public key from config (base64)."""
    raw = base64.b64decode(settings.ed25519_public_key_b64)
    return VerifyKey(raw, encoder=RawEncoder)


def create_license_blob(
    *,
    email: str,
    plan: str,
    seats: int,
    machine_fingerprint: str,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    """Create a signed license blob.

    Returns:
        ``base64(payload_json).base64(signature)``
    """
    payload = {
        "email": email,
        "plan": plan,
        "seats": seats,
        "machine_id": machine_fingerprint,
        "issued": issued_at.isoformat(),
        "expires": expires_at.isoformat(),
        "v": 1,  # schema version
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode()

    sk = _get_signing_key()
    sig = sk.sign(payload_bytes, encoder=RawEncoder).signature
    sig_b64 = base64.urlsafe_b64encode(sig).decode()

    return f"{payload_b64}.{sig_b64}"


def verify_license_blob(blob: str) -> dict | None:
    """Verify a license blob signature and return the payload dict.

    Returns None if the signature is invalid.
    """
    try:
        parts = blob.split(".", 1)
        if len(parts) != 2:
            return None

        payload_b64, sig_b64 = parts
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        sig_bytes = base64.urlsafe_b64decode(sig_b64)

        vk = _get_verify_key()
        vk.verify(payload_bytes, sig_bytes, encoder=RawEncoder)

        return json.loads(payload_bytes)
    except Exception:
        return None


# ── Key generation utility (run once during initial setup) ─────

def generate_keypair() -> tuple[str, str]:
    """Generate a fresh Ed25519 keypair.

    Returns:
        (private_key_b64, public_key_b64)
    """
    sk = SigningKey.generate()
    vk = sk.verify_key
    priv_b64 = base64.b64encode(bytes(sk)).decode()
    pub_b64 = base64.b64encode(bytes(vk)).decode()
    return priv_b64, pub_b64
