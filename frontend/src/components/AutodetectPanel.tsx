/** Autodetect PII settings dropdown panel. */

import { useState } from "react";
import { ScanSearch } from "lucide-react";
import { Z_TOP_DIALOG } from "../zIndex";

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
  }) => void;
  onReset: () => void;
  onClose: () => void;
}

export default function AutodetectPanel({
  isProcessing,
  activePage,
  llmStatus,
  onDetect,
  onReset,
  onClose,
}: AutodetectPanelProps) {
  const [fuzziness, setFuzziness] = useState(0.55);
  const [scope, setScope] = useState<"page" | "all">("page");
  const [tab, setTab] = useState<"patterns" | "ai" | "deep">("patterns");
  const [showDataTypes, setShowDataTypes] = useState(false);
  const [regexTypes, setRegexTypes] = useState<Record<string, boolean>>({
    EMAIL: true, PHONE: true, SSN: true, CREDIT_CARD: true,
    IBAN: true, DATE: true, IP_ADDRESS: true, PASSPORT: true,
    DRIVER_LICENSE: true, ADDRESS: true,
  });
  const [nerTypes, setNerTypes] = useState<Record<string, boolean>>({
    PERSON: true, ORG: true, LOCATION: true, CUSTOM: false,
  });
  const [llmEnabled, setLlmEnabled] = useState(false);

  const regexEnabled = Object.values(regexTypes).some(Boolean);
  const nerEnabled = Object.values(nerTypes).some(Boolean);
  const activeRegexTypes = Object.entries(regexTypes).filter(([, v]) => v).map(([k]) => k);
  const activeNerTypes = Object.entries(nerTypes).filter(([, v]) => v).map(([k]) => k);

  const handleRun = () => {
    onDetect({
      fuzziness,
      scope,
      regexEnabled,
      nerEnabled,
      llmEnabled,
      regexTypes: regexEnabled ? activeRegexTypes : [],
      nerTypes: nerEnabled ? activeNerTypes : [],
    });
    onClose();
  };

  return (
    <div
      style={{
        position: "absolute",
        top: "100%",
        left: 0,
        marginTop: 6,
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 8,
        boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
        zIndex: Z_TOP_DIALOG,
        width: 340,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Scope tabs */}
      <div style={{
        display: "flex",
        borderBottom: "1px solid var(--border-color)",
        background: "rgba(0,0,0,0.15)",
        flexShrink: 0,
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
                flex: 1,
                padding: "8px 0",
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
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Sensitivity slider */}
      <div style={{ padding: "10px 14px 0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-secondary)", marginBottom: 3 }}>
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

      {/* Choose data types toggle */}
      <div style={{ padding: "8px 14px 0" }}>
        <button
          className="btn-ghost btn-sm"
          onClick={() => setShowDataTypes(prev => !prev)}
          style={{ width: "auto", display: "flex", alignItems: "center", justifyContent: "flex-start", gap: 6, fontSize: 12, border: "1px solid transparent" }}
        >
          <span style={{ transform: showDataTypes ? "rotate(45deg)" : "rotate(0deg)", transition: "transform 0.2s ease", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 18, fontWeight: 600, width: 18, height: 18, marginTop: -1 }}>+</span>
          <span>Choose data types</span>
        </button>
      </div>

      {/* Data types section (collapsible) */}
      {showDataTypes && (<>
        {/* Layer tabs */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--border-color)", flexShrink: 0, marginTop: 6 }}>
          {([
            { key: "patterns" as const, label: "Patterns", active: regexEnabled },
            { key: "ai" as const, label: "AI Recognition", active: nerEnabled },
            { key: "deep" as const, label: "Deep Analysis", active: llmEnabled },
          ]).map(({ key, label, active }) => {
            const isSel = tab === key;
            return (
              <button
                key={key}
                onClick={() => setTab(key)}
                style={{
                  flex: 1,
                  padding: "9px 4px",
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
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Tab content */}
        <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10, maxHeight: 300, overflowY: "auto" }}>

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

      {/* Run button */}
      <div style={{ padding: "10px 14px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
        <button
          className="btn-primary"
          onClick={handleRun}
          disabled={isProcessing || (!regexEnabled && !nerEnabled && !llmEnabled)}
          style={{ width: "100%" }}
        >
          <ScanSearch size={14} />
          {isProcessing ? "Detecting…" : `Run on ${scope === "page" ? `page ${activePage}` : "all pages"}`}
        </button>
        <button
          className="btn-ghost btn-sm"
          onClick={() => { onClose(); onReset(); }}
          disabled={isProcessing}
          style={{
            width: "100%",
            fontSize: 11,
            color: "var(--text-muted)",
            padding: "6px 0",
          }}
          title="Clear ALL existing detections and run a fresh scan from scratch"
        >
          Reset detection (clear &amp; rescan)
        </button>
      </div>
    </div>
  );
}
