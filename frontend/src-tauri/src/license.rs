/// License validation module.
///
/// Verifies Ed25519-signed license blobs produced by the licensing server.
/// The desktop app ships with only the **public** key — it can verify but
/// never forge a license. Blobs are stored as a file in the user's data
/// directory and checked on every app launch.

use base64::engine::general_purpose::STANDARD as B64;
use base64::Engine;
use chrono::{DateTime, Utc};
use ed25519_dalek::{Signature, VerifyingKey, Verifier};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

// ── Ed25519 public key (set during build / release) ────────────────────
// Generated 2026-02-11 via src-licensing/generate_keys.py.
// Must match the private key in the licensing server's .env.
const ED25519_PUBLIC_KEY_B64: &str = "B4EIWiBILG2lIl4tq4KeQsm/Vh2Z3q5YUpsl2yxH1q4=";

// C3: Compile-time check — fail release builds if the placeholder key is still present
#[cfg(not(debug_assertions))]
const _: () = {
    const KEY: &[u8] = ED25519_PUBLIC_KEY_B64.as_bytes();
    // Check if it's the all-A placeholder (base64 of all zeros)
    // All-A pattern: 43 'A' chars + '='
    const fn is_all_a(key: &[u8]) -> bool {
        let mut i = 0;
        while i < key.len() - 1 {
            if key[i] != b'A' {
                return false;
            }
            i += 1;
        }
        true
    }
    assert!(
        !is_all_a(KEY),
        "CRITICAL: ED25519_PUBLIC_KEY_B64 is still the placeholder. Set the real public key before building a release."
    );
};

/// Parsed license payload — matches the JSON the server signs.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LicensePayload {
    pub email: String,
    pub plan: String,
    pub seats: u32,
    pub machine_id: String,
    pub issued: String,
    pub expires: String,
    #[serde(default = "default_version")]
    pub v: u32,
}

fn default_version() -> u32 {
    1
}

impl LicensePayload {
    /// Check whether the license has expired.
    pub fn is_expired(&self) -> bool {
        DateTime::parse_from_rfc3339(&self.expires)
            .map(|exp| exp.with_timezone(&Utc) < Utc::now())
            .unwrap_or(true)
    }

    /// Days until expiry (negative = already expired).
    pub fn days_remaining(&self) -> i64 {
        DateTime::parse_from_rfc3339(&self.expires)
            .map(|exp| (exp.with_timezone(&Utc) - Utc::now()).num_days())
            .unwrap_or(-1)
    }
}

/// Result of a license verification attempt.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LicenseStatus {
    pub valid: bool,
    pub payload: Option<LicensePayload>,
    pub error: Option<String>,
    pub days_remaining: Option<i64>,
}

// ── Core verification ──────────────────────────────────────────────────

/// Verify a license blob string: `base64(json_payload).base64(signature)`.
///
/// Returns `Ok(LicensePayload)` if the signature is valid and not expired.
pub fn verify_license_blob(blob: &str) -> Result<LicensePayload, String> {
    let parts: Vec<&str> = blob.splitn(2, '.').collect();
    if parts.len() != 2 {
        return Err("Invalid license format".to_string());
    }

    let payload_bytes = B64.decode(parts[0]).map_err(|e| format!("Bad payload base64: {}", e))?;
    let sig_bytes = B64.decode(parts[1]).map_err(|e| format!("Bad signature base64: {}", e))?;

    // Decode public key
    let pub_key_bytes = B64
        .decode(ED25519_PUBLIC_KEY_B64)
        .map_err(|e| format!("Bad public key: {}", e))?;
    let pub_key_array: [u8; 32] = pub_key_bytes
        .try_into()
        .map_err(|_| "Public key must be 32 bytes".to_string())?;
    let verifying_key =
        VerifyingKey::from_bytes(&pub_key_array).map_err(|e| format!("Invalid public key: {}", e))?;

    // Decode signature
    let sig_array: [u8; 64] = sig_bytes
        .try_into()
        .map_err(|_| "Signature must be 64 bytes".to_string())?;
    let signature = Signature::from_bytes(&sig_array);

    // Verify
    verifying_key
        .verify(&payload_bytes, &signature)
        .map_err(|_| "Signature verification failed — license is invalid or tampered".to_string())?;

    // Parse payload
    let payload: LicensePayload = serde_json::from_slice(&payload_bytes)
        .map_err(|e| format!("Bad payload JSON: {}", e))?;

    // Check expiry
    if payload.is_expired() {
        return Err(format!(
            "License expired on {}. Please revalidate online.",
            payload.expires
        ));
    }

    Ok(payload)
}

// ── File persistence ───────────────────────────────────────────────────

/// Returns the path where the license file is stored.
pub fn license_file_path() -> PathBuf {
    let data_dir = dirs::data_dir().unwrap_or_else(|| PathBuf::from("."));
    data_dir.join("promptshield").join("license.key")
}

/// Read the license blob from disk.
pub fn read_license_file() -> Option<String> {
    let path = license_file_path();
    std::fs::read_to_string(&path).ok().map(|s| s.trim().to_string())
}

