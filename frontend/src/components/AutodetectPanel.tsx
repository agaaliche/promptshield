/** Autodetect PII settings dropdown panel with Blacklist grid. */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ScanSearch, SlidersHorizontal, Maximize2, Minimize2, X, Save, Trash2, Plus, Pin } from "../icons";
import { Z_TOP_DIALOG } from "../zIndex";
import BlacklistGrid, { type BlacklistAction } from "./BlacklistGrid";
import { createEmptyGrid } from "./blacklistUtils";
import type { PIIRegion, CustomPattern } from "../types";
import { fetchCustomPatterns } from "../api";

type TabKey = "patterns" | "blacklist" | "ai" | "deep";

/** Saved detection template stored in localStorage */
interface DetectionTemplate {
  name: string;
  fuzziness: number;
  regexTypes: Record<string, boolean>;
  nerTypes: Record<string, boolean>;
  llmEnabled: boolean;
  blCells: string[][];
  blAction: BlacklistAction;
  blFuzziness: number;
  customToggles?: Record<string, boolean>;
}

const TEMPLATES_KEY = "doc-anon-detection-templates";
const LAST_TEMPLATE_KEY = "doc-anon-last-template";

function loadTemplates(): DetectionTemplate[] {
  try {
    const raw = localStorage.getItem(TEMPLATES_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveTemplates(templates: DetectionTemplate[]) {
  localStorage.setItem(TEMPLATES_KEY, JSON.stringify(templates));
}

function loadLastTemplateName(): string {
  return localStorage.getItem(LAST_TEMPLATE_KEY) || "";
}

function saveLastTemplateName(name: string) {
  if (name) localStorage.setItem(LAST_TEMPLATE_KEY, name);
  else localStorage.removeItem(LAST_TEMPLATE_KEY);
}

const CUSTOM_TOGGLES_KEY = "detect-custom-toggles";

function loadCustomToggles(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(CUSTOM_TOGGLES_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveCustomTogglesLS(toggles: Record<string, boolean>) {
  localStorage.setItem(CUSTOM_TOGGLES_KEY, JSON.stringify(toggles));
}

const FILTER_CONFIG_KEY = "detect-filter-config";

interface FilterConfig {
  fuzziness: number;
  regexTypes: Record<string, boolean>;
  nerTypes: Record<string, boolean>;
  llmEnabled: boolean;
  blCells: string[][];
  blAction: BlacklistAction;
  blFuzziness: number;
}

const DEFAULT_REGEX_TYPES: Record<string, boolean> = {
  EMAIL: true, PHONE: true, SSN: true, CREDIT_CARD: true,
  IBAN: true, DATE: true, IP_ADDRESS: true, PASSPORT: true,
  DRIVER_LICENSE: true, ADDRESS: true,
};

const DEFAULT_NER_TYPES: Record<string, boolean> = {
  PERSON: true, ORG: true, LOCATION: true, CUSTOM: false,
};

function loadFilterConfig(): FilterConfig | null {
  try {
    const raw = localStorage.getItem(FILTER_CONFIG_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function saveFilterConfig(cfg: FilterConfig) {
  localStorage.setItem(FILTER_CONFIG_KEY, JSON.stringify(cfg));
}

interface AutodetectPanelProps {
  isProcessing: boolean;
  activePage: number;
  llmStatus: { loaded?: boolean; provider?: string; remote_api_url?: string } | null;
  onDetect: (opts: {
    fuzziness: number;
    scope: "page" | "all";
    regexEnabled: boolean;
    nerEnabled: boolean;
    llmEnabled: boolean;
    regexTypes: string[];
    nerTypes: string[];
    blacklistTerms: string[];
    blacklistAction: BlacklistAction;
    blacklistFuzziness: number;
  }) => void;
  onReset: () => void;
  onResetPage: (page: number) => void;
  onClose: () => void;
  /** Sidebar width (or collapsed width) so panel can't overlap it */
  rightOffset?: number;
  /** Left sidebar width so maximized panel starts after it */
  leftOffset?: number;
  /** Page navigator width so maximized panel stops before it */
  pageNavWidth?: number;
  /** Detected regions to highlight matched expressions */
  regions?: PIIRegion[];
}

const MIN_PANEL_W = 380;
const MIN_PANEL_H = 260;
const DEFAULT_PANEL_W = 480;
const DEFAULT_PANEL_H = 520;

export default function AutodetectPanel({
  isProcessing,
  activePage,
  llmStatus,
  onDetect,
  onReset,
  onResetPage,
  onClose,
  rightOffset = 0,
  leftOffset = 0,
  pageNavWidth = 0,
  regions = [],
}: AutodetectPanelProps) {
  const { t } = useTranslation();
  const savedFilterConfig = useRef(loadFilterConfig());
  const [fuzziness, setFuzziness] = useState(savedFilterConfig.current?.fuzziness ?? 0.55);
  const [scope, setScope] = useState<"page" | "all">("page");
  const [tab, setTab] = useState<TabKey>("patterns");
  const [showTabs, setShowTabs] = useState(false);
  const [regexTypes, setRegexTypes] = useState<Record<string, boolean>>(
    savedFilterConfig.current?.regexTypes ?? { ...DEFAULT_REGEX_TYPES },
  );
  const [nerTypes, setNerTypes] = useState<Record<string, boolean>>(
    savedFilterConfig.current?.nerTypes ?? { ...DEFAULT_NER_TYPES },
  );
  const [llmEnabled, setLlmEnabled] = useState(savedFilterConfig.current?.llmEnabled ?? false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [toolbarBottom, setToolbarBottom] = useState(0);

  // Templates
  const [templates, setTemplates] = useState<DetectionTemplate[]>(loadTemplates);
  const [templateName, setTemplateName] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [showSaveMenu, setShowSaveMenu] = useState(false);

  // Blacklist state
  const [blCells, setBlCells] = useState(() => savedFilterConfig.current?.blCells ?? createEmptyGrid());
  const [blAction, setBlAction] = useState<BlacklistAction>(savedFilterConfig.current?.blAction ?? "none");
  const [blFuzziness, setBlFuzziness] = useState(savedFilterConfig.current?.blFuzziness ?? 1.0);

  // Custom patterns from settings
  const [customPatterns, setCustomPatterns] = useState<CustomPattern[]>([]);
  const [customToggles, setCustomToggles] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetchCustomPatterns()
      .then(patterns => {
        const enabled = patterns.filter(p => p.enabled);
        setCustomPatterns(enabled);
        // Restore saved toggles; default new patterns to checked
        const saved = loadCustomToggles();
        setCustomToggles(Object.fromEntries(enabled.map(p => [p.id, saved[p.id] ?? true])));
      })
      .catch(() => {});
  }, []);

  // Compute match status: highlight expressions found in detected regions
  const blMatchStatus = useMemo(() => {
    const map = new Map<string, "matched" | "no-match" | "exists">();
    if (regions.length === 0) return map;
    
    // Collect all detected text (lowercase for case-insensitive matching)
    const detectedTexts = new Set(
      regions.map(r => r.text.toLowerCase().trim()).filter(Boolean)
    );
    
    // Check each cell: if its expression appears in detectedTexts, mark as matched
    for (let row = 0; row < blCells.length; row++) {
      for (let col = 0; col < blCells[row].length; col++) {
        const cell = blCells[row][col].trim();
        if (!cell) continue;
        const key = `${row},${col}`;
        const cellLower = cell.toLowerCase();
        // Check if any detected text contains this expression
        let found = false;
        for (const detected of detectedTexts) {
          if (detected.includes(cellLower)) {
            found = true;
            break;
          }
        }
        map.set(key, found ? "matched" : "no-match");
      }
    }
    return map;
  }, [regions, blCells]);

  // Restore last-used template on mount
  useEffect(() => {
    const lastName = loadLastTemplateName();
    if (!lastName) return;
    const tpl = templates.find(t => t.name === lastName);
    if (!tpl) return;
    setSelectedTemplate(lastName);
    setFuzziness(tpl.fuzziness);
    setRegexTypes(tpl.regexTypes);
    setNerTypes(tpl.nerTypes);
    setLlmEnabled(tpl.llmEnabled);
    setBlCells(tpl.blCells);
    setBlAction(tpl.blAction);
    setBlFuzziness(tpl.blFuzziness ?? 1.0);
    if (tpl.customToggles) { setCustomToggles(tpl.customToggles); saveCustomTogglesLS(tpl.customToggles); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // mount-only

  // Persist last-used template name
  useEffect(() => {
    saveLastTemplateName(selectedTemplate);
  }, [selectedTemplate]);

  // Auto-save option changes back to the selected template
  useEffect(() => {
    if (!selectedTemplate) return;
    const tpl: DetectionTemplate = {
      name: selectedTemplate,
      fuzziness,
      regexTypes: { ...regexTypes },
      nerTypes: { ...nerTypes },
      llmEnabled,
      blCells: blCells.map(r => [...r]),
      blAction,
      blFuzziness,
      customToggles: { ...customToggles },
    };
    setTemplates(prev => {
      const updated = prev.map(t => t.name === selectedTemplate ? tpl : t);
      saveTemplates(updated);
      return updated;
    });
  }, [selectedTemplate, fuzziness, regexTypes, nerTypes, llmEnabled, blCells, blAction, blFuzziness, customToggles]);

  // Persist filter config to localStorage when no template is selected
  useEffect(() => {
    if (selectedTemplate) return;
    saveFilterConfig({ fuzziness, regexTypes, nerTypes, llmEnabled, blCells, blAction, blFuzziness });
  }, [selectedTemplate, fuzziness, regexTypes, nerTypes, llmEnabled, blCells, blAction, blFuzziness]);

  // Resize state
  const [panelSize, setPanelSize] = useState({ w: DEFAULT_PANEL_W, h: DEFAULT_PANEL_H });
  const resizeRef = useRef<{ startX: number; startY: number; startW: number; startH: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Drag state
  const [dragPos, setDragPos] = useState<{ x: number; y: number } | null>(null);
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    if (isMaximized) return;
    // Don't start drag on window-control buttons (maximize/close)
    if ((e.target as HTMLElement).closest("[data-nodrag]")) return;
    e.preventDefault();
    const rect = panelRef.current?.getBoundingClientRect();
    if (!rect) return;
    const origX = dragPos?.x ?? rect.left;
    const origY = dragPos?.y ?? rect.top;
    // Top boundary = bottom of the document viewer toolbar (panel's parent)
    const toolbar = panelRef.current?.parentElement as HTMLElement | null;
    const topBound = toolbar ? toolbar.getBoundingClientRect().bottom : 48;
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX, origY };
    const PAD = 8;
    const onMove = (me: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = me.clientX - dragRef.current.startX;
      const dy = me.clientY - dragRef.current.startY;
      const pw = rect.width;
      const ph = rect.height;
      setDragPos({
        x: Math.max(leftOffset + PAD, Math.min(window.innerWidth - rightOffset - pageNavWidth - pw - PAD, dragRef.current.origX + dx)),
        y: Math.max(topBound + PAD, Math.min(window.innerHeight - ph - PAD, dragRef.current.origY + dy)),
      });
    };
    const onUp = () => {
      dragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [isMaximized, dragPos, leftOffset, rightOffset, pageNavWidth]);

  // Re-clamp undocked panel when sidebar/nav layout changes
  useEffect(() => {
    if (!dragPos || isMaximized) return;
    const el = panelRef.current;
    if (!el) return;
    const PAD = 8;
    const pw = el.offsetWidth;
    const ph = el.offsetHeight;
    const minX = leftOffset + PAD;
    const maxX = window.innerWidth - rightOffset - pageNavWidth - pw - PAD;
    const maxY = window.innerHeight - ph - PAD;
    let { x, y } = dragPos;
    let changed = false;
    if (x < minX) { x = minX; changed = true; }
    if (x > maxX) { x = Math.max(minX, maxX); changed = true; }
    if (y > maxY) { y = Math.max(0, maxY); changed = true; }
    if (changed) setDragPos({ x, y });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rightOffset, leftOffset, pageNavWidth]);

  const regexEnabled = Object.values(regexTypes).some(Boolean) || Object.values(customToggles).some(Boolean);
  const nerEnabled = Object.values(nerTypes).some(Boolean);
  const activeRegexTypes = Object.entries(regexTypes).filter(([, v]) => v).map(([k]) => k);
  const activeNerTypes = Object.entries(nerTypes).filter(([, v]) => v).map(([k]) => k);

  // Include PII types from active custom patterns
  const activeCustomPiiTypes = customPatterns
    .filter(p => customToggles[p.id])
    .map(p => p.pii_type)
    .filter(t => !activeRegexTypes.includes(t));
  const allActiveRegexTypes = [...activeRegexTypes, ...activeCustomPiiTypes];

  const handleRun = () => {
    const blacklistTerms = blCells.flat().map(c => c.trim()).filter(Boolean);
    onDetect({
      fuzziness,
      scope,
      regexEnabled,
      nerEnabled,
      llmEnabled,
      regexTypes: regexEnabled ? allActiveRegexTypes : [],
      nerTypes: nerEnabled ? activeNerTypes : [],
      blacklistTerms,
      blacklistAction: blAction,
      blacklistFuzziness: blFuzziness,
    });
    onClose();
  };

  // Resize handlers
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const panelLeft = panelRef.current?.getBoundingClientRect().left ?? 0;
    resizeRef.current = { startX: e.clientX, startY: e.clientY, startW: panelSize.w, startH: panelSize.h };
    const onMove = (me: MouseEvent) => {
      if (!resizeRef.current) return;
      const dx = me.clientX - resizeRef.current.startX;
      const dy = me.clientY - resizeRef.current.startY;
      const maxW = window.innerWidth - panelLeft - rightOffset - 8;
      setPanelSize({
        w: Math.min(maxW, Math.max(MIN_PANEL_W, resizeRef.current.startW + dx)),
        h: Math.max(MIN_PANEL_H, resizeRef.current.startH + dy),
      });
    };
    const onUp = () => {
      resizeRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [panelSize, rightOffset]);

  return (
    <div
      ref={panelRef}
      style={isMaximized ? {
        position: "fixed",
        top: toolbarBottom,
        left: leftOffset,
        right: rightOffset + pageNavWidth,
        bottom: 0,
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 0,
        boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
        zIndex: Z_TOP_DIALOG,
        display: "flex",
        flexDirection: "column" as const,
        overflow: "hidden",
      } : dragPos ? {
        position: "fixed",
        top: dragPos.y,
        left: dragPos.x,
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 8,
        boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
        zIndex: Z_TOP_DIALOG,
        width: showTabs ? panelSize.w : 380,
        maxWidth: `calc(100vw - ${rightOffset + 8}px)`,
        maxHeight: showTabs ? panelSize.h : undefined,
        display: "flex",
        flexDirection: "column" as const,
        overflow: "hidden",
      } : {
        position: "absolute",
        top: "calc(100% + 8px)",
        left: 6,
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 8,
        boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
        zIndex: Z_TOP_DIALOG,
        width: showTabs ? panelSize.w : 380,
        maxWidth: `calc(100vw - ${rightOffset + 8}px)`,
        maxHeight: showTabs ? panelSize.h : undefined,
        display: "flex",
        flexDirection: "column" as const,
        overflow: "hidden",
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Scope tabs + window controls — drag handle */}
      <div
        onMouseDown={handleDragStart}
        style={{
          display: "flex",
          gap: 2,
          borderBottom: "1px solid var(--border-color)",
          background: "rgba(0,0,0,0.15)",
          flexShrink: 0,
          padding: "0 10px",
          alignItems: "center",
          cursor: isMaximized ? "default" : "pointer",
          userSelect: "none",
        }}>
        {/* Dock button — left side, only when undocked */}
        {dragPos && (
          <button
            data-nodrag
            onClick={() => setDragPos(null)}
            style={{
              width: 26, height: 26,
              padding: 0,
              background: "transparent",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--text-secondary)",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.1)"; e.currentTarget.style.color = "var(--text-primary)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
            title={t("detection.dockToToolbar")}
          >
            <Pin size={14} strokeWidth={2.2} variant="light" />
          </button>
        )}
        {/* Spacer + window controls */}
        <div style={{ flex: 1 }} />
        <div data-nodrag style={{ display: "flex", gap: 2, marginLeft: 8 }}>
          <button
            onClick={() => {
              if (!isMaximized && panelRef.current) {
                const parent = panelRef.current.offsetParent as HTMLElement | null;
                setToolbarBottom(parent ? parent.getBoundingClientRect().bottom : 48);
                if (!showTabs) setShowTabs(true);
              }
              setIsMaximized(prev => !prev);
            }}
            style={{
              width: 26, height: 26,
              padding: 0,
              background: "transparent",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--text-secondary)",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.1)"; e.currentTarget.style.color = "var(--text-primary)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
            title={isMaximized ? t("detection.restore") : t("detection.maximize")}
          >
            {isMaximized ? <Minimize2 size={14} strokeWidth={2.2} variant="light" /> : <Maximize2 size={14} strokeWidth={2.2} variant="light" />}
          </button>
          <button
            onClick={onClose}
            style={{
              width: 26, height: 26,
              padding: 0,
              background: "transparent",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--text-secondary)",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(220,38,38,0.25)"; e.currentTarget.style.color = "#f87171"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
            title={t("common.close")}
          >
            <X size={14} strokeWidth={2.2} variant="light" />
          </button>
        </div>
      </div>

      {/* Filter button + Sensitivity slider on same line */}
      <div className="slider-row" style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 20 }}>
        {/* Filter adjustment button — top-left */}
        <button
          onClick={() => {
            const willHide = showTabs;
            setShowTabs(prev => !prev);
            if (willHide && isMaximized) setIsMaximized(false);
          }}
          style={{
            width: 32,
            height: 32,
            flexShrink: 0,
            marginTop: 1,
            marginRight: 4,
            background: showTabs ? "rgba(var(--accent-primary-rgb, 59,130,246), 0.12)" : "rgba(255,255,255,0.04)",
            border: showTabs ? "1px solid var(--accent-primary)" : "1px solid var(--border-color)",
            borderRadius: 6,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: showTabs ? "var(--accent-primary)" : "var(--text-muted)",
            transition: "all 0.15s ease",
            padding: 0,
          }}
          title={showTabs ? t("detection.hideSettings") : t("detection.showSettings")}
        >
          <SlidersHorizontal size={16} variant="light" />
        </button>

        {/* Slider column */}
        <div style={{ flex: 1, minWidth: 0, marginRight: 12, marginLeft: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, color: "var(--text-secondary)", marginBottom: 3 }}>
            <span>{t("detection.sensitivity")}</span>
            <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{fuzziness.toFixed(2)}</span>
          </div>
          <input
            type="range" min={0.1} max={0.95} step={0.05}
            value={fuzziness}
            onChange={(e) => setFuzziness(parseFloat(e.target.value))}
            style={{ width: "100%", accentColor: "var(--accent-primary)" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--text-muted)", marginTop: 1 }}>
            <span>{t("detection.moreResults")}</span>
            <span>{t("detection.fewerResults")}</span>
          </div>
        </div>
      </div>

      {/* Saved templates — selector (when templates exist) or inline save box (when empty) */}
      {templates.length > 0 ? (
        <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 14px", marginTop: 6, marginBottom: 12, position: "relative" }}>
          <select
            value={selectedTemplate}
            onChange={(e) => {
              const name = e.target.value;
              setSelectedTemplate(name);
              const tpl = templates.find(t => t.name === name);
              if (!tpl) return;
              setFuzziness(tpl.fuzziness);
              setRegexTypes(tpl.regexTypes);
              setNerTypes(tpl.nerTypes);
              setLlmEnabled(tpl.llmEnabled);
              setBlCells(tpl.blCells);
              setBlAction(tpl.blAction);
              setBlFuzziness(tpl.blFuzziness ?? 1.0);
              if (tpl.customToggles) { setCustomToggles(tpl.customToggles); saveCustomTogglesLS(tpl.customToggles); }
              if (!showTabs) setShowTabs(true);
            }}
            style={{
              flex: 1,
              height: 28,
              fontSize: 11,
              background: "var(--bg-surface)",
              color: "var(--text-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 4,
              padding: "0 6px",
              cursor: "pointer",
            }}
          >
            <option value="" disabled>{t("detection.loadTemplate")}</option>
            {templates.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
          </select>
          {selectedTemplate && (
            <button
              title={t("detection.deleteTemplate")}
              onClick={() => {
                const updated = templates.filter(t => t.name !== selectedTemplate);
                saveTemplates(updated);
                setTemplates(updated);
                setSelectedTemplate("");
              }}
              style={{
                width: 28, height: 28, padding: 0,
                background: "transparent",
                border: "1px solid var(--border-color)",
                borderRadius: 4,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--text-muted)",
                transition: "all 0.15s ease",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(220,38,38,0.15)"; e.currentTarget.style.color = "#f87171"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)"; }}
            >
              <Trash2 size={13} variant="light" />
            </button>
          )}
          {/* Ellipsis (save-as) button */}
          <button
            title={t("detection.saveAsTemplate")}
            onClick={() => setShowSaveMenu(v => !v)}
            style={{
              width: 28, height: 28, padding: 0,
              marginLeft: selectedTemplate ? 16 : 0,
              background: showSaveMenu ? "var(--bg-surface)" : "transparent",
              border: "1px solid var(--border-color)",
              borderRadius: 4,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--text-muted)",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={(e) => { if (!showSaveMenu) e.currentTarget.style.background = "var(--bg-surface)"; }}
            onMouseLeave={(e) => { if (!showSaveMenu) e.currentTarget.style.background = "transparent"; }}
          >
            <Plus size={14} variant="light" />
          </button>
          {/* Save-as dropdown menu */}
          {showSaveMenu && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                left: 14,
                right: 14,
                marginTop: 4,
                background: "var(--bg-surface)",
                border: "1px solid var(--border-color)",
                borderRadius: 6,
                boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
                padding: 8,
                display: "flex",
                alignItems: "center",
                gap: 6,
                zIndex: 10,
              }}
            >
              <input
                autoFocus
                type="text"
                placeholder={t("detection.templateNamePlaceholder")}
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") document.getElementById("save-tpl-btn")?.click();
                  if (e.key === "Escape") setShowSaveMenu(false);
                }}
                style={{
                  flex: 1,
                  height: 28,
                  fontSize: 11,
                  background: "var(--bg-secondary)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-color)",
                  borderRadius: 4,
                  padding: "0 8px",
                }}
              />
              <button
                id="save-tpl-btn"
                disabled={!templateName.trim()}
                onClick={() => {
                  const name = templateName.trim();
                  if (!name) return;
                  const tpl: DetectionTemplate = {
                    name,
                    fuzziness,
                    regexTypes: { ...regexTypes },
                    nerTypes: { ...nerTypes },
                    llmEnabled,
                    blCells: blCells.map(r => [...r]),
                    blAction,
                    customToggles: { ...customToggles },
                  };
                  const updated = [...templates.filter(t => t.name !== name), tpl];
                  saveTemplates(updated);
                  setTemplates(updated);
                  setSelectedTemplate(name);
                  setTemplateName("");
                  setShowSaveMenu(false);
                }}
                title={t("detection.saveTemplateTitle")}
                style={{
                  height: 28,
                  padding: "0 10px",
                  fontSize: 11,
                  fontWeight: 500,
                  background: "var(--accent-primary)",
                  color: "white",
                  border: "none",
                  borderRadius: 4,
                  cursor: templateName.trim() ? "pointer" : "not-allowed",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  opacity: templateName.trim() ? 1 : 0.5,
                }}
              >
                <Save size={12} variant="light" /> {t("common.save")}
              </button>
            </div>
          )}
        </div>
      ) : showTabs ? (
        <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 14px", marginTop: 6, marginBottom: 12 }}>
          <input
            type="text"
            placeholder={t("detection.templateNamePlaceholder")}
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const name = templateName.trim();
                if (!name) return;
                const tpl: DetectionTemplate = {
                  name,
                  fuzziness,
                  regexTypes: { ...regexTypes },
                  nerTypes: { ...nerTypes },
                  llmEnabled,
                  blCells: blCells.map(r => [...r]),
                  blAction,
                  customToggles: { ...customToggles },
                };
                saveTemplates([tpl]);
                setTemplates([tpl]);
                setSelectedTemplate(name);
                setTemplateName("");
              }
            }}
            style={{
              flex: 1,
              height: 28,
              fontSize: 11,
              background: "var(--bg-surface)",
              color: "var(--text-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 4,
              padding: "0 8px",
            }}
          />
          <button
            disabled={!templateName.trim()}
            onClick={() => {
              const name = templateName.trim();
              if (!name) return;
              const tpl: DetectionTemplate = {
                name,
                fuzziness,
                regexTypes: { ...regexTypes },
                nerTypes: { ...nerTypes },
                llmEnabled,
                blCells: blCells.map(r => [...r]),
                blAction,
                customToggles: { ...customToggles },
              };
              saveTemplates([tpl]);
              setTemplates([tpl]);
              setSelectedTemplate(name);
              setTemplateName("");
            }}
            title={t("detection.saveTemplateTitle")}
            style={{
              height: 28,
              padding: "0 10px",
              fontSize: 11,
              fontWeight: 500,
              background: "var(--accent-primary)",
              color: "white",
              border: "none",
              borderRadius: 4,
              cursor: templateName.trim() ? "pointer" : "not-allowed",
              display: "flex",
              alignItems: "center",
              gap: 4,
              opacity: templateName.trim() ? 1 : 0.5,
            }}
          >
            <Save size={12} variant="light" /> {t("common.save")}
          </button>
        </div>
      ) : null}

      {/* Detection settings tabs (collapsible via gear) */}
      {showTabs && (
      <div style={{ padding: 6, margin: 12, background: "rgba(0,0,0,0.15)", borderRadius: 6 }}>
        {/* 4-tab bar: Patterns | Expressions | AI Recognition | Deep Analysis */}
        <div style={{ display: "flex", gap: 2, borderBottom: "1px solid var(--border-color)", flexShrink: 0, padding: "0 10px" }}>
          {([
            { key: "patterns" as const, label: t("detection.tabPatterns"), active: regexEnabled },
            { key: "blacklist" as const, label: t("detection.tabExpressions"), active: blCells.flat().some(c => c.trim()) },
            { key: "ai" as const, label: t("detection.tabAI"), active: nerEnabled },
            { key: "deep" as const, label: t("detection.tabDeepAnalysis"), active: llmEnabled },
          ] as const).map(({ key, label, active }) => {
            const isSel = tab === key;
            return (
              <button
                key={key}
                onClick={() => setTab(key)}
                style={{
                  padding: "9px 10px",
                  fontSize: 11,
                  fontWeight: isSel ? 600 : 400,
                  color: isSel ? "var(--accent-primary)" : active ? "var(--text-secondary)" : "var(--text-muted)",
                  background: "transparent",
                  border: "none",
                  borderBottom: isSel ? "2px solid var(--accent-primary)" : "2px solid transparent",
                  borderRadius: 0,
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  opacity: active ? 1 : 0.5,
                  whiteSpace: "nowrap",
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Tab content */}
        <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10, flex: 1, overflowY: tab === "blacklist" ? "hidden" : "auto", minHeight: 0 }}>

          {/* Patterns tab (regex) */}
          {tab === "patterns" && (<>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>
              {t("detection.selectPatterns")}
            </div>
            {/* Select all header checkbox */}
            {(() => {
              const allKeys = ["EMAIL","PHONE","SSN","CREDIT_CARD","IBAN","DATE","IP_ADDRESS","PASSPORT","DRIVER_LICENSE","ADDRESS"] as const;
              const allChecked = allKeys.every(k => regexTypes[k]);
              const noneChecked = allKeys.every(k => !regexTypes[k]);
              return (
                <label style={{
                  display: "flex", alignItems: "center", gap: 8,
                  fontSize: 12, fontWeight: 600, color: "var(--text-primary)", cursor: "pointer",
                  padding: "4px 0", borderBottom: "1px solid var(--border-color)", marginBottom: 2,
                }}>
                  <input
                    type="checkbox"
                    checked={allChecked}
                    ref={el => { if (el) el.indeterminate = !allChecked && !noneChecked; }}
                    onChange={() => {
                      const val = !allChecked;
                      setRegexTypes(prev => Object.fromEntries(Object.keys(prev).map(k => [k, val])) as typeof prev);
                    }}
                    style={{ accentColor: "var(--accent-primary)", width: 15, height: 15 }}
                  />
                  {t("common.selectAll")}
                </label>
              );
            })()}
            {([
              { key: "EMAIL", icon: "✉", label: "Email addresses" },
              { key: "PHONE", icon: "📞", label: "Phone numbers" },
              { key: "SSN", icon: "🆔", label: "Social Security / National ID" },
              { key: "CREDIT_CARD", icon: "💳", label: "Credit card numbers" },
              { key: "IBAN", icon: "🏦", label: "Bank accounts (IBAN)" },
              { key: "DATE", icon: "📅", label: "Dates of birth" },
              { key: "IP_ADDRESS", icon: "🌐", label: "IP addresses" },
              { key: "PASSPORT", icon: "🛂", label: "Passport numbers" },
              { key: "DRIVER_LICENSE", icon: "🪪", label: "Driver license numbers" },
              { key: "ADDRESS", icon: "🏠", label: "Physical addresses" },
            ] as const).map(({ key, icon, label }) => (
              <label key={key} style={{
                display: "flex", alignItems: "center", gap: 8,
                fontSize: 13, color: "var(--text-primary)", cursor: "pointer",
                padding: "4px 0",
              }}>
                <input
                  type="checkbox"
                  checked={regexTypes[key]}
                  onChange={(e) => setRegexTypes(prev => ({ ...prev, [key]: e.target.checked }))}
                  style={{ accentColor: "var(--accent-primary)", width: 15, height: 15 }}
                />
                <span style={{ fontSize: 15, width: 22, textAlign: "center" }}>{icon}</span>
                {label}
              </label>
            ))}

            {/* Custom patterns from Settings */}
            {customPatterns.length > 0 && (
              <>
                <div style={{
                  fontSize: 11, fontWeight: 600, color: "var(--text-muted)",
                  marginTop: 10, paddingTop: 8,
                  borderTop: "1px solid var(--border-color)",
                  display: "flex", alignItems: "center", gap: 6,
                }}>
                  🎯 {t("detection.customPatterns")}
                  <span style={{
                    fontSize: 10, color: "var(--text-muted)", fontWeight: 400,
                    marginLeft: "auto",
                  }}>
                    {t("detection.fromSettings")}
                  </span>
                </div>
                {customPatterns.map(cp => (
                  <label key={cp.id} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    fontSize: 13, color: "var(--text-primary)", cursor: "pointer",
                    padding: "4px 0",
                  }}>
                    <input
                      type="checkbox"
                      checked={customToggles[cp.id] ?? true}
                      onChange={(e) => setCustomToggles(prev => { const next = { ...prev, [cp.id]: e.target.checked }; saveCustomTogglesLS(next); return next; })}
                      style={{ accentColor: "var(--accent-primary)", width: 15, height: 15 }}
                    />
                    <span style={{ fontSize: 15, width: 22, textAlign: "center" }}>🎯</span>
                    <span style={{ flex: 1 }}>{cp.name}</span>
                    <span style={{
                      fontSize: 10, padding: "1px 6px",
                      background: "rgba(156, 39, 176, 0.15)", color: "#ce93d8",
                      borderRadius: 3, fontWeight: 500,
                    }}>
                      {cp.pii_type}
                    </span>
                  </label>
                ))}
              </>
            )}
          </>)}

          {/* Blacklist tab */}
          {tab === "blacklist" && (
            <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
                {t("detection.expressionsHint")}
              </div>
              <BlacklistGrid
                cells={blCells}
                onCellsChange={setBlCells}
                action={blAction}
                onActionChange={setBlAction}
                fuzziness={blFuzziness}
                onFuzzinessChange={setBlFuzziness}
                matchStatus={blMatchStatus}
              />
            </div>
          )}

          {/* AI Recognition tab (NER) */}
          {tab === "ai" && (<>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>
              {t("detection.aiTitle")}
            </div>
            {([
              { key: "PERSON", icon: "👤", label: t("detection.aiPeople") },
              { key: "ORG", icon: "🏢", label: t("detection.aiOrgs") },
              { key: "LOCATION", icon: "📍", label: t("detection.aiPlaces") },
              { key: "CUSTOM", icon: "🔎", label: t("detection.aiCatchAll") },
            ] as const).map(({ key, icon, label }) => (
              <label key={key} style={{
                display: "flex", alignItems: "center", gap: 8,
                fontSize: 13, color: "var(--text-primary)", cursor: "pointer",
                padding: "6px 0",
              }}>
                <input
                  type="checkbox"
                  checked={nerTypes[key]}
                  onChange={(e) => setNerTypes(prev => ({ ...prev, [key]: e.target.checked }))}
                  style={{ accentColor: "var(--accent-primary)", width: 15, height: 15 }}
                />
                <span style={{ fontSize: 15, width: 22, textAlign: "center" }}>{icon}</span>
                {label}
              </label>
            ))}
            <div style={{
              marginTop: 4, padding: "8px 10px",
              borderRadius: 6,
              fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5,
            }}>
              {t("detection.aiHint")}
            </div>
          </>)}

          {/* Deep Analysis tab (LLM) */}
          {tab === "deep" && (<>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>
              {t("detection.deepTitle")}
            </div>
            {(() => {
              const llmReady = llmStatus?.loaded === true || (llmStatus?.provider === "remote" && !!llmStatus?.remote_api_url);
              return (<>
                <label style={{
                  display: "flex", alignItems: "center", gap: 8,
                  fontSize: 13, color: llmReady ? "var(--text-primary)" : "var(--text-muted)", cursor: llmReady ? "pointer" : "not-allowed",
                  padding: "6px 0",
                  opacity: llmReady ? 1 : 0.5,
                }}>
                  <input
                    type="checkbox"
                    checked={llmEnabled && llmReady}
                    onChange={(e) => setLlmEnabled(e.target.checked)}
                    disabled={!llmReady}
                    style={{ accentColor: "var(--accent-primary)", width: 15, height: 15 }}
                  />
                  <span style={{ fontSize: 15, width: 22, textAlign: "center" }}>🧠</span>
                  {t("detection.deepEnable")}
                </label>
                {!llmReady && (
                  <div style={{
                    marginTop: 2, padding: "8px 10px",
                    background: "rgba(255,180,0,0.08)", borderRadius: 6, border: "1px solid rgba(255,180,0,0.15)",
                    fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5,
                  }}>
                    {t("detection.deepNoLLM")}
                  </div>
                )}
                <div style={{
                  marginTop: 4, padding: "8px 10px",
                  background: "rgba(255,255,255,0.04)", borderRadius: 6,
                  fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5,
                }}>
                  {t("detection.deepHint")}
                </div>
              </>);
            })()}
          </>)}

        </div>
      </div>)}

      {/* Bottom toolbar — scope radio left, detect right */}
      <div style={{
        marginTop: 12,
        padding: "8px 14px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        flexShrink: 0,
        borderTop: "1px solid var(--border-color)",
        background: "rgba(0,0,0,0.08)",
      }}>
        {/* Scope radio group — left */}
        <div style={{ display: "flex", gap: 10 }}>
          {([
            { key: "page" as const, label: t("detection.scopePage", { n: activePage }) },
            { key: "all" as const, label: t("detection.scopeAllPages") },
          ]).map(({ key, label }) => (
            <label
              key={key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                fontSize: 11,
                color: scope === key ? "var(--text-primary)" : "var(--text-muted)",
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              <input
                type="radio"
                name="detect-scope"
                checked={scope === key}
                onChange={() => setScope(key)}
                style={{ accentColor: "var(--accent-primary)", margin: 0 }}
              />
              {label}
            </label>
          ))}
        </div>

        <div style={{ flex: 1 }} />

        {/* Detect — right */}
        <button
          className="btn-primary"
          onClick={handleRun}
          disabled={isProcessing || (!regexEnabled && !nerEnabled && !llmEnabled && !blCells.flat().some(c => c.trim()))}
          style={{ whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 6, marginRight: 4 }}
        >
          <ScanSearch size={14} variant="light" />
                    {isProcessing ? t("detection.detecting") : t("common.detect")}
        </button>
      </div>

      {/* Resize handle (bottom-right corner) */}
      {showTabs && !isMaximized && (
        <div
          onMouseDown={handleResizeStart}
          style={{
            position: "absolute",
            bottom: 0,
            right: 0,
            width: 20,
            height: 20,
            cursor: "nwse-resize",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            userSelect: "none",
          }}
          title={t("detection.dragToResize")}
        >
          <svg width="14" height="14" viewBox="0 0 10 10" style={{ opacity: 0.85 }}>
            <line x1="9" y1="1" x2="1" y2="9" stroke="var(--text-muted)" strokeWidth="1.2" />
            <line x1="9" y1="4.5" x2="4.5" y2="9" stroke="var(--text-muted)" strokeWidth="1.2" />
            <line x1="9" y1="8" x2="8" y2="9" stroke="var(--text-muted)" strokeWidth="1.2" />
          </svg>
        </div>
      )}
    </div>
  );
}
