/** Root application component. */

import { useEffect, Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { useAppStore } from "./store";

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
import { checkHealth, getVaultStatus, getLLMStatus, listDocuments, getRegions, getDocument, logError } from "./api";
import { resolveAllOverlaps } from "./regionUtils";
import Sidebar from "./components/Sidebar";
import Snackbar from "./components/Snackbar";
import UploadView from "./components/UploadView";
import DocumentViewer from "./components/DocumentViewer";
import DetokenizeView from "./components/DetokenizeView";
import SettingsView from "./components/SettingsView";

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
  } = useAppStore();

  // Poll for backend readiness on startup
  useEffect(() => {
    let cancelled = false;
    let attempts = 0;

    const poll = async () => {
      while (!cancelled && attempts < 60) {
        const ok = await checkHealth();
        if (ok && !cancelled) {
          setBackendReady(true);
          // Load initial status
          getVaultStatus()
            .then((s) => setVaultUnlocked(s.unlocked))
            .catch(logError("vault-status"));
          getLLMStatus().then(setLLMStatus).catch(logError("llm-status"));

          // Load persisted documents and sync Zustand state with backend
          try {
            const docs = await listDocuments();
            if (cancelled) return;

            const backendDocIds = new Set(docs.map((d) => d.doc_id));
            const state = useAppStore.getState();

            if (docs.length > 0) {
              setDocuments(docs);
              // If activeDocId is stale (not on backend), reset it
              if (state.activeDocId && !backendDocIds.has(state.activeDocId)) {
                setActiveDocId(docs[0].doc_id);
              } else if (!state.activeDocId) {
                setActiveDocId(docs[0].doc_id);
              }
              setCurrentView("viewer");
            } else {
              // Backend has no documents — clear any stale HMR state
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
          return;
        }
        attempts++;
        await new Promise((r) => setTimeout(r, 1000));
      }
    };

    poll();
    return () => { cancelled = true; };
  }, [setBackendReady, setVaultUnlocked, setLLMStatus, setDocuments, setActiveDocId, setCurrentView, setRegions]);

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
      <Sidebar />
      <main style={{ flex: 1, overflow: "hidden", position: "relative", minHeight: 0, height: "100%" }}>
        {!backendReady ? (
          <div style={styles.connecting}>
            <div style={styles.spinner} />
            <p>Connecting to local database...</p>
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
