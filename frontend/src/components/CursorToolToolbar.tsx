import React from "react";
import {
  MousePointer,
  BoxSelect,
  PenTool,
  Undo2,
  Redo2,
  ChevronLeft,
  ChevronRight,
} from "../icons";
import { useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";

interface CursorToolToolbarProps {
  cursorToolbarRef: React.RefObject<HTMLDivElement | null>;
  cursorToolbarPos: { x: number; y: number };
  isDragging: boolean;
  startDrag: (e: React.MouseEvent) => void;
  expanded: boolean;
  setExpanded: (v: boolean) => void;
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
  expanded,
  setExpanded,
  cursorTool,
  setCursorTool,
  canUndo,
  canRedo,
  undo,
  redo,
}: CursorToolToolbarProps) {
  const { t } = useTranslation();
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
        <div
          style={{
            width: 24,
            height: 4,
            background: "var(--text-secondary)",
            borderRadius: 2,
            opacity: 0.5,
          }}
        />
        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(!expanded);
            try {
              localStorage.setItem("cursorToolbarExpanded", String(!expanded));
            } catch {}
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
          title={expanded ? t("tools.collapse") : t("tools.expand")}
        >
          {expanded ? <ChevronLeft size={14} variant="light" /> : <ChevronRight size={14} variant="light" />}
        </button>
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
          style={{
            padding: "8px",
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: expanded ? "flex-start" : "center",
            gap: 8,
            background:
              cursorTool === "pointer" ? "var(--bg-primary)" : "transparent",
            border:
              cursorTool === "pointer"
                ? "1px solid var(--accent-primary)"
                : "1px solid transparent",
            borderRadius: 4,
            cursor: "pointer",
            color:
              cursorTool === "pointer"
                ? "var(--accent-primary)"
                : "var(--text-primary)",
            fontWeight: cursorTool === "pointer" ? 600 : 400,
            whiteSpace: "nowrap",
          }}
          title={t("tools.pointerTooltip")}
        >
          <MousePointer size={16} variant="light" />
          {expanded && t("tools.pointer")}
        </button>

        {/* Lasso */}
        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            setCursorTool("lasso");
          }}
          style={{
            padding: "8px",
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: expanded ? "flex-start" : "center",
            gap: 8,
            background:
              cursorTool === "lasso" ? "var(--bg-primary)" : "transparent",
            border:
              cursorTool === "lasso"
                ? "1px solid var(--accent-primary)"
                : "1px solid transparent",
            borderRadius: 4,
            cursor: "pointer",
            color:
              cursorTool === "lasso"
                ? "var(--accent-primary)"
                : "var(--text-primary)",
            fontWeight: cursorTool === "lasso" ? 600 : 400,
            whiteSpace: "nowrap",
          }}
          title={t("tools.lassoTooltip")}
        >
          <BoxSelect size={16} variant="light" />
          {expanded && t("tools.lasso")}
        </button>

        {/* Draw */}
        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            setCursorTool("draw");
          }}
          style={{
            padding: "8px",
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: expanded ? "flex-start" : "center",
            gap: 8,
            background:
              cursorTool === "draw" ? "var(--bg-primary)" : "transparent",
            border:
              cursorTool === "draw"
                ? "1px solid var(--accent-primary)"
                : "1px solid transparent",
            borderRadius: 4,
            cursor: "pointer",
            color:
              cursorTool === "draw"
                ? "var(--accent-primary)"
                : "var(--text-primary)",
            fontWeight: cursorTool === "draw" ? 600 : 400,
            whiteSpace: "nowrap",
          }}
          title={t("tools.drawTooltip")}
        >
          <PenTool size={16} variant="light" />
          {expanded && t("tools.draw")}
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
            padding: "8px",
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: expanded ? "flex-start" : "center",
            gap: 8,
            background: "transparent",
            border: "1px solid transparent",
            borderRadius: 4,
            cursor: canUndo ? "pointer" : "default",
            color: canUndo ? "var(--text-primary)" : "var(--text-secondary)",
            opacity: canUndo ? 1 : 0.4,
            whiteSpace: "nowrap",
          }}
          title={t("tools.undoTooltip")}
        >
          <Undo2 size={16} variant="light" />
          {expanded && t("tools.undo")}
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
            padding: "8px",
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: expanded ? "flex-start" : "center",
            gap: 8,
            background: "transparent",
            border: "1px solid transparent",
            borderRadius: 4,
            cursor: canRedo ? "pointer" : "default",
            color: canRedo ? "var(--text-primary)" : "var(--text-secondary)",
            opacity: canRedo ? 1 : 0.4,
            whiteSpace: "nowrap",
          }}
          title={t("tools.redoTooltip")}
        >
          <Redo2 size={16} variant="light" />
          {expanded && t("tools.redo")}
        </button>
      </div>
    </div>
  );
}
