/** Document viewer — renders page bitmap with PII highlight overlays. */

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { createPortal } from "react-dom";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ChevronDown,
  ChevronUp,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Shield,
  Lock,
  PenTool,
  Undo2,
  Redo2,
  X,
  Trash2,
  Key,
  ScanSearch,
  Edit3,
  Type,
  Search,
  MousePointer,
  BoxSelect,
  Loader2,
} from "lucide-react";
import { useAppStore } from "../store";
import {
  getPageBitmapUrl,
  setRegionAction,
  batchRegionAction,
  syncRegions,
  anonymizeDocument,
  getDownloadUrl,
  unlockVault,
  addManualRegion,
  updateRegionBBox as updateRegionBBoxApi,
  reanalyzeRegion,
  highlightAllRegions,
  updateRegionLabel,
  updateRegionText,
  redetectPII,
  deleteRegion,
  batchDeleteRegions,
} from "../api";
import { PII_COLORS, getPIIColor, loadLabelConfig, cacheLabelConfig, ensureBuiltinLabels, type PIILabelEntry, type BBox, type PIIRegion, type PIIType, type RegionAction } from "../types";
import { CURSOR_CROSSHAIR, CURSOR_GRAB, CURSOR_GRABBING } from "../cursors";
import { resolveAllOverlaps } from "../regionUtils";
import RegionOverlay, { type ResizeHandle } from "./RegionOverlay";
import ExportDialog from "./ExportDialog";
import DetectionProgressDialog from "./DetectionProgressDialog";

