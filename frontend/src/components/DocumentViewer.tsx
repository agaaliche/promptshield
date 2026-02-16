/** Document viewer — renders page bitmap with PII highlight overlays. */

import { useEffect, useRef, useMemo } from "react";
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
} from "lucide-react";
import { useDocumentStore, useRegionStore, useUIStore, useVaultStore, useDocLoadingStore, useSidebarStore, useDetectionStore } from "../store";
import {
  getPageBitmapUrl,
  batchRegionAction,
  batchDeleteRegions,
} from "../api";
import { CURSOR_CROSSHAIR } from "../cursors";
import type { PIIType } from "../types";
import RegionOverlay from "./RegionOverlay";
import ExportDialog from "./ExportDialog";
import DetectionProgressDialog from "./DetectionProgressDialog";
import PIITypePicker from "./PIITypePicker";
import RegionSidebar from "./RegionSidebar";
import PageNavigator from "./PageNavigator";
import AutodetectPanel from "./AutodetectPanel";
import VaultUnlockDialog from "./VaultUnlockDialog";
import CursorToolToolbar from "./CursorToolToolbar";
import MultiSelectToolbar from "./MultiSelectToolbar";
import UserMenu from "./UserMenu";
import useRegionActions from "../hooks/useRegionActions";
import useDocumentExport from "../hooks/useDocumentExport";
import useCanvasInteraction from "../hooks/useCanvasInteraction";
import useViewerToolbars from "../hooks/useViewerToolbars";
import useKeyboardShortcuts from "../hooks/useKeyboardShortcuts";
import useLabelConfig from "../hooks/useLabelConfig";

export default function DocumentViewer() {
  const { activeDocId, documents, activePage, setActivePage } = useDocumentStore();
  const { regions, updateRegionAction, removeRegion, setRegions, updateRegionBBox, updateRegion, selectedRegionIds, setSelectedRegionIds, toggleSelectedRegionId, clearSelection, pushUndo, undo, redo, canUndo, canRedo } = useRegionStore();
  const { zoom, setZoom, isProcessing, setIsProcessing, setStatusMessage, setDrawMode } = useUIStore();
  const { vaultUnlocked, setVaultUnlocked } = useVaultStore();
  const { docLoading, docLoadingMessage, docDetecting } = useDocLoadingStore();
  const { rightSidebarWidth, setRightSidebarWidth, isSidebarDragging, leftSidebarWidth } = useSidebarStore();
  const { llmStatus } = useDetectionStore();

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
  } = useViewerToolbars({ setDrawMode });

  // ── DOM refs for canvas ──
  const containerRef = useRef<HTMLDivElement>(null);
  const imageContainerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  const doc = documents.find((d) => d.doc_id === activeDocId) ?? null;
  const pageCount = doc?.page_count ?? 0;
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
    showVaultPrompt, setShowVaultPrompt,
    vaultPass, setVaultPass,
    vaultError, setVaultError,
    showExportDialog, setShowExportDialog,
    handleVaultUnlockAndAnonymize,
  } = useDocumentExport({
    activeDocId: activeDocId ?? null,
    regions,
    vaultUnlocked,
    setVaultUnlocked,
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
  });

  if (!doc) return <div style={styles.empty}>No document loaded</div>;

  // Block the viewer while loading OR detecting
  const isDocLoading = docLoading || docDetecting || !doc.pages;

  if (isDocLoading) {
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

    return (
      <div style={styles.wrapper}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", width: "100%" }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
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
              rightOffset={sidebarCollapsed ? 60 : rightSidebarWidth}
              leftOffset={leftSidebarWidth}
              pageNavWidth={pageCount > 1 ? (pageNavCollapsed ? 28 : 148) : 0}
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
          Export secure file
        </button>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Page navigation + Zoom — centered */}
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
              <button className="btn-ghost btn-sm" onClick={() => setActivePage(1)} disabled={activePage <= 1} title="First page" style={{ padding: "4px 6px", color: "var(--text-secondary)" }}>
                <ChevronsLeft size={16} />
              </button>
              <button className="btn-ghost btn-sm" onClick={() => setActivePage(Math.max(1, activePage - 1))} disabled={activePage <= 1} title="Previous page" style={{ padding: "4px 6px", color: "var(--text-secondary)" }}>
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
                    if (!isNaN(val) && val >= 1 && val <= pageCount) setActivePage(val);
                  }}
                  onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
                  style={{
                    width: 36, padding: "3px 4px", fontSize: 13, fontWeight: 600, textAlign: "center",
                    background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)",
                    borderRadius: 4, color: "var(--text-primary)", outline: "none",
                    MozAppearance: "textfield",
                  }}
                  title="Go to page"
                />
                <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>/</span>
                <span style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500 }}>{pageCount}</span>
              </div>
              <button className="btn-ghost btn-sm" onClick={() => setActivePage(Math.min(pageCount, activePage + 1))} disabled={activePage >= pageCount} title="Next page" style={{ padding: "4px 6px", color: "var(--text-secondary)" }}>
                <ChevronRight size={16} />
              </button>
              <button className="btn-ghost btn-sm" onClick={() => setActivePage(pageCount)} disabled={activePage >= pageCount} title="Last page" style={{ padding: "4px 6px", color: "var(--text-secondary)" }}>
                <ChevronsRight size={16} />
              </button>
            </div>
          )}

          {/* Zoom controls */}
          <div style={{ display: "flex", alignItems: "center", gap: 4, marginLeft: pageCount > 1 ? 25 : 0 }}>
            <button className="btn-ghost btn-sm" onClick={() => setZoom(Math.max(0.1, zoom - 0.1))} title="Zoom out" style={{ padding: "4px 6px", color: "var(--text-secondary)" }}>
              <ZoomOut size={16} />
            </button>
            <span
              style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", minWidth: 40, textAlign: "center", cursor: "pointer" }}
              onClick={() => setZoom(1)}
              title="Reset zoom to 100%"
            >
              {Math.round(zoom * 100)}%
            </span>
            <button className="btn-ghost btn-sm" onClick={() => setZoom(zoom + 0.1)} title="Zoom in" style={{ padding: "4px 6px", color: "var(--text-secondary)" }}>
              <ZoomIn size={16} />
            </button>
          </div>
        </div>

        {/* User menu */}
        <div style={{ position: "fixed", right: (sidebarCollapsed ? 60 : rightSidebarWidth) + 12, top: "inherit", display: "flex", alignItems: "center", zIndex: 41, pointerEvents: "auto" }}>
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
        paddingRight: (sidebarCollapsed ? 60 : rightSidebarWidth) + (pageCount > 1 ? (pageNavCollapsed ? 28 : 148) : 0),
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
              const linkedGroups = new Set(selRegions.map((r) => r.linked_group).filter(Boolean));
              let label: string;
              if (linkedGroups.size === 1 && selRegions.every((r) => r.linked_group)) {
                const type = selRegions[0].pii_type;
                const text = selRegions[0].text.replace(/\n/g, " ");
                label = `${type}: ${text}`;
              } else if (types.size === 1) {
                label = `${selRegions.length} × ${[...types][0]}`;
              } else {
                label = `${selRegions.length} regions (multiple types)`;
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
