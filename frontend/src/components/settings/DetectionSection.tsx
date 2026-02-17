/** Detection settings — Regex/NER/LLM toggles, NER model dropdown, language selector, fuzziness slider. */

import { useState, useRef } from "react";
import { ChevronDown } from "lucide-react";
import { useDetectionStore } from "../../store";
import { toErrorMessage } from "../../errorUtils";
import { updateSettings, logError } from "../../api";
import { Section, styles } from "./settingsStyles";
import { CustomPatternsContent } from "./CustomPatternsSection";

const NER_MODELS = [
  { value: "auto", label: "Auto — best model per language (recommended)", lang: "Auto", languages: "English, Spanish, French, German, Italian, Dutch, Portuguese" },
  { value: "spacy", label: "Default — fast, works offline, no download", lang: "English" },
  // Multilingual models
  { value: "iiiorg/piiranha-v1-detect-personal-information", label: "Multilingual (Piiranha) — 6 languages, high accuracy", lang: "Multilingual", languages: "English, German, French, Spanish, Italian, Dutch" },
  { value: "Babelscape/wikineural-multilingual-ner", label: "Multilingual (WikiNEural) — 9 languages incl. Portuguese", lang: "Multilingual", languages: "English, German, Spanish, French, Italian, Dutch, Polish, Portuguese, Russian" },
  { value: "Davlan/xlm-roberta-base-ner-hrl", label: "Multilingual (XLM-R) — 10+ high-resource languages", lang: "Multilingual", languages: "English, German, Spanish, French, Italian, Dutch, Portuguese, Chinese, Arabic, and more" },
  // English-specific models
  { value: "Isotonic/distilbert_finetuned_ai4privacy_v2", label: "English — Comprehensive, 54 PII types", lang: "English", languages: "Covers 54 PII types including names, financial, identity, addresses, and more" },
  { value: "dslim/bert-base-NER", label: "English — General purpose, good all-around", lang: "English" },
  { value: "StanfordAIMI/stanford-deidentifier-base", label: "English — Medical & clinical documents", lang: "English" },
  { value: "lakshyakh93/deberta_finetuned_pii", label: "English — Personal info (names, emails, phones)", lang: "English" },
  // Language-specific models
  { value: "Jean-Baptiste/camembert-ner", label: "French — CamemBERT, high accuracy", lang: "French" },
  { value: "mrm8488/bert-spanish-cased-finetuned-ner", label: "Spanish — BERT fine-tuned NER", lang: "Spanish" },
  { value: "fhswf/bert_de_ner", label: "German — BERT GermEval2014, high accuracy", lang: "German" },
  { value: "pierreguillou/ner-bert-base-cased-pt-lenerbr", label: "Portuguese — LeNER-Br, legal & general NER", lang: "Portuguese" },
] as const;

