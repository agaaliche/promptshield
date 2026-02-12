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
  logError,
} from "../api";
import { PII_COLORS, getPIIColor, loadLabelConfig, cacheLabelConfig, ensureBuiltinLabels, type PIILabelEntry, type BBox, type PIIRegion, type PIIType, type RegionAction } from "../types";
import { CURSOR_CROSSHAIR, CURSOR_GRAB, CURSOR_GRABBING } from "../cursors";
import { resolveAllOverlaps } from "../regionUtils";
import RegionOverlay, { type ResizeHandle } from "./RegionOverlay";
import ExportDialog from "./ExportDialog";
import DetectionProgressDialog from "./DetectionProgressDialog";
import PIITypePicker from "./PIITypePicker";
import RegionSidebar from "./RegionSidebar";
import PageNavigator from "./PageNavigator";
import useDraggableToolbar from "../hooks/useDraggableToolbar";
import useKeyboardShortcuts from "../hooks/useKeyboardShortcuts";
import useLabelConfig from "../hooks/useLabelConfig";
import AutodetectPanel from "./AutodetectPanel";
import VaultUnlockDialog from "./VaultUnlockDialog";
import CursorToolToolbar from "./CursorToolToolbar";
import MultiSelectToolbar from "./MultiSelectToolbar";
import UserMenu from "./UserMenu";

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
    rightSidebarWidth,
    setRightSidebarWidth,
    isSidebarDragging,
    llmStatus,
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
  // Progress dialog for redetection
  const [redetecting, setRedetecting] = useState(false);

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
  const [sidebarTypeFilter, setSidebarTypeFilter] = useState<Set<string> | null>(null); // null = all types
  const [pageNavCollapsed, setPageNavCollapsed] = useState(false);

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
  
  const { pos: cursorToolbarPos, isDragging: isDraggingCursorToolbar, startDrag: startCursorToolbarDrag, constrainToArea: constrainCursorToolbar } = useDraggableToolbar({
    storageKey: 'cursorToolbarPos',
    defaultPos: { x: 208, y: 60 },
    toolbarRef: cursorToolbarRef,
    boundaryRef: contentAreaRef,
    sidebarRef,
    sidebarCollapsed,
  });

  // Multi-select toolbar state
  const [multiSelectToolbarExpanded, setMultiSelectToolbarExpanded] = useState(() => {
    try {
      const saved = localStorage.getItem('multiSelectToolbarExpanded');
      return saved === 'true';
    } catch {}
    return false;
  });
  const multiSelectToolbarRef = useRef<HTMLDivElement>(null);
  const { pos: multiSelectToolbarPos, isDragging: isDraggingMultiSelectToolbar, startDrag: startMultiSelectToolbarDrag, constrainToArea: constrainMultiSelectToolbar } = useDraggableToolbar({
    storageKey: 'multiSelectToolbarPos',
    defaultPos: { x: 300, y: 200 },
    toolbarRef: multiSelectToolbarRef,
    boundaryRef: contentAreaRef,
    sidebarRef,
    sidebarCollapsed,
  });
  const [showMultiSelectEdit, setShowMultiSelectEdit] = useState(false);
  const [multiSelectEditLabel, setMultiSelectEditLabel] = useState<PIIType>("PERSON");
  
  const setCursorTool = useCallback((tool: CursorTool) => {
    setCursorToolRaw(tool);
    setDrawMode(tool === "draw");
  }, [setDrawMode]);
  
  useEffect(() => {
    try {
      localStorage.setItem('multiSelectToolbarExpanded', String(multiSelectToolbarExpanded));
    } catch {}
  }, [multiSelectToolbarExpanded]);

  useEffect(() => {
    constrainCursorToolbar();
    constrainMultiSelectToolbar();
  }, [sidebarCollapsed, constrainCursorToolbar, constrainMultiSelectToolbar]);

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
  const skipAutoSelectRef = useRef(false);
  useEffect(() => {
    if (activePage !== prevPageRef.current) {
      prevPageRef.current = activePage;
      if (skipAutoSelectRef.current) {
        skipAutoSelectRef.current = false;
        return;
      }
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
        pushUndo();
        updateRegion(regionId, { pii_type: newType });
        await updateRegionLabel(activeDocId, regionId, newType);
      } catch (e: any) {
        console.error("Update label failed:", e);
        setStatusMessage(`Update failed: ${e.message}`);
      }
    },
    [activeDocId, pushUndo, updateRegion, setStatusMessage]
  );

  const handleUpdateText = useCallback(
    async (regionId: string, newText: string) => {
      if (!activeDocId) return;
      try {
        pushUndo();
        updateRegion(regionId, { text: newText });
        await updateRegionText(activeDocId, regionId, newText);
      } catch (e: any) {
        console.error("Update text failed:", e);
        setStatusMessage(`Update failed: ${e.message}`);
      }
    },
    [activeDocId, pushUndo, updateRegion, setStatusMessage]
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

  useKeyboardShortcuts({
    activePage, pageCount, zoom, regions, pageRegions, selectedRegionIds,
    copiedRegions, activeDocId: activeDocId ?? null, cursorTool, showTypePicker,
    canUndo, canRedo, setActivePage, setZoom, setSelectedRegionIds, clearSelection,
    setCursorTool, prevCursorToolRef, cancelTypePicker, handleRegionAction,
    undo, redo, pushUndo, removeRegion, setCopiedRegions, setStatusMessage,
    handlePasteRegions, batchDeleteRegions,
  });

  // ── Autodetect (redetect) ──
  const handleAutodetect = useCallback(async (opts: {
    fuzziness: number;
    scope: "page" | "all";
    regexEnabled: boolean;
    nerEnabled: boolean;
    llmEnabled: boolean;
    regexTypes: string[];
    nerTypes: string[];
  }) => {
    if (!activeDocId) return;
    setIsProcessing(true);
    setRedetecting(true);
    setStatusMessage("Running PII autodetection…");
    try {
      pushUndo();
      const result = await redetectPII(activeDocId, {
        confidence_threshold: opts.fuzziness,
        page_number: opts.scope === "page" ? activePage : undefined,
        regex_enabled: opts.regexEnabled,
        ner_enabled: opts.nerEnabled,
        llm_detection_enabled: opts.llmEnabled,
        regex_types: opts.regexEnabled ? opts.regexTypes : null,
        ner_types: opts.nerEnabled ? opts.nerTypes : null,
      });
      setRegions(resolveAllOverlaps(result.regions));
      setStatusMessage(
        `Autodetect: ${result.added} added, ${result.updated} updated (${result.total_regions} total)`
      );
    } catch (err) {
      setStatusMessage(`Autodetect failed: ${err}`);
    } finally {
      setIsProcessing(false);
      setRedetecting(false);
    }
  }, [activeDocId, activePage, pushUndo, setRegions, setIsProcessing, setStatusMessage]);

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
      if (result.output_path) {
        window.open(getDownloadUrl(activeDocId, "pdf"), "_blank");
      }
    } catch (e: any) {
      setStatusMessage(`Anonymization failed: ${e.message}`);
    } finally {
      setIsProcessing(false);
    }
  }, [activeDocId, setIsProcessing, setStatusMessage, regions, vaultUnlocked]);

  const handleVaultUnlockAndAnonymize = useCallback(async () => {
    if (!activeDocId) return;
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
        activeDocId,
        regions.map((r) => ({ id: r.id, action: r.action, bbox: r.bbox })),
      );
      const result = await anonymizeDocument(activeDocId);
      setStatusMessage(
        `Done! ${result.regions_removed} removed, ${result.tokens_created} tokenized`
      );
      if (result.output_path) {
        window.open(getDownloadUrl(activeDocId, "pdf"), "_blank");
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
        setImgSize(prev => {
          if (prev.width === img.offsetWidth && prev.height === img.offsetHeight) return prev;
          return { width: img.offsetWidth, height: img.offsetHeight };
        });
      }
    };

    // Update on window resize
    window.addEventListener('resize', updateImageSize);
    
    // Use ResizeObserver on both the image AND its container for reliable tracking
    // during sidebar drag where the container changes size before the image does.
    const img = imageRef.current;
    const container = imageContainerRef.current;
    let observer: ResizeObserver | null = null;
    if (window.ResizeObserver) {
      observer = new ResizeObserver(updateImageSize);
      if (img) observer.observe(img);
      if (container) observer.observe(container);
    }

    return () => {
      window.removeEventListener('resize', updateImageSize);
      if (observer) observer.disconnect();
    };
  }, [imgLoaded]);



  // ── Page data for coordinate mapping ──
  const pageData = doc?.pages?.[activePage - 1];

  // ── Manual draw handlers ──
  const {
    labelConfig, visibleLabels, frequentLabels, otherLabels, usedLabels,
    updateLabelConfig, typePickerEditMode, setTypePickerEditMode,
    typePickerNewLabel, setTypePickerNewLabel,
  } = useLabelConfig(regions);

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
      </div>
    );
  }

  return (
    <div style={styles.wrapper}>

      {/* Re-detection progress overlay */}
      {redetecting && activeDocId && (
        <DetectionProgressDialog
          docId={activeDocId}
          docName={doc.original_filename}
          visible
        />
      )}

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
            <AutodetectPanel
              isProcessing={isProcessing}
              activePage={activePage}
              llmStatus={llmStatus}
              onDetect={(opts) => {
                setShowAutodetect(false);
                handleAutodetect(opts);
              }}
              onClose={() => setShowAutodetect(false)}
            />
        )}
        </div>
        <button
          className="btn-success"
          onClick={() => setShowExportDialog(true)}
          disabled={
            isProcessing ||
            pendingCount > 0 ||
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

        {/* User menu — fixed right edge of toolbar */}
        <div style={{ position: "fixed", right: 16, top: "inherit", display: "flex", alignItems: "center", zIndex: 41, pointerEvents: "auto" }}>
          <UserMenu />
        </div>
      </div>

      {/* Content area — everything below toolbar */}
      <div ref={contentAreaRef} style={styles.contentArea}>

      <CursorToolToolbar
        cursorToolbarRef={cursorToolbarRef}
        cursorToolbarPos={cursorToolbarPos}
        isDragging={isDraggingCursorToolbar}
        startDrag={startCursorToolbarDrag}
        expanded={cursorToolbarExpanded}
        setExpanded={(v) => {
          setCursorToolbarExpanded(v);
          try { localStorage.setItem('cursorToolbarExpanded', String(v)); } catch {}
        }}
        cursorTool={cursorTool}
        setCursorTool={setCursorTool}
        canUndo={canUndo}
        canRedo={canRedo}
        undo={undo}
        redo={redo}
      />

      {/* Multi-select toolbar — shown when multiple regions selected */}
      {selectedRegionIds.length > 1 && (
        <MultiSelectToolbar
          toolbarRef={multiSelectToolbarRef}
          pos={multiSelectToolbarPos}
          isDragging={isDraggingMultiSelectToolbar}
          startDrag={startMultiSelectToolbarDrag}
          expanded={multiSelectToolbarExpanded}
          setExpanded={(v) => {
            setMultiSelectToolbarExpanded(v);
            try { localStorage.setItem('multiSelectToolbarExpanded', String(v)); } catch {}
          }}
          selectedRegionIds={selectedRegionIds}
          regions={regions}
          activeDocId={activeDocId}
          activePage={activePage}
          showEditDialog={showMultiSelectEdit}
          setShowEditDialog={setShowMultiSelectEdit}
          multiSelectEditLabel={multiSelectEditLabel}
          setMultiSelectEditLabel={setMultiSelectEditLabel}
          visibleLabels={visibleLabels}
          frequentLabels={frequentLabels}
          otherLabels={otherLabels}
          pushUndo={pushUndo}
          handleHighlightAll={handleHighlightAll}
          handleRefreshRegion={handleRefreshRegion}
          removeRegion={(_docId, regionId) => removeRegion(regionId)}
          updateRegionAction={(_docId, regionId, action) => updateRegionAction(regionId, action)}
          updateRegion={(_docId, regionId, patch) => updateRegion(regionId, patch)}
          clearSelection={clearSelection}
          setStatusMessage={setStatusMessage}
        />
      )}

      {/* Export dialog */}
      <ExportDialog open={showExportDialog} onClose={() => setShowExportDialog(false)} />

      {/* Vault unlock prompt overlay */}
      {showVaultPrompt && (
        <VaultUnlockDialog
          vaultPass={vaultPass}
          vaultError={vaultError}
          isProcessing={isProcessing}
          onPassChange={setVaultPass}
          onUnlock={handleVaultUnlockAndAnonymize}
          onCancel={() => { setShowVaultPrompt(false); setVaultPass(""); setVaultError(""); }}
        />
      )}

      {/* Canvas area */}
      <div ref={containerRef} style={{
        ...styles.canvasArea,
        paddingRight: (sidebarCollapsed ? 60 : rightSidebarWidth) + (pageCount > 1 ? (pageNavCollapsed ? 28 : 120) : 0),
        transition: isSidebarDragging ? 'none' : 'padding-right 0.2s ease',
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
              pageRegions
                .filter(region => !sidebarTypeFilter || sidebarTypeFilter.has(region.pii_type))
                .map((region) => {
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

      {showTypePicker && (
        <PIITypePicker
          frequentLabels={frequentLabels}
          otherLabels={otherLabels}
          labelConfig={labelConfig}
          usedLabels={usedLabels}
          typePickerEditMode={typePickerEditMode}
          setTypePickerEditMode={setTypePickerEditMode}
          typePickerNewLabel={typePickerNewLabel}
          setTypePickerNewLabel={setTypePickerNewLabel}
          onSelect={handleTypePickerSelect}
          onCancel={() => { cancelTypePicker(); setTypePickerEditMode(false); }}
          updateLabelConfig={updateLabelConfig}
        />
      )}

      <PageNavigator
        docId={activeDocId}
        pageCount={pageCount}
        activePage={activePage}
        onPageSelect={setActivePage}
        rightOffset={sidebarCollapsed ? 60 : rightSidebarWidth}
        collapsed={pageNavCollapsed}
        onCollapsedChange={setPageNavCollapsed}
        regions={regions}
        sidebarWidth={rightSidebarWidth}
        onSidebarWidthChange={setRightSidebarWidth}
      />
      </div>{/* end contentArea */}

      <RegionSidebar
        sidebarRef={sidebarRef}
        collapsed={sidebarCollapsed}
        setCollapsed={setSidebarCollapsed}
        width={rightSidebarWidth}
        onWidthChange={setRightSidebarWidth}
        pageRegions={pageRegions}
        allRegions={regions}
        selectedRegionIds={selectedRegionIds}
        activeDocId={activeDocId ?? null}
        pendingCount={pendingCount}
        removeCount={removeCount}
        tokenizeCount={tokenizeCount}
        onRegionAction={handleRegionAction}
        onClear={handleClearRegion}
        onRefresh={handleRefreshRegion}
        onHighlightAll={handleHighlightAll}
        onToggleSelect={toggleSelectedRegionId}
        onSelect={setSelectedRegionIds}
        onNavigateToRegion={(region) => {
          // Switch page if needed
          if (region.page_number !== activePage) {
            skipAutoSelectRef.current = true;
            setActivePage(region.page_number);
          }
          // Scroll to the region overlay after page renders
          requestAnimationFrame(() => {
            setTimeout(() => {
              const el = contentAreaRef.current?.querySelector(
                `[data-region-id="${region.id}"]`
              ) as HTMLElement | null;
              if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
              }
            }, region.page_number !== activePage ? 150 : 0);
          });
        }}
        pushUndo={pushUndo}
        removeRegion={removeRegion}
        updateRegionAction={updateRegionAction}
        batchRegionAction={batchRegionAction}
        batchDeleteRegions={batchDeleteRegions}
        onTypeFilterChange={setSidebarTypeFilter}
        hideResizeHandle={pageCount > 1}
      />
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
