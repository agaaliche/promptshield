/** Multi-select floating toolbar — shown when multiple regions are selected. */

import React from "react";
import {
  ChevronLeft,
  ChevronRight,
  Search,
  Edit3,
  Trash2,
  X,
  Key,
  ReplaceAll,
} from "lucide-react";
import useDrag from "../hooks/useDrag";
import {
  batchDeleteRegions,
  setRegionAction,
  updateRegionLabel,
  logError,
} from "../api";
import type {
  PIIRegion,
  PIIType,
  PIILabelEntry,
  RegionAction,
} from "../types";

export interface MultiSelectToolbarProps {
  toolbarRef: React.RefObject<HTMLDivElement | null>;
  pos: { x: number; y: number };
  isDragging: boolean;
  startDrag: (e: React.MouseEvent) => void;
  expanded: boolean;
  setExpanded: (v: boolean) => void;
  selectedRegionIds: string[];
  regions: PIIRegion[];
  activeDocId: string | null;
  activePage: number;
  showEditDialog: boolean;
  setShowEditDialog: (v: boolean) => void;
  multiSelectEditLabel: string;
  setMultiSelectEditLabel: (label: PIIType) => void;
  visibleLabels: PIILabelEntry[];
  frequentLabels: PIILabelEntry[];
  otherLabels: PIILabelEntry[];
  // Callbacks
  pushUndo: () => void;
  handleHighlightAll: (regionId: string) => void;
  handleRefreshRegion: (regionId: string) => void;
  removeRegion: (docId: string, regionId: string) => void;
  updateRegionAction: (docId: string, regionId: string, action: RegionAction) => void;
  updateRegion: (docId: string, regionId: string, patch: Partial<PIIRegion>) => void;
  clearSelection: () => void;
  setStatusMessage: (msg: string) => void;
}

