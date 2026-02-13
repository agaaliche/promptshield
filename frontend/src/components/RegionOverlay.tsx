/**
 * PII region overlay — semi-transparent rectangle with action buttons.
 * Supports move (drag the body) and resize (drag corner/edge handles).
 */

import { useState, useRef, useEffect, memo } from "react";
import { createPortal } from "react-dom";
import { PII_COLORS, getPIIColor, loadLabelConfig, type PIIRegion, type RegionAction, type PIIType } from "../types";
import { CURSOR_GRAB, CURSOR_GRABBING } from "../cursors";
import { X, Trash2, Key, Edit3, Tag, ChevronRight, ChevronLeft, Type, Search } from "lucide-react";

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
let _cachedToolbarExpanded: boolean | null = null;
let _cachedToolbarPos: { x: number; y: number } | null | undefined = undefined;
let _cachedDialogPos: { x: number; y: number } | null = null;

function getCachedToolbarExpanded(): boolean {
  if (_cachedToolbarExpanded !== null) return _cachedToolbarExpanded;
  try {
    _cachedToolbarExpanded = localStorage.getItem('regionToolbarExpanded') === 'true';
  } catch (_e) {
    _cachedToolbarExpanded = false;
  }
  return _cachedToolbarExpanded;
}

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
  portalTarget?: HTMLElement | null;
  imageContainerEl?: HTMLElement | null;
  cursorToolbarExpanded?: boolean;
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
  portalTarget,
  imageContainerEl,
  cursorToolbarExpanded,
}: Props) {
  const [showEditPanel, setShowEditPanel] = useState(false);
  const [toolbarExpanded, setToolbarExpanded] = useState(getCachedToolbarExpanded);
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

  // Toolbar drag handlers (fixed/viewport coordinates, same as cursor toolbar)
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

      // Clamp within content area (viewport coords, same bounds as cursor toolbar)
      const area = portalTarget;
      if (area) {
        const areaRect = area.getBoundingClientRect();
        const minX = areaRect.left + PAD;
        const minY = areaRect.top + PAD;
        const maxX = areaRect.right - tb.offsetWidth - PAD;
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
  }, [isDraggingToolbar, portalTarget]);

  // Save toolbar offset to localStorage + module cache
  useEffect(() => {
    _cachedToolbarPos = toolbarPos;
    try {
      localStorage.setItem('regionToolbarPos', JSON.stringify(toolbarPos));
    } catch (e) {
      console.error('Failed to save toolbar offset:', e);
    }
  }, [toolbarPos]);

  // Save toolbar expanded state to localStorage + module cache
  useEffect(() => {
    _cachedToolbarExpanded = toolbarExpanded;
    try {
      localStorage.setItem('regionToolbarExpanded', String(toolbarExpanded));
    } catch (e) {
      console.error('Failed to save toolbar expanded state:', e);
    }
  }, [toolbarExpanded]);

  // Dialog drag handlers
  useEffect(() => {
    if (!isDraggingDialog) return;
    
    const handleMouseMove = (e: MouseEvent) => {
      const PAD = 4;
      const dx = e.clientX - dialogDragStart.current.mouseX;
      const dy = e.clientY - dialogDragStart.current.mouseY;
      const newX = Math.max(PAD, Math.min(window.innerWidth - PAD - 320, dialogDragStart.current.startX + dx));
      const newY = Math.max(PAD, Math.min(window.innerHeight - PAD - 100, dialogDragStart.current.startY + dy));
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
  }, [isDraggingDialog]);

  // Save dialog position to localStorage + module cache
  useEffect(() => {
    _cachedDialogPos = dialogPos;
    try {
      localStorage.setItem('regionDialogPos', JSON.stringify(dialogPos));
    } catch (e) {
      console.error('Failed to save dialog position:', e);
    }
  }, [dialogPos]);

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

  // Clamp toolbar position to stay within document (image) bounds + 4px padding
  useEffect(() => {
    if (!showDetails || !toolbarRef.current || !toolbarPos) return;
    const PAD = 4;
    const area = portalTarget;
    const img = imageContainerEl;
    const tb = toolbarRef.current;
    if (!area || !img) return;
    const w = tb.offsetWidth;
    const h = tb.offsetHeight;
    if (w === 0 || h === 0) return;
    const areaRect = area.getBoundingClientRect();
    const imgRect = img.getBoundingClientRect();
    const imgLeft = imgRect.left - areaRect.left;
    const imgTop = imgRect.top - areaRect.top;
    const minX = imgLeft + PAD;
    const minY = imgTop + PAD;
    const maxX = imgLeft + imgRect.width - w - PAD;
    const maxY = imgTop + imgRect.height - h - PAD;
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
  }, [showDetails, toolbarExpanded, toolbarPos, portalTarget, imageContainerEl, cursorToolbarExpanded]);

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
            overflow: "hidden",
            userSelect: "none",
            cursor: isDraggingToolbar ? CURSOR_GRABBING : "default",
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
              padding: "4px 6px",
              background: "var(--bg-primary)",
              cursor: isDraggingToolbar ? CURSOR_GRABBING : CURSOR_GRAB,
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
                setToolbarExpanded(!toolbarExpanded);
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
              title={toolbarExpanded ? "Collapse" : "Expand"}
            >
              {toolbarExpanded ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
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
                onHighlightAll?.(region.id);
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
              title="Replace all matching"
              className="btn-ghost btn-sm"
            >
              <Type size={16} />
              {toolbarExpanded && "Replace all"}
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
                gap: 8,
                background: "transparent",
                border: "1px solid transparent",
                borderRadius: 4,
                cursor: "pointer",
                color: "var(--text-primary)",
                whiteSpace: "nowrap",
              }}
              title="Detect — re-analyze"
              className="btn-ghost btn-sm"
            >
              <Search size={16} />
              {toolbarExpanded && "Detect"}
            </button>

            {/* Edit */}
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                setShowEditPanel(!showEditPanel);
              }}
              style={{
                padding: "8px",
                fontSize: 12,
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: showEditPanel ? "var(--bg-primary)" : "transparent",
                border: "1px solid transparent",
                borderRadius: 4,
                cursor: "pointer",
                color: "var(--text-primary)",
                fontWeight: showEditPanel ? 600 : 400,
                whiteSpace: "nowrap",
              }}
              title="Edit label/content"
              className="btn-ghost btn-sm"
            >
              <Edit3 size={16} />
              {toolbarExpanded && "Edit"}
            </button>

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
              {toolbarExpanded && "Clear"}
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
                gap: 8,
                background: region.action === "TOKENIZE" ? "rgba(156,39,176,0.15)" : "transparent",
                border: region.action === "TOKENIZE" ? "1px solid #9c27b0" : "1px solid transparent",
                borderRadius: 4,
                cursor: "pointer",
                color: "#9c27b0",
                whiteSpace: "nowrap",
                boxShadow: region.action === "TOKENIZE" ? "0 0 6px rgba(156,39,176,0.3)" : "none",
                transition: "all 0.15s ease",
              }}
              title={region.action === "TOKENIZE" ? "Undo tokenize" : "Tokenize"}
              className="btn-tokenize btn-sm"
            >
              <Key size={16} />
              {toolbarExpanded && "Tokenize"}
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
                gap: 8,
                background: region.action === "REMOVE" ? "rgba(244,67,54,0.15)" : "transparent",
                border: region.action === "REMOVE" ? "1px solid #f44336" : "1px solid transparent",
                borderRadius: 4,
                cursor: "pointer",
                color: "#f44336",
                whiteSpace: "nowrap",
                boxShadow: region.action === "REMOVE" ? "0 0 6px rgba(244,67,54,0.3)" : "none",
                transition: "all 0.15s ease",
              }}
              title={region.action === "REMOVE" ? "Undo remove" : "Remove"}
              className="btn-danger btn-sm"
            >
              <Trash2 size={16} />
              {toolbarExpanded && "Remove"}
            </button>
          </div>
        </div>,
        portalTarget
      )}

      {/* Floating edit dialog - shown when edit is active */}
      {showEditPanel && (
        <div
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
              cursor: isDraggingDialog ? CURSOR_GRABBING : CURSOR_GRAB,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              borderBottom: "1px solid var(--border-color)",
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
              Edit Content
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
              title="Close"
            >
              <X size={16} />
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
              <Tag size={14} />
              Label
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
              <Edit3 size={14} />
              Content
            </button>
          </div>

          {/* Tab content */}
          <div style={{ padding: 12 }}>
            {activeTab === "label" ? (
              <div>
                {/* Label selector */}
                {!isEditingLabel ? (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>PII Type:</div>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                        {region.pii_type}
                      </span>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setIsEditingLabel(true)}
                        title="Change label"
                        style={{ padding: "2px 6px", fontSize: 11 }}
                      >
                        Change
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>Select PII Type:</div>
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
                  Confidence: <span style={{ fontWeight: 600 }}>{Math.round(region.confidence * 100)}%</span>
                </div>
              </div>
            ) : (
              <div>
                {/* Content text - editable only for images */}
                {!isEditingText ? (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>Detected Text:</div>
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
                    {isImageFile && onUpdateText && (
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => {
                          setEditedText(region.text);
                          setIsEditingText(true);
                        }}
                        title="Edit text (images only)"
                        style={{ padding: "6px 10px", fontSize: 12, marginTop: 8 }}
                      >
                        Edit Text
                      </button>
                    )}
                  </div>
                ) : (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>Edit Text:</div>
                    <textarea
                      autoFocus
                      value={editedText}
                      onChange={(e) => setEditedText(e.target.value)}
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
                        Save
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => {
                          setEditedText(region.text);
                          setIsEditingText(false);
                        }}
                        style={{ padding: "6px 16px", fontSize: 12 }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default memo(RegionOverlay);
