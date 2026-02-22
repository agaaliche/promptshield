/**
 * PII region overlay — semi-transparent rectangle with action buttons.
 * Supports move (drag the body) and resize (drag corner/edge handles).
 */

import React, { useState, useRef, useEffect, memo } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { PII_COLORS, getPIIColor, loadLabelConfig, type PIIRegion, type RegionAction, type PIIType } from "../types";
import { X, Trash2, Key, Edit3, Tag, ReplaceAll, RefreshCw, LayerGroup } from "../icons";

export type ResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

const HANDLE_SIZE = 8;
const HALF = HANDLE_SIZE / 2;
const MIN_REGION_PX = 10; // minimum rendered height/width in pixels

const HANDLE_CURSORS: Record<ResizeHandle, string> = {
  nw: "nwse-resize",
  n: "ns-resize",
  ne: "nesw-resize",
  e: "ew-resize",
  se: "nwse-resize",
  s: "ns-resize",
  sw: "nesw-resize",
  w: "ew-resize",
};

// ── Module-level caches for localStorage (avoids 300+ reads with many regions) ──
let _cachedToolbarPos: { x: number; y: number } | null | undefined = undefined;
let _cachedDialogPos: { x: number; y: number } | null = null;

function getCachedToolbarPos(): { x: number; y: number } | null {
  if (_cachedToolbarPos !== undefined) return _cachedToolbarPos;
  try {
    const saved = localStorage.getItem('regionToolbarPos');
    _cachedToolbarPos = saved ? JSON.parse(saved) : null;
  } catch (_e) {
    _cachedToolbarPos = null;
  }
  return _cachedToolbarPos;
}

function getCachedDialogPos(): { x: number; y: number } {
  if (_cachedDialogPos !== null) return _cachedDialogPos;
  try {
    const saved = localStorage.getItem('regionDialogPos');
    _cachedDialogPos = saved ? JSON.parse(saved) : { x: 300, y: 100 };
  } catch (_e) {
    _cachedDialogPos = { x: 300, y: 100 };
  }
  return _cachedDialogPos!;
}

interface Props {
  region: PIIRegion;
  pageWidth: number;
  pageHeight: number;
  imgWidth: number;
  imgHeight: number;
  isSelected: boolean;
  isMultiSelected: boolean;
  isImageFile: boolean;
  onSelect: (e: React.MouseEvent) => void;
  onAction: (regionId: string, action: RegionAction) => void;
  onClear?: (regionId: string) => void;
  onRefresh?: (regionId: string) => void;
  onHighlightAll?: (regionId: string) => void;
  onMoveStart?: (regionId: string, e: React.MouseEvent) => void;
  onResizeStart?: (
    regionId: string,
    handle: ResizeHandle,
    e: React.MouseEvent,
  ) => void;
  onUpdateLabel?: (regionId: string, newType: PIIType) => void;
  onUpdateText?: (regionId: string, newText: string) => void;
  /** IDs of all currently selected regions — used for bulk label change */
  selectedRegionIds?: string[];
  /** When true, auto-open the edit panel (triggered from sidebar edit button) */
  autoOpenEdit?: boolean;
  /** Called after auto-open has been consumed */
  onEditOpened?: () => void;
  portalTarget?: HTMLElement | null;
  imageContainerEl?: HTMLElement | null;
  cursorToolbarExpanded?: boolean;
  /** Total right-side reserved width (sidebar + page nav) for toolbar/dialog clamping */
  rightInset?: number;
  /** Left sidebar width — triggers re-clamp when left sidebar resizes */
  leftSidebarWidth?: number;
}

