/** Shared styles, Section, and StatItem used across all settings sub-components. */

import type React from "react";

export const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: 32,
    height: "100%",
    overflowY: "auto",
    maxWidth: 700,
  },
  title: { fontSize: 22, fontWeight: 700, marginBottom: 24 },
  section: {
    background: "var(--bg-surface)",
    borderRadius: 8,
    marginBottom: 16,
    border: "1px solid var(--border-color)",
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "12px 16px",
    borderBottom: "1px solid var(--border-color)",
    color: "var(--text-primary)",
  },
  sectionBody: { padding: 16 },
  hint: {
    fontSize: 13,
    color: "var(--text-secondary)",
    marginBottom: 12,
    lineHeight: 1.5,
  },
  formRow: { display: "flex", gap: 8, alignItems: "center" },
  errorText: { color: "var(--accent-danger)", fontSize: 13, marginTop: 8 },
  badge: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    fontSize: 13,
    fontWeight: 500,
    padding: "4px 10px",
    background: "var(--bg-primary)",
    borderRadius: 4,
  },
  gpuTag: {
    fontSize: 10,
    fontWeight: 600,
    color: "var(--accent-success)",
    background: "rgba(76, 175, 80, 0.15)",
    padding: "1px 6px",
    borderRadius: 3,
  },
  vaultInfo: { display: "flex", flexDirection: "column", gap: 12 },
  vaultForm: {},
  statsGrid: { display: "flex", gap: 16, marginTop: 8 },
  statItem: {
    display: "flex",
    flexDirection: "column",
    background: "var(--bg-primary)",
    padding: "8px 16px",
    borderRadius: 6,
    minWidth: 100,
  },
  statValue: { fontSize: 18, fontWeight: 700 },
  statLabel: { fontSize: 11, color: "var(--text-muted)" },
  modelList: { display: "flex", flexDirection: "column", gap: 8 },
  modelItem: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 12px",
    background: "var(--bg-primary)",
    borderRadius: 6,
  },
  modelSize: { fontSize: 12, color: "var(--text-muted)", marginLeft: 8 },
  checkboxGroup: { display: "flex", flexDirection: "column", gap: 8 },
  checkboxLabel: {
    fontSize: 13,
    display: "flex",
    alignItems: "center",
    gap: 8,
    color: "var(--text-secondary)",
    cursor: "pointer",
  },
};

export function Section({
  children,
}: {
  title?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div style={styles.section}>
      <div style={styles.sectionBody}>{children}</div>
    </div>
  );
}

export function StatItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={styles.statItem}>
      <span style={styles.statValue}>{value}</span>
      <span style={styles.statLabel}>{label}</span>
    </div>
  );
}
