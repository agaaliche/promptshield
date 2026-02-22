/** Multi-select floating toolbar — shown when multiple regions are selected. */

import React from "react";
import {
  Search,
  Trash2,
  X,
  Key,
  ReplaceAll,
  LayerGroup,
} from "../icons";
import { useTranslation } from "react-i18next";
import useDraggableToolbar from "../hooks/useDraggableToolbar";
import {
  batchDeleteRegions,
  batchRegionAction,
  updateRegionLabel,
  logError,
} from "../api";
import type {
  PIIRegion,
  PIIType,
  PIILabelEntry,
  RegionAction,
} from "../types";
import { PII_COLORS } from "../types";

export interface MultiSelectToolbarProps {
  toolbarRef: React.RefObject<HTMLDivElement | null>;
  pos: { x: number; y: number };
  isDragging: boolean;
  startDrag: (e: React.MouseEvent) => void;
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
  handleHighlightAll: (regionId: string, skipUndo?: boolean) => void;
  handleRefreshRegion: (regionId: string, textOnly?: boolean, skipUndo?: boolean) => void;
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
  const { t } = useTranslation();
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
          userSelect: "none",
          cursor: "pointer",
          width: 50,
        }}
      >
        {/* Drag handle header */}
        <div
          onMouseDown={(e) => {
            e.stopPropagation();
            startDrag(e);
          }}
          style={{
            padding: "8px 6px",
            background: "var(--bg-primary)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          <div style={{
            width: 24,
            height: 4,
            background: "#4a9eff",
            borderRadius: 2,
            opacity: 0.5,
          }} />
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
              selectedRegionIds.forEach(id => handleHighlightAll(id, true));
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
              transition: "color 0.15s, background 0.15s, border-color 0.15s",
              aspectRatio: "1",
            }}
            title={t("multiSelect.replaceAllTooltip")}
          >
            <ReplaceAll size={16} variant="light" />
          </button>

          {/* Detect */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              if (!activeDocId || selectedRegionIds.length === 0) return;
              pushUndo();
              selectedRegionIds.forEach(id => handleRefreshRegion(id, false, true));
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
              transition: "color 0.15s, background 0.15s, border-color 0.15s",
              aspectRatio: "1",
            }}
            title={t("multiSelect.detectTooltip")}
          >
            <Search size={16} variant="light" />
          </button>

          {/* Change PII type */}
          <div style={{ position: "relative" }}>
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
                justifyContent: "center",
                gap: 8,
                background: showEditDialog ? "var(--bg-primary)" : "transparent",
                border: "1px solid transparent",
                borderRadius: 4,
                cursor: "pointer",
                color: "var(--text-primary)",
                fontWeight: showEditDialog ? 600 : 400,
                whiteSpace: "nowrap",
                transition: "color 0.15s, background 0.15s, border-color 0.15s",
                aspectRatio: "1",
              }}
              title={t("regions.changePiiType")}
            >
              <LayerGroup size={16} variant="light" />
            </button>
            {showEditDialog && (
              <div
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => e.stopPropagation()}
                style={{
                  position: "absolute",
                  top: 0,
                  left: "100%",
                  marginLeft: 4,
                  zIndex: 100,
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-color)",
                  borderRadius: 6,
                  boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
                  maxHeight: 260,
                  overflowY: "auto",
                  minWidth: 140,
                }}
              >
                {visibleLabels.map((entry) => (
                  <button
                    key={entry.label}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!activeDocId || selectedRegionIds.length === 0) return;
                      pushUndo();
                      const newType = entry.label as PIIType;
                      selectedRegionIds.forEach(id => {
                        updateRegion(activeDocId, id, { pii_type: newType });
                      });
                      // Fire API calls in parallel — propagate sibling updates from each response
                      Promise.all(
                        selectedRegionIds.map(id =>
                          updateRegionLabel(activeDocId, id, entry.label)
                            .then(resp => {
                              for (const item of resp.updated) {
                                updateRegion(activeDocId, item.id, { pii_type: item.pii_type as PIIType });
                              }
                            })
                            .catch(logError("update-label"))
                        )
                      );
                      setShowEditDialog(false);
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      width: "100%",
                      padding: "6px 10px",
                      fontSize: 11,
                      color: "var(--text-primary)",
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      whiteSpace: "nowrap",
                    }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-tertiary)"; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                  >
                    <span style={{
                      width: 8, height: 8, borderRadius: "50%",
                      background: entry.color || PII_COLORS[entry.label] || "#888",
                      flexShrink: 0,
                    }} />
                    {entry.label}
                  </button>
                ))}
              </div>
            )}
          </div>

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
              justifyContent: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
              transition: "color 0.15s, background 0.15s, border-color 0.15s",
              aspectRatio: "1",
            }}
            title={t("multiSelect.clearTooltip")}
          >
            <X size={16} variant="light" />
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
              const ids = [...selectedRegionIds];
              ids.forEach(id => updateRegionAction(activeDocId, id, "TOKENIZE"));
              batchRegionAction(activeDocId, ids, "TOKENIZE").catch(logError("batch-tokenize"));
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--tokenize)",
              whiteSpace: "nowrap",
              transition: "color 0.15s, background 0.15s, border-color 0.15s",
              aspectRatio: "1",
            }}
            title={t("regions.tokenize")}
          >
            <Key size={16} variant="light" />
          </button>

          {/* Remove */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              if (!activeDocId || selectedRegionIds.length === 0) return;
              pushUndo();
              const ids = [...selectedRegionIds];
              ids.forEach(id => updateRegionAction(activeDocId, id, "REMOVE"));
              batchRegionAction(activeDocId, ids, "REMOVE").catch(logError("batch-remove"));
            }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: "var(--danger)",
              whiteSpace: "nowrap",
              transition: "color 0.15s, background 0.15s, border-color 0.15s",
              aspectRatio: "1",
            }}
            title={t("regions.remove")}
          >
            <Trash2 size={16} variant="light" />
          </button>
        </div>
      </div>


    </>
  );
}
