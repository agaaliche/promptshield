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
  /** Current right sidebar width (from store) */
  rightSidebarWidth: number;
  /** Current left sidebar width (from store) — used as re-constrain trigger */
  leftSidebarWidth: number;
  /** Total number of pages in current document */
  pageCount: number;
}

export default function useViewerToolbars(opts: UseViewerToolbarsOpts) {
  const { setDrawMode, rightSidebarWidth, leftSidebarWidth, pageCount } = opts;

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

  // ── Compute right inset (sidebar + page nav) for toolbar clamping ──
  const sidebarWidth = sidebarCollapsed ? 60 : rightSidebarWidth;
  const pageNavWidth = pageCount > 1 ? (pageNavCollapsed ? 28 : 148) : 0;
  const rightInset = sidebarWidth + pageNavWidth;

  // ── Cursor toolbar ──
  const cursorToolbarExpanded = false;
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
    rightInset,
  });

  // ── Multi-select toolbar ──
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
    rightInset,
  });

  // ── Multi-select edit dialog ──
  const [showMultiSelectEdit, setShowMultiSelectEdit] = useState(false);
  const [multiSelectEditLabel, setMultiSelectEditLabel] = useState<string>("PERSON");

  // ── Re-constrain toolbars when any layout inset changes ──
  // rightInset: sidebar collapse/expand/resize, page nav toggle
  // leftSidebarWidth: left sidebar resize (areaRect.left shifts)
  useEffect(() => {
    constrainCursorToolbar();
    constrainMultiSelectToolbar();
  }, [rightInset, leftSidebarWidth, constrainCursorToolbar, constrainMultiSelectToolbar]);

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
    // Multi-select toolbar
    multiSelectToolbarRef,
    multiSelectToolbarPos,
    isDraggingMultiSelectToolbar,
    startMultiSelectToolbarDrag,
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
    // Computed inset
    rightInset,
  };
}
