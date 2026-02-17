"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  getAdminStats,
  type AdminStats,
} from "@/lib/admin";
import {
  Users,
  CreditCard,
  Monitor,
  TrendingUp,
  Loader2,
  AlertCircle,
} from "lucide-react";

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
}: {
  label: string;
  value: number | string;
  sub?: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}) {
  return (
    <div className="card-gradient p-5">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm text-dark-400">{label}</span>
        <div
          className={`rounded-lg p-2 ${color}`}
        >
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="mt-1 text-xs text-dark-500">{sub}</div>}
    </div>
  );
}

export default function AdminOverviewPage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        setLoading(true);
        const s = await getAdminStats(token);
        setStats(s);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-brand-500" />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Admin Overview</h1>
        <p className="text-sm text-dark-400">
          Platform-wide statistics and recent activity.
        </p>
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-3 rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertCircle className="h-5 w-5 shrink-0" />
          {error}
        </div>
      )}

      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total Users"
            value={stats.total_users}
            icon={Users}
            color="bg-brand-600/15 text-brand-400"
          />
          <StatCard
            label="Active Subscriptions"
            value={stats.active_subscriptions}
            sub={`${stats.total_subscriptions} total`}
            icon={CreditCard}
            color="bg-green-600/15 text-green-400"
          />
          <StatCard
            label="Active Devices"
            value={stats.active_machines}
            sub={`${stats.total_machines} total`}
            icon={Monitor}
            color="bg-purple-600/15 text-purple-400"
          />
          <StatCard
            label="Conversion Rate"
            value={
              stats.total_users > 0
                ? `${Math.round(
                    (stats.active_subscriptions / stats.total_users) * 100
                  )}%`
                : "—"
            }
            sub={`${stats.active_subscriptions} paying of ${stats.total_users}`}
            icon={TrendingUp}
            color="bg-yellow-600/15 text-yellow-400"
          />
        </div>
      )}

      {/* Quick info cards */}
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <div className="card-gradient p-6">
          <h3 className="mb-3 text-sm font-semibold text-dark-300">Quick Links</h3>
          <div className="space-y-2 text-sm">
            <a
              href="/admin/users"
              className="block text-brand-400 transition hover:text-brand-300"
            >
              → Manage Users &amp; Licenses
            </a>
            <a
              href="/admin/releases"
              className="block text-brand-400 transition hover:text-brand-300"
            >
              → Manage Releases &amp; Updates
            </a>
            <a
              href="/dashboard"
              className="block text-dark-500 transition hover:text-dark-300"
            >
              → Your Dashboard
            </a>
          </div>
        </div>

        <div className="card-gradient p-6">
          <h3 className="mb-3 text-sm font-semibold text-dark-300">System Status</h3>
          <div className="space-y-2 text-sm text-dark-400">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              Licensing API operational
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              Update server operational
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              Stripe integration active
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
