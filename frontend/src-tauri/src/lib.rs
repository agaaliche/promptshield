// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarChild(Mutex::new(None)))
        .setup(|app| {
            // If backend is already running (e.g. started by start.ps1),
            // skip sidecar and emit the port directly.
            let dev_port: u16 = std::env::var("DOC_ANON_BACKEND_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(8910);

            if backend_already_running(dev_port) {
                println!("Backend already running on port {}", dev_port);
                let port_str = dev_port.to_string();
                let app_handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    let _ = app_handle.emit("sidecar-port", &port_str);
                });
                return Ok(());
            }

            // Otherwise spawn the Python sidecar
            let sidecar_command = app
                .shell()
                .sidecar("doc-anonymizer-sidecar")
                .expect("failed to create sidecar command");

            let (mut rx, child) = sidecar_command
                .spawn()
                .expect("failed to spawn sidecar");

            // Store the child handle so we can kill it on shutdown
            {
                let state = app.state::<SidecarChild>();
                let mut guard = state.0.lock().expect("Failed to acquire sidecar mutex during setup");
                *guard = Some(child);
            }

            // Read the port from sidecar stdout (with a startup timeout)
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let timeout = tokio::time::Duration::from_secs(30);
                let port_received = tokio::time::timeout(timeout, async {
                    while let Some(event) = rx.recv().await {
                        match event {
                            CommandEvent::Stdout(line) => {
                                let line_str = String::from_utf8_lossy(&line);
                                if line_str.starts_with("PORT:") {
                                    let port = line_str
                                        .trim_start_matches("PORT:")
                                        .trim()
                                        .to_string();
                                    // Emit the port to the frontend
                                    let _ = app_handle.emit("sidecar-port", &port);
                                    println!("Sidecar started on port {}", port);
                                    return true;
                                }
                            }
                            CommandEvent::Stderr(line) => {
                                let line_str = String::from_utf8_lossy(&line);
                                eprintln!("[sidecar] {}", line_str);
                            }
                            _ => {}
                        }
                    }
                    false
                })
                .await;

                match port_received {
                    Ok(true) => {}
                    Ok(false) => {
                        eprintln!("Sidecar process exited without emitting a port");
                    }
                    Err(_) => {
                        eprintln!("Sidecar did not start within 30 seconds — timed out");
                    }
                }

                // Continue draining stderr after port is received
                // (rx is consumed by now so nothing more to do here)
            });

            Ok(())
        })
        .on_event(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let state = app.state::<SidecarChild>();
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                        println!("Killed sidecar process on exit");
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
