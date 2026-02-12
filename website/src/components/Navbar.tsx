"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Shield, Menu, X } from "lucide-react";

export default function Navbar() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-dark-950/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 text-xl font-bold">
          <Shield className="h-7 w-7 text-brand-500" />
          <span>
            Prompt<span className="gradient-text">Shield</span>
          </span>
        </Link>

        {/* Desktop links */}
        <div className="hidden items-center gap-8 md:flex">
          <Link href="/#features" className="text-sm text-dark-300 transition hover:text-white">
            Features
          </Link>
          <Link href="/#how-it-works" className="text-sm text-dark-300 transition hover:text-white">
            How It Works
          </Link>
          <Link href="/#pricing" className="text-sm text-dark-300 transition hover:text-white">
            Pricing
          </Link>
          <Link href="/download" className="text-sm text-dark-300 transition hover:text-white">
            Download
          </Link>
          {user ? (
            <Link
              href="/dashboard"
              className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-700"
            >
              Dashboard
            </Link>
          ) : (
            <>
              <Link href="/signin" className="text-sm text-dark-300 transition hover:text-white">
                Sign In
              </Link>
              <Link
                href="/signup"
                className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-700"
              >
                Get Started Free
              </Link>
            </>
          )}
        </div>

        {/* Mobile toggle */}
        <button className="md:hidden text-white" onClick={() => setOpen(!open)}>
          {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="border-t border-white/5 bg-dark-950 px-6 py-4 md:hidden">
          <div className="flex flex-col gap-4">
            <Link href="/#features" onClick={() => setOpen(false)} className="text-sm text-dark-300">
              Features
            </Link>
            <Link href="/#how-it-works" onClick={() => setOpen(false)} className="text-sm text-dark-300">
              How It Works
            </Link>
            <Link href="/#pricing" onClick={() => setOpen(false)} className="text-sm text-dark-300">
              Pricing
            </Link>
            <Link href="/download" onClick={() => setOpen(false)} className="text-sm text-dark-300">
              Download
            </Link>
            {user ? (
              <Link href="/dashboard" onClick={() => setOpen(false)} className="text-sm font-medium text-brand-500">
                Dashboard
              </Link>
            ) : (
              <>
                <Link href="/signin" onClick={() => setOpen(false)} className="text-sm text-dark-300">
                  Sign In
                </Link>
                <Link
                  href="/signup"
                  onClick={() => setOpen(false)}
                  className="rounded-lg bg-brand-600 px-5 py-2 text-center text-sm font-medium text-white"
                >
                  Get Started Free
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </nav>
  );
}
