/**
 * useDocumentExport — Anonymization workflow: vault unlock, sync-and-anonymize,
 * export dialog toggle.
 *
 * Extracted from DocumentViewer to reduce component size.
 */

import { useState, useCallback } from "react";
import {
  syncRegions,
  anonymizeDocument,
  getDownloadUrl,
  unlockVault,
} from "../api";
import type { PIIRegion } from "../types";

interface UseDocumentExportOpts {
  activeDocId: string | null;
  regions: PIIRegion[];
  vaultUnlocked: boolean;
  setVaultUnlocked: (v: boolean) => void;
  setIsProcessing: (v: boolean) => void;
  setStatusMessage: (msg: string) => void;
}

export default function useDocumentExport(opts: UseDocumentExportOpts) {
  const {
    activeDocId, regions, vaultUnlocked,
    setVaultUnlocked, setIsProcessing, setStatusMessage,
  } = opts;

  const [showVaultPrompt, setShowVaultPrompt] = useState(false);
  const [vaultPass, setVaultPass] = useState("");
  const [vaultError, setVaultError] = useState("");
  const [showExportDialog, setShowExportDialog] = useState(false);

  const handleAnonymize = useCallback(async () => {
    if (!activeDocId) return;

    const hasTokenize = regions.some((r) => r.action === "TOKENIZE");
    if (hasTokenize && !vaultUnlocked) {
      setShowVaultPrompt(true);
      return;
    }

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
    } catch (e: any) {
      setStatusMessage(`Anonymization failed: ${e.message}`);
    } finally {
      setIsProcessing(false);
    }
  }, [activeDocId, setIsProcessing, setStatusMessage, regions, vaultUnlocked]);

  const handleVaultUnlockAndAnonymize = useCallback(async () => {
    if (!activeDocId) return;
    try {
      setVaultError("");
      await unlockVault(vaultPass);
      setVaultUnlocked(true);
      setShowVaultPrompt(false);
      setVaultPass("");
      setIsProcessing(true);
      setStatusMessage("Syncing regions & anonymizing...");
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
    } catch (e: any) {
      if (e.message?.includes("403") || e.message?.includes("passphrase")) {
        setVaultError("Invalid passphrase");
      } else {
        setStatusMessage(`Anonymization failed: ${e.message}`);
        setShowVaultPrompt(false);
      }
    } finally {
      setIsProcessing(false);
    }
  }, [activeDocId, vaultPass, setVaultUnlocked, setIsProcessing, setStatusMessage, regions]);

  return {
    showVaultPrompt,
    setShowVaultPrompt,
    vaultPass,
    setVaultPass,
    vaultError,
    setVaultError,
    showExportDialog,
    setShowExportDialog,
    handleAnonymize,
    handleVaultUnlockAndAnonymize,
  };
}
