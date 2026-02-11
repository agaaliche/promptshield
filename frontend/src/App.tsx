/** Root application component. */

import { useEffect, useState, Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { useAppStore } from "./store";
import { validateLocalLicense, startBackend, getMe } from "./licenseApi";
import type { LicenseStatus as LicenseStatusType } from "./types";

// ── Error Boundary ──────────────────────────────────────────────
interface EBProps { children: ReactNode }
interface EBState { hasError: boolean; error: Error | null }

class ErrorBoundary extends Component<EBProps, EBState> {
  state: EBState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): EBState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 32, textAlign: "center", color: "var(--text-secondary)" }}>
          <h2 style={{ color: "var(--text-primary)", marginBottom: 8 }}>Something went wrong</h2>
          <p style={{ fontSize: 13, marginBottom: 16 }}>{this.state.error?.message}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: "8px 16px",
              background: "var(--accent-primary)",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
import { checkHealth, getVaultStatus, getLLMStatus, listDocuments, getRegions, getDocument, logError, setBaseUrl } from "./api";
import { resolveAllOverlaps } from "./regionUtils";
import Sidebar from "./components/Sidebar";
import Snackbar from "./components/Snackbar";
import UploadView from "./components/UploadView";
import DocumentViewer from "./components/DocumentViewer";
import DetokenizeView from "./components/DetokenizeView";
import SettingsView from "./components/SettingsView";
import AuthScreen from "./components/AuthScreen";
import RevalidationDialog from "./components/RevalidationDialog";

