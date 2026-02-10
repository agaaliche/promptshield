/** PII Type Picker dialog — shown after the user draws a region. */

import { PenTool, Edit3, Trash2 } from "lucide-react";
import type { PIILabelEntry } from "../types";

interface PIITypePickerProps {
  frequentLabels: PIILabelEntry[];
  otherLabels: PIILabelEntry[];
  labelConfig: PIILabelEntry[];
  usedLabels: Set<string>;
  typePickerEditMode: boolean;
  setTypePickerEditMode: (v: boolean) => void;
  typePickerNewLabel: string;
  setTypePickerNewLabel: (v: string) => void;
  onSelect: (type: string) => void;
  onCancel: () => void;
  updateLabelConfig: (updater: (prev: PIILabelEntry[]) => PIILabelEntry[]) => void;
}

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.6)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 100,
};

const dialogStyle: React.CSSProperties = {
  background: "var(--bg-secondary)",
  border: "1px solid var(--border-color)",
  borderRadius: 12,
  padding: 24,
  maxWidth: 520,
  width: "100%",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
  maxHeight: "90vh",
  overflow: "auto",
};

export default function PIITypePicker({
  frequentLabels,
  otherLabels,
  labelConfig,
  usedLabels,
  typePickerEditMode,
  setTypePickerEditMode,
  typePickerNewLabel,
  setTypePickerNewLabel,
  onSelect,
  onCancel,
  updateLabelConfig,
}: PIITypePickerProps) {
  return (
    <div style={overlayStyle}>
      <div style={dialogStyle}>
        <PenTool size={24} style={{ color: "var(--accent-primary)", marginBottom: 8 }} />
        <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
          Select PII Type
        </h3>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
          What type of sensitive data does this region contain?
        </p>

        {/* ── Frequent labels (big buttons) ── */}
        {!typePickerEditMode && frequentLabels.length > 0 && (
          <>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Frequent</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, width: "100%", marginBottom: 12 }}>
              {frequentLabels.map((entry) => (
                <button
                  key={entry.label}
                  className="btn-ghost"
                  style={{
                    padding: "10px 12px",
                    fontSize: 13,
                    fontWeight: 600,
                    borderRadius: 8,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    justifyContent: "flex-start",
                    border: `1.5px solid ${entry.color}22`,
                    background: `${entry.color}0a`,
                  }}
                  onClick={() => onSelect(entry.label)}
                >
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: entry.color, flexShrink: 0 }} />
                  {entry.label}
                </button>
              ))}
            </div>
          </>
        )}

        {/* ── Other labels (smaller buttons) ── */}
        {!typePickerEditMode && otherLabels.length > 0 && (
          <>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Other</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, width: "100%", marginBottom: 12 }}>
              {otherLabels.map((entry) => (
                <button
                  key={entry.label}
                  className="btn-ghost"
                  style={{
                    padding: "5px 8px",
                    fontSize: 11,
                    fontWeight: 500,
                    borderRadius: 6,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    justifyContent: "flex-start",
                  }}
                  onClick={() => onSelect(entry.label)}
                >
                  <span style={{ width: 7, height: 7, borderRadius: "50%", background: entry.color, flexShrink: 0 }} />
                  {entry.label}
                </button>
              ))}
            </div>
          </>
        )}

        {/* ── Edit mode ── */}
        {typePickerEditMode && (
          <div style={{ width: "100%", marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>Manage Labels</div>

            {/* Add new label */}
            <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
              <input
                type="text"
                placeholder="New label name..."
                value={typePickerNewLabel}
                onChange={(e) => setTypePickerNewLabel(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_"))}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && typePickerNewLabel.length > 0) {
                    const name = typePickerNewLabel;
                    if (labelConfig.some((x) => x.label === name)) return;
                    updateLabelConfig((prev) => [...prev, {
                      label: name,
                      frequent: false,
                      hidden: false,
                      userAdded: true,
                      color: `hsl(${Math.floor(Math.random() * 360)}, 55%, 50%)`,
                    }]);
                    setTypePickerNewLabel("");
                  }
                }}
                style={{
                  flex: 1,
                  padding: "6px 10px",
                  fontSize: 12,
                  background: "var(--bg-primary)",
                  border: "1px solid var(--border-color)",
                  borderRadius: 6,
                  color: "var(--text-primary)",
                }}
              />
              <button
                className="btn-primary"
                disabled={typePickerNewLabel.length === 0 || labelConfig.some((x) => x.label === typePickerNewLabel)}
                onClick={() => {
                  const name = typePickerNewLabel;
                  if (!name || labelConfig.some((x) => x.label === name)) return;
                  updateLabelConfig((prev) => [...prev, {
                    label: name,
                    frequent: false,
                    hidden: false,
                    userAdded: true,
                    color: `hsl(${Math.floor(Math.random() * 360)}, 55%, 50%)`,
                  }]);
                  setTypePickerNewLabel("");
                }}
                style={{ padding: "6px 12px", fontSize: 12 }}
              >
                Add
              </button>
            </div>

            {/* Label list */}
            <div style={{ maxHeight: 320, overflowY: "auto", display: "flex", flexDirection: "column", gap: 3 }}>
              {labelConfig.map((entry) => {
                const inUse = usedLabels.has(entry.label);
                return (
                  <div
                    key={entry.label}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "5px 8px",
                      borderRadius: 6,
                      background: entry.hidden ? "var(--bg-primary)" : "transparent",
                      opacity: entry.hidden ? 0.5 : 1,
                    }}
                  >
                    {/* Color dot */}
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: entry.color, flexShrink: 0 }} />

                    {/* Label name */}
                    <span style={{ flex: 1, fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>
                      {entry.label}
                      {inUse && <span style={{ fontSize: 10, color: "var(--text-secondary)", marginLeft: 4 }}>(in use)</span>}
                    </span>

                    {/* Frequent star toggle */}
                    <button
                      title={entry.frequent ? "Remove from frequent" : "Add to frequent"}
                      onClick={() => updateLabelConfig((prev) => prev.map((e) => e.label === entry.label ? { ...e, frequent: !e.frequent } : e))}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 2, fontSize: 14, color: entry.frequent ? "#f59e0b" : "var(--text-secondary)" }}
                    >
                      {entry.frequent ? "★" : "☆"}
                    </button>

                    {/* Hide/show toggle */}
                    <button
                      title={entry.hidden ? "Show label" : "Hide label"}
                      onClick={() => updateLabelConfig((prev) => prev.map((e) => e.label === entry.label ? { ...e, hidden: !e.hidden } : e))}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 2, fontSize: 12, color: "var(--text-secondary)" }}
                    >
                      {entry.hidden ? "👁" : "🙈"}
                    </button>

                    {/* Delete (only user-added AND not in use) */}
                    {entry.userAdded && !inUse && (
                      <button
                        title="Delete label"
                        onClick={() => updateLabelConfig((prev) => prev.filter((e) => e.label !== entry.label))}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: 2, fontSize: 12, color: "#ef4444" }}
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Bottom actions */}
        <div style={{ display: "flex", gap: 8, width: "100%" }}>
          <button
            className="btn-ghost btn-sm"
            onClick={() => { setTypePickerEditMode(!typePickerEditMode); setTypePickerNewLabel(""); }}
            style={{ display: "flex", alignItems: "center", gap: 4 }}
          >
            <Edit3 size={12} />
            {typePickerEditMode ? "Done" : "Edit"}
          </button>
          <div style={{ flex: 1 }} />
          <button
            className="btn-ghost btn-sm"
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
