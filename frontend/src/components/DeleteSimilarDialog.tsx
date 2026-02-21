/**
 * DeleteSimilarDialog — shown when the user deletes a single region.
 * Lets them choose between removing just this occurrence or all matching
 * regions across the document, with an optional "don't ask again" toggle.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2, X } from "../icons";

interface Props {
  regionText: string;
  /** Total number of regions (this page + all others) with the same text */
  occurrenceCount: number;
  onDeleteOne: (neverAsk: boolean) => void;
  onDeleteAll: (neverAsk: boolean) => void;
  onCancel: () => void;
}

export default function DeleteSimilarDialog({
  regionText,
  occurrenceCount,
  onDeleteOne,
  onDeleteAll,
  onCancel,
}: Props) {
  const { t } = useTranslation();
  const [neverAsk, setNeverAsk] = useState(false);

  const truncated =
    regionText.length > 50 ? regionText.slice(0, 47) + "…" : regionText;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Delete region"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        zIndex: 9100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
          borderRadius: 10,
          padding: "24px 28px",
          maxWidth: 400,
          width: "92%",
          boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
          position: "relative",
        }}
      >
        {/* Close × */}
        <button
          onClick={onCancel}
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            background: "transparent",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            padding: 4,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 4,
          }}
          title={t("common.cancel")}
        >
          <X size={16} />
        </button>

        {/* Icon + title */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: "50%",
              background: "rgba(244,67,54,0.15)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <Trash2 size={18} color="#f44336" />
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
            {t("deleteSimilar.title")}
          </div>
        </div>

        {/* Region text preview */}
        <div
          style={{
            background: "var(--bg-primary)",
            border: "1px solid var(--border-color)",
            borderRadius: 6,
            padding: "8px 12px",
            fontSize: 13,
            color: "var(--text-secondary)",
            fontStyle: "italic",
            marginBottom: 14,
            wordBreak: "break-word",
          }}
        >
          "{truncated}"
        </div>

        {/* Body copy */}
        {occurrenceCount > 1 ? (
          <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 18px", lineHeight: 1.55 }}>
            {t("deleteSimilar.foundCount", { count: occurrenceCount })}
          </p>
        ) : (
          <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 18px", lineHeight: 1.55 }}>
            {t("deleteSimilar.onlyOne")}
          </p>
        )}

        {/* "Don't ask again" */}
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: 12,
            color: "var(--text-muted)",
            cursor: "pointer",
            marginBottom: 20,
            userSelect: "none",
          }}
        >
          <input
            type="checkbox"
            checked={neverAsk}
            onChange={(e) => setNeverAsk(e.target.checked)}
            style={{ accentColor: "var(--accent-primary)", cursor: "pointer" }}
          />
          {t("deleteSimilar.rememberChoice")}
        </label>

        {/* Action buttons */}
        <div style={{ display: "flex", gap: 8, flexDirection: "column" }}>
          {occurrenceCount > 1 && (
            <button
              onClick={() => onDeleteAll(neverAsk)}
              style={{
                padding: "9px 16px",
                fontSize: 13,
                fontWeight: 600,
                borderRadius: 6,
                border: "none",
                background: "#f44336",
                color: "white",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
              }}
            >
              <Trash2 size={14} />
              {t("deleteSimilar.deleteAll", { count: occurrenceCount })}
            </button>
          )}
          <button
            onClick={() => onDeleteOne(neverAsk)}
            style={{
              padding: "9px 16px",
              fontSize: 13,
              fontWeight: 500,
              borderRadius: 6,
              border: "1px solid var(--border-color)",
              background: "transparent",
              color: "var(--text-primary)",
              cursor: "pointer",
            }}
          >
            {t("deleteSimilar.deleteOne")}
          </button>
          <button
            onClick={onCancel}
            style={{
              padding: "7px 16px",
              fontSize: 12,
              fontWeight: 400,
              borderRadius: 6,
              border: "none",
              background: "transparent",
              color: "var(--text-muted)",
              cursor: "pointer",
            }}
          >
            {t("common.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}
