/**
 * PII region overlay — semi-transparent rectangle with action buttons.
 * Supports move (drag the body) and resize (drag corner/edge handles).
 */

import { useState, useRef, useEffect } from "react";
import { PII_COLORS, type PIIRegion, type RegionAction, type PIIType } from "../types";
import { X, Trash2, Key, RefreshCw, Highlighter, Edit3, Tag, ChevronRight, ChevronLeft } from "lucide-react";

export type ResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

const HANDLE_SIZE = 8;
const HALF = HANDLE_SIZE / 2;

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
}

export default function RegionOverlay({
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
  onRefresh,
  onHighlightAll,
  onMoveStart,
  onResizeStart,
  onUpdateLabel,
  onUpdateText,
}: Props) {
  const [showEditPanel, setShowEditPanel] = useState(false);
  const [toolbarExpanded, setToolbarExpanded] = useState(() => {
    try {
      const saved = localStorage.getItem('regionToolbarExpanded');
      return saved === 'true';
    } catch (e) {
      console.error('Failed to load toolbar expanded state:', e);
    }
    return false;
  });
  const [activeTab, setActiveTab] = useState<"label" | "content">("label");
  const [isEditingLabel, setIsEditingLabel] = useState(false);
  const [isEditingText, setIsEditingText] = useState(false);
  const [editedText, setEditedText] = useState(region.text);
  
  // Toolbar position (relative to region)
  const [toolbarOffset, setToolbarOffset] = useState(() => {
    try {
      const saved = localStorage.getItem('regionToolbarOffset');
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (e) {
      console.error('Failed to load toolbar offset:', e);
    }
    return { x: 0, y: 0 };
  });
  const [isDraggingToolbar, setIsDraggingToolbar] = useState(false);
  const toolbarDragStart = useRef({ mouseX: 0, mouseY: 0, offsetX: 0, offsetY: 0 });
  const toolbarRef = useRef<HTMLDivElement>(null);
  
  // Edit dialog position (viewport coordinates)
  const [dialogPos, setDialogPos] = useState(() => {
    try {
      const saved = localStorage.getItem('regionDialogPos');
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (e) {
      console.error('Failed to load dialog position:', e);
    }
    return { x: 300, y: 100 };
  });
  const [isDraggingDialog, setIsDraggingDialog] = useState(false);
  const dialogDragStart = useRef({ mouseX: 0, mouseY: 0, startX: 0, startY: 0 });
  
  // Convert page coordinates → pixel coordinates on the displayed image
  const sx = imgWidth / pageWidth;
  const sy = imgHeight / pageHeight;

  const left = region.bbox.x0 * sx;
  const top = region.bbox.y0 * sy;
  const width = (region.bbox.x1 - region.bbox.x0) * sx;
  const height = (region.bbox.y1 - region.bbox.y0) * sy;

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

  // Darker shade of yellow for selected border
  const baseBorderColor = PII_COLORS[region.pii_type] || "#ffd740";
  const borderColor = (isSelected || showEditPanel) ? "#cca000" : baseBorderColor;
  const [hovered, setHovered] = useState(false);
  // In multi-select mode: only show frame and border, no label/buttons
  const soloSelected = isSelected && !isMultiSelected;
  // Keep toolbar visible when edit panel is open
  const showDetails = (hovered && !isMultiSelected) || soloSelected || showEditPanel;
  const showFrame = hovered || isSelected || isMultiSelected || showEditPanel;

  // Toolbar drag handlers
  useEffect(() => {
    if (!isDraggingToolbar) return;
    
    const handleMouseMove = (e: MouseEvent) => {
      const dx = e.clientX - toolbarDragStart.current.mouseX;
      const dy = e.clientY - toolbarDragStart.current.mouseY;
      
      let newOffsetX = toolbarDragStart.current.offsetX + dx;
      let newOffsetY = toolbarDragStart.current.offsetY + dy;
      
      // Clamp toolbar position to stay within document boundaries
      const toolbarWidth = toolbarRef.current?.offsetWidth || 50;
      const toolbarHeight = toolbarRef.current?.offsetHeight || 300;
      
      const toolbarLeft = left + width + 8 + newOffsetX;
      const toolbarTop = top + newOffsetY;
      
      // Clamp horizontal position
      if (toolbarLeft < 0) {
        newOffsetX = -(left + width + 8);
      } else if (toolbarLeft + toolbarWidth > imgWidth) {
        newOffsetX = imgWidth - (left + width + 8 + toolbarWidth);
      }
      
      // Clamp vertical position
      if (toolbarTop < 0) {
        newOffsetY = -top;
      } else if (toolbarTop + toolbarHeight > imgHeight) {
        newOffsetY = imgHeight - (top + toolbarHeight);
      }
      
      setToolbarOffset({
        x: newOffsetX,
        y: newOffsetY,
      });
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
  }, [isDraggingToolbar, left, width, top, imgWidth, imgHeight]);

  // Save toolbar offset to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('regionToolbarOffset', JSON.stringify(toolbarOffset));
    } catch (e) {
      console.error('Failed to save toolbar offset:', e);
    }
  }, [toolbarOffset]);

  // Save toolbar expanded state to localStorage
  useEffect(() => {
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
      const dx = e.clientX - dialogDragStart.current.mouseX;
      const dy = e.clientY - dialogDragStart.current.mouseY;
      setDialogPos({
        x: dialogDragStart.current.startX + dx,
        y: dialogDragStart.current.startY + dy,
      });
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

  // Save dialog position to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('regionDialogPos', JSON.stringify(dialogPos));
    } catch (e) {
      console.error('Failed to save dialog position:', e);
    }
  }, [dialogPos]);

  // Clamp toolbar position to stay within document boundaries
  useEffect(() => {
    if (!showDetails || !toolbarRef.current) return;
    
    const toolbarWidth = toolbarRef.current.offsetWidth;
    const toolbarHeight = toolbarRef.current.offsetHeight;
    
    if (toolbarWidth === 0 || toolbarHeight === 0) return; // Not rendered yet
    
    const toolbarLeft = left + width + 8 + toolbarOffset.x;
    const toolbarTop = top + toolbarOffset.y;
    
    let needsAdjustment = false;
    let newOffsetX = toolbarOffset.x;
    let newOffsetY = toolbarOffset.y;
    
    // Check horizontal bounds
    if (toolbarLeft < 0) {
      newOffsetX = -(left + width + 8);
      needsAdjustment = true;
    } else if (toolbarLeft + toolbarWidth > imgWidth) {
      newOffsetX = imgWidth - (left + width + 8 + toolbarWidth);
      needsAdjustment = true;
    }
    
    // Check vertical bounds
    if (toolbarTop < 0) {
      newOffsetY = -top;
      needsAdjustment = true;
    } else if (toolbarTop + toolbarHeight > imgHeight) {
      newOffsetY = imgHeight - (top + toolbarHeight);
      needsAdjustment = true;
    }
    
    if (needsAdjustment) {
      setToolbarOffset({ x: newOffsetX, y: newOffsetY });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showDetails, left, width, top, imgWidth, imgHeight, toolbarExpanded]);

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
        style={{
          position: "absolute",
          left,
          top,
          width,
          height,
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
        title={`${region.pii_type}: "${region.text}" (${Math.round(region.confidence * 100)}%)`}
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
      {showDetails && (
        <div
          onMouseDown={(e) => e.stopPropagation()}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          style={{
            position: "absolute",
            left: left,
            top: top - 26,
            zIndex: 6,
            background: borderColor,
            color: "#000",
            padding: "4px 10px",
            borderRadius: "4px 4px 0 0",
            fontSize: 13,
            fontWeight: 600,
            whiteSpace: "nowrap",
          }}
        >
          {region.pii_type}
        </div>
      )}

      {/* Vertical toolbar - draggable */}
      {showDetails && (
        <div
          ref={toolbarRef}
          onMouseDown={(e) => e.stopPropagation()}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          style={{
            position: "absolute",
            left: left + width + 8 + toolbarOffset.x,
            top: top + toolbarOffset.y,
            zIndex: 6,
            background: "var(--bg-secondary)",
            borderRadius: 8,
            boxShadow: "0 2px 12px rgba(0,0,0,0.5)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            cursor: isDraggingToolbar ? "grabbing" : "default",
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
                offsetX: toolbarOffset.x,
                offsetY: toolbarOffset.y,
              };
            }}
            style={{
              padding: "4px 6px",
              background: "var(--bg-primary)",
              cursor: isDraggingToolbar ? "grabbing" : "grab",
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
            
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                onAction(region.id, "CANCEL");
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
              title="Cancel — keep original"
              className="btn-ghost btn-sm"
            >
              <X size={16} />
              {toolbarExpanded && "Cancel"}
            </button>
            
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
              title="Refresh — re-analyze"
              className="btn-ghost btn-sm"
            >
              <RefreshCw size={16} />
              {toolbarExpanded && "Refresh"}
            </button>
            
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
              title="Highlight all"
              className="btn-ghost btn-sm"
            >
              <Highlighter size={16} />
              {toolbarExpanded && "All"}
            </button>
            
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                onAction(region.id, "REMOVE");
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
              {toolbarExpanded && "Remove"}
            </button>
            
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                onAction(region.id, "TOKENIZE");
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
              {toolbarExpanded && "Tokenize"}
            </button>
          </div>
        </div>
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
              cursor: isDraggingDialog ? "grabbing" : "grab",
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
                      <option value="PERSON">PERSON</option>
                      <option value="ORG">ORG</option>
                      <option value="EMAIL">EMAIL</option>
                      <option value="PHONE">PHONE</option>
                      <option value="SSN">SSN</option>
                      <option value="CREDIT_CARD">CREDIT_CARD</option>
                      <option value="DATE">DATE</option>
                      <option value="ADDRESS">ADDRESS</option>
                      <option value="LOCATION">LOCATION</option>
                      <option value="IP_ADDRESS">IP_ADDRESS</option>
                      <option value="IBAN">IBAN</option>
                      <option value="PASSPORT">PASSPORT</option>
                      <option value="DRIVER_LICENSE">DRIVER_LICENSE</option>
                      <option value="CUSTOM">CUSTOM</option>
                      <option value="UNKNOWN">UNKNOWN</option>
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
