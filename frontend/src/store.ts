/** Global application state using Zustand. */

import { create } from "zustand";
import type {
  BBox,
  DocumentInfo,
  PIIRegion,
  RegionAction,
  LLMStatus,
  UploadItem,
  SnackbarItem,
} from "./types";

interface AppState {
  // ── Connection ──
  backendReady: boolean;
  setBackendReady: (v: boolean) => void;

  // ── Vault ──
  vaultUnlocked: boolean;
  setVaultUnlocked: (v: boolean) => void;

  // ── Documents ──
  documents: DocumentInfo[];
  setDocuments: (docs: DocumentInfo[]) => void;
  addDocument: (doc: DocumentInfo) => void;
  updateDocument: (docId: string, partial: Partial<DocumentInfo>) => void;

  // ── Active document ──
  activeDocId: string | null;
  setActiveDocId: (id: string | null) => void;

  // ── Page navigation ──
  activePage: number;
  setActivePage: (n: number) => void;

  // ── Regions ──
  regions: PIIRegion[];
  setRegions: (regions: PIIRegion[]) => void;
  updateRegionAction: (regionId: string, action: RegionAction) => void;
  removeRegion: (regionId: string) => void;
  updateRegionBBox: (regionId: string, bbox: BBox) => void;
  updateRegion: (regionId: string, updates: Partial<PIIRegion>) => void;
  selectedRegionIds: string[];
  setSelectedRegionIds: (ids: string[]) => void;
  toggleSelectedRegionId: (id: string, additive?: boolean) => void;
  clearSelection: () => void;

  // ── Undo / Redo ──
  /** Push current regions onto the undo stack (call before mutating). */
  pushUndo: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  _undoStack: PIIRegion[][];
  _redoStack: PIIRegion[][];

  // ── Zoom ──
  zoom: number;
  setZoom: (z: number) => void;

  // ── LLM ──
  llmStatus: LLMStatus | null;
  setLLMStatus: (s: LLMStatus) => void;

  // ── Detection settings ──
  detectionSettings: {
    regex_enabled: boolean;
    ner_enabled: boolean;
    llm_detection_enabled: boolean;
    ner_backend: string;
  };
  setDetectionSettings: (s: Partial<AppState["detectionSettings"]>) => void;

  // ── Draw mode ──
  drawMode: boolean;
  setDrawMode: (v: boolean) => void;

  // ── Document loading ──
  docLoading: boolean;
  setDocLoading: (v: boolean) => void;
  docLoadingMessage: string;
  setDocLoadingMessage: (msg: string) => void;
  docDetecting: boolean;
  setDocDetecting: (v: boolean) => void;

  // ── UI ──
  currentView: "upload" | "viewer" | "detokenize" | "settings";
  setCurrentView: (v: "upload" | "viewer" | "detokenize" | "settings") => void;
  isProcessing: boolean;
  setIsProcessing: (v: boolean) => void;
  statusMessage: string;
  setStatusMessage: (msg: string) => void;

  // ── Snackbar ──
  snackbars: SnackbarItem[];
  addSnackbar: (message: string, type?: "success" | "error" | "info") => void;
  removeSnackbar: (id: string) => void;

  // ── Left sidebar ──
  leftSidebarWidth: number;
  setLeftSidebarWidth: (w: number) => void;

  // ── Upload queue ──
  uploadQueue: UploadItem[];
  setUploadQueue: (items: UploadItem[]) => void;
  addToUploadQueue: (items: UploadItem[]) => void;
  updateUploadItem: (id: string, updates: Partial<UploadItem>) => void;
  clearCompletedUploads: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Connection
  backendReady: false,
  setBackendReady: (v) => set({ backendReady: v }),

  // Left sidebar
  leftSidebarWidth: parseInt(localStorage.getItem('leftSidebarWidth') || '200', 10),
  setLeftSidebarWidth: (w) => {
    localStorage.setItem('leftSidebarWidth', String(w));
    set({ leftSidebarWidth: w });
  },

  // Vault
  vaultUnlocked: false,
  setVaultUnlocked: (v) => set({ vaultUnlocked: v }),

  // Documents
  documents: [],
  setDocuments: (docs) => set({ documents: docs }),
  addDocument: (doc) =>
    set((s) => ({ documents: [...s.documents, doc] })),
  updateDocument: (docId, partial) =>
    set((s) => ({
      documents: s.documents.map((d) =>
        d.doc_id === docId ? { ...d, ...partial } : d
      ),
    })),

  // Active document
  activeDocId: null,
  setActiveDocId: (id) => set({ activeDocId: id, activePage: 1 }),

  // Page
  activePage: 1,
  setActivePage: (n) => set({ activePage: n }),

