/**
 * useRegionActions — Region CRUD, autodetect, clipboard, and reset handlers.
 *
 * Extracted from DocumentViewer to reduce component size.
 */

import { useState, useCallback } from "react";
import { useAppStore } from "../store";
import {
  setRegionAction,
  batchRegionAction,
  reanalyzeRegion,
  highlightAllRegions,
  updateRegionLabel,
  updateRegionText,
  addManualRegion,
  redetectPII,
  resetDetection,
  deleteRegion,
  batchDeleteRegions,
} from "../api";
import { resolveAllOverlaps } from "../regionUtils";
import { toErrorMessage } from "../errorUtils";
import type { PIIRegion, PIIType, RegionAction } from "../types";

interface UseRegionActionsOpts {
  activeDocId: string | null;
  activePage: number;
  regions: PIIRegion[];
  pushUndo: () => void;
  updateRegionAction: (id: string, action: RegionAction) => void;
  removeRegion: (id: string) => void;
  setRegions: (regions: PIIRegion[]) => void;
  updateRegion: (id: string, patch: Partial<PIIRegion>) => void;
  setIsProcessing: (v: boolean) => void;
  setStatusMessage: (msg: string) => void;
  setSelectedRegionIds: (ids: string[]) => void;
}

export default function useRegionActions(opts: UseRegionActionsOpts) {
  const {
    activeDocId, activePage, regions,
    pushUndo, updateRegionAction, removeRegion, setRegions,
    updateRegion, setIsProcessing, setStatusMessage, setSelectedRegionIds,
  } = opts;

  const [copiedRegions, setCopiedRegions] = useState<PIIRegion[]>([]);
  const [showAutodetect, setShowAutodetect] = useState(false);
  const [redetecting, setRedetecting] = useState(false);

  const handleRegionAction = useCallback(
    async (regionId: string, action: RegionAction) => {
      if (!activeDocId) return;
      try {
        pushUndo();
        await setRegionAction(activeDocId, regionId, action);
        updateRegionAction(regionId, action);
      } catch (e: unknown) {
        console.error("Failed to set region action:", e);
      }
    },
    [activeDocId, updateRegionAction, pushUndo],
  );

  const handleRefreshRegion = useCallback(
    async (regionId: string, textOnly?: boolean) => {
      if (!activeDocId) return;
      try {
        if (!textOnly) pushUndo();
        const result = await reanalyzeRegion(activeDocId, regionId);
        if (textOnly) {
          // Auto-refresh after move/resize/create: only update extracted text,
          // preserve the user-chosen PII type, confidence, and source.
          if (result.text) {
            updateRegion(regionId, { text: result.text });
          }
        } else {
          // Explicit "Detect" button: full re-classification.
          updateRegion(regionId, {
            text: result.text,
            pii_type: result.pii_type as PIIType,
            confidence: result.confidence,
            source: result.source as any,
          });
          setStatusMessage(
            result.text
              ? `Refreshed: ${result.pii_type} — "${result.text.slice(0, 40)}"`
              : "No text found under this region",
          );
        }
      } catch (e: unknown) {
        console.error("Failed to refresh region:", e);
        if (!textOnly) setStatusMessage(`Refresh failed: ${toErrorMessage(e)}`);
      }
    },
    [activeDocId, pushUndo, updateRegion, setStatusMessage],
  );

  const handleClearRegion = useCallback(
    async (regionId: string) => {
      if (!activeDocId) return;
      try {
        pushUndo();
        removeRegion(regionId);
        await deleteRegion(activeDocId, regionId);
      } catch (e: unknown) {
        if (toErrorMessage(e).includes("404")) return;
        console.error("Failed to delete region:", e);
        setStatusMessage(`Delete failed: ${toErrorMessage(e)}`);
      }
    },
    [activeDocId, pushUndo, removeRegion, setStatusMessage],
  );

  const handleHighlightAll = useCallback(
    async (regionId: string) => {
      if (!activeDocId) return;
      const region = regions.find((r) => r.id === regionId);
      if (!region) return;
      const addSnackbar = useAppStore.getState().addSnackbar;
      try {
        pushUndo();
        const resp = await highlightAllRegions(activeDocId, regionId);
        if (resp.new_regions.length > 0) {
          setRegions(resolveAllOverlaps([...regions, ...resp.new_regions]));
        }
        setSelectedRegionIds(resp.all_ids);
        const msg =
          resp.created > 0
            ? `Found ${resp.all_ids.length} occurrences of "${region.text}" (${resp.created} new)`
            : `Highlighted ${resp.all_ids.length} existing region${resp.all_ids.length !== 1 ? "s" : ""} matching "${region.text}"`;
        setStatusMessage(msg);
        addSnackbar(msg, "success");
      } catch (e: unknown) {
        console.error("Highlight all failed:", e);
        const errMsg = `Highlight all failed: ${toErrorMessage(e)}`;
        setStatusMessage(errMsg);
        addSnackbar(errMsg, "error");
      }
    },
    [activeDocId, regions, setRegions, setSelectedRegionIds, setStatusMessage, pushUndo],
  );

  const handleUpdateLabel = useCallback(
    async (regionId: string, newType: PIIType) => {
      if (!activeDocId) return;
      try {
        pushUndo();
        // Optimistic update for the target
        updateRegion(regionId, { pii_type: newType });
        // Backend propagates to all same-text siblings and returns the full list
        const resp = await updateRegionLabel(activeDocId, regionId, newType);
        for (const item of resp.updated) {
          updateRegion(item.id, { pii_type: item.pii_type as PIIType });
        }
      } catch (e: unknown) {
        console.error("Update label failed:", e);
        setStatusMessage(`Update failed: ${toErrorMessage(e)}`);
      }
    },
    [activeDocId, pushUndo, updateRegion, setStatusMessage],
  );

  const handleUpdateText = useCallback(
    async (regionId: string, newText: string) => {
      if (!activeDocId) return;
      try {
        pushUndo();
        // Optimistic update for the target
        updateRegion(regionId, { text: newText });
        // Backend propagates to all same-text siblings and returns the full list
        const resp = await updateRegionText(activeDocId, regionId, newText);
        for (const item of resp.updated) {
          updateRegion(item.id, { text: item.text });
        }
      } catch (e: unknown) {
        console.error("Update text failed:", e);
        setStatusMessage(`Update failed: ${toErrorMessage(e)}`);
      }
    },
    [activeDocId, pushUndo, updateRegion, setStatusMessage],
  );

  const handlePasteRegions = useCallback(async () => {
    if (!activeDocId || copiedRegions.length === 0) return;
    try {
      pushUndo();
      const newRegions: PIIRegion[] = [];
      const newIds: string[] = [];

      for (const copied of copiedRegions) {
        const regionToPaste: Partial<PIIRegion> = {
          page_number: activePage,
          bbox: { ...copied.bbox },
          text: copied.text,
          pii_type: copied.pii_type,
          confidence: copied.confidence,
          source: "MANUAL",
          char_start: 0,
          char_end: 0,
          action: copied.action === "CANCEL" ? "PENDING" : copied.action,
        };

        const response = await addManualRegion(activeDocId, regionToPaste);

        const created: PIIRegion = {
          id: response.region_id,
          page_number: activePage,
          bbox: { ...copied.bbox },
          text: copied.text,
          pii_type: copied.pii_type,
          confidence: copied.confidence,
          source: "MANUAL",
          char_start: 0,
          char_end: 0,
          action: copied.action === "CANCEL" ? "PENDING" : copied.action,
        };

        newRegions.push(created);
        newIds.push(created.id);
      }

      setRegions(resolveAllOverlaps([...regions, ...newRegions]));
      setSelectedRegionIds(newIds);
      setStatusMessage(`Pasted ${newRegions.length} region(s) on page ${activePage}`);
    } catch (e: unknown) {
      console.error("Failed to paste regions:", e);
      setStatusMessage(`Paste failed: ${toErrorMessage(e)}`);
    }
  }, [activeDocId, activePage, copiedRegions, regions, setRegions, setSelectedRegionIds, setStatusMessage, pushUndo]);

  const handleBatchAction = useCallback(
    async (action: RegionAction) => {
      if (!activeDocId) return;
      const ids = regions.filter((r) => r.action === "PENDING").map((r) => r.id);
      if (ids.length === 0) return;
      try {
        pushUndo();
        await batchRegionAction(activeDocId, ids, action);
        ids.forEach((id) => updateRegionAction(id, action));
      } catch (e: unknown) {
        console.error("Batch action failed:", e);
      }
    },
    [activeDocId, regions, updateRegionAction, pushUndo],
  );

  const handleResetAll = useCallback(async () => {
    if (!activeDocId) return;
    const ids = regions.map((r) => r.id);
    if (ids.length === 0) return;
    try {
      pushUndo();
      await batchDeleteRegions(activeDocId, ids);
      ids.forEach((id) => removeRegion(id));
    } catch (e: unknown) {
      console.error("Reset all failed:", e);
    }
  }, [activeDocId, regions, removeRegion, pushUndo]);

  const handleResetPage = useCallback(async (page: number) => {
    if (!activeDocId) return;
    const ids = regions.filter((r) => r.page_number === page).map((r) => r.id);
    if (ids.length === 0) return;
    try {
      pushUndo();
      await batchDeleteRegions(activeDocId, ids);
      ids.forEach((id) => removeRegion(id));
    } catch (e: unknown) {
      console.error("Reset page failed:", e);
    }
  }, [activeDocId, regions, removeRegion, pushUndo]);

  const handleAutodetect = useCallback(
    async (autodetectOpts: {
      fuzziness: number;
      scope: "page" | "all";
      regexEnabled: boolean;
      nerEnabled: boolean;
      llmEnabled: boolean;
      regexTypes: string[];
      nerTypes: string[];
      blacklistTerms: string[];
      blacklistAction: string;
      blacklistFuzziness: number;
    }) => {
      if (!activeDocId) return;
      setIsProcessing(true);
      setRedetecting(true);
      setStatusMessage("Running PII autodetection…");
      try {
        pushUndo();
        const result = await redetectPII(activeDocId, {
          confidence_threshold: autodetectOpts.fuzziness,
          page_number: autodetectOpts.scope === "page" ? activePage : undefined,
          regex_enabled: autodetectOpts.regexEnabled,
          ner_enabled: autodetectOpts.nerEnabled,
          llm_detection_enabled: autodetectOpts.llmEnabled,
          regex_types: autodetectOpts.regexEnabled ? autodetectOpts.regexTypes : null,
          ner_types: autodetectOpts.nerEnabled ? autodetectOpts.nerTypes : null,
          blacklist_terms: autodetectOpts.blacklistTerms.length > 0 ? autodetectOpts.blacklistTerms : undefined,
          blacklist_action: autodetectOpts.blacklistTerms.length > 0 ? autodetectOpts.blacklistAction : undefined,
          blacklist_fuzziness: autodetectOpts.blacklistTerms.length > 0 ? autodetectOpts.blacklistFuzziness : undefined,
        });
        setRegions(resolveAllOverlaps(result.regions));
        setStatusMessage(
          `Autodetect: ${result.added} added, ${result.updated} updated, ${result.removed ?? 0} removed (${result.total_regions} total)`,
        );
      } catch (err) {
        setStatusMessage(`Autodetect failed: ${err}`);
      } finally {
        setIsProcessing(false);
        setRedetecting(false);
      }
    },
    [activeDocId, activePage, pushUndo, setRegions, setIsProcessing, setStatusMessage],
  );

  const handleResetDetection = useCallback(async () => {
    if (!activeDocId) return;
    setIsProcessing(true);
    setRedetecting(true);
    setStatusMessage("Resetting detection — clearing all regions and rescanning…");
    try {
      pushUndo();
      const result = await resetDetection(activeDocId);
      setRegions(resolveAllOverlaps(result.regions));
      setStatusMessage(
        `Detection reset: cleared ${result.cleared} old regions, found ${result.total_regions} fresh`,
      );
    } catch (err) {
      setStatusMessage(`Reset detection failed: ${err}`);
    } finally {
      setIsProcessing(false);
      setRedetecting(false);
    }
  }, [activeDocId, pushUndo, setRegions, setIsProcessing, setStatusMessage]);

  return {
    copiedRegions,
    setCopiedRegions,
    showAutodetect,
    setShowAutodetect,
    redetecting,
    setRedetecting,
    handleRegionAction,
    handleRefreshRegion,
    handleClearRegion,
    handleHighlightAll,
    handleUpdateLabel,
    handleUpdateText,
    handlePasteRegions,
    handleBatchAction,
    handleResetAll,
    handleResetPage,
    handleAutodetect,
    handleResetDetection,
  };
}
