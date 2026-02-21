/** Top-center snackbar / toast notifications. */

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { X, CheckCircle2, AlertCircle, InfoCircle } from "../icons";
import { useAppStore } from "../store";
import { Z_TOAST } from "../zIndex";
import type { SnackbarItem } from "../types";

const TYPE_CONFIG: Record<
  SnackbarItem["type"],
  { bg: string; Icon: React.ComponentType<{ size?: number }> }
> = {
  success: { bg: "#2e7d32", Icon: CheckCircle2 },
  error:   { bg: "#c62828", Icon: AlertCircle },
  info:    { bg: "#1565c0", Icon: InfoCircle },
};

export default function Snackbar() {
  const { t } = useTranslation();
  const snackbars = useAppStore((s) => s.snackbars);
  const removeSnackbar = useAppStore((s) => s.removeSnackbar);

  // Auto-dismiss non-error snackbars after 4 seconds
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    for (const snack of snackbars) {
      if (snack.type !== "error") {
        const age = Date.now() - snack.createdAt;
        const remaining = Math.max(0, 4000 - age);
        timers.push(setTimeout(() => removeSnackbar(snack.id), remaining));
      }
    }
    return () => timers.forEach(clearTimeout);
  }, [snackbars, removeSnackbar]);

  if (snackbars.length === 0) return null;

  return (
    <div style={styles.container}>
      {snackbars.map((snack) => {
        const { bg, Icon } = TYPE_CONFIG[snack.type];
        return (
          <div key={snack.id} style={{ ...styles.snackbar, background: bg }}>
            <Icon size={16} />
            <span style={styles.message}>{snack.message}</span>
            <button
              onClick={() => removeSnackbar(snack.id)}
              style={styles.close}
              title={t("snackbar.dismiss")}
              aria-label={t("snackbar.dismiss")}
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    position: "fixed",
    // Position below the top toolbar (~49 px tall)
    top: 50,
    left: "50%",
    transform: "translateX(-50%)",
    zIndex: Z_TOAST,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    pointerEvents: "none",
    width: "min(480px, calc(100vw - 48px))",
  },
  snackbar: {
    pointerEvents: "auto",
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 14px",
    borderRadius: 6,
    boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
    color: "#fff",
  },
  message: {
    flex: 1,
    fontSize: 13,
    color: "#fff",
    lineHeight: 1.4,
    fontWeight: 500,
  },
  close: {
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "3px 5px",
    background: "rgba(255,255,255,0.18)",
    border: "none",
    color: "#fff",
    cursor: "pointer",
    borderRadius: 4,
  },
};
