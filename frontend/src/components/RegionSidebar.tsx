/** Region sidebar — displays detected PII regions with actions. */

import React from "react";
import {
  Shield,
  ChevronLeft,
  ChevronRight,
  Key,
  Trash2,
  X,
  Type,
  Search,
  Edit3,
} from "lucide-react";
import { PII_COLORS, type PIIRegion, type RegionAction } from "../types";

interface RegionSidebarProps {
  sidebarRef: React.RefObject<HTMLDivElement | null>;
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  width: number;
  onWidthChange: (w: number) => void;
  pageRegions: PIIRegion[];
  selectedRegionIds: string[];
  activeDocId: string | null;
  pendingCount: number;
  removeCount: number;
  tokenizeCount: number;
  onRegionAction: (id: string, action: RegionAction) => void;
  onClear: (id: string) => void;
  onRefresh: (id: string) => void;
  onHighlightAll: (id: string) => void;
  onToggleSelect: (id: string, multi: boolean) => void;
  onSelect: (ids: string[]) => void;
  pushUndo: () => void;
  removeRegion: (id: string) => void;
  updateRegionAction: (id: string, action: RegionAction) => void;
  batchRegionAction: (docId: string, ids: string[], action: RegionAction) => Promise<any>;
  batchDeleteRegions: (docId: string, ids: string[]) => Promise<any>;
}

const RIGHT_MIN_WIDTH = 200;
const RIGHT_MAX_WIDTH = 600;

