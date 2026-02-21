/** Detection settings — Regex/NER/LLM toggles, NER model dropdown, language selector, fuzziness slider. */

import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, CircleQuestion } from "../../icons";
import { useDetectionStore } from "../../store";
import { toErrorMessage } from "../../errorUtils";
import { updateSettings, logError, fetchCustomPatterns } from "../../api";
import { Section, styles } from "./settingsStyles";
import { CustomPatternsDialog, formatTemplate } from "./CustomPatternsSection";
import { DELETE_SIMILAR_PREF_KEY } from "../../hooks/useRegionActions";
import type { CustomPattern } from "../../types";

const NER_MODELS = [
  { value: "auto", key: "auto", lang: "Auto", hasLanguages: true },
  { value: "spacy", key: "default", lang: "English", hasLanguages: false },
  // Multilingual models
  { value: "iiiorg/piiranha-v1-detect-personal-information", key: "piiranha", lang: "Multilingual", hasLanguages: true },
  { value: "Babelscape/wikineural-multilingual-ner", key: "wikineural", lang: "Multilingual", hasLanguages: true },
  { value: "Davlan/xlm-roberta-base-ner-hrl", key: "xlmr", lang: "Multilingual", hasLanguages: true },
  // English-specific models
  { value: "Isotonic/distilbert_finetuned_ai4privacy_v2", key: "enComprehensive", lang: "English", hasLanguages: true },
  { value: "dslim/bert-base-NER", key: "enGeneral", lang: "English", hasLanguages: false },
  { value: "StanfordAIMI/stanford-deidentifier-base", key: "enMedical", lang: "English", hasLanguages: false },
  { value: "lakshyakh93/deberta_finetuned_pii", key: "enPersonal", lang: "English", hasLanguages: false },
  // Language-specific models
  { value: "Jean-Baptiste/camembert-ner", key: "frCamembert", lang: "French", hasLanguages: false },
  { value: "mrm8488/bert-spanish-cased-finetuned-ner", key: "esBert", lang: "Spanish", hasLanguages: false },
  { value: "fhswf/bert_de_ner", key: "deGermeval", lang: "German", hasLanguages: false },
  { value: "pierreguillou/ner-bert-base-cased-pt-lenerbr", key: "ptLener", lang: "Portuguese", hasLanguages: false },
] as const;

