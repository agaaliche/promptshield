//! App update mechanism — online check + download, and offline package install.
//!
//! ## Online flow
//! 1. `check_for_updates` → GET update manifest from server
//! 2. `download_and_install_update` → download package, verify hash, launch installer
//!
//! ## Offline flow
//! 1. User picks a `.promptshield-update` file via the frontend
//! 2. `install_offline_update` → verify hash in embedded manifest, extract, launch installer

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

/// Base URL for the update server (can be overridden in dev via env var).
const UPDATE_SERVER_URL: &str = "https://api.promptshield.com";

/// Current app version — read from tauri.conf.json at compile time.
const CURRENT_VERSION: &str = env!("CARGO_PKG_VERSION");

// ── Types ────────────────────────────────────────────────────────────────

/// Update manifest returned by the server.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateManifest {
    /// Latest available version string, e.g. "0.2.0"
    pub version: String,
    /// Release notes / changelog (Markdown)
    pub notes: String,
    /// Publication date (ISO 8601)
    pub pub_date: String,
    /// Download URL for the installer package
    pub url: String,
    /// SHA-256 hex digest of the package file
    pub sha256: String,
    /// Package file size in bytes
    pub size: u64,
    /// Whether this update is mandatory
    #[serde(default)]
    pub mandatory: bool,
}

/// Result of checking for updates.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateCheckResult {
    /// Whether an update is available
    pub update_available: bool,
    /// Current running version
    pub current_version: String,
    /// Latest version on the server (if check succeeded)
    pub latest_version: Option<String>,
    /// Full manifest (if update is available)
    pub manifest: Option<UpdateManifest>,
    /// Error message if the check failed
    pub error: Option<String>,
}

/// Progress info emitted during download.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DownloadProgress {
    pub downloaded_bytes: u64,
    pub total_bytes: u64,
    pub percent: f64,
}

/// Result of an install operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstallResult {
    pub success: bool,
    pub message: String,
    /// If true, the app needs to restart
    pub needs_restart: bool,
}

/// Metadata embedded in offline update packages.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OfflinePackageMeta {
    pub version: String,
    pub sha256: String,
    pub notes: String,
    pub pub_date: String,
    pub platform: String,
}

// ── Helpers ──────────────────────────────────────────────────────────────

/// Get the update server URL, respecting dev override.
fn update_server_url() -> String {
    if cfg!(debug_assertions) {
        std::env::var("UPDATE_SERVER_URL").unwrap_or_else(|_| UPDATE_SERVER_URL.to_string())
    } else {
        UPDATE_SERVER_URL.to_string()
    }
}

/// Directory where downloaded updates are staged.
fn updates_dir() -> PathBuf {
    let base = dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("promptshield")
        .join("updates");
    let _ = fs::create_dir_all(&base);
    base
}

/// Compare two semver-like version strings. Returns true if `remote` > `local`.
pub fn is_newer_version(local: &str, remote: &str) -> bool {
    let parse = |v: &str| -> Vec<u64> {
        v.trim_start_matches('v')
            .split('.')
            .filter_map(|s| s.parse::<u64>().ok())
            .collect()
    };
    let l = parse(local);
    let r = parse(remote);
    for i in 0..std::cmp::max(l.len(), r.len()) {
        let lv = l.get(i).copied().unwrap_or(0);
        let rv = r.get(i).copied().unwrap_or(0);
        if rv > lv {
            return true;
        }
        if rv < lv {
            return false;
        }
    }
    false
}

/// Compute SHA-256 hex digest of a file.
fn sha256_file(path: &Path) -> Result<String, String> {
    let data = fs::read(path).map_err(|e| format!("Failed to read file: {}", e))?;
    let mut hasher = Sha256::new();
    hasher.update(&data);
    Ok(hex::encode(hasher.finalize()))
}

// ── Online update check ──────────────────────────────────────────────────

