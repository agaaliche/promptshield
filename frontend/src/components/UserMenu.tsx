/** User menu — shows logged user info in sidebar bottom. */

import { User } from "lucide-react";
import { useLicenseStore } from "../store";
import { auth } from "../firebaseConfig";

export default function UserMenu() {
  const { licenseStatus } = useLicenseStore();

  if (!licenseStatus?.valid) return null;

  const payload = licenseStatus.payload;
  const email = payload?.email ?? auth.currentUser?.email ?? "Unknown";

  // Derive display values
  const userName = email.split("@")[0];
  const initials = userName
    .split(".")
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 2);

  return (
    <div style={styles.container}>
      <div style={styles.avatarCircle}>
        {initials || <User size={14} />}
      </div>
      <div style={styles.userInfo}>
        <div style={styles.userName}>{userName}</div>
        <div style={styles.userEmail}>{email}</div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
  },
  avatarCircle: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    background: "var(--accent-primary, #2f81f7)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.5,
    userSelect: "none",
    flexShrink: 0,
  },
  userInfo: {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
  },
  userName: {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--text-primary, #c9d1d9)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  userEmail: {
    fontSize: 10,
    color: "var(--text-muted, #8b949e)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
};
