# PromptShield Licensing Server

Cloud API server that handles user authentication, license activation, subscription billing (Stripe), and Ed25519-signed offline license key generation.

## Architecture

```
Desktop App (Tauri/Rust)
  ├── Ed25519 public key (verifies license blobs offline)
  ├── Machine fingerprinting (SHA-256 of hardware IDs)
  └── License file (~/.local/share/promptshield/license.key)
          │
          │  HTTPS (activate / validate / login)
          ▼
Licensing Server (this code)
  ├── FastAPI + async SQLAlchemy (PostgreSQL)
  ├── Ed25519 private key (signs license blobs)
  ├── JWT authentication (access + refresh tokens)
  └── Stripe integration (checkout sessions, webhooks)
```

## Quick Start

```bash
# 1. Create PostgreSQL database
createdb promptshield_licensing

# 2. Install dependencies
cd src-licensing
pip install -e .

# 3. Generate Ed25519 keypair
python generate_keys.py
# → Copy the output into .env

# 4. Configure environment
cp .env.example .env
# → Edit .env with your values

# 5. Run migrations
alembic upgrade head

# 6. Start server
uvicorn main:app --host 0.0.0.0 --port 8443 --reload
```

## API Endpoints

### Auth (`/auth`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create a new user account |
| POST | `/auth/login` | Sign in, get access + refresh tokens |
| POST | `/auth/refresh` | Rotate refresh token |
| POST | `/auth/logout` | Revoke refresh token |
| GET | `/auth/me` | Get current user info |

### License (`/license`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/license/activate` | Activate on a machine, get signed blob |
| POST | `/license/validate` | Monthly heartbeat, refresh license blob |
| POST | `/license/offline-key` | Generate offline license key |
| GET | `/license/status` | Check subscription/license status |
| GET | `/license/machines` | List activated machines |
| DELETE | `/license/machines/{id}` | Deactivate a machine |

### Billing (`/billing`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/billing/checkout` | Create Stripe checkout session |
| POST | `/billing/webhook` | Stripe webhook handler |
| GET | `/billing/subscription` | Get current subscription |
| POST | `/billing/portal` | Get Stripe customer portal URL |

### Admin (`/admin`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/stats` | Licensing statistics |
| GET | `/admin/users` | List users (paginated) |
| GET | `/admin/users/{id}` | User detail |
| POST | `/admin/users/{id}/revoke` | Revoke all licenses |

## License Blob Format

```
base64(JSON_payload) . base64(Ed25519_signature)
```

Payload fields:
```json
{
  "email": "user@example.com",
  "plan": "pro",
  "seats": 5,
  "machine_id": "sha256_hex_of_hardware_ids",
  "issued": "2024-01-01T00:00:00Z",
  "expires": "2024-02-05T00:00:00Z",
  "v": 1
}
```

The desktop app ships with only the Ed25519 **public key** — it can verify but never forge a license.

## Security Notes

- Passwords hashed with bcrypt (via passlib)
- JWTs signed with HS256 (symmetric), short-lived (30 min)
- Refresh tokens stored as SHA-256 hashes in DB
- Ed25519 license blobs are cryptographically signed
- Machine fingerprinting uses CPU, BIOS, board, and disk serial numbers
- Stripe webhook signatures verified before processing
- Admin endpoints gated by email whitelist (`PS_ADMIN_EMAILS` env var)
