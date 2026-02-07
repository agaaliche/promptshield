/**
 * PII region overlay — semi-transparent rectangle with action buttons.
 * Supports move (drag the body) and resize (drag corner/edge handles).
 */

import { PII_COLORS, type PIIRegion, type RegionAction } from "../types";
import { X, Trash2, Key } from "lucide-react";

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
  onSelect: () => void;
  onAction: (regionId: string, action: RegionAction) => void;
  onMoveStart?: (regionId: string, e: React.MouseEvent) => void;
  onResizeStart?: (
    regionId: string,
    handle: ResizeHandle,
    e: React.MouseEvent,
  ) => void;
}

export default function RegionOverlay({
  region,
  pageWidth,
  pageHeight,
  imgWidth,
  imgHeight,
  isSelected,
  onSelect,
  onAction,
  onMoveStart,
  onResizeStart,
}: Props) {
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

  const borderColor = PII_COLORS[region.pii_type] || "#ffd740";

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
          border: `2px solid ${borderColor}`,
          borderRadius: 2,
          cursor: isSelected ? "move" : "pointer",
          zIndex: isSelected ? 5 : 2,
          transition: isSelected ? "none" : "all 0.15s ease",
          boxShadow: isSelected ? `0 0 0 2px ${borderColor}` : "none",
        }}
        onMouseDown={(e) => {
          e.stopPropagation();
          if (onMoveStart) {
            onMoveStart(region.id, e);
          } else {
            onSelect();
          }
        }}
        title={`${region.pii_type}: "${region.text}" (${Math.round(region.confidence * 100)}%)`}
      >
        {/* Resize handles — only visible when selected */}
        {isSelected &&
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

      {/* Action buttons — shown below the highlight */}
      {(isSelected || region.action === "PENDING") && (
        <div
          style={{
            position: "absolute",
            left: left,
            top: top + height + 4,
            display: "flex",
            gap: 3,
            zIndex: 6,
            background: "var(--bg-secondary)",
            borderRadius: 4,
            padding: 3,
            boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
          }}
        >
          <button
            className="btn-ghost btn-sm"
            onClick={(e) => {
              e.stopPropagation();
              onAction(region.id, "CANCEL");
            }}
            title="Cancel — keep original content"
            style={{ padding: "2px 6px" }}
          >
            <X size={12} />
          </button>
          <button
            className="btn-danger btn-sm"
            onClick={(e) => {
              e.stopPropagation();
              onAction(region.id, "REMOVE");
            }}
            title="Remove — permanently redact"
            style={{ padding: "2px 6px" }}
          >
            <Trash2 size={12} />
          </button>
          <button
            className="btn-tokenize btn-sm"
            onClick={(e) => {
              e.stopPropagation();
              onAction(region.id, "TOKENIZE");
            }}
            title="Tokenize — replace with reversible token"
            style={{ padding: "2px 6px" }}
          >
            <Key size={12} />
          </button>
        </div>
      )}

      {/* PII type label */}
      <div
        style={{
          position: "absolute",
          left: left,
          top: top - 16,
          fontSize: 9,
          fontWeight: 600,
          color: "white",
          background: borderColor,
          padding: "1px 4px",
          borderRadius: "3px 3px 0 0",
          zIndex: 3,
          whiteSpace: "nowrap",
        }}
      >
        {region.pii_type}
      </div>
    </>
  );
}
