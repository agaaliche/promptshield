/**
 * useViewerToolbars — UI chrome state: cursor tool mode, floating toolbar
 * positions/expanded state, sidebar collapse, type filter, page navigator,
 * multi-select edit dialog.
 *
 * Extracted from DocumentViewer to reduce component size.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import useDraggableToolbar from "./useDraggableToolbar";

type CursorTool = "pointer" | "lasso" | "draw";

interface UseViewerToolbarsOpts {
  setDrawMode: (v: boolean) => void;
}

export default function useViewerToolbars(opts: UseViewerToolbarsOpts) {
  const { setDrawMode } = opts;

  // ── Cursor tool mode ──
  const [cursorTool, setCursorToolRaw] = useState<CursorTool>("pointer");
  const prevCursorToolRef = useRef<CursorTool>("draw");

  const setCursorTool = useCallback(
    (tool: CursorTool) => {
      setCursorToolRaw(tool);
      setDrawMode(tool === "draw");
    },
    [setDrawMode],
  );

  // ── Sidebar / nav state ──
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarTypeFilter, setSidebarTypeFilter] = useState<Set<string> | null>(null);
  const [pageNavCollapsed, setPageNavCollapsed] = useState(false);

  // ── DOM refs ──
  const sidebarRef = useRef<HTMLDivElement>(null);
  const topToolbarRef = useRef<HTMLDivElement>(null);
  const contentAreaRef = useRef<HTMLDivElement>(null);

  // ── Cursor toolbar ──
  const [cursorToolbarExpanded, setCursorToolbarExpanded] = useState(() => {
    try {
      const saved = localStorage.getItem("cursorToolbarExpanded");
      return saved === null ? true : saved === "true";
    } catch {
      return true;
    }
  });
  const cursorToolbarRef = useRef<HTMLDivElement>(null);
  const {
    pos: cursorToolbarPos,
    isDragging: isDraggingCursorToolbar,
    startDrag: startCursorToolbarDrag,
    constrainToArea: constrainCursorToolbar,
  } = useDraggableToolbar({
    storageKey: "cursorToolbarPos",
    defaultPos: { x: 208, y: 60 },
    toolbarRef: cursorToolbarRef,
    boundaryRef: contentAreaRef,
    sidebarRef,
    sidebarCollapsed,
  });

  // ── Multi-select toolbar ──
  const [multiSelectToolbarExpanded, setMultiSelectToolbarExpanded] = useState(() => {
    try {
      const saved = localStorage.getItem("multiSelectToolbarExpanded");
      return saved === "true";
    } catch {
      return false;
    }
  });
  const multiSelectToolbarRef = useRef<HTMLDivElement>(null);
  const {
    pos: multiSelectToolbarPos,
    isDragging: isDraggingMultiSelectToolbar,
    startDrag: startMultiSelectToolbarDrag,
    constrainToArea: constrainMultiSelectToolbar,
  } = useDraggableToolbar({
    storageKey: "multiSelectToolbarPos",
    defaultPos: { x: 300, y: 200 },
    toolbarRef: multiSelectToolbarRef,
    boundaryRef: contentAreaRef,
    sidebarRef,
    sidebarCollapsed,
  });

  // ── Multi-select edit dialog ──
  const [showMultiSelectEdit, setShowMultiSelectEdit] = useState(false);
  const [multiSelectEditLabel, setMultiSelectEditLabel] = useState<string>("PERSON");

  // ── Persist multi-select toolbar expanded state ──
  useEffect(() => {
    try {
      localStorage.setItem("multiSelectToolbarExpanded", String(multiSelectToolbarExpanded));
    } catch {}
  }, [multiSelectToolbarExpanded]);

  // ── Re-constrain toolbars when sidebar collapses ──
  useEffect(() => {
    constrainCursorToolbar();
    constrainMultiSelectToolbar();
  }, [sidebarCollapsed, constrainCursorToolbar, constrainMultiSelectToolbar]);

  return {
    cursorTool,
    setCursorTool,
    prevCursorToolRef,
    // Cursor toolbar
    cursorToolbarRef,
    cursorToolbarPos,
    isDraggingCursorToolbar,
    startCursorToolbarDrag,
    cursorToolbarExpanded,
    setCursorToolbarExpanded,
    // Multi-select toolbar
    multiSelectToolbarRef,
    multiSelectToolbarPos,
    isDraggingMultiSelectToolbar,
    startMultiSelectToolbarDrag,
    multiSelectToolbarExpanded,
    setMultiSelectToolbarExpanded,
    showMultiSelectEdit,
    setShowMultiSelectEdit,
    multiSelectEditLabel,
    setMultiSelectEditLabel,
    // Sidebar & nav
    sidebarRef,
    topToolbarRef,
    contentAreaRef,
    sidebarCollapsed,
    setSidebarCollapsed,
    sidebarTypeFilter,
    setSidebarTypeFilter,
    pageNavCollapsed,
    setPageNavCollapsed,
  };
}
