/** Document viewer — renders page bitmap with PII highlight overlays. */

import { useEffect, useRef, useMemo, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ZoomIn,
  ZoomOut,
  Shield,
  ScanSearch,
  Loader2,
  Upload,
  LayoutGrid,
  X,
} from "../icons";
import { useDocumentStore, useRegionStore, useUIStore, useDocLoadingStore, useSidebarStore, useDetectionStore, useUploadStore } from "../store";
import {
  getPageBitmapUrl,
  batchRegionAction,
  batchDeleteRegions,
} from "../api";
import { CURSOR_CROSSHAIR } from "../cursors";
import type { PIIType } from "../types";
import RegionOverlay from "./RegionOverlay";
import ExportDialog from "./ExportDialog";
import UploadProgressDialog from "./UploadProgressDialog";
import DetectionProgressDialog from "./DetectionProgressDialog";
import PIITypePicker from "./PIITypePicker";
import RegionSidebar from "./RegionSidebar";
import PageNavigator from "./PageNavigator";
import AutodetectPanel from "./AutodetectPanel";
import DeleteSimilarDialog from "./DeleteSimilarDialog";

import CursorToolToolbar from "./CursorToolToolbar";
import MultiSelectToolbar from "./MultiSelectToolbar";
import useRegionActions from "../hooks/useRegionActions";
import useDocumentExport from "../hooks/useDocumentExport";
import useCanvasInteraction from "../hooks/useCanvasInteraction";
import useViewerToolbars from "../hooks/useViewerToolbars";
import useKeyboardShortcuts from "../hooks/useKeyboardShortcuts";
import useLabelConfig from "../hooks/useLabelConfig";


