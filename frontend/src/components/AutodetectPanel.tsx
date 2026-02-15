/** Autodetect PII settings dropdown panel with Blacklist grid. */

import { useState, useCallback, useRef } from "react";
import { ScanSearch, SlidersHorizontal, Maximize2, Minimize2, X } from "lucide-react";
import { Z_TOP_DIALOG } from "../zIndex";
import BlacklistGrid, { type BlacklistAction, createEmptyGrid } from "./BlacklistGrid";

type TabKey = "patterns" | "blacklist" | "ai" | "deep";

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
}

const MIN_PANEL_W = 340;
const MIN_PANEL_H = 260;
const DEFAULT_PANEL_W = 420;
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
}: AutodetectPanelProps) {
  const [fuzziness, setFuzziness] = useState(0.55);
  const [scope, setScope] = useState<"page" | "all">("page");
  const [tab, setTab] = useState<TabKey>("patterns");
  const [showTabs, setShowTabs] = useState(false);
  const [regexTypes, setRegexTypes] = useState<Record<string, boolean>>({
    EMAIL: true, PHONE: true, SSN: true, CREDIT_CARD: true,
    IBAN: true, DATE: true, IP_ADDRESS: true, PASSPORT: true,
    DRIVER_LICENSE: true, ADDRESS: true,
  });
  const [nerTypes, setNerTypes] = useState<Record<string, boolean>>({
    PERSON: true, ORG: true, LOCATION: true, CUSTOM: false,
  });
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [toolbarBottom, setToolbarBottom] = useState(0);

  // Blacklist state
  const [blCells, setBlCells] = useState(() => createEmptyGrid());
  const [blAction, setBlAction] = useState<BlacklistAction>("none");
  const [blMatchStatus, setBlMatchStatus] = useState<Map<string, "matched" | "no-match" | "exists">>(new Map());

  // Resize state
  const [panelSize, setPanelSize] = useState({ w: DEFAULT_PANEL_W, h: DEFAULT_PANEL_H });
  const resizeRef = useRef<{ startX: number; startY: number; startW: number; startH: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const regexEnabled = Object.values(regexTypes).some(Boolean);
  const nerEnabled = Object.values(nerTypes).some(Boolean);
  const activeRegexTypes = Object.entries(regexTypes).filter(([, v]) => v).map(([k]) => k);
  const activeNerTypes = Object.entries(nerTypes).filter(([, v]) => v).map(([k]) => k);

  const handleRun = () => {
    const blacklistTerms = blCells.flat().map(c => c.trim()).filter(Boolean);
    onDetect({
      fuzziness,
      scope,
      regexEnabled,
      nerEnabled,
      llmEnabled,
      regexTypes: regexEnabled ? activeRegexTypes : [],
      nerTypes: nerEnabled ? activeNerTypes : [],
      blacklistTerms,
      blacklistAction: blAction,
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
  }, [panelSize]);

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
      } : {
        position: "absolute",
        top: "calc(100% + 8px)",
        left: 6,
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 8,
        boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
        zIndex: Z_TOP_DIALOG,
        width: showTabs ? panelSize.w : 340,
        maxWidth: `calc(100vw - ${rightOffset + 8}px)`,
        maxHeight: showTabs ? panelSize.h : undefined,
        display: "flex",
        flexDirection: "column" as const,
        overflow: "hidden",
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Scope tabs + window controls */}
      <div style={{
        display: "flex",
        gap: 2,
        borderBottom: "1px solid var(--border-color)",
        background: "rgba(0,0,0,0.15)",
        flexShrink: 0,
        padding: "0 10px",
        alignItems: "center",
      }}>
        {([
          { key: "page" as const, label: "Current page" },
          { key: "all" as const, label: "All pages" },
        ]).map(({ key, label }) => {
          const isActive = scope === key;
          return (
            <button
              key={key}
              onClick={() => setScope(key)}
              style={{
                padding: "8px 12px",
                fontSize: 12,
                fontWeight: isActive ? 600 : 400,
                color: isActive ? "var(--accent-primary)" : "var(--text-muted)",
                background: "transparent",
                border: "none",
                borderBottom: isActive ? "2px solid var(--accent-primary)" : "2px solid transparent",
                borderRadius: 0,
                cursor: "pointer",
                transition: "all 0.15s ease",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                whiteSpace: "nowrap",
              }}
            >
              {label}
            </button>
          );
        })}

        {/* Spacer + window controls */}
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", gap: 2, marginLeft: 8 }}>
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
            title={isMaximized ? "Restore" : "Maximize"}
          >
            {isMaximized ? <Minimize2 size={14} strokeWidth={2.2} /> : <Maximize2 size={14} strokeWidth={2.2} />}
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
            title="Close"
          >
            <X size={14} strokeWidth={2.2} />
          </button>
        </div>
      </div>

      {/* Filter button + Sensitivity slider on same line */}
      <div className="slider-row" style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
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
          title={showTabs ? "Hide detection settings" : "Show detection settings"}
        >
          <SlidersHorizontal size={16}  />
        </button>

        {/* Slider column */}
        <div style={{ flex: 1, minWidth: 0, marginRight: 12, marginLeft: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, color: "var(--text-secondary)", marginBottom: 3 }}>
            <span>Sensitivity</span>
            <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{fuzziness.toFixed(2)}</span>
          </div>
          <input
            type="range" min={0.1} max={0.95} step={0.05}
            value={fuzziness}
            onChange={(e) => setFuzziness(parseFloat(e.target.value))}
            style={{ width: "100%", accentColor: "var(--accent-primary)" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--text-muted)", marginTop: 1 }}>
            <span>More results</span>
            <span>Fewer results</span>
          </div>
        </div>
      </div>

      {/* Detection settings tabs (collapsible via gear) */}
      {showTabs && (<>
        {/* 4-tab bar: Patterns | Blacklist | AI Recognition | Deep Analysis */}
        <div style={{ display: "flex", gap: 2, borderBottom: "1px solid var(--border-color)", flexShrink: 0, marginTop: 6, padding: "0 10px" }}>
          {([
            { key: "patterns" as const, label: "Patterns", active: regexEnabled },
            { key: "blacklist" as const, label: "Blacklist", active: blCells.flat().some(c => c.trim()) },
            { key: "ai" as const, label: "AI Recognition", active: nerEnabled },
            { key: "deep" as const, label: "Deep Analysis", active: llmEnabled },
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
              Select which data patterns to look for
            </div>
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
            <div style={{ display: "flex", gap: 8, marginTop: 2 }}>
              <button className="btn-ghost btn-sm" style={{ fontSize: 11 }}
                onClick={() => setRegexTypes(prev => Object.fromEntries(Object.keys(prev).map(k => [k, true])))}
              >Select all</button>
              <button className="btn-ghost btn-sm" style={{ fontSize: 11 }}
                onClick={() => setRegexTypes(prev => Object.fromEntries(Object.keys(prev).map(k => [k, false])))}
              >Clear all</button>
            </div>
          </>)}

          {/* Blacklist tab */}
          {tab === "blacklist" && (
            <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
                Enter words or phrases to find and flag in the document. Paste from Excel or CSV supported.
              </div>
              <BlacklistGrid
                cells={blCells}
                onCellsChange={setBlCells}
                action={blAction}
                onActionChange={setBlAction}
                matchStatus={blMatchStatus}
              />
            </div>
          )}

          {/* AI Recognition tab (NER) */}
          {tab === "ai" && (<>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>
              AI-powered recognition of names and entities
            </div>
            {([
              { key: "PERSON", icon: "👤", label: "People's names" },
              { key: "ORG", icon: "🏢", label: "Organizations & companies" },
              { key: "LOCATION", icon: "📍", label: "Cities, countries & places" },
              { key: "CUSTOM", icon: "🔎", label: "Catch all (IDs, codes, misc. entities)" },
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
              background: "rgba(255,255,255,0.04)", borderRadius: 6,
              fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5,
            }}>
              Uses machine learning to find names, organizations and locations even when they don't follow a predictable format.
            </div>
          </>)}

          {/* Deep Analysis tab (LLM) */}
          {tab === "deep" && (<>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>
              Context-aware analysis using a language model
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
                  Enable deep analysis
                </label>
                {!llmReady && (
                  <div style={{
                    marginTop: 2, padding: "8px 10px",
                    background: "rgba(255,180,0,0.08)", borderRadius: 6, border: "1px solid rgba(255,180,0,0.15)",
                    fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5,
                  }}>
                    No LLM engine configured. Go to <strong style={{ color: "var(--text-secondary)" }}>Settings → LLM Engine</strong> to load a local model or connect a remote API.
                  </div>
                )}
                <div style={{
                  marginTop: 4, padding: "8px 10px",
                  background: "rgba(255,255,255,0.04)", borderRadius: 6,
                  fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5,
                }}>
                  Reads the full text to understand context and catch PII that patterns and AI names might miss. <strong style={{ color: "var(--text-secondary)" }}>Slowest method</strong> — best used after reviewing faster layers.
                </div>
              </>);
            })()}
          </>)}

        </div>
      </>)}

      {/* Run + Clear all buttons side by side */}
      <div style={{ padding: "10px 14px 14px", display: "flex", gap: 6, flexShrink: 0 }}>
        <button
          className="btn-primary"
          onClick={handleRun}
          disabled={isProcessing || (!regexEnabled && !nerEnabled && !llmEnabled && !blCells.flat().some(c => c.trim()))}
          style={{ whiteSpace: "nowrap" }}
        >
          <ScanSearch size={14} />
          {isProcessing ? "Detecting…" : `Run on ${scope === "page" ? `page ${activePage}` : "all pages"}`}
        </button>
        <button
          className="btn-ghost btn-sm"
          onClick={() => {
            onClose();
            if (scope === "page") { onResetPage(activePage); } else { onReset(); }
          }}
          disabled={isProcessing}
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
            padding: "6px 12px",
            whiteSpace: "nowrap",
          }}
          title={scope === "page" ? `Delete all regions on page ${activePage}` : "Delete all detected regions from the document"}
        >
          {scope === "page" ? `Clear page ${activePage}` : "Clear all pages"}
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
          title="Drag to resize"
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
