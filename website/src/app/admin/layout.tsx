"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  Shield,
  LayoutDashboard,
  Users,
  Package,
  ArrowLeft,
  Loader2,
} from "lucide-react";

const ADMIN_EMAILS = new Set(
  (process.env.NEXT_PUBLIC_ADMIN_EMAILS || "").split(",").map((e) => e.trim()).filter(Boolean)
);

const NAV_ITEMS = [
  { href: "/admin", label: "Overview", icon: LayoutDashboard },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/releases", label: "Releases", icon: Package },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.push("/signin");
    }
  }, [loading, user, router]);

  // Gate on admin email
  const isAdmin = user?.email && ADMIN_EMAILS.has(user.email);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-dark-950">
        <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
      </div>
    );
  }

  if (!user) return null;

  if (!isAdmin) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-dark-950 px-6 text-center">
        <Shield className="mb-4 h-12 w-12 text-red-500" />
        <h1 className="mb-2 text-2xl font-bold">Access Denied</h1>
        <p className="mb-6 text-dark-400">
          You do not have admin privileges. Contact your administrator.
        </p>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-dark-950">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-white/5 bg-dark-950/95 backdrop-blur-xl">
        {/* Logo */}
        <div className="flex items-center gap-2.5 border-b border-white/5 px-6 py-5">
          <Shield className="h-6 w-6 text-brand-500" />
          <span className="text-lg font-bold">
            Prompt<span className="gradient-text">Shield</span>
          </span>
          <span className="ml-auto rounded-md bg-brand-600/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-brand-400">
            Admin
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/admin"
                ? pathname === "/admin"
                : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  active
                    ? "bg-brand-600/15 text-brand-400"
                    : "text-dark-400 hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon className="h-[18px] w-[18px]" />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Bottom */}
        <div className="border-t border-white/5 px-4 py-4">
          <Link
            href="/dashboard"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-dark-500 transition hover:bg-white/5 hover:text-dark-300"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Link>
          <div className="mt-3 px-3 text-xs text-dark-600">
            {user.email}
          </div>
        </div>
      </aside>

      {/* Main area */}
      <main className="ml-64 flex-1 p-8">{children}</main>
    </div>
  );
}
