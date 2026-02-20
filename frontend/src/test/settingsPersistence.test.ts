import { describe, it, expect, beforeEach } from "vitest";
import { useAppStore } from "../store";

describe("Settings persistence", () => {
  beforeEach(() => {
    localStorage.clear();
    // Reset store to defaults
    useAppStore.setState({
      detectionSettings: {
        regex_enabled: true,
        custom_patterns_enabled: true,
        ner_enabled: true,
        llm_detection_enabled: true,
        ner_backend: "spacy",
        detection_fuzziness: 0.5,
        detection_language: "auto",
      },
    });
  });

  it("should persist detection settings to localStorage on change", () => {
    useAppStore.getState().setDetectionSettings({ regex_enabled: false });
    const stored = JSON.parse(localStorage.getItem("detectionSettings") || "{}");
    expect(stored.regex_enabled).toBe(false);
    // Other settings should still be present
    expect(stored.ner_enabled).toBe(true);
  });

  it("should persist language setting", () => {
    useAppStore.getState().setDetectionSettings({ detection_language: "de" });
    const stored = JSON.parse(localStorage.getItem("detectionSettings") || "{}");
    expect(stored.detection_language).toBe("de");
  });

  it("should persist fuzziness setting", () => {
    useAppStore.getState().setDetectionSettings({ detection_fuzziness: 0.8 });
    const stored = JSON.parse(localStorage.getItem("detectionSettings") || "{}");
    expect(stored.detection_fuzziness).toBe(0.8);
  });

  it("should persist NER backend setting", () => {
    useAppStore.getState().setDetectionSettings({ ner_backend: "gliner" });
    const stored = JSON.parse(localStorage.getItem("detectionSettings") || "{}");
    expect(stored.ner_backend).toBe("gliner");
  });

  it("should merge partial updates without losing other settings", () => {
    useAppStore.getState().setDetectionSettings({ regex_enabled: false });
    useAppStore.getState().setDetectionSettings({ ner_enabled: false });
    const settings = useAppStore.getState().detectionSettings;
    expect(settings.regex_enabled).toBe(false);
    expect(settings.ner_enabled).toBe(false);
    expect(settings.llm_detection_enabled).toBe(true);
  });
});

describe("Store - undo/redo", () => {
  beforeEach(() => {
    useAppStore.setState({
      regions: [],
      _undoStack: [],
      _redoStack: [],
      canUndo: false,
      canRedo: false,
    });
  });

  it("should push state to undo stack", () => {
    const r1 = [{ id: "r1", page_number: 1, bbox: { x0: 0, y0: 0, x1: 10, y1: 10 }, text: "a", pii_type: "PERSON" as const, confidence: 1, source: "NER" as const, char_start: 0, char_end: 1, action: "PENDING" as const }];
    useAppStore.setState({ regions: r1 as any });
    useAppStore.getState().pushUndo();
    expect(useAppStore.getState().canUndo).toBe(true);
    expect(useAppStore.getState()._undoStack).toHaveLength(1);
  });

  it("should undo to previous state", () => {
    const r1 = [{ id: "r1", text: "a", page_number: 1, bbox: { x0: 0, y0: 0, x1: 10, y1: 10 }, pii_type: "PERSON" as const, confidence: 1, source: "NER" as const, char_start: 0, char_end: 1, action: "PENDING" as const }];
    useAppStore.setState({ regions: [] });
    useAppStore.getState().pushUndo();
    useAppStore.setState({ regions: r1 as any });
    useAppStore.getState().undo();
    expect(useAppStore.getState().regions).toHaveLength(0);
    expect(useAppStore.getState().canRedo).toBe(true);
  });

  it("should redo after undo", () => {
    const r1 = [{ id: "r1", text: "b", page_number: 1, bbox: { x0: 0, y0: 0, x1: 10, y1: 10 }, pii_type: "PERSON" as const, confidence: 1, source: "NER" as const, char_start: 0, char_end: 1, action: "PENDING" as const }];
    useAppStore.setState({ regions: [] });
    useAppStore.getState().pushUndo();
    useAppStore.setState({ regions: r1 as any });
    useAppStore.getState().undo();
    useAppStore.getState().redo();
    expect(useAppStore.getState().regions).toHaveLength(1);
  });
});

