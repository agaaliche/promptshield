/** Page navigator sidebar — shows page thumbnails for quick navigation. */

import React from "react";
import { ChevronLeft, ChevronRight, ShieldCheck } from "lucide-react";
import { getPageBitmapUrl } from "../api";
import type { PIIRegion } from "../types";

interface PageNavigatorProps {
  docId: string | null;
  pageCount: number;
  activePage: number;
  onPageSelect: (page: number) => void;
  /** Right offset so it sits left of the region sidebar */
  rightOffset: number;
  collapsed: boolean;
  onCollapsedChange: (v: boolean) => void;
  /** All regions across all pages — used for per-page status badges */
  regions: PIIRegion[];
  /** Sidebar width for resize handle */
  sidebarWidth: number;
  onSidebarWidthChange: (w: number) => void;
}

const NAV_WIDTH = 148;
const NAV_COLLAPSED_WIDTH = 28;

export default function PageNavigator({
  docId,
  pageCount,
  activePage,
  onPageSelect,
  rightOffset,
  collapsed,
  onCollapsedChange,
  regions,
  sidebarWidth,
  onSidebarWidthChange,
}: PageNavigatorProps) {
  const listRef = React.useRef<HTMLDivElement>(null);
  const isDragging = React.useRef(false);
  const startX = React.useRef(0);
  const startWidth = React.useRef(sidebarWidth);

  const onResizeMouseDown = React.useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    startX.current = e.clientX;
    startWidth.current = sidebarWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [sidebarWidth]);

  React.useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      const delta = startX.current - e.clientX;
      const newWidth = Math.min(600, Math.max(200, startWidth.current + delta));
      onSidebarWidthChange(newWidth);
    };
    const onMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, [onSidebarWidthChange]);

  // Scroll active page thumbnail into view
  React.useEffect(() => {
    if (collapsed || !listRef.current) return;
    const thumb = listRef.current.querySelector(`[data-page="${activePage}"]`) as HTMLElement | null;
    if (thumb) {
      thumb.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [activePage, collapsed]);

  // Compute which pages are "cleared" — no pending regions and at least one tokenized/removed
  const clearedPages = React.useMemo(() => {
    const set = new Set<number>();
    for (let p = 1; p <= pageCount; p++) {
      const pageRegs = regions.filter((r) => r.page_number === p);
      if (pageRegs.length === 0) continue;
      const hasPending = pageRegs.some((r) => r.action === "PENDING");
      const hasHandled = pageRegs.some((r) => r.action === "REMOVE" || r.action === "TOKENIZE");
      if (!hasPending && hasHandled) set.add(p);
    }
    return set;
  }, [regions, pageCount]);

  if (pageCount <= 1) return null;

  return (
    <div style={{
      position: "absolute",
      right: rightOffset,
      top: 0,
      bottom: 0,
      width: collapsed ? NAV_COLLAPSED_WIDTH : NAV_WIDTH,
      background: "var(--bg-secondary)",
      borderLeft: "1px solid var(--border-color)",
      display: "flex",
      flexDirection: "column",
      zIndex: 9,
      transition: isDragging.current ? "none" : "width 0.2s ease",
    }}>
      {/* Resize handle on the left edge */}
      <div
        onMouseDown={onResizeMouseDown}
        style={{
          position: 'absolute',
          left: -3,
          top: 0,
          bottom: 0,
          width: 6,
          cursor: 'col-resize',
          zIndex: 20,
          background: 'transparent',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--accent-primary)')}
        onMouseLeave={(e) => { if (!isDragging.current) e.currentTarget.style.background = 'transparent'; }}
      />
      {collapsed ? (
        <div style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          paddingTop: 12,
          gap: 8,
        }}>
          <button
            onClick={() => onCollapsedChange(false)}
            style={btnStyle}
            title="Expand page navigator"
          >
            <ChevronLeft size={14} />
          </button>
          <span style={{
            writingMode: "vertical-lr",
            fontSize: 10,
            color: "var(--text-muted)",
            letterSpacing: 1,
            userSelect: "none",
          }}>
            Pages
          </span>
        </div>
      ) : (
        <>
          {/* Header */}
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "8px 8px 6px",
            borderBottom: "1px solid var(--border-color)",
            flexShrink: 0,
          }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)" }}>
              Pages
            </span>
            <button
              onClick={() => onCollapsedChange(true)}
              style={btnStyle}
              title="Collapse page navigator"
            >
              <ChevronRight size={14} />
            </button>
          </div>
          {/* Thumbnail list */}
          <div ref={listRef} style={{
            flex: 1,
            overflowY: "auto",
            padding: "8px 14px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}>
            {Array.from({ length: pageCount }, (_, i) => i + 1).map((page) => {
              const isActive = page === activePage;
              const isCleared = clearedPages.has(page);
              return (
                <div
                  key={page}
                  data-page={page}
                  onClick={() => onPageSelect(page)}
                  style={{
                    cursor: "pointer",
                    borderRadius: 4,
                    border: isActive
                      ? "2px solid var(--accent-primary)"
                      : "2px solid transparent",
                    background: isActive ? "rgba(100,181,246,0.08)" : "transparent",
                    padding: 2,
                    position: "relative",
                    transition: "border-color 0.15s ease, background 0.15s ease",
                  }}
                >
                  {docId && (
                    <img
                      src={getPageBitmapUrl(docId, page)}
                      alt={`Page ${page}`}
                      style={{
                        width: "100%",
                        display: "block",
                        borderRadius: 2,
                        opacity: isActive ? 1 : 0.7,
                        transition: "opacity 0.15s ease",
                      }}
                      loading="lazy"
                    />
                  )}
                  {isCleared && (
                    <div style={{
                      position: "absolute",
                      inset: 0,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      opacity: 0.5,
                      pointerEvents: "none",
                    }}>
                      <ShieldCheck size={80} color="#4caf50" fill="#4caf50" strokeWidth={0} />
                    </div>
                  )}
                  <div style={{
                    textAlign: "center",
                    fontSize: 10,
                    color: isActive ? "var(--accent-primary)" : "var(--text-muted)",
                    fontWeight: isActive ? 600 : 400,
                    marginTop: 2,
                    userSelect: "none",
                  }}>
                    {page}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "var(--text-secondary)",
  cursor: "pointer",
  padding: 4,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};