export default function MultiSelectToolbar({
  toolbarRef,
  pos,
  isDragging,
  startDrag,
  expanded,
  setExpanded,
  selectedRegionIds,
  regions: _regions,
  activeDocId,
  activePage: _activePage,
  showEditDialog,
  setShowEditDialog,
  multiSelectEditLabel,
  setMultiSelectEditLabel,
  visibleLabels,
  frequentLabels: _frequentLabels,
  otherLabels: _otherLabels,
  pushUndo,
  handleHighlightAll,
  handleRefreshRegion,
  removeRegion,
  updateRegionAction,
  updateRegion,
  clearSelection: _clearSelection,
  setStatusMessage: _setStatusMessage,
}: MultiSelectToolbarProps) {
  if (selectedRegionIds.length <= 1) return null;

  return (
    <>
      {/* Multi-select toolbar */}
      <div
        ref={toolbarRef}
        data-multi-select-toolbar
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
        style={{
          position: "fixed",
          left: pos.x,
          top: pos.y,
          zIndex: 30,
          background: "var(--bg-secondary)",
          borderRadius: 8,
          boxShadow: "0 2px 12px rgba(0,0,0,0.5)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          cursor: "pointer",
        }}
      >
        {/* Drag handle header */}
        <div
          onMouseDown={(e) => {
            e.stopPropagation();
            startDrag(e);
          }}
          style={{
            padding: "4px 6px",
            background: "var(--bg-primary)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          <div style={{
            width: 24,
            height: 4,
            background: "var(--text-secondary)",
            borderRadius: 2,
            opacity: 0.5,
          }} />
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            style={{
              background: "transparent",
              border: "none",
              padding: 2,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              color: "var(--text-secondary)",
            }}
            title={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>

        {/* Toolbar buttons */}
        <div
          onMouseDown={(e) => e.stopPropagation()}
          style={{ padding: 4, display: "flex", flexDirection: "column", gap: 2 }}
        >
          {/* Replace all */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              if (!activeDocId || selectedRegionIds.length === 0) return;
              pushUndo();
              selectedRegionIds.forEach(id => handleHighlightAll(id));
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
            }}
            title="Replace all matching text"
            className="btn-ghost btn-sm"
          >
            <ReplaceAll size={16} />
            {expanded && "Replace all"}
          </button>

          {/* Detect */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              if (!activeDocId || selectedRegionIds.length === 0) return;
              pushUndo();
              selectedRegionIds.forEach(id => handleRefreshRegion(id));
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
            }}
            title="Re-detect content"
            className="btn-ghost btn-sm"
          >
            <Search size={16} />
            {expanded && "Detect"}
          </button>

          {/* Edit */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              setShowEditDialog(!showEditDialog);
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: showEditDialog ? "var(--bg-primary)" : "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--text-primary)",
              fontWeight: showEditDialog ? 600 : 400,
              whiteSpace: "nowrap",
            }}
            title="Edit label"
            className="btn-ghost btn-sm"
          >
            <Edit3 size={16} />
            {expanded && "Edit"}
          </button>

          {/* Clear */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              if (!activeDocId || selectedRegionIds.length === 0) return;
              pushUndo();
              const ids = [...selectedRegionIds];
              batchDeleteRegions(activeDocId, ids).catch(logError("batch-delete"));
              ids.forEach(id => removeRegion(activeDocId, id));
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
            }}
            title="Clear — remove from document"
            className="btn-ghost btn-sm"
          >
            <X size={16} />
            {expanded && "Clear"}
          </button>

          {/* Separator */}
          <div style={{ height: 1, background: "rgba(255,255,255,0.15)", margin: "2px 4px" }} />

          {/* Tokenize */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              if (!activeDocId || selectedRegionIds.length === 0) return;
              pushUndo();
              selectedRegionIds.forEach(id => {
                setRegionAction(activeDocId, id, "TOKENIZE").catch(logError("set-tokenize"));
                updateRegionAction(activeDocId, id, "TOKENIZE");
              });
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--tokenize)",
              whiteSpace: "nowrap",
            }}
            title="Tokenize"
            className="btn-tokenize btn-sm"
          >
            <Key size={16} />
            {expanded && "Tokenize"}
          </button>

          {/* Remove */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              if (!activeDocId || selectedRegionIds.length === 0) return;
              pushUndo();
              selectedRegionIds.forEach(id => {
                setRegionAction(activeDocId, id, "REMOVE").catch(logError("set-remove"));
                updateRegionAction(activeDocId, id, "REMOVE");
              });
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--danger)",
              whiteSpace: "nowrap",
            }}
            title="Remove"
            className="btn-danger btn-sm"
          >
            <Trash2 size={16} />
            {expanded && "Remove"}
          </button>
        </div>
      </div>

      {/* Multi-select edit dialog */}
      {showEditDialog && (
        <div
          role="dialog"
          aria-label="Edit selected regions"
          style={{
            position: "fixed",
            left: pos.x + 100,
            top: pos.y,
            zIndex: 1000,
            background: "var(--bg-secondary)",
            borderRadius: 8,
            boxShadow: "0 4px 24px rgba(0,0,0,0.6)",
            minWidth: 280,
            maxWidth: 350,
            border: "1px solid var(--border-color)",
            padding: 12,
          }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: "var(--text-primary)" }}>
            Change Label for {selectedRegionIds.length} Regions
          </div>
          <select
            autoFocus
            value={multiSelectEditLabel}
            onChange={(e) => setMultiSelectEditLabel(e.target.value as PIIType)}
            style={{
              width: "100%",
              padding: "6px 8px",
              fontSize: 13,
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 4,
              color: "var(--text-primary)",
              marginBottom: 8,
            }}
          >
            {visibleLabels.map((entry) => (
              <option key={entry.label} value={entry.label}>{entry.label}</option>
            ))}
          </select>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn-primary"
              onClick={() => {
                if (!activeDocId || selectedRegionIds.length === 0) return;
                pushUndo();
                selectedRegionIds.forEach(id => {
                  updateRegion(activeDocId, id, { pii_type: multiSelectEditLabel });
                  updateRegionLabel(activeDocId, id, multiSelectEditLabel).catch(logError("update-label"));
                });
                setShowEditDialog(false);
              }}
              style={{ flex: 1 }}
            >
              Apply
            </button>
            <button
              className="btn-ghost btn-sm"
              onClick={() => setShowEditDialog(false)}
              style={{ flex: 1 }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </>
  );
}