export default function DocumentViewer() {
  const { t } = useTranslation();
  const { activeDocId, documents, activePage, setActivePage } = useDocumentStore();
  const { regions, updateRegionAction, removeRegion, setRegions, updateRegionBBox, updateRegion, selectedRegionIds, setSelectedRegionIds, toggleSelectedRegionId, clearSelection, pushUndo, undo, redo, canUndo, canRedo } = useRegionStore();
  const { zoom, setZoom, isProcessing, setIsProcessing, setStatusMessage, setDrawMode } = useUIStore();
  const { docLoading, docLoadingMessage, docDetecting, uploadProgressId, uploadProgressDocId, uploadProgressDocName, uploadProgressPhase } = useDocLoadingStore();
  const { rightSidebarWidth, setRightSidebarWidth, isSidebarDragging, leftSidebarWidth } = useSidebarStore();
  const { llmStatus } = useDetectionStore();
  const { setShowUploadDialog } = useUploadStore();

  const doc = documents.find((d) => d.doc_id === activeDocId) ?? null;
  const pageCount = doc?.page_count ?? 0;

  // ── UI chrome (toolbars, sidebar, cursor tool) ──
  const {
    cursorTool, setCursorTool, prevCursorToolRef,
    cursorToolbarRef, cursorToolbarPos, isDraggingCursorToolbar, startCursorToolbarDrag,
    cursorToolbarExpanded, setCursorToolbarExpanded,
    multiSelectToolbarRef, multiSelectToolbarPos, isDraggingMultiSelectToolbar, startMultiSelectToolbarDrag,
    multiSelectToolbarExpanded, setMultiSelectToolbarExpanded,
    showMultiSelectEdit, setShowMultiSelectEdit,
    multiSelectEditLabel, setMultiSelectEditLabel,
    sidebarRef, topToolbarRef, contentAreaRef,
    sidebarCollapsed, setSidebarCollapsed,
    sidebarTypeFilter, setSidebarTypeFilter,
    pageNavCollapsed, setPageNavCollapsed,
    rightInset,
  } = useViewerToolbars({ setDrawMode, rightSidebarWidth, leftSidebarWidth, pageCount });

  // ── DOM refs for canvas ──
  const containerRef = useRef<HTMLDivElement>(null);
  const imageContainerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  // ── Fixed document width — captured once on image load so sidebar resizes don't reflow ──
  const [baseWidth, setBaseWidth] = useState(0);
  const baseWidthRef = useRef(0);

  const isImageFile = doc?.mime_type?.startsWith("image/") || false;
  const bitmapUrl = activeDocId ? getPageBitmapUrl(activeDocId, activePage) : "";
  const pageData = doc?.pages?.[activePage - 1];

  const pageRegions = useMemo(
    () => regions.filter((r) => r.page_number === activePage),
    [regions, activePage],
  );

  const pendingCount = regions.filter((r) => r.action === "PENDING").length;
  const removeCount = regions.filter((r) => r.action === "REMOVE").length;
  const tokenizeCount = regions.filter((r) => r.action === "TOKENIZE").length;

  // ── Region CRUD actions ──
  const {
    copiedRegions, setCopiedRegions,
    showAutodetect, setShowAutodetect,
    redetecting,
    handleRegionAction, handleRefreshRegion, handleClearRegion,
    handleHighlightAll, handleUpdateLabel, handleUpdateText,
    handlePasteRegions,
    handleAutodetect, handleResetAll, handleResetPage,
    pendingDeleteRegionId, handleConfirmDelete, handleCancelDelete,
  } = useRegionActions({
    activeDocId: activeDocId ?? null,
    activePage,
    regions,
    pushUndo,
    updateRegionAction,
    removeRegion,
    setRegions,
    updateRegion,
    setIsProcessing,
    setStatusMessage,
    setSelectedRegionIds,
  });

  // ── Export / anonymize ──
  const {
    showExportDialog, setShowExportDialog,
    handleAnonymize,
  } = useDocumentExport({
    activeDocId: activeDocId ?? null,
    regions,
    setIsProcessing,
    setStatusMessage,
  });

  // ── Canvas interactions (draw, lasso, pan, move, resize) ──
  const {
    imgSize, imgLoaded,
    isDrawing, drawStart, drawEnd,
    isLassoing, lassoStart, lassoEnd,
    isPanning,
    showTypePicker,
    handleCanvasMouseDown, handleCanvasMouseMove, handleCanvasMouseUp,
    handleMoveStart, handleResizeStart,
    onImageLoad,
    handleTypePickerSelect, cancelTypePicker,
    setIsPanning, panStartRef,
  } = useCanvasInteraction({
    zoom,
    activeDocId: activeDocId ?? null,
    activePage,
    regions,
    pageRegions,
    pageData,
    selectedRegionIds,
    cursorTool,
    containerRef,
    imageContainerRef,
    imageRef,
    pushUndo,
    updateRegionBBox,
    clearSelection,
    setSelectedRegionIds,
    setRegions,
    setStatusMessage,
    handleRefreshRegion,
  });

  // ── Label config ──
  const {
    labelConfig, visibleLabels, frequentLabels, otherLabels, usedLabels,
    updateLabelConfig, typePickerEditMode, setTypePickerEditMode,
    typePickerNewLabel, setTypePickerNewLabel,
  } = useLabelConfig(regions);

  // ── Auto-select first region on page change ──
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

  // ── Keyboard shortcuts ──
  useKeyboardShortcuts({
    activePage, pageCount, zoom, regions, pageRegions, selectedRegionIds,
    copiedRegions, activeDocId: activeDocId ?? null, cursorTool, showTypePicker,
    canUndo, canRedo, showAutodetect, setShowAutodetect, setActivePage, setZoom,
    setSelectedRegionIds, clearSelection, setCursorTool, prevCursorToolRef,
    cancelTypePicker, handleRegionAction, undo, redo, pushUndo, removeRegion,
    setCopiedRegions, setStatusMessage, handlePasteRegions, batchDeleteRegions,
    handleClearRegion,
  });

  // ── Reset base width when switching documents ──
  useEffect(() => {
    baseWidthRef.current = 0;
    setBaseWidth(0);
  }, [activeDocId]);

  // ── Wrap onImageLoad to capture fixed base width ──
  const handleImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    onImageLoad(e);
    if (baseWidthRef.current === 0) {
      const w = e.currentTarget.offsetWidth;
      if (w > 0) {
        baseWidthRef.current = w;
        setBaseWidth(w);
      }
    }
  }, [onImageLoad]);

  // ── Responsive sidebar: shrink right sidebar first when window gets narrow ──
  const RIGHT_SIDEBAR_MIN_WIDTH = 200;
  const TOOLBAR_MIN_CONTENT_WIDTH = 400; // Minimum width for toolbar buttons + page nav + zoom
  const preferredSidebarWidthRef = useRef(rightSidebarWidth);
  const currentSidebarWidthRef = useRef(rightSidebarWidth);
  const wasDraggingSidebarRef = useRef(false);

  // Keep ref in sync with actual width
  useEffect(() => {
    currentSidebarWidthRef.current = rightSidebarWidth;
  }, [rightSidebarWidth]);

  // Track preferred width when user manually resizes (drag ends).
  // Only capture on drag→no-drag transition so auto-shrink from the
  // responsive handler doesn't overwrite the user's preferred width.
  useEffect(() => {
    if (isSidebarDragging) {
      wasDraggingSidebarRef.current = true;
    } else if (wasDraggingSidebarRef.current) {
      wasDraggingSidebarRef.current = false;
      preferredSidebarWidthRef.current = rightSidebarWidth;
    }
  }, [rightSidebarWidth, isSidebarDragging]);

  useEffect(() => {
    const handleResize = () => {
      if (sidebarCollapsed || isSidebarDragging) return; // Don't adjust when collapsed or user is dragging
      
      const windowWidth = window.innerWidth;
      const leftSpace = leftSidebarWidth;
      const availableForToolbarAndSidebar = windowWidth - leftSpace;
      const neededForToolbar = TOOLBAR_MIN_CONTENT_WIDTH;
      const maxSidebarWidth = availableForToolbarAndSidebar - neededForToolbar;
      const currentWidth = currentSidebarWidthRef.current;
      
      // If there's plenty of space, restore to preferred width
      if (maxSidebarWidth >= preferredSidebarWidthRef.current) {
        if (currentWidth < preferredSidebarWidthRef.current) {
          setRightSidebarWidth(preferredSidebarWidthRef.current);
        }
        return;
      }
      
      // If space is limited, shrink sidebar to max allowed (but not below minimum)
      if (maxSidebarWidth >= RIGHT_SIDEBAR_MIN_WIDTH) {
        // Always set to maxSidebarWidth when constrained
        if (currentWidth !== maxSidebarWidth) {
          setRightSidebarWidth(maxSidebarWidth);
        }
      } else {
        // At minimum sidebar width, let toolbar compress
        if (currentWidth > RIGHT_SIDEBAR_MIN_WIDTH) {
          setRightSidebarWidth(RIGHT_SIDEBAR_MIN_WIDTH);
        }
      }
    };

    window.addEventListener('resize', handleResize);
    // Only run initial check if not dragging
    if (!isSidebarDragging) {
      handleResize();
    }
    return () => window.removeEventListener('resize', handleResize);
  }, [sidebarCollapsed, leftSidebarWidth, isSidebarDragging, setRightSidebarWidth]);

  if (!doc) {
    // When uploading the very first file, show the progress dialog even though
    // no document object exists yet.
    const showUploadProgress = uploadProgressPhase === "uploading";
    if (showUploadProgress) {
      return (
        <div style={styles.wrapper}>
          <UploadProgressDialog
            uploadProgressId={uploadProgressId}
            docId={uploadProgressDocId}
            docName={uploadProgressDocName || "Document"}
            phase={uploadProgressPhase}
            visible
          />
        </div>
      );
    }
    return <div style={styles.empty}>{t("viewer.noDocumentLoaded")}</div>;
  }

  // Block the viewer while loading OR detecting
  const isDocLoading = docLoading || docDetecting || !doc.pages;
  const showUploadProgressDialog = uploadProgressPhase === "uploading";

  if (isDocLoading) {
    if (!showUploadProgressDialog) {
      return (
        <div style={styles.wrapper}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", width: "100%" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
              <Loader2 size={36} color="var(--accent-primary)" style={{ animation: "spin 1s linear infinite" }} />
              <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>
                {docLoadingMessage || t("viewer.loadingDocument")}
              </div>
            </div>
          </div>
        </div>
      );
    }
  }

  return (
    <div style={styles.wrapper}>

      {/* Upload progress overlay – shown immediately on file upload */}
      {showUploadProgressDialog && (
        <UploadProgressDialog
          uploadProgressId={uploadProgressId}
          docId={uploadProgressDocId}
          docName={uploadProgressDocName || doc.original_filename}
          phase={uploadProgressPhase}
          visible
        />
      )}

      {/* Re-detection progress overlay */}
      {redetecting && activeDocId && (
        <DetectionProgressDialog
          docId={activeDocId}
          docName={doc.original_filename}
          visible
        />
      )}

      {/* Toolbar */}
      <div ref={topToolbarRef} style={{
        ...styles.toolbar,
        paddingRight: 16 + (sidebarCollapsed ? 60 : rightSidebarWidth),
      }}>
        <button
          className="btn-warning"
          onClick={() => setShowUploadDialog(true)}
          disabled={isProcessing}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <Upload size={14} />
          {t("common.upload")}
        </button>
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
          {t("common.detect")}
        </button>

        {showAutodetect && (
            <AutodetectPanel
              isProcessing={isProcessing}
              activePage={activePage}
              llmStatus={llmStatus}
              rightOffset={sidebarCollapsed ? 60 : rightSidebarWidth}
              leftOffset={leftSidebarWidth}
              pageNavWidth={pageCount > 1 && !pageNavCollapsed ? 148 : 0}
              regions={regions}
              onDetect={(opts) => {
                setShowAutodetect(false);
                handleAutodetect(opts);
              }}
              onReset={() => {
                setShowAutodetect(false);
                handleResetAll();
              }}
              onResetPage={(page) => {
                setShowAutodetect(false);
                handleResetPage(page);
              }}
              onClose={() => setShowAutodetect(false)}
            />
        )}
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
          {t("common.export")}
        </button>

        {/* Center section: Zoom controls */}
        <div style={{
          flex: 1,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minWidth: 0,
          overflow: "hidden",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button className="btn-ghost btn-sm" onClick={() => setZoom(Math.max(0.1, zoom - 0.1))} title={t("viewer.zoomOut")} style={{ padding: "4px 6px", color: "var(--text-secondary)" }}>
              <ZoomOut size={16} />
            </button>
            <span
              style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", minWidth: 40, textAlign: "center", cursor: "pointer" }}
              onClick={() => setZoom(1)}
              title={t("viewer.resetZoom")}
            >
              {Math.round(zoom * 100)}%
            </span>
            <button className="btn-ghost btn-sm" onClick={() => setZoom(zoom + 0.1)} title={t("viewer.zoomIn")} style={{ padding: "4px 6px", color: "var(--text-secondary)" }}>
              <ZoomIn size={16} />
            </button>
          </div>
        </div>

        {/* Right section: Page navigation */}
        {pageCount > 1 && (
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button className="btn-ghost btn-sm" onClick={() => setActivePage(1)} disabled={activePage <= 1} title={t("viewer.firstPage")} style={{ padding: 6, color: "var(--text-secondary)", background: "var(--bg-tertiary)", borderRadius: "50%", width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <ChevronsLeft size={16} />
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setActivePage(Math.max(1, activePage - 1))} disabled={activePage <= 1} title={t("viewer.previousPage")} style={{ padding: 6, color: "var(--text-secondary)", background: "var(--bg-tertiary)", borderRadius: "50%", width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <ChevronLeft size={16} />
            </button>
            <input
              type="number"
              className="no-spinner"
              min={1}
              max={pageCount}
              value={activePage}
              onChange={(e) => {
                const val = parseInt(e.target.value, 10);
                if (!isNaN(val) && val >= 1 && val <= pageCount) setActivePage(val);
              }}
              onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
              style={{
                width: 36, padding: "3px 4px", fontSize: 13, fontWeight: 600, textAlign: "center",
                background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)",
                borderRadius: 4, color: "var(--text-primary)", outline: "none",
              }}
              title={t("viewer.goToPage")}
            />
            <button className="btn-ghost btn-sm" onClick={() => setActivePage(Math.min(pageCount, activePage + 1))} disabled={activePage >= pageCount} title={t("viewer.nextPage")} style={{ padding: 6, color: "var(--text-secondary)", background: "var(--bg-tertiary)", borderRadius: "50%", width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <ChevronRight size={16} />
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setActivePage(pageCount)} disabled={activePage >= pageCount} title={t("viewer.lastPage")} style={{ padding: 6, color: "var(--text-secondary)", background: "var(--bg-tertiary)", borderRadius: "50%", width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <ChevronsRight size={16} />
            </button>
            <div style={{ padding: "4px 10px", background: "var(--bg-tertiary)", borderRadius: 14, fontSize: 12, color: "var(--text-secondary)", fontWeight: 500, marginLeft: 20 }}>
              {t("viewer.nPages", { count: pageCount })}
            </div>
            <button
              className="btn-ghost btn-sm"
              onClick={() => setPageNavCollapsed(!pageNavCollapsed)}
              title={pageNavCollapsed ? t("viewer.showThumbnails") : t("viewer.hideThumbnails")}
              style={{
                marginLeft: 4,
                padding: 0,
                width: 28,
                height: 28,
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: pageNavCollapsed ? "var(--text-secondary)" : "var(--text-primary)",
                background: pageNavCollapsed ? "var(--bg-tertiary)" : "rgba(255,255,255,0.12)",
              }}
            >
              {pageNavCollapsed ? <LayoutGrid size={15} /> : <X size={15} />}
            </button>
          </div>
        )}
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

      {/* Multi-select toolbar */}
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
          multiSelectEditLabel={multiSelectEditLabel as PIIType}
          setMultiSelectEditLabel={setMultiSelectEditLabel as (v: PIIType) => void}
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
      <ExportDialog
        open={showExportDialog}
        onClose={() => setShowExportDialog(false)}
      />

      {/* Delete-similar confirmation dialog */}
      {pendingDeleteRegionId && (() => {
        const target = regions.find((r) => r.id === pendingDeleteRegionId);
        if (!target) return null;
        const normText = target.text.trim().toLowerCase();
        const occurrenceCount = regions.filter(
          (r) => r.text.trim().toLowerCase() === normText,
        ).length;
        return (
          <DeleteSimilarDialog
            regionText={target.text}
            occurrenceCount={occurrenceCount}
            onDeleteOne={(neverAsk) => handleConfirmDelete(false, neverAsk)}
            onDeleteAll={(neverAsk) => handleConfirmDelete(true, neverAsk)}
            onCancel={handleCancelDelete}
          />
        );
      })()}

      {/* Canvas area */}
      <div ref={containerRef} style={{
        ...styles.canvasArea,
        paddingRight: rightInset,
        transition: isSidebarDragging ? 'none' : 'padding-right 0.2s ease',
      }}>
        {/* Scroll sizer — explicit zoomed dimensions for correct scroll range */}
        <div style={{
          ...(baseWidth > 0
            ? { width: Math.ceil(imgSize.width * zoom), height: Math.ceil(imgSize.height * zoom), overflow: 'hidden' as const }
            : {}),
          margin: '0 auto',
        }}>
        <div
          style={{
            ...styles.pageContainer,
            transform: `scale(${zoom})`,
            transformOrigin: "top left",
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
                ...(baseWidth > 0 ? { width: baseWidth } : { maxWidth: '100%' }),
                cursor: cursorTool === "draw" ? CURSOR_CROSSHAIR
                  : cursorTool === "lasso" ? 'crosshair'
                  : isPanning ? 'grabbing' : 'default',
              }}
              onLoad={handleImageLoad}
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
                    rightInset={rightInset}
                    leftSidebarWidth={leftSidebarWidth}
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
              const linkedGroups = new Set(selRegions.map((r) => r.linked_group).filter(Boolean));
              let label: string;
              if (linkedGroups.size === 1 && selRegions.every((r) => r.linked_group)) {
                const type = selRegions[0].pii_type;
                const text = selRegions[0].text.replace(/\n/g, " ");
                label = `${type}: ${text}`;
              } else if (types.size === 1) {
                label = t("viewer.regionsSameType", { count: selRegions.length, type: [...types][0] });
              } else {
                label = t("viewer.regionsMultiType", { count: selRegions.length });
              }
              return (
                <>
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
        </div>{/* end scroll sizer */}

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

      {!pageNavCollapsed && pageCount > 1 && (
        <PageNavigator
          docId={activeDocId}
          pageCount={pageCount}
          activePage={activePage}
          onPageSelect={setActivePage}
          rightOffset={sidebarCollapsed ? 60 : rightSidebarWidth}
          collapsed={false}
          onCollapsedChange={setPageNavCollapsed}
          regions={regions}
          sidebarWidth={rightSidebarWidth}
          onSidebarWidthChange={setRightSidebarWidth}
        />
      )}
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
          if (region.page_number !== activePage) {
            skipAutoSelectRef.current = true;
            setActivePage(region.page_number);
          }
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
        hideResizeHandle={pageCount > 1 && !pageNavCollapsed}
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
    paddingTop: 20,
    paddingBottom: 20,
  },
  pageContainer: {
    transition: "transform 0.15s ease",
  },
  pageImage: {
    display: "block",
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
