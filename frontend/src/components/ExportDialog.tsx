/**
 * Export dialog — lets users select documents (up to 50) with checkboxes
 * and export them as anonymized PDFs. Multiple files → zip archive.
 */

import { useState, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Shield, X, Search, FileText, Download, Package } from "../icons";
import { useAppStore } from "../store";
import { toErrorMessage } from "../errorUtils";
import { exportToDownloads, syncRegions } from "../api";
import type { ExportSaveResult } from "../api";
import type { DocumentInfo } from "../types";
import { Z_TOP_DIALOG } from "../zIndex";
import ExportProgressDialog from "./ExportProgressDialog";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ExportDialog({ open, onClose }: Props) {
  const { t } = useTranslation();
  const documents = useAppStore((s) => s.documents);
  const regions = useAppStore((s) => s.regions);
  const activeDocId = useAppStore((s) => s.activeDocId);
  const setStatusMessage = useAppStore((s) => s.setStatusMessage);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => {
    // Pre-select the active document
    return new Set(activeDocId ? [activeDocId] : []);
  });
  const [search, setSearch] = useState("");
  const [isExporting, setIsExporting] = useState(false);
  const [exportId, setExportId] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<ExportSaveResult | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  // Filter & sort docs
  const filteredDocs = useMemo(() => {
    let filtered = documents.filter((d) =>
      d.original_filename.toLowerCase().includes(search.toLowerCase())
    );
    // Protected docs first, then alphabetically
    filtered.sort((a, b) => {
      const ap = a.is_protected ? 0 : 1;
      const bp = b.is_protected ? 0 : 1;
      if (ap !== bp) return ap - bp;
      return a.original_filename.localeCompare(b.original_filename);
    });
    return filtered;
  }, [documents, search]);

  const toggleDoc = useCallback((docId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        if (next.size >= 50) return prev; // max 50
        next.add(docId);
      }
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    const ids = filteredDocs.slice(0, 50).map((d) => d.doc_id);
    setSelectedIds(new Set(ids));
  }, [filteredDocs]);

  const selectNone = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const doExport = useCallback(async () => {
    if (selectedIds.size === 0) return;

    // Generate a unique export tracking ID
    const eid = `export-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setExportId(eid);
    setExportResult(null);
    setExportError(null);
    setIsExporting(true);

    try {
      // Sync current document's regions before export
      if (activeDocId && selectedIds.has(activeDocId) && regions.length > 0) {
        await syncRegions(
          activeDocId,
          regions.map((r) => ({ id: r.id, action: r.action, bbox: r.bbox })),
        );
      }

      const docIds = Array.from(selectedIds);
      const result = await exportToDownloads(docIds, eid);

      setExportResult(result);
      setStatusMessage(t("exportDialog.exportSuccess", { count: docIds.length }));
    } catch (e: unknown) {
      setExportError(toErrorMessage(e));
      setStatusMessage(t("exportDialog.exportFailed", { error: toErrorMessage(e) }));
    } finally {
      setIsExporting(false);
    }
  }, [selectedIds, activeDocId, regions, setStatusMessage]);

  const handleCloseAll = useCallback(() => {
    setExportId(null);
    setExportResult(null);
    setExportError(null);
    onClose();
  }, [onClose]);

  const handleExport = useCallback(async () => {
    await doExport();
  }, [doExport]);

  if (!open) return null;

  // When exporting or showing results, render the unified progress dialog
  if (isExporting || exportResult || exportError) {
    return (
      <ExportProgressDialog
        exportId={exportId}
        visible
        exportResult={exportResult}
        onClose={handleCloseAll}
      />
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="export-dialog-title"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: Z_TOP_DIALOG,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
          borderRadius: 10,
          width: 520,
          maxWidth: "90vw",
          minHeight: 350,
          maxHeight: "80vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", padding: "14px 16px", borderBottom: "1px solid var(--border-color)", gap: 10 }}>
          <Shield size={18} style={{ color: "#4caf50" }} />
          <span id="export-dialog-title" style={{ flex: 1, fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>
            {t("exportDialog.title")}
          </span>
          <button className="btn-ghost btn-sm" onClick={onClose} style={{ padding: 4 }} aria-label={t("exportDialog.closeAriaLabel")}>
            <X size={16} />
          </button>
        </div>

        {/* Search bar */}
        <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border-color)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--bg-primary)", borderRadius: 6, padding: "6px 10px", border: "1px solid var(--border-color)" }}>
            <Search size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
            <input
              type="text"
              placeholder={t("exportDialog.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
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
          </div>
          {/* Select all / none */}
          <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 11, color: "var(--text-muted)" }}>
            <span
              onClick={selectAll}
              style={{ cursor: "pointer", textDecoration: "underline" }}
            >
              {t("common.selectAll")}
            </span>
            <span
              onClick={selectNone}
              style={{ cursor: "pointer", textDecoration: "underline" }}
            >
              {t("common.selectNone")}
            </span>
            <span style={{ marginLeft: "auto" }}>
              {t("exportDialog.nOfSelected", { selected: selectedIds.size, total: documents.length })}
              {selectedIds.size >= 50 && <span style={{ color: "#ff9800" }}> {t("exportDialog.maxFiles")}</span>}
            </span>
          </div>
        </div>

        {/* File list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
          {filteredDocs.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
              {t("exportDialog.noDocumentsFound")}
            </div>
          ) : (
            filteredDocs.map((doc) => (
              <label
                key={doc.doc_id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "7px 16px",
                  cursor: "pointer",
                  background: selectedIds.has(doc.doc_id) ? "rgba(74, 158, 255, 0.08)" : "transparent",
                  borderLeft: selectedIds.has(doc.doc_id) ? "2px solid var(--accent-primary)" : "2px solid transparent",
                  transition: "background 0.1s",
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedIds.has(doc.doc_id)}
                  onChange={() => toggleDoc(doc.doc_id)}
                  style={{ accentColor: "var(--accent-primary)", flexShrink: 0 }}
                />
                {doc.is_protected ? (
                  <Shield size={14} style={{ color: "#4caf50", flexShrink: 0 }} fill="#4caf50" />
                ) : (
                  <FileText size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                )}
                <span style={{
                  flex: 1,
                  fontSize: 13,
                  color: "var(--text-primary)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}>
                  {doc.original_filename}
                </span>
                <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>
                  {doc.page_count}p
                </span>
              </label>
            ))
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "12px 16px",
          borderTop: "1px solid var(--border-color)",
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: "rgba(0,0,0,0.15)",
          borderRadius: "0 0 10px 10px",
        }}>
          {selectedIds.size > 1 && (
            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--text-muted)" }}>
              <Package size={12} />
              {t("exportDialog.exportsAsZip")}
            </div>
          )}
          <div style={{ flex: 1 }} />
          <button
            className="btn-ghost btn-sm"
            onClick={onClose}
            style={{ marginRight: 4 }}
          >
            {t("common.cancel")}
          </button>
          <button
            className="btn-success"
            onClick={handleExport}
            disabled={selectedIds.size === 0 || isExporting}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <Download size={14} />
            {isExporting
              ? t("exportDialog.exporting")
              : t("exportDialog.exportNFiles", { count: selectedIds.size })}
          </button>
        </div>
      </div>
    </div>
  );
}
