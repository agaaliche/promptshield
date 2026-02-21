/**
 * useDocumentExport — Anonymization workflow: sync-and-anonymize,
 * export dialog toggle.
 *
 * Extracted from DocumentViewer to reduce component size.
 */

import { useState, useCallback } from "react";
import {
  syncRegions,
  anonymizeDocument,
  getDownloadUrl,
} from "../api";
import { toErrorMessage } from "../errorUtils";
import type { PIIRegion } from "../types";

interface UseDocumentExportOpts {
  activeDocId: string | null;
  regions: PIIRegion[];
  setIsProcessing: (v: boolean) => void;
  setStatusMessage: (msg: string) => void;
}

export default function useDocumentExport(opts: UseDocumentExportOpts) {
  const {
    activeDocId, regions,
    setIsProcessing, setStatusMessage,
  } = opts;

  const [showExportDialog, setShowExportDialog] = useState(false);

  const handleAnonymize = useCallback(async () => {
    if (!activeDocId) return;

    setIsProcessing(true);
    setStatusMessage("Syncing regions & anonymizing...");
    try {
      await syncRegions(
        activeDocId,
        regions.map((r) => ({ id: r.id, action: r.action, bbox: r.bbox })),
      );
      const result = await anonymizeDocument(activeDocId);
      setStatusMessage(
        `Done! ${result.regions_removed} removed, ${result.tokens_created} tokenized`,
      );
      if (result.output_path) {
        window.open(getDownloadUrl(activeDocId, "pdf"), "_blank");
      }
    } catch (e: unknown) {
      setStatusMessage(`Anonymization failed: ${toErrorMessage(e)}`);
    } finally {
      setIsProcessing(false);
    }
  }, [activeDocId, setIsProcessing, setStatusMessage, regions]);

  return {
    showExportDialog,
    setShowExportDialog,
    handleAnonymize,
  };
}