/// Check the update server for a newer version.
pub async fn check_for_updates() -> UpdateCheckResult {
    let url = format!(
        "{}/updates/check?version={}&platform={}",
        update_server_url(),
        CURRENT_VERSION,
        std::env::consts::OS,
    );

    match reqwest::get(&url).await {
        Ok(resp) => {
            if resp.status().is_success() {
                match resp.json::<UpdateManifest>().await {
                    Ok(manifest) => {
                        let available = is_newer_version(CURRENT_VERSION, &manifest.version);
                        UpdateCheckResult {
                            update_available: available,
                            current_version: CURRENT_VERSION.to_string(),
                            latest_version: Some(manifest.version.clone()),
                            manifest: if available { Some(manifest) } else { None },
                            error: None,
                        }
                    }
                    Err(e) => UpdateCheckResult {
                        update_available: false,
                        current_version: CURRENT_VERSION.to_string(),
                        latest_version: None,
                        manifest: None,
                        error: Some(format!("Failed to parse update manifest: {}", e)),
                    },
                }
            } else if resp.status().as_u16() == 204 {
                // 204 = no update available
                UpdateCheckResult {
                    update_available: false,
                    current_version: CURRENT_VERSION.to_string(),
                    latest_version: Some(CURRENT_VERSION.to_string()),
                    manifest: None,
                    error: None,
                }
            } else {
                UpdateCheckResult {
                    update_available: false,
                    current_version: CURRENT_VERSION.to_string(),
                    latest_version: None,
                    manifest: None,
                    error: Some(format!("Server returned status {}", resp.status())),
                }
            }
        }
        Err(e) => UpdateCheckResult {
            update_available: false,
            current_version: CURRENT_VERSION.to_string(),
            latest_version: None,
            manifest: None,
            error: Some(format!("Network error: {}", e)),
        },
    }
}

// ── Online download + install ────────────────────────────────────────────

/// Download the update package, verify its integrity, and launch the installer.
pub async fn download_and_install(
    manifest: &UpdateManifest,
    app: &tauri::AppHandle,
) -> InstallResult {
    let dir = updates_dir();

    // Derive filename from URL
    let filename = manifest
        .url
        .rsplit('/')
        .next()
        .unwrap_or("update-package.exe");
    let dest = dir.join(filename);

    // Download with progress events
    match download_file(&manifest.url, &dest, &manifest.sha256, manifest.size, app).await {
        Ok(_) => {}
        Err(e) => {
            return InstallResult {
                success: false,
                message: format!("Download failed: {}", e),
                needs_restart: false,
            }
        }
    }

    // Launch the installer
    launch_installer(&dest)
}

/// Download a file with SHA-256 verification and progress events.
async fn download_file(
    url: &str,
    dest: &Path,
    expected_sha256: &str,
    total_size: u64,
    app: &tauri::AppHandle,
) -> Result<(), String> {
    use tauri::Emitter;

    let resp = reqwest::get(url)
        .await
        .map_err(|e| format!("Download request failed: {}", e))?;

    if !resp.status().is_success() {
        return Err(format!("Download failed with status {}", resp.status()));
    }

    let total = resp.content_length().unwrap_or(total_size);
    let bytes = resp
        .bytes()
        .await
        .map_err(|e| format!("Failed to read download body: {}", e))?;

    // Emit final progress
    let _ = app.emit(
        "update-download-progress",
        DownloadProgress {
            downloaded_bytes: bytes.len() as u64,
            total_bytes: total,
            percent: 100.0,
        },
    );

    // Verify SHA-256
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    let actual_hash = hex::encode(hasher.finalize());

    if actual_hash != expected_sha256.to_lowercase() {
        return Err(format!(
            "SHA-256 mismatch: expected {}, got {}",
            expected_sha256, actual_hash
        ));
    }

    // Write to disk
    let mut file =
        fs::File::create(dest).map_err(|e| format!("Failed to create file: {}", e))?;
    file.write_all(&bytes)
        .map_err(|e| format!("Failed to write file: {}", e))?;

    Ok(())
}

/// Launch the downloaded installer and signal app restart.
fn launch_installer(path: &Path) -> InstallResult {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    let result = match ext.as_str() {
        "exe" | "msi" => {
            // Launch NSIS/MSI installer silently
            std::process::Command::new(path)
                .args(["--update", "/S"]) // /S = silent for NSIS
                .spawn()
        }
        _ => {
            // Try to open with system default handler
            #[cfg(target_os = "windows")]
            {
                std::process::Command::new("cmd")
                    .args(["/C", "start", "", &path.to_string_lossy()])
                    .spawn()
            }
            #[cfg(not(target_os = "windows"))]
            {
                std::process::Command::new("open").arg(path).spawn()
            }
        }
    };

    match result {
        Ok(_) => InstallResult {
            success: true,
            message: "Update installer launched. The app will restart.".to_string(),
            needs_restart: true,
        },
        Err(e) => InstallResult {
            success: false,
            message: format!("Failed to launch installer: {}", e),
            needs_restart: false,
        },
    }
}

// ── Offline update ───────────────────────────────────────────────────────

