/** Navigation sidebar. */

import { useRef, useCallback, useEffect, useState, useMemo } from "react";
import {
  Upload,
  FileSearch,
  ArrowRightLeft,
  Settings,
  Shield,
  ShieldCheck,
  FileText,
  Trash2,
  ChevronDown,
  ChevronRight,
  Plus,
  FolderOpen,
  FolderUp,
  Search,
  ArrowUpDown,
  X,
} from "lucide-react";
import { useAppStore } from "../store";
import { deleteDocument, uploadDocument, getDocument, detectPII } from "../api";
import { resolveAllOverlaps } from "../regionUtils";
import type { UploadItem } from "../types";

type View = "upload" | "viewer" | "detokenize" | "settings";

const MIN_WIDTH = 160;
const MAX_WIDTH = 400;
const ACCEPT =
  ".pdf,.jpg,.jpeg,.png,.tiff,.tif,.bmp,.webp,.docx,.xlsx,.pptx,.doc,.xls,.ppt";

type SortField = "name" | "pages" | "date";
type SortDir = "asc" | "desc";

export default function Sidebar() {
  const {
    currentView,
    setCurrentView,
    backendReady,
    documents,
    activeDocId,
    setActiveDocId,
    setDocuments,
    setRegions,
    leftSidebarWidth,
    setLeftSidebarWidth,
    addDocument,
    setIsProcessing,
    setStatusMessage,
    isProcessing,
    updateDocument,
    regions: storeRegions,
    uploadQueue,
    addToUploadQueue,
    updateUploadItem,
    clearCompletedUploads,
    setDocDetecting,
    setDocLoadingMessage,
  } = useAppStore();

  const isDragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(200);

  // Accordion state for Protect Files
  const [protectExpanded, setProtectExpanded] = useState(true);
  // Dialogs
  const [showFilesDialog, setShowFilesDialog] = useState(false);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [filesSearch, setFilesSearch] = useState("");
  const [sortField, setSortField] = useState<SortField>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  // Upload drag state
  const [uploadDragging, setUploadDragging] = useState(false);
  const uploadFileRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  // File list height resize
  const [fileListHeight, setFileListHeight] = useState(280);
  const isResizingFileList = useRef(false);
  const fileListStartY = useRef(0);
  const fileListStartH = useRef(280);

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
  useEffect(() => {
    if (uploadQueue.length > 0 || documents.length > 0) {
      setProtectExpanded(true);
    }
  }, [uploadQueue.length, documents.length]);

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

  // Upload handler — supports multiple files with progress tracking
  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      // Snapshot into array — FileList is live and gets cleared when the input resets
      const fileArray = Array.from(files);
      setShowAddDialog(false);
      setProtectExpanded(true);
      setCurrentView("viewer");

      // Build queue items with parent path metadata
      const items: { file: File; item: UploadItem }[] = [];
      for (let i = 0; i < fileArray.length; i++) {
        const file = fileArray[i];
        const relPath = (file as any).webkitRelativePath || "";
        const parentPath = relPath ? relPath.substring(0, relPath.lastIndexOf("/")) : "";
        const id = `upload-${Date.now()}-${i}`;
        items.push({
          file,
          item: { id, name: file.name, parentPath, status: "queued", progress: 0 },
        });
      }

      addToUploadQueue(items.map((i) => i.item));

      // Process sequentially
      for (const { file, item } of items) {
        try {
          updateUploadItem(item.id, { status: "uploading", progress: 30 });
          setDocLoadingMessage("Uploading document\u2026");
          const uploadRes = await uploadDocument(file);

          updateUploadItem(item.id, { progress: 50 });
          setDocLoadingMessage("Processing pages\u2026");
          const doc = await getDocument(uploadRes.doc_id);
          addDocument(doc);
          // Set detecting BEFORE activeDocId so the progress dialog shows immediately
          setDocDetecting(true);
          setDocLoadingMessage("Analyzing document for PII entities\u2026");
          setActiveDocId(doc.doc_id);
          updateUploadItem(item.id, { status: "detecting", progress: 70 });
          const detection = await detectPII(doc.doc_id);
          const resolved = resolveAllOverlaps(detection.regions);
          setRegions(resolved);
          updateDocument(doc.doc_id, { regions: resolved });

          setDocDetecting(false);
          setDocLoadingMessage("");
          updateUploadItem(item.id, { status: "done", progress: 100 });
        } catch (e: any) {
          setDocDetecting(false);
          setDocLoadingMessage("");
          updateUploadItem(item.id, { status: "error", error: e.message || "Failed" });
        }
      }

      clearCompletedUploads();
    },
    [setActiveDocId, setRegions, setCurrentView, addDocument, updateDocument, setShowAddDialog, setProtectExpanded, addToUploadQueue, updateUploadItem, clearCompletedUploads, setDocDetecting, setDocLoadingMessage]
  );

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
    { id: "detokenize", label: "Token Swap", icon: <ArrowRightLeft size={18} /> },
    { id: "settings", label: "Settings", icon: <Settings size={18} /> },
  ];

  return (
    <div style={{ ...sidebarStyles.sidebar, width: leftSidebarWidth }}>
      {/* Logo */}
      <div style={sidebarStyles.logo}>
        <Shield size={22} style={{ color: "var(--accent-primary)" }} />
        <span style={sidebarStyles.logoText}>prompt<span style={{ color: 'var(--accent-primary)', fontWeight: 700 }}>Shield</span></span>
      </div>

      {/* Nav items */}
      <nav style={sidebarStyles.nav}>
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
            <FileSearch size={18} />
            <span style={{ flex: 1 }}>Protect Files</span>
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
                border: "1px solid rgba(255,255,255,0.55)",
                borderRadius: 6,
                paddingBottom: 12,
              }}>
                {/* Upload queue — progress items (hide done items immediately) */}
                {uploadQueue.filter((item) => item.status !== "done").map((item) => (
                  <div key={item.id} style={{ padding: "4px 6px", fontSize: 11 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                      <FileText size={10} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const, color: item.status === "error" ? "#f44336" : "var(--text-secondary)" }}>
                        {item.name}
                      </span>
                      <span style={{ fontSize: 9, color: "var(--text-muted)", flexShrink: 0 }}>
                        {item.status === "queued" ? "Queued" : item.status === "uploading" ? "Uploading" : item.status === "detecting" ? "Detecting" : item.status === "done" ? "Done" : "Error"}
                      </span>
                    </div>
                    {item.parentPath && (
                      <div style={{ fontSize: 9, color: "var(--text-muted)", marginBottom: 2, paddingLeft: 16 }}>
                        {item.parentPath}
                      </div>
                    )}
                    <div style={{ height: 2, background: "rgba(255,255,255,0.1)", borderRadius: 1, overflow: "hidden" }}>
                      <div style={{
                        height: "100%",
                        width: `${item.progress}%`,
                        background: item.status === "error" ? "#f44336" : "rgba(255,255,255,0.7)",
                        borderRadius: 1,
                        transition: "width 0.3s ease",
                      }} />
                    </div>
                  </div>
                ))}

                {recentDocs.length === 0 && uploadQueue.length === 0 ? (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", padding: "10px 8px", textAlign: "center" }}>
                    No files yet
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
                            return <Shield size={12} fill="#4caf50" style={{ flexShrink: 0, color: "#4caf50" }} />;
                          }
                        } else if (doc.is_protected) {
                          return <Shield size={12} fill="#4caf50" style={{ flexShrink: 0, color: "#4caf50" }} />;
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
                  setFileListHeight(Math.max(80, Math.min(600, fileListStartH.current + delta)));
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

            {/* Action buttons: Files / Add */}
            <div style={{
              display: "flex",
              gap: 4,
              padding: "6px 8px",
              background: "rgba(0,0,0,0.15)",
              borderRadius: "0 0 6px 6px",
            }}>
              <button
                className="btn-ghost btn-sm"
                style={{
                  flex: 1, fontSize: 11, padding: "5px 6px", display: "flex", alignItems: "center", justifyContent: "center", gap: 4, border: "1px solid transparent",
                }}
                onClick={() => setShowFilesDialog(true)}
                title="View all files"
              >
                <FolderOpen size={12} /> Files
              </button>
              <button
                className="btn-ghost btn-sm"
                style={{
                  flex: 1, fontSize: 11, padding: "5px 6px", display: "flex", alignItems: "center", justifyContent: "center", gap: 4, border: "1px solid transparent",
                }}
                onClick={() => setShowAddDialog(true)}
                title="Add a new file"
              >
                <Plus size={12} /> Add
              </button>
            </div>
          </div>
        )}
        </div>

        {/* Other nav items */}
        {navItems.map((item) => (
          <button
            key={item.id}
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

      {/* Status */}
      <div style={sidebarStyles.statusArea}>
        <div style={sidebarStyles.statusDot(backendReady)} />
        <span style={sidebarStyles.statusText}>
          {backendReady ? "Local database connected" : "Connecting..."}
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

      {/* ── Add Document Dialog ── */}
      {showAddDialog && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 10000,
          }}
          onClick={() => setShowAddDialog(false)}
        >
          <div
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              borderRadius: 10,
              width: 480,
              maxWidth: "90vw",
              display: "flex",
              flexDirection: "column",
              boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Dialog header */}
            <div style={{ display: "flex", alignItems: "center", padding: "14px 16px", borderBottom: "1px solid var(--border-color)", gap: 10 }}>
              <Upload size={18} style={{ color: "var(--accent-primary)" }} />
              <span style={{ flex: 1, fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>Add Document</span>
              <button
                className="btn-ghost btn-sm"
                onClick={() => setShowAddDialog(false)}
                style={{ padding: 4 }}
              >
                <X size={16} />
              </button>
            </div>

            {/* Upload area */}
            <div style={{ padding: 20 }}>
              <div
                style={{
                  border: `2px dashed ${uploadDragging ? "var(--accent-primary)" : "var(--border-color)"}`,
                  borderRadius: 10,
                  padding: "36px 24px",
                  textAlign: "center",
                  cursor: isProcessing ? "default" : "pointer",
                  background: uploadDragging ? "rgba(74,158,255,0.06)" : "transparent",
                  transition: "all 0.2s ease",
                }}
                onDragOver={(e) => { e.preventDefault(); setUploadDragging(true); }}
                onDragLeave={() => setUploadDragging(false)}
                onDrop={(e) => { e.preventDefault(); setUploadDragging(false); handleFiles(e.dataTransfer.files); }}
                onClick={() => !isProcessing && uploadFileRef.current?.click()}
              >
                <input
                  ref={uploadFileRef}
                  type="file"
                  accept={ACCEPT}
                  multiple
                  style={{ display: "none" }}
                  onChange={(e) => { handleFiles(e.target.files); if (e.target) e.target.value = ""; }}
                />
                <input
                  ref={folderInputRef}
                  type="file"
                  // @ts-expect-error webkitdirectory is non-standard
                  webkitdirectory=""
                  multiple
                  style={{ display: "none" }}
                  onChange={(e) => { handleFiles(e.target.files); if (e.target) e.target.value = ""; }}
                />
                {isProcessing ? (
                  <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>Processing...</div>
                ) : (
                  <>
                    <Upload size={36} style={{ color: "var(--accent-primary)", marginBottom: 12 }} />
                    <div style={{ fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.4, marginBottom: 6 }}>
                      Drag & drop files here, or click to browse
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                      PDF, DOCX, XLSX, PPTX, JPG, PNG, TIFF, BMP
                    </div>
                    <button
                      className="btn-ghost btn-sm"
                      style={{ fontSize: 12, display: "inline-flex", alignItems: "center", gap: 4, padding: "6px 12px", border: "1px solid var(--border-color)", borderRadius: 6 }}
                      onClick={(e) => { e.stopPropagation(); folderInputRef.current?.click(); }}
                    >
                      <FolderUp size={14} /> Upload folder
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Files Dialog (portal-style overlay) ── */}
      {showFilesDialog && (
        <div
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
              minHeight: 350,
              maxHeight: "80vh",
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
              <span style={{ flex: 1, fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>All Documents</span>
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
                  placeholder="Search files..."
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

            {/* Column headers */}
            <div style={{ display: "flex", alignItems: "center", padding: "6px 16px", gap: 8, borderBottom: "1px solid var(--border-color)", fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>
              <span
                style={{ flex: 1, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}
                onClick={() => toggleSort("name")}
              >
                Name {sortField === "name" && <ArrowUpDown size={10} />}
              </span>
              <span
                style={{ width: 50, textAlign: "right", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}
                onClick={() => toggleSort("pages")}
              >
                Pages {sortField === "pages" && <ArrowUpDown size={10} />}
              </span>
              <span
                style={{ width: 80, textAlign: "right", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}
                onClick={() => toggleSort("date")}
              >
                Date {sortField === "date" && <ArrowUpDown size={10} />}
              </span>
              <span style={{ width: 28 }} />
            </div>

            {/* File list */}
            <div style={{ flex: 1, overflowY: "auto", padding: "4px 8px" }}>
              {sortedDocs.length === 0 ? (
                <div style={{ textAlign: "center", padding: 24, color: "var(--text-muted)", fontSize: 13 }}>
                  {documents.length === 0 ? "No documents uploaded yet" : "No matches"}
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
                      title="Delete"
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
