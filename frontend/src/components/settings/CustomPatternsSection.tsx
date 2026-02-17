/** Custom Patterns — user-defined regex patterns for PII detection. */

import { useState, useEffect } from "react";
import { Plus, Trash2, Play, ToggleLeft, ToggleRight, AlertCircle, Check, X } from "lucide-react";
import { styles } from "./settingsStyles";
import { toErrorMessage } from "../../errorUtils";
import {
  fetchCustomPatterns,
  saveCustomPatterns,
  deleteCustomPattern,
  testPattern,
} from "../../api";
import type { CustomPattern, PatternTemplateBlock, PatternTestResult } from "../../types";

// Template block types for the simple mode dropdown
const BLOCK_TYPES = [
  { value: "letters", label: "Letters (a-z)", hint: "Any letter, case-insensitive" },
  { value: "LETTERS", label: "LETTERS (A-Z)", hint: "Uppercase letters only" },
  { value: "digits", label: "Digits (0-9)", hint: "Numeric digits" },
  { value: "alphanumeric", label: "Alphanumeric", hint: "Letters and numbers" },
  { value: "separator", label: "Separator", hint: "Fixed character like - or /" },
  { value: "literal", label: "Literal text", hint: "Exact text match" },
] as const;

// PII type options
const PII_TYPES = [
  "CUSTOM", "PERSON", "ORG", "EMAIL", "PHONE", "SSN",
  "CREDIT_CARD", "DATE", "ADDRESS", "LOCATION",
  "IP_ADDRESS", "IBAN", "PASSPORT", "DRIVER_LICENSE",
];

// Convert template blocks to regex
function templateToRegex(blocks: PatternTemplateBlock[]): string {
  return blocks.map(block => {
    const count = block.count ?? 1;
    const value = block.value ?? "";
    switch (block.type) {
      case "letters": return `[A-Za-z]{${count}}`;
      case "LETTERS": return `[A-Z]{${count}}`;
      case "digits": return `\\d{${count}}`;
      case "alphanumeric": return `[A-Za-z0-9]{${count}}`;
      case "separator": return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      case "literal": return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      case "any": return `.{${count}}`;
      default: return "";
    }
  }).join("");
}

// Format template blocks for display
function formatTemplate(blocks: PatternTemplateBlock[]): string {
  return blocks.map(block => {
    const count = block.count ?? 1;
    switch (block.type) {
      case "letters": return `[${count} letters]`;
      case "LETTERS": return `[${count} LETTERS]`;
      case "digits": return `[${count} digits]`;
      case "alphanumeric": return `[${count} alnum]`;
      case "separator": return block.value ?? "";
      case "literal": return block.value ?? "";
      case "any": return `[${count} any]`;
      default: return "";
    }
  }).join(" ");
}

interface PatternEditorProps {
  onSave: (pattern: Omit<CustomPattern, "id">) => void;
  onCancel: () => void;
  initial?: CustomPattern;
}

