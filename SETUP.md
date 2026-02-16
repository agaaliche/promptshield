# Developer Setup Guide

Complete guide for setting up the PromptShield / Document Anonymizer project from scratch, including all secrets, tokens, and configuration values.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Initial Setup](#2-initial-setup)
3. [Python Backend Configuration](#3-python-backend-configuration)
4. [Firebase Setup](#4-firebase-setup)
5. [PostgreSQL Setup](#5-postgresql-setup)
6. [Licensing Server Configuration](#6-licensing-server-configuration)
7. [Stripe Setup](#7-stripe-setup)
8. [Frontend Configuration](#8-frontend-configuration)
9. [Tauri Desktop Build](#9-tauri-desktop-build)
10. [Website Configuration](#10-website-configuration)
11. [Running the Application](#11-running-the-application)
12. [Environment Variables Reference](#12-environment-variables-reference)

---

## 1. Prerequisites

### Required Software

| Software | Version | Purpose | Installation |
|----------|---------|---------|--------------|
| **Node.js** | ≥ 18 | Frontend, Website | [nodejs.org](https://nodejs.org) |
| **Python** | ≥ 3.11 | Backend, Licensing Server | [python.org](https://www.python.org/downloads/) |
| **Git** | Any | Version control | [git-scm.com](https://git-scm.com/downloads) |

### Optional Software

| Software | Version | Purpose | Installation |
|----------|---------|---------|--------------|
| **Rust** | ≥ 1.70 | Tauri desktop build | [rustup.rs](https://rustup.rs) |
| **MSVC Build Tools** | 2019+ | Windows: llama-cpp-python, Tauri | [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |
| **Tesseract OCR** | Any | OCR for scanned PDFs | [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) |
| **PostgreSQL** | ≥ 14 | Licensing Server database | [postgresql.org](https://www.postgresql.org/download/) |

### Verify Installation

```powershell
node --version    # Should be v18.x.x or higher
python --version  # Should be 3.11.x or higher
git --version     # Any version
rustc --version   # (Optional) 1.70.x or higher
```

---

## 2. Initial Setup

### Clone and Run Setup Script

```powershell
git clone <repository-url> doc-anonymizer
cd doc-anonymizer
.\setup.ps1
```

The setup script will:
- Check all prerequisites
- Create Python virtual environment (`src-python/.venv`)
- Install Python dependencies (FastAPI, spaCy, etc.)
- Download spaCy English model (`en_core_web_sm`)
- Install frontend npm dependencies
- Validate the installation

### Setup Script Options

```powershell
.\setup.ps1 -SpacyModel lg      # Use larger/more accurate spaCy model
.\setup.ps1 -SkipOptional       # Skip Tesseract and Rust checks
.\setup.ps1 -Force              # Recreate venv/node_modules from scratch
```

---

## 3. Python Backend Configuration

The Python backend requires **no mandatory environment variables** for basic operation. Configuration is managed via the Settings UI in the app.

### Optional Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DOC_ANON_LLM_API_KEY` | Bearer token for remote LLM API (OpenAI-compatible) | Empty (local GGUF model used) |

### LLM Setup (Optional)

For local LLM detection, download a GGUF model and configure via the app's Settings UI:

1. Download a model (e.g., `mistral-7b-instruct-v0.3.Q4_K_M.gguf`)
2. In the app: Settings → LLM → Select GGUF file path
3. Adjust context size and GPU layers as needed

---

## 4. Firebase Setup

Firebase is used for user authentication across the desktop app, website, and licensing server.

### Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click **Add project** → Name it (e.g., `promptshield`)
3. Disable Google Analytics (optional)
4. Click **Create project**

### Enable Authentication

1. In Firebase Console → **Build** → **Authentication**
2. Click **Get started**
3. Enable sign-in providers:
   - **Email/Password**: Enable both email and passwordless
   - **Google**: Enable and configure OAuth consent screen

### Get Web Config (Frontend)

1. **Project Settings** (gear icon) → **General**
2. Scroll to **Your apps** → Click web icon (`</>`)
3. Register app (e.g., `promptshield-web`)
4. Copy the config values:

```javascript
// These are PUBLIC and safe to commit (used in frontend)
const firebaseConfig = {
  apiKey: "AIza...",           // NEXT_PUBLIC_FIREBASE_API_KEY
  authDomain: "xyz.firebaseapp.com",  // NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
  projectId: "xyz",            // NEXT_PUBLIC_FIREBASE_PROJECT_ID
};
```

### Get Service Account (Server)

1. **Project Settings** → **Service accounts**
2. Click **Generate new private key**
3. Save as `src-licensing/firebase-sa-key.json`

> ⚠️ **NEVER commit the service account JSON file.** It's already in `.gitignore`.

---

## 5. PostgreSQL Setup

The licensing server requires a PostgreSQL database.

### Local Development

```powershell
# Windows (after installing PostgreSQL)
createdb promptshield_licensing

# Or using psql
psql -U postgres
CREATE DATABASE promptshield_licensing;
\q
```

### Connection String Format

```
postgresql+asyncpg://username:password@host:port/database
```

**Examples:**
```bash
# Local (default user, no password)
PS_DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/promptshield_licensing

# Local with password
PS_DATABASE_URL=postgresql+asyncpg://postgres:mypassword@localhost:5432/promptshield_licensing

# Cloud SQL (via proxy)
PS_DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/promptshield
```

### Run Migrations

```powershell
cd src-licensing
..\.venv\Scripts\Activate.ps1  # Or create a venv for src-licensing
alembic upgrade head
```

---

## 6. Licensing Server Configuration

### Create Environment File

```powershell
cd src-licensing
# Create .env from scratch (no .env.example exists)
```

Create `src-licensing/.env` with the following content:

```bash
# ══════════════════════════════════════════════════════════════════════════════
# PromptShield Licensing Server — Environment Configuration
# ══════════════════════════════════════════════════════════════════════════════

# ─── Database ─────────────────────────────────────────────────────────────────
PS_DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/promptshield_licensing

# ─── JWT (still validated even though Firebase is primary auth) ───────────────
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
PS_JWT_SECRET=CHANGE-ME-GENERATE-A-RANDOM-64-CHAR-STRING

# ─── Firebase ─────────────────────────────────────────────────────────────────
PS_FIREBASE_PROJECT_ID=promptshield-6d5cd
PS_FIREBASE_SERVICE_ACCOUNT_PATH=firebase-sa-key.json

# ─── Ed25519 License Signing Keys ─────────────────────────────────────────────
# Generate both with: python generate_keys.py
PS_ED25519_PRIVATE_KEY_B64=
PS_ED25519_PUBLIC_KEY_B64=

# ─── Stripe Billing (leave empty to disable billing features) ─────────────────
PS_STRIPE_SECRET_KEY=
PS_STRIPE_WEBHOOK_SECRET=
PS_STRIPE_PRICE_ID_MONTHLY=

# ─── Admin Access ─────────────────────────────────────────────────────────────
# Comma-separated list of emails that can access /admin endpoints
PS_ADMIN_EMAILS=admin@example.com

# ─── Development Only (NEVER set these in production) ─────────────────────────
PS_ALLOW_DEFAULT_SECRET=1
PS_DEV_MODE=1
```

### Generate Ed25519 Keys

```powershell
cd src-licensing
python generate_keys.py
```

**Output example:**
```
Generated Ed25519 keypair:
PS_ED25519_PRIVATE_KEY_B64=<base64-encoded-private-key>
PS_ED25519_PUBLIC_KEY_B64=<base64-encoded-public-key>
```

Copy both values into `.env`. The **public key** must also be updated in the Tauri source code (see [Section 9](#9-tauri-desktop-build)).

### Generate JWT Secret

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the output to `PS_JWT_SECRET` in `.env`.

---

## 7. Stripe Setup

Stripe is required for subscription billing. Skip this section for local development without billing.

### Get API Keys

1. Go to [Stripe Dashboard](https://dashboard.stripe.com/)
2. Create an account or log in
3. Toggle **Test mode** (top-right) for development
4. **Developers** → **API keys**:
   - **Publishable key**: `pk_test_...` (for frontend)
   - **Secret key**: `sk_test_...` (for backend)

### Create Product & Price

1. **Products** → **Add product**
2. Name: "PromptShield Pro" (or similar)
3. Add a price: $14/month recurring
4. Copy the **Price ID**: `price_...`

### Set Up Webhook

1. **Developers** → **Webhooks** → **Add endpoint**
2. URL: `https://your-licensing-server.com/billing/webhook`
3. Events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
4. Copy the **Signing secret**: `whsec_...`

### Add to Licensing Server `.env`

```bash
PS_STRIPE_SECRET_KEY=sk_test_...
PS_STRIPE_WEBHOOK_SECRET=whsec_...
PS_STRIPE_PRICE_ID_MONTHLY=price_...
```

---

## 8. Frontend Configuration

The frontend has minimal configuration. Most values are hardcoded or have sensible defaults.

### Environment Variables (Optional)

Create `frontend/.env` if you need to override defaults:

```bash
# Override backend API port (default: 8910)
VITE_API_PORT=8910

# Override licensing server URL (default: production)
VITE_LICENSING_URL=http://localhost:8443
```

### Firebase Config

The Firebase web config is hardcoded in `frontend/src/firebaseConfig.ts`. For a different Firebase project, update the values:

```typescript
const firebaseConfig = {
  apiKey: "your-api-key",
  authDomain: "your-project.firebaseapp.com",
  projectId: "your-project-id",
};
```

These are **public** values (safe to commit) — they only allow client-side auth with Firebase.

---

## 9. Tauri Desktop Build

For building the Tauri desktop application, you need Rust installed and must update the Ed25519 public key.

### Install Rust

```powershell
# Install rustup (Rust toolchain manager)
winget install Rustlang.Rustup
# Or download from https://rustup.rs

# Verify installation
rustc --version
cargo --version
```

### Update Public Key for License Verification

Edit `frontend/src-tauri/src/license.rs`:

```rust
// Line ~18 — Replace with your generated public key
const ED25519_PUBLIC_KEY_B64: &str = "YOUR_PUBLIC_KEY_FROM_generate_keys.py";
```

> ⚠️ **CRITICAL**: If you don't update this, license verification will fail in production builds.

### Update Licensing Server URL

The URL is hardcoded for release builds. Edit `frontend/src-tauri/src/license.rs`:

```rust
// Line ~22
pub const LICENSING_SERVER_URL: &str = "https://your-licensing-server.com";
```

### Build Desktop App

```powershell
cd frontend
npm run tauri build
```

The installer will be in `frontend/src-tauri/target/release/bundle/`.

---

## 10. Website Configuration

The marketing/billing website (`website/`) needs both build-time and runtime environment variables.

### Build-Time Variables

Create `website/.env.local`:

```bash
# Firebase (public)
NEXT_PUBLIC_FIREBASE_API_KEY=AIza...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id

# URLs
NEXT_PUBLIC_LICENSING_URL=https://your-licensing-server.com
NEXT_PUBLIC_APP_URL=https://your-website.com

# Stripe (public)
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

### Runtime Variables (Server-Side)

For API routes, set these in your hosting environment (Vercel, Cloud Run, etc.):

```bash
# Stripe (secret)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=price_...

# Licensing server communication
LICENSING_SERVER_URL=https://your-licensing-server.com
LICENSING_INTERNAL_KEY=your-internal-api-key

# Firebase Admin (choose one):
# Option A: JSON string
FIREBASE_SERVICE_ACCOUNT_KEY={"type":"service_account",...}
# Option B: File path
GOOGLE_APPLICATION_CREDENTIALS=/path/to/firebase-sa-key.json
```

### Run Website Locally

```powershell
cd website
npm install
npm run dev
# Opens at http://localhost:3000
```

---

## 11. Running the Application

### Development Mode (Recommended)

```powershell
# From project root — starts backend + frontend
.\dev.ps1
```

This runs:
- Python backend on `http://localhost:8910`
- Frontend dev server on `http://localhost:5173`

### Individual Components

```powershell
# Backend only
cd src-python
..\.venv\Scripts\Activate.ps1
python -m uvicorn api.server:app --host 127.0.0.1 --port 8910 --reload

# Frontend only
cd frontend
npm run dev

# Licensing server
.\dev-licensing.ps1

# Tauri desktop app (with backend)
.\dev-tauri.ps1
```

### Production Build

```powershell
# Backend (Nuitka standalone)
.\build-nuitka.ps1

# Frontend + Tauri
cd frontend
npm run tauri build
```

---

## 12. Environment Variables Reference

### Python Backend (`src-python/`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DOC_ANON_LLM_API_KEY` | No | Empty | Bearer token for remote LLM API |

### Licensing Server (`src-licensing/`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PS_DATABASE_URL` | **Yes** | `postgresql+asyncpg://localhost:5432/promptshield` | PostgreSQL connection string |
| `PS_JWT_SECRET` | **Yes** | `CHANGE-ME-IN-PRODUCTION` | JWT signing secret (64+ chars) |
| `PS_FIREBASE_PROJECT_ID` | **Yes** | `promptshield-6d5cd` | Firebase project ID |
| `PS_FIREBASE_SERVICE_ACCOUNT_PATH` | **Yes** | Empty | Path to service account JSON |
| `PS_ED25519_PRIVATE_KEY_B64` | **Yes** | Empty | License signing private key |
| `PS_ED25519_PUBLIC_KEY_B64` | **Yes** | Empty | License signing public key |
| `PS_STRIPE_SECRET_KEY` | No | Empty | Stripe API secret key |
| `PS_STRIPE_WEBHOOK_SECRET` | No | Empty | Stripe webhook signing secret |
| `PS_STRIPE_PRICE_ID_MONTHLY` | No | Empty | Stripe price ID for Pro plan |
| `PS_ADMIN_EMAILS` | No | Empty | Comma-separated admin emails |
| `PS_ALLOW_DEFAULT_SECRET` | No | `false` | Skip secret validation (dev only) |
| `PS_DEV_MODE` | No | `false` | Enable dev mode |
| `PS_LICENSE_VALIDITY_DAYS` | No | `35` | Offline license validity |
| `PS_TRIAL_DAYS` | No | `14` | Free trial duration |
| `PS_FRONTEND_URL` | No | `https://app.promptshield.com` | App URL for redirects |

### Frontend (`frontend/`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_PORT` | No | `8910` | Backend API port |
| `VITE_LICENSING_URL` | No | Production URL | Licensing server URL |

### Website (`website/`)

**Build-time:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Recommended | Hardcoded | Firebase API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Recommended | Hardcoded | Firebase auth domain |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Recommended | Hardcoded | Firebase project ID |
| `NEXT_PUBLIC_LICENSING_URL` | **Yes** | `https://api.promptshield.ca` | Licensing API URL |
| `NEXT_PUBLIC_APP_URL` | **Yes** | `http://localhost:3000` | Website URL |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | **Yes** | Empty | Stripe publishable key |

**Runtime:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STRIPE_SECRET_KEY` | **Yes** | — | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | **Yes** | — | Stripe webhook secret |
| `STRIPE_PRO_PRICE_ID` | **Yes** | — | Stripe price ID |
| `LICENSING_SERVER_URL` | **Yes** | — | Licensing API URL |
| `LICENSING_INTERNAL_KEY` | **Yes** | — | Server-to-server API key |
| `FIREBASE_SERVICE_ACCOUNT_KEY` | **Yes** | — | Firebase service account JSON string |

---

## Quick Reference: Key Generation

```powershell
# Ed25519 keypair (run from src-licensing/)
python generate_keys.py

# Random JWT secret
python -c "import secrets; print(secrets.token_urlsafe(48))"

# Verify Firebase setup
python -c "import firebase_admin; firebase_admin.initialize_app(); print('OK')"
```

---

## Troubleshooting

### "Port 8910 already in use"
```powershell
Get-Process -Name python* | Stop-Process -Force
```

### "spaCy model not found"
```powershell
cd src-python
.venv\Scripts\python.exe -m spacy download en_core_web_sm
```

### "Rust not found" (Tauri build)
```powershell
winget install Rustlang.Rustup
# Restart terminal, then verify:
rustc --version
```

### "Firebase credentials not found"
Ensure `firebase-sa-key.json` exists in `src-licensing/` and `PS_FIREBASE_SERVICE_ACCOUNT_PATH` points to it.

### License verification fails
1. Ensure `PS_ED25519_PUBLIC_KEY_B64` in `.env` matches `ED25519_PUBLIC_KEY_B64` in `license.rs`
2. Rebuild Tauri app after changing the key

---

## Security Checklist

Before deploying to production:

- [ ] Generate unique `PS_JWT_SECRET` (64+ chars)
- [ ] Generate Ed25519 keypair and update both `.env` and `license.rs`
- [ ] Remove `PS_ALLOW_DEFAULT_SECRET` and `PS_DEV_MODE`
- [ ] Set up Stripe with live keys (not test keys)
- [ ] Ensure `firebase-sa-key.json` is NOT committed to git
- [ ] Update `LICENSING_SERVER_URL` in `license.rs` to production URL
- [ ] Run `npm run tauri build` (not dev mode) for release

---

*Last updated: February 2025*
