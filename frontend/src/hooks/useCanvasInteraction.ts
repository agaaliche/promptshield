/**
 * useCanvasInteraction — Mouse-driven canvas interactions: drawing, lasso
 * selection, pan-scrolling, move/resize, image size tracking, snap-to-text,
 * overlap prevention, and the post-draw type-picker flow.
 *
 * Extracted from DocumentViewer to reduce component size.
 */

import { useState, useCallback, useRef, useEffect, type RefObject } from "react";
import {
  addManualRegion,
  updateRegionBBox as updateRegionBBoxApi,
} from "../api";
import { toErrorMessage } from "../errorUtils";
// regionUtils import removed — resolveAllOverlaps unused after refactor
import { useAppStore } from "../store";
import type { BBox, PIIRegion, PIIType } from "../types";
import type { ResizeHandle } from "../components/RegionOverlay";

interface PageData {
  width: number;
  height: number;
  text_blocks?: { bbox: BBox }[];
}

type CursorTool = "pointer" | "lasso" | "draw";

interface UseCanvasInteractionOpts {
  zoom: number;
  activeDocId: string | null;
  activePage: number;
  regions: PIIRegion[];
  pageRegions: PIIRegion[];
  pageData: PageData | undefined;
  selectedRegionIds: string[];
  cursorTool: CursorTool;
  containerRef: RefObject<HTMLDivElement | null>;
  imageContainerRef: RefObject<HTMLDivElement | null>;
  imageRef: RefObject<HTMLImageElement | null>;
  pushUndo: () => void;
  updateRegionBBox: (id: string, bbox: BBox) => void;
  clearSelection: () => void;
  setSelectedRegionIds: (ids: string[]) => void;
  setRegions: (regions: PIIRegion[]) => void;
  setStatusMessage: (msg: string) => void;
  handleRefreshRegion: (id: string, textOnly?: boolean) => Promise<void>;
}

