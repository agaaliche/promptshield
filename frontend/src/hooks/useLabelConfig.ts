/**
 * Hook that owns PII-label configuration state, localStorage cache,
 * and backend sync.
 */
import { useState, useEffect, useMemo, useCallback } from "react";
import type { PIILabelEntry, PIIRegion } from "../types";
import { loadLabelConfig, cacheLabelConfig, ensureBuiltinLabels } from "../types";
import { logError } from "../api";

interface UseLabelConfigResult {
  labelConfig: PIILabelEntry[];
  visibleLabels: PIILabelEntry[];
  frequentLabels: PIILabelEntry[];
  otherLabels: PIILabelEntry[];
  usedLabels: Set<string>;
  updateLabelConfig: (updater: (prev: PIILabelEntry[]) => PIILabelEntry[]) => void;
  /** Type-picker edit mode */
  typePickerEditMode: boolean;
  setTypePickerEditMode: (v: boolean) => void;
  typePickerNewLabel: string;
  setTypePickerNewLabel: (v: string) => void;
}

export default function useLabelConfig(regions: PIIRegion[]): UseLabelConfigResult {
  const [labelConfig, setLabelConfig] = useState<PIILabelEntry[]>(() => loadLabelConfig());
  const [typePickerEditMode, setTypePickerEditMode] = useState(false);
  const [typePickerNewLabel, setTypePickerNewLabel] = useState("");

  // Load label config from backend on mount (overrides localStorage cache)
  useEffect(() => {
    import("../api").then(({ fetchLabelConfig }) =>
      fetchLabelConfig().then((remote) => {
        const merged = ensureBuiltinLabels(remote);
        setLabelConfig(merged);
        cacheLabelConfig(merged);
      })
    ).catch(logError("fetch-labels")); // fall back to localStorage cache on error
  }, []);

  const visibleLabels = useMemo(() => labelConfig.filter((e) => !e.hidden), [labelConfig]);
  const frequentLabels = useMemo(() => visibleLabels.filter((e) => e.frequent), [visibleLabels]);
  const otherLabels = useMemo(() => visibleLabels.filter((e) => !e.frequent), [visibleLabels]);

  const usedLabels = useMemo(() => {
    const s = new Set<string>();
    for (const r of regions) s.add(r.pii_type);
    return s;
  }, [regions]);

  const updateLabelConfig = useCallback(
    (updater: (prev: PIILabelEntry[]) => PIILabelEntry[]) => {
      setLabelConfig((prev) => {
        const next = updater(prev);
        cacheLabelConfig(next);
        import("../api").then(({ saveLabelConfigAPI }) => saveLabelConfigAPI(next)).catch(logError("save-labels"));
        return next;
      });
    },
    [],
  );

  return {
    labelConfig,
    visibleLabels,
    frequentLabels,
    otherLabels,
    usedLabels,
    updateLabelConfig,
    typePickerEditMode,
    setTypePickerEditMode,
    typePickerNewLabel,
    setTypePickerNewLabel,
  };
}
