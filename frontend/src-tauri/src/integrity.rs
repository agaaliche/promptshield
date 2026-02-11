/// Anti-tamper and integrity verification module.
///
/// Provides runtime checks to detect debugging, tampering, and unauthorized
/// modification of the application binary or license system.

use std::time::{Instant, Duration};

/// Detect if a debugger is attached (Windows-specific).
///
/// Uses the `IsDebuggerPresent` WinAPI call. On other platforms this is
/// a no-op that always returns false to avoid breaking development.
#[cfg(target_os = "windows")]
pub fn is_debugger_present() -> bool {
    extern "system" {
        fn IsDebuggerPresent() -> i32;
    }
    unsafe { IsDebuggerPresent() != 0 }
}

#[cfg(not(target_os = "windows"))]
pub fn is_debugger_present() -> bool {
    // On macOS/Linux, check for common debugger indicators
    #[cfg(target_os = "linux")]
    {
        // Check /proc/self/status for TracerPid
        if let Ok(status) = std::fs::read_to_string("/proc/self/status") {
            for line in status.lines() {
                if line.starts_with("TracerPid:") {
                    let pid: i32 = line
                        .split_whitespace()
                        .nth(1)
                        .and_then(|s| s.parse().ok())
                        .unwrap_or(0);
                    return pid != 0;
                }
            }
        }
    }
    false
}

/// Timing-based anti-debug check.
///
/// Executes a calibrated workload and checks if it took suspiciously long,
/// which may indicate single-stepping or breakpoint traps.
pub fn timing_check() -> bool {
    let start = Instant::now();
    // Meaningless but non-optimizable work
    let mut acc: u64 = 0;
    for i in 0..100_000u64 {
        acc = acc.wrapping_add(i.wrapping_mul(0x5DEECE66D));
    }
    // Prevent optimization
    std::hint::black_box(acc);
    let elapsed = start.elapsed();
    // If a simple loop takes > 2 seconds, something is very wrong
    elapsed > Duration::from_secs(2)
}

/// Verify the sidecar binary hasn't been tampered with.
///
/// Checks that the binary at the given path matches an expected SHA-256 hash.
/// The expected hash should be set at build time (e.g. via `include_str!` or
/// environment variable).
pub fn verify_binary_integrity(binary_path: &str, expected_hash: &str) -> bool {
    use sha2::{Sha256, Digest};

    let bytes = match std::fs::read(binary_path) {
        Ok(b) => b,
        Err(_) => return false,
    };

    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    let digest = hasher.finalize();
    let hex_hash: String = digest.iter().map(|b| format!("{:02x}", b)).collect();

    hex_hash == expected_hash
}

/// Run all anti-tamper checks. Returns an error message if any fail.
///
/// In production builds, failing these checks should prevent the app from
/// starting. In development (debug builds), checks are logged but non-fatal.
pub fn run_integrity_checks() -> Result<(), String> {
    if is_debugger_present() {
        let msg = "Debugger detected. The application cannot run under a debugger.";
        if cfg!(debug_assertions) {
            eprintln!("[integrity] WARNING: {}", msg);
        } else {
            return Err(msg.to_string());
        }
    }

    if timing_check() {
        let msg = "Timing anomaly detected — possible debugger or instrumentation.";
        if cfg!(debug_assertions) {
            eprintln!("[integrity] WARNING: {}", msg);
        } else {
            return Err(msg.to_string());
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn timing_check_passes_normally() {
        // Under normal conditions the timing check should not trigger
        assert!(!timing_check());
    }

    #[test]
    fn debugger_check_runs_without_panic() {
        // Just verify the function doesn't panic
        let _ = is_debugger_present();
    }
}