function RegionOverlay({
  region,
  pageWidth,
  pageHeight,
  imgWidth,
  imgHeight,
  isSelected,
  isMultiSelected,
  isImageFile,
  onSelect,
  onAction,
  onClear,
  onRefresh,
  onHighlightAll,
  onMoveStart,
  onResizeStart,
  onUpdateLabel,
  onUpdateText,
  selectedRegionIds = [],
  autoOpenEdit,
  onEditOpened,
  portalTarget,
  imageContainerEl,
  cursorToolbarExpanded,
  rightInset = 0,
  leftSidebarWidth = 0,
}: Props) {
  const { t } = useTranslation();
  const [showEditPanel, setShowEditPanel] = useState(false);
  const [showTypeDropdown, setShowTypeDropdown] = useState(false);
  const typeDropdownRef = useRef<HTMLDivElement>(null);

  // Resolved PII label list (cached at module level)
  const resolvedLabels = React.useMemo(() => loadLabelConfig().filter(l => !l.hidden), []);

  const [activeTab, setActiveTab] = useState<"label" | "content">("label");
  const [isEditingLabel, setIsEditingLabel] = useState(false);
  const [isEditingText, setIsEditingText] = useState(false);
  const [editedText, setEditedText] = useState(region.text);
  
  // Toolbar position (viewport/fixed coordinates)
  const [toolbarPos, setToolbarPos] = useState<{ x: number; y: number } | null>(getCachedToolbarPos);
  const highlightRef = useRef<HTMLDivElement>(null);
  const [isDraggingToolbar, setIsDraggingToolbar] = useState(false);
  const toolbarDragStart = useRef({ mouseX: 0, mouseY: 0, startX: 0, startY: 0 });
  const toolbarRef = useRef<HTMLDivElement>(null);
  
  // Edit dialog position (viewport coordinates)
  const [dialogPos, setDialogPos] = useState(getCachedDialogPos);
  const [isDraggingDialog, setIsDraggingDialog] = useState(false);
  const dialogDragStart = useRef({ mouseX: 0, mouseY: 0, startX: 0, startY: 0 });
  const dialogRef = useRef<HTMLDivElement>(null);

  // Auto-open edit panel when triggered from sidebar
  useEffect(() => {
    if (autoOpenEdit && isSelected) {
      setShowEditPanel(true);
      setActiveTab("label");
      onEditOpened?.();
    }
  }, [autoOpenEdit, isSelected, onEditOpened]);

  // Close type dropdown on outside click
  useEffect(() => {
    if (!showTypeDropdown) return;
    const handler = (e: MouseEvent) => {
      if (typeDropdownRef.current && !typeDropdownRef.current.contains(e.target as Node)) {
        setShowTypeDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showTypeDropdown]);
  
  // Convert page coordinates → CSS percentage coordinates on the displayed image.
  // Using percentages keeps regions in sync during CSS transitions (sidebar
  // collapse/expand) because the browser resolves them at layout time rather
  // than relying on React state which lags behind by ≥1 frame.
  // Clamp to [0, 100] so regions never visually overflow the page boundary.
  const rawLeft = (region.bbox.x0 / pageWidth) * 100;
  const rawTop = (region.bbox.y0 / pageHeight) * 100;
  const rawWidth = ((region.bbox.x1 - region.bbox.x0) / pageWidth) * 100;
  const rawHeight = ((region.bbox.y1 - region.bbox.y0) / pageHeight) * 100;
  const leftPct = Math.max(0, Math.min(rawLeft, 100));
  const topPct = Math.max(0, Math.min(rawTop, 100));
  const widthPct = Math.max(0, Math.min(rawWidth, 100 - leftPct));
  const heightPct = Math.max(0, Math.min(rawHeight, 100 - topPct));

  // Pixel values still needed for maxWidth on the label
  const sx = imgWidth / pageWidth;
  const pixelWidth = (region.bbox.x1 - region.bbox.x0) * sx;

  // Background color based on action
  let bgColor: string;
  switch (region.action) {
    case "REMOVE":
      bgColor = "var(--highlight-remove)";
      break;
    case "TOKENIZE":
      bgColor = "var(--highlight-tokenize)";
      break;
    case "CANCEL":
      bgColor = "var(--highlight-cancel)";
      break;
    default:
      bgColor = "var(--highlight-pending)";
  }

  // Use shield-blue for selected border, PII color otherwise
  const baseBorderColor = getPIIColor(region.pii_type);
  const borderColor = (isSelected || showEditPanel) ? "var(--accent-primary)" : baseBorderColor;
  const [hovered, setHovered] = useState(false);
  // In multi-select mode: only show frame and border, no label/buttons
  const soloSelected = isSelected && !isMultiSelected;
  // Keep toolbar visible when edit panel is open
  const showDetails = soloSelected || showEditPanel;
  const showTab = (hovered && !isMultiSelected) || showDetails;
  const showFrame = hovered || isSelected || isMultiSelected || showEditPanel;

  // Close dropdown when toolbar hides
  useEffect(() => {
    if (!showDetails) setShowTypeDropdown(false);
  }, [showDetails]);

  // Toolbar drag handlers (fixed/viewport coordinates, identical to useDraggableToolbar)
  useEffect(() => {
    if (!isDraggingToolbar) return;
    const PAD = 8;
    const handleMouseMove = (e: MouseEvent) => {
      const tb = toolbarRef.current;
      if (!tb) return;
      const dx = e.clientX - toolbarDragStart.current.mouseX;
      const dy = e.clientY - toolbarDragStart.current.mouseY;
      let newX = toolbarDragStart.current.startX + dx;
      let newY = toolbarDragStart.current.startY + dy;

      // Clamp within content area minus right inset (identical to useDraggableToolbar.clamp)
      const area = portalTarget;
      if (area) {
        const areaRect = area.getBoundingClientRect();
        const minX = areaRect.left + PAD;
        const minY = areaRect.top + PAD;
        const maxX = areaRect.right - rightInset - tb.offsetWidth - PAD;
        const maxY = areaRect.bottom - tb.offsetHeight - PAD;
        newX = Math.max(minX, Math.min(maxX, newX));
        newY = Math.max(minY, Math.min(maxY, newY));
      }
      setToolbarPos({ x: newX, y: newY });
    };
    const handleMouseUp = () => {
      setIsDraggingToolbar(false);
    };
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDraggingToolbar, portalTarget, rightInset]);

  // Save toolbar offset to localStorage + module cache
  useEffect(() => {
    _cachedToolbarPos = toolbarPos;
    try {
      localStorage.setItem('regionToolbarPos', JSON.stringify(toolbarPos));
    } catch (e) {
      console.error('Failed to save toolbar offset:', e);
    }
  }, [toolbarPos]);



  // Dialog drag handlers — constrained to content area minus sidebar (identical to useDraggableToolbar.clamp)
  useEffect(() => {
    if (!isDraggingDialog) return;
    const PAD = 8;
    const handleMouseMove = (e: MouseEvent) => {
      const dlg = dialogRef.current;
      if (!dlg) return;
      const dx = e.clientX - dialogDragStart.current.mouseX;
      const dy = e.clientY - dialogDragStart.current.mouseY;
      let newX = dialogDragStart.current.startX + dx;
      let newY = dialogDragStart.current.startY + dy;

      // Clamp within content area minus right inset (identical to useDraggableToolbar.clamp)
      const area = portalTarget;
      if (area) {
        const areaRect = area.getBoundingClientRect();
        const minX = areaRect.left + PAD;
        const minY = areaRect.top + PAD;
        const maxX = areaRect.right - rightInset - dlg.offsetWidth - PAD;
        const maxY = areaRect.bottom - dlg.offsetHeight - PAD;
        newX = Math.max(minX, Math.min(maxX, newX));
        newY = Math.max(minY, Math.min(maxY, newY));
      }
      setDialogPos({ x: newX, y: newY });
    };
    
    const handleMouseUp = () => {
      setIsDraggingDialog(false);
    };
    
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDraggingDialog, portalTarget, rightInset]);

  // Clamp dialog position to content area minus right inset (identical to useDraggableToolbar.clamp)
  useEffect(() => {
    if (!showEditPanel || !dialogRef.current) return;
    const PAD = 8;
    const area = portalTarget;
    const dlg = dialogRef.current;
    if (!area) return;
    const w = dlg.offsetWidth;
    const h = dlg.offsetHeight;
    if (w === 0 || h === 0) return;
    const areaRect = area.getBoundingClientRect();
    const minX = areaRect.left + PAD;
    const minY = areaRect.top + PAD;
    const maxX = areaRect.right - rightInset - w - PAD;
    const maxY = areaRect.bottom - h - PAD;
    let { x, y } = dialogPos;
    let changed = false;
    if (x < minX) { x = minX; changed = true; }
    if (x > maxX) { x = maxX; changed = true; }
    if (y < minY) { y = minY; changed = true; }
    if (y > maxY) { y = maxY; changed = true; }
    if (changed) setDialogPos({ x, y });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showEditPanel, dialogPos, portalTarget, rightInset]);

  // Save dialog position to localStorage + module cache
  useEffect(() => {
    _cachedDialogPos = dialogPos;
    try {
      localStorage.setItem('regionDialogPos', JSON.stringify(dialogPos));
    } catch (e) {
      console.error('Failed to save dialog position:', e);
    }
  }, [dialogPos]);

  // Re-clamp toolbar + dialog when layout insets change
  // (sidebar collapse/expand/resize, page nav toggle, left sidebar resize)
  useEffect(() => {
    const PAD = 8;
    const area = portalTarget;
    if (!area) return;
    const areaRect = area.getBoundingClientRect();

    // Re-clamp toolbar
    const tb = toolbarRef.current;
    if (tb && toolbarPos) {
      const w = tb.offsetWidth;
      const h = tb.offsetHeight;
      if (w > 0 && h > 0) {
        const minX = areaRect.left + PAD;
        const minY = areaRect.top + PAD;
        const maxX = areaRect.right - rightInset - w - PAD;
        const maxY = areaRect.bottom - h - PAD;
        let { x, y } = toolbarPos;
        let changed = false;
        if (x < minX) { x = minX; changed = true; }
        if (x > maxX) { x = maxX; changed = true; }
        if (y < minY) { y = minY; changed = true; }
        if (y > maxY) { y = maxY; changed = true; }
        if (changed) setToolbarPos({ x, y });
      }
    }

    // Re-clamp dialog
    const dlg = dialogRef.current;
    if (dlg && showEditPanel) {
      const w = dlg.offsetWidth;
      const h = dlg.offsetHeight;
      if (w > 0 && h > 0) {
        const minX = areaRect.left + PAD;
        const minY = areaRect.top + PAD;
        const maxX = areaRect.right - rightInset - w - PAD;
        const maxY = areaRect.bottom - h - PAD;
        let { x, y } = dialogPos;
        let changed = false;
        if (x < minX) { x = minX; changed = true; }
        if (x > maxX) { x = maxX; changed = true; }
        if (y < minY) { y = minY; changed = true; }
        if (y > maxY) { y = maxY; changed = true; }
        if (changed) setDialogPos({ x, y });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rightInset, leftSidebarWidth]);

  // Set initial toolbar position on first show (absolute coords relative to contentArea)
  useEffect(() => {
    if (!showDetails || toolbarPos !== null) return;
    const el = highlightRef.current;
    const area = portalTarget;
    if (el && area) {
      const elRect = el.getBoundingClientRect();
      const areaRect = area.getBoundingClientRect();
      setToolbarPos({ x: elRect.right - areaRect.left + 8, y: elRect.top - areaRect.top });
    } else {
      setToolbarPos({ x: 12, y: 12 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showDetails]);

  // Clamp toolbar position to content area minus right inset (identical to useDraggableToolbar.clamp)
  useEffect(() => {
    if (!showDetails || !toolbarRef.current || !toolbarPos) return;
    const PAD = 8;
    const area = portalTarget;
    const tb = toolbarRef.current;
    if (!area) return;
    const w = tb.offsetWidth;
    const h = tb.offsetHeight;
    if (w === 0 || h === 0) return;
    const areaRect = area.getBoundingClientRect();
    const minX = areaRect.left + PAD;
    const minY = areaRect.top + PAD;
    const maxX = areaRect.right - rightInset - w - PAD;
    const maxY = areaRect.bottom - h - PAD;
    let { x, y } = toolbarPos;
    let changed = false;
    if (x < minX) { x = minX; changed = true; }
    if (x > maxX) { x = maxX; changed = true; }
    if (y < minY) { y = minY; changed = true; }
    if (y > maxY) { y = maxY; changed = true; }
    if (changed) setToolbarPos({ x, y });

    // Avoid overlapping the cursor toolbar
    const GAP = 2;
    const cursorTb = document.querySelector('[data-cursor-toolbar]');
    if (cursorTb) {
      const ctRect = cursorTb.getBoundingClientRect();
      const tbScreenLeft = areaRect.left + x;
      const tbScreenTop = areaRect.top + y;
      if (ctRect.width > 0 &&
        tbScreenLeft < ctRect.right + GAP &&
        tbScreenLeft + w > ctRect.left - GAP &&
        tbScreenTop < ctRect.bottom + GAP &&
        tbScreenTop + h > ctRect.top - GAP
      ) {
        const pushLeft = (tbScreenLeft + w) - (ctRect.left - GAP);
        const pushRight = (ctRect.right + GAP) - tbScreenLeft;
        const pushUp = (tbScreenTop + h) - (ctRect.top - GAP);
        const pushDown = (ctRect.bottom + GAP) - tbScreenTop;
        const minPush = Math.min(pushLeft, pushRight, pushUp, pushDown);
        if (minPush === pushLeft) x -= pushLeft;
        else if (minPush === pushRight) x += pushRight;
        else if (minPush === pushUp) y -= pushUp;
        else y += pushDown;
        x = Math.max(minX, Math.min(maxX, x));
        y = Math.max(minY, Math.min(maxY, y));
        setToolbarPos({ x, y });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showDetails, toolbarPos, portalTarget, cursorToolbarExpanded, rightInset]);

  if (region.action === "CANCEL") {
    return null;
  }

  // ── Handle positions ──────────────────────────────────────────────
  const handles: { key: ResizeHandle; style: React.CSSProperties }[] = [
    { key: "nw", style: { left: -HALF, top: -HALF } },
    {
      key: "n",
      style: { left: "50%", top: -HALF, marginLeft: -HALF },
    },
    { key: "ne", style: { right: -HALF, top: -HALF } },
    {
      key: "e",
      style: { right: -HALF, top: "50%", marginTop: -HALF },
    },
    { key: "se", style: { right: -HALF, bottom: -HALF } },
    {
      key: "s",
      style: { left: "50%", bottom: -HALF, marginLeft: -HALF },
    },
    { key: "sw", style: { left: -HALF, bottom: -HALF } },
    {
      key: "w",
      style: { left: -HALF, top: "50%", marginTop: -HALF },
    },
  ];

  return (
    <>
      {/* Highlight rectangle — drag body to move */}
      <div
        ref={highlightRef}
        data-region-id={region.id}
        style={{
          position: "absolute",
          left: `${leftPct}%`,
          top: `${topPct}%`,
          width: `${widthPct}%`,
          height: `${heightPct}%`,
          minWidth: MIN_REGION_PX,
          minHeight: MIN_REGION_PX,
          background: bgColor,
          border: showFrame ? `1px solid ${borderColor}` : "1px solid transparent",
          borderRadius: 2,
          cursor: soloSelected ? "move" : "pointer",
          zIndex: isSelected || showEditPanel ? 5 : hovered ? 4 : 2,
          transition: "border-color 0.15s ease, box-shadow 0.15s ease",
          boxShadow: isSelected || showEditPanel ? `0 0 0 1px ${borderColor}` : "none",
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onMouseDown={(e) => {
          e.stopPropagation();
          if (onMoveStart && soloSelected) {
            onMoveStart(region.id, e);
          } else {
            onSelect(e);
          }
        }}
      >
        {/* Resize handles — only visible when solo-selected */}
        {soloSelected &&
          handles.map((h) => (
            <div
              key={h.key}
              onMouseDown={(e) => {
                e.stopPropagation();
                e.preventDefault();
                onResizeStart?.(region.id, h.key, e);
              }}
              style={{
                position: "absolute",
                width: HANDLE_SIZE,
                height: HANDLE_SIZE,
                background: "white",
                border: `1.5px solid ${borderColor}`,
                borderRadius: 2,
                cursor: HANDLE_CURSORS[h.key],
                zIndex: 10,
                ...h.style,
              }}
            />
          ))}
      </div>

      {/* Top label - flush with border */}
      {showTab && (
        <div
          onMouseDown={(e) => e.stopPropagation()}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          style={{
            position: "absolute",
            left: `calc(${leftPct}% + 7px)`,
            top: `${topPct}%`,
            transform: "translateY(calc(-100% - 2px))",
            zIndex: 6,
            background: borderColor,
            color: "#000",
            padding: "4px 10px",
            borderRadius: "8px 8px 0 0",
            fontSize: 13,
            fontWeight: 600,
            whiteSpace: "nowrap",
            maxWidth: Math.max(pixelWidth - 5, 120),
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {region.pii_type}{region.text ? `: ${region.text.replace(/\n/g, " ")}` : ""}
        </div>
      )}

      {/* Vertical toolbar - rendered via portal into contentArea container */}
      {showDetails && portalTarget && createPortal(
        <div
          ref={toolbarRef}
          data-region-toolbar
          onMouseDown={(e) => e.stopPropagation()}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          style={{
            position: "fixed",
            left: toolbarPos?.x ?? 120,
            top: toolbarPos?.y ?? 120,
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
              setIsDraggingToolbar(true);
              toolbarDragStart.current = {
                mouseX: e.clientX,
                mouseY: e.clientY,
              startX: toolbarPos?.x ?? 120,
              startY: toolbarPos?.y ?? 120,
              };
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
                onHighlightAll?.(region.id);
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
              title={t("regions.replaceAllMatching")}
            >
              <ReplaceAll size={16} variant="light" />
            </button>

            {/* Detect */}
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                onRefresh?.(region.id);
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
              title={t("regions.redetect")}
            >
              <RefreshCw size={16} variant="light" />
            </button>

            {/* Change PII type */}
            <div style={{ position: "relative" }}>
              <button
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  setShowTypeDropdown(!showTypeDropdown);
                }}
                style={{
                  padding: "8px",
                  fontSize: 12,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  background: showTypeDropdown ? "var(--bg-primary)" : "transparent",
                  border: "1px solid transparent",
                  borderRadius: 4,
                  cursor: "pointer",
                  color: "var(--text-primary)",
                  fontWeight: showTypeDropdown ? 600 : 400,
                  whiteSpace: "nowrap",
                  transition: "color 0.15s, background 0.15s, border-color 0.15s",
                  aspectRatio: "1",
                }}
                title={t("regions.changePiiType")}
              >
                <LayerGroup size={16} variant="light" />
              </button>
              {showTypeDropdown && (
                <div
                  ref={typeDropdownRef}
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
                  {resolvedLabels.map((entry) => (
                    <button
                      key={entry.label}
                      onClick={(e) => {
                        e.stopPropagation();
                        // Apply to all selected regions (or just this one)
                        const targetIds = selectedRegionIds.length > 1 && selectedRegionIds.includes(region.id)
                          ? selectedRegionIds
                          : [region.id];
                        for (const id of targetIds) {
                          if (entry.label !== region.pii_type) {
                            onUpdateLabel?.(id, entry.label as PIIType);
                          }
                        }
                        setShowTypeDropdown(false);
                      }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        width: "100%",
                        padding: "6px 10px",
                        fontSize: 11,
                        fontWeight: entry.label === region.pii_type ? 700 : 400,
                        color: entry.label === region.pii_type ? "white" : "var(--text-primary)",
                        background: entry.label === region.pii_type ? "var(--bg-tertiary)" : "transparent",
                        border: "none",
                        cursor: "pointer",
                        textAlign: "left",
                        whiteSpace: "nowrap",
                      }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-tertiary)"; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = entry.label === region.pii_type ? "var(--bg-tertiary)" : "transparent"; }}
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
                onClear?.(region.id);
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
              title={t("regions.clearFromDocument")}
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
                onAction(region.id, region.action === "TOKENIZE" ? "PENDING" : "TOKENIZE");
              }}
              style={{
                padding: "8px",
                fontSize: 12,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                background: region.action === "TOKENIZE" ? "rgba(156,39,176,0.15)" : "transparent",
                border: region.action === "TOKENIZE" ? "1px solid #9c27b0" : "1px solid transparent",
                borderRadius: 4,
                cursor: "pointer",
                color: "#9c27b0",
                whiteSpace: "nowrap",
                boxShadow: region.action === "TOKENIZE" ? "0 0 6px rgba(156,39,176,0.3)" : "none",
                transition: "all 0.15s ease",
                aspectRatio: "1",
              }}
              title={region.action === "TOKENIZE" ? t("regions.undoTokenize") : t("regions.tokenize")}
            >
              <Key size={16} variant="light" />
            </button>

            {/* Remove */}
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                onAction(region.id, region.action === "REMOVE" ? "PENDING" : "REMOVE");
              }}
              style={{
                padding: "8px",
                fontSize: 12,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                background: region.action === "REMOVE" ? "rgba(244,67,54,0.15)" : "transparent",
                border: region.action === "REMOVE" ? "1px solid #f44336" : "1px solid transparent",
                borderRadius: 4,
                cursor: "pointer",
                color: "#f44336",
                whiteSpace: "nowrap",
                boxShadow: region.action === "REMOVE" ? "0 0 6px rgba(244,67,54,0.3)" : "none",
                transition: "all 0.15s ease",
                aspectRatio: "1",
              }}
              title={region.action === "REMOVE" ? t("regions.undoRemove") : t("regions.remove")}
            >
              <Trash2 size={16} variant="light" />
            </button>
          </div>
        </div>,
        portalTarget
      )}

      {/* Floating edit dialog - rendered via portal to escape userSelect:none */}
      {showEditPanel && portalTarget && createPortal(
        <div
          ref={dialogRef}
          role="dialog"
          aria-label={t("regions.editContent")}
          style={{
            position: "fixed",
            left: dialogPos.x,
            top: dialogPos.y,
            zIndex: 1000,
            background: "var(--bg-secondary)",
            borderRadius: 8,
            boxShadow: "0 4px 24px rgba(0,0,0,0.6)",
            minWidth: 320,
            maxWidth: 450,
            border: "1px solid var(--border-color)",
            userSelect: "text",
            WebkitUserSelect: "text",
          }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {/* Dialog header - draggable */}
          <div
            onMouseDown={(e) => {
              e.stopPropagation();
              setIsDraggingDialog(true);
              dialogDragStart.current = {
                mouseX: e.clientX,
                mouseY: e.clientY,
                startX: dialogPos.x,
                startY: dialogPos.y,
              };
            }}
            style={{
              padding: "10px 12px",
              background: "var(--bg-primary)",
              borderRadius: "8px 8px 0 0",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              borderBottom: "1px solid var(--border-color)",
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
              {t("regions.editContent")}
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowEditPanel(false);
              }}
              style={{
                background: "transparent",
                border: "none",
                padding: 4,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                color: "var(--text-secondary)",
              }}
              title={t("common.close")}
            >
              <X size={16} variant="light" />
            </button>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--border-color)" }}>
            <button
              onClick={() => setActiveTab("label")}
              style={{
                flex: 1,
                padding: "8px 12px",
                fontSize: 13,
                fontWeight: activeTab === "label" ? 600 : 400,
                background: activeTab === "label" ? "var(--bg-primary)" : "transparent",
                border: "none",
                cursor: "pointer",
                color: activeTab === "label" ? "var(--text-primary)" : "var(--text-secondary)",
                display: "flex",
                alignItems: "center",
                gap: 6,
                justifyContent: "center",
              }}
            >
              <Tag size={14} variant="light" />
              {t("regions.labelTab")}
            </button>
            <button
              onClick={() => setActiveTab("content")}
              style={{
                flex: 1,
                padding: "8px 12px",
                fontSize: 13,
                fontWeight: activeTab === "content" ? 600 : 400,
                background: activeTab === "content" ? "var(--bg-primary)" : "transparent",
                border: "none",
                cursor: "pointer",
                color: activeTab === "content" ? "var(--text-primary)" : "var(--text-secondary)",
                display: "flex",
                alignItems: "center",
                gap: 6,
                justifyContent: "center",
              }}
            >
              <Edit3 size={14} variant="light" />
              {t("regions.contentTab")}
            </button>
          </div>

          {/* Tab content */}
          <div style={{ padding: 12, userSelect: "text", WebkitUserSelect: "text" }}>
            {activeTab === "label" ? (
              <div>
                {/* Label selector */}
                {!isEditingLabel ? (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>{t("regions.piiType")}</div>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                        {region.pii_type}
                      </span>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setIsEditingLabel(true)}
                        title={t("regions.change")}
                        style={{ padding: "2px 6px", fontSize: 11 }}
                      >
                        {t("regions.change")}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>{t("regions.selectPIIType")}</div>
                    <select
                      autoFocus
                      value={region.pii_type}
                      onChange={(e) => {
                        onUpdateLabel?.(region.id, e.target.value as PIIType);
                        setIsEditingLabel(false);
                      }}
                      onBlur={() => setIsEditingLabel(false)}
                      style={{
                        width: "100%",
                        padding: "6px 8px",
                        fontSize: 13,
                        background: "var(--bg-primary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: 4,
                        color: "var(--text-primary)",
                      }}
                    >
                      {loadLabelConfig().filter((e) => !e.hidden).map((entry) => (
                        <option key={entry.label} value={entry.label}>{entry.label}</option>
                      ))}
                      {/* Ensure current value is always present even if hidden */}
                      {!loadLabelConfig().some((e) => !e.hidden && e.label === region.pii_type) && (
                        <option value={region.pii_type}>{region.pii_type}</option>
                      )}
                    </select>
                  </div>
                )}

                {/* Confidence */}
                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 8 }}>
                  {t("regions.confidence")} <span style={{ fontWeight: 600 }}>{Math.round(region.confidence * 100)}%</span>
                </div>
              </div>
            ) : (
              <div>
                {/* Content text - editable only for images */}
                {!isEditingText ? (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>{t("regions.detectedText")}</div>
                    <div style={{ 
                      fontSize: 13, 
                      color: "var(--text-primary)", 
                      padding: "8px",
                      background: "var(--bg-primary)",
                      borderRadius: 4,
                      wordBreak: "break-word",
                      maxHeight: 120,
                      overflow: "auto",
                    }}>
                      "{region.text}"
                    </div>
                    {onUpdateText && (
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => {
                          setEditedText(region.text);
                          setIsEditingText(true);
                        }}
                        title={t("regions.editText")}
                        style={{ padding: "6px 10px", fontSize: 12, marginTop: 8 }}
                      >
                        {t("regions.editText")}
                      </button>
                    )}
                  </div>
                ) : (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>{t("regions.editTextLabel")}</div>
                    <textarea
                      autoFocus
                      value={editedText}
                      onChange={(e) => setEditedText(e.target.value)}
                      onMouseDown={(e) => e.stopPropagation()}
                      style={{
                        width: "100%",
                        minHeight: 80,
                        padding: "8px",
                        fontSize: 13,
                        background: "var(--bg-primary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: 4,
                        color: "var(--text-primary)",
                        resize: "vertical",
                        fontFamily: "inherit",
                        userSelect: "text",
                        WebkitUserSelect: "text",
                      }}
                    />
                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                      <button
                        className="btn-primary btn-sm"
                        onClick={() => {
                          onUpdateText?.(region.id, editedText);
                          setIsEditingText(false);
                        }}
                        style={{ padding: "6px 16px", fontSize: 12 }}
                      >
                        {t("common.save")}
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => {
                          setEditedText(region.text);
                          setIsEditingText(false);
                        }}
                        style={{ padding: "6px 16px", fontSize: 12 }}
                      >
                        {t("common.cancel")}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>,
        portalTarget
      )}
    </>
  );
}

export default memo(RegionOverlay);
