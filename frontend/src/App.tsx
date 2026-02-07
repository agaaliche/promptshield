/** Root application component. */

import { useEffect } from "react";
import { useAppStore } from "./store";
import { checkHealth, getVaultStatus, getLLMStatus } from "./api";
import Sidebar from "./components/Sidebar";
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
          return;
        }
        attempts++;
        await new Promise((r) => setTimeout(r, 1000));
      }
    };

    poll();
    return () => { cancelled = true; };
  }, [setBackendReady, setVaultUnlocked, setLLMStatus]);

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
      <Sidebar />
      <main style={{ flex: 1, overflow: "hidden", position: "relative" }}>
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
