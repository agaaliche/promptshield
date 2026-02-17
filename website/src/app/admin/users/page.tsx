"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  getAdminUsers,
  getAdminUserDetail,
  revokeUserLicenses,
  type AdminUser,
  type AdminUserDetail,
} from "@/lib/admin";
import {
  Users,
  Search,
  ChevronLeft,
  ChevronRight,
  Monitor,
  Key,
  CreditCard,
  AlertTriangle,
  Loader2,
  AlertCircle,
  X,
  Trash2,
  Eye,
  Crown,
} from "lucide-react";

const PAGE_SIZE = 25;

export default function AdminUsersPage() {
  const { token } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [selectedUser, setSelectedUser] = useState<AdminUserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [revoking, setRevoking] = useState(false);

  const fetchUsers = useCallback(async () => {
    if (!token) return;
    try {
      setLoading(true);
      const u = await getAdminUsers(token, page * PAGE_SIZE, PAGE_SIZE);
      setUsers(u);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token, page]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  async function viewUser(userId: string) {
    if (!token) return;
    try {
      setDetailLoading(true);
      const detail = await getAdminUserDetail(token, userId);
      setSelectedUser(detail);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleRevoke(userId: string) {
    if (!token) return;
    if (!confirm("This will revoke ALL license keys and deactivate ALL machines for this user. Continue?")) return;
    try {
      setRevoking(true);
      const result = await revokeUserLicenses(token, userId);
      alert(`Revoked ${result.revoked_keys} keys, deactivated ${result.deactivated_machines} machines.`);
      // Refresh detail
      const detail = await getAdminUserDetail(token, userId);
      setSelectedUser(detail);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRevoking(false);
    }
  }

  const filtered = search
    ? users.filter((u) =>
        u.email.toLowerCase().includes(search.toLowerCase())
      )
    : users;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Users &amp; Licenses</h1>
        <p className="text-sm text-dark-400">
          View all users, their subscriptions, and activated devices.
        </p>
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-3 rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertCircle className="h-5 w-5 shrink-0" />
          {error}
          <button onClick={() => setError("")} className="ml-auto">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Search + pagination */}
      <div className="mb-4 flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-dark-500" />
          <input
            type="text"
            placeholder="Filter by email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-dark-900 py-2 pl-9 pr-3 text-sm placeholder-dark-500 outline-none focus:border-brand-500/50"
          />
        </div>
        <div className="flex items-center gap-1 text-sm text-dark-400">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
            className="rounded-lg p-2 transition hover:bg-white/5 disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="px-2">Page {page + 1}</span>
          <button
            disabled={users.length < PAGE_SIZE}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg p-2 transition hover:bg-white/5 disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Users table */}
      {loading ? (
        <div className="flex h-40 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-brand-500" />
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-white/5">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/5 bg-dark-900/60">
                <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400">
                  Email
                </th>
                <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400">
                  Plan
                </th>
                <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400 text-center">
                  Devices
                </th>
                <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400">
                  Joined
                </th>
                <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr
                  key={u.id}
                  className="border-b border-white/5 transition hover:bg-white/[0.02]"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium">{u.email}</div>
                  </td>
                  <td className="px-4 py-3">
                    {u.has_billing ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-brand-600/15 px-2.5 py-0.5 text-xs font-medium text-brand-400">
                        <Crown className="h-3 w-3" />
                        Pro
                      </span>
                    ) : u.trial_used ? (
                      <span className="inline-flex items-center rounded-full bg-dark-800 px-2.5 py-0.5 text-xs text-dark-400">
                        Expired
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-yellow-600/15 px-2.5 py-0.5 text-xs text-yellow-400">
                        Trial
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center text-dark-400">
                    {u.machine_count}
                  </td>
                  <td className="px-4 py-3 text-dark-500">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => viewUser(u.id)}
                      className="rounded-lg p-1.5 text-dark-400 transition hover:bg-white/5 hover:text-white"
                      title="View details"
                    >
                      <Eye className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-8 text-center text-sm text-dark-500"
                  >
                    {search ? "No users match your filter." : "No users found."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* User detail modal */}
      {(selectedUser || detailLoading) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-dark-900 p-6 shadow-2xl">
            {detailLoading ? (
              <div className="flex h-40 items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-brand-500" />
              </div>
            ) : selectedUser ? (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-lg font-bold">User Details</h2>
                  <button
                    onClick={() => setSelectedUser(null)}
                    className="rounded-lg p-1.5 text-dark-400 transition hover:bg-white/10 hover:text-white"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Info */}
                <div className="mb-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-dark-400">Email</span>
                    <span className="font-medium">{selectedUser.email}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-dark-400">Joined</span>
                    <span>{new Date(selectedUser.created_at).toLocaleDateString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-dark-400">Stripe</span>
                    <span className="font-mono text-xs text-dark-500">
                      {selectedUser.stripe_customer_id || "—"}
                    </span>
                  </div>
                </div>

                {/* Subscriptions */}
                <div className="mb-4">
                  <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-dark-300">
                    <CreditCard className="h-4 w-4" />
                    Subscriptions ({selectedUser.subscriptions.length})
                  </h3>
                  {selectedUser.subscriptions.length === 0 ? (
                    <p className="text-xs text-dark-500">No subscriptions.</p>
                  ) : (
                    <div className="space-y-2">
                      {selectedUser.subscriptions.map((s) => (
                        <div
                          key={s.id}
                          className="flex items-center justify-between rounded-lg border border-white/5 bg-dark-950 px-3 py-2 text-xs"
                        >
                          <div>
                            <span className="font-medium capitalize">{s.plan}</span>
                            <span className="ml-2 text-dark-500">{s.status}</span>
                          </div>
                          <div className="text-dark-500">
                            {s.seats} seat{s.seats !== 1 ? "s" : ""}
                            {s.period_end && ` · ends ${new Date(s.period_end).toLocaleDateString()}`}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Machines */}
                <div className="mb-4">
                  <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-dark-300">
                    <Monitor className="h-4 w-4" />
                    Machines ({selectedUser.machines.length})
                  </h3>
                  {selectedUser.machines.length === 0 ? (
                    <p className="text-xs text-dark-500">No machines activated.</p>
                  ) : (
                    <div className="space-y-2">
                      {selectedUser.machines.map((m) => (
                        <div
                          key={m.id}
                          className="flex items-center justify-between rounded-lg border border-white/5 bg-dark-950 px-3 py-2 text-xs"
                        >
                          <div>
                            <span className="font-medium">
                              {m.machine_name || m.machine_fingerprint}
                            </span>
                            <span
                              className={`ml-2 ${
                                m.is_active ? "text-green-400" : "text-dark-500"
                              }`}
                            >
                              {m.is_active ? "active" : "inactive"}
                            </span>
                          </div>
                          <div className="text-dark-500">
                            {m.last_validated
                              ? `seen ${new Date(m.last_validated).toLocaleDateString()}`
                              : "—"}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex justify-end gap-3 border-t border-white/5 pt-4">
                  <button
                    onClick={() => handleRevoke(selectedUser.id)}
                    disabled={revoking}
                    className="inline-flex items-center gap-2 rounded-lg bg-red-500/10 px-4 py-2 text-sm font-medium text-red-400 transition hover:bg-red-500/20 disabled:opacity-50"
                  >
                    {revoking ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <AlertTriangle className="h-4 w-4" />
                    )}
                    Revoke All Licenses
                  </button>
                  <button
                    onClick={() => setSelectedUser(null)}
                    className="rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm transition hover:bg-white/10"
                  >
                    Close
                  </button>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