export default function DetectionSection() {
  const { t } = useTranslation();
  const { detectionSettings, setDetectionSettings } = useDetectionStore();

  const [pendingNerBackend, setPendingNerBackend] = useState<string | null>(null);
  const [nerApplyStatus, setNerApplyStatus] = useState<"" | "saving" | "saved" | "error">("");
  const [nerApplyError, setNerApplyError] = useState("");
  const [nerDropOpen, setNerDropOpen] = useState(false);
  const nerDropRef = useRef<HTMLDivElement>(null);
  const [regionGroupingHovered, setRegionGroupingHovered] = useState(false);
  const [regionGroupingTooltip, setRegionGroupingTooltip] = useState(false);
  const [langHovered, setLangHovered] = useState(false);
  const [langTooltip, setLangTooltip] = useState(false);
  const [methodsHovered, setMethodsHovered] = useState(false);
  const [methodsTooltip, setMethodsTooltip] = useState(false);
  const [patternHovered, setPatternHovered] = useState(false);
  const [patternTooltip, setPatternTooltip] = useState(false);
  const [customPatternsHovered, setCustomPatternsHovered] = useState(false);
  const [customPatternsTooltip, setCustomPatternsTooltip] = useState(false);
  const [aiHovered, setAiHovered] = useState(false);
  const [aiTooltip, setAiTooltip] = useState(false);
  const [deepHovered, setDeepHovered] = useState(false);
  const [deepTooltip, setDeepTooltip] = useState(false);
  const [customPatternsDialogOpen, setCustomPatternsDialogOpen] = useState(false);
  const [activePatterns, setActivePatterns] = useState<CustomPattern[]>([]);

  // ── Review-behaviour prefs (localStorage) ──
  const [deletePref, setDeletePref] = useState<string>(
    () => localStorage.getItem(DELETE_SIMILAR_PREF_KEY) ?? "ask",
  );

  useEffect(() => {
    if (detectionSettings.regex_enabled && detectionSettings.custom_patterns_enabled) {
      fetchCustomPatterns()
        .then((all) => setActivePatterns(all.filter((p) => p.enabled)))
        .catch(() => setActivePatterns([]));
    }
  }, [detectionSettings.regex_enabled, detectionSettings.custom_patterns_enabled]);

  return (
    <>
      <Section>
        <div
          style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, position: "relative", cursor: "default" }}
          onMouseEnter={() => setMethodsHovered(true)}
          onMouseLeave={() => setMethodsHovered(false)}
        >
          <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
            {t("settingsDetection.detectionMethods")}
          </p>
          <CircleQuestion
            size={16}
            style={{
              color: "#ffffff",
              opacity: methodsHovered ? 1 : 0,
              transition: "opacity 0.15s",
              flexShrink: 0,
              cursor: "pointer",
            }}
            onMouseEnter={() => setMethodsTooltip(true)}
            onMouseLeave={() => setMethodsTooltip(false)}
          />
          {methodsTooltip && (
            <div style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: 0,
              zIndex: 100,
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 6,
              padding: "8px 10px",
              fontSize: 11,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
              minWidth: 200,
              maxWidth: 320,
              boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
              pointerEvents: "none",
            }}>
              {t("settingsDetection.detectionMethodsTooltip")}
            </div>
          )}
        </div>
      <div style={styles.checkboxGroup}>
        <div
          style={{ display: "flex", alignItems: "center", position: "relative" }}
          onMouseEnter={() => setPatternHovered(true)}
          onMouseLeave={() => setPatternHovered(false)}
        >
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
            {t("settingsDetection.patternMatching")}
          </label>
          <CircleQuestion
            size={14}
            style={{
              color: "#ffffff",
              opacity: patternHovered ? 1 : 0,
              transition: "opacity 0.15s",
              flexShrink: 0,
              cursor: "pointer",
              marginLeft: 4,
            }}
            onMouseEnter={() => setPatternTooltip(true)}
            onMouseLeave={() => setPatternTooltip(false)}
          />
          {patternTooltip && (
            <div style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: 0,
              zIndex: 100,
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 6,
              padding: "8px 10px",
              fontSize: 11,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
              minWidth: 200,
              maxWidth: 320,
              boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
              pointerEvents: "none",
            }}>
              {t("settingsDetection.patternMatchingTooltip")}
            </div>
          )}
        </div>
        <div
          style={{ display: "flex", alignItems: "center", position: "relative", marginLeft: 24, opacity: detectionSettings.regex_enabled ? 1 : 0.5 }}
          onMouseEnter={() => setCustomPatternsHovered(true)}
          onMouseLeave={() => setCustomPatternsHovered(false)}
        >
          <label style={styles.checkboxLabel}>
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
            {t("settingsDetection.customPatterns")}
          </label>
          <CircleQuestion
            size={14}
            style={{
              color: "#ffffff",
              opacity: customPatternsHovered ? 1 : 0,
              transition: "opacity 0.15s",
              flexShrink: 0,
              cursor: "pointer",
              marginLeft: 4,
            }}
            onMouseEnter={() => setCustomPatternsTooltip(true)}
            onMouseLeave={() => setCustomPatternsTooltip(false)}
          />
          {customPatternsTooltip && (
            <div style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: 0,
              zIndex: 100,
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 6,
              padding: "8px 10px",
              fontSize: 11,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
              minWidth: 200,
              maxWidth: 320,
              boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
              pointerEvents: "none",
            }}>
              {t("settingsDetection.customPatternsTooltip")}
            </div>
          )}
        </div>
        {detectionSettings.regex_enabled && detectionSettings.custom_patterns_enabled && (
          <div style={{ marginLeft: 24, marginTop: 6 }}>
            {activePatterns.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 8 }}>
                {activePatterns.map((p) => (
                  <div key={p.id} style={{ paddingLeft: 4 }}>
                    <div style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 500 }}>{p.name}</div>
                    <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "monospace", marginTop: 1 }}>
                      {p.template ? formatTemplate(p.template) : (p.pattern ?? p._generated_pattern ?? "")}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <button
              type="button"
              className="btn-primary btn-sm"
              onClick={() => setCustomPatternsDialogOpen(true)}
            >
              {t("customPatterns.manage")}
            </button>
          </div>
        )}
        <div
          style={{ display: "flex", alignItems: "center", position: "relative" }}
          onMouseEnter={() => setAiHovered(true)}
          onMouseLeave={() => setAiHovered(false)}
        >
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
            {t("settingsDetection.aiRecognition")}
          </label>
          <CircleQuestion
            size={14}
            style={{
              color: "#ffffff",
              opacity: aiHovered ? 1 : 0,
              transition: "opacity 0.15s",
              flexShrink: 0,
              cursor: "pointer",
              marginLeft: 4,
            }}
            onMouseEnter={() => setAiTooltip(true)}
            onMouseLeave={() => setAiTooltip(false)}
          />
          {aiTooltip && (
            <div style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: 0,
              zIndex: 100,
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 6,
              padding: "8px 10px",
              fontSize: 11,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
              minWidth: 200,
              maxWidth: 320,
              boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
              pointerEvents: "none",
            }}>
              {t("settingsDetection.aiRecognitionTooltip")}
            </div>
          )}
        </div>

        {detectionSettings.ner_enabled && (
          <div style={{ marginLeft: 24, marginTop: 4, marginBottom: 8 }}>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              {t("settingsDetection.aiModel")}
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
                    {t(`settingsDetection.nerModels.${(NER_MODELS.find(m => m.value === (pendingNerBackend ?? detectionSettings.ner_backend)) ?? NER_MODELS[0]).key}`)}
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
                      }}>{t(`settingsDetection.nerModels.${sel.key}Badge`)}</span>
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
                          <span style={{ flex: 1 }}>{t(`settingsDetection.nerModels.${m.key}`)}</span>
                          <span style={{
                            fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 4, flexShrink: 0,
                            ...(isAuto ? { background: "rgba(76,175,80,0.15)", color: "var(--accent-success)" } : isMulti ? { background: "rgba(74,158,255,0.12)", color: "var(--accent-primary)" } : isLangSpecific ? { background: "rgba(255,183,77,0.15)", color: "#ffb74d" } : { background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }),
                          }}>{t(`settingsDetection.nerModels.${m.key}Badge`)}</span>
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
                    setNerApplyError(toErrorMessage(e) || t("settingsDetection.modelUpdateFailed"));
                  }
                }}
                style={{ whiteSpace: "nowrap" }}
              >
                {nerApplyStatus === "saving" ? t("settingsDetection.applying") : t("common.apply")}
              </button>
            </div>
            {(() => {
              const sel = pendingNerBackend ?? detectionSettings.ner_backend;
              const model = NER_MODELS.find(m => m.value === sel);
              if (sel === "auto") {
                return (
                  <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
                    {t("settingsDetection.autoModelDescription")}
                  </p>
                );
              }
              return model && "hasLanguages" in model && model.hasLanguages ? (
                <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
                  🌐 {t(`settingsDetection.nerModels.${model.key}Languages`)}
                </p>
              ) : null;
            })()}
            {nerApplyStatus === "saved" && (
              <p style={{ fontSize: 12, color: "var(--accent-success)", marginTop: 4 }}>
                {t("settingsDetection.modelUpdated")}
              </p>
            )}
            {nerApplyStatus === "error" && (
              <p style={{ fontSize: 12, color: "var(--accent-danger)", marginTop: 4 }}>
                {nerApplyError}
              </p>
            )}
          </div>
        )}
        <div
          style={{ display: "flex", alignItems: "center", position: "relative" }}
          onMouseEnter={() => setDeepHovered(true)}
          onMouseLeave={() => setDeepHovered(false)}
        >
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
            {t("settingsDetection.deepAnalysis")}
          </label>
          <CircleQuestion
            size={14}
            style={{
              color: "#ffffff",
              opacity: deepHovered ? 1 : 0,
              transition: "opacity 0.15s",
              flexShrink: 0,
              cursor: "pointer",
              marginLeft: 4,
            }}
            onMouseEnter={() => setDeepTooltip(true)}
            onMouseLeave={() => setDeepTooltip(false)}
          />
          {deepTooltip && (
            <div style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: 0,
              zIndex: 100,
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 6,
              padding: "8px 10px",
              fontSize: 11,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
              minWidth: 200,
              maxWidth: 320,
              boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
              pointerEvents: "none",
            }}>
              {t("settingsDetection.deepAnalysisTooltip")}
            </div>
          )}
        </div>
      </div>
    </Section>

    {/* Detection language card */}
    <Section>
      <div
        style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, position: "relative", cursor: "default" }}
        onMouseEnter={() => setLangHovered(true)}
        onMouseLeave={() => setLangHovered(false)}
      >
        <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
          {t("settingsDetection.detectionLanguage")}
        </p>
        <CircleQuestion
          size={16}
          style={{
            color: "#ffffff",
            opacity: langHovered ? 1 : 0,
            transition: "opacity 0.15s",
            flexShrink: 0,
            cursor: "pointer",
          }}
          onMouseEnter={() => setLangTooltip(true)}
          onMouseLeave={() => setLangTooltip(false)}
        />
        {langTooltip && (
          <div style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            zIndex: 100,
            background: "var(--bg-primary)",
            border: "1px solid var(--border-color)",
            borderRadius: 6,
            padding: "8px 10px",
            fontSize: 11,
            color: "var(--text-secondary)",
            lineHeight: 1.5,
            minWidth: 200,
            maxWidth: 320,
            boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
            pointerEvents: "none",
          }}>
            {t("settingsDetection.languageFilterHint")}
          </div>
        )}
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
        <option value="auto">{t("settingsDetection.autoDetectPerPage")}</option>
        <option value="en">{t("settingsDetection.lang.english")}</option>
        <option value="fr">{t("settingsDetection.lang.french")}</option>
        <option value="de">{t("settingsDetection.lang.german")}</option>
        <option value="es">{t("settingsDetection.lang.spanish")}</option>
        <option value="it">{t("settingsDetection.lang.italian")}</option>
        <option value="nl">{t("settingsDetection.lang.dutch")}</option>
        <option value="pt">{t("settingsDetection.lang.portuguese")}</option>
      </select>
    </Section>

    {/* Region grouping card */}
    <Section>
      <div
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, cursor: "default" }}
        onMouseEnter={() => setRegionGroupingHovered(true)}
        onMouseLeave={() => setRegionGroupingHovered(false)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 6, position: "relative" }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
            {t("settingsDetection.regionGrouping")}
          </p>
          <CircleQuestion
            size={16}
            style={{
              color: "#ffffff",
              opacity: regionGroupingHovered ? 1 : 0,
              transition: "opacity 0.15s",
              flexShrink: 0,
              cursor: "pointer",
              position: "relative",
            }}
            onMouseEnter={() => setRegionGroupingTooltip(true)}
            onMouseLeave={() => setRegionGroupingTooltip(false)}
          />
          {regionGroupingTooltip && (
            <div style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: 0,
              zIndex: 100,
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              borderRadius: 6,
              padding: "8px 10px",
              fontSize: 11,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
              minWidth: 200,
              maxWidth: 320,
              boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
              pointerEvents: "none",
            }}>
              {t("settingsDetection.regionGroupingHint")}
            </div>
          )}
        </div>
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
        <span>{t("settingsDetection.strictSplit")}</span>
        <span>{t("settingsDetection.permissiveGroup")}</span>
      </div>
    </Section>
    {/* ── Review behaviour ── */}
    <Section>
      <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: "0 0 6px" }}>
        {t("settingsDetection.reviewBehaviorTitle")}
      </p>
      <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 14px", lineHeight: 1.5 }}>
        {t("settingsDetection.deletePrefLabel")}{" "}
        <strong style={{ color: "var(--text-secondary)" }}>
          {deletePref === "all"
            ? t("settingsDetection.deletePrefAll")
            : deletePref === "one"
            ? t("settingsDetection.deletePrefOne")
            : t("settingsDetection.deletePrefAsk")}
        </strong>
      </p>
      {deletePref !== "ask" && (
        <button
          onClick={() => {
            localStorage.removeItem(DELETE_SIMILAR_PREF_KEY);
            setDeletePref("ask");
          }}
          style={{
            padding: "7px 14px",
            fontSize: 12,
            fontWeight: 600,
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: "transparent",
            color: "var(--accent-primary)",
            cursor: "pointer",
          }}
        >
          {t("settingsDetection.restoreDeleteDialog")}
        </button>
      )}
      {deletePref === "ask" && (
        <p style={{ fontSize: 11, color: "var(--text-muted)", margin: 0, fontStyle: "italic" }}>
          {t("settingsDetection.deleteDialogActive")}
        </p>
      )}
    </Section>

    <CustomPatternsDialog
      open={customPatternsDialogOpen}
      onClose={() => {
        setCustomPatternsDialogOpen(false);
        fetchCustomPatterns()
          .then((all) => setActivePatterns(all.filter((p) => p.enabled)))
          .catch(() => {});
      }}
    />
    </>
  );
}
