/** Updates section — online check + download, offline package install. */

import { useState, useEffect, useCallback } from "react";
import {
  Download,
  RefreshCw,
  Upload,
  CheckCircle,
  AlertTriangle,
  ArrowUpCircle,
  Package,
} from "lucide-react";
import { Section, styles } from "./settingsStyles";
import {
  getAppVersion,
  checkForUpdates,
  downloadAndInstallUpdate,
  readOfflinePackage,
  installOfflineUpdate,
  onDownloadProgress,
  pickUpdateFile,
  cleanupUpdates,
} from "../../updateApi";
import type {
  UpdateCheckResult,
  UpdateManifest,
  DownloadProgress,
  OfflinePackageMeta,
} from "../../updateApi";
import { isTauri } from "../../licenseApi";

type UpdatePhase =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "installing"
  | "up-to-date"
  | "error"
  | "offline-preview"
  | "offline-installing"
  | "done";

export default function UpdatesSection() {
  const [phase, setPhase] = useState<UpdatePhase>("idle");
  const [currentVersion, setCurrentVersion] = useState("…");
  const [checkResult, setCheckResult] = useState<UpdateCheckResult | null>(null);
  const [manifest, setManifest] = useState<UpdateManifest | null>(null);
  const [progress, setProgress] = useState<DownloadProgress | null>(null);
  const [error, setError] = useState("");
  const [offlineMeta, setOfflineMeta] = useState<OfflinePackageMeta | null>(null);
  const [offlinePath, setOfflinePath] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<string | null>(null);

  // Load current version
  useEffect(() => {
    getAppVersion().then(setCurrentVersion).catch(() => setCurrentVersion("unknown"));
  }, []);

  // Listen for download progress
  useEffect(() => {
    let unlisten: (() => void) | null = null;
    onDownloadProgress((p) => setProgress(p)).then((u) => {
      unlisten = u;
    });
    return () => {
      unlisten?.();
    };
  }, []);

  // ── Online check ──────────────────────────────────────────────

  const handleCheckForUpdates = useCallback(async () => {
    setPhase("checking");
    setError("");
    setCheckResult(null);
    setManifest(null);

    try {
      const result = await checkForUpdates();
      setCheckResult(result);
      setLastChecked(new Date().toLocaleTimeString());

      if (result.error) {
        setPhase("error");
        setError(result.error);
      } else if (result.update_available && result.manifest) {
        setPhase("available");
        setManifest(result.manifest);
      } else {
        setPhase("up-to-date");
      }
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  // ── Online download + install ─────────────────────────────────

  const handleDownloadAndInstall = useCallback(async () => {
    if (!manifest) return;
    setPhase("downloading");
    setProgress(null);
    setError("");

    try {
      const result = await downloadAndInstallUpdate(manifest);
      if (result.success) {
        setPhase("done");
        if (result.needs_restart) {
          // Give user a moment to read the message before app restarts
          setTimeout(() => {
            window.location.reload();
          }, 3000);
        }
      } else {
        setPhase("error");
        setError(result.message);
      }
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [manifest]);

  // ── Offline update ────────────────────────────────────────────

  const handlePickOfflineFile = useCallback(async () => {
    setError("");
    try {
      const path = await pickUpdateFile();
      if (!path) return;

      setOfflinePath(path);
      setPhase("checking");

      const meta = await readOfflinePackage(path);
      setOfflineMeta(meta);
      setPhase("offline-preview");
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : String(err));
      setOfflineMeta(null);
      setOfflinePath(null);
    }
  }, []);

  const handleInstallOffline = useCallback(async () => {
    if (!offlinePath) return;
    setPhase("offline-installing");
    setError("");

    try {
      const result = await installOfflineUpdate(offlinePath);
      if (result.success) {
        setPhase("done");
        if (result.needs_restart) {
          setTimeout(() => {
            window.location.reload();
          }, 3000);
        }
      } else {
        setPhase("error");
        setError(result.message);
      }
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [offlinePath]);

  // ── Cleanup ───────────────────────────────────────────────────

  const handleCleanup = useCallback(async () => {
    try {
      await cleanupUpdates();
    } catch {
      /* non-fatal */
    }
  }, []);

  // ── Format helpers ────────────────────────────────────────────

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const inTauri = isTauri();

  return (
    <Section title="Updates" icon={<ArrowUpCircle size={18} />}>
      {/* Version info */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 500 }}>
            Current version: <span style={{ fontFamily: "monospace" }}>{currentVersion}</span>
          </div>
          {lastChecked && (
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
              Last checked: {lastChecked}
            </div>
          )}
        </div>
      </div>

      {/* ── Online update section ── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
          <Download size={14} /> Online update
        </div>

        {phase === "idle" && (
          <button
            className="btn-primary"
            onClick={handleCheckForUpdates}
            disabled={!inTauri}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <RefreshCw size={14} /> Check for updates
          </button>
        )}

        {phase === "checking" && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-muted)", fontSize: 13 }}>
            <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} />
            Checking for updates…
          </div>
        )}

        {phase === "up-to-date" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--accent-success)", fontSize: 13 }}>
              <CheckCircle size={16} /> You're up to date!
              {checkResult?.latest_version && (
                <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                  (v{checkResult.latest_version})
                </span>
              )}
            </div>
            <button
              className="btn-secondary btn-sm"
              onClick={() => { setPhase("idle"); setCheckResult(null); }}
              style={{ alignSelf: "flex-start", display: "flex", alignItems: "center", gap: 4 }}
            >
              <RefreshCw size={12} /> Check again
            </button>
          </div>
        )}

        {phase === "available" && manifest && (
          <div style={{
            background: "var(--bg-primary)",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            padding: 12,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Package size={16} style={{ color: "var(--accent-primary)" }} />
              <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                Version {manifest.version} available
              </span>
              {manifest.mandatory && (
                <span style={{
                  fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 3,
                  background: "rgba(244,67,54,0.15)", color: "var(--accent-danger)",
                }}>
                  Required
                </span>
              )}
            </div>

            {manifest.notes && (
              <div style={{
                fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5,
                marginBottom: 8, maxHeight: 120, overflowY: "auto",
                padding: 8, background: "var(--bg-secondary)", borderRadius: 4,
                whiteSpace: "pre-wrap",
              }}>
                {manifest.notes}
              </div>
            )}

            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 10 }}>
              Size: {formatSize(manifest.size)} · Released: {manifest.pub_date}
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn-primary"
                onClick={handleDownloadAndInstall}
                style={{ display: "flex", alignItems: "center", gap: 6 }}
              >
                <Download size={14} /> Download & Install
              </button>
              <button
                className="btn-secondary btn-sm"
                onClick={() => { setPhase("idle"); setManifest(null); setCheckResult(null); }}
              >
                Later
              </button>
            </div>
          </div>
        )}

        {phase === "downloading" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-muted)", fontSize: 13 }}>
              <Download size={14} style={{ animation: "pulse 1.5s ease-in-out infinite" }} />
              Downloading update…
            </div>
            {progress && (
              <div>
                <div style={{
                  height: 6, borderRadius: 3, background: "var(--bg-primary)",
                  overflow: "hidden", marginBottom: 4,
                }}>
                  <div style={{
                    height: "100%", borderRadius: 3,
                    background: "var(--accent-primary)",
                    width: `${Math.min(progress.percent, 100)}%`,
                    transition: "width 0.3s ease",
                  }} />
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", justifyContent: "space-between" }}>
                  <span>{formatSize(progress.downloaded_bytes)} / {formatSize(progress.total_bytes)}</span>
                  <span>{Math.round(progress.percent)}%</span>
                </div>
              </div>
            )}
          </div>
        )}

        {phase === "done" && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--accent-success)", fontSize: 13 }}>
            <CheckCircle size={16} /> Update installed successfully. Restarting…
          </div>
        )}

        {!inTauri && phase === "idle" && (
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
            Online updates are only available in the desktop app.
          </p>
        )}
      </div>

      {/* ── Divider ── */}
      <div style={{ borderTop: "1px solid var(--border-color)", marginBottom: 16 }} />

      {/* ── Offline update section ── */}
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
          <Upload size={14} /> Offline update
        </div>
        <p style={styles.hint}>
          Install an update from a downloaded package file. Use this when the machine has no internet access.
        </p>

        {phase !== "offline-preview" && phase !== "offline-installing" && (
          <button
            className="btn-secondary"
            onClick={handlePickOfflineFile}
            disabled={!inTauri || phase === "downloading" || phase === "installing" || phase === "checking"}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <Upload size={14} /> Select update package…
          </button>
        )}

        {phase === "offline-preview" && offlineMeta && (
          <div style={{
            background: "var(--bg-primary)",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            padding: 12,
            marginTop: 8,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Package size={16} style={{ color: "var(--accent-primary)" }} />
              <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                Offline package: v{offlineMeta.version}
              </span>
            </div>

            {offlineMeta.notes && (
              <div style={{
                fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5,
                marginBottom: 8, maxHeight: 120, overflowY: "auto",
                padding: 8, background: "var(--bg-secondary)", borderRadius: 4,
                whiteSpace: "pre-wrap",
              }}>
                {offlineMeta.notes}
              </div>
            )}

            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 10 }}>
              Platform: {offlineMeta.platform} · Released: {offlineMeta.pub_date}
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn-primary"
                onClick={handleInstallOffline}
                style={{ display: "flex", alignItems: "center", gap: 6 }}
              >
                <Download size={14} /> Install update
              </button>
              <button
                className="btn-secondary btn-sm"
                onClick={() => {
                  setPhase("idle");
                  setOfflineMeta(null);
                  setOfflinePath(null);
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {phase === "offline-installing" && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-muted)", fontSize: 13, marginTop: 8 }}>
            <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} />
            Installing update…
          </div>
        )}
      </div>

      {/* ── Error display ── */}
      {phase === "error" && error && (
        <div style={{
          display: "flex", alignItems: "flex-start", gap: 8,
          marginTop: 12, padding: 10, borderRadius: 6,
          background: "rgba(244,67,54,0.08)",
          border: "1px solid rgba(244,67,54,0.2)",
        }}>
          <AlertTriangle size={16} style={{ color: "var(--accent-danger)", flexShrink: 0, marginTop: 1 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, color: "var(--accent-danger)", fontWeight: 500 }}>
              Update failed
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
              {error}
            </div>
          </div>
          <button
            onClick={() => { setPhase("idle"); setError(""); }}
            style={{
              background: "none", border: "none", cursor: "pointer",
              color: "var(--text-muted)", fontSize: 12, padding: "2px 6px",
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ── Cleanup link ── */}
      <div style={{ marginTop: 16, borderTop: "1px solid var(--border-color)", paddingTop: 12 }}>
        <button
          onClick={handleCleanup}
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--text-muted)", fontSize: 11, textDecoration: "underline",
            padding: 0,
          }}
        >
          Clear downloaded update cache
        </button>
      </div>

      {/* Inline keyframes for spinner */}
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </Section>
  );
}
