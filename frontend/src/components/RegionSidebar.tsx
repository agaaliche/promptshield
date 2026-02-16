/** Region sidebar — displays detected PII regions with actions. */

import React from "react";
import {
  Shield,
  ChevronLeft,
  ChevronRight,
  Key,
  Trash2,
  X,
  ReplaceAll,
  Search,
  Edit3,
  MoreVertical,
  ChevronDown,
} from "lucide-react";
import { PII_COLORS, type PIIRegion, type RegionAction } from "../types";
import { logError } from "../api";
import { useSidebarStore } from "../store";

type SidebarTab = "page" | "document";

interface RegionSidebarProps {
  sidebarRef: React.RefObject<HTMLDivElement | null>;
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  width: number;
  onWidthChange: (w: number) => void;
  pageRegions: PIIRegion[];
  allRegions: PIIRegion[];
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
  onNavigateToRegion: (region: PIIRegion) => void;
  pushUndo: () => void;
  removeRegion: (id: string) => void;
  updateRegionAction: (id: string, action: RegionAction) => void;
  batchRegionAction: (docId: string, ids: string[], action: RegionAction) => Promise<any>;
  batchDeleteRegions: (docId: string, ids: string[]) => Promise<any>;
  onTypeFilterChange?: (enabledTypes: Set<string> | null) => void;
  hideResizeHandle?: boolean;
}

const RIGHT_MIN_WIDTH = 200;
const RIGHT_MAX_WIDTH = 600;

