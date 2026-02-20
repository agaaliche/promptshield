/** Top-center snackbar / toast notifications. */

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { X } from "../icons";
import { useAppStore } from "../store";
import { Z_TOAST } from "../zIndex";

export default function Snackbar() {
  const { t } = useTranslation();
  const snackbars = useAppStore((s) => s.snackbars);
  const removeSnackbar = useAppStore((s) => s.removeSnackbar);

  // Auto-dismiss non-error snackbars after 3 seconds
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    for (const snack of snackbars) {
      if (snack.type !== "error") {
        const age = Date.now() - snack.createdAt;
        const remaining = Math.max(0, 3000 - age);
        timers.push(setTimeout(() => removeSnackbar(snack.id), remaining));
      }
    }
    return () => timers.forEach(clearTimeout);
  }, [snackbars, removeSnackbar]);

  if (snackbars.length === 0) return null;

  return (
    <div style={styles.container}>
      {snackbars.map((snack) => (
        <div
          key={snack.id}
          style={{
            ...styles.snackbar,
            borderLeft: `3px solid ${snack.type === "error" ? "#f44336" : snack.type === "success" ? "#4caf50" : "var(--accent-primary)"}`,
          }}
        >
          <span style={styles.message}>{snack.message}</span>
          <button
            onClick={() => removeSnackbar(snack.id)}
            style={styles.close}
            title={t("snackbar.dismiss")}
          >
            <X size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    position: "fixed",
    top: 12,
    left: "50%",
    transform: "translateX(-50%)",
    zIndex: Z_TOAST,
    display: "flex",
    flexDirection: "column",
    gap: 6,
    pointerEvents: "none",
    maxWidth: "80vw",
  },
  snackbar: {
    pointerEvents: "auto",
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "8px 12px",
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    borderRadius: 6,
    boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
    minWidth: 240,
    maxWidth: 500,
  },
  message: {
    flex: 1,
    fontSize: 12,
    color: "var(--text-primary)",
    lineHeight: 1.4,
  },
  close: {
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 4,
    background: "transparent",
    border: "none",
    color: "var(--text-muted)",
    cursor: "pointer",
    borderRadius: 3,
  },
};
