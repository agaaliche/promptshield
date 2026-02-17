/**
 * Update API — Tauri commands for checking, downloading, and installing updates.
 *
 * Online: check server → download → verify → install
 * Offline: user picks .promptshield-update file → verify → install
 */

import { isTauri } from "./licenseApi";

// ── Tauri invoke helper ──────────────────────────────────────────

async function tauriInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(cmd, args);
}

// ── Types ────────────────────────────────────────────────────────

export interface UpdateManifest {
  version: string;
  notes: string;
  pub_date: string;
  url: string;
  sha256: string;
  size: number;
  mandatory: boolean;
}

export interface UpdateCheckResult {
  update_available: boolean;
  current_version: string;
  latest_version: string | null;
  manifest: UpdateManifest | null;
  error: string | null;
}

export interface DownloadProgress {
  downloaded_bytes: number;
  total_bytes: number;
  percent: number;
}

export interface InstallResult {
  success: boolean;
  message: string;
  needs_restart: boolean;
}

export interface OfflinePackageMeta {
  version: string;
  sha256: string;
  notes: string;
  pub_date: string;
  platform: string;
}

// ── API functions ────────────────────────────────────────────────

/** Get current app version. */
export async function getAppVersion(): Promise<string> {
  if (!isTauri()) return "0.1.0-dev";
  return tauriInvoke<string>("get_app_version");
}

/** Check server for a newer version. */
export async function checkForUpdates(): Promise<UpdateCheckResult> {
  if (!isTauri()) {
    return {
      update_available: false,
      current_version: "0.1.0-dev",
      latest_version: null,
      manifest: null,
      error: "Updates are only available in the desktop app",
    };
  }
  return tauriInvoke<UpdateCheckResult>("check_for_updates");
}

/** Download and install an online update. */
export async function downloadAndInstallUpdate(manifest: UpdateManifest): Promise<InstallResult> {
  return tauriInvoke<InstallResult>("download_and_install_update", {
    manifestJson: JSON.stringify(manifest),
  });
}

/** Read and validate an offline update package (without installing). */
export async function readOfflinePackage(path: string): Promise<OfflinePackageMeta> {
  return tauriInvoke<OfflinePackageMeta>("read_offline_package", { path });
}

/** Install an offline update package. */
export async function installOfflineUpdate(path: string): Promise<InstallResult> {
  return tauriInvoke<InstallResult>("install_offline_update", { path });
}

/** Clean up downloaded update files. */
export async function cleanupUpdates(): Promise<void> {
  if (!isTauri()) return;
  return tauriInvoke<void>("cleanup_updates");
}

/** Listen for download progress events. */
export async function onDownloadProgress(
  callback: (progress: DownloadProgress) => void,
): Promise<() => void> {
  if (!isTauri()) return () => {};
  const { listen } = await import("@tauri-apps/api/event");
  const unlisten = await listen<DownloadProgress>("update-download-progress", (event) => {
    callback(event.payload);
  });
  return unlisten;
}

/** Open a file dialog to pick an offline update package. */
export async function pickUpdateFile(): Promise<string | null> {
  if (!isTauri()) return null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const result = await open({
    title: "Select update package",
    filters: [
      { name: "promptShield Update", extensions: ["zip", "promptshield-update"] },
    ],
    multiple: false,
    directory: false,
  });
  if (!result) return null;
  // Tauri v2 open() returns string | string[] | null
  return typeof result === "string" ? result : result[0] ?? null;
}
