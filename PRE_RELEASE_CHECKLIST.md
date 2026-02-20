# Pre-Release Checklist

## Certificates & Signing (DO BEFORE RELEASE)

### Windows EV Code-Signing Certificate
- [ ] Purchase EV code-signing cert (recommended: **SSL.com** ~$240/yr)
- [ ] Complete identity verification (5–10 business days)
- [ ] Configure GitHub Actions secrets:
  - `WINDOWS_CERTIFICATE` — Base64-encoded `.pfx`
  - `WINDOWS_CERTIFICATE_PWD` — PFX password
- [ ] Verify `certificateThumbprint` in `frontend/src-tauri/tauri.conf.json`

### Apple Developer ID Certificate
- [ ] Enroll in Apple Developer Program ($99/yr) — https://developer.apple.com/programs/
- [ ] Create "Developer ID Application" certificate in Xcode/portal
- [ ] Configure GitHub Actions secrets:
  - `APPLE_CERTIFICATE` — Base64-encoded `.p12`
  - `APPLE_CERTIFICATE_PWD` — .p12 password
  - `APPLE_ID` — Apple ID email
  - `APPLE_ID_PASSWORD` — App-specific password (not account password)
  - `APPLE_TEAM_ID` — 10-character Team ID
- [ ] Update `signingIdentity` in `frontend/src-tauri/tauri.conf.json` (replace `"-"`)

---

## Sentry Crash Reporting

### Setup (already integrated in code)
- [ ] Create Sentry project at https://sentry.io (see instructions below)
- [ ] Set `VITE_SENTRY_DSN` in `frontend/.env.production`
- [ ] Set `SENTRY_DSN` in Python backend environment (Tauri sidecar env or system env)
- [ ] Test error reporting in staging before release

### Sentry DSN Configuration
- Frontend reads: `VITE_SENTRY_DSN` (via Vite's `import.meta.env`)
- Backend reads: `SENTRY_DSN` (via `os.environ`)
- Both are safe to leave empty — Sentry is disabled when DSN is blank

---

## Remaining Production Items
- [ ] New app icons
- [ ] i18n for 7 languages
- [ ] Night mode / light theme
- [ ] Knowledgebase / help system
- [ ] Desktop app bundling with lazy-loading models
- [ ] Onboarding / first-run experience
- [ ] Settings persistence (detection settings lost on refresh)
- [ ] Structured logging
- [ ] Frontend test coverage expansion
- [ ] Accessibility improvements
