/** Navigation sidebar. */

import { useRef, useCallback, useEffect, useState, useMemo } from "react";
import {
  FileShield,
  ArrowRightLeft,
  Settings,
  Shield,
  ShieldSolid,
  FileText,
  Trash2,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  Search,
  ArrowUpDown,
  X,
  AlertTriangle,
} from "../icons";
import { useShallow } from "zustand/react/shallow";
import { useDocumentStore, useRegionStore, useUIStore, useConnectionStore, useSidebarStore, useUploadStore, useAppStore } from "../store";
import { deleteDocument } from "../api";
import { useTranslation } from "react-i18next";
import { useDocumentUpload } from "../hooks/useDocumentUpload";
import UserMenu from "./UserMenu";

type View = "upload" | "viewer" | "detokenize" | "settings";

const MIN_WIDTH = 160;
const MAX_WIDTH = 400;

type SortField = "name" | "pages" | "date";
type SortDir = "asc" | "desc";

export default function Sidebar() {
  const { currentView, setCurrentView, isProcessing, setIsProcessing, setStatusMessage } = useUIStore();
  const { documents, activeDocId, setActiveDocId, setDocuments, updateDocument } = useDocumentStore();
  const { setRegions, regions: storeRegions } = useRegionStore();
  const { leftSidebarWidth, setLeftSidebarWidth } = useSidebarStore();
  const { uploadQueue, dismissingErrorUploads } = useUploadStore();
  const { showUploadDialog, setShowUploadDialog } = useAppStore(useShallow((s) => ({ showUploadDialog: s.showUploadDialog, setShowUploadDialog: s.setShowUploadDialog })));
  const { backendReady } = useConnectionStore();
  const { t } = useTranslation();

  const isDragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(200);

  // Accordion state for Protect Files — collapsed on non-viewer views
  const [protectExpanded, setProtectExpanded] = useState(currentView === "viewer" || currentView === "upload");
  // Dialogs
  const [showFilesDialog, setShowFilesDialog] = useState(false);
  const [filesSearch, setFilesSearch] = useState("");
  const [sortField, setSortField] = useState<SortField>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  // File list height resize
  const [fileListHeight, setFileListHeight] = useState(280);
  const isResizingFileList = useRef(false);
  const fileListStartY = useRef(0);
  const fileListStartH = useRef(280);
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    startX.current = e.clientX;
    startWidth.current = leftSidebarWidth;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [leftSidebarWidth]);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth.current + (e.clientX - startX.current)));
      setLeftSidebarWidth(newWidth);
    };
    const onMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [setLeftSidebarWidth]);

  // Auto-expand accordion when files are added (e.g. from UploadView)
  // Only expand when in viewer/upload — not when in settings/detokenize
  useEffect(() => {
    if ((currentView === "viewer" || currentView === "upload") && (uploadQueue.length > 0 || documents.length > 0)) {
      setProtectExpanded(true);
    }
  }, [uploadQueue.length, documents.length, currentView]);

  // Keep is_protected in sync for the active document when regions change
  useEffect(() => {
    if (!activeDocId) return;
    const hasPending = storeRegions.some((r) => r.action === "PENDING");
    const hasResolved = storeRegions.some((r) => r.action === "TOKENIZE" || r.action === "REMOVE");
    const isProtected = !hasPending && hasResolved;
    updateDocument(activeDocId, { is_protected: isProtected });
  }, [storeRegions, activeDocId, updateDocument]);

  const handleDelete = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation();
    try {
      await deleteDocument(docId);
      const updated = documents.filter((d) => d.doc_id !== docId);
      setDocuments(updated);
      if (activeDocId === docId) {
        if (updated.length > 0) {
          // Select the next document (or the last one if we deleted the last item)
          const oldIndex = documents.findIndex((d) => d.doc_id === docId);
          const nextIndex = Math.min(oldIndex, updated.length - 1);
          setActiveDocId(updated[nextIndex].doc_id);
        } else {
          setActiveDocId(null);
          setRegions([]);
          setCurrentView("upload");
          setShowFilesDialog(false);
        }
      }
      if (updated.length === 0) {
        setShowFilesDialog(false);
      }
    } catch (err) {
      console.error("Failed to delete document:", err);
    }
  };

  const handleSelectDoc = (docId: string) => {
    setActiveDocId(docId);
    setCurrentView("viewer");
    setShowFilesDialog(false);
  };

  const handleDeleteAll = async () => {
    try {
      await Promise.all(documents.map((d) => deleteDocument(d.doc_id)));
      setDocuments([]);
      setActiveDocId(null);
      setRegions([]);
      setCurrentView("upload");
      setShowFilesDialog(false);
      setConfirmDeleteAll(false);
    } catch (err) {
      console.error("Failed to delete all documents:", err);
    }
  };

  // Upload handler — shared hook (M5)
  const { handleFiles } = useDocumentUpload({
    onBeforeUpload: () => {
      setShowUploadDialog(false);
      setProtectExpanded(true);
    },
    verboseLoadingMessages: true,
  });

  // Sorted + filtered documents for dialog
  const sortedDocs = useMemo(() => {
    let filtered = documents.filter((d) =>
      d.original_filename.toLowerCase().includes(filesSearch.toLowerCase())
    );
    filtered.sort((a, b) => {
      let cmp = 0;
      if (sortField === "name") cmp = a.original_filename.localeCompare(b.original_filename);
      else if (sortField === "pages") cmp = a.page_count - b.page_count;
      else cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      return sortDir === "asc" ? cmp : -cmp;
    });
    return filtered;
  }, [documents, filesSearch, sortField, sortDir]);

  const recentDocs = documents.slice(-50).reverse().filter((doc) => {
    // Hide docs that are still in the upload queue (shown with progress bar instead)
    const activeUploads = uploadQueue.filter((u) => u.status !== "done");
    return !activeUploads.some((u) => u.name === doc.original_filename);
  });

  const toggleSort = (field: SortField) => {
    if (sortField === field) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortField(field); setSortDir("asc"); }
  };

  const navItems: Array<{ id: View; label: string; icon: React.ReactNode }> = [
    { id: "detokenize", label: t("sidebar.tokenSwap"), icon: <ArrowRightLeft size={18} /> },
    { id: "settings", label: t("sidebar.settings"), icon: <Settings size={18} /> },
  ];

  return (
    <div style={{ ...sidebarStyles.sidebar, width: leftSidebarWidth }} role="navigation" aria-label={t("sidebar.ariaLabel")}>
      {/* Logo */}
      <div style={sidebarStyles.logo}>
        <Shield size={22} style={{ color: "var(--accent-primary)" }} />
        <span style={sidebarStyles.logoText}>prompt<span style={{ color: 'var(--accent-primary)', fontWeight: 700 }}>{t("common.shield")}</span></span>
      </div>

      {/* Nav items */}
      <nav style={sidebarStyles.nav} aria-label={t("sidebar.mainNavigation")}>
        {/* Protect Files — accordion wrapper */}
        <div style={{
          background: (currentView === "viewer" || currentView === "upload") ? "var(--bg-tertiary)" : "transparent",
          borderRadius: 6,
          marginBottom: 2,
        }}>
          <button
            style={{
              ...sidebarStyles.navItem,
              ...((currentView === "viewer" || currentView === "upload") ? sidebarStyles.navItemActive : {}),
              borderRadius: protectExpanded && (documents.length > 0 || uploadQueue.length > 0) ? "6px 6px 0 0" : 6,
            }}
            onClick={() => {
              if (documents.length === 0 && uploadQueue.length === 0) {
                setProtectExpanded(false);
                setCurrentView("upload");
              } else {
                setProtectExpanded(!protectExpanded);
                setCurrentView("viewer");
              }
            }}
          >
            <FileShield size={18} />
            <span style={{ flex: 1 }}>{t("sidebar.protectFiles")}</span>
            {(documents.length > 0 || uploadQueue.length > 0) && (protectExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
          </button>

          {/* Accordion content */}
          {protectExpanded && (documents.length > 0 || uploadQueue.length > 0) && (
            <div style={{
              display: "flex",
              flexDirection: "column",
              gap: 0,
              paddingLeft: 0,
            }}>
            {/* Recent files list */}
              <div style={{
                height: fileListHeight,
                overflowY: "auto",
                padding: "4px",
                margin: "6px 8px 8px 8px",
                background: "var(--bg-secondary)",
                border: "1px solid rgba(255,255,255,0.15)",
                borderRadius: 6,
                paddingBottom: 12,
              }}>
                {/* Upload queue — progress items (hide done items immediately) */}
                {uploadQueue.filter((item) => item.status !== "done").map((item) => (
                  <div key={item.id} style={{
                    padding: "4px 6px",
                    fontSize: 11,
                    transition: item.status === "error" ? "opacity 0.35s ease, transform 0.35s ease, max-height 0.35s ease" : undefined,
                    opacity: item.status === "error" && dismissingErrorUploads ? 0 : 1,
                    transform: item.status === "error" && dismissingErrorUploads ? "translateX(-20px)" : undefined,
                    maxHeight: item.status === "error" && dismissingErrorUploads ? 0 : 80,
                    overflow: "hidden",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                      <FileText size={10} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const, color: item.status === "error" ? "#f44336" : "var(--text-secondary)" }}>
                        {item.name}
                      </span>
                      <span style={{ fontSize: 9, color: "var(--text-muted)", flexShrink: 0 }}>
                        {item.status === "queued" ? t("sidebar.uploadStatus.queued")
                          : item.status === "uploading" && item.ocrPhase === "extracting" ? t("sidebar.uploadStatus.extracting")
                          : item.status === "uploading" && item.ocrPhase === "ocr" ? t("sidebar.uploadStatus.ocr")
                          : item.status === "uploading" ? t("sidebar.uploadStatus.uploading")
                          : item.status === "done" ? t("sidebar.uploadStatus.done") : t("sidebar.uploadStatus.error")}
                      </span>
                    </div>
                    {/* OCR progress detail line */}
                    {item.status === "uploading" && item.ocrMessage && (
                      <div style={{ fontSize: 9, color: "var(--text-muted)", marginBottom: 2, paddingLeft: 16, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const }}>
                        {item.ocrMessage}
                      </div>
                    )}
                    {item.parentPath && (
                      <div style={{ fontSize: 9, color: "var(--text-muted)", marginBottom: 2, paddingLeft: 16 }}>
                        {item.parentPath}
                      </div>
                    )}
                    <div style={{ height: 3, background: "rgba(255,255,255,0.1)", borderRadius: 2, overflow: "hidden" }}>
                      <div style={{
                        height: "100%",
                        width: `${item.progress}%`,
                        background: item.status === "error" ? "#f44336"
                          : item.ocrPhase === "ocr" ? "linear-gradient(90deg, #5b9bd5, #7ec8e3)"
                          : "rgba(255,255,255,0.7)",
                        borderRadius: 2,
                        transition: "width 0.3s ease",
                      }} />
                    </div>
                  </div>
                ))}

                {recentDocs.length === 0 && uploadQueue.length === 0 ? (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", padding: "10px 8px", textAlign: "center" }}>
                    {t("sidebar.noFilesYet")}
                  </div>
                ) : (
                  recentDocs.map((doc) => (
                    <button
                      key={doc.doc_id}
                      style={{
                        ...sidebarStyles.docItem,
                        ...(doc.doc_id === activeDocId ? sidebarStyles.docItemActive : {}),
                      }}
                      onClick={() => handleSelectDoc(doc.doc_id)}
                      title={doc.original_filename}
                    >
                      {(() => {
                        // For active doc, compute live from store regions; otherwise use API-provided flag
                        if (doc.doc_id === activeDocId) {
                          const hasPending = storeRegions.some((r) => r.action === "PENDING");
                          const hasResolved = storeRegions.some((r) => r.action === "TOKENIZE" || r.action === "REMOVE");
                          if (!hasPending && hasResolved) {
                            return <ShieldSolid size={12} fill="#4caf50" style={{ flexShrink: 0, color: "#4caf50" }} />;
                          }
                        } else if (doc.is_protected) {
                          return <ShieldSolid size={12} fill="#4caf50" style={{ flexShrink: 0, color: "#4caf50" }} />;
                        }
                        return <FileText size={12} style={{ flexShrink: 0 }} />;
                      })()}
                      <span style={sidebarStyles.docName}>{doc.original_filename}</span>
                    </button>
                  ))
                )}
              </div>

            {/* Resize handle */}
            <div
              style={{
                height: 6,
                cursor: "row-resize",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 8px",
              }}
              onMouseDown={(e) => {
                e.preventDefault();
                isResizingFileList.current = true;
                fileListStartY.current = e.clientY;
                fileListStartH.current = fileListHeight;
                document.body.style.cursor = "row-resize";
                document.body.style.userSelect = "none";
                const onMove = (ev: MouseEvent) => {
                  if (!isResizingFileList.current) return;
                  const delta = ev.clientY - fileListStartY.current;
                  // Allow expansion up to window height minus space for logo, nav items, user menu, status
                  const maxH = Math.max(200, window.innerHeight - 280);
                  setFileListHeight(Math.max(80, Math.min(maxH, fileListStartH.current + delta)));
                };
                const onUp = () => {
                  isResizingFileList.current = false;
                  document.body.style.cursor = "";
                  document.body.style.userSelect = "";
                  document.removeEventListener("mousemove", onMove);
                  document.removeEventListener("mouseup", onUp);
                };
                document.addEventListener("mousemove", onMove);
                document.addEventListener("mouseup", onUp);
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.1)"; }}
              onMouseLeave={(e) => { if (!isResizingFileList.current) e.currentTarget.style.background = "transparent"; }}
            >
              <div style={{ width: 24, height: 2, borderRadius: 1, background: "rgba(255,255,255,0.25)" }} />
            </div>

            {/* Action button: Manage Files */}
            <div style={{
              display: "flex",
              gap: 4,
              padding: "6px 8px",
              justifyContent: "flex-end",
            }}>
              <button
                className="btn-ghost btn-sm"
                style={{
                  fontSize: 11, padding: "5px 6px", display: "flex", alignItems: "center", gap: 4, border: "1px solid transparent",
                }}
                onClick={() => setShowFilesDialog(true)}
                title={t("sidebar.manageAllFiles")}
              >
                <FolderOpen size={12} /> {t("sidebar.manageFiles")}
              </button>
            </div>
          </div>
        )}
        </div>

        {/* Other nav items */}
        {navItems.map((item) => (
          <button
            key={item.id}
            aria-label={item.label}
            aria-current={currentView === item.id ? "page" : undefined}
            style={{
              ...sidebarStyles.navItem,
              ...(currentView === item.id ? sidebarStyles.navItemActive : {}),
            }}
            onClick={() => { setCurrentView(item.id); setProtectExpanded(false); }}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      {/* User account - bottom */}
      <div style={{ marginBottom: 20 }}>
        <UserMenu />
      </div>

      {/* Connection status */}
      <div style={sidebarStyles.statusArea} role="status" aria-live="polite">
        <div style={sidebarStyles.statusDot(backendReady)} />
        <span style={sidebarStyles.statusText}>
          {backendReady ? t("sidebar.statusConnected") : t("sidebar.statusConnecting")}
        </span>
      </div>

      {/* Resize handle */}
      <div
        onMouseDown={onMouseDown}
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          width: 5,
          height: "100%",
          cursor: "col-resize",
          zIndex: 50,
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--accent-primary)")}
        onMouseLeave={(e) => { if (!isDragging.current) e.currentTarget.style.background = "transparent"; }}
      />

      {/* ── Files Dialog (portal-style overlay) ── */}
      {showFilesDialog && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t("sidebar.documentFiles")}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 10000,
          }}
          onClick={() => setShowFilesDialog(false)}
        >
          <div
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              borderRadius: 10,
              width: 600,
              maxWidth: "90vw",
              height: "70vh",
              display: "flex",
              flexDirection: "column",
              boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
              paddingBottom: 25,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Dialog header */}
            <div style={{ display: "flex", alignItems: "center", padding: "14px 16px", borderBottom: "1px solid var(--border-color)", gap: 10 }}>
              <FolderOpen size={18} style={{ color: "var(--accent-primary)" }} />
              <span style={{ flex: 1, fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>{t("sidebar.allDocuments")}</span>
              {documents.length > 0 && (
                <button
                  className="btn-ghost btn-sm"
                  onClick={() => setConfirmDeleteAll(true)}
                  style={{ padding: "4px 8px", fontSize: 11, display: "flex", alignItems: "center", gap: 4, color: "var(--text-muted)" }}
                  title={t("sidebar.deleteAllTitle")}
                  onMouseEnter={(e) => { e.currentTarget.style.color = "#f44336"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-muted)"; }}
                >
                  <Trash2 size={13} /> {t("sidebar.deleteAll")}
                </button>
              )}
              <button
                className="btn-ghost btn-sm"
                onClick={() => setShowFilesDialog(false)}
                style={{ padding: 4 }}
              >
                <X size={16} />
              </button>
            </div>

            {/* Search bar */}
            <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border-color)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--bg-primary)", borderRadius: 6, padding: "6px 10px", border: "1px solid var(--border-color)" }}>
                <Search size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                <input
                  type="text"
                  placeholder={t("sidebar.searchFiles")}
                  value={filesSearch}
                  onChange={(e) => setFilesSearch(e.target.value)}
                  style={{
                    flex: 1,
                    background: "transparent",
                    border: "none",
                    outline: "none",
                    fontSize: 13,
                    color: "var(--text-primary)",
                  }}
                  autoFocus
                />
                {filesSearch && (
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => setFilesSearch("")}
                    style={{ padding: 2 }}
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            </div>

            {/* Delete All confirmation banner */}
            {confirmDeleteAll && (
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "10px 16px",
                background: "rgba(244, 67, 54, 0.1)",
                borderBottom: "1px solid rgba(244, 67, 54, 0.3)",
                fontSize: 12,
                color: "#f44336",
              }}>
                <AlertTriangle size={14} style={{ flexShrink: 0 }} />
                <span style={{ flex: 1 }}>{t("sidebar.deleteConfirm", { count: documents.length })}</span>
                <button
                  className="btn-ghost btn-sm"
                  onClick={handleDeleteAll}
                  style={{ padding: "4px 10px", fontSize: 11, color: "#f44336", fontWeight: 600, border: "1px solid rgba(244, 67, 54, 0.4)", borderRadius: 4 }}
                >
                  {t("common.confirm")}
                </button>
                <button
                  className="btn-ghost btn-sm"
                  onClick={() => setConfirmDeleteAll(false)}
                  style={{ padding: "4px 8px", fontSize: 11 }}
                >
                  {t("common.cancel")}
                </button>
              </div>
            )}

            {/* Column headers */}
            <div style={{ display: "flex", alignItems: "center", padding: "6px 16px", gap: 8, borderBottom: "1px solid var(--border-color)", fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>
              <span
                style={{ flex: 1, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}
                onClick={() => toggleSort("name")}
              >
                {t("common.name")} {sortField === "name" && <ArrowUpDown size={10} />}
              </span>
              <span
                style={{ width: 50, textAlign: "right", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}
                onClick={() => toggleSort("pages")}
              >
                {t("common.pages")} {sortField === "pages" && <ArrowUpDown size={10} />}
              </span>
              <span
                style={{ width: 80, textAlign: "right", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}
                onClick={() => toggleSort("date")}
              >
                {t("common.date")} {sortField === "date" && <ArrowUpDown size={10} />}
              </span>
              <span style={{ width: 28 }} />
            </div>

            {/* File list */}
            <div style={{ flex: 1, overflowY: "auto", padding: "4px 8px" }}>
              {sortedDocs.length === 0 ? (
                <div style={{ textAlign: "center", padding: 24, color: "var(--text-muted)", fontSize: 13 }}>
                  {documents.length === 0 ? t("sidebar.noDocumentsUploaded") : t("common.noMatches")}
                </div>
              ) : (
                sortedDocs.map((doc) => (
                  <button
                    key={doc.doc_id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "8px 8px",
                      borderRadius: 6,
                      background: doc.doc_id === activeDocId ? "var(--bg-tertiary)" : "transparent",
                      color: doc.doc_id === activeDocId ? "var(--text-primary)" : "var(--text-secondary)",
                      border: "none",
                      cursor: "pointer",
                      fontSize: 13,
                      width: "100%",
                      textAlign: "left" as const,
                      transition: "background 0.1s ease",
                    }}
                    onClick={() => handleSelectDoc(doc.doc_id)}
                    title={doc.original_filename}
                    onMouseEnter={(e) => { if (doc.doc_id !== activeDocId) e.currentTarget.style.background = "var(--bg-tertiary)"; }}
                    onMouseLeave={(e) => { if (doc.doc_id !== activeDocId) e.currentTarget.style.background = "transparent"; }}
                  >
                    <FileText size={14} style={{ flexShrink: 0 }} />
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const }}>
                      {doc.original_filename}
                    </span>
                    <span style={{ width: 50, textAlign: "right", fontSize: 12, color: "var(--text-muted)", flexShrink: 0 }}>
                      {doc.page_count}
                    </span>
                    <span style={{ width: 80, textAlign: "right", fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>
                      {new Date(doc.created_at).toLocaleDateString()}
                    </span>
                    <span
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 28,
                        flexShrink: 0,
                        padding: 4,
                        borderRadius: 4,
                        color: "var(--text-muted)",
                        cursor: "pointer",
                      }}
                      onClick={(e) => handleDelete(e, doc.doc_id)}
                      title={t("common.delete")}
                      onMouseEnter={(e) => { e.currentTarget.style.color = "#f44336"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-muted)"; }}
                    >
                      <Trash2 size={13} />
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const sidebarStyles: Record<string, any> = {
  sidebar: {
    position: "relative" as const,
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
    overflowY: "auto" as const,
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
  docItem: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "4px 8px",
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