export default function RegionSidebar({
  sidebarRef,
  collapsed,
  setCollapsed,
  width,
  hideResizeHandle,
  onWidthChange,
  pageRegions,
  allRegions,
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
  onNavigateToRegion,
  pushUndo,
  removeRegion,
  updateRegionAction,
  batchRegionAction,
  batchDeleteRegions,
  onTypeFilterChange,
}: RegionSidebarProps) {
  const [activeTab, setActiveTab] = React.useState<SidebarTab>("page");
  const [typeFilterOpen, setTypeFilterOpen] = React.useState(false);
  const [enabledTypes, setEnabledTypes] = React.useState<Set<string> | null>(null); // null = all
  const filterRef = React.useRef<HTMLDivElement>(null);
  const lastClickedIndexRef = React.useRef<number | null>(null);
  const [clearConfirmOpen, setClearConfirmOpen] = React.useState(false);
  const [clearNeverAsk, setClearNeverAsk] = React.useState(false);
  const clearConfirmRef = React.useRef<{ ids: string[] }>({ ids: [] });

  // ── Virtualization: cap rendered items to avoid DOM bloat ──
  const INITIAL_VISIBLE = 100;
  const LOAD_MORE_STEP = 100;
  const [maxVisible, setMaxVisible] = React.useState(INITIAL_VISIBLE);
  // Reset max visible when tab/page/doc changes
  React.useEffect(() => { setMaxVisible(INITIAL_VISIBLE); }, [activeTab, activeDocId, pageRegions]);

  // Close dropdown on outside click
  React.useEffect(() => {
    if (!typeFilterOpen) return;
    const handler = (e: MouseEvent) => {
      if (filterRef.current && !filterRef.current.contains(e.target as Node)) {
        setTypeFilterOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [typeFilterOpen]);

  const tabRegions = activeTab === "page" ? pageRegions : allRegions;
  // Collect all unique types present in current tab regions
  const availableTypes = React.useMemo(() => {
    const types = new Set<string>();
    tabRegions.forEach(r => types.add(r.pii_type));
    return Array.from(types).sort();
  }, [tabRegions]);

  // Filter displayed regions by enabled types
  const displayedRegions = React.useMemo(() => {
    if (!enabledTypes) return tabRegions; // null = show all
    return tabRegions.filter(r => enabledTypes.has(r.pii_type));
  }, [tabRegions, enabledTypes]);

  // Notify parent of type filter changes so overlays stay in sync
  React.useEffect(() => {
    onTypeFilterChange?.(enabledTypes);
  }, [enabledTypes, onTypeFilterChange]);

  const toggleType = (type: string) => {
    setEnabledTypes(prev => {
      // If null (all), start from all available minus the toggled one
      if (!prev) {
        const next = new Set(availableTypes);
        next.delete(type);
        return next;
      }
      const next = new Set(prev);
      if (next.has(type)) {
        // Prevent unchecking the last remaining type
        if (next.size <= 1) return prev;
        next.delete(type);
      } else {
        next.add(type);
      }
      // If all types re-enabled, reset to null
      if (next.size === availableTypes.length) return null;
      return next;
    });
  };

  const allTypesEnabled = enabledTypes === null || enabledTypes.size === availableTypes.length;

  const { setIsSidebarDragging, isSidebarDragging: sidebarDragging } = useSidebarStore();
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
    setIsSidebarDragging(true);
  }, [width, setIsSidebarDragging]);

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
      setIsSidebarDragging(false);
    };
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, [onWidthChange, setIsSidebarDragging]);

  return (
    <div ref={sidebarRef} style={{
      ...styles.sidebar,
      width: collapsed ? 60 : width,
      transition: sidebarDragging ? 'none' : 'width 0.2s ease',
    }}>
      {/* Resize handle */}
      {!collapsed && !hideResizeHandle && (
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
          padding: '12px 8px',
          gap: 12,
        }}>
          <button
            onClick={() => setCollapsed(false)}
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
            title="Expand sidebar"
          >
            <ChevronLeft size={18} />
          </button>
          <Shield size={20} color="var(--accent-primary)" />
          <div style={{
            background: 'var(--accent-primary)',
            color: 'white',
            fontSize: 11,
            fontWeight: 600,
            padding: '2px 7px',
            borderRadius: 12,
            minWidth: 28,
            textAlign: 'center',
          }}>
            {pageRegions.length}
          </div>
        </div>
      ) : (
        <>
          {/* Header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 14px',
            borderBottom: '1px solid var(--border-color)',
            flexShrink: 0,
          }}>
            <Shield size={18} color="var(--accent-primary)" />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>Detected</span>
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
                borderRadius: 4,
              }}
              title="Collapse sidebar"
            >
              <ChevronRight size={16} />
            </button>
          </div>
          {/* Tab bar */}
          <div style={{
            display: 'flex',
            borderBottom: '1px solid var(--border-color)',
            background: 'rgba(0,0,0,0.15)',
            flexShrink: 0,
          }}>
            {(["page", "document"] as const).map((tab) => {
              const isActive = activeTab === tab;
              const count = tab === "page" ? pageRegions.length : allRegions.length;
              const label = tab === "page" ? `This page (${count})` : `Document (${count})`;
              return (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  style={{
                    flex: 1,
                    padding: '8px 0',
                    fontSize: 12,
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? 'var(--accent-primary)' : 'var(--text-muted)',
                    background: 'transparent',
                    border: 'none',
                    borderBottom: isActive ? '2px solid var(--accent-primary)' : '2px solid transparent',
                    borderRadius: 0,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>
          {/* Bulk actions toolbar */}
          {tabRegions.length > 0 && (() => {
            // If items are selected, scope actions to selected visible items; otherwise all visible
            const hasSelection = selectedRegionIds.length > 0;
            const targetRegions = hasSelection
              ? displayedRegions.filter(r => selectedRegionIds.includes(r.id))
              : displayedRegions;
            const activeRegions = targetRegions.filter(r => r.action !== "CANCEL");
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
                  batchRegionAction(activeDocId, ids, newAction).catch(logError("batch-tokenize"));
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
                title={allTokenized ? "Undo tokenize" : "Tokenize regions"}
              >
                <Key size={13} />
                Tokenize
              </button>
              <button
                onClick={() => {
                  if (!activeDocId) return;
                  pushUndo();
                  const ids = activeRegions.map(r => r.id);
                  const newAction = allRemoved ? "PENDING" : "REMOVE";
                  ids.forEach(id => updateRegionAction(id, newAction));
                  batchRegionAction(activeDocId, ids, newAction).catch(logError("batch-remove"));
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
                title={allRemoved ? "Undo remove" : "Remove regions"}
              >
                <Trash2 size={13} />
                Remove
              </button>
              {/* Filter by type — ellipsis button */}
              <div ref={filterRef} style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <button
                  onClick={() => setTypeFilterOpen(v => !v)}
                  style={{
                    padding: '5px 4px',
                    fontSize: 11,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderRadius: 4,
                    cursor: 'pointer',
                    border: !allTypesEnabled ? '1px solid var(--accent-primary)' : '1px solid transparent',
                    background: !allTypesEnabled ? 'rgba(100,181,246,0.12)' : 'transparent',
                    color: 'var(--text-secondary)',
                    transition: 'all 0.15s ease',
                    flexShrink: 0,
                  }}
                  title="Filter by PII type"
                >
                  <MoreVertical size={14} />
                </button>
                {typeFilterOpen && (
                  <div style={{
                    position: 'absolute',
                    top: '100%',
                    right: 0,
                    marginTop: 4,
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border-color)',
                    borderRadius: 6,
                    padding: '6px 0',
                    minWidth: 170,
                    zIndex: 50,
                    boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
                    maxHeight: 260,
                    overflowY: 'auto',
                  }}>
                    {availableTypes.map(type => {
                      const checked = enabledTypes === null || enabledTypes.has(type);
                      return (
                        <label
                          key={type}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            padding: '3px 12px',
                            fontSize: 11,
                            color: 'var(--text-primary)',
                            cursor: 'pointer',
                          }}
                          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
                          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleType(type)}
                            style={{ accentColor: PII_COLORS[type] || '#888' }}
                          />
                          {type}
                        </label>
                      );
                    })}
                    {/* Divider + Clear checked types */}
                    <div style={{ height: 1, background: 'var(--border-color)', margin: '6px 0' }} />
                    <button
                      onClick={() => {
                        if (!activeDocId) return;
                        // Only clear regions whose types are currently checked
                        const checkedTypes = enabledTypes === null
                          ? new Set(availableTypes)
                          : enabledTypes;
                        const targetRegions = tabRegions.filter(
                          r => checkedTypes.has(r.pii_type) && r.action !== "CANCEL"
                        );
                        if (targetRegions.length === 0) return;
                        const ids = targetRegions.map(r => r.id);
                        const skipConfirm = localStorage.getItem('clearRegionsNeverAsk') === 'true';
                        if (skipConfirm) {
                          pushUndo();
                          ids.forEach(id => removeRegion(id));
                          batchDeleteRegions(activeDocId, ids).catch(logError("batch-clear"));
                          setEnabledTypes(null);
                        } else {
                          clearConfirmRef.current.ids = ids;
                          setClearNeverAsk(false);
                          setClearConfirmOpen(true);
                        }
                        setTypeFilterOpen(false);
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '5px 12px',
                        fontSize: 11,
                        fontWeight: 600,
                        color: '#f44336',
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        width: '100%',
                        textAlign: 'left',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(244,67,54,0.08)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                      title="Clear all regions matching checked types"
                    >
                      <X size={13} />
                      Clear checked types
                    </button>
                  </div>
                )}
              </div>
              </div>
            </div>
            );
          })()}
          <div style={styles.regionList}>
        {displayedRegions.slice(0, maxVisible).map((r) => (
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
            onClick={(e) => {
              const idx = displayedRegions.indexOf(r);
              if (e.shiftKey && lastClickedIndexRef.current !== null) {
                // Shift-click: range select without page change or scroll
                const start = Math.min(lastClickedIndexRef.current, idx);
                const end = Math.max(lastClickedIndexRef.current, idx);
                const rangeIds = displayedRegions.slice(start, end + 1).map(reg => reg.id);
                onSelect(rangeIds);
              } else {
                // Normal or ctrl click
                if (!e.ctrlKey && !e.metaKey) {
                  onNavigateToRegion(r);
                }
                onToggleSelect(r.id, e.ctrlKey || e.metaKey);
                lastClickedIndexRef.current = idx;
              }
            }}
            onMouseEnter={(e) => {
              const tb = e.currentTarget.querySelector('[data-region-toolbar]') as HTMLElement | null;
              if (tb) tb.style.opacity = '1';
            }}
            onMouseLeave={(e) => {
              const tb = e.currentTarget.querySelector('[data-region-toolbar]') as HTMLElement | null;
              if (tb) tb.style.opacity = '0.6';
            }}
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
            <div
              data-region-toolbar
              style={styles.regionActions}
            >
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
                <ReplaceAll size={13} />
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
                  gap: r.action === "TOKENIZE" ? 4 : 0,
                  transition: "all 0.2s ease",
                }}
              >
                <Key size={13} />
                <span style={{
                  fontSize: 11,
                  fontWeight: 600,
                  maxWidth: r.action === "TOKENIZE" ? 60 : 0,
                  overflow: "hidden",
                  opacity: r.action === "TOKENIZE" ? 1 : 0,
                  transition: "max-width 0.2s ease, opacity 0.15s ease",
                  whiteSpace: "nowrap",
                }}>Tokenize</span>
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
                  gap: r.action === "REMOVE" ? 4 : 0,
                  transition: "all 0.2s ease",
                }}
              >
                <Trash2 size={13} />
                <span style={{
                  fontSize: 11,
                  fontWeight: 600,
                  maxWidth: r.action === "REMOVE" ? 52 : 0,
                  overflow: "hidden",
                  opacity: r.action === "REMOVE" ? 1 : 0,
                  transition: "max-width 0.2s ease, opacity 0.15s ease",
                  whiteSpace: "nowrap",
                }}>Remove</span>
              </button>
            </div>
            {activeTab === "document" && (
              <div style={{
                position: "absolute",
                bottom: 4,
                right: 8,
                fontSize: 10,
                color: "var(--text-muted)",
                opacity: 0.7,
              }}>
                page {r.page_number}
              </div>
            )}
          </div>
        ))}
        {displayedRegions.length > maxVisible && (
          <button
            onClick={() => setMaxVisible(prev => prev + LOAD_MORE_STEP)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 4,
              padding: "8px 12px", margin: "4px 8px", fontSize: 12, color: "var(--accent-primary)",
              background: "var(--bg-primary)", border: "1px solid var(--border-color)",
              borderRadius: 6, cursor: "pointer", width: "calc(100% - 16px)",
            }}
          >
            <ChevronDown size={14} />
            Show {Math.min(LOAD_MORE_STEP, displayedRegions.length - maxVisible)} more
            ({displayedRegions.length - maxVisible} remaining)
          </button>
        )}
        {displayedRegions.length === 0 && (
          <p style={{ color: "var(--text-muted)", padding: 12, fontSize: 13 }}>
            {activeTab === "page" ? "No PII detected on this page." : "No PII detected in this document."}
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

      {/* Clear confirmation dialog */}
      {clearConfirmOpen && (
        <div role="dialog" aria-modal="true" aria-label="Confirm clear regions" style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(0,0,0,0.5)',
          zIndex: 100,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: 8,
            padding: '20px 24px',
            width: '85%',
            maxWidth: 280,
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
              Clear all regions?
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '0 0 12px', lineHeight: 1.5 }}>
              This will remove {clearConfirmRef.current.ids.length} region{clearConfirmRef.current.ids.length !== 1 ? 's' : ''} from the list. You can still <strong>undo</strong> this action.
            </p>
            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 11,
              color: 'var(--text-muted)',
              cursor: 'pointer',
              marginBottom: 16,
            }}>
              <input
                type="checkbox"
                checked={clearNeverAsk}
                onChange={e => setClearNeverAsk(e.target.checked)}
                style={{ accentColor: 'var(--accent-primary)' }}
              />
              Never show this message again
            </label>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setClearConfirmOpen(false)}
                style={{
                  padding: '6px 14px',
                  fontSize: 12,
                  fontWeight: 500,
                  borderRadius: 4,
                  border: '1px solid var(--border-color)',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (clearNeverAsk) {
                    localStorage.setItem('clearRegionsNeverAsk', 'true');
                  }
                  setClearConfirmOpen(false);
                  if (!activeDocId) return;
                  pushUndo();
                  const ids = clearConfirmRef.current.ids;
                  ids.forEach(id => removeRegion(id));
                  batchDeleteRegions(activeDocId, ids).catch(logError("batch-clear"));
                  setEnabledTypes(null);
                }}
                style={{
                  padding: '6px 14px',
                  fontSize: 12,
                  fontWeight: 600,
                  borderRadius: 4,
                  border: 'none',
                  background: '#f44336',
                  color: 'white',
                  cursor: 'pointer',
                }}
              >
                Clear
              </button>
            </div>
          </div>
        </div>
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
    zIndex: 42,
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
    opacity: 0.6,
    transition: "opacity 0.15s ease",
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
    background: "transparent",
    border: "none",
    borderRadius: 5,
    cursor: "pointer",
    color: "var(--text-secondary)",
    transition: "opacity 0.15s ease, color 0.15s ease, background 0.15s ease",
  },
  statBadge: {
    fontSize: 11,
    color: "var(--text-secondary)",
    background: "var(--bg-surface)",
    padding: "2px 8px",
    borderRadius: 4,
  },
};