/// Write a license blob to disk.
pub fn write_license_file(blob: &str) -> Result<(), String> {
    let path = license_file_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("Cannot create license dir: {}", e))?;
    }
    std::fs::write(&path, blob).map_err(|e| format!("Cannot write license file: {}", e))?;

    // M20: Restrict file permissions (Windows: this is best-effort; real ACL control
    // would need the windows-acl crate. On Unix we'd use std::os::unix::fs::PermissionsExt.)
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600));
    }

    Ok(())
}

/// Delete the license file (e.g. on logout).
pub fn delete_license_file() -> Result<(), String> {
    let path = license_file_path();
    if path.exists() {
        std::fs::remove_file(&path).map_err(|e| format!("Cannot delete license file: {}", e))?;
    }
    Ok(())
}

// ── High-level check ───────────────────────────────────────────────────

/// Validate the license on disk. Returns full status info.
pub fn validate_stored_license() -> LicenseStatus {
    match read_license_file() {
        None => LicenseStatus {
            valid: false,
            payload: None,
            error: Some("No license file found. Please activate.".to_string()),
            days_remaining: None,
        },
        Some(blob) => match verify_license_blob(&blob) {
            Ok(payload) => {
                let days = payload.days_remaining();
                LicenseStatus {
                    valid: true,
                    payload: Some(payload),
                    error: None,
                    days_remaining: Some(days),
                }
            }
            Err(e) => LicenseStatus {
                valid: false,
                payload: None,
                error: Some(e),
                days_remaining: None,
            },
        },
    }
}

/// Validate a specific machine fingerprint against the stored license.
pub fn validate_for_machine(machine_fingerprint: &str) -> LicenseStatus {
    let status = validate_stored_license();
    if let Some(ref payload) = status.payload {
        if payload.machine_id != machine_fingerprint {
            return LicenseStatus {
                valid: false,
                payload: status.payload,
                error: Some("License is bound to a different machine".to_string()),
                days_remaining: status.days_remaining,
            };
        }
    }
    status
}

// ── S2: NTP clock drift check ──────────────────────────────────────────

/// Maximum tolerated drift between local clock and network time (seconds).
const MAX_CLOCK_DRIFT_SECS: i64 = 300; // 5 minutes

/// Fetch current UTC time from worldtimeapi.org and compare against
/// the local system clock. Returns `Err` if the drift exceeds the
/// threshold, indicating the user may have manipulated their clock.
///
/// Fails *open* — if the network is unreachable we allow the app to continue
/// (the user is working offline with a local license blob).
pub async fn check_clock_drift() -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))?;

    // Try worldtimeapi.org (returns RFC3339 datetime in .utc_datetime)
    let resp = match client
        .get("https://worldtimeapi.org/api/timezone/Etc/UTC")
        .send()
        .await
    {
        Ok(r) if r.status().is_success() => r,
        _ => return Ok(()), // network unreachable — fail open
    };

    #[derive(serde::Deserialize)]
    struct TimeResp {
        utc_datetime: String,
    }

    let body: TimeResp = match resp.json().await {
        Ok(b) => b,
        Err(_) => return Ok(()), // malformed response — fail open
    };

    let server_time = DateTime::parse_from_rfc3339(&body.utc_datetime)
        .or_else(|_| {
            // worldtimeapi sometimes returns "2025-01-01T00:00:00.123456+00:00" style
            DateTime::parse_from_str(&body.utc_datetime, "%Y-%m-%dT%H:%M:%S%.f%:z")
        })
        .map_err(|e| format!("Cannot parse server time: {e}"))?
        .with_timezone(&Utc);

    let local_time = Utc::now();
    let drift = (server_time - local_time).num_seconds().abs();

    if drift > MAX_CLOCK_DRIFT_SECS {
        return Err(format!(
            "System clock appears to be off by {drift} seconds. \
             Please correct your system time to use PromptShield."
        ));
    }

    Ok(())
}

// ── S1: Server-side revocation check ───────────────────────────────────

/// Check with the licensing server whether this machine's license has been
/// revoked (e.g. subscription cancelled, machine deactivated from dashboard).
///
/// Fails *open* — if the network is unreachable the app continues with the
/// local blob. Only blocks when the server explicitly says `revoked: true`.
pub async fn check_revocation(
    licensing_url: &str,
    machine_fingerprint: &str,
) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))?;

    let url = format!(
        "{}/license/check-revocation?machine_fingerprint={}",
        licensing_url, machine_fingerprint,
    );

    let resp = match client.get(&url).send().await {
        Ok(r) if r.status().is_success() => r,
        _ => return Ok(()), // network unreachable — fail open
    };

    #[derive(serde::Deserialize)]
    struct RevocationResp {
        revoked: bool,
    }

    let body: RevocationResp = match resp.json().await {
        Ok(b) => b,
        Err(_) => return Ok(()), // malformed response — fail open
    };

    if body.revoked {
        // Delete the local license file so the user must re-authenticate
        let _ = delete_license_file();
        return Err(
            "Your license has been revoked. Please sign in again or contact support.".to_string(),
        );
    }

    Ok(())
}