export default function DetectionSection() {
  const { detectionSettings, setDetectionSettings } = useDetectionStore();

  const [pendingNerBackend, setPendingNerBackend] = useState<string | null>(null);
  const [nerApplyStatus, setNerApplyStatus] = useState<"" | "saving" | "saved" | "error">("");
  const [nerApplyError, setNerApplyError] = useState("");
  const [nerDropOpen, setNerDropOpen] = useState(false);
  const nerDropRef = useRef<HTMLDivElement>(null);

  return (
    <Section title="Detection" icon={<span>🔍</span>}>
      <p style={styles.hint}>
        Choose which methods are used to find personal information in your documents.
      </p>
      <div style={styles.checkboxGroup}>
        <label style={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={detectionSettings.regex_enabled}
            onChange={(e) => {
              const v = e.target.checked;
              setDetectionSettings({ regex_enabled: v });
              updateSettings({ regex_enabled: v }).catch(logError("update-settings"));
            }}
          />{" "}
          Pattern matching (finds IDs, emails, phone numbers, etc.)
        </label>
        <label style={{ ...styles.checkboxLabel, marginLeft: 24, opacity: detectionSettings.regex_enabled ? 1 : 0.5 }}>
          <input
            type="checkbox"
            checked={detectionSettings.custom_patterns_enabled}
            disabled={!detectionSettings.regex_enabled}
            onChange={(e) => {
              const v = e.target.checked;
              setDetectionSettings({ custom_patterns_enabled: v });
              updateSettings({ custom_patterns_enabled: v }).catch(logError("update-settings"));
            }}
          />{" "}
          Custom patterns
        </label>
        {detectionSettings.regex_enabled && detectionSettings.custom_patterns_enabled && (
          <div style={{ marginLeft: 24, marginTop: 4, marginBottom: 8 }}>
            <CustomPatternsContent />
          </div>
        )}
        <label style={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={detectionSettings.ner_enabled}
            onChange={(e) => {
              const v = e.target.checked;
              setDetectionSettings({ ner_enabled: v });
              updateSettings({ ner_enabled: v }).catch(logError("update-settings"));
            }}
          />{" "}
          AI recognition (finds names, organizations, locations)
        </label>

        {detectionSettings.ner_enabled && (
          <div style={{ marginLeft: 24, marginTop: 4, marginBottom: 8 }}>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              AI recognition model
            </label>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <div ref={nerDropRef} style={{ flex: 1, position: "relative" }}>
                {/* Custom dropdown trigger */}
                <button
                  type="button"
                  onClick={() => setNerDropOpen(!nerDropOpen)}
                  onBlur={(e) => {
                    if (!nerDropRef.current?.contains(e.relatedTarget as Node)) setNerDropOpen(false);
                  }}
                  style={{
                    width: "100%",
                    padding: "6px 8px",
                    borderRadius: 6,
                    border: "1px solid var(--border-color)",
                    background: "var(--bg-secondary)",
                    color: "var(--text-primary)",
                    fontSize: 13,
                    textAlign: "left",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {(NER_MODELS.find(m => m.value === (pendingNerBackend ?? detectionSettings.ner_backend)) ?? NER_MODELS[0]).label}
                  </span>
                  {(() => {
                    const sel = NER_MODELS.find(m => m.value === (pendingNerBackend ?? detectionSettings.ner_backend)) ?? NER_MODELS[0];
                    const isAuto = sel.lang === "Auto";
                    const isMulti = sel.lang === "Multilingual";
                    const isLangSpecific = ["French", "Spanish", "German", "Portuguese", "Italian", "Dutch"].includes(sel.lang);
                    return (
                      <span style={{
                        fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 4, flexShrink: 0,
                        ...(isAuto ? { background: "rgba(76,175,80,0.15)", color: "var(--accent-success)" } : isMulti ? { background: "rgba(74,158,255,0.12)", color: "var(--accent-primary)" } : isLangSpecific ? { background: "rgba(255,183,77,0.15)", color: "#ffb74d" } : { background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }),
                      }}>{sel.lang}</span>
                    );
                  })()}
                  <ChevronDown size={14} style={{ flexShrink: 0, color: "var(--text-muted)", transition: "transform 0.15s", transform: nerDropOpen ? "rotate(180deg)" : "none" }} />
                </button>
                {/* Dropdown list */}
                {nerDropOpen && (
                  <div style={{
                    position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
                    background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: 6,
                    zIndex: 50, maxHeight: 260, overflowY: "auto",
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                  }}>
                    {NER_MODELS.map((m) => {
                      const selected = m.value === (pendingNerBackend ?? detectionSettings.ner_backend);
                      const isAuto = m.lang === "Auto";
                      const isMulti = m.lang === "Multilingual";
                      const isLangSpecific = ["French", "Spanish", "German", "Portuguese", "Italian", "Dutch"].includes(m.lang);
                      return (
                        <button
                          key={m.value}
                          type="button"
                          onClick={() => { setPendingNerBackend(m.value); setNerApplyStatus(""); setNerDropOpen(false); }}
                          style={{
                            width: "100%", padding: "8px 10px",
                            background: selected ? "rgba(74,158,255,0.1)" : "transparent",
                            border: "none", color: "var(--text-primary)", fontSize: 13, textAlign: "left",
                            cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                            borderBottom: m.value === "auto" ? "1px solid rgba(255,255,255,0.10)" : "1px solid rgba(255,255,255,0.04)",
                          }}
                          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = selected ? "rgba(74,158,255,0.15)" : "rgba(255,255,255,0.05)"; }}
                          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = selected ? "rgba(74,158,255,0.1)" : "transparent"; }}
                        >
                          <span style={{ flex: 1 }}>{m.label}</span>
                          <span style={{
                            fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 4, flexShrink: 0,
                            ...(isAuto ? { background: "rgba(76,175,80,0.15)", color: "var(--accent-success)" } : isMulti ? { background: "rgba(74,158,255,0.12)", color: "var(--accent-primary)" } : isLangSpecific ? { background: "rgba(255,183,77,0.15)", color: "#ffb74d" } : { background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }),
                          }}>{m.lang}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
              <button
                className="btn-primary btn-sm"
                disabled={
                  !pendingNerBackend ||
                  pendingNerBackend === detectionSettings.ner_backend ||
                  nerApplyStatus === "saving"
                }
                onClick={async () => {
                  if (!pendingNerBackend) return;
                  setNerApplyStatus("saving");
                  setNerApplyError("");
                  try {
                    await updateSettings({ ner_backend: pendingNerBackend });
                    setDetectionSettings({ ner_backend: pendingNerBackend });
                    setPendingNerBackend(null);
                    setNerApplyStatus("saved");
                    setTimeout(() => setNerApplyStatus(""), 3000);
                  } catch (e: unknown) {
                    setNerApplyStatus("error");
                    setNerApplyError(toErrorMessage(e) || "Failed to update NER backend");
                  }
                }}
                style={{ whiteSpace: "nowrap" }}
              >
                {nerApplyStatus === "saving" ? "Applying..." : "Apply"}
              </button>
            </div>
            {(() => {
              const sel = pendingNerBackend ?? detectionSettings.ner_backend;
              const model = NER_MODELS.find(m => m.value === sel);
              if (sel === "auto") {
                return (
                  <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
                    🧠 Detects document language automatically and picks the best model.
                    <br />🌐 Supported: English, Spanish, French, German, Italian, Dutch, Portuguese
                  </p>
                );
              }
              return model && "languages" in model ? (
                <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
                  🌐 {model.languages}
                </p>
              ) : null;
            })()}
            {nerApplyStatus === "saved" && (
              <p style={{ fontSize: 12, color: "var(--accent-success)", marginTop: 4 }}>
                Model updated — takes effect on next scan.
              </p>
            )}
            {nerApplyStatus === "error" && (
              <p style={{ fontSize: 12, color: "var(--accent-danger)", marginTop: 4 }}>
                {nerApplyError}
              </p>
            )}
          </div>
        )}
        <label style={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={detectionSettings.llm_detection_enabled}
            onChange={(e) => {
              const v = e.target.checked;
              setDetectionSettings({ llm_detection_enabled: v });
              updateSettings({ llm_detection_enabled: v }).catch(logError("update-settings"));
            }}
          />{" "}
          Deep analysis (uses an LLM for harder-to-find information)
        </label>

        {/* Detection language selector */}
        <div style={{ marginTop: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <span style={{ fontSize: 13, color: "var(--text-primary)" }}>
              Detection language
            </span>
          </div>
          <select
            value={detectionSettings.detection_language ?? "auto"}
            onChange={async (e) => {
              const v = e.target.value;
              setDetectionSettings({ detection_language: v });
              try {
                await updateSettings({ detection_language: v });
              } catch (err: unknown) {
                console.error("Failed to update detection language:", err);
              }
            }}
            style={{
              width: "100%",
              padding: "6px 8px",
              borderRadius: 6,
              border: "1px solid var(--border-color)",
              background: "var(--bg-secondary)",
              color: "var(--text-primary)",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            <option value="auto">Auto-detect per page</option>
            <option value="en">English</option>
            <option value="fr">French</option>
            <option value="de">German</option>
            <option value="es">Spanish</option>
            <option value="it">Italian</option>
            <option value="nl">Dutch</option>
            <option value="pt">Portuguese</option>
          </select>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
            Filters regex patterns to only those relevant for the selected
            language. &ldquo;Auto&rdquo; detects per page using stop-word analysis.
          </p>
        </div>

        {/* Detection fuzziness slider */}
        <div style={{ marginTop: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <span style={{ fontSize: 13, color: "var(--text-primary)" }}>
              Region grouping
            </span>
            <span style={{ fontSize: 12, color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
              {Math.round(detectionSettings.detection_fuzziness * 100)}%
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={Math.round(detectionSettings.detection_fuzziness * 100)}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10) / 100;
              setDetectionSettings({ detection_fuzziness: v });
            }}
            onMouseUp={() => {
              updateSettings({ detection_fuzziness: detectionSettings.detection_fuzziness })
                .catch(logError("update-settings"));
            }}
            onTouchEnd={() => {
              updateSettings({ detection_fuzziness: detectionSettings.detection_fuzziness })
                .catch(logError("update-settings"));
            }}
            style={{ width: "100%", accentColor: "var(--accent-primary)" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
            <span>Strict — split more</span>
            <span>Permissive — group more</span>
          </div>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
            Controls how aggressively nearby words merge into a single
            highlight. Higher values allow wider gaps between words in
            the same region (capped at 20 pt regardless).
          </p>
        </div>
      </div>
    </Section>
  );
}