function PatternEditor({ onSave, onCancel, initial }: PatternEditorProps) {
  const [mode, setMode] = useState<"simple" | "advanced">(initial?.pattern ? "advanced" : "simple");
  const [name, setName] = useState(initial?.name ?? "");
  const [piiType, setPiiType] = useState(initial?.pii_type ?? "CUSTOM");
  const [caseSensitive, setCaseSensitive] = useState(initial?.case_sensitive ?? false);
  const [confidence, setConfidence] = useState(initial?.confidence ?? 0.85);
  
  // Advanced mode
  const [regexPattern, setRegexPattern] = useState(initial?.pattern ?? "");
  
  // Simple mode - template blocks
  const [blocks, setBlocks] = useState<PatternTemplateBlock[]>(
    initial?.template ?? [{ type: "digits", count: 3 }]
  );
  
  // Test
  const [testText, setTestText] = useState("");
  const [testResult, setTestResult] = useState<PatternTestResult | null>(null);
  const [testError, setTestError] = useState("");
  const [testing, setTesting] = useState(false);
  
  // Validation
  const [error, setError] = useState("");

  const generatedRegex = mode === "simple" ? templateToRegex(blocks) : regexPattern;

  const addBlock = () => {
    setBlocks([...blocks, { type: "digits", count: 1 }]);
  };

  const removeBlock = (index: number) => {
    setBlocks(blocks.filter((_, i) => i !== index));
  };

  const updateBlock = (index: number, updates: Partial<PatternTemplateBlock>) => {
    setBlocks(blocks.map((b, i) => i === index ? { ...b, ...updates } : b));
  };

  const handleTest = async () => {
    if (!testText.trim()) return;
    setTesting(true);
    setTestError("");
    setTestResult(null);
    
    try {
      const result = await testPattern(generatedRegex, testText, caseSensitive);
      setTestResult(result);
    } catch (err) {
      setTestError(toErrorMessage(err));
    } finally {
      setTesting(false);
    }
  };

  const handleSave = () => {
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (!generatedRegex.trim()) {
      setError("Pattern is required");
      return;
    }
    
    // Validate regex
    try {
      new RegExp(generatedRegex);
    } catch {
      setError("Invalid regex pattern");
      return;
    }
    
    const patternData: Omit<CustomPattern, "id"> = {
      name: name.trim(),
      pii_type: piiType,
      enabled: true,
      case_sensitive: caseSensitive,
      confidence,
    };
    
    if (mode === "simple") {
      patternData.template = blocks;
      patternData._generated_pattern = generatedRegex;
    } else {
      patternData.pattern = regexPattern;
    }
    
    onSave(patternData);
  };

  return (
    <div style={{
      background: "var(--bg-primary)",
      borderRadius: 8,
      padding: 16,
      border: "1px solid var(--border-color)",
    }}>
      {/* Mode toggle */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setMode("simple")}
          style={{
            flex: 1,
            padding: "8px 12px",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: mode === "simple" ? "var(--accent-primary)" : "var(--bg-secondary)",
            color: mode === "simple" ? "white" : "var(--text-secondary)",
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          Simple Mode
        </button>
        <button
          onClick={() => setMode("advanced")}
          style={{
            flex: 1,
            padding: "8px 12px",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: mode === "advanced" ? "var(--accent-primary)" : "var(--bg-secondary)",
            color: mode === "advanced" ? "white" : "var(--text-secondary)",
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          Advanced (Regex)
        </button>
      </div>
      
      {/* Name */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
          Pattern name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => { setName(e.target.value); setError(""); }}
          placeholder="e.g., Employee ID"
          style={{
            width: "100%",
            padding: "8px 10px",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: "var(--bg-secondary)",
            color: "var(--text-primary)",
            fontSize: 13,
          }}
        />
      </div>
      
      {/* PII Type */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
          PII type
        </label>
        <select
          value={piiType}
          onChange={(e) => setPiiType(e.target.value)}
          style={{
            width: "100%",
            padding: "8px 10px",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: "var(--bg-secondary)",
            color: "var(--text-primary)",
            fontSize: 13,
          }}
        >
          {PII_TYPES.map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>
      
      {/* Simple mode: Template builder */}
      {mode === "simple" && (
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 8 }}>
            Pattern template
          </label>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {blocks.map((block, index) => (
              <div key={index} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <select
                  value={block.type}
                  onChange={(e) => updateBlock(index, { type: e.target.value as PatternTemplateBlock["type"] })}
                  style={{
                    flex: 2,
                    padding: "6px 8px",
                    borderRadius: 6,
                    border: "1px solid var(--border-color)",
                    background: "var(--bg-secondary)",
                    color: "var(--text-primary)",
                    fontSize: 12,
                  }}
                >
                  {BLOCK_TYPES.map(bt => (
                    <option key={bt.value} value={bt.value}>{bt.label}</option>
                  ))}
                </select>
                
                {(block.type === "separator" || block.type === "literal") ? (
                  <input
                    type="text"
                    value={block.value ?? ""}
                    onChange={(e) => updateBlock(index, { value: e.target.value })}
                    placeholder={block.type === "separator" ? "-" : "text"}
                    style={{
                      flex: 1,
                      padding: "6px 8px",
                      borderRadius: 6,
                      border: "1px solid var(--border-color)",
                      background: "var(--bg-secondary)",
                      color: "var(--text-primary)",
                      fontSize: 12,
                      width: 60,
                    }}
                  />
                ) : (
                  <input
                    type="number"
                    value={block.count ?? 1}
                    onChange={(e) => updateBlock(index, { count: Math.max(1, parseInt(e.target.value) || 1) })}
                    min={1}
                    max={100}
                    style={{
                      flex: 1,
                      padding: "6px 8px",
                      borderRadius: 6,
                      border: "1px solid var(--border-color)",
                      background: "var(--bg-secondary)",
                      color: "var(--text-primary)",
                      fontSize: 12,
                      width: 60,
                    }}
                  />
                )}
                
                <button
                  onClick={() => removeBlock(index)}
                  disabled={blocks.length === 1}
                  style={{
                    padding: 6,
                    borderRadius: 4,
                    border: "none",
                    background: "transparent",
                    color: blocks.length === 1 ? "var(--text-muted)" : "var(--accent-danger)",
                    cursor: blocks.length === 1 ? "not-allowed" : "pointer",
                  }}
                >
                  <X size={16} />
                </button>
              </div>
            ))}
            
            <button
              onClick={addBlock}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                padding: "8px 12px",
                borderRadius: 6,
                border: "1px dashed var(--border-color)",
                background: "transparent",
                color: "var(--text-secondary)",
                cursor: "pointer",
                fontSize: 12,
              }}
            >
              <Plus size={14} /> Add block
            </button>
          </div>
          
          <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-muted)" }}>
            Preview: <code style={{ background: "var(--bg-secondary)", padding: "2px 6px", borderRadius: 3 }}>
              {formatTemplate(blocks)}
            </code>
          </div>
        </div>
      )}
      
      {/* Advanced mode: Raw regex */}
      {mode === "advanced" && (
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
            Regex pattern
          </label>
          <input
            type="text"
            value={regexPattern}
            onChange={(e) => { setRegexPattern(e.target.value); setError(""); }}
            placeholder="e.g., [A-Z]{3}-\d{5}"
            style={{
              width: "100%",
              padding: "8px 10px",
              borderRadius: 6,
              border: "1px solid var(--border-color)",
              background: "var(--bg-secondary)",
              color: "var(--text-primary)",
              fontSize: 13,
              fontFamily: "monospace",
            }}
          />
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            Use standard regex syntax. Common patterns: <code>\d</code> (digit), <code>[A-Z]</code> (letter), <code>\{"{n}"}</code> (exactly n times)
          </p>
        </div>
      )}
      
      {/* Generated regex preview */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
          Generated regex
        </label>
        <code style={{
          display: "block",
          padding: "8px 10px",
          borderRadius: 6,
          background: "var(--bg-secondary)",
          color: "var(--accent-primary)",
          fontSize: 12,
          fontFamily: "monospace",
          wordBreak: "break-all",
        }}>
          {generatedRegex || "(empty)"}
        </code>
      </div>
      
      {/* Options row */}
      <div style={{ display: "flex", gap: 16, marginBottom: 12 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={caseSensitive}
            onChange={(e) => setCaseSensitive(e.target.checked)}
          />
          Case sensitive
        </label>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Confidence:</label>
          <input
            type="number"
            value={confidence}
            onChange={(e) => setConfidence(Math.min(1, Math.max(0, parseFloat(e.target.value) || 0)))}
            step={0.05}
            min={0}
            max={1}
            style={{
              width: 60,
              padding: "4px 6px",
              borderRadius: 4,
              border: "1px solid var(--border-color)",
              background: "var(--bg-secondary)",
              color: "var(--text-primary)",
              fontSize: 12,
            }}
          />
        </div>
      </div>
      
      {/* Test section */}
      <div style={{ marginBottom: 12, padding: 12, background: "var(--bg-secondary)", borderRadius: 6 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
          Test your pattern
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            value={testText}
            onChange={(e) => setTestText(e.target.value)}
            placeholder="Enter sample text to test..."
            style={{
              flex: 1,
              padding: "8px 10px",
              borderRadius: 6,
              border: "1px solid var(--border-color)",
              background: "var(--bg-primary)",
              color: "var(--text-primary)",
              fontSize: 13,
            }}
          />
          <button
            onClick={handleTest}
            disabled={!testText.trim() || !generatedRegex || testing}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "8px 16px",
              borderRadius: 6,
              border: "none",
              background: "var(--accent-primary)",
              color: "white",
              cursor: !testText.trim() || !generatedRegex || testing ? "not-allowed" : "pointer",
              opacity: !testText.trim() || !generatedRegex || testing ? 0.5 : 1,
              fontSize: 13,
            }}
          >
            <Play size={14} /> Test
          </button>
        </div>
        
        {testError && (
          <div style={{ marginTop: 8, color: "var(--accent-danger)", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
            <AlertCircle size={14} /> {testError}
          </div>
        )}
        
        {testResult && (
          <div style={{ marginTop: 8 }}>
            <div style={{
              fontSize: 12,
              color: testResult.match_count > 0 ? "var(--accent-success)" : "var(--text-muted)",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}>
              {testResult.match_count > 0 ? <Check size={14} /> : <X size={14} />}
              {testResult.match_count} match{testResult.match_count !== 1 ? "es" : ""} found
            </div>
            {testResult.matches.length > 0 && (
              <div style={{ marginTop: 6, fontSize: 12, color: "var(--text-secondary)" }}>
                Matches: {testResult.matches.map(m => (
                  <code key={m.start} style={{ background: "var(--accent-success)", color: "white", padding: "1px 4px", borderRadius: 2, marginRight: 4 }}>
                    {m.text}
                  </code>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Error */}
      {error && (
        <div style={{ marginBottom: 12, color: "var(--accent-danger)", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <AlertCircle size={14} /> {error}
        </div>
      )}
      
      {/* Actions */}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button
          onClick={onCancel}
          style={{
            padding: "8px 16px",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: "transparent",
            color: "var(--text-secondary)",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          style={{
            padding: "8px 16px",
            borderRadius: 6,
            border: "none",
            background: "var(--accent-primary)",
            color: "white",
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          {initial ? "Update" : "Add"} Pattern
        </button>
      </div>
    </div>
  );
}

/**
 * Inner content of the custom patterns panel — pattern list + add/edit form.
 * Used by DetectionSection when the "Custom patterns" checkbox is checked.
 */
export function CustomPatternsContent() {
  const [patterns, setPatterns] = useState<CustomPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showEditor, setShowEditor] = useState(false);
  const [editingPattern, setEditingPattern] = useState<CustomPattern | null>(null);

  // Load patterns on mount
  useEffect(() => {
    fetchCustomPatterns()
      .then(setPatterns)
      .catch((err) => setError(toErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  const handleSavePattern = async (patternData: Omit<CustomPattern, "id">) => {
    try {
      if (editingPattern) {
        // Update existing
        const updated = patterns.map(p =>
          p.id === editingPattern.id ? { ...p, ...patternData } : p
        );
        await saveCustomPatterns(updated);
        setPatterns(updated);
      } else {
        // Add new - generate ID client-side for optimistic update
        const newPattern: CustomPattern = {
          ...patternData,
          id: Math.random().toString(36).substring(2, 10),
        };
        const updated = [...patterns, newPattern];
        await saveCustomPatterns(updated);
        setPatterns(updated);
      }
      setShowEditor(false);
      setEditingPattern(null);
    } catch (err) {
      setError(toErrorMessage(err));
    }
  };

  const handleDeletePattern = async (patternId: string) => {
    if (!confirm("Delete this pattern?")) return;
    try {
      await deleteCustomPattern(patternId);
      setPatterns(patterns.filter(p => p.id !== patternId));
    } catch (err) {
      setError(toErrorMessage(err));
    }
  };

  const handleToggleEnabled = async (patternId: string) => {
    const updated = patterns.map(p =>
      p.id === patternId ? { ...p, enabled: !p.enabled } : p
    );
    setPatterns(updated);
    try {
      await saveCustomPatterns(updated);
    } catch (err) {
      // Revert on error
      setPatterns(patterns);
      setError(toErrorMessage(err));
    }
  };

  const handleEdit = (pattern: CustomPattern) => {
    setEditingPattern(pattern);
    setShowEditor(true);
  };

  return (
    <div>
      <p style={styles.hint}>
        Define custom regex patterns to detect organization-specific data formats like employee IDs, reference numbers, or internal codes.
      </p>
      
      {error && (
        <div style={{ ...styles.errorText, marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <AlertCircle size={14} /> {error}
          <button
            onClick={() => setError("")}
            style={{ marginLeft: "auto", background: "none", border: "none", color: "inherit", cursor: "pointer" }}
          >
            <X size={14} />
          </button>
        </div>
      )}
      
      {loading ? (
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Loading patterns...</p>
      ) : (
        <>
          {/* Pattern list */}
          {patterns.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              {patterns.map(pattern => (
                <div
                  key={pattern.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "10px 12px",
                    background: "var(--bg-primary)",
                    borderRadius: 6,
                    border: "1px solid var(--border-color)",
                    opacity: pattern.enabled ? 1 : 0.6,
                  }}
                >
                  <button
                    onClick={() => handleToggleEnabled(pattern.id)}
                    style={{
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      color: pattern.enabled ? "var(--accent-success)" : "var(--text-muted)",
                      padding: 0,
                      display: "flex",
                    }}
                    title={pattern.enabled ? "Disable" : "Enable"}
                  >
                    {pattern.enabled ? <ToggleRight size={20} /> : <ToggleLeft size={20} />}
                  </button>
                  
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>
                      {pattern.name}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                      {pattern.template ? (
                        <span title={pattern._generated_pattern}>{formatTemplate(pattern.template)}</span>
                      ) : (
                        <code style={{ fontFamily: "monospace" }}>{pattern.pattern}</code>
                      )}
                      <span style={{
                        marginLeft: 8,
                        padding: "1px 6px",
                        background: "var(--bg-secondary)",
                        borderRadius: 3,
                        fontSize: 10,
                      }}>
                        {pattern.pii_type}
                      </span>
                    </div>
                  </div>
                  
                  <button
                    onClick={() => handleEdit(pattern)}
                    style={{
                      padding: "4px 10px",
                      borderRadius: 4,
                      border: "1px solid var(--border-color)",
                      background: "transparent",
                      color: "var(--text-secondary)",
                      cursor: "pointer",
                      fontSize: 12,
                    }}
                  >
                    Edit
                  </button>
                  
                  <button
                    onClick={() => handleDeletePattern(pattern.id)}
                    style={{
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      color: "var(--accent-danger)",
                      padding: 4,
                      display: "flex",
                    }}
                    title="Delete"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
          
          {/* Add/Edit form or button */}
          {showEditor ? (
            <PatternEditor
              initial={editingPattern ?? undefined}
              onSave={handleSavePattern}
              onCancel={() => { setShowEditor(false); setEditingPattern(null); }}
            />
          ) : (
            <button
              onClick={() => { setShowEditor(true); setEditingPattern(null); }}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                width: "100%",
                padding: "12px 16px",
                borderRadius: 6,
                border: "1px dashed var(--border-color)",
                background: "transparent",
                color: "var(--text-secondary)",
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              <Plus size={16} /> Add custom pattern
            </button>
          )}
          
          {patterns.length === 0 && !showEditor && (
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8, textAlign: "center" }}>
              No custom patterns defined yet. Add one to detect organization-specific data.
            </p>
          )}
        </>
      )}
    </div>
  );
}

export default CustomPatternsContent;
