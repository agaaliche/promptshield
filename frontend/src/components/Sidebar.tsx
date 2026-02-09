/** Navigation sidebar. */

import {
  Upload,
  FileSearch,
  ArrowRightLeft,
  Settings,
  Shield,
  FileText,
  Trash2,
} from "lucide-react";
import { useAppStore } from "../store";
import { deleteDocument } from "../api";

type View = "upload" | "viewer" | "detokenize" | "settings";

const NAV_ITEMS: Array<{
  id: View;
  label: string;
  icon: React.ReactNode;
}> = [
  { id: "upload", label: "Upload file", icon: <Upload size={18} /> },
  { id: "viewer", label: "Download secure file", icon: <FileSearch size={18} /> },
  { id: "detokenize", label: "De-tokenize", icon: <ArrowRightLeft size={18} /> },
  { id: "settings", label: "Settings", icon: <Settings size={18} /> },
];

export default function Sidebar() {
  const {
    currentView,
    setCurrentView,
    backendReady,
    statusMessage,
    documents,
    activeDocId,
    setActiveDocId,
    setDocuments,
    setRegions,
  } = useAppStore();

  const handleDelete = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation();
    try {
      await deleteDocument(docId);
      const updated = documents.filter((d) => d.doc_id !== docId);
      setDocuments(updated);
      if (activeDocId === docId) {
        setActiveDocId(null);
        setRegions([]);
        setCurrentView("upload");
      }
    } catch (err) {
      console.error("Failed to delete document:", err);
    }
  };

  return (
    <div style={styles.sidebar}>
      {/* Logo */}
      <div style={styles.logo}>
        <Shield size={22} style={{ color: "var(--accent-primary)" }} />
        <span style={styles.logoText}>prompt<span style={{ color: 'var(--accent-primary)', fontWeight: 700 }}>Shield</span></span>
      </div>

      {/* Nav items */}
      <nav style={styles.nav}>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            style={{
              ...styles.navItem,
              ...(currentView === item.id ? styles.navItemActive : {}),
            }}
            onClick={() => setCurrentView(item.id)}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      {/* Recent documents */}
      {documents.length > 0 && (
        <div style={styles.docsSection}>
          <div style={styles.docsSectionTitle}>Recent Documents</div>
          <div style={styles.docsList}>
            {documents.slice(-5).reverse().map((doc) => (
              <button
                key={doc.doc_id}
                style={{
                  ...styles.docItem,
                  ...(doc.doc_id === activeDocId ? styles.docItemActive : {}),
                }}
                onClick={() => {
                  setActiveDocId(doc.doc_id);
                  setCurrentView("viewer");
                }}
                title={doc.original_filename}
              >
                <FileText size={13} style={{ flexShrink: 0 }} />
                <span style={styles.docName}>{doc.original_filename}</span>
                <span style={styles.docPages}>{doc.page_count}p</span>
                <span
                  style={styles.docDelete}
                  onClick={(e) => handleDelete(e, doc.doc_id)}
                  title="Delete document"
                >
                  <Trash2 size={11} />
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Status */}
      <div style={styles.statusArea}>
        <div style={styles.statusDot(backendReady)} />
        <span style={styles.statusText}>
          {backendReady ? "Backend connected" : "Connecting..."}
        </span>
      </div>

      {statusMessage && (
        <div style={styles.message}>{statusMessage}</div>
      )}
    </div>
  );
}

const styles: Record<string, any> = {
  sidebar: {
    width: 200,
    background: "var(--bg-secondary)",
    borderRight: "1px solid var(--border-color)",
    display: "flex",
    flexDirection: "column",
    flexShrink: 0,
  },
  logo: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "16px 16px 20px",
  },
  logoText: {
    fontSize: 16,
    fontWeight: 500,
    color: "var(--text-primary)",
    letterSpacing: "-0.3px",
  },
  nav: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 2,
    padding: "0 8px",
  },
  navItem: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "8px 12px",
    borderRadius: 6,
    background: "transparent",
    color: "var(--text-secondary)",
    border: "none",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 500,
    transition: "all 0.1s ease",
    width: "100%",
    textAlign: "left" as const,
  },
  navItemActive: {
    background: "var(--bg-tertiary)",
    color: "var(--text-primary)",
  },
  statusArea: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "12px 16px",
    borderTop: "1px solid var(--border-color)",
  },
  statusDot: (connected: boolean) => ({
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: connected ? "var(--accent-success)" : "var(--accent-warning)",
    flexShrink: 0,
  }),
  statusText: {
    fontSize: 11,
    color: "var(--text-muted)",
  },
  message: {
    fontSize: 11,
    color: "var(--text-secondary)",
    padding: "0 16px 12px",
    lineHeight: 1.4,
  },
  docsSection: {
    borderTop: "1px solid var(--border-color)",
    padding: "8px 8px 4px",
  },
  docsSectionTitle: {
    fontSize: 10,
    fontWeight: 600,
    color: "var(--text-muted)",
    textTransform: "uppercase" as const,
    letterSpacing: 0.5,
    padding: "4px 8px 6px",
  },
  docsList: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 1,
    maxHeight: 160,
    overflowY: "auto" as const,
  },
  docItem: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "5px 8px",
    borderRadius: 4,
    background: "transparent",
    color: "var(--text-secondary)",
    border: "none",
    cursor: "pointer",
    fontSize: 11,
    width: "100%",
    textAlign: "left" as const,
    transition: "background 0.1s ease",
  },
  docItemActive: {
    background: "var(--bg-tertiary)",
    color: "var(--text-primary)",
  },
  docName: {
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
  },
  docPages: {
    fontSize: 10,
    color: "var(--text-muted)",
    flexShrink: 0,
  },
  docDelete: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    padding: 2,
    borderRadius: 3,
    color: "var(--text-muted)",
    cursor: "pointer",
    opacity: 0.4,
    transition: "opacity 0.15s ease, color 0.15s ease",
  },
};
