import React from "react";
import {
  MousePointer,
  BoxSelect,
  PenTool,
  Undo2,
  Redo2,
} from "../icons";
import { useState } from "react";
import { useTranslation } from "react-i18next";

interface CursorToolToolbarProps {
  cursorToolbarRef: React.RefObject<HTMLDivElement | null>;
  cursorToolbarPos: { x: number; y: number };
  isDragging: boolean;
  startDrag: (e: React.MouseEvent) => void;
  cursorTool: "pointer" | "lasso" | "draw";
  setCursorTool: (t: "pointer" | "lasso" | "draw") => void;
  canUndo: boolean;
  canRedo: boolean;
  undo: () => void;
  redo: () => void;
}

export default function CursorToolToolbar({
  cursorToolbarRef,
  cursorToolbarPos,
  isDragging,
  startDrag,
  cursorTool,
  setCursorTool,
  canUndo,
  canRedo,
  undo,
  redo,
}: CursorToolToolbarProps) {
  const { t } = useTranslation();
  const [hoveredTool, setHoveredTool] = useState<string | null>(null);

  const TOOL_COLORS: Record<string, string> = {
    pointer: "#4a9eff",
    lasso: "#f5a623",
    draw: "#4caf50",
  };

  const getToolColor = (tool: string) => {
    const isActive = cursorTool === tool;
    const isHovered = hoveredTool === tool;
    if (isActive || isHovered) return TOOL_COLORS[tool];
    return "var(--text-primary)";
  };

  const getToolBorder = (tool: string) => {
    if (cursorTool === tool) return `1px solid ${TOOL_COLORS[tool]}`;
    return "1px solid transparent";
  };

  const getToolBg = (tool: string) => {
    if (cursorTool === tool) return "var(--bg-primary)";
    return "transparent";
  };

  return (
    <div
      ref={cursorToolbarRef}
      data-cursor-toolbar
      onMouseDown={(e) => e.stopPropagation()}
      style={{
        position: "fixed",
        top: cursorToolbarPos.y,
        left: cursorToolbarPos.x,
        zIndex: 30,
        background: "var(--bg-secondary)",
        borderRadius: 8,
        boxShadow: "0 2px 12px rgba(0,0,0,0.5)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
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
        <div
          style={{
            width: 24,
            height: 4,
            background: TOOL_COLORS[cursorTool] || "var(--text-secondary)",
            borderRadius: 2,
            opacity: 0.5,
          }}
        />
      </div>

      {/* Toolbar buttons */}
      <div
        onMouseDown={(e) => e.stopPropagation()}
        style={{ padding: 4, display: "flex", flexDirection: "column", gap: 2 }}
      >
        {/* Pointer */}
        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            setCursorTool("pointer");
          }}
          onMouseEnter={() => setHoveredTool("pointer")}
          onMouseLeave={() => setHoveredTool(null)}
          style={{
            padding: 8,
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            background: getToolBg("pointer"),
            border: getToolBorder("pointer"),
            borderRadius: 4,
            cursor: "pointer",
            color: getToolColor("pointer"),
            fontWeight: cursorTool === "pointer" ? 600 : 400,
            whiteSpace: "nowrap",
            transition: "color 0.15s, background 0.15s, border-color 0.15s",
            aspectRatio: "1",
          }}
          title={t("tools.pointerTooltip")}
        >
          <MousePointer size={16} variant="light" />
        </button>

        {/* Lasso */}
        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            setCursorTool("lasso");
          }}
          onMouseEnter={() => setHoveredTool("lasso")}
          onMouseLeave={() => setHoveredTool(null)}
          style={{
            padding: 8,
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            background: getToolBg("lasso"),
            border: getToolBorder("lasso"),
            borderRadius: 4,
            cursor: "pointer",
            color: getToolColor("lasso"),
            fontWeight: cursorTool === "lasso" ? 600 : 400,
            whiteSpace: "nowrap",
            transition: "color 0.15s, background 0.15s, border-color 0.15s",
            aspectRatio: "1",
          }}
          title={t("tools.lassoTooltip")}
        >
          <BoxSelect size={16} variant="light" />
        </button>

        {/* Draw */}
        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            setCursorTool("draw");
          }}
          onMouseEnter={() => setHoveredTool("draw")}
          onMouseLeave={() => setHoveredTool(null)}
          style={{
            padding: 8,
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            background: getToolBg("draw"),
            border: getToolBorder("draw"),
            borderRadius: 4,
            cursor: "pointer",
            color: getToolColor("draw"),
            fontWeight: cursorTool === "draw" ? 600 : 400,
            whiteSpace: "nowrap",
            transition: "color 0.15s, background 0.15s, border-color 0.15s",
            aspectRatio: "1",
          }}
          title={t("tools.drawTooltip")}
        >
          <PenTool size={16} variant="light" />
        </button>

        {/* Separator */}
        <div
          style={{
            height: 1,
            background: "rgba(255,255,255,0.15)",
            margin: "2px 4px",
          }}
        />

        {/* Undo */}
        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            undo();
          }}
          disabled={!canUndo}
          style={{
            padding: 8,
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            background: "transparent",
            border: "1px solid transparent",
            borderRadius: 4,
            cursor: canUndo ? "pointer" : "default",
            color: canUndo ? "var(--text-primary)" : "var(--text-secondary)",
            opacity: canUndo ? 1 : 0.4,
            whiteSpace: "nowrap",
            aspectRatio: "1",
          }}
          title={t("tools.undoTooltip")}
        >
          <Undo2 size={16} variant="light" />
        </button>

        {/* Redo */}
        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            redo();
          }}
          disabled={!canRedo}
          style={{
            padding: 8,
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            background: "transparent",
            border: "1px solid transparent",
            borderRadius: 4,
            cursor: canRedo ? "pointer" : "default",
            color: canRedo ? "var(--text-primary)" : "var(--text-secondary)",
            opacity: canRedo ? 1 : 0.4,
            whiteSpace: "nowrap",
            aspectRatio: "1",
          }}
          title={t("tools.redoTooltip")}
        >
          <Redo2 size={16} variant="light" />
        </button>
      </div>
    </div>
  );
}