export default function RegionSidebar({
  sidebarRef,
  collapsed,
  setCollapsed,
  width,
  onWidthChange,
  pageRegions,
  selectedRegionIds,
  activeDocId,
  pendingCount,
  removeCount,
  tokenizeCount,
  onRegionAction,
  onClear,
  onRefresh,
  onHighlightAll,
  onToggleSelect,
  onSelect,
  pushUndo,
  removeRegion,
  updateRegionAction,
  batchRegionAction,
  batchDeleteRegions,
}: RegionSidebarProps) {
  const isDragging = React.useRef(false);
  const startX = React.useRef(0);
  const startWidth = React.useRef(width);

  const onResizeMouseDown = React.useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    startX.current = e.clientX;
    startWidth.current = width;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [width]);

  React.useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      // Dragging left increases width (sidebar is on the right)
      const delta = startX.current - e.clientX;
      const newWidth = Math.min(RIGHT_MAX_WIDTH, Math.max(RIGHT_MIN_WIDTH, startWidth.current + delta));
      onWidthChange(newWidth);
    };
    const onMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, [onWidthChange]);

  return (
    <div ref={sidebarRef} style={{
      ...styles.sidebar,
      width: collapsed ? 60 : width,
      transition: isDragging.current ? 'none' : 'width 0.2s ease',
    }}>
      {/* Resize handle */}
      {!collapsed && (
        <div
          onMouseDown={onResizeMouseDown}
          style={{
            position: 'absolute',
            left: -3,
            top: 0,
            bottom: 0,
            width: 6,
            cursor: 'col-resize',
            zIndex: 20,
            background: 'transparent',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--accent-primary)')}
          onMouseLeave={(e) => { if (!isDragging.current) e.currentTarget.style.background = 'transparent'; }}
        />
      )}
      {collapsed ? (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '16px 8px',
          gap: 16,
        }}>
          <Shield size={24} color="var(--text-secondary)" />
          <div style={{
            background: 'var(--accent-primary)',
            color: 'white',
            fontSize: 12,
            fontWeight: 600,
            padding: '4px 8px',
            borderRadius: 12,
            minWidth: 32,
            textAlign: 'center',
          }}>
            {pageRegions.length}
          </div>
          <button
            onClick={() => setCollapsed(false)}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              padding: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Expand sidebar"
          >
            <ChevronLeft size={20} />
          </button>
        </div>
      ) : (
        <>
          <div style={{
            ...styles.sidebarTitle,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'rgba(0,0,0,0.15)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Shield size={18} color="var(--text-secondary)" />
              <span>Detected ({pageRegions.length})</span>
            </div>
            <button
              onClick={() => setCollapsed(true)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                padding: 4,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Collapse sidebar"
            >
              <ChevronRight size={16} />
            </button>
          </div>
          {/* Bulk actions toolbar */}
          {pageRegions.length > 0 && (() => {
            const activeRegions = pageRegions.filter(r => r.action !== "CANCEL");
            const allTokenized = activeRegions.length > 0 && activeRegions.every(r => r.action === "TOKENIZE");
            const allRemoved = activeRegions.length > 0 && activeRegions.every(r => r.action === "REMOVE");
            return (
            <div style={{
              padding: "6px 12px",
              borderBottom: "1px solid var(--border-color)",
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}>
              <div style={{ display: "flex", gap: 6 }}>
              <button
                onClick={() => {
                  if (!activeDocId) return;
                  pushUndo();
                  const ids = activeRegions.map(r => r.id);
                  const newAction = allTokenized ? "PENDING" : "TOKENIZE";
                  ids.forEach(id => updateRegionAction(id, newAction));
                  batchRegionAction(activeDocId, ids, newAction).catch(() => {});
                }}
                style={{
                  flex: 1,
                  padding: "5px 0",
                  fontSize: 11,
                  fontWeight: 600,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 4,
                  borderRadius: 4,
                  cursor: "pointer",
                  border: allTokenized ? "1px solid #9c27b0" : "1px solid transparent",
                  background: allTokenized ? "rgba(156,39,176,0.15)" : "transparent",
                  color: "#9c27b0",
                  boxShadow: allTokenized ? "0 0 8px rgba(156,39,176,0.3)" : "none",
                  textShadow: "none",
                  transition: "all 0.15s ease",
                }}
                title={allTokenized ? "Undo tokenize all" : "Tokenize all regions on this page"}
              >
                <Key size={13} />
                Tokenize all
              </button>
              <button
                onClick={() => {
                  if (!activeDocId) return;
                  pushUndo();
                  const ids = activeRegions.map(r => r.id);
                  const newAction = allRemoved ? "PENDING" : "REMOVE";
                  ids.forEach(id => updateRegionAction(id, newAction));
                  batchRegionAction(activeDocId, ids, newAction).catch(() => {});
                }}
                style={{
                  flex: 1,
                  padding: "5px 0",
                  fontSize: 11,
                  fontWeight: 600,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 4,
                  borderRadius: 4,
                  cursor: "pointer",
                  border: allRemoved ? "1px solid #f44336" : "1px solid transparent",
                  background: allRemoved ? "rgba(244,67,54,0.15)" : "transparent",
                  color: "#f44336",
                  boxShadow: allRemoved ? "0 0 8px rgba(244,67,54,0.3)" : "none",
                  textShadow: "none",
                  transition: "all 0.15s ease",
                }}
                title={allRemoved ? "Undo remove all" : "Remove all regions on this page"}
              >
                <Trash2 size={13} />
                Remove all
              </button>
              <button
                onClick={() => {
                  if (!activeDocId) return;
                  pushUndo();
                  const ids = activeRegions.map(r => r.id);
                  ids.forEach(id => removeRegion(id));
                  batchDeleteRegions(activeDocId, ids).catch(() => {});
                }}
                style={{
                  flex: 1,
                  padding: "5px 0",
                  fontSize: 11,
                  fontWeight: 600,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 4,
                  borderRadius: 4,
                  cursor: "pointer",
                  border: "1px solid transparent",
                  background: "transparent",
                  color: "var(--text-secondary)",
                  transition: "all 0.15s ease",
                }}
                title="Clear all regions from this page"
              >
                <X size={13} />
                Clear all
              </button>
              </div>
            </div>
            );
          })()}
          <div style={styles.regionList}>
        {pageRegions.map((r) => (
          <div
            key={r.id}
            style={{
              ...styles.regionItem,
              borderLeftColor: PII_COLORS[r.pii_type] || "#888",
              background:
                selectedRegionIds.includes(r.id)
                  ? "var(--bg-tertiary)"
                  : "var(--bg-surface)",
            }}
            onClick={(e) => onToggleSelect(r.id, e.ctrlKey || e.metaKey)}
          >
            {/* Clear — top-right close button */}
            <button
              className="btn-ghost btn-sm"
              onClick={(e) => {
                e.stopPropagation();
                onClear(r.id);
              }}
              title="Clear — remove from document"
              style={styles.sidebarCloseBtn}
            >
              <X size={14} />
            </button>
            <div style={styles.regionHeader}>
              <span
                style={{
                  ...styles.typeBadge,
                  background: PII_COLORS[r.pii_type] || "#888",
                }}
              >
                {r.pii_type}
              </span>
              <span style={styles.confidence}>
                {Math.round(r.confidence * 100)}%
              </span>
              <span style={styles.sourceTag}>{r.source}</span>
            </div>
            <p style={styles.regionText}>"{r.text}"</p>
            <div style={styles.regionActions}>
              {/* Replace all */}
              <button
                className="btn-ghost btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onHighlightAll(r.id);
                }}
                title="Replace all matching"
                style={styles.sidebarBtn}
              >
                <Type size={13} />
              </button>
              {/* Detect */}
              <button
                className="btn-ghost btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onRefresh(r.id);
                }}
                title="Detect — re-analyze"
                style={styles.sidebarBtn}
              >
                <Search size={13} />
              </button>
              {/* Edit */}
              <button
                className="btn-ghost btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect([r.id]);
                }}
                title="Edit label/content"
                style={styles.sidebarBtn}
              >
                <Edit3 size={13} />
              </button>
              {/* Separator */}
              <div style={{ width: 1, height: 18, background: "rgba(255,255,255,0.15)", margin: "0 2px" }} />

              {/* Tokenize */}
              <button
                className="btn-tokenize btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onRegionAction(r.id, r.action === "TOKENIZE" ? "PENDING" : "TOKENIZE");
                }}
                title={r.action === "TOKENIZE" ? "Undo tokenize" : "Tokenize"}
                style={{
                  ...styles.sidebarBtn,
                  border: r.action === "TOKENIZE" ? "1px solid #9c27b0" : "1px solid transparent",
                  background: r.action === "TOKENIZE" ? "rgba(156,39,176,0.15)" : "transparent",
                  color: "#9c27b0",
                  boxShadow: r.action === "TOKENIZE" ? "0 0 6px rgba(156,39,176,0.3)" : "none",
                  transition: "all 0.15s ease",
                }}
              >
                <Key size={13} />
              </button>
              {/* Remove */}
              <button
                className="btn-danger btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onRegionAction(r.id, r.action === "REMOVE" ? "PENDING" : "REMOVE");
                }}
                title={r.action === "REMOVE" ? "Undo remove" : "Remove"}
                style={{
                  ...styles.sidebarBtn,
                  border: r.action === "REMOVE" ? "1px solid #f44336" : "1px solid transparent",
                  background: r.action === "REMOVE" ? "rgba(244,67,54,0.15)" : "transparent",
                  color: "#f44336",
                  boxShadow: r.action === "REMOVE" ? "0 0 6px rgba(244,67,54,0.3)" : "none",
                  transition: "all 0.15s ease",
                }}
              >
                <Trash2 size={13} />
              </button>
            </div>
            {r.action !== "PENDING" && (
              <div
                style={{
                  ...styles.actionStatus,
                  color:
                    r.action === "REMOVE"
                      ? "var(--accent-danger)"
                      : r.action === "TOKENIZE"
                      ? "var(--accent-tokenize)"
                      : "var(--text-muted)",
                }}
              >
                {r.action === "CANCEL" ? "✕ Dismissed" : `✓ ${r.action}`}
              </div>
            )}
          </div>
        ))}
        {pageRegions.length === 0 && (
          <p style={{ color: "var(--text-muted)", padding: 12, fontSize: 13 }}>
            No PII detected on this page.
          </p>
        )}
          </div>
          {/* Sidebar footer — stats */}
          <div style={{
            padding: "8px 12px",
            borderTop: "1px solid var(--border-color)",
            display: "flex",
            justifyContent: "space-evenly",
            flexShrink: 0,
            background: "rgba(0,0,0,0.15)",
          }}>
            <span style={{ ...styles.statBadge, fontSize: 11, background: "transparent" }}>
              {pendingCount} pending
            </span>
            <span style={{ ...styles.statBadge, fontSize: 11, color: "#f44336", background: "transparent" }}>
              {removeCount} remove
            </span>
            <span style={{ ...styles.statBadge, fontSize: 11, color: "#9c27b0", background: "transparent" }}>
              {tokenizeCount} tokenize
            </span>
          </div>
        </>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    position: "absolute",
    right: 0,
    top: 0,
    bottom: 0,
    width: 320,
    background: "var(--bg-secondary)",
    borderLeft: "1px solid var(--border-color)",
    display: "flex",
    flexDirection: "column",
    zIndex: 10,
  },
  sidebarTitle: {
    fontSize: 14,
    fontWeight: 600,
    padding: "12px 16px",
    borderBottom: "1px solid var(--border-color)",
  },
  regionList: {
    flex: 1,
    overflowY: "auto",
    padding: 8,
  },
  regionItem: {
    position: "relative" as const,
    padding: 10,
    paddingRight: 28,
    marginBottom: 6,
    borderRadius: 6,
    borderLeft: "3px solid",
    cursor: "pointer",
    transition: "background 0.1s ease",
  },
  regionHeader: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginBottom: 4,
  },
  typeBadge: {
    fontSize: 10,
    fontWeight: 600,
    color: "white",
    padding: "1px 6px",
    borderRadius: 3,
    textTransform: "uppercase" as const,
  },
  confidence: {
    fontSize: 11,
    color: "var(--text-muted)",
  },
  sourceTag: {
    fontSize: 10,
    color: "var(--text-muted)",
    background: "var(--bg-primary)",
    padding: "1px 4px",
    borderRadius: 2,
  },
  regionText: {
    fontSize: 12,
    color: "var(--text-secondary)",
    marginBottom: 6,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: 'calc(100% - 60px)',
  },
  regionActions: {
    display: "flex",
    alignItems: "center",
    gap: 2,
  },
  sidebarBtn: {
    padding: "4px 6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "transparent",
    borderRadius: 4,
    cursor: "pointer",
  },
  sidebarCloseBtn: {
    position: "absolute" as const,
    top: 4,
    right: 4,
    padding: 4,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 5,
    cursor: "pointer",
    color: "var(--text-secondary)",
    transition: "opacity 0.15s ease, color 0.15s ease, background 0.15s ease",
  },
  actionStatus: {
    fontSize: 11,
    fontWeight: 500,
    marginTop: 4,
  },
  statBadge: {
    fontSize: 11,
    color: "var(--text-secondary)",
    background: "var(--bg-surface)",
    padding: "2px 8px",
    borderRadius: 4,
  },
};
