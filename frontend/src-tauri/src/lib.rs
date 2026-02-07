// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/

use tauri::Emitter;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Spawn the Python sidecar
            let sidecar_command = app
                .shell()
                .sidecar("doc-anonymizer-sidecar")
                .expect("failed to create sidecar command");

            let (mut rx, _child) = sidecar_command
                .spawn()
                .expect("failed to spawn sidecar");

            // Read the port from sidecar stdout
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
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
                            }
                        }
                        CommandEvent::Stderr(line) => {
                            let line_str = String::from_utf8_lossy(&line);
                            eprintln!("[sidecar] {}", line_str);
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