  // Regions
  regions: [],
  setRegions: (regions) => set({ regions }),
  updateRegionAction: (regionId, action) =>
    set((s) => ({
      regions: s.regions.map((r) =>
        r.id === regionId ? { ...r, action } : r
      ),
    })),
  removeRegion: (regionId) =>
    set((s) => ({
      regions: s.regions.filter((r) => r.id !== regionId),
      selectedRegionIds: s.selectedRegionIds.filter((id) => id !== regionId),
    })),
  updateRegionBBox: (regionId, bbox) =>
    set((s) => ({
      regions: s.regions.map((r) =>
        r.id === regionId ? { ...r, bbox } : r
      ),
    })),
  updateRegion: (regionId, updates) =>
    set((s) => ({
      regions: s.regions.map((r) =>
        r.id === regionId ? { ...r, ...updates } : r
      ),
    })),
  selectedRegionIds: [],
  setSelectedRegionIds: (ids) => set({ selectedRegionIds: ids }),
  toggleSelectedRegionId: (id, additive) =>
    set((s) => {
      if (additive) {
        // Ctrl+click: toggle in/out
        return {
          selectedRegionIds: s.selectedRegionIds.includes(id)
            ? s.selectedRegionIds.filter((x) => x !== id)
            : [...s.selectedRegionIds, id],
        };
      }
      // Plain click: single-select
      return { selectedRegionIds: [id] };
    }),
  clearSelection: () => set({ selectedRegionIds: [] }),

  // Undo / Redo
  _undoStack: [],
  _redoStack: [],
  canUndo: false,
  canRedo: false,
  pushUndo: () =>
    set((s) => {
      const stack = [...s._undoStack, s.regions.map((r) => ({ ...r }))];
      // Cap at 50 entries to avoid memory bloat
      if (stack.length > 50) stack.shift();
      return { _undoStack: stack, _redoStack: [], canUndo: true, canRedo: false };
    }),
  undo: () =>
    set((s) => {
      if (s._undoStack.length === 0) return s;
      const newUndo = [...s._undoStack];
      const prev = newUndo.pop()!;
      const newRedo = [...s._redoStack, s.regions.map((r) => ({ ...r }))];
      if (newRedo.length > 50) newRedo.shift();
      return {
        regions: prev,
        _undoStack: newUndo,
        _redoStack: newRedo,
        canUndo: newUndo.length > 0,
        canRedo: true,
      };
    }),
  redo: () =>
    set((s) => {
      if (s._redoStack.length === 0) return s;
      const newRedo = [...s._redoStack];
      const next = newRedo.pop()!;
      const newUndo = [...s._undoStack, s.regions.map((r) => ({ ...r }))];
      if (newUndo.length > 50) newUndo.shift();
      return {
        regions: next,
        _undoStack: newUndo,
        _redoStack: newRedo,
        canUndo: true,
        canRedo: newRedo.length > 0,
      };
    }),

  // Zoom
  zoom: 1.0,
  setZoom: (z) => set({ zoom: Math.max(0.25, Math.min(4, z)) }),

  // LLM
  llmStatus: null,
  setLLMStatus: (s) => set({ llmStatus: s }),

  // Detection settings
  detectionSettings: {
    regex_enabled: true,
    ner_enabled: true,
    llm_detection_enabled: true,
    ner_backend: "spacy",
  },
  setDetectionSettings: (s) =>
    set((state) => ({
      detectionSettings: { ...state.detectionSettings, ...s },
    })),

  // Draw mode
  drawMode: false,
  setDrawMode: (v) => set({ drawMode: v }),

  // Document loading
  docLoading: false,
  setDocLoading: (v) => set({ docLoading: v }),
  docLoadingMessage: "",
  setDocLoadingMessage: (msg) => set({ docLoadingMessage: msg }),
  docDetecting: false,
  setDocDetecting: (v) => set({ docDetecting: v }),

  // UI
  currentView: "upload",
  setCurrentView: (v) => set({ currentView: v }),
  isProcessing: false,
  setIsProcessing: (v) => set({ isProcessing: v }),
  statusMessage: "",
  setStatusMessage: (msg) => {
    set({ statusMessage: msg });
    if (!msg) return;
    const isError = /fail|error/i.test(msg);
    const type = isError ? "error" : "success";
    const id = `snack-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    set((s) => ({ snackbars: [...s.snackbars, { id, message: msg, type, createdAt: Date.now() }] }));
  },

  // Snackbar
  snackbars: [],
  addSnackbar: (message, type = "info") => {
    const id = `snack-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    set((s) => ({ snackbars: [...s.snackbars, { id, message, type, createdAt: Date.now() }] }));
  },
  removeSnackbar: (id) =>
    set((s) => ({ snackbars: s.snackbars.filter((s2) => s2.id !== id) })),

  // Upload queue
  uploadQueue: [],
  setUploadQueue: (items) => set({ uploadQueue: items }),
  addToUploadQueue: (items) => set((s) => ({ uploadQueue: [...s.uploadQueue, ...items] })),
  updateUploadItem: (id, updates) => set((s) => ({
    uploadQueue: s.uploadQueue.map((u) => u.id === id ? { ...u, ...updates } : u),
  })),
  clearCompletedUploads: () => set((s) => ({
    uploadQueue: s.uploadQueue.filter((u) => u.status !== "done"),
  })),
}));
