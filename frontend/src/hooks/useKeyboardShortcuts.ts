import { useEffect, useRef } from "react";
import type { PIIRegion, RegionAction } from "../types";
import { logError } from "../api";

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
  showAutodetect: boolean;
  setShowAutodetect: (show: boolean) => void;
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
  // Keep a ref to the latest opts so the keydown handler always reads
  // fresh values without needing to re-register the listener.
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const o = optsRef.current;
      const el = e.target as HTMLElement;
      const tag = el.tagName;
      // Skip when user is typing in an editable field
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        el.isContentEditable
      ) return;
      // Skip all keys when inside BlacklistGrid (Excel-like control handles its own shortcuts)
      if (el.closest("[data-blacklist-grid]")) return;
      switch (e.key) {
        case "f":
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            o.setShowAutodetect(!o.showAutodetect);
          }
          break;
        case "z":
          if (e.ctrlKey || e.metaKey) { e.preventDefault(); o.undo(); }
          break;
        case "y":
          if (e.ctrlKey || e.metaKey) { e.preventDefault(); o.redo(); }
          break;
        case "a":
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            o.setSelectedRegionIds(o.pageRegions.filter((r) => r.action !== "CANCEL").map((r) => r.id));
          }
          break;
        case "ArrowLeft":
          e.preventDefault();
          o.setActivePage(Math.max(1, o.activePage - 1));
          break;
        case "ArrowRight":
          e.preventDefault();
          o.setActivePage(Math.min(o.pageCount, o.activePage + 1));
          break;
        case "+":
        case "=":
          e.preventDefault(); o.setZoom(o.zoom + 0.1);
          break;
        case "-":
          e.preventDefault(); o.setZoom(o.zoom - 0.1);
          break;
        case "0":
          e.preventDefault(); o.setZoom(1);
          break;
        case "Escape":
          o.clearSelection();
          if (o.cursorTool !== "pointer") o.setCursorTool("pointer");
          if (o.showTypePicker) o.cancelTypePicker();
          break;
        case " ": {
          e.preventDefault();
          if (o.cursorTool !== "pointer") {
            o.prevCursorToolRef.current = o.cursorTool;
            o.setCursorTool("pointer");
          } else {
            o.setCursorTool(o.prevCursorToolRef.current);
          }
          break;
        }
        case "d":
          if (o.selectedRegionIds.length > 0) {
            e.preventDefault();
            o.selectedRegionIds.forEach((id) => {
              const r = o.regions.find((reg) => reg.id === id);
              o.handleRegionAction(id, r?.action === "REMOVE" ? "PENDING" : "REMOVE");
            });
          } else {
            // No selection: switch to draw cursor
            e.preventDefault();
            o.setCursorTool("draw");
          }
          break;
        case "Delete":
          if (o.selectedRegionIds.length > 0 && o.activeDocId) {
            e.preventDefault();
            o.pushUndo();
            const delIds = [...o.selectedRegionIds];
            delIds.forEach((id) => o.removeRegion(id));
            o.batchDeleteRegions(o.activeDocId, delIds).catch(logError("delete-regions"));
          }
          break;
        case "Backspace":
          if (o.selectedRegionIds.length > 0) {
            e.preventDefault();
            o.selectedRegionIds.forEach((id) => {
              const r = o.regions.find((reg) => reg.id === id);
              o.handleRegionAction(id, r?.action === "REMOVE" ? "PENDING" : "REMOVE");
            });
          }
          break;
        case "t":
          if (o.selectedRegionIds.length > 0) {
            e.preventDefault();
            o.selectedRegionIds.forEach((id) => {
              const r = o.regions.find((reg) => reg.id === id);
              o.handleRegionAction(id, r?.action === "TOKENIZE" ? "PENDING" : "TOKENIZE");
            });
          }
          break;
        case "c":
          if (e.ctrlKey || e.metaKey) {
            if (o.selectedRegionIds.length > 0) {
              e.preventDefault();
              const regionsToCopy = o.regions.filter((r) => o.selectedRegionIds.includes(r.id));
              o.setCopiedRegions(regionsToCopy);
              o.setStatusMessage(`Copied ${regionsToCopy.length} region(s)`);
            }
          }
          // Bare "c" without modifier is intentionally a no-op to prevent
          // accidental region deletion (M14: destructive-action guard).
          break;
        case "v":
          if ((e.ctrlKey || e.metaKey) && o.copiedRegions.length > 0) {
            e.preventDefault();
            o.handlePasteRegions();
          } else if (!e.ctrlKey && !e.metaKey) {
            // Bare "v": switch to pointer cursor
            e.preventDefault();
            o.setCursorTool("pointer");
          }
          break;
        case "s":
          if (!e.ctrlKey && !e.metaKey) {
            // Bare "s": switch to multi-select (lasso) cursor
            e.preventDefault();
            o.setCursorTool("lasso");
          }
          break;
        case "Tab": {
          e.preventDefault();
          const pending = o.pageRegions.filter((r) => r.action === "PENDING");
          if (pending.length === 0) break;
          const lastSelected = o.selectedRegionIds[o.selectedRegionIds.length - 1];
          const currentIdx = pending.findIndex((r) => r.id === lastSelected);
          const next = e.shiftKey
            ? (currentIdx <= 0 ? pending.length - 1 : currentIdx - 1)
            : (currentIdx + 1) % pending.length;
          o.setSelectedRegionIds([pending[next].id]);
          break;
        }
      }
    };

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []); // stable — handler reads from optsRef
}
