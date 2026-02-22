/** Region sidebar — displays detected PII regions with actions. */

import React from "react";
import { useTranslation } from "react-i18next";
import {
  BullseyePointer,
  ChevronLeft,
  ChevronRight,
  Key,
  Trash2,
  X,
  ReplaceAll,
  RefreshCw,
  Search,
  Edit3,
  MoreVertical,
  ChevronDown,
} from "../icons";
import { PII_COLORS, type PIIRegion, type RegionAction, type PIILabelEntry, loadLabelConfig } from "../types";
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
  onEdit: (regionId: string) => void;
  onNavigateToRegion: (region: PIIRegion) => void;
  pushUndo: () => void;
  removeRegion: (id: string) => void;
  updateRegionAction: (id: string, action: RegionAction) => void;
  batchRegionAction: (docId: string, ids: string[], action: RegionAction) => Promise<any>;
  batchDeleteRegions: (docId: string, ids: string[]) => Promise<any>;
  onTypeFilterChange?: (enabledTypes: Set<string> | null) => void;
  hideResizeHandle?: boolean;
  visibleLabels?: PIILabelEntry[];
  onUpdateLabel?: (regionId: string, newLabel: string) => void;
  onUpdateText?: (regionId: string, newText: string) => void;
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
  onEdit,
  onNavigateToRegion,
  pushUndo,
  removeRegion,
  updateRegionAction,
  batchRegionAction,
  batchDeleteRegions,
  onTypeFilterChange,
  visibleLabels: visibleLabelsProp,
  onUpdateLabel,
  onUpdateText,
}: RegionSidebarProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<SidebarTab>("page");
  const [typeFilterOpen, setTypeFilterOpen] = React.useState(false);
  const [enabledTypes, setEnabledTypes] = React.useState<Set<string> | null>(null); // null = all
  const filterRef = React.useRef<HTMLDivElement>(null);
  const lastClickedIndexRef = React.useRef<number | null>(null);
  const regionListRef = React.useRef<HTMLDivElement>(null);
  const itemRefs = React.useRef<Map<string, HTMLDivElement>>(new Map());
  const [clearConfirmOpen, setClearConfirmOpen] = React.useState(false);
  const [clearNeverAsk, setClearNeverAsk] = React.useState(false);
  const clearConfirmRef = React.useRef<{ ids: string[] }>({ ids: [] });
  // When true, skip the next sidebar auto-scroll (user clicked an item directly)
  const skipSidebarScrollRef = React.useRef(false);

  // ── Inline PII type dropdown & text editing state ──
  const [typeDropdownRegionId, setTypeDropdownRegionId] = React.useState<string | null>(null);
  const typeDropdownRef = React.useRef<HTMLDivElement>(null);
  const [editingTextRegionId, setEditingTextRegionId] = React.useState<string | null>(null);
  const [editingTextValue, setEditingTextValue] = React.useState("");
  const editTextRef = React.useRef<HTMLTextAreaElement>(null);

  // ── Scroll sidebar to first selected item when selection changes ──
  React.useEffect(() => {
    if (skipSidebarScrollRef.current) {
      skipSidebarScrollRef.current = false;
      return;
    }
    if (selectedRegionIds.length === 0) return;
    const firstId = selectedRegionIds[0];
    const el = itemRefs.current.get(firstId);
    const list = regionListRef.current;
    if (el && list) {
      const elTop = el.offsetTop;
      const elBottom = elTop + el.offsetHeight;
      const listTop = list.scrollTop;
      const listMid = listTop + list.clientHeight / 2;
      // Scroll if the item is out of view OR is in the lower half of the list —
      // target position: item sits ~25% from the top of the visible area.
      if (elTop < listTop || elBottom > listMid) {
        const targetScroll = Math.max(0, elTop - Math.round(list.clientHeight * 0.25));
        list.scrollTo({ top: targetScroll, behavior: "smooth" });
      }
    }
  }, [selectedRegionIds]);

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

  // Close type dropdown on outside click
  React.useEffect(() => {
    if (!typeDropdownRegionId) return;
    const handler = (e: MouseEvent) => {
      if (typeDropdownRef.current && !typeDropdownRef.current.contains(e.target as Node)) {
        setTypeDropdownRegionId(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [typeDropdownRegionId]);

  // Auto-focus textarea when editing text
  React.useEffect(() => {
    if (editingTextRegionId && editTextRef.current) {
      editTextRef.current.focus();
      editTextRef.current.select();
    }
  }, [editingTextRegionId]);

  // Resolve labels list — use prop or fallback to loadLabelConfig
  const resolvedLabels = React.useMemo(() => {
    if (visibleLabelsProp && visibleLabelsProp.length > 0) return visibleLabelsProp;
    return loadLabelConfig().filter(l => !l.hidden);
  }, [visibleLabelsProp]);

  const tabRegions = activeTab === "page" ? pageRegions : allRegions;

  // Compute footer stats scoped to the active tab (page vs document)
  const scopedPendingCount = React.useMemo(() => tabRegions.filter(r => r.action === "PENDING").length, [tabRegions]);
  const scopedRemoveCount = React.useMemo(() => tabRegions.filter(r => r.action === "REMOVE").length, [tabRegions]);
  const scopedTokenizeCount = React.useMemo(() => tabRegions.filter(r => r.action === "TOKENIZE").length, [tabRegions]);

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
            title={t("regions.expandSidebar")}
          >
            <ChevronLeft size={18} variant="light" />
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
            <BullseyePointer size={18} color="var(--accent-primary)" />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>{t("regions.detected")}</span>
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
              title={t("regions.collapseSidebar")}
            >
              <ChevronRight size={16} variant="light" />
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
              const label = tab === "page" ? t("regions.tabThisPage", { count }) : t("regions.tabDocument", { count });
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
                title={allTokenized ? t("regions.undoTokenize") : t("regions.tokenizeRegions")}
              >
                <Key size={13} variant="light" />
                {t("regions.tokenize")}
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
                title={allRemoved ? t("regions.undoRemove") : t("regions.removeRegions")}
              >
                <Trash2 size={13} variant="light" />
                {t("regions.remove")}
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
                  title={t("regions.filterByType")}
                >
                  <MoreVertical size={14} variant="light" />
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
                    {/* Select / Deselect all type filters */}
                    <label
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '4px 12px',
                        fontSize: 11,
                        fontWeight: 600,
                        color: 'var(--text-primary)',
                        cursor: 'pointer',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <input
                        type="checkbox"
                        checked={allTypesEnabled}
                        ref={el => { if (el) el.indeterminate = !allTypesEnabled && enabledTypes !== null && enabledTypes.size > 0; }}
                        onChange={() => {
                          if (allTypesEnabled) {
                            // Deselect all — keep only the first type so at least one stays
                            setEnabledTypes(new Set());
                          } else {
                            // Select all
                            setEnabledTypes(null);
                          }
                        }}
                        style={{ accentColor: 'var(--accent-primary)' }}
                      />
                      {t("common.selectAll")}
                    </label>
                    <div style={{ height: 1, background: 'var(--border-color)', margin: '4px 0' }} />
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
                      title={t("regions.clearCheckedTypes")}
                    >
                      <X size={13} variant="light" />
                      {t("regions.clearCheckedTypes")}
                    </button>
                  </div>
                )}
              </div>
              </div>
            </div>
            );
          })()}
          <div ref={regionListRef} style={styles.regionList}>
        {displayedRegions.slice(0, maxVisible).map((r) => (
          <div
            key={r.id}
            ref={el => { if (el) itemRefs.current.set(r.id, el); else itemRefs.current.delete(r.id); }}
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
              skipSidebarScrollRef.current = true;
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
              e.currentTarget.querySelectorAll('[data-dim-btn]').forEach(el => {
                (el as HTMLElement).style.opacity = '1';
              });
            }}
            onMouseLeave={(e) => {
              e.currentTarget.querySelectorAll('[data-dim-btn]').forEach(el => {
                (el as HTMLElement).style.opacity = '0.35';
              });
            }}
          >
            {/* Clear — top-right close button */}
            <button
              className="btn-ghost btn-sm"
              onClick={(e) => {
                e.stopPropagation();
                onClear(r.id);
              }}
              title={t("regions.clearFromDocument")}
              style={styles.sidebarCloseBtn}
            >
              <X size={14} variant="light" />
            </button>
            <div style={styles.regionHeader}>
              {/* PII type chip with dropdown */}
              <div style={{ position: "relative" }}>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setTypeDropdownRegionId(prev => prev === r.id ? null : r.id);
                    setEditingTextRegionId(null);
                  }}
                  style={{
                    ...styles.typeBadge,
                    background: PII_COLORS[r.pii_type] || "#888",
                    border: "none",
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 3,
                  }}
                >
                  {r.pii_type}
                  <span style={{ fontSize: 8, marginLeft: 1, opacity: 0.8 }}>&#9660;</span>
                </button>
                {typeDropdownRegionId === r.id && (
                  <div
                    ref={typeDropdownRef}
                    style={{
                      position: "absolute",
                      top: "100%",
                      left: 0,
                      marginTop: 4,
                      zIndex: 100,
                      background: "var(--bg-secondary)",
                      border: "1px solid var(--border-color)",
                      borderRadius: 6,
                      boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
                      maxHeight: 200,
                      overflowY: "auto",
                      minWidth: 130,
                    }}
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                  >
                    {resolvedLabels.map((entry) => (
                      <button
                        key={entry.label}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (entry.label !== r.pii_type) {
                            pushUndo();
                            onUpdateLabel?.(r.id, entry.label);
                          }
                          setTypeDropdownRegionId(null);
                        }}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          width: "100%",
                          padding: "6px 10px",
                          fontSize: 11,
                          fontWeight: entry.label === r.pii_type ? 700 : 400,
                          color: entry.label === r.pii_type ? "white" : "var(--text-primary)",
                          background: entry.label === r.pii_type ? "var(--bg-tertiary)" : "transparent",
                          border: "none",
                          cursor: "pointer",
                          textAlign: "left",
                        }}
                        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-tertiary)"; }}
                        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = entry.label === r.pii_type ? "var(--bg-tertiary)" : "transparent"; }}
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
              <span style={styles.confidence}>
                {Math.round(r.confidence * 100)}%
              </span>
              <span style={styles.sourceTag}>{r.source}</span>
              {activeTab === "document" && (
                <span style={styles.sourceTag}>p.{r.page_number}</span>
              )}
              {(r.action === "TOKENIZE" || r.action === "REMOVE") && (
                <span style={{
                  ...styles.typeBadge,
                  background: r.action === "TOKENIZE" ? "#9c27b0" : "#f44336",
                }}>
                  {r.action === "TOKENIZE" ? t("regions.tokenize") : t("regions.remove")}
                </span>
              )}
            </div>
            {/* Region text — inline editable */}
            {editingTextRegionId === r.id ? (
              <div style={{ paddingTop: 6 }} onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
                <textarea
                  ref={editTextRef}
                  value={editingTextValue}
                  onChange={(e) => setEditingTextValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") { setEditingTextRegionId(null); }
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      if (editingTextValue.trim() !== r.text) {
                        pushUndo();
                        onUpdateText?.(r.id, editingTextValue.trim());
                      }
                      setEditingTextRegionId(null);
                    }
                  }}
                  style={{
                    width: "100%",
                    fontSize: 12,
                    color: "var(--text-primary)",
                    background: "var(--bg-primary)",
                    border: "1px solid var(--accent-primary)",
                    borderRadius: 4,
                    padding: "4px 6px",
                    resize: "vertical",
                    minHeight: 32,
                    fontFamily: "inherit",
                  }}
                  rows={2}
                />
                <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                  <button
                    className="btn-primary"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (editingTextValue.trim() !== r.text) {
                        pushUndo();
                        onUpdateText?.(r.id, editingTextValue.trim());
                      }
                      setEditingTextRegionId(null);
                    }}
                    style={{ fontSize: 11, padding: "3px 10px" }}
                  >
                    {t("common.save")}
                  </button>
                  <button
                    className="btn-ghost btn-sm"
                    onClick={(e) => { e.stopPropagation(); setEditingTextRegionId(null); }}
                    style={{ fontSize: 11, padding: "3px 8px" }}
                  >
                    {t("common.cancel")}
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ paddingTop: 6, paddingBottom: 12 }}>
                <span style={{ fontSize: 12, color: "var(--text-secondary)", wordBreak: "break-word" }}>
                  <span
                    style={{ cursor: "pointer" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingTextRegionId(r.id);
                      setEditingTextValue(r.text);
                      setTypeDropdownRegionId(null);
                    }}
                  >"{r.text}"</span>
                  <button
                    data-dim-btn
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingTextRegionId(r.id);
                      setEditingTextValue(r.text);
                      setTypeDropdownRegionId(null);
                    }}
                    title={t("common.edit")}
                    style={{
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      padding: "0 0 0 4px",
                      color: "var(--text-secondary)",
                      opacity: 0.35,
                      verticalAlign: "middle",
                      display: "inline-flex",
                    }}
                  >
                    <Edit3 size={11} variant="light" />
                  </button>
                </span>
              </div>
            )}
            <div
              data-region-toolbar
              style={{ ...styles.regionActions, opacity: 1, width: "100%", paddingTop: 8, paddingRight: 10 }}
            >
              {/* Left group */}
              <div style={{ display: "flex", gap: 2 }}>
              {/* Replace all */}
              <button
                data-dim-btn
                className="btn-ghost btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onHighlightAll(r.id);
                }}
                title={t("regions.replaceAllMatching")}
                style={{ ...styles.sidebarBtn, opacity: 0.35 }}
              >
                <ReplaceAll size={13} variant="light" />
              </button>
              {/* Detect */}
              <button
                data-dim-btn
                className="btn-ghost btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onRefresh(r.id);
                }}
                title={t("regions.redetect")}
                style={{ ...styles.sidebarBtn, opacity: 0.35 }}
              >
                <RefreshCw size={13} variant="light" />
              </button>
              </div>
              {/* Right group */}
              <div style={{ display: "flex", gap: 2, marginLeft: "auto" }}>
              {/* Tokenize */}
              <button
                data-dim-btn
                className="btn-tokenize btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onRegionAction(r.id, r.action === "TOKENIZE" ? "PENDING" : "TOKENIZE");
                }}
                title={r.action === "TOKENIZE" ? t("regions.undoTokenize") : t("regions.tokenize")}
                style={{
                  ...styles.sidebarBtn,
                  opacity: 0.35,
                  color: "#9c27b0",
                  gap: 3,
                }}
              >
                <Key size={13} variant="light" />
                <span style={{ fontSize: 11 }}>{t("regions.tokenize")}</span>
              </button>
              {/* Remove */}
              <button
                data-dim-btn
                className="btn-danger btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onRegionAction(r.id, r.action === "REMOVE" ? "PENDING" : "REMOVE");
                }}
                title={r.action === "REMOVE" ? t("regions.undoRemove") : t("regions.remove")}
                style={{
                  ...styles.sidebarBtn,
                  opacity: 0.35,
                  color: "#f44336",
                  gap: 3,
                }}
              >
                <Trash2 size={13} variant="light" />
                <span style={{ fontSize: 11 }}>{t("regions.remove")}</span>
              </button>
              </div>
            </div>

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
            <ChevronDown size={14} variant="light" />
            {t("regions.showMore", { count: Math.min(LOAD_MORE_STEP, displayedRegions.length - maxVisible), remaining: displayedRegions.length - maxVisible })}
          </button>
        )}
        {displayedRegions.length === 0 && (
          <p style={{ color: "var(--text-muted)", padding: 12, fontSize: 13 }}>
            {activeTab === "page" ? t("regions.noDetectedThisPage") : t("regions.noDetectedDocument")}
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
              {t("regions.pendingCount", { count: scopedPendingCount })}
            </span>
            <span style={{ ...styles.statBadge, fontSize: 11, color: "#f44336", background: "transparent" }}>
              {t("regions.removeCount", { count: scopedRemoveCount })}
            </span>
            <span style={{ ...styles.statBadge, fontSize: 11, color: "#9c27b0", background: "transparent" }}>
              {t("regions.tokenizeCount", { count: scopedTokenizeCount })}
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
              {t("regions.clearAllTitle")}
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '0 0 12px', lineHeight: 1.5 }}>
              {t("regions.clearAllMessage", { count: clearConfirmRef.current.ids.length })}
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
              {t("regions.neverShowAgain")}
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
                {t("common.cancel")}
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
                {t("regions.clear")}
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
    paddingRight: 6,
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
    fontSize: 10,
    fontWeight: 600,
    color: "white",
    background: "rgba(0,0,0,0.15)",
    padding: "2px 6px",
    borderRadius: 3,
    textTransform: "uppercase" as const,
  },
  sourceTag: {
    fontSize: 10,
    fontWeight: 600,
    color: "white",
    background: "rgba(0,0,0,0.15)",
    padding: "2px 6px",
    borderRadius: 3,
    textTransform: "uppercase" as const,
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
    opacity: 0.35,
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