export default function useCanvasInteraction(opts: UseCanvasInteractionOpts) {
  const {
    zoom, activeDocId, activePage, regions, pageRegions, pageData,
    selectedRegionIds, cursorTool,
    containerRef, imageContainerRef, imageRef,
    pushUndo, updateRegionBBox, clearSelection,
    setSelectedRegionIds, setRegions, setStatusMessage,
    handleRefreshRegion,
  } = opts;

  // ── Image tracking state ──
  const [imgSize, setImgSize] = useState({ width: 0, height: 0 });
  const [imgLoaded, setImgLoaded] = useState(false);

  // ── Draw state ──
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawEnd, setDrawEnd] = useState<{ x: number; y: number } | null>(null);
  const [showTypePicker, setShowTypePicker] = useState(false);
  const [drawnBBox, setDrawnBBox] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  // ── Lasso state ──
  const [isLassoing, setIsLassoing] = useState(false);
  const [lassoStart, setLassoStart] = useState<{ x: number; y: number } | null>(null);
  const [lassoEnd, setLassoEnd] = useState<{ x: number; y: number } | null>(null);

  // ── Pan state ──
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<{ x: number; y: number; scrollLeft: number; scrollTop: number } | null>(null);

  // ── Move / resize state ──
  const interactionRef = useRef<{
    mode: "moving" | "resizing";
    regionId: string;
    handle?: ResizeHandle;
    startX: number;
    startY: number;
    origBBox: BBox;
    hasMoved: boolean;
  } | null>(null);
  const [isInteracting, setIsInteracting] = useState(false);
  const autoRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Mutable mirrors for event handlers
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const imgSizeRef = useRef(imgSize);
  imgSizeRef.current = imgSize;

  // ── Image load handler ──
  const onImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    setImgSize({ width: img.offsetWidth, height: img.offsetHeight });
    setImgLoaded(true);
  }, []);

  // ── Track displayed image size on window resize ──
  useEffect(() => {
    const updateImageSize = () => {
      const img = imageRef.current;
      if (img && img.offsetWidth > 0 && img.offsetHeight > 0) {
        setImgSize((prev) => {
          if (prev.width === img.offsetWidth && prev.height === img.offsetHeight) return prev;
          return { width: img.offsetWidth, height: img.offsetHeight };
        });
      }
    };

    window.addEventListener("resize", updateImageSize);

    const img = imageRef.current;
    const container = imageContainerRef.current;
    let observer: ResizeObserver | null = null;
    if (window.ResizeObserver) {
      observer = new ResizeObserver(updateImageSize);
      if (img) observer.observe(img);
      if (container) observer.observe(container);
    }

    return () => {
      window.removeEventListener("resize", updateImageSize);
      if (observer) observer.disconnect();
    };
  }, [imgLoaded, imageRef, imageContainerRef]);

  // ── Cleanup auto-refresh timer on unmount ──
  useEffect(() => {
    return () => {
      if (autoRefreshTimerRef.current) clearTimeout(autoRefreshTimerRef.current);
    };
  }, []);

  // ── Coordinate conversion ──
  const getPointerPosOnImage = useCallback(
    (e: React.MouseEvent) => {
      if (!imageContainerRef.current) return null;
      const rect = imageContainerRef.current.getBoundingClientRect();
      return {
        x: (e.clientX - rect.left) / zoom,
        y: (e.clientY - rect.top) / zoom,
      };
    },
    [zoom, imageContainerRef],
  );

  // ── Snap-to-text helper ──
  const snapToText = useCallback(
    (nb: BBox, edges: { left: boolean; right: boolean; top: boolean; bottom: boolean }): BBox => {
      if (!pageData) return nb;
      const blocks = pageData.text_blocks;
      if (!blocks || blocks.length === 0) return nb;

      const { width: iw, height: ih } = imgSizeRef.current;
      const PAD_PX = 2;
      const padX = iw > 0 ? (PAD_PX * pageData.width) / iw : 1;
      const padY = ih > 0 ? (PAD_PX * pageData.height) / ih : 1;
      const SNAP_PX = 8;
      const snapDistX = iw > 0 ? (SNAP_PX * pageData.width) / iw : 4;
      const snapDistY = ih > 0 ? (SNAP_PX * pageData.height) / ih : 4;

      const relevantBlocks = blocks.filter(
        (b) =>
          b.bbox.x1 > nb.x0 - snapDistX &&
          b.bbox.x0 < nb.x1 + snapDistX &&
          b.bbox.y1 > nb.y0 - snapDistY &&
          b.bbox.y0 < nb.y1 + snapDistY,
      );

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

  // ── Prevent overlap helper ──
  const preventOverlap = useCallback(
    (proposed: BBox, movingId: string): BBox => {
      const others = regions.filter(
        (r) => r.id !== movingId && r.page_number === activePage && r.action !== "CANCEL",
      );
      let box = { ...proposed };

      for (const other of others) {
        const ob = other.bbox;
        if (box.x0 >= ob.x1 || box.x1 <= ob.x0 || box.y0 >= ob.y1 || box.y1 <= ob.y0) continue;

        const overlapX = Math.min(box.x1, ob.x1) - Math.max(box.x0, ob.x0);
        const overlapY = Math.min(box.y1, ob.y1) - Math.max(box.y0, ob.y0);
        const cx = (box.x0 + box.x1) / 2;
        const cy = (box.y0 + box.y1) / 2;
        const ocx = (ob.x0 + ob.x1) / 2;
        const ocy = (ob.y0 + ob.y1) / 2;

        if (overlapY <= overlapX) {
          const shift = cy < ocy ? -overlapY : overlapY;
          box = { ...box, y0: box.y0 + shift, y1: box.y1 + shift };
        } else {
          const shift = cx < ocx ? -overlapX : overlapX;
          box = { ...box, x0: box.x0 + shift, x1: box.x1 + shift };
        }
      }
      return box;
    },
    [regions, activePage],
  );

  // ── Canvas mouse handlers ──
  const handleCanvasMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (cursorTool === "draw") {
        const pos = getPointerPosOnImage(e);
        if (!pos) return;
        e.preventDefault();
        setIsDrawing(true);
        setDrawStart(pos);
        setDrawEnd(pos);
        return;
      }
      if (cursorTool === "lasso") {
        const pos = getPointerPosOnImage(e);
        if (!pos) return;
        e.preventDefault();
        setIsLassoing(true);
        setLassoStart(pos);
        setLassoEnd(pos);
        return;
      }
      // Pointer mode
      if (e.ctrlKey || e.metaKey) {
        const pos = getPointerPosOnImage(e);
        if (!pos) return;
        e.preventDefault();
        setIsLassoing(true);
        setLassoStart(pos);
        setLassoEnd(pos);
      } else {
        e.preventDefault();
        clearSelection();
        const el = containerRef.current;
        if (!el) return;
        setIsPanning(true);
        panStartRef.current = { x: e.clientX, y: e.clientY, scrollLeft: el.scrollLeft, scrollTop: el.scrollTop };
      }
    },
    [cursorTool, getPointerPosOnImage, clearSelection, containerRef],
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
    [isDrawing, cursorTool, isLassoing, isPanning, getPointerPosOnImage, containerRef],
  );

  const handleCanvasMouseUp = useCallback(
    (e: React.MouseEvent) => {
      if (isPanning) {
        setIsPanning(false);
        panStartRef.current = null;
        return;
      }

      if (isLassoing && lassoStart && lassoEnd && pageData) {
        setIsLassoing(false);
        const w = Math.abs(lassoEnd.x - lassoStart.x);
        const h = Math.abs(lassoEnd.y - lassoStart.y);
        if (w > 5 || h > 5) {
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

      if (!isDrawing || !drawStart || !drawEnd || !pageData) return;
      setIsDrawing(false);

      const w = Math.abs(drawEnd.x - drawStart.x);
      const h = Math.abs(drawEnd.y - drawStart.y);
      if (w < 10 || h < 10) {
        setDrawStart(null);
        setDrawEnd(null);
        return;
      }

      const sx = pageData.width / imgSize.width;
      const sy = pageData.height / imgSize.height;

      let box: BBox = {
        x0: Math.min(drawStart.x, drawEnd.x) * sx,
        y0: Math.min(drawStart.y, drawEnd.y) * sy,
        x1: Math.max(drawStart.x, drawEnd.x) * sx,
        y1: Math.max(drawStart.y, drawEnd.y) * sy,
      };

      box = snapToText(box, { left: true, right: true, top: true, bottom: true });

      setDrawnBBox(box);
      setShowTypePicker(true);
      setDrawStart(null);
      setDrawEnd(null);
    },
    [isPanning, isDrawing, isLassoing, lassoStart, lassoEnd, drawStart, drawEnd, pageData, imgSize, pageRegions, selectedRegionIds, setSelectedRegionIds, snapToText],
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

  // ── Global mouse tracking for move/resize ──
  useEffect(() => {
    if (!isInteracting) return;

    const handleMouseMove = (e: MouseEvent) => {
      const ix = interactionRef.current;
      if (!ix || !imageContainerRef.current || !pageData) return;

      const rect = imageContainerRef.current.getBoundingClientRect();
      const imgX = (e.clientX - rect.left) / zoomRef.current;
      const imgY = (e.clientY - rect.top) / zoomRef.current;

      if (!ix.hasMoved) {
        const dist = Math.abs(imgX - ix.startX) + Math.abs(imgY - ix.startY);
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
        const MIN = 5;
        if (nb.x1 - nb.x0 < MIN) {
          if (h.includes("w")) nb.x0 = nb.x1 - MIN;
          else nb.x1 = nb.x0 + MIN;
        }
        if (nb.y1 - nb.y0 < MIN) {
          if (h.includes("n")) nb.y0 = nb.y1 - MIN;
          else nb.y1 = nb.y0 + MIN;
        }
        nb.x0 = Math.max(0, nb.x0);
        nb.y0 = Math.max(0, nb.y0);
        nb.x1 = Math.min(pageData.width, nb.x1);
        nb.y1 = Math.min(pageData.height, nb.y1);

        nb = snapToText(nb, {
          left: h.includes("w"),
          right: h.includes("e"),
          top: h.includes("n"),
          bottom: h.includes("s"),
        });
      }

      nb = preventOverlap(nb, ix.regionId);
      updateRegionBBox(ix.regionId, nb);
    };

    const handleMouseUp = async () => {
      const ix = interactionRef.current;
      interactionRef.current = null;
      setIsInteracting(false);
      if (!ix || !ix.hasMoved || !activeDocId) return;

      const latest = useAppStore.getState().regions.find((r) => r.id === ix.regionId);
      if (latest) {
        try {
          await updateRegionBBoxApi(activeDocId, ix.regionId, latest.bbox);
        } catch (err) {
          console.error("Failed to persist bbox update:", err);
        }
      }

      if (autoRefreshTimerRef.current) clearTimeout(autoRefreshTimerRef.current);
      autoRefreshTimerRef.current = setTimeout(() => {
        handleRefreshRegion(ix.regionId, true);
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

  // ── Type picker callbacks ──
  const cancelTypePicker = useCallback(() => {
    setShowTypePicker(false);
    setDrawnBBox(null);
  }, []);

  const handleTypePickerSelect = useCallback(
    async (piiType: PIIType) => {
      if (!activeDocId || !drawnBBox) return;
      setShowTypePicker(false);

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
        const fullRegion: PIIRegion = {
          id: resp.region_id,
          page_number: activePage,
          bbox: resp.bbox || adjustedBBox,
          text: resp.text || "[manual selection]",
          pii_type: (resp.pii_type as PIIType) || piiType,
          confidence: 1.0,
          source: "MANUAL",
          char_start: 0,
          char_end: 0,
          action: "PENDING",
        };
        pushUndo();
        const siblings: PIIRegion[] = resp.new_regions || [];
        setRegions([...regions, fullRegion, ...siblings]);

        if (siblings.length > 0) {
          setSelectedRegionIds(resp.all_ids || [fullRegion.id]);
          setStatusMessage(
            `Added ${piiType} region — found ${1 + siblings.length} occurrences of "${(resp.text || "").slice(0, 30)}"`,
          );
        } else {
          setStatusMessage(`Added manual ${piiType} region`);
        }
      } catch (e: unknown) {
        setStatusMessage(`Failed to add region: ${toErrorMessage(e)}`);
      }
      setDrawnBBox(null);
    },
    [activeDocId, activePage, drawnBBox, regions, setRegions, setSelectedRegionIds, setStatusMessage, pushUndo, preventOverlap],
  );

  return {
    imgSize,
    imgLoaded,
    isDrawing,
    drawStart,
    drawEnd,
    isLassoing,
    lassoStart,
    lassoEnd,
    isPanning,
    isInteracting,
    showTypePicker,
    drawnBBox,
    handleCanvasMouseDown,
    handleCanvasMouseMove,
    handleCanvasMouseUp,
    handleMoveStart,
    handleResizeStart,
    onImageLoad,
    handleTypePickerSelect,
    cancelTypePicker,
    setShowTypePicker,
    setDrawnBBox,
    setIsPanning,
    panStartRef,
  };
}
