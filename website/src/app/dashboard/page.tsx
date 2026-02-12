"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { signOut, auth } from "@/lib/firebase";
import { getLicenseStatus, getOrCreateUser, getMachines, deactivateMachine } from "@/lib/licensing";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import {
  Shield,
  Key,
  Monitor,
  CreditCard,
  LogOut,
  Trash2,
  Loader2,
  Copy,
  Check,
  Crown,
  Clock,
  AlertCircle,
} from "lucide-react";

interface LicenseInfo {
  plan: string;
  expires: string;
  seats: number;
  stripe_customer_id?: string;
}

interface MachineInfo {
  machine_id: string;
  activated_at: string;
  last_seen?: string;
}

function DashboardContent() {
  const { user, loading: authLoading, token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [license, setLicense] = useState<LicenseInfo | null>(null);
  const [machines, setMachines] = useState<MachineInfo[]>([]);
  const [licenseKey, setLicenseKey] = useState<string>("");
  const [loadingData, setLoadingData] = useState(true);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      setLoadingData(true);

      // Ensure user exists (creates free trial if new)
      await getOrCreateUser(token);

      // Fetch license status
      const ls = await getLicenseStatus(token);
      setLicense(ls);

      // Fetch machines
      try {
        const m = await getMachines(token);
        setMachines(Array.isArray(m) ? m : m.machines || []);
      } catch {
        // machines endpoint may not exist yet
        setMachines([]);
      }

      // Check if we need to start Stripe checkout (from signup?plan=pro)
      if (searchParams.get("checkout") === "pro") {
        await startCheckout();
      }

      // Check for Stripe success callback
      if (searchParams.get("stripe") === "success") {
        // Refresh license status to show updated plan
        const refreshed = await getLicenseStatus(token);
        setLicense(refreshed);
      }
    } catch (err: unknown) {
      setError((err as Error).message || "Failed to load dashboard data");
    } finally {
      setLoadingData(false);
    }
  }, [token, searchParams]);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/signin");
      return;
    }
    if (token) {
      fetchData();
    }
  }, [authLoading, user, token, fetchData, router]);

  async function startCheckout() {
    if (!token) return;
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ plan: "pro" }),
      });
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (err: unknown) {
      setError((err as Error).message || "Failed to start checkout");
    }
  }

  async function openBillingPortal() {
    if (!token) return;
    try {
      const res = await fetch("/api/stripe/portal", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (err: unknown) {
      setError((err as Error).message || "Failed to open billing portal");
    }
  }

  async function handleDeactivateMachine(machineId: string) {
    if (!token) return;
    try {
      await deactivateMachine(token, machineId);
      setMachines((prev) => prev.filter((m) => m.machine_id !== machineId));
    } catch (err: unknown) {
      setError((err as Error).message || "Failed to deactivate machine");
    }
  }

  async function handleSignOut() {
    await signOut(auth);
    router.push("/");
  }

  function copyKey() {
    navigator.clipboard.writeText(licenseKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  // Generate a display key from UID
  useEffect(() => {
    if (user?.uid) {
      // The actual license key is fetched from the activation endpoint,
      // but for display purposes we show a truncated version
      setLicenseKey(user.uid);
    }
  }, [user]);

  if (authLoading || loadingData) {
    return (
      <>
        <Navbar />
        <main className="flex min-h-screen items-center justify-center pt-20">
          <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
        </main>
      </>
    );
  }

  const daysRemaining = license?.expires
    ? Math.max(
        0,
        Math.ceil(
          (new Date(license.expires).getTime() - Date.now()) / 86400000
        )
      )
    : 0;

  const planLabel =
    license?.plan === "pro" ? "Pro Plan" : "Free Trial";
  const planColor =
    license?.plan === "pro" ? "text-brand-400" : "text-yellow-400";

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 pb-16">
        <div className="mx-auto max-w-5xl px-6">
          {/* Welcome header */}
          <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-bold">Dashboard</h1>
              <p className="text-sm text-dark-400">
                Welcome back, {user?.email}
              </p>
            </div>
            <button
              onClick={handleSignOut}
              className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-dark-300 transition hover:bg-white/10 hover:text-white"
            >
              <LogOut className="h-4 w-4" />
              Sign Out
            </button>
          </div>

          {error && (
            <div className="mb-6 flex items-center gap-3 rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-400">
              <AlertCircle className="h-5 w-5 shrink-0" />
              {error}
            </div>
          )}

          {/* Stats cards */}
          <div className="mb-8 grid gap-4 sm:grid-cols-3">
            {/* Plan card */}
            <div className="card-gradient p-5">
              <div className="mb-3 flex items-center gap-2 text-sm text-dark-400">
                <Crown className="h-4 w-4" />
                Current Plan
              </div>
              <div className={`text-xl font-bold ${planColor}`}>
                {planLabel}
              </div>
              {license?.plan !== "pro" && (
                <button
                  onClick={startCheckout}
                  className="mt-3 rounded-lg bg-gradient-to-r from-brand-600 to-purple-600 px-4 py-1.5 text-xs font-medium text-white transition hover:shadow-lg hover:shadow-brand-600/25"
                >
                  Upgrade to Pro — $14/mo
                </button>
              )}
            </div>

            {/* Expiry card */}
            <div className="card-gradient p-5">
              <div className="mb-3 flex items-center gap-2 text-sm text-dark-400">
                <Clock className="h-4 w-4" />
                {license?.plan === "pro" ? "Next Billing" : "Trial Expires"}
              </div>
              <div className="text-xl font-bold">
                {daysRemaining} days
              </div>
              <div className="mt-1 text-xs text-dark-500">
                {license?.expires
                  ? new Date(license.expires).toLocaleDateString()
                  : "—"}
              </div>
            </div>

            {/* Devices card */}
            <div className="card-gradient p-5">
              <div className="mb-3 flex items-center gap-2 text-sm text-dark-400">
                <Monitor className="h-4 w-4" />
                Active Devices
              </div>
              <div className="text-xl font-bold">
                {machines.length}{" "}
                <span className="text-sm font-normal text-dark-500">
                  / {license?.seats || 1}
                </span>
              </div>
            </div>
          </div>

          {/* License key section */}
          <div className="mb-8 card-gradient p-6">
            <div className="mb-4 flex items-center gap-2">
              <Key className="h-5 w-5 text-brand-500" />
              <h2 className="text-lg font-semibold">License Key</h2>
            </div>
            <p className="mb-4 text-sm text-dark-400">
              Use this key to activate PromptShield on your desktop. Open the
              app, go to the License Key tab, and paste it in.
            </p>
            <div className="flex items-center gap-3">
              <div className="flex-1 rounded-xl border border-white/10 bg-dark-900 px-4 py-3 font-mono text-sm text-dark-200 select-all overflow-x-auto">
                {licenseKey}
              </div>
              <button
                onClick={copyKey}
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm transition hover:bg-white/10"
              >
                {copied ? (
                  <Check className="h-4 w-4 text-green-500" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          {/* Activated machines */}
          <div className="mb-8 card-gradient p-6">
            <div className="mb-4 flex items-center gap-2">
              <Monitor className="h-5 w-5 text-brand-500" />
              <h2 className="text-lg font-semibold">Activated Devices</h2>
            </div>
            {machines.length === 0 ? (
              <p className="text-sm text-dark-500">
                No devices activated yet. Download the app and sign in to
                activate.
              </p>
            ) : (
              <div className="space-y-3">
                {machines.map((m) => (
                  <div
                    key={m.machine_id}
                    className="flex items-center justify-between rounded-xl border border-white/5 bg-dark-900 px-4 py-3"
                  >
                    <div>
                      <div className="text-sm font-medium">
                        {m.machine_id.slice(0, 16)}...
                      </div>
                      <div className="text-xs text-dark-500">
                        Activated{" "}
                        {new Date(m.activated_at).toLocaleDateString()}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeactivateMachine(m.machine_id)}
                      className="rounded-lg p-2 text-dark-500 transition hover:bg-red-500/10 hover:text-red-400"
                      title="Deactivate this device"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Billing section */}
          <div className="card-gradient p-6">
            <div className="mb-4 flex items-center gap-2">
              <CreditCard className="h-5 w-5 text-brand-500" />
              <h2 className="text-lg font-semibold">Billing</h2>
            </div>
            {license?.plan === "pro" ? (
              <div>
                <p className="mb-4 text-sm text-dark-400">
                  Manage your subscription, update payment method, or cancel.
                </p>
                <button
                  onClick={openBillingPortal}
                  className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-5 py-2.5 text-sm font-medium transition hover:bg-white/10"
                >
                  <CreditCard className="h-4 w-4" />
                  Manage Billing
                </button>
              </div>
            ) : (
              <div>
                <p className="mb-4 text-sm text-dark-400">
                  You&apos;re on the free trial. Upgrade to Pro for unlimited access
                  and priority support.
                </p>
                <button
                  onClick={startCheckout}
                  className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-purple-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:shadow-lg hover:shadow-brand-600/25"
                >
                  <Crown className="h-4 w-4" />
                  Upgrade to Pro — $14/mo
                </button>
              </div>
            )}
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <>
          <Navbar />
          <main className="flex min-h-screen items-center justify-center pt-20">
            <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
          </main>
        </>
      }
    >
      <DashboardContent />
    </Suspense>
  );
}