describe("Store - upload queue", () => {
  beforeEach(() => {
    useAppStore.setState({ uploadQueue: [] });
  });

  it("should add items to upload queue", () => {
    useAppStore.getState().addToUploadQueue([
      { id: "u1", name: "test.pdf", file: null as any, status: "pending", progress: 0 },
    ]);
    expect(useAppStore.getState().uploadQueue).toHaveLength(1);
  });

  it("should update upload item", () => {
    useAppStore.getState().addToUploadQueue([
      { id: "u1", name: "test.pdf", file: null as any, status: "pending", progress: 0 },
    ]);
    useAppStore.getState().updateUploadItem("u1", { progress: 50, status: "uploading" });
    expect(useAppStore.getState().uploadQueue[0].progress).toBe(50);
  });

  it("should clear completed uploads", () => {
    useAppStore.setState({
      uploadQueue: [
        { id: "u1", name: "a.pdf", file: null as any, status: "done", progress: 100 },
        { id: "u2", name: "b.pdf", file: null as any, status: "pending", progress: 0 },
      ],
    });
    useAppStore.getState().clearCompletedUploads();
    expect(useAppStore.getState().uploadQueue).toHaveLength(1);
    expect(useAppStore.getState().uploadQueue[0].id).toBe("u2");
  });

  it("should remove error uploads", () => {
    useAppStore.setState({
      uploadQueue: [
        { id: "u1", name: "a.pdf", file: null as any, status: "error", progress: 0 },
        { id: "u2", name: "b.pdf", file: null as any, status: "done", progress: 100 },
      ],
    });
    useAppStore.getState().removeErrorUploads();
    expect(useAppStore.getState().uploadQueue).toHaveLength(1);
    expect(useAppStore.getState().uploadQueue[0].id).toBe("u2");
  });
});

describe("Store - snackbar", () => {
  beforeEach(() => {
    useAppStore.setState({ snackbars: [] });
  });

  it("should add snackbar", () => {
    useAppStore.getState().addSnackbar("Hello", "info");
    expect(useAppStore.getState().snackbars).toHaveLength(1);
    expect(useAppStore.getState().snackbars[0].message).toBe("Hello");
  });

  it("should cap snackbars at 5", () => {
    for (let i = 0; i < 8; i++) {
      useAppStore.getState().addSnackbar(`msg ${i}`);
    }
    expect(useAppStore.getState().snackbars.length).toBeLessThanOrEqual(5);
  });

  it("should remove snackbar by id", () => {
    useAppStore.getState().addSnackbar("test");
    const id = useAppStore.getState().snackbars[0].id;
    useAppStore.getState().removeSnackbar(id);
    expect(useAppStore.getState().snackbars).toHaveLength(0);
  });
});

describe("Store - region selection", () => {
  const regions = [
    { id: "r1", linked_group: "g1", page_number: 1, bbox: { x0: 0, y0: 0, x1: 10, y1: 10 }, text: "a", pii_type: "PERSON" as const, confidence: 1, source: "NER" as const, char_start: 0, char_end: 1, action: "PENDING" as const },
    { id: "r2", linked_group: "g1", page_number: 1, bbox: { x0: 0, y0: 10, x1: 10, y1: 20 }, text: "b", pii_type: "PERSON" as const, confidence: 1, source: "NER" as const, char_start: 1, char_end: 2, action: "PENDING" as const },
    { id: "r3", linked_group: null, page_number: 1, bbox: { x0: 20, y0: 0, x1: 30, y1: 10 }, text: "c", pii_type: "EMAIL" as const, confidence: 0.9, source: "REGEX" as const, char_start: 3, char_end: 4, action: "PENDING" as const },
  ];

  beforeEach(() => {
    useAppStore.setState({ regions: regions as any, selectedRegionIds: [] });
  });

  it("should select linked group when clicking one part", () => {
    useAppStore.getState().toggleSelectedRegionId("r1");
    expect(useAppStore.getState().selectedRegionIds).toContain("r1");
    expect(useAppStore.getState().selectedRegionIds).toContain("r2");
  });

  it("should select single non-linked region", () => {
    useAppStore.getState().toggleSelectedRegionId("r3");
    expect(useAppStore.getState().selectedRegionIds).toEqual(["r3"]);
  });

  it("should deselect linked group with additive toggle", () => {
    useAppStore.getState().toggleSelectedRegionId("r1"); // select g1
    useAppStore.getState().toggleSelectedRegionId("r1", true); // ctrl+click to deselect
    expect(useAppStore.getState().selectedRegionIds).toHaveLength(0);
  });

  it("clearSelection empties selectedRegionIds", () => {
    useAppStore.getState().toggleSelectedRegionId("r1");
    useAppStore.getState().clearSelection();
    expect(useAppStore.getState().selectedRegionIds).toHaveLength(0);
  });
});