/// Read and validate an offline update package.
///
/// The package is a zip archive containing:
/// - `manifest.json` — version, sha256, notes, platform
/// - The actual installer binary
pub fn read_offline_package(path: &str) -> Result<OfflinePackageMeta, String> {
    let archive_path = Path::new(path);
    if !archive_path.exists() {
        return Err("File not found".to_string());
    }

    let file = fs::File::open(archive_path)
        .map_err(|e| format!("Failed to open package: {}", e))?;
    let mut archive = zip::ZipArchive::new(file)
        .map_err(|e| format!("Invalid update package (not a valid zip): {}", e))?;

    // Read manifest
    let manifest_str = {
        let mut manifest_file = archive
            .by_name("manifest.json")
            .map_err(|_| "Update package missing manifest.json".to_string())?;
        let mut buf = String::new();
        std::io::Read::read_to_string(&mut manifest_file, &mut buf)
            .map_err(|e| format!("Failed to read manifest: {}", e))?;
        buf
    };

    let meta: OfflinePackageMeta = serde_json::from_str(&manifest_str)
        .map_err(|e| format!("Invalid manifest.json: {}", e))?;

    // Verify it's newer than current
    if !is_newer_version(CURRENT_VERSION, &meta.version) {
        return Err(format!(
            "Package version {} is not newer than current version {}",
            meta.version, CURRENT_VERSION
        ));
    }

    Ok(meta)
}

/// Install an offline update package.
///
/// Extracts the installer from the zip, verifies its hash, and launches it.
pub fn install_offline_package(path: &str) -> InstallResult {
    let archive_path = Path::new(path);
    let file = match fs::File::open(archive_path) {
        Ok(f) => f,
        Err(e) => {
            return InstallResult {
                success: false,
                message: format!("Failed to open package: {}", e),
                needs_restart: false,
            }
        }
    };

    let mut archive = match zip::ZipArchive::new(file) {
        Ok(a) => a,
        Err(e) => {
            return InstallResult {
                success: false,
                message: format!("Invalid update package: {}", e),
                needs_restart: false,
            }
        }
    };

    // Read manifest
    let meta: OfflinePackageMeta = {
        let mut manifest_file = match archive.by_name("manifest.json") {
            Ok(f) => f,
            Err(_) => {
                return InstallResult {
                    success: false,
                    message: "Package missing manifest.json".to_string(),
                    needs_restart: false,
                }
            }
        };
        let mut buf = String::new();
        if std::io::Read::read_to_string(&mut manifest_file, &mut buf).is_err() {
            return InstallResult {
                success: false,
                message: "Failed to read manifest".to_string(),
                needs_restart: false,
            };
        }
        match serde_json::from_str(&buf) {
            Ok(m) => m,
            Err(e) => {
                return InstallResult {
                    success: false,
                    message: format!("Invalid manifest: {}", e),
                    needs_restart: false,
                }
            }
        }
    };

    // Find installer file (any file that isn't manifest.json)
    let dest_dir = updates_dir();
    let mut installer_path: Option<PathBuf> = None;

    for i in 0..archive.len() {
        let mut entry = match archive.by_index(i) {
            Ok(e) => e,
            Err(_) => continue,
        };
        let name = entry.name().to_string();
        if name == "manifest.json" || entry.is_dir() {
            continue;
        }

        let dest = dest_dir.join(&name);
        let mut outfile = match fs::File::create(&dest) {
            Ok(f) => f,
            Err(e) => {
                return InstallResult {
                    success: false,
                    message: format!("Failed to extract {}: {}", name, e),
                    needs_restart: false,
                }
            }
        };
        if std::io::copy(&mut entry, &mut outfile).is_err() {
            return InstallResult {
                success: false,
                message: format!("Failed to write {}", name),
                needs_restart: false,
            };
        }
        installer_path = Some(dest);
    }

    let installer = match installer_path {
        Some(p) => p,
        None => {
            return InstallResult {
                success: false,
                message: "No installer found in update package".to_string(),
                needs_restart: false,
            }
        }
    };

    // Verify SHA-256 of the extracted installer
    match sha256_file(&installer) {
        Ok(hash) => {
            if hash != meta.sha256.to_lowercase() {
                return InstallResult {
                    success: false,
                    message: format!(
                        "Integrity check failed: expected {}, got {}",
                        meta.sha256, hash
                    ),
                    needs_restart: false,
                };
            }
        }
        Err(e) => {
            return InstallResult {
                success: false,
                message: format!("Hash verification failed: {}", e),
                needs_restart: false,
            }
        }
    }

    // Launch installer
    launch_installer(&installer)
}

/// Clean up any downloaded update files.
pub fn cleanup_updates() {
    let dir = updates_dir();
    if dir.exists() {
        let _ = fs::remove_dir_all(&dir);
        let _ = fs::create_dir_all(&dir);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_version_comparison() {
        assert!(is_newer_version("0.1.0", "0.2.0"));
        assert!(is_newer_version("0.1.0", "0.1.1"));
        assert!(is_newer_version("0.1.0", "1.0.0"));
        assert!(!is_newer_version("0.2.0", "0.1.0"));
        assert!(!is_newer_version("0.1.0", "0.1.0"));
        assert!(is_newer_version("v0.1.0", "v0.2.0"));
    }
}
