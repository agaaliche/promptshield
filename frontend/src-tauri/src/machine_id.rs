/// Machine fingerprinting for license binding.
///
/// Collects hardware identifiers and produces a deterministic SHA-256 digest
/// that uniquely identifies the physical machine. The fingerprint is stable
/// across reboots but will change if hardware is swapped.

use base64::Engine;
use sha2::{Digest, Sha256};
use std::process::Command;

/// Collect a hardware fingerprint string from OS-specific sources.
///
/// On Windows we query WMI via PowerShell for:
///   - CPU ProcessorId
///   - BIOS SerialNumber
///   - BaseBoard SerialNumber
///   - Disk drive serial (first physical disk)
///
/// The raw identifiers are concatenated and SHA-256 hashed to produce a
/// fixed-length hex string.
pub fn get_machine_fingerprint() -> String {
    let raw = collect_raw_identifiers();
    let mut hasher = Sha256::new();
    hasher.update(raw.as_bytes());
    let result = hasher.finalize();
    hex_encode(&result)
}

fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

#[cfg(target_os = "windows")]
fn collect_raw_identifiers() -> String {
    let cpu = wmi_query("cpu", "ProcessorId");
    let bios = wmi_query("bios", "SerialNumber");
    let board = wmi_query("baseboard", "SerialNumber");
    let disk = wmi_query("diskdrive where Index=0", "SerialNumber");
    format!("{}|{}|{}|{}", cpu, bios, board, disk)
}

#[cfg(target_os = "macos")]
fn collect_raw_identifiers() -> String {
    // macOS: use IOPlatformSerialNumber from ioreg
    let output = Command::new("ioreg")
        .args(["-rd1", "-c", "IOPlatformExpertDevice"])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).to_string())
        .unwrap_or_default();

    // Extract serial number
    let serial = output
        .lines()
        .find(|l| l.contains("IOPlatformSerialNumber"))
        .and_then(|l| l.split('"').nth(3))
        .unwrap_or("unknown")
        .to_string();

    // Also grab hardware UUID
    let hw_uuid = Command::new("system_profiler")
        .args(["SPHardwareDataType"])
        .output()
        .map(|o| {
            String::from_utf8_lossy(&o.stdout)
                .lines()
                .find(|l| l.contains("Hardware UUID"))
                .and_then(|l| l.split(':').nth(1))
                .map(|s| s.trim().to_string())
                .unwrap_or_default()
        })
        .unwrap_or_default();

    format!("{}|{}", serial, hw_uuid)
}

#[cfg(target_os = "linux")]
fn collect_raw_identifiers() -> String {
    let machine_id = std::fs::read_to_string("/etc/machine-id")
        .or_else(|_| std::fs::read_to_string("/var/lib/dbus/machine-id"))
        .unwrap_or_default()
        .trim()
        .to_string();

    let product_uuid = std::fs::read_to_string("/sys/class/dmi/id/product_uuid")
        .unwrap_or_default()
        .trim()
        .to_string();

    format!("{}|{}", machine_id, product_uuid)
}

#[cfg(target_os = "windows")]
fn wmi_query(wmi_class: &str, property: &str) -> String {
    // M22: Use -EncodedCommand to avoid shell injection via class/property names.
    // Structured arguments prevent any interpolation attacks.
    let script = format!(
        "(Get-CimInstance -ClassName Win32_{} -ErrorAction SilentlyContinue | Select-Object -First 1).{}",
        wmi_class, property
    );
    // Encode the script as base64 UTF-16LE for -EncodedCommand
    let encoded: String = base64::engine::general_purpose::STANDARD.encode(
        script.encode_utf16().flat_map(|c| c.to_le_bytes()).collect::<Vec<u8>>()
    );
    Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-EncodedCommand", &encoded])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|_| "unknown".to_string())
}

/// Return a friendly machine name (hostname).
pub fn get_machine_name() -> String {
    hostname::get()
        .map(|h| h.to_string_lossy().to_string())
        .unwrap_or_else(|_| "Unknown".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fingerprint_is_deterministic() {
        let fp1 = get_machine_fingerprint();
        let fp2 = get_machine_fingerprint();
        assert_eq!(fp1, fp2);
        assert_eq!(fp1.len(), 64); // SHA-256 hex = 64 chars
    }
}
