/** Document viewer — renders page bitmap with PII highlight overlays. */

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Download,
  CheckCircle2,
  XCircle,
  Shield,
  Lock,
  PenTool,
  Undo2,
  Redo2,
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
} from "../api";
import { PII_COLORS, type BBox, type PIIRegion, type PIIType, type RegionAction } from "../types";
import RegionOverlay, { type ResizeHandle } from "./RegionOverlay";

export default function DocumentViewer() {
  const {
    activeDocId,
    documents,
    activePage,
    setActivePage,
    regions,
    updateRegionAction,
    setRegions,
    updateRegionBBox,
    zoom,
    setZoom,
    selectedRegionId,
    setSelectedRegionId,
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
  } = useAppStore();

  const containerRef = useRef<HTMLDivElement>(null);
  const imageContainerRef = useRef<HTMLDivElement>(null);
  const [imgSize, setImgSize] = useState({ width: 0, height: 0 });
  const [imgLoaded, setImgLoaded] = useState(false);
  const [showVaultPrompt, setShowVaultPrompt] = useState(false);
  const [vaultPass, setVaultPass] = useState("");
  const [vaultError, setVaultError] = useState("");

  // ── Manual drawing state ──
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawEnd, setDrawEnd] = useState<{ x: number; y: number } | null>(null);
  const [showTypePicker, setShowTypePicker] = useState(false);
  const [drawnBBox, setDrawnBBox] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

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
  // Keep mutable refs so global event handlers see latest values
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const imgSizeRef = useRef(imgSize);
  imgSizeRef.current = imgSize;

  const doc = documents.find((d) => d.doc_id === activeDocId);
  if (!doc) return <div style={styles.empty}>No document loaded</div>;

  const pageCount = doc.page_count;
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

  const cancelTypePicker = useCallback(() => {
    setShowTypePicker(false);
    setDrawnBBox(null);
  }, []);

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
          setSelectedRegionId(null);
          if (drawMode) setDrawMode(false);
          if (showTypePicker) cancelTypePicker();
          break;
        case "d":
        case "Delete":
          if (selectedRegionId) {
            e.preventDefault();
            handleRegionAction(selectedRegionId, "REMOVE");
          }
          break;
        case "t":
          if (selectedRegionId) {
            e.preventDefault();
            handleRegionAction(selectedRegionId, "TOKENIZE");
          }
          break;
        case "c":
          if (selectedRegionId && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            handleRegionAction(selectedRegionId, "CANCEL");
          }
          break;
        case "Tab": {
          e.preventDefault();
          const pending = pageRegions.filter((r) => r.action === "PENDING");
          if (pending.length === 0) break;
          const currentIdx = pending.findIndex((r) => r.id === selectedRegionId);
          const next = e.shiftKey
            ? (currentIdx <= 0 ? pending.length - 1 : currentIdx - 1)
            : (currentIdx + 1) % pending.length;
          setSelectedRegionId(pending[next].id);
          break;
        }
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [activePage, pageCount, zoom, selectedRegionId, pageRegions, setActivePage, setZoom, setSelectedRegionId, handleRegionAction, undo, redo, drawMode, showTypePicker, cancelTypePicker, setDrawMode]);

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
    setImgSize({ width: img.naturalWidth, height: img.naturalHeight });
    setImgLoaded(true);
  }, []);

  // ── Page data for coordinate mapping ──
  const pageData = doc.pages[activePage - 1];

  // ── Manual draw handlers ──
  const PII_TYPE_OPTIONS: PIIType[] = [
    "PERSON", "ORG", "EMAIL", "PHONE", "SSN",
    "CREDIT_CARD", "DATE", "ADDRESS", "LOCATION",
    "IP_ADDRESS", "IBAN", "PASSPORT", "DRIVER_LICENSE",
    "CUSTOM", "UNKNOWN",
  ];

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
      if (!drawMode) return;
      const pos = getPointerPosOnImage(e);
      if (!pos) return;
      e.preventDefault();
      setIsDrawing(true);
      setDrawStart(pos);
      setDrawEnd(pos);
    },
    [drawMode, getPointerPosOnImage]
  );

  const handleCanvasMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDrawing || !drawMode) return;
      const pos = getPointerPosOnImage(e);
      if (pos) setDrawEnd(pos);
    },
    [isDrawing, drawMode, getPointerPosOnImage]
  );

  const handleCanvasMouseUp = useCallback(
    (e: React.MouseEvent) => {
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

      const x0 = Math.min(drawStart.x, drawEnd.x) * sx;
      const y0 = Math.min(drawStart.y, drawEnd.y) * sy;
      const x1 = Math.max(drawStart.x, drawEnd.x) * sx;
      const y1 = Math.max(drawStart.y, drawEnd.y) * sy;

      setDrawnBBox({ x0, y0, x1, y1 });
      setShowTypePicker(true);
      setDrawStart(null);
      setDrawEnd(null);
    },
    [isDrawing, drawStart, drawEnd, pageData, imgSize]
  );

  // ── Move / resize handlers ──
  const handleMoveStart = useCallback(
    (regionId: string, e: React.MouseEvent) => {
      if (drawMode) return;
      const pos = getPointerPosOnImage(e);
      if (!pos) return;
      const region = regions.find((r) => r.id === regionId);
      if (!region) return;
      e.preventDefault();
      setSelectedRegionId(regionId);
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
    [drawMode, getPointerPosOnImage, regions, setSelectedRegionId],
  );

  const handleResizeStart = useCallback(
    (regionId: string, handle: ResizeHandle, e: React.MouseEvent) => {
      if (drawMode) return;
      const pos = getPointerPosOnImage(e);
      if (!pos) return;
      const region = regions.find((r) => r.id === regionId);
      if (!region) return;
      e.preventDefault();
      setSelectedRegionId(regionId);
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
    [drawMode, getPointerPosOnImage, regions, setSelectedRegionId],
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
      }

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
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isInteracting, pageData, activeDocId, pushUndo, updateRegionBBox]);

  const handleTypePickerSelect = useCallback(
    async (piiType: PIIType) => {
      if (!activeDocId || !drawnBBox) return;
      setShowTypePicker(false);

      const newRegion: Partial<PIIRegion> = {
        page_number: activePage,
        bbox: drawnBBox,
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
          bbox: drawnBBox,
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
      } catch (e: any) {
        setStatusMessage(`Failed to add region: ${e.message}`);
      }
      setDrawnBBox(null);
    },
    [activeDocId, activePage, drawnBBox, regions, setRegions, setStatusMessage, pushUndo]
  );

  return (
    <div style={styles.wrapper}>
      {/* Toolbar */}
      <div style={styles.toolbar}>
        <div style={styles.toolbarGroup}>
          <button
            className="btn-ghost btn-sm"
            onClick={() => setActivePage(Math.max(1, activePage - 1))}
            disabled={activePage <= 1}
          >
            <ChevronLeft size={14} />
          </button>
          <span style={styles.pageInfo}>
            Page {activePage} / {pageCount}
          </span>
          <button
            className="btn-ghost btn-sm"
            onClick={() => setActivePage(Math.min(pageCount, activePage + 1))}
            disabled={activePage >= pageCount}
          >
            <ChevronRight size={14} />
          </button>
        </div>

        <div style={styles.toolbarGroup}>
          <button className="btn-icon" onClick={() => setZoom(zoom - 0.1)}>
            <ZoomOut size={16} />
          </button>
          <span style={styles.zoomLabel}>{Math.round(zoom * 100)}%</span>
          <button className="btn-icon" onClick={() => setZoom(zoom + 0.1)}>
            <ZoomIn size={16} />
          </button>
          <button className="btn-icon" onClick={() => setZoom(1)}>
            <RotateCcw size={14} />
          </button>
        </div>

        <div style={styles.toolbarGroup}>
          <button
            className="btn-ghost btn-sm"
            onClick={undo}
            disabled={!canUndo}
            title="Undo (Ctrl+Z)"
            style={{ padding: "2px 6px" }}
          >
            <Undo2 size={14} />
          </button>
          <button
            className="btn-ghost btn-sm"
            onClick={redo}
            disabled={!canRedo}
            title="Redo (Ctrl+Y)"
            style={{ padding: "2px 6px" }}
          >
            <Redo2 size={14} />
          </button>
        </div>

        <div style={styles.toolbarGroup}>
          <span style={styles.statBadge}>
            {pendingCount} pending
          </span>
          <span style={{ ...styles.statBadge, color: "var(--accent-danger)" }}>
            {removeCount} remove
          </span>
          <span style={{ ...styles.statBadge, color: "var(--accent-tokenize)" }}>
            {tokenizeCount} tokenize
          </span>
        </div>

        <div style={styles.toolbarGroup}>
          <button
            className="btn-ghost btn-sm"
            onClick={() => handleBatchAction("CANCEL")}
            title="Dismiss all pending"
          >
            <XCircle size={14} /> Cancel All
          </button>
          <button
            className="btn-danger btn-sm"
            onClick={() => handleBatchAction("REMOVE")}
            title="Remove all pending"
          >
            Remove All
          </button>
          <button
            className="btn-tokenize btn-sm"
            onClick={() => handleBatchAction("TOKENIZE")}
            title="Tokenize all pending"
          >
            Tokenize All
          </button>
        </div>

        <button
          className="btn-success"
          onClick={handleAnonymize}
          disabled={
            isProcessing ||
            (removeCount === 0 && tokenizeCount === 0)
          }
        >
          <Shield size={14} />
          Anonymize & Export
        </button>

        <button
          className={drawMode ? "btn-primary" : "btn-ghost"}
          onClick={() => setDrawMode(!drawMode)}
          title="Draw manual anonymization region (click and drag on page)"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            ...(drawMode
              ? { boxShadow: "0 0 0 2px var(--accent-primary)" }
              : {}),
          }}
        >
          <PenTool size={14} />
          {drawMode ? "Drawing..." : "Draw Region"}
        </button>
      </div>

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
      <div ref={containerRef} style={styles.canvasArea}>
        <div
          style={{
            ...styles.pageContainer,
            transform: `scale(${zoom})`,
            transformOrigin: "top center",
          }}
        >
          <div
            style={{ position: "relative", display: "inline-block" }}
            ref={imageContainerRef}
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp}
          >
            <img
              src={bitmapUrl}
              alt={`Page ${activePage}`}
              style={{
                ...styles.pageImage,
                cursor: drawMode ? "crosshair" : "default",
              }}
              onLoad={onImageLoad}
              draggable={false}
            />

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
              pageRegions.map((region) => (
                <RegionOverlay
                  key={region.id}
                  region={region}
                  pageWidth={pageData.width}
                  pageHeight={pageData.height}
                  imgWidth={imgSize.width}
                  imgHeight={imgSize.height}
                  isSelected={region.id === selectedRegionId}
                  onSelect={() => setSelectedRegionId(region.id)}
                  onAction={handleRegionAction}
                  onMoveStart={handleMoveStart}
                  onResizeStart={handleResizeStart}
                />
              ))}
          </div>
        </div>
      </div>

      {/* PII Type Picker dialog — shown after drawing a region */}
      {showTypePicker && (
        <div style={styles.overlay}>
          <div style={{ ...styles.dialog, maxWidth: 480 }}>
            <PenTool size={24} style={{ color: "var(--accent-primary)", marginBottom: 8 }} />
            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
              Select PII Type
            </h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
              What type of sensitive data does this region contain?
            </p>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                gap: 6,
                width: "100%",
                marginBottom: 12,
              }}
            >
              {PII_TYPE_OPTIONS.map((t) => (
                <button
                  key={t}
                  className="btn-ghost"
                  style={{
                    padding: "6px 8px",
                    fontSize: 12,
                    fontWeight: 500,
                    borderRadius: 6,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    justifyContent: "flex-start",
                  }}
                  onClick={() => handleTypePickerSelect(t)}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: PII_COLORS[t] || "#888",
                      flexShrink: 0,
                    }}
                  />
                  {t}
                </button>
              ))}
            </div>
            <button
              className="btn-ghost btn-sm"
              onClick={cancelTypePicker}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Region sidebar */}
      <div style={styles.sidebar}>
        <h3 style={styles.sidebarTitle}>Detected PII ({pageRegions.length})</h3>
        <div style={styles.regionList}>
          {pageRegions.map((r) => (
            <div
              key={r.id}
              style={{
                ...styles.regionItem,
                borderLeftColor: PII_COLORS[r.pii_type] || "#888",
                background:
                  r.id === selectedRegionId
                    ? "var(--bg-tertiary)"
                    : "var(--bg-surface)",
              }}
              onClick={() => setSelectedRegionId(r.id)}
            >
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
                <button
                  className="btn-ghost btn-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRegionAction(r.id, "CANCEL");
                  }}
                >
                  Cancel
                </button>
                <button
                  className="btn-danger btn-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRegionAction(r.id, "REMOVE");
                  }}
                >
                  Remove
                </button>
                <button
                  className="btn-tokenize btn-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRegionAction(r.id, "TOKENIZE");
                  }}
                >
                  Tokenize
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
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "8px 16px",
    background: "var(--bg-secondary)",
    borderBottom: "1px solid var(--border-color)",
    flexShrink: 0,
    flexWrap: "wrap",
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
    flex: 1,
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
    padding: 10,
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
    gap: 4,
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
