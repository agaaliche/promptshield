import { useEffect } from "react";
import type { PIIRegion, RegionAction } from "../types";

interface UseKeyboardShortcutsOptions {
  activePage: number;
  pageCount: number;
  zoom: number;
  regions: PIIRegion[];
  pageRegions: PIIRegion[];
  selectedRegionIds: string[];
  copiedRegions: PIIRegion[];
  activeDocId: string | null;
  cursorTool: "pointer" | "lasso" | "draw";
  showTypePicker: boolean;
  canUndo: boolean;
  canRedo: boolean;
  setActivePage: (p: number) => void;
  setZoom: (z: number) => void;
  setSelectedRegionIds: (ids: string[]) => void;
  clearSelection: () => void;
  setCursorTool: (t: "pointer" | "lasso" | "draw") => void;
  prevCursorToolRef: React.MutableRefObject<"pointer" | "lasso" | "draw">;
  cancelTypePicker: () => void;
  handleRegionAction: (id: string, action: RegionAction) => void;
  undo: () => void;
  redo: () => void;
  pushUndo: () => void;
  removeRegion: (id: string) => void;
  setCopiedRegions: (regions: PIIRegion[]) => void;
  setStatusMessage: (msg: string) => void;
  handlePasteRegions: () => void;
  batchDeleteRegions: (docId: string, ids: string[]) => Promise<any>;
}

export default function useKeyboardShortcuts(opts: UseKeyboardShortcutsOptions) {
  const {
    activePage,
    pageCount,
    zoom,
    regions,
    pageRegions,
    selectedRegionIds,
    copiedRegions,
    activeDocId,
    cursorTool,
    showTypePicker,
    canUndo,
    canRedo,
    setActivePage,
    setZoom,
    setSelectedRegionIds,
    clearSelection,
    setCursorTool,
    prevCursorToolRef,
    cancelTypePicker,
    handleRegionAction,
    undo,
    redo,
    pushUndo,
    removeRegion,
    setCopiedRegions,
    setStatusMessage,
    handlePasteRegions,
    batchDeleteRegions,
  } = opts;

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      switch (e.key) {
        case "z":
          if (e.ctrlKey || e.metaKey) { e.preventDefault(); undo(); }
          break;
        case "y":
          if (e.ctrlKey || e.metaKey) { e.preventDefault(); redo(); }
          break;
        case "a":
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
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
          e.preventDefault(); setZoom(zoom + 0.1);
          break;
        case "-":
          e.preventDefault(); setZoom(zoom - 0.1);
          break;
        case "0":
          e.preventDefault(); setZoom(1);
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
  }, [
    activePage,
    pageCount,
    zoom,
    regions,
    pageRegions,
    selectedRegionIds,
    copiedRegions,
    activeDocId,
    cursorTool,
    showTypePicker,
    canUndo,
    canRedo,
    setActivePage,
    setZoom,
    setSelectedRegionIds,
    clearSelection,
    setCursorTool,
    prevCursorToolRef,
    cancelTypePicker,
    handleRegionAction,
    undo,
    redo,
    pushUndo,
    removeRegion,
    setCopiedRegions,
    setStatusMessage,
    handlePasteRegions,
    batchDeleteRegions,
  ]);
}
