// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/

mod integrity;
mod license;
mod machine_id;

use std::sync::Mutex;
use tauri::Emitter;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};

/// Check if a backend is already listening on the given port.
fn backend_already_running(port: u16) -> bool {
    std::net::TcpStream::connect_timeout(
        &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
        std::time::Duration::from_millis(500),
    )
    .is_ok()
}

/// Holds the sidecar child process so we can kill it on app exit.
struct SidecarChild(Mutex<Option<CommandChild>>);

// ── Tauri commands for license operations ──────────────────────────────

/// Return the machine hardware fingerprint (SHA-256 hex of HW identifiers).
#[tauri::command]
fn get_machine_id() -> String {
    machine_id::get_machine_fingerprint()
}

/// Return a friendly machine name (hostname).
#[tauri::command]
fn get_machine_name() -> String {
    machine_id::get_machine_name()
}

/// Validate the currently stored license file.
/// Returns full status including validity, plan, days remaining, errors.
#[tauri::command]
fn validate_license() -> license::LicenseStatus {
    let fingerprint = machine_id::get_machine_fingerprint();
    license::validate_for_machine(&fingerprint)
}

/// Store a license blob received from the licensing server.
/// The blob is written to `%APPDATA%/promptshield/license.key`.
#[tauri::command]
fn store_license(blob: String) -> Result<license::LicenseStatus, String> {
    license::write_license_file(&blob)?;
    let fingerprint = machine_id::get_machine_fingerprint();
    Ok(license::validate_for_machine(&fingerprint))
}

/// Delete the stored license file (logout / deactivation).
#[tauri::command]
fn clear_license() -> Result<(), String> {
    license::delete_license_file()
}

/// Get the path where the license file is stored, for debugging.
#[tauri::command]
fn get_license_path() -> String {
    license::license_file_path().to_string_lossy().to_string()
}

// ── Sidecar launcher (gated behind license check) ─────────────────────

/// Attempt to start the sidecar if a valid license is present.
/// This is called from the frontend after successful auth.
#[tauri::command]
async fn start_backend(app: tauri::AppHandle) -> Result<String, String> {
    // Check license first
    let fingerprint = machine_id::get_machine_fingerprint();
    let status = license::validate_for_machine(&fingerprint);
    if !status.valid {
        return Err(status.error.unwrap_or_else(|| "Invalid license".to_string()));
    }

    // S2: Check for clock manipulation before allowing backend start
    if let Err(drift_err) = license::check_clock_drift().await {
        return Err(drift_err);
    }

    // S1: Check if the license has been revoked server-side
    let licensing_url = std::env::var("LICENSING_URL")
        .unwrap_or_else(|_| "https://licensing-server-455859748614.us-east4.run.app".to_string());
    if let Err(revoke_err) = license::check_revocation(&licensing_url, &fingerprint).await {
        return Err(revoke_err);
    }

    let dev_port: u16 = std::env::var("DOC_ANON_BACKEND_PORT")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(8910);

    if backend_already_running(dev_port) {
        return Ok(dev_port.to_string());
    }

    let sidecar_command = app
        .shell()
        .sidecar("doc-anonymizer-sidecar")
        .map_err(|e| format!("Failed to create sidecar command: {}", e))?;

    // H12: Verify sidecar binary integrity before spawning (if hash is available)
    // In production, set SIDECAR_HASH at build time.
    if let Ok(expected_hash) = std::env::var("SIDECAR_EXPECTED_HASH") {
        let sidecar_path = app
            .path()
            .resource_dir()
            .map(|d| d.join("binaries").join("doc-anonymizer-sidecar"))
            .unwrap_or_default();
        let path_str = sidecar_path.to_string_lossy();
        if !path_str.is_empty() && !integrity::verify_binary_integrity(&path_str, &expected_hash) {
            return Err("Sidecar binary integrity check failed — possible tampering".to_string());
        }
    }

    let (mut rx, child) = sidecar_command
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

    // Store the child handle
    {
        let state = app.state::<SidecarChild>();
        let mut guard = state
            .0
            .lock()
            .map_err(|_| "Failed to acquire sidecar mutex".to_string())?;
        *guard = Some(child);
    }

    // Wait for PORT: line with timeout
    let app_handle = app.clone();
    let port_result = tokio::time::timeout(
        tokio::time::Duration::from_secs(30),
        async move {
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        let line_str = String::from_utf8_lossy(&line);
                        if line_str.starts_with("PORT:") {
                            let port = line_str
                                .trim_start_matches("PORT:")
                                .trim()
                                .to_string();
                            let _ = app_handle.emit("sidecar-port", &port);
                            return Ok(port);
                        }
                    }
                    CommandEvent::Stderr(line) => {
                        let line_str = String::from_utf8_lossy(&line);
                        eprintln!("[sidecar] {}", line_str);
                    }
                    _ => {}
                }
            }
            Err("Sidecar exited without emitting a port".to_string())
        },
    )
    .await;

    match port_result {
        Ok(Ok(port)) => Ok(port),
        Ok(Err(e)) => Err(e),
        Err(_) => Err("Sidecar did not start within 30 seconds".to_string()),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarChild(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            get_machine_id,
            get_machine_name,
            validate_license,
            store_license,
            clear_license,
            get_license_path,
            start_backend,
        ])
        .setup(|app| {
            // Run integrity checks (anti-debug, timing)
            if let Err(e) = integrity::run_integrity_checks() {
                eprintln!("[SECURITY] Integrity check failed: {}", e);
                // In release builds, exit immediately
                if !cfg!(debug_assertions) {
                    std::process::exit(1);
                }
            }

            // Emit initial license status so frontend knows whether to show
            // the auth screen or the main app.
            let status = license::validate_stored_license();
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let _ = app_handle.emit("license-status", &status);
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let state = app.state::<SidecarChild>();
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                        println!("Killed sidecar process on exit");
                    }
                };
            }
        });
}