function App() {
  const {
    currentView,
    setCurrentView,
    setBackendReady,
    setVaultUnlocked,
    setLLMStatus,
    backendReady,
    setDocuments,
    setRegions,
    updateDocument,
    activeDocId,
    setActiveDocId,
    setDocLoading,
    setDocLoadingMessage,
    licenseStatus,
    setLicenseStatus,
    licenseChecked,
    setLicenseChecked,
    authTokens,
    addSnackbar,
  } = useAppStore();

  const [showRevalidation, setShowRevalidation] = useState(false);
  const [backendStarting, setBackendStarting] = useState(false);

  // ── Step 1: Check license on mount ──────────────────────────
  useEffect(() => {
    let cancelled = false;

    const checkLicense = async () => {
      try {
        const status: LicenseStatusType = await validateLocalLicense();
        if (cancelled) return;
        setLicenseStatus(status);
        setLicenseChecked(true);

        // If license is valid but expiring soon, prompt revalidation
        if (status.valid && status.days_remaining !== null && status.days_remaining <= 7) {
          setShowRevalidation(true);
        }
      } catch {
        // Not running in Tauri (browser dev) — skip license check
        if (!cancelled) {
          setLicenseStatus({ valid: true, payload: null, error: null, days_remaining: null });
          setLicenseChecked(true);
        }
      }
    };

    checkLicense();
    return () => { cancelled = true; };
  }, [setLicenseStatus, setLicenseChecked]);

  // Restore user info from saved tokens
  useEffect(() => {
    if (authTokens && licenseStatus?.valid) {
      getMe().catch(() => {});
    }
  }, [authTokens, licenseStatus?.valid]);

  // ── Step 2: Start backend once license is valid ─────────────
  useEffect(() => {
    if (!licenseChecked || !licenseStatus?.valid) return;
    let cancelled = false;

    const launch = async () => {
      setBackendStarting(true);
      try {
        const port = await startBackend();
        if (cancelled) return;
        // Set the API base URL to the sidecar port
        setBaseUrl(`http://127.0.0.1:${port}`);
        setBackendReady(true);
      } catch (err: any) {
        if (cancelled) return;
        // Fallback: try polling for existing backend
        console.warn("startBackend failed, falling back to polling:", err.message);
        pollForBackend(cancelled);
      } finally {
        if (!cancelled) setBackendStarting(false);
      }
    };

    const pollForBackend = async (wasCancelled: boolean) => {
      let attempts = 0;
      while (!wasCancelled && attempts < 60) {
        const ok = await checkHealth();
        if (ok && !wasCancelled) {
          setBackendReady(true);
          return;
        }
        attempts++;
        await new Promise((r) => setTimeout(r, 1000));
      }
    };

    launch();
    return () => { cancelled = true; };
  }, [licenseChecked, licenseStatus?.valid, setBackendReady]);

  // ── Step 3: Load initial data once backend is ready ─────────
  useEffect(() => {
    if (!backendReady) return;
    let cancelled = false;

    const init = async () => {
      getVaultStatus()
        .then((s) => setVaultUnlocked(s.unlocked))
        .catch(logError("vault-status"));
      getLLMStatus().then(setLLMStatus).catch(logError("llm-status"));

      try {
        const docs = await listDocuments();
        if (cancelled) return;

        const backendDocIds = new Set(docs.map((d) => d.doc_id));
        const state = useAppStore.getState();

        if (docs.length > 0) {
          setDocuments(docs);
          if (state.activeDocId && !backendDocIds.has(state.activeDocId)) {
            setActiveDocId(docs[0].doc_id);
          } else if (!state.activeDocId) {
            setActiveDocId(docs[0].doc_id);
          }
          setCurrentView("viewer");
        } else {
          setDocuments([]);
          if (state.activeDocId) {
            setActiveDocId(null);
            setRegions([]);
          }
          setCurrentView("upload");
        }
      } catch {
        // Storage may be empty — that's fine
      }
    };

    init();
    return () => { cancelled = true; };
  }, [backendReady, setVaultUnlocked, setLLMStatus, setDocuments, setActiveDocId, setCurrentView, setRegions]);

  // Load full document data + regions when the active document changes
  useEffect(() => {
    if (!activeDocId) return;

    let cancelled = false;

    // Signal loading start
    setDocLoading(true);
    setDocLoadingMessage("Fetching document data…");

    // Fetch full document (with pages array) and regions in parallel
    Promise.all([
      getDocument(activeDocId),
      getRegions(activeDocId),
    ])
      .then(([fullDoc, regions]) => {
        if (cancelled || useAppStore.getState().activeDocId !== activeDocId) return;
        setDocLoadingMessage("Processing pages…");
        // Merge full document data (pages, mime_type, etc.) into the store entry
        updateDocument(activeDocId, fullDoc);
        setDocLoadingMessage("Loading regions…");
        setRegions(resolveAllOverlaps(regions));
      })
      .catch((err) => {
        if (cancelled) return;
        // Document no longer exists on the backend (e.g. server restart) —
        // remove it from the local list and fall back to the upload view.
        const state = useAppStore.getState();
        const remaining = state.documents.filter((d) => d.doc_id !== activeDocId);
        setDocuments(remaining);
        if (remaining.length > 0) {
          setActiveDocId(remaining[0].doc_id);
        } else {
          setActiveDocId(null);
          setRegions([]);
          setCurrentView("upload");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setDocLoading(false);
          // Don't clear message if detection is in progress — Sidebar manages it
          if (!useAppStore.getState().docDetecting) {
            setDocLoadingMessage("");
          }
        }
      });

    return () => { cancelled = true; };
  }, [activeDocId, setRegions, updateDocument, setDocLoading, setDocLoadingMessage, setDocuments, setActiveDocId, setCurrentView]);

  // ── Auth gate: show AuthScreen if no valid license ──────────
  if (!licenseChecked) {
    return (
      <div style={styles.connecting}>
        <div style={styles.spinner} />
        <p>Checking license...</p>
      </div>
    );
  }

  if (!licenseStatus?.valid) {
    return <AuthScreen />;
  }

  const renderView = () => {
    switch (currentView) {
      case "upload":
        return <UploadView />;
      case "viewer":
        return <DocumentViewer />;
      case "detokenize":
        return <DetokenizeView />;
      case "settings":
        return <SettingsView />;
    }
  };

  return (
    <div style={{ display: "flex", height: "100vh", width: "100vw" }}>
      <Snackbar />
      {showRevalidation && (
        <RevalidationDialog
          daysRemaining={licenseStatus.days_remaining}
          onDismiss={() => setShowRevalidation(false)}
        />
      )}
      <Sidebar />
      <main style={{ flex: 1, overflow: "hidden", position: "relative", minHeight: 0, height: "100%" }}>
        {!backendReady ? (
          <div style={styles.connecting}>
            <div style={styles.spinner} />
            <p>{backendStarting ? "Starting backend..." : "Connecting to local database..."}</p>
            <p style={styles.hint}>
              Make sure the Python sidecar is running on port 8910
            </p>
          </div>
        ) : (
          <ErrorBoundary>
            {renderView()}
          </ErrorBoundary>
        )}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  connecting: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    gap: 16,
    color: "var(--text-secondary)",
  },
  spinner: {
    width: 40,
    height: 40,
    border: "3px solid var(--border-color)",
    borderTopColor: "var(--accent-primary)",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  hint: {
    fontSize: 12,
    color: "var(--text-muted)",
  },
};

export default App;