export default function DocumentViewer() {
  const {
    activeDocId,
    documents,
    activePage,
    setActivePage,
    regions,
    updateRegionAction,
    removeRegion,
    setRegions,
    updateRegionBBox,
    updateRegion,
    zoom,
    setZoom,
    selectedRegionIds,
    setSelectedRegionIds,
    toggleSelectedRegionId,
    clearSelection,
    setIsProcessing,
    setStatusMessage,
    isProcessing,
    vaultUnlocked,
    setVaultUnlocked,
    drawMode,
    setDrawMode,
    pushUndo,
    undo,
    redo,
    canUndo,
    canRedo,
    docLoading,
    docLoadingMessage,
    docDetecting,
  } = useAppStore();

  const containerRef = useRef<HTMLDivElement>(null);
  const imageContainerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const topToolbarRef = useRef<HTMLDivElement>(null);
  const [imgSize, setImgSize] = useState({ width: 0, height: 0 });
  const [imgLoaded, setImgLoaded] = useState(false);
  const [showVaultPrompt, setShowVaultPrompt] = useState(false);
  const [vaultPass, setVaultPass] = useState("");
  const [vaultError, setVaultError] = useState("");
  const [showExportDialog, setShowExportDialog] = useState(false);

  // ── Manual drawing state ──
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawEnd, setDrawEnd] = useState<{ x: number; y: number } | null>(null);
  const [showTypePicker, setShowTypePicker] = useState(false);
  const [drawnBBox, setDrawnBBox] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  // ── Lasso selection state ──
  const [isLassoing, setIsLassoing] = useState(false);
  const [lassoStart, setLassoStart] = useState<{ x: number; y: number } | null>(null);
  const [lassoEnd, setLassoEnd] = useState<{ x: number; y: number } | null>(null);

  // ── Pan (grab-to-scroll) state ──
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<{ x: number; y: number; scrollLeft: number; scrollTop: number } | null>(null);

  // ── Clipboard state for copy-paste ──
  const [copiedRegions, setCopiedRegions] = useState<PIIRegion[]>([]);

  // ── Autodetect panel state ──
  const [showAutodetect, setShowAutodetect] = useState(false);
  const [autodetectFuzziness, setAutodetectFuzziness] = useState(0.55);
  const [autodetectScope, setAutodetectScope] = useState<"page" | "all">("page");
  const [autodetectRegex, setAutodetectRegex] = useState(true);
  const [autodetectNer, setAutodetectNer] = useState(true);
  const [autodetectLlm, setAutodetectLlm] = useState(true);

  // ── Move / resize interaction state ──
  const interactionRef = useRef<{
    mode: "moving" | "resizing";
    regionId: string;
    handle?: ResizeHandle;
    startX: number; // mouse pos in image space
    startY: number;
    origBBox: BBox; // page coordinates
    hasMoved: boolean;
  } | null>(null);
  const [isInteracting, setIsInteracting] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // ── Cursor tool mode ──
  type CursorTool = "pointer" | "lasso" | "draw";
  const [cursorTool, setCursorToolRaw] = useState<CursorTool>("pointer");
  const prevCursorToolRef = useRef<CursorTool>("draw");
  const [cursorToolbarExpanded, setCursorToolbarExpanded] = useState(() => {
    try {
      const saved = localStorage.getItem('cursorToolbarExpanded');
      return saved === null ? true : saved === 'true';
    } catch { return true; }
  });
  const cursorToolbarRef = useRef<HTMLDivElement>(null);
  const contentAreaRef = useRef<HTMLDivElement>(null);
  
  // Cursor toolbar drag state
  const [cursorToolbarPos, setCursorToolbarPos] = useState(() => {
    try {
      const saved = localStorage.getItem('cursorToolbarPos');
      if (saved) return JSON.parse(saved);
    } catch {}
    return { x: 208, y: 60 };
  });
  const [isDraggingCursorToolbar, setIsDraggingCursorToolbar] = useState(false);
  const cursorToolbarDragStart = useRef({ mouseX: 0, mouseY: 0, startX: 0, startY: 0 });
  
  // Multi-select toolbar state
  const [multiSelectToolbarExpanded, setMultiSelectToolbarExpanded] = useState(() => {
    try {
      const saved = localStorage.getItem('multiSelectToolbarExpanded');
      return saved === 'true';
    } catch {}
    return false;
  });
  const [multiSelectToolbarPos, setMultiSelectToolbarPos] = useState(() => {
    try {
      const saved = localStorage.getItem('multiSelectToolbarPos');
      if (saved) return JSON.parse(saved);
    } catch {}
    return { x: 300, y: 200 };
  });
  const [isDraggingMultiSelectToolbar, setIsDraggingMultiSelectToolbar] = useState(false);
  const multiSelectToolbarDragStart = useRef({ mouseX: 0, mouseY: 0, startX: 0, startY: 0 });
  const multiSelectToolbarRef = useRef<HTMLDivElement>(null);
  const [showMultiSelectEdit, setShowMultiSelectEdit] = useState(false);
  const [multiSelectEditLabel, setMultiSelectEditLabel] = useState<PIIType>("PERSON");
  
  const setCursorTool = useCallback((tool: CursorTool) => {
    setCursorToolRaw(tool);
    setDrawMode(tool === "draw");
  }, [setDrawMode]);
  
  // Cursor toolbar drag handlers
  useEffect(() => {
    if (!isDraggingCursorToolbar) return;
    const PAD = 8;
    const handleMouseMove = (e: MouseEvent) => {
      const tb = cursorToolbarRef.current;
      const area = contentAreaRef.current;
      if (!tb || !area) return;
      const dx = e.clientX - cursorToolbarDragStart.current.mouseX;
      const dy = e.clientY - cursorToolbarDragStart.current.mouseY;
      let newX = cursorToolbarDragStart.current.startX + dx;
      let newY = cursorToolbarDragStart.current.startY + dy;
      
      // Boundaries: use actual content area rect, minus sidebar
      const areaRect = area.getBoundingClientRect();
      const sbWidth = sidebarRef.current?.offsetWidth ?? (sidebarCollapsed ? 60 : 320);
      const minX = areaRect.left + PAD;
      const minY = areaRect.top + PAD;
      const maxX = areaRect.right - sbWidth - tb.offsetWidth - PAD;
      const maxY = areaRect.bottom - tb.offsetHeight - PAD;
      
      newX = Math.max(minX, Math.min(maxX, newX));
      newY = Math.max(minY, Math.min(maxY, newY));
      
      setCursorToolbarPos({ x: newX, y: newY });
    };
    const handleMouseUp = () => {
      setIsDraggingCursorToolbar(false);
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingCursorToolbar]);
  
  // Save cursor toolbar position
  useEffect(() => {
    try {
      localStorage.setItem('cursorToolbarPos', JSON.stringify(cursorToolbarPos));
    } catch {}
  }, [cursorToolbarPos]);
  
  // Multi-select toolbar drag handlers
  useEffect(() => {
    if (!isDraggingMultiSelectToolbar) return;
    const PAD = 8;
    const handleMouseMove = (e: MouseEvent) => {
      const tb = multiSelectToolbarRef.current;
      const area = contentAreaRef.current;
      if (!tb || !area) return;
      const dx = e.clientX - multiSelectToolbarDragStart.current.mouseX;
      const dy = e.clientY - multiSelectToolbarDragStart.current.mouseY;
      let newX = multiSelectToolbarDragStart.current.startX + dx;
      let newY = multiSelectToolbarDragStart.current.startY + dy;
      
      // Boundaries: use actual content area rect, minus sidebar
      const areaRect = area.getBoundingClientRect();
      const sbWidth = sidebarRef.current?.offsetWidth ?? (sidebarCollapsed ? 60 : 320);
      const minX = areaRect.left + PAD;
      const minY = areaRect.top + PAD;
      const maxX = areaRect.right - sbWidth - tb.offsetWidth - PAD;
      const maxY = areaRect.bottom - tb.offsetHeight - PAD;
      
      newX = Math.max(minX, Math.min(maxX, newX));
      newY = Math.max(minY, Math.min(maxY, newY));
      
      setMultiSelectToolbarPos({ x: newX, y: newY });
    };
    const handleMouseUp = () => {
      setIsDraggingMultiSelectToolbar(false);
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingMultiSelectToolbar]);
  
  // Save multi-select toolbar state
  useEffect(() => {
    try {
      localStorage.setItem('multiSelectToolbarPos', JSON.stringify(multiSelectToolbarPos));
    } catch {}
  }, [multiSelectToolbarPos]);
  
  useEffect(() => {
    try {
      localStorage.setItem('multiSelectToolbarExpanded', String(multiSelectToolbarExpanded));
    } catch {}
  }, [multiSelectToolbarExpanded]);

  // Push floating toolbars out of the sidebar when it expands
  useEffect(() => {
    const area = contentAreaRef.current;
    if (!area) return;
    const PAD = 8;
    // Use target width, not measured — sidebar is still transitioning
    const sbWidth = sidebarCollapsed ? 60 : 320;
    const areaRect = area.getBoundingClientRect();
    const maxRight = areaRect.right - sbWidth - PAD;

    // Cursor toolbar
    const ctb = cursorToolbarRef.current;
    if (ctb) {
      const maxX = maxRight - ctb.offsetWidth;
      if (cursorToolbarPos.x > maxX) {
        setCursorToolbarPos((prev) => ({ ...prev, x: Math.max(areaRect.left + PAD, maxX) }));
      }
    }
    // Multi-select toolbar
    const mtb = multiSelectToolbarRef.current;
    if (mtb) {
      const maxX = maxRight - mtb.offsetWidth;
      if (multiSelectToolbarPos.x > maxX) {
        setMultiSelectToolbarPos((prev) => ({ ...prev, x: Math.max(areaRect.left + PAD, maxX) }));
      }
    }
  }, [sidebarCollapsed]);

  const autoRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Keep mutable refs so global event handlers see latest values
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const imgSizeRef = useRef(imgSize);
  imgSizeRef.current = imgSize;

  const doc = documents.find((d) => d.doc_id === activeDocId) ?? null;

  const pageCount = doc?.page_count ?? 0;
  const isImageFile = doc?.mime_type?.startsWith("image/") || false;
  const bitmapUrl = activeDocId
    ? getPageBitmapUrl(activeDocId, activePage)
    : "";

  const pageRegions = useMemo(
    () => regions.filter((r) => r.page_number === activePage),
    [regions, activePage]
  );

  const pendingCount = regions.filter((r) => r.action === "PENDING").length;
  const removeCount = regions.filter((r) => r.action === "REMOVE").length;
  const tokenizeCount = regions.filter((r) => r.action === "TOKENIZE").length;

  // Auto-select first region on page change (only on activePage change)
  const prevPageRef = useRef(activePage);
  useEffect(() => {
    if (activePage !== prevPageRef.current) {
      prevPageRef.current = activePage;
      const pRegions = regions.filter((r) => r.page_number === activePage);
      if (pRegions.length > 0) {
        setSelectedRegionIds([pRegions[0].id]);
      } else {
        setSelectedRegionIds([]);
      }
    }
  }, [activePage, regions, setSelectedRegionIds]);

  // ── Region actions ──
  const handleRegionAction = useCallback(
    async (regionId: string, action: RegionAction) => {
      if (!activeDocId) return;
      try {
        pushUndo();
        await setRegionAction(activeDocId, regionId, action);
        updateRegionAction(regionId, action);
      } catch (e: any) {
        console.error("Failed to set region action:", e);
      }
    },
    [activeDocId, updateRegionAction, pushUndo]
  );

  const handleRefreshRegion = useCallback(
    async (regionId: string) => {
      if (!activeDocId) return;
      try {
        pushUndo();
        const result = await reanalyzeRegion(activeDocId, regionId);
        updateRegion(regionId, {
          text: result.text,
          pii_type: result.pii_type as PIIType,
          confidence: result.confidence,
          source: result.source as any,
        });
        setStatusMessage(
          result.text
            ? `Refreshed: ${result.pii_type} — "${result.text.slice(0, 40)}"`
            : "No text found under this region"
        );
      } catch (e: any) {
        console.error("Failed to refresh region:", e);
        setStatusMessage(`Refresh failed: ${e.message}`);
      }
    },
    [activeDocId, pushUndo, updateRegion, setStatusMessage]
  );

  const handleClearRegion = useCallback(
    async (regionId: string) => {
      if (!activeDocId) return;
      try {
        pushUndo();
        removeRegion(regionId);
        await deleteRegion(activeDocId, regionId);
      } catch (e: any) {
        // 404 means region already deleted on server — not an error
        if (e.message?.includes("404")) return;
        console.error("Failed to delete region:", e);
        setStatusMessage(`Delete failed: ${e.message}`);
      }
    },
    [activeDocId, pushUndo, removeRegion, setStatusMessage]
  );

  const handleHighlightAll = useCallback(
    async (regionId: string) => {
      if (!activeDocId) return;
      const region = regions.find((r) => r.id === regionId);
      if (!region) return;
      try {
        pushUndo();
        const resp = await highlightAllRegions(activeDocId, regionId);
        // Merge new regions into store
        if (resp.new_regions.length > 0) {
          setRegions(resolveAllOverlaps([...regions, ...resp.new_regions]));
        }
        // Select all matching (existing + newly created)
        setSelectedRegionIds(resp.all_ids);
        const msg = resp.created > 0
          ? `Found ${resp.all_ids.length} occurrences of "${region.text}" (${resp.created} new)`
          : `Highlighted ${resp.all_ids.length} existing region${resp.all_ids.length !== 1 ? "s" : ""} matching "${region.text}"`;
        setStatusMessage(msg);
      } catch (e: any) {
        console.error("Highlight all failed:", e);
        setStatusMessage(`Highlight all failed: ${e.message}`);
      }
    },
    [activeDocId, regions, setRegions, setSelectedRegionIds, setStatusMessage, pushUndo]
  );

  const handleUpdateLabel = useCallback(
    async (regionId: string, newType: PIIType) => {
      if (!activeDocId) return;
      try {
        updateRegion(regionId, { pii_type: newType });
        await updateRegionLabel(activeDocId, regionId, newType);
      } catch (e: any) {
        console.error("Update label failed:", e);
        setStatusMessage(`Update failed: ${e.message}`);
      }
    },
    [activeDocId, updateRegion, setStatusMessage]
  );

  const handleUpdateText = useCallback(
    async (regionId: string, newText: string) => {
      if (!activeDocId) return;
      try {
        updateRegion(regionId, { text: newText });
        await updateRegionText(activeDocId, regionId, newText);
      } catch (e: any) {
        console.error("Update text failed:", e);
        setStatusMessage(`Update failed: ${e.message}`);
      }
    },
    [activeDocId, updateRegion, setStatusMessage]
  );

  const handlePasteRegions = useCallback(
    async () => {
      if (!activeDocId || copiedRegions.length === 0) return;
      try {
        pushUndo();
        const newRegions: PIIRegion[] = [];
        const newIds: string[] = [];

        // Create new regions with same bbox but on current page
        for (const copied of copiedRegions) {
          const regionToPaste: Partial<PIIRegion> = {
            page_number: activePage,
            bbox: { ...copied.bbox },
            text: copied.text,
            pii_type: copied.pii_type,
            confidence: copied.confidence,
            source: "MANUAL",
            char_start: 0,
            char_end: 0,
            action: copied.action === "CANCEL" ? "PENDING" : copied.action, // Don't paste cancelled regions
          };

          // Create the region on the backend
          const response = await addManualRegion(activeDocId, regionToPaste);

          // Construct the full region object with the returned ID
          const created: PIIRegion = {
            id: response.region_id,
            page_number: activePage,
            bbox: { ...copied.bbox },
            text: copied.text,
            pii_type: copied.pii_type,
            confidence: copied.confidence,
            source: "MANUAL",
            char_start: 0,
            char_end: 0,
            action: copied.action === "CANCEL" ? "PENDING" : copied.action,
          };

          newRegions.push(created);
          newIds.push(created.id);
        }

        // Add to local state
        setRegions(resolveAllOverlaps([...regions, ...newRegions]));
        setSelectedRegionIds(newIds);
        setStatusMessage(`Pasted ${newRegions.length} region(s) on page ${activePage}`);
      } catch (e: any) {
        console.error("Failed to paste regions:", e);
        setStatusMessage(`Paste failed: ${e.message}`);
      }
    },
    [activeDocId, activePage, copiedRegions, regions, setRegions, setSelectedRegionIds, setStatusMessage, pushUndo]
  );

  const handleBatchAction = useCallback(
    async (action: RegionAction) => {
      if (!activeDocId) return;
      const ids = regions
        .filter((r) => r.action === "PENDING")
        .map((r) => r.id);
      if (ids.length === 0) return;

      try {
        pushUndo();
        await batchRegionAction(activeDocId, ids, action);
        ids.forEach((id) => updateRegionAction(id, action));
      } catch (e: any) {
        console.error("Batch action failed:", e);
      }
    },
    [activeDocId, regions, updateRegionAction, pushUndo]
  );

  const handleResetAll = useCallback(
    async () => {
      if (!activeDocId) return;
      const ids = regions.map((r) => r.id);
      if (ids.length === 0) return;

      try {
        pushUndo();
        await batchDeleteRegions(activeDocId, ids);
        ids.forEach((id) => removeRegion(id));
      } catch (e: any) {
        console.error("Reset all failed:", e);
      }
    },
    [activeDocId, regions, removeRegion, pushUndo]
  );

  const cancelTypePicker = useCallback(() => {
    setShowTypePicker(false);
    setDrawnBBox(null);
  }, []);

  // Cleanup auto-refresh timer on unmount
  useEffect(() => {
    return () => {
      if (autoRefreshTimerRef.current) clearTimeout(autoRefreshTimerRef.current);
    };
  }, []);

  // ── Scroll wheel page navigation ──
  const wheelCooldown = useRef(false);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      // Only change page on vertical scroll when not holding Ctrl (Ctrl+scroll = browser zoom)
      if (e.ctrlKey || e.metaKey) return;
      if (wheelCooldown.current) return;
      const threshold = 30; // minimum delta to trigger
      if (Math.abs(e.deltaY) < threshold) return;

      e.preventDefault();
      wheelCooldown.current = true;
      setTimeout(() => { wheelCooldown.current = false; }, 1000); // 1 second cooldown

      if (e.deltaY > 0) {
        // Scroll down → next page
        setActivePage(Math.min(pageCount, activePage + 1));
      } else {
        // Scroll up → prev page
        setActivePage(Math.max(1, activePage - 1));
      }
      
      // Scroll to top of container after page change
      el.scrollTop = 0;
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [activePage, pageCount, setActivePage]);

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      // Don't capture when typing in inputs
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      switch (e.key) {
        case "z":
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            undo();
          }
          break;
        case "y":
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            redo();
          }
          break;
        case "a":
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            // Select all visible regions on current page
            setSelectedRegionIds(pageRegions.filter((r) => r.action !== "CANCEL").map((r) => r.id));
          }
          break;
        case "ArrowLeft":
          e.preventDefault();
          setActivePage(Math.max(1, activePage - 1));
          break;
        case "ArrowRight":
          e.preventDefault();
          setActivePage(Math.min(pageCount, activePage + 1));
          break;
        case "+":
        case "=":
          e.preventDefault();
          setZoom(zoom + 0.1);
          break;
        case "-":
          e.preventDefault();
          setZoom(zoom - 0.1);
          break;
        case "0":
          e.preventDefault();
          setZoom(1);
          break;
        case "Escape":
          clearSelection();
          if (cursorTool !== "pointer") setCursorTool("pointer");
          if (showTypePicker) cancelTypePicker();
          break;
        case " ": {
          e.preventDefault();
          if (cursorTool !== "pointer") {
            prevCursorToolRef.current = cursorTool;
            setCursorTool("pointer");
          } else {
            setCursorTool(prevCursorToolRef.current);
          }
          break;
        }
        case "d":
          if (selectedRegionIds.length > 0) {
            e.preventDefault();
            selectedRegionIds.forEach((id) => {
              const r = regions.find((reg) => reg.id === id);
              handleRegionAction(id, r?.action === "REMOVE" ? "PENDING" : "REMOVE");
            });
          }
          break;
        case "Delete":
          if (selectedRegionIds.length > 0) {
            e.preventDefault();
            pushUndo();
            const delIds = [...selectedRegionIds];
            delIds.forEach((id) => removeRegion(id));
            batchDeleteRegions(activeDocId!, delIds).catch(() => {});
          }
          break;
        case "Backspace":
          if (selectedRegionIds.length > 0) {
            e.preventDefault();
            selectedRegionIds.forEach((id) => {
              const r = regions.find((reg) => reg.id === id);
              handleRegionAction(id, r?.action === "REMOVE" ? "PENDING" : "REMOVE");
            });
          }
          break;
        case "t":
          if (selectedRegionIds.length > 0) {
            e.preventDefault();
            selectedRegionIds.forEach((id) => {
              const r = regions.find((reg) => reg.id === id);
              handleRegionAction(id, r?.action === "TOKENIZE" ? "PENDING" : "TOKENIZE");
            });
          }
          break;
        case "c":
          if (e.ctrlKey || e.metaKey) {
            // Ctrl+C: Copy selected regions
            if (selectedRegionIds.length > 0) {
              e.preventDefault();
              const regionsToCopy = regions.filter((r) => selectedRegionIds.includes(r.id));
              setCopiedRegions(regionsToCopy);
              setStatusMessage(`Copied ${regionsToCopy.length} region(s)`);
            }
          } else if (selectedRegionIds.length > 0) {
            e.preventDefault();
            pushUndo();
            const clearIds = [...selectedRegionIds];
            clearIds.forEach((id) => removeRegion(id));
            batchDeleteRegions(activeDocId!, clearIds).catch(() => {});
          }
          break;
        case "v":
          if ((e.ctrlKey || e.metaKey) && copiedRegions.length > 0) {
            // Ctrl+V: Paste copied regions on current page
            e.preventDefault();
            handlePasteRegions();
          }
          break;
        case "Tab": {
          e.preventDefault();
          const pending = pageRegions.filter((r) => r.action === "PENDING");
          if (pending.length === 0) break;
          const lastSelected = selectedRegionIds[selectedRegionIds.length - 1];
          const currentIdx = pending.findIndex((r) => r.id === lastSelected);
          const next = e.shiftKey
            ? (currentIdx <= 0 ? pending.length - 1 : currentIdx - 1)
            : (currentIdx + 1) % pending.length;
          setSelectedRegionIds([pending[next].id]);
          break;
        }
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [activePage, pageCount, zoom, selectedRegionIds, pageRegions, setActivePage, setZoom, setSelectedRegionIds, clearSelection, handleRegionAction, handleClearRegion, undo, redo, cursorTool, setCursorTool, showTypePicker, cancelTypePicker, copiedRegions, handlePasteRegions]);

  // ── Autodetect (redetect) ──
  const handleAutodetect = useCallback(async () => {
    if (!activeDocId) return;
    setIsProcessing(true);
    setStatusMessage("Running PII autodetection…");
    setShowAutodetect(false);
    try {
      pushUndo();
      const result = await redetectPII(activeDocId, {
        confidence_threshold: autodetectFuzziness,
        page_number: autodetectScope === "page" ? activePage : undefined,
        regex_enabled: autodetectRegex,
        ner_enabled: autodetectNer,
        llm_detection_enabled: autodetectLlm,
      });
      setRegions(resolveAllOverlaps(result.regions));
      setStatusMessage(
        `Autodetect: ${result.added} added, ${result.updated} updated (${result.total_regions} total)`
      );
    } catch (err) {
      setStatusMessage(`Autodetect failed: ${err}`);
    } finally {
      setIsProcessing(false);
    }
  }, [activeDocId, activePage, autodetectFuzziness, autodetectScope, autodetectRegex, autodetectNer, autodetectLlm, pushUndo, setRegions, setIsProcessing, setStatusMessage]);

  // ── Anonymize ──
  const handleAnonymize = useCallback(async () => {
    if (!activeDocId) return;

    // If there are tokenized regions and vault isn't unlocked, prompt
    const hasTokenize = regions.some((r) => r.action === "TOKENIZE");
    if (hasTokenize && !vaultUnlocked) {
      setShowVaultPrompt(true);
      return;
    }

    setIsProcessing(true);
    setStatusMessage("Syncing regions & anonymizing...");
    try {
      // Sync ALL region state (actions + bboxes) to backend before
      // anonymizing so moved/resized regions are always up-to-date.
      await syncRegions(
        activeDocId,
        regions.map((r) => ({ id: r.id, action: r.action, bbox: r.bbox })),
      );
      const result = await anonymizeDocument(activeDocId);
      setStatusMessage(
        `Done! ${result.regions_removed} removed, ${result.tokens_created} tokenized`
      );
      // Open download links
      if (result.output_pdf_path) {
        window.open(getDownloadUrl(activeDocId, "pdf"), "_blank");
      }
    } catch (e: any) {
      setStatusMessage(`Anonymization failed: ${e.message}`);
    } finally {
      setIsProcessing(false);
    }
  }, [activeDocId, setIsProcessing, setStatusMessage, regions, vaultUnlocked]);

  const handleVaultUnlockAndAnonymize = useCallback(async () => {
    try {
      setVaultError("");
      await unlockVault(vaultPass);
      setVaultUnlocked(true);
      setShowVaultPrompt(false);
      setVaultPass("");
      // Now anonymize
      setIsProcessing(true);
      setStatusMessage("Syncing regions & anonymizing...");
      await syncRegions(
        activeDocId!,
        regions.map((r) => ({ id: r.id, action: r.action, bbox: r.bbox })),
      );
      const result = await anonymizeDocument(activeDocId!);
      setStatusMessage(
        `Done! ${result.regions_removed} removed, ${result.tokens_created} tokenized`
      );
      if (result.output_pdf_path) {
        window.open(getDownloadUrl(activeDocId!, "pdf"), "_blank");
      }
    } catch (e: any) {
      if (e.message?.includes("403") || e.message?.includes("passphrase")) {
        setVaultError("Invalid passphrase");
      } else {
        setStatusMessage(`Anonymization failed: ${e.message}`);
        setShowVaultPrompt(false);
      }
    } finally {
      setIsProcessing(false);
    }
  }, [activeDocId, vaultPass, setVaultUnlocked, setIsProcessing, setStatusMessage]);

  // ── Image load handler ──
  const onImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    // Use displayed dimensions, not natural dimensions
    setImgSize({ width: img.offsetWidth, height: img.offsetHeight });
    setImgLoaded(true);
  }, []);

  // ── Track displayed image size on window resize ──
  useEffect(() => {
    const updateImageSize = () => {
      const img = imageRef.current;
      if (img && img.offsetWidth > 0 && img.offsetHeight > 0) {
        setImgSize({ width: img.offsetWidth, height: img.offsetHeight });
      }
    };

    // Update on window resize
    window.addEventListener('resize', updateImageSize);
    
    // Also use ResizeObserver for more accurate tracking
    const img = imageRef.current;
    let observer: ResizeObserver | null = null;
    if (img && window.ResizeObserver) {
      observer = new ResizeObserver(updateImageSize);
      observer.observe(img);
    }

    return () => {
      window.removeEventListener('resize', updateImageSize);
      if (observer) observer.disconnect();
    };
  }, [imgLoaded]);



  // ── Page data for coordinate mapping ──
  const pageData = doc?.pages?.[activePage - 1];

  // ── Manual draw handlers ──
  const [labelConfig, setLabelConfig] = useState<PIILabelEntry[]>(() => loadLabelConfig());
  const [typePickerEditMode, setTypePickerEditMode] = useState(false);
  const [typePickerNewLabel, setTypePickerNewLabel] = useState("");

  // Load label config from backend on mount (overrides localStorage cache)
  useEffect(() => {
    import("../api").then(({ fetchLabelConfig }) =>
      fetchLabelConfig().then((remote) => {
        const merged = ensureBuiltinLabels(remote);
        setLabelConfig(merged);
        cacheLabelConfig(merged);
      })
    ).catch(() => {}); // fall back to localStorage cache on error
  }, []);

  // Derived lists from label config
  const visibleLabels = useMemo(() => labelConfig.filter((e) => !e.hidden), [labelConfig]);
  const frequentLabels = useMemo(() => visibleLabels.filter((e) => e.frequent), [visibleLabels]);
  const otherLabels = useMemo(() => visibleLabels.filter((e) => !e.frequent), [visibleLabels]);

  // Labels currently used in the document (cannot be deleted, only hidden)
  const usedLabels = useMemo(() => {
    const s = new Set<string>();
    for (const r of regions) s.add(r.pii_type);
    return s;
  }, [regions]);

  const updateLabelConfig = useCallback((updater: (prev: PIILabelEntry[]) => PIILabelEntry[]) => {
    setLabelConfig((prev) => {
      const next = updater(prev);
      cacheLabelConfig(next);
      // Persist to backend (fire-and-forget)
      import("../api").then(({ saveLabelConfigAPI }) => saveLabelConfigAPI(next)).catch(() => {});
      return next;
    });
  }, []);

  const getPointerPosOnImage = useCallback(
    (e: React.MouseEvent) => {
      if (!imageContainerRef.current) return null;
      const rect = imageContainerRef.current.getBoundingClientRect();
      return {
        x: (e.clientX - rect.left) / zoom,
        y: (e.clientY - rect.top) / zoom,
      };
    },
    [zoom]
  );

  const handleCanvasMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (cursorTool === "draw") {
        // Draw mode: start drawing a new region
        const pos = getPointerPosOnImage(e);
        if (!pos) return;
        e.preventDefault();
        setIsDrawing(true);
        setDrawStart(pos);
        setDrawEnd(pos);
        return;
      }
      if (cursorTool === "lasso") {
        // Lasso mode: drag to select multiple regions
        const pos = getPointerPosOnImage(e);
        if (!pos) return;
        e.preventDefault();
        setIsLassoing(true);
        setLassoStart(pos);
        setLassoEnd(pos);
        return;
      }
      // Pointer mode: Ctrl/Meta+drag = lasso select, plain drag = pan
      if (e.ctrlKey || e.metaKey) {
        const pos = getPointerPosOnImage(e);
        if (!pos) return;
        e.preventDefault();
        setIsLassoing(true);
        setLassoStart(pos);
        setLassoEnd(pos);
      } else {
        // Pan mode - also clear selection when clicking on empty space
        e.preventDefault();
        clearSelection();
        const el = containerRef.current;
        if (!el) return;
        setIsPanning(true);
        panStartRef.current = { x: e.clientX, y: e.clientY, scrollLeft: el.scrollLeft, scrollTop: el.scrollTop };
      }
    },
    [cursorTool, getPointerPosOnImage, clearSelection]
  );

  const handleCanvasMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (isDrawing && cursorTool === "draw") {
        const pos = getPointerPosOnImage(e);
        if (pos) setDrawEnd(pos);
        return;
      }
      if (isLassoing) {
        const pos = getPointerPosOnImage(e);
        if (pos) setLassoEnd(pos);
        return;
      }
      if (isPanning && panStartRef.current) {
        const el = containerRef.current;
        if (!el) return;
        const dx = e.clientX - panStartRef.current.x;
        const dy = e.clientY - panStartRef.current.y;
        el.scrollLeft = panStartRef.current.scrollLeft - dx;
        el.scrollTop = panStartRef.current.scrollTop - dy;
      }
    },
    [isDrawing, cursorTool, isLassoing, isPanning, getPointerPosOnImage]
  );

  // ── Snap-to-text helper for resize and draw ──
  // When resizing or drawing, snap edges to nearby text block boundaries (with padding).
  // `edges` controls which edges snap: { left, right, top, bottom }.
  const snapToText = useCallback(
    (nb: BBox, edges: { left: boolean; right: boolean; top: boolean; bottom: boolean }): BBox => {
      if (!pageData) return nb;

      const blocks = pageData.text_blocks;
      if (!blocks || blocks.length === 0) return nb;

      // Padding in page-coordinate units (~2 display px).
      const { width: iw, height: ih } = imgSizeRef.current;
      const PAD_PX = 2;
      const padX = iw > 0 ? (PAD_PX * pageData.width) / iw : 1;
      const padY = ih > 0 ? (PAD_PX * pageData.height) / ih : 1;

      // Snap distance threshold in page units (~8 display px)
      const SNAP_PX = 8;
      const snapDistX = iw > 0 ? (SNAP_PX * pageData.width) / iw : 4;
      const snapDistY = ih > 0 ? (SNAP_PX * pageData.height) / ih : 4;

      // Only consider blocks near the region
      const relevantBlocks = blocks.filter((b) => (
        b.bbox.x1 > nb.x0 - snapDistX &&
        b.bbox.x0 < nb.x1 + snapDistX &&
        b.bbox.y1 > nb.y0 - snapDistY &&
        b.bbox.y0 < nb.y1 + snapDistY
      ));

      const snapped = { ...nb };

      if (edges.left) {
        let bestDist = snapDistX;
        let bestSnap = snapped.x0;
        for (const b of relevantBlocks) {
          const d = Math.abs(snapped.x0 - (b.bbox.x0 - padX));
          if (d < bestDist) { bestDist = d; bestSnap = b.bbox.x0 - padX; }
        }
        snapped.x0 = bestSnap;
      }
      if (edges.right) {
        let bestDist = snapDistX;
        let bestSnap = snapped.x1;
        for (const b of relevantBlocks) {
          const d = Math.abs(snapped.x1 - (b.bbox.x1 + padX));
          if (d < bestDist) { bestDist = d; bestSnap = b.bbox.x1 + padX; }
        }
        snapped.x1 = bestSnap;
      }
      if (edges.top) {
        let bestDist = snapDistY;
        let bestSnap = snapped.y0;
        for (const b of relevantBlocks) {
          const d = Math.abs(snapped.y0 - (b.bbox.y0 - padY));
          if (d < bestDist) { bestDist = d; bestSnap = b.bbox.y0 - padY; }
        }
        snapped.y0 = bestSnap;
      }
      if (edges.bottom) {
        let bestDist = snapDistY;
        let bestSnap = snapped.y1;
        for (const b of relevantBlocks) {
          const d = Math.abs(snapped.y1 - (b.bbox.y1 + padY));
          if (d < bestDist) { bestDist = d; bestSnap = b.bbox.y1 + padY; }
        }
        snapped.y1 = bestSnap;
      }

      return snapped;
    },
    [pageData],
  );

  const handleCanvasMouseUp = useCallback(
    (e: React.MouseEvent) => {
      // Pan finish
      if (isPanning) {
        setIsPanning(false);
        panStartRef.current = null;
        return;
      }

      // Lasso selection finish
      if (isLassoing && lassoStart && lassoEnd && pageData) {
        setIsLassoing(false);
        const w = Math.abs(lassoEnd.x - lassoStart.x);
        const h = Math.abs(lassoEnd.y - lassoStart.y);
        if (w > 5 || h > 5) {
          // Find regions whose bbox overlaps the lasso rectangle
          const sx = imgSize.width / pageData.width;
          const sy = imgSize.height / pageData.height;
          const lx0 = Math.min(lassoStart.x, lassoEnd.x);
          const ly0 = Math.min(lassoStart.y, lassoEnd.y);
          const lx1 = Math.max(lassoStart.x, lassoEnd.x);
          const ly1 = Math.max(lassoStart.y, lassoEnd.y);

          const hits = pageRegions.filter((r) => {
            if (r.action === "CANCEL") return false;
            const rx0 = r.bbox.x0 * sx;
            const ry0 = r.bbox.y0 * sy;
            const rx1 = r.bbox.x1 * sx;
            const ry1 = r.bbox.y1 * sy;
            return rx0 < lx1 && rx1 > lx0 && ry0 < ly1 && ry1 > ly0;
          });

          if (hits.length > 0) {
            const hitIds = hits.map((r) => r.id);
            if (e.ctrlKey || e.metaKey) {
              // Additive lasso
              setSelectedRegionIds([...new Set([...selectedRegionIds, ...hitIds])]);
            } else {
              setSelectedRegionIds(hitIds);
            }
          }
        }
        setLassoStart(null);
        setLassoEnd(null);
        return;
      }

      // Draw mode finish
      if (!isDrawing || !drawStart || !drawEnd || !pageData) return;
      setIsDrawing(false);

      // Minimum bbox size (10px) to avoid accidental clicks
      const w = Math.abs(drawEnd.x - drawStart.x);
      const h = Math.abs(drawEnd.y - drawStart.y);
      if (w < 10 || h < 10) {
        setDrawStart(null);
        setDrawEnd(null);
        return;
      }

      // Convert pixel coords on displayed image → page coordinates
      const sx = pageData.width / imgSize.width;
      const sy = pageData.height / imgSize.height;

      let box: BBox = {
        x0: Math.min(drawStart.x, drawEnd.x) * sx,
        y0: Math.min(drawStart.y, drawEnd.y) * sy,
        x1: Math.max(drawStart.x, drawEnd.x) * sx,
        y1: Math.max(drawStart.y, drawEnd.y) * sy,
      };

      // Snap all edges to nearby text block boundaries
      box = snapToText(box, { left: true, right: true, top: true, bottom: true });

      setDrawnBBox(box);
      setShowTypePicker(true);
      setDrawStart(null);
      setDrawEnd(null);
    },
    [isPanning, isDrawing, isLassoing, lassoStart, lassoEnd, drawStart, drawEnd, pageData, imgSize, pageRegions, selectedRegionIds, setSelectedRegionIds, clearSelection, snapToText]
  );

  // ── Move / resize handlers ──
  const handleMoveStart = useCallback(
    (regionId: string, e: React.MouseEvent) => {
      const pos = getPointerPosOnImage(e);
      if (!pos) return;
      const region = regions.find((r) => r.id === regionId);
      if (!region) return;
      e.preventDefault();
      setSelectedRegionIds([regionId]);
      interactionRef.current = {
        mode: "moving",
        regionId,
        startX: pos.x,
        startY: pos.y,
        origBBox: { ...region.bbox },
        hasMoved: false,
      };
      setIsInteracting(true);
    },
    [getPointerPosOnImage, regions, setSelectedRegionIds],
  );

  const handleResizeStart = useCallback(
    (regionId: string, handle: ResizeHandle, e: React.MouseEvent) => {
      const pos = getPointerPosOnImage(e);
      if (!pos) return;
      const region = regions.find((r) => r.id === regionId);
      if (!region) return;
      e.preventDefault();
      setSelectedRegionIds([regionId]);
      interactionRef.current = {
        mode: "resizing",
        regionId,
        handle,
        startX: pos.x,
        startY: pos.y,
        origBBox: { ...region.bbox },
        hasMoved: false,
      };
      setIsInteracting(true);
    },
    [getPointerPosOnImage, regions, setSelectedRegionIds],
  );

  // ── Prevent overlap helper ──
  // Pushes the proposed bbox out of any other visible region on the same page.
  const preventOverlap = useCallback(
    (proposed: BBox, movingId: string): BBox => {
      const others = regions.filter(
        (r) => r.id !== movingId && r.page_number === activePage && r.action !== "CANCEL",
      );
      let box = { ...proposed };

      for (const other of others) {
        const ob = other.bbox;
        // Check for overlap
        if (box.x0 >= ob.x1 || box.x1 <= ob.x0 || box.y0 >= ob.y1 || box.y1 <= ob.y0) continue;

        // Overlap detected — push the box along the axis with the smallest overlap
        const overlapX = Math.min(box.x1, ob.x1) - Math.max(box.x0, ob.x0);
        const overlapY = Math.min(box.y1, ob.y1) - Math.max(box.y0, ob.y0);
        const cx = (box.x0 + box.x1) / 2;
        const cy = (box.y0 + box.y1) / 2;
        const ocx = (ob.x0 + ob.x1) / 2;
        const ocy = (ob.y0 + ob.y1) / 2;

        if (overlapY <= overlapX) {
          // Push vertically
          const shift = cy < ocy ? -(overlapY) : overlapY;
          box = { ...box, y0: box.y0 + shift, y1: box.y1 + shift };
        } else {
          // Push horizontally
          const shift = cx < ocx ? -(overlapX) : overlapX;
          box = { ...box, x0: box.x0 + shift, x1: box.x1 + shift };
        }
      }
      return box;
    },
    [regions, activePage],
  );

  // Global mouse tracking for move/resize
  useEffect(() => {
    if (!isInteracting) return;

    const handleMouseMove = (e: MouseEvent) => {
      const ix = interactionRef.current;
      if (!ix || !imageContainerRef.current || !pageData) return;

      const rect = imageContainerRef.current.getBoundingClientRect();
      const imgX = (e.clientX - rect.left) / zoomRef.current;
      const imgY = (e.clientY - rect.top) / zoomRef.current;

      // Dead zone — don't start mutation until user actually moves 3px
      if (!ix.hasMoved) {
        const dist =
          Math.abs(imgX - ix.startX) + Math.abs(imgY - ix.startY);
        if (dist < 3) return;
        ix.hasMoved = true;
        pushUndo();
      }

      const { width: iw, height: ih } = imgSizeRef.current;
      if (iw === 0 || ih === 0) return;

      const pxToPgX = pageData.width / iw;
      const pxToPgY = pageData.height / ih;
      const dx = (imgX - ix.startX) * pxToPgX;
      const dy = (imgY - ix.startY) * pxToPgY;
      const orig = ix.origBBox;

      let nb: BBox;

      if (ix.mode === "moving") {
        nb = {
          x0: orig.x0 + dx,
          y0: orig.y0 + dy,
          x1: orig.x1 + dx,
          y1: orig.y1 + dy,
        };
        // Clamp to page
        const bw = nb.x1 - nb.x0;
        const bh = nb.y1 - nb.y0;
        if (nb.x0 < 0) { nb.x0 = 0; nb.x1 = bw; }
        if (nb.y0 < 0) { nb.y0 = 0; nb.y1 = bh; }
        if (nb.x1 > pageData.width) { nb.x1 = pageData.width; nb.x0 = pageData.width - bw; }
        if (nb.y1 > pageData.height) { nb.y1 = pageData.height; nb.y0 = pageData.height - bh; }
      } else {
        nb = { ...orig };
        const h = ix.handle!;
        if (h.includes("w")) nb.x0 = orig.x0 + dx;
        if (h.includes("e")) nb.x1 = orig.x1 + dx;
        if (h.includes("n")) nb.y0 = orig.y0 + dy;
        if (h.includes("s")) nb.y1 = orig.y1 + dy;
        // Min size 5 page units
        const MIN = 5;
        if (nb.x1 - nb.x0 < MIN) {
          if (h.includes("w")) nb.x0 = nb.x1 - MIN; else nb.x1 = nb.x0 + MIN;
        }
        if (nb.y1 - nb.y0 < MIN) {
          if (h.includes("n")) nb.y0 = nb.y1 - MIN; else nb.y1 = nb.y0 + MIN;
        }
        // Clamp
        nb.x0 = Math.max(0, nb.x0);
        nb.y0 = Math.max(0, nb.y0);
        nb.x1 = Math.min(pageData.width, nb.x1);
        nb.y1 = Math.min(pageData.height, nb.y1);

        // Snap edges to nearby text block boundaries
        nb = snapToText(nb, {
          left: h.includes("w"),
          right: h.includes("e"),
          top: h.includes("n"),
          bottom: h.includes("s"),
        });
      }

      // Prevent overlap with other visible regions on the same page
      nb = preventOverlap(nb, ix.regionId);

      updateRegionBBox(ix.regionId, nb);
    };

    const handleMouseUp = async () => {
      const ix = interactionRef.current;
      interactionRef.current = null;
      setIsInteracting(false);
      if (!ix || !ix.hasMoved || !activeDocId) return;

      // Persist to backend
      const latest = useAppStore.getState().regions.find(
        (r) => r.id === ix.regionId,
      );
      if (latest) {
        try {
          await updateRegionBBoxApi(activeDocId, ix.regionId, latest.bbox);
        } catch (err) {
          console.error("Failed to persist bbox update:", err);
        }
      }

      // Auto-refresh: re-analyze content after move/resize
      if (autoRefreshTimerRef.current) clearTimeout(autoRefreshTimerRef.current);
      autoRefreshTimerRef.current = setTimeout(() => {
        handleRefreshRegion(ix.regionId);
      }, 300);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isInteracting, pageData, activeDocId, pushUndo, updateRegionBBox, preventOverlap, snapToText, handleRefreshRegion]);

  const handleTypePickerSelect = useCallback(
    async (piiType: PIIType) => {
      if (!activeDocId || !drawnBBox) return;
      setShowTypePicker(false);

      // Adjust drawn bbox to prevent overlap with existing regions
      const adjustedBBox = preventOverlap(drawnBBox, "");

      const newRegion: Partial<PIIRegion> = {
        page_number: activePage,
        bbox: adjustedBBox,
        text: "[manual selection]",
        pii_type: piiType,
        confidence: 1.0,
        source: "MANUAL",
        char_start: 0,
        char_end: 0,
        action: "PENDING",
      };

      try {
        const resp = await addManualRegion(activeDocId, newRegion);
        // Add to local state with server-assigned id
        const fullRegion: PIIRegion = {
          id: (resp as any).region_id ?? crypto.randomUUID().slice(0, 12),
          page_number: activePage,
          bbox: adjustedBBox,
          text: "[manual selection]",
          pii_type: piiType,
          confidence: 1.0,
          source: "MANUAL",
          char_start: 0,
          char_end: 0,
          action: "PENDING",
        };
        pushUndo();
        setRegions([...regions, fullRegion]);
        setStatusMessage(`Added manual ${piiType} region`);

        // Auto-refresh: re-analyze content under the new region
        if (autoRefreshTimerRef.current) clearTimeout(autoRefreshTimerRef.current);
        const regionId = fullRegion.id;
        autoRefreshTimerRef.current = setTimeout(() => {
          handleRefreshRegion(regionId);
        }, 300);
      } catch (e: any) {
        setStatusMessage(`Failed to add region: ${e.message}`);
      }
      setDrawnBBox(null);
    },
    [activeDocId, activePage, drawnBBox, regions, setRegions, setStatusMessage, pushUndo, preventOverlap, handleRefreshRegion]
  );

  if (!doc) return <div style={styles.empty}>No document loaded</div>;

  // Block the viewer while loading OR detecting
  const isDocLoading = docLoading || docDetecting || !doc.pages;

  if (isDocLoading) {
    // During detection, show the real progress dialog
    if (docDetecting) {
      return (
        <div style={styles.wrapper}>
          <DetectionProgressDialog
            docId={doc.doc_id}
            docName={doc.original_filename}
            visible
          />
        </div>
      );
    }

    // Otherwise show the simple loading spinner
    return (
      <div style={styles.wrapper}>
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          width: "100%",
        }}>
          <div style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 16,
          }}>
            <Loader2 size={36} color="var(--accent-primary)" style={{ animation: "spin 1s linear infinite" }} />
            <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>
              {docLoadingMessage || "Loading document\u2026"}
            </div>
          </div>
        </div>
        <style>{`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  return (
    <div style={styles.wrapper}>

      {/* Toolbar */}
      <div ref={topToolbarRef} style={styles.toolbar}>
        <div style={{ position: "relative" }}>
        <button
          className="btn-primary"
          onClick={() => setShowAutodetect(!showAutodetect)}
          disabled={isProcessing}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            ...(showAutodetect
              ? { boxShadow: "0 0 0 2px var(--accent-primary)" }
              : {}),
          }}
        >
          <ScanSearch size={14} />
          Detect
        </button>

        {showAutodetect && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                left: 0,
                marginTop: 6,
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                borderRadius: 8,
                padding: 16,
                boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
                zIndex: 9999,
                width: 300,
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
              onMouseDown={(e) => e.stopPropagation()}
            >

              {/* Fuzziness slider */}
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                  <span>Sensitivity (confidence threshold)</span>
                  <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{autodetectFuzziness.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0.1}
                  max={0.95}
                  step={0.05}
                  value={autodetectFuzziness}
                  onChange={(e) => setAutodetectFuzziness(parseFloat(e.target.value))}
                  style={{ width: "100%", accentColor: "var(--accent-primary)" }}
                />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-secondary)", marginTop: 2 }}>
                  <span>More results</span>
                  <span>Fewer results</span>
                </div>
              </div>

              {/* Scope */}
              <div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>Scope</div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    className={autodetectScope === "page" ? "btn-primary btn-sm" : "btn-ghost btn-sm"}
                    onClick={() => setAutodetectScope("page")}
                    style={{ flex: 1 }}
                  >
                    Current Page
                  </button>
                  <button
                    className={autodetectScope === "all" ? "btn-primary btn-sm" : "btn-ghost btn-sm"}
                    onClick={() => setAutodetectScope("all")}
                    style={{ flex: 1 }}
                  >
                    All Pages
                  </button>
                </div>
              </div>

              {/* Detection layers */}
              <div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>Detection layers</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-primary)", cursor: "pointer" }}>
                    <input type="checkbox" checked={autodetectRegex} onChange={(e) => setAutodetectRegex(e.target.checked)} style={{ accentColor: "var(--accent-primary)" }} />
                    SSN, email, phone, etc.
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-primary)", cursor: "pointer" }}>
                    <input type="checkbox" checked={autodetectNer} onChange={(e) => setAutodetectNer(e.target.checked)} style={{ accentColor: "var(--accent-primary)" }} />
                    Names, orgs, locations
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-primary)", cursor: "pointer" }}>
                    <input type="checkbox" checked={autodetectLlm} onChange={(e) => setAutodetectLlm(e.target.checked)} style={{ accentColor: "var(--accent-primary)" }} />
                    Contextual (slowest)
                  </label>
                </div>
              </div>

              {/* Run button */}
              <button
                className="btn-primary"
                onClick={handleAutodetect}
                disabled={isProcessing || (!autodetectRegex && !autodetectNer && !autodetectLlm)}
                style={{ width: "100%" }}
              >
                <ScanSearch size={14} />
                {isProcessing ? "Detecting…" : `Run on ${autodetectScope === "page" ? `Page ${activePage}` : "All Pages"}`}
              </button>
            </div>
        )}
        </div>
        <button
          className="btn-success"
          onClick={() => setShowExportDialog(true)}
          disabled={
            isProcessing ||
            (removeCount === 0 && tokenizeCount === 0)
          }
        >
          <Shield size={14} />
          Export secure file
        </button>

        {/* Spacer — left buttons stay in flow, center group is absolutely positioned */}
        <div style={{ flex: 1 }} />

        {/* Page navigation + Zoom — centered on window width via fixed positioning */}
        <div style={{
          position: "fixed",
          left: "50%",
          transform: "translateX(-50%)",
          display: "flex",
          alignItems: "center",
          gap: 4,
          pointerEvents: "auto",
          zIndex: 41,
        }}>
          {pageCount > 1 && (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <button
                className="btn-ghost btn-sm"
                onClick={() => setActivePage(1)}
                disabled={activePage <= 1}
                title="First page"
                style={{ padding: "4px 6px", color: "var(--text-secondary)" }}
              >
                <ChevronsLeft size={16} />
              </button>
              <button
                className="btn-ghost btn-sm"
                onClick={() => setActivePage(Math.max(1, activePage - 1))}
                disabled={activePage <= 1}
                title="Previous page"
                style={{ padding: "4px 6px", color: "var(--text-secondary)" }}
              >
                <ChevronLeft size={16} />
              </button>
              <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "0 4px" }}>
                <input
                  type="number"
                  min={1}
                  max={pageCount}
                  value={activePage}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (!isNaN(val) && val >= 1 && val <= pageCount) {
                      setActivePage(val);
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.currentTarget.blur();
                    }
                  }}
                  style={{
                    width: 36,
                    padding: "3px 4px",
                    fontSize: 13,
                    fontWeight: 600,
                    textAlign: "center",
                    background: "rgba(255,255,255,0.08)",
                    border: "1px solid rgba(255,255,255,0.15)",
                    borderRadius: 4,
                    color: "var(--text-primary)",
                    outline: "none",
                    MozAppearance: "textfield",
                  }}
                  title="Go to page"
                />
                <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>/</span>
                <span style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500 }}>{pageCount}</span>
              </div>
              <button
                className="btn-ghost btn-sm"
                onClick={() => setActivePage(Math.min(pageCount, activePage + 1))}
                disabled={activePage >= pageCount}
                title="Next page"
                style={{ padding: "4px 6px", color: "var(--text-secondary)" }}
              >
                <ChevronRight size={16} />
              </button>
              <button
                className="btn-ghost btn-sm"
                onClick={() => setActivePage(pageCount)}
                disabled={activePage >= pageCount}
                title="Last page"
                style={{ padding: "4px 6px", color: "var(--text-secondary)" }}
              >
                <ChevronsRight size={16} />
              </button>
            </div>
          )}

          {/* Zoom controls — right of page nav */}
          <div style={{ display: "flex", alignItems: "center", gap: 4, marginLeft: pageCount > 1 ? 25 : 0 }}>
            <button
              className="btn-ghost btn-sm"
              onClick={() => setZoom(Math.max(0.1, zoom - 0.1))}
              title="Zoom out"
              style={{ padding: "4px 6px", color: "var(--text-secondary)" }}
            >
              <ZoomOut size={16} />
            </button>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--text-primary)",
                minWidth: 40,
                textAlign: "center",
                cursor: "pointer",
              }}
              onClick={() => setZoom(1)}
              title="Reset zoom to 100%"
            >
              {Math.round(zoom * 100)}%
            </span>
            <button
              className="btn-ghost btn-sm"
              onClick={() => setZoom(zoom + 0.1)}
              title="Zoom in"
              style={{ padding: "4px 6px", color: "var(--text-secondary)" }}
            >
              <ZoomIn size={16} />
            </button>
          </div>
        </div>

      </div>

      {/* Content area — everything below toolbar */}
      <div ref={contentAreaRef} style={styles.contentArea}>

      {/* Cursor tool toolbar — fixed next to left sidebar, like zoom control */}
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
          cursor: isDraggingCursorToolbar ? CURSOR_GRABBING : "default",
        }}
      >
        {/* Drag handle header */}
        <div
          onMouseDown={(e) => {
            e.stopPropagation();
            setIsDraggingCursorToolbar(true);
            cursorToolbarDragStart.current = {
              mouseX: e.clientX,
              mouseY: e.clientY,
              startX: cursorToolbarPos.x,
              startY: cursorToolbarPos.y,
            };
          }}
          style={{
            padding: "4px 6px",
            background: "var(--bg-primary)",
            cursor: isDraggingCursorToolbar ? CURSOR_GRABBING : CURSOR_GRAB,
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
              setCursorToolbarExpanded(!cursorToolbarExpanded);
              try { localStorage.setItem('cursorToolbarExpanded', String(!cursorToolbarExpanded)); } catch {}
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
            title={cursorToolbarExpanded ? "Collapse" : "Expand"}
          >
            {cursorToolbarExpanded ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
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
            onClick={(e) => { e.stopPropagation(); setCursorTool("pointer"); }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: cursorTool === "pointer" ? "var(--bg-primary)" : "transparent",
              border: cursorTool === "pointer" ? "1px solid var(--accent-primary)" : "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: cursorTool === "pointer" ? "var(--accent-primary)" : "var(--text-primary)",
              fontWeight: cursorTool === "pointer" ? 600 : 400,
              whiteSpace: "nowrap",
            }}
            title="Pointer — pan & select (Esc)"
          >
            <MousePointer size={16} />
            {cursorToolbarExpanded && "Pointer"}
          </button>

          {/* Lasso */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.stopPropagation(); setCursorTool("lasso"); }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: cursorTool === "lasso" ? "var(--bg-primary)" : "transparent",
              border: cursorTool === "lasso" ? "1px solid var(--accent-primary)" : "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: cursorTool === "lasso" ? "var(--accent-primary)" : "var(--text-primary)",
              fontWeight: cursorTool === "lasso" ? 600 : 400,
              whiteSpace: "nowrap",
            }}
            title="Lasso — drag to select multiple regions"
          >
            <BoxSelect size={16} />
            {cursorToolbarExpanded && "Lasso"}
          </button>

          {/* Draw */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.stopPropagation(); setCursorTool("draw"); }}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: cursorTool === "draw" ? "var(--bg-primary)" : "transparent",
              border: cursorTool === "draw" ? "1px solid var(--accent-primary)" : "1px solid transparent",
              borderRadius: 4,
              cursor: "pointer",
              color: cursorTool === "draw" ? "var(--accent-primary)" : "var(--text-primary)",
              fontWeight: cursorTool === "draw" ? 600 : 400,
              whiteSpace: "nowrap",
            }}
            title="Draw — create new anonymization region"
          >
            <PenTool size={16} />
            {cursorToolbarExpanded && "Draw"}
          </button>

          {/* Separator */}
          <div style={{ height: 1, background: "rgba(255,255,255,0.15)", margin: "2px 4px" }} />

          {/* Undo */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.stopPropagation(); undo(); }}
            disabled={!canUndo}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: canUndo ? "pointer" : "default",
              color: canUndo ? "var(--text-primary)" : "var(--text-secondary)",
              opacity: canUndo ? 1 : 0.4,
              whiteSpace: "nowrap",
            }}
            title="Undo (Ctrl+Z)"
          >
            <Undo2 size={16} />
            {cursorToolbarExpanded && "Undo"}
          </button>

          {/* Redo */}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.stopPropagation(); redo(); }}
            disabled={!canRedo}
            style={{
              padding: "8px",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 4,
              cursor: canRedo ? "pointer" : "default",
              color: canRedo ? "var(--text-primary)" : "var(--text-secondary)",
              opacity: canRedo ? 1 : 0.4,
              whiteSpace: "nowrap",
            }}
            title="Redo (Ctrl+Y)"
          >
            <Redo2 size={16} />
            {cursorToolbarExpanded && "Redo"}
          </button>
        </div>
      </div>

      {/* Multi-select toolbar — shown when multiple regions selected */}
      {selectedRegionIds.length > 1 && (
        <div
          ref={multiSelectToolbarRef}
          data-multi-select-toolbar
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          style={{
            position: "fixed",
            left: multiSelectToolbarPos.x,
            top: multiSelectToolbarPos.y,
            zIndex: 30,
            background: "var(--bg-secondary)",
            borderRadius: 8,
            boxShadow: "0 2px 12px rgba(0,0,0,0.5)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            cursor: isDraggingMultiSelectToolbar ? CURSOR_GRABBING : "default",
          }}
        >
          {/* Drag handle header */}
          <div
            onMouseDown={(e) => {
              e.stopPropagation();
              setIsDraggingMultiSelectToolbar(true);
              multiSelectToolbarDragStart.current = {
                mouseX: e.clientX,
                mouseY: e.clientY,
                startX: multiSelectToolbarPos.x,
                startY: multiSelectToolbarPos.y,
              };
            }}
            style={{
              padding: "4px 6px",
              background: "var(--bg-primary)",
              cursor: isDraggingMultiSelectToolbar ? CURSOR_GRABBING : CURSOR_GRAB,
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
                setMultiSelectToolbarExpanded(!multiSelectToolbarExpanded);
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
              title={multiSelectToolbarExpanded ? "Collapse" : "Expand"}
            >
              {multiSelectToolbarExpanded ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
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
                if (!activeDocId || selectedRegionIds.length === 0) return;
                pushUndo();
                selectedRegionIds.forEach(id => handleHighlightAll(id));
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
              title="Replace all matching text"
              className="btn-ghost btn-sm"
            >
              <Type size={16} />
              {multiSelectToolbarExpanded && "Replace all"}
            </button>

            {/* Detect */}
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                if (!activeDocId || selectedRegionIds.length === 0) return;
                pushUndo();
                selectedRegionIds.forEach(id => handleRefreshRegion(id));
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
              title="Re-detect content"
              className="btn-ghost btn-sm"
            >
              <Search size={16} />
              {multiSelectToolbarExpanded && "Detect"}
            </button>

            {/* Edit */}
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                setShowMultiSelectEdit(!showMultiSelectEdit);
              }}
              style={{
                padding: "8px",
                fontSize: 12,
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: showMultiSelectEdit ? "var(--bg-primary)" : "transparent",
                border: "1px solid transparent",
                borderRadius: 4,
                cursor: "pointer",
                color: "var(--text-primary)",
                fontWeight: showMultiSelectEdit ? 600 : 400,
                whiteSpace: "nowrap",
              }}
              title="Edit label"
              className="btn-ghost btn-sm"
            >
              <Edit3 size={16} />
              {multiSelectToolbarExpanded && "Edit"}
            </button>

            {/* Clear */}
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                if (!activeDocId || selectedRegionIds.length === 0) return;
                pushUndo();
                const ids = [...selectedRegionIds];
                batchDeleteRegions(activeDocId, ids).catch(() => {});
                ids.forEach(id => removeRegion(id));
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
              {multiSelectToolbarExpanded && "Clear"}
            </button>

            {/* Separator */}
            <div style={{ height: 1, background: "rgba(255,255,255,0.15)", margin: "2px 4px" }} />

            {/* Tokenize */}
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                if (!activeDocId || selectedRegionIds.length === 0) return;
                pushUndo();
                selectedRegionIds.forEach(id => {
                  setRegionAction(activeDocId, id, "TOKENIZE").catch(() => {});
                  updateRegionAction(id, "TOKENIZE");
                });
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
              {multiSelectToolbarExpanded && "Tokenize"}
            </button>

            {/* Remove */}
            <button
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                if (!activeDocId || selectedRegionIds.length === 0) return;
                pushUndo();
                selectedRegionIds.forEach(id => {
                  setRegionAction(activeDocId, id, "REMOVE").catch(() => {});
                  updateRegionAction(id, "REMOVE");
                });
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
              {multiSelectToolbarExpanded && "Remove"}
            </button>
          </div>
        </div>
      )}

      {/* Multi-select edit dialog */}
      {showMultiSelectEdit && selectedRegionIds.length > 1 && (
        <div
          style={{
            position: "fixed",
            left: multiSelectToolbarPos.x + 100,
            top: multiSelectToolbarPos.y,
            zIndex: 1000,
            background: "var(--bg-secondary)",
            borderRadius: 8,
            boxShadow: "0 4px 24px rgba(0,0,0,0.6)",
            minWidth: 280,
            maxWidth: 350,
            border: "1px solid var(--border-color)",
            padding: 12,
          }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: "var(--text-primary)" }}>
            Change Label for {selectedRegionIds.length} Regions
          </div>
          <select
            autoFocus
            value={multiSelectEditLabel}
            onChange={(e) => setMultiSelectEditLabel(e.target.value as PIIType)}
            style={{
              width: "100%",
              padding: "6px 8px",
              fontSize: 13,
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 4,
              color: "var(--text-primary)",
              marginBottom: 8,
            }}
          >
            {visibleLabels.map((entry) => (
              <option key={entry.label} value={entry.label}>{entry.label}</option>
            ))}
          </select>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn-primary"
              onClick={() => {
                if (!activeDocId || selectedRegionIds.length === 0) return;
                pushUndo();
                selectedRegionIds.forEach(id => {
                  updateRegion(id, { pii_type: multiSelectEditLabel });
                  updateRegionLabel(activeDocId, id, multiSelectEditLabel).catch(() => {});
                });
                setShowMultiSelectEdit(false);
              }}
              style={{ flex: 1 }}
            >
              Apply
            </button>
            <button
              className="btn-ghost btn-sm"
              onClick={() => setShowMultiSelectEdit(false)}
              style={{ flex: 1 }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Export dialog */}
      <ExportDialog open={showExportDialog} onClose={() => setShowExportDialog(false)} />

      {/* Vault unlock prompt overlay */}
      {showVaultPrompt && (
        <div style={styles.overlay}>
          <div style={styles.dialog}>
            <Lock size={24} style={{ color: "var(--accent-warning)", marginBottom: 8 }} />
            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Unlock Vault</h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
              Tokenization requires the vault to store reversible mappings.
              Enter your passphrase to unlock or create the vault.
            </p>
            <div style={{ display: "flex", gap: 8, width: "100%" }}>
              <input
                type="password"
                value={vaultPass}
                onChange={(e) => setVaultPass(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleVaultUnlockAndAnonymize()}
                placeholder="Vault passphrase"
                autoFocus
                style={{ flex: 1 }}
              />
              <button
                className="btn-primary"
                onClick={handleVaultUnlockAndAnonymize}
                disabled={!vaultPass || isProcessing}
              >
                Unlock & Anonymize
              </button>
            </div>
            {vaultError && <p style={{ color: "var(--accent-danger)", fontSize: 12, marginTop: 6 }}>{vaultError}</p>}
            <button
              className="btn-ghost btn-sm"
              style={{ marginTop: 8 }}
              onClick={() => { setShowVaultPrompt(false); setVaultPass(""); setVaultError(""); }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Canvas area */}
      <div ref={containerRef} style={{
        ...styles.canvasArea,
        paddingRight: sidebarCollapsed ? 60 : 320,
        transition: 'padding-right 0.2s ease',
      }}>
        <div
          style={{
            ...styles.pageContainer,
            transform: `scale(${zoom})`,
            transformOrigin: "top center",
          }}
        >
          <div
            style={{ position: "relative", display: "inline-block", userSelect: "none" }}
            ref={imageContainerRef}
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp}
            onMouseLeave={() => { if (isPanning) { setIsPanning(false); panStartRef.current = null; } }}
          >
            <img
              ref={imageRef}
              src={bitmapUrl}
              alt={`Page ${activePage}`}
              style={{
                ...styles.pageImage,
                cursor: cursorTool === "draw" ? CURSOR_CROSSHAIR
                  : cursorTool === "lasso" ? 'crosshair'
                  : isPanning ? 'grabbing' : 'default',
              }}
              onLoad={onImageLoad}
              draggable={false}
            />

            {/* Lasso rectangle preview */}
            {isLassoing && lassoStart && lassoEnd && (
              <div
                style={{
                  position: "absolute",
                  left: Math.min(lassoStart.x, lassoEnd.x),
                  top: Math.min(lassoStart.y, lassoEnd.y),
                  width: Math.abs(lassoEnd.x - lassoStart.x),
                  height: Math.abs(lassoEnd.y - lassoStart.y),
                  border: "1.5px dashed rgba(160,160,160,0.7)",
                  background: "rgba(100, 150, 255, 0.08)",
                  borderRadius: 2,
                  pointerEvents: "none",
                  zIndex: 20,
                }}
              />
            )}

            {/* Drawing rectangle preview */}
            {isDrawing && drawStart && drawEnd && (
              <div
                style={{
                  position: "absolute",
                  left: Math.min(drawStart.x, drawEnd.x),
                  top: Math.min(drawStart.y, drawEnd.y),
                  width: Math.abs(drawEnd.x - drawStart.x),
                  height: Math.abs(drawEnd.y - drawStart.y),
                  border: "2px dashed var(--accent-primary)",
                  background: "rgba(33, 150, 243, 0.15)",
                  borderRadius: 2,
                  pointerEvents: "none",
                  zIndex: 20,
                }}
              />
            )}

            {/* PII Region overlays */}
            {imgLoaded &&
              pageData &&
              pageRegions.map((region) => {
                const isInSelection = selectedRegionIds.includes(region.id);
                const isMulti = selectedRegionIds.length > 1;
                return (
                  <RegionOverlay
                    key={region.id}
                    region={region}
                    pageWidth={pageData.width}
                    pageHeight={pageData.height}
                    imgWidth={imgSize.width}
                    imgHeight={imgSize.height}
                    isSelected={isInSelection}
                    isMultiSelected={isMulti && isInSelection}
                    isImageFile={isImageFile}
                    onSelect={(e: React.MouseEvent) => {
                      toggleSelectedRegionId(region.id, e.ctrlKey || e.metaKey);
                    }}
                    onAction={handleRegionAction}
                    onClear={handleClearRegion}
                    onRefresh={handleRefreshRegion}
                    onHighlightAll={handleHighlightAll}
                    onMoveStart={handleMoveStart}
                    onResizeStart={handleResizeStart}
                    onUpdateLabel={handleUpdateLabel}
                    onUpdateText={handleUpdateText}
                    portalTarget={contentAreaRef.current}
                    imageContainerEl={imageContainerRef.current}
                    cursorToolbarExpanded={cursorToolbarExpanded}
                  />
                );
              })}

            {/* Multi-select bounding box */}
            {imgLoaded && pageData && selectedRegionIds.length > 1 && (() => {
              const selRegions = pageRegions.filter((r) => selectedRegionIds.includes(r.id) && r.action !== "CANCEL");
              if (selRegions.length < 2) return null;
              const sx = imgSize.width / pageData.width;
              const sy = imgSize.height / pageData.height;
              const bx0 = Math.min(...selRegions.map((r) => r.bbox.x0 * sx));
              const by0 = Math.min(...selRegions.map((r) => r.bbox.y0 * sy));
              const bx1 = Math.max(...selRegions.map((r) => r.bbox.x1 * sx));
              const by1 = Math.max(...selRegions.map((r) => r.bbox.y1 * sy));
              const pad = 6;
              const types = new Set(selRegions.map((r) => r.pii_type));
              const label = types.size === 1 ? `${selRegions.length} × ${[...types][0]}` : `${selRegions.length} regions (multiple types)`;
              return (
                <>
                  {/* Bounding rectangle */}
                  <div
                    style={{
                      position: "absolute",
                      left: bx0 - pad,
                      top: by0 - pad,
                      width: bx1 - bx0 + pad * 2,
                      height: by1 - by0 + pad * 2,
                      border: "2px dashed var(--accent-primary)",
                      borderRadius: 4,
                      pointerEvents: "none",
                      zIndex: 8,
                    }}
                  />
                  {/* Label */}
                  <div
                    style={{
                      position: "absolute",
                      left: bx0 - pad,
                      top: by0 - pad - 20,
                      fontSize: 10,
                      fontWeight: 600,
                      color: "white",
                      background: "var(--accent-primary)",
                      padding: "2px 8px",
                      borderRadius: "4px 4px 0 0",
                      zIndex: 9,
                      whiteSpace: "nowrap",
                      pointerEvents: "none",
                    }}
                  >
                    {label}
                  </div>
                </>
              );
            })()}
          </div>
        </div>

      </div>

      {/* PII Type Picker dialog — shown after drawing a region */}
      {showTypePicker && (
        <div style={styles.overlay}>
          <div style={{ ...styles.dialog, maxWidth: 520, maxHeight: '90vh', overflow: 'auto' }}>
            <PenTool size={24} style={{ color: "var(--accent-primary)", marginBottom: 8 }} />
            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
              Select PII Type
            </h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
              What type of sensitive data does this region contain?
            </p>

            {/* ── Frequent labels (big buttons) ── */}
            {!typePickerEditMode && frequentLabels.length > 0 && (
              <>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Frequent</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, width: "100%", marginBottom: 12 }}>
                  {frequentLabels.map((entry) => (
                    <button
                      key={entry.label}
                      className="btn-ghost"
                      style={{
                        padding: "10px 12px",
                        fontSize: 13,
                        fontWeight: 600,
                        borderRadius: 8,
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        justifyContent: "flex-start",
                        border: `1.5px solid ${entry.color}22`,
                        background: `${entry.color}0a`,
                      }}
                      onClick={() => handleTypePickerSelect(entry.label)}
                    >
                      <span style={{ width: 10, height: 10, borderRadius: "50%", background: entry.color, flexShrink: 0 }} />
                      {entry.label}
                    </button>
                  ))}
                </div>
              </>
            )}

            {/* ── Other labels (smaller buttons) ── */}
            {!typePickerEditMode && otherLabels.length > 0 && (
              <>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Other</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, width: "100%", marginBottom: 12 }}>
                  {otherLabels.map((entry) => (
                    <button
                      key={entry.label}
                      className="btn-ghost"
                      style={{
                        padding: "5px 8px",
                        fontSize: 11,
                        fontWeight: 500,
                        borderRadius: 6,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        justifyContent: "flex-start",
                      }}
                      onClick={() => handleTypePickerSelect(entry.label)}
                    >
                      <span style={{ width: 7, height: 7, borderRadius: "50%", background: entry.color, flexShrink: 0 }} />
                      {entry.label}
                    </button>
                  ))}
                </div>
              </>
            )}

            {/* ── Edit mode ── */}
            {typePickerEditMode && (
              <div style={{ width: "100%", marginBottom: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>Manage Labels</div>

                {/* Add new label */}
                <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
                  <input
                    type="text"
                    placeholder="New label name..."
                    value={typePickerNewLabel}
                    onChange={(e) => setTypePickerNewLabel(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_"))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && typePickerNewLabel.length > 0) {
                        const name = typePickerNewLabel;
                        if (labelConfig.some((x) => x.label === name)) return;
                        updateLabelConfig((prev) => [...prev, {
                          label: name,
                          frequent: false,
                          hidden: false,
                          userAdded: true,
                          color: `hsl(${Math.floor(Math.random() * 360)}, 55%, 50%)`,
                        }]);
                        setTypePickerNewLabel("");
                      }
                    }}
                    style={{
                      flex: 1,
                      padding: "6px 10px",
                      fontSize: 12,
                      background: "var(--bg-primary)",
                      border: "1px solid var(--border-color)",
                      borderRadius: 6,
                      color: "var(--text-primary)",
                    }}
                  />
                  <button
                    className="btn-primary"
                    disabled={typePickerNewLabel.length === 0 || labelConfig.some((x) => x.label === typePickerNewLabel)}
                    onClick={() => {
                      const name = typePickerNewLabel;
                      if (!name || labelConfig.some((x) => x.label === name)) return;
                      updateLabelConfig((prev) => [...prev, {
                        label: name,
                        frequent: false,
                        hidden: false,
                        userAdded: true,
                        color: `hsl(${Math.floor(Math.random() * 360)}, 55%, 50%)`,
                      }]);
                      setTypePickerNewLabel("");
                    }}
                    style={{ padding: "6px 12px", fontSize: 12 }}
                  >
                    Add
                  </button>
                </div>

                {/* Label list */}
                <div style={{ maxHeight: 320, overflowY: "auto", display: "flex", flexDirection: "column", gap: 3 }}>
                  {labelConfig.map((entry) => {
                    const inUse = usedLabels.has(entry.label);
                    return (
                      <div
                        key={entry.label}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          padding: "5px 8px",
                          borderRadius: 6,
                          background: entry.hidden ? "var(--bg-primary)" : "transparent",
                          opacity: entry.hidden ? 0.5 : 1,
                        }}
                      >
                        {/* Color dot */}
                        <span style={{ width: 8, height: 8, borderRadius: "50%", background: entry.color, flexShrink: 0 }} />

                        {/* Label name */}
                        <span style={{ flex: 1, fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>
                          {entry.label}
                          {inUse && <span style={{ fontSize: 10, color: "var(--text-secondary)", marginLeft: 4 }}>(in use)</span>}
                        </span>

                        {/* Frequent star toggle */}
                        <button
                          title={entry.frequent ? "Remove from frequent" : "Add to frequent"}
                          onClick={() => updateLabelConfig((prev) => prev.map((e) => e.label === entry.label ? { ...e, frequent: !e.frequent } : e))}
                          style={{ background: "none", border: "none", cursor: "pointer", padding: 2, fontSize: 14, color: entry.frequent ? "#f59e0b" : "var(--text-secondary)" }}
                        >
                          {entry.frequent ? "★" : "☆"}
                        </button>

                        {/* Hide/show toggle */}
                        <button
                          title={entry.hidden ? "Show label" : "Hide label"}
                          onClick={() => updateLabelConfig((prev) => prev.map((e) => e.label === entry.label ? { ...e, hidden: !e.hidden } : e))}
                          style={{ background: "none", border: "none", cursor: "pointer", padding: 2, fontSize: 12, color: "var(--text-secondary)" }}
                        >
                          {entry.hidden ? "👁" : "🙈"}
                        </button>

                        {/* Delete (only user-added AND not in use) */}
                        {entry.userAdded && !inUse && (
                          <button
                            title="Delete label"
                            onClick={() => updateLabelConfig((prev) => prev.filter((e) => e.label !== entry.label))}
                            style={{ background: "none", border: "none", cursor: "pointer", padding: 2, fontSize: 12, color: "#ef4444" }}
                          >
                            <Trash2 size={12} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Bottom actions */}
            <div style={{ display: "flex", gap: 8, width: "100%" }}>
              <button
                className="btn-ghost btn-sm"
                onClick={() => { setTypePickerEditMode(!typePickerEditMode); setTypePickerNewLabel(""); }}
                style={{ display: "flex", alignItems: "center", gap: 4 }}
              >
                <Edit3 size={12} />
                {typePickerEditMode ? "Done" : "Edit"}
              </button>
              <div style={{ flex: 1 }} />
              <button
                className="btn-ghost btn-sm"
                onClick={() => { cancelTypePicker(); setTypePickerEditMode(false); }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Region sidebar */}
      <div ref={sidebarRef} style={{
        ...styles.sidebar,
        width: sidebarCollapsed ? 60 : 320,
        transition: 'width 0.2s ease',
      }}>
        {sidebarCollapsed ? (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            padding: '16px 8px',
            gap: 16,
          }}>
            <Shield size={24} color="var(--text-secondary)" />
            <div style={{
              background: 'var(--accent-primary)',
              color: 'white',
              fontSize: 12,
              fontWeight: 600,
              padding: '4px 8px',
              borderRadius: 12,
              minWidth: 32,
              textAlign: 'center',
            }}>
              {pageRegions.length}
            </div>
            <button
              onClick={() => setSidebarCollapsed(false)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                padding: 8,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Expand sidebar"
            >
              <ChevronLeft size={20} />
            </button>
          </div>
        ) : (
          <>
            <div style={{
              ...styles.sidebarTitle,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'rgba(0,0,0,0.15)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Shield size={18} color="var(--text-secondary)" />
                <span>Detected ({pageRegions.length})</span>
              </div>
              <button
                onClick={() => setSidebarCollapsed(true)}
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
                title="Collapse sidebar"
              >
                <ChevronRight size={16} />
              </button>
            </div>
            {/* Bulk actions toolbar */}
            {pageRegions.length > 0 && (() => {
              const activeRegions = pageRegions.filter(r => r.action !== "CANCEL");
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
                    batchRegionAction(activeDocId, ids, newAction).catch(() => {});
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
                  title={allTokenized ? "Undo tokenize all" : "Tokenize all regions on this page"}
                >
                  <Key size={13} />
                  Tokenize all
                </button>
                <button
                  onClick={() => {
                    if (!activeDocId) return;
                    pushUndo();
                    const ids = activeRegions.map(r => r.id);
                    const newAction = allRemoved ? "PENDING" : "REMOVE";
                    ids.forEach(id => updateRegionAction(id, newAction));
                    batchRegionAction(activeDocId, ids, newAction).catch(() => {});
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
                  title={allRemoved ? "Undo remove all" : "Remove all regions on this page"}
                >
                  <Trash2 size={13} />
                  Remove all
                </button>
                <button
                  onClick={() => {
                    if (!activeDocId) return;
                    pushUndo();
                    const ids = activeRegions.map(r => r.id);
                    ids.forEach(id => removeRegion(id));
                    batchDeleteRegions(activeDocId, ids).catch(() => {});
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
                    border: "1px solid transparent",
                    background: "transparent",
                    color: "var(--text-secondary)",
                    transition: "all 0.15s ease",
                  }}
                  title="Clear all regions from this page"
                >
                  <X size={13} />
                  Clear all
                </button>
                </div>
              </div>
              );
            })()}
            <div style={styles.regionList}>
          {pageRegions.map((r) => (
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
              onClick={(e) => toggleSelectedRegionId(r.id, e.ctrlKey || e.metaKey)}
            >
              {/* Clear — top-right close button */}
              <button
                className="btn-ghost btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  handleClearRegion(r.id);
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
              <div style={styles.regionActions}>
                {/* Replace all */}
                <button
                  className="btn-ghost btn-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleHighlightAll(r.id);
                  }}
                  title="Replace all matching"
                  style={styles.sidebarBtn}
                >
                  <Type size={13} />
                </button>
                {/* Detect */}
                <button
                  className="btn-ghost btn-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRefreshRegion(r.id);
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
                    setSelectedRegionIds([r.id]);
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
                    handleRegionAction(r.id, r.action === "TOKENIZE" ? "PENDING" : "TOKENIZE");
                  }}
                  title={r.action === "TOKENIZE" ? "Undo tokenize" : "Tokenize"}
                  style={{
                    ...styles.sidebarBtn,
                    border: r.action === "TOKENIZE" ? "1px solid #9c27b0" : "1px solid transparent",
                    background: r.action === "TOKENIZE" ? "rgba(156,39,176,0.15)" : "transparent",
                    color: "#9c27b0",
                    boxShadow: r.action === "TOKENIZE" ? "0 0 6px rgba(156,39,176,0.3)" : "none",
                    transition: "all 0.15s ease",
                  }}
                >
                  <Key size={13} />
                </button>
                {/* Remove */}
                <button
                  className="btn-danger btn-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRegionAction(r.id, r.action === "REMOVE" ? "PENDING" : "REMOVE");
                  }}
                  title={r.action === "REMOVE" ? "Undo remove" : "Remove"}
                  style={{
                    ...styles.sidebarBtn,
                    border: r.action === "REMOVE" ? "1px solid #f44336" : "1px solid transparent",
                    background: r.action === "REMOVE" ? "rgba(244,67,54,0.15)" : "transparent",
                    color: "#f44336",
                    boxShadow: r.action === "REMOVE" ? "0 0 6px rgba(244,67,54,0.3)" : "none",
                    transition: "all 0.15s ease",
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
              {r.action !== "PENDING" && (
                <div
                  style={{
                    ...styles.actionStatus,
                    color:
                      r.action === "REMOVE"
                        ? "var(--accent-danger)"
                        : r.action === "TOKENIZE"
                        ? "var(--accent-tokenize)"
                        : "var(--text-muted)",
                  }}
                >
                  {r.action === "CANCEL" ? "✕ Dismissed" : `✓ ${r.action}`}
                </div>
              )}
            </div>
          ))}
          {pageRegions.length === 0 && (
            <p style={{ color: "var(--text-muted)", padding: 12, fontSize: 13 }}>
              No PII detected on this page.
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
      </div>
      </div>{/* end contentArea */}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    position: "relative" as const,
    display: "flex",
    flexDirection: "column",
    height: "100%",
    overflow: "hidden",
  },
  toolbar: {
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "8px 16px",
    background: "var(--bg-secondary)",
    borderBottom: "1px solid var(--border-color)",
    flexWrap: "wrap",
    position: "relative" as const,
    zIndex: 40,
  },
  contentArea: {
    flex: 1,
    position: "relative" as const,
    overflow: "hidden",
    minHeight: 0,
  },
  toolbarGroup: {
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  pageInfo: { fontSize: 13, color: "var(--text-secondary)", minWidth: 80, textAlign: "center" },
  zoomLabel: { fontSize: 12, color: "var(--text-muted)", minWidth: 40, textAlign: "center" },
  statBadge: {
    fontSize: 11,
    color: "var(--text-secondary)",
    background: "var(--bg-surface)",
    padding: "2px 8px",
    borderRadius: 4,
  },
  canvasArea: {
    position: "absolute" as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    overflow: "auto",
    background: "var(--bg-primary)",
    display: "flex",
    justifyContent: "center",
    paddingTop: 20,
    paddingBottom: 20,
  },
  pageContainer: {
    transition: "transform 0.15s ease",
  },
  pageImage: {
    display: "block",
    maxWidth: "100%",
    boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
  },
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
    zIndex: 10,
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
    maxWidth: 260,
  },
  regionActions: {
    display: "flex",
    alignItems: "center",
    gap: 2,
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
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 5,
    cursor: "pointer",
    color: "var(--text-secondary)",
    transition: "opacity 0.15s ease, color 0.15s ease, background 0.15s ease",
  },
  actionStatus: {
    fontSize: 11,
    fontWeight: 500,
    marginTop: 4,
  },
  empty: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    color: "var(--text-muted)",
  },
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 100,
  },
  dialog: {
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    borderRadius: 12,
    padding: 24,
    maxWidth: 420,
    width: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
  },
};
