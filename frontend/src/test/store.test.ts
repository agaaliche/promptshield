import { describe, it, expect, beforeEach } from "vitest";
import { useAppStore } from "../store";

describe("AppStore", () => {
  beforeEach(() => {
    // Reset store between tests
    useAppStore.setState({
      backendReady: false,
      vaultUnlocked: false,
      documents: [],
      activeDocId: null,
      activePage: 1,
      regions: [],
      selectedRegionIds: [],
      zoom: 1,
      llmStatus: null,
      currentView: "upload",
      isProcessing: false,
      statusMessage: "",
    });
  });

  it("should start with upload view", () => {
    expect(useAppStore.getState().currentView).toBe("upload");
  });

  it("should set backend ready state", () => {
    useAppStore.getState().setBackendReady(true);
    expect(useAppStore.getState().backendReady).toBe(true);
  });

  it("should set current view", () => {
    useAppStore.getState().setCurrentView("viewer");
    expect(useAppStore.getState().currentView).toBe("viewer");
  });

  it("should set active document", () => {
    useAppStore.getState().setActiveDocId("doc-123");
    expect(useAppStore.getState().activeDocId).toBe("doc-123");
  });

  it("should set zoom level", () => {
    useAppStore.getState().setZoom(1.5);
    expect(useAppStore.getState().zoom).toBe(1.5);
  });

  it("should track processing state", () => {
    useAppStore.getState().setIsProcessing(true);
    expect(useAppStore.getState().isProcessing).toBe(true);
    useAppStore.getState().setIsProcessing(false);
    expect(useAppStore.getState().isProcessing).toBe(false);
  });

  it("should update status message", () => {
    useAppStore.getState().setStatusMessage("Uploading...");
    expect(useAppStore.getState().statusMessage).toBe("Uploading...");
  });

  it("should manage regions array", () => {
    const mockRegions = [
      {
        id: "r1",
        page_number: 1,
        bbox: { x: 0, y: 0, width: 100, height: 20 },
        pii_type: "PERSON" as const,
        confidence: 0.95,
        source: "ner" as const,
        original_text: "John Doe",
        action: "pending" as const,
      },
    ];
    useAppStore.getState().setRegions(mockRegions);
    expect(useAppStore.getState().regions).toHaveLength(1);
    expect(useAppStore.getState().regions[0].original_text).toBe("John Doe");
  });

  it("should set vault unlocked state", () => {
    useAppStore.getState().setVaultUnlocked(true);
    expect(useAppStore.getState().vaultUnlocked).toBe(true);
  });
});
