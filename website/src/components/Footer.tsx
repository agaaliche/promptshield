import Link from "next/link";
import { Shield } from "lucide-react";

export default function Footer() {
  return (
    <footer className="border-t border-white/5 bg-dark-950">
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-8 md:grid-cols-4">
          {/* Brand */}
          <div className="md:col-span-1">
            <Link href="/" className="flex items-center gap-2 text-lg font-bold">
              <Shield className="h-6 w-6 text-brand-500" />
              <span>
                Prompt<span className="gradient-text">Shield</span>
              </span>
            </Link>
            <p className="mt-4 text-sm text-dark-400 leading-relaxed">
              AI-powered document anonymization. Detect and redact PII offline, with complete
              privacy.
            </p>
          </div>

          {/* Product */}
          <div>
            <h4 className="mb-4 text-sm font-semibold uppercase tracking-wider text-dark-300">
              Product
            </h4>
            <ul className="space-y-2 text-sm text-dark-400">
              <li>
                <Link href="/#features" className="transition hover:text-white">
                  Features
                </Link>
              </li>
              <li>
                <Link href="/#pricing" className="transition hover:text-white">
                  Pricing
                </Link>
              </li>
              <li>
                <Link href="/download" className="transition hover:text-white">
                  Download
                </Link>
              </li>
              <li>
                <Link href="/#how-it-works" className="transition hover:text-white">
                  How It Works
                </Link>
              </li>
            </ul>
          </div>

          {/* Account */}
          <div>
            <h4 className="mb-4 text-sm font-semibold uppercase tracking-wider text-dark-300">
              Account
            </h4>
            <ul className="space-y-2 text-sm text-dark-400">
              <li>
                <Link href="/signin" className="transition hover:text-white">
                  Sign In
                </Link>
              </li>
              <li>
                <Link href="/signup" className="transition hover:text-white">
                  Sign Up
                </Link>
              </li>
              <li>
                <Link href="/dashboard" className="transition hover:text-white">
                  Dashboard
                </Link>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="mb-4 text-sm font-semibold uppercase tracking-wider text-dark-300">
              Legal
            </h4>
            <ul className="space-y-2 text-sm text-dark-400">
              <li>
                <Link href="/privacy" className="transition hover:text-white">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link href="/terms" className="transition hover:text-white">
                  Terms of Service
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 border-t border-white/5 pt-8 text-center text-sm text-dark-500">
          &copy; {new Date().getFullYear()} PromptShield. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
