/** Root application component. */

import { useEffect } from "react";
import { useAppStore } from "./store";
import { checkHealth, getVaultStatus, getLLMStatus, listDocuments, getRegions, getDocument } from "./api";
import Sidebar from "./components/Sidebar";
import Snackbar from "./components/Snackbar";
import UploadView from "./components/UploadView";
import DocumentViewer from "./components/DocumentViewer";
import DetokenizeView from "./components/DetokenizeView";
import SettingsView from "./components/SettingsView";

function App() {
  const {
    currentView,
    setBackendReady,
    setVaultUnlocked,
    setLLMStatus,
    backendReady,
    setDocuments,
    setRegions,
    updateDocument,
    activeDocId,
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
            .catch(() => {});
          getLLMStatus().then(setLLMStatus).catch(() => {});

          // Load persisted documents
          try {
            const docs = await listDocuments();
            if (!cancelled && docs.length > 0) {
              setDocuments(docs);
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
  }, [setBackendReady, setVaultUnlocked, setLLMStatus, setDocuments]);

  // Load full document data + regions when the active document changes
  useEffect(() => {
    if (!activeDocId) return;

    let cancelled = false;

    // Fetch full document (with pages array) and regions in parallel
    Promise.all([
      getDocument(activeDocId),
      getRegions(activeDocId),
    ])
      .then(([fullDoc, regions]) => {
        if (cancelled || useAppStore.getState().activeDocId !== activeDocId) return;
        // Merge full document data (pages, mime_type, etc.) into the store entry
        updateDocument(activeDocId, fullDoc);
        setRegions(regions);
      })
      .catch(() => {});

    return () => { cancelled = true; };
  }, [activeDocId, setRegions, updateDocument]);

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
            <p>Connecting to backend...</p>
            <p style={styles.hint}>
              Make sure the Python sidecar is running on port 8910
            </p>
          </div>
        ) : (
          renderView()
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
