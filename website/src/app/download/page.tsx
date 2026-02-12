import Link from "next/link";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Monitor, Apple, Shield, CheckCircle } from "lucide-react";

const platforms = [
  {
    name: "Windows",
    icon: Monitor,
    description: "Windows 10 / 11 (64-bit)",
    filename: "PromptShield-Setup.exe",
    href: "#", // TODO: Replace with actual download URL
    available: true,
  },
  {
    name: "macOS",
    icon: Apple,
    description: "macOS 12+ (Intel & Apple Silicon)",
    filename: "PromptShield.dmg",
    href: "#", // TODO: Replace with actual download URL
    available: false,
  },
];

const requirements = [
  "8 GB RAM minimum (16 GB recommended for large documents)",
  "2 GB free disk space",
  "No internet required for processing (offline-first)",
  "Internet needed only for initial activation",
];

export default function DownloadPage() {
  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-32 pb-20">
        <div className="mx-auto max-w-4xl px-6">
          {/* Header */}
          <div className="mb-12 text-center">
            <div className="mx-auto mb-4 inline-flex items-center gap-2 rounded-full border border-brand-500/20 bg-brand-500/10 px-4 py-1.5 text-sm text-brand-400">
              <Shield className="h-4 w-4" />
              Desktop Application
            </div>
            <h1 className="text-3xl font-bold md:text-4xl">
              Download <span className="gradient-text">PromptShield</span>
            </h1>
            <p className="mx-auto mt-4 max-w-xl text-dark-400 md:text-lg">
              Get the desktop app and start anonymizing documents in minutes.
              All processing happens locally on your machine.
            </p>
          </div>

          {/* Download cards */}
          <div className="mx-auto grid max-w-2xl gap-6 md:grid-cols-2">
            {platforms.map((p) => (
              <div key={p.name} className="card-gradient p-6 text-center">
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-600/10">
                  <p.icon className="h-8 w-8 text-brand-500" />
                </div>
                <h3 className="mb-1 text-lg font-semibold">{p.name}</h3>
                <p className="mb-4 text-sm text-dark-400">{p.description}</p>
                {p.available ? (
                  <a
                    href={p.href}
                    className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-purple-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:shadow-lg hover:shadow-brand-600/25"
                  >
                    Download {p.filename}
                  </a>
                ) : (
                  <div className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-6 py-2.5 text-sm text-dark-500">
                    Coming Soon
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* System requirements */}
          <div className="mx-auto mt-16 max-w-2xl">
            <h2 className="mb-6 text-xl font-semibold">System Requirements</h2>
            <ul className="space-y-3">
              {requirements.map((r) => (
                <li key={r} className="flex items-start gap-3 text-sm text-dark-300">
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
                  {r}
                </li>
              ))}
            </ul>
          </div>

          {/* Quick start */}
          <div className="mx-auto mt-16 max-w-2xl card-gradient p-8">
            <h2 className="mb-4 text-xl font-semibold">Quick Start</h2>
            <ol className="space-y-3 text-sm text-dark-300">
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/20 text-xs font-bold text-brand-400">
                  1
                </span>
                Download and install PromptShield for your platform
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/20 text-xs font-bold text-brand-400">
                  2
                </span>
                Open the app and sign in with your Google or email account
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/20 text-xs font-bold text-brand-400">
                  3
                </span>
                Upload a document and click &ldquo;Detect PII&rdquo; to start
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/20 text-xs font-bold text-brand-400">
                  4
                </span>
                Review detections and export your anonymized PDF
              </li>
            </ol>
          </div>

          {/* Need account CTA */}
          <div className="mt-12 text-center">
            <p className="text-sm text-dark-400">
              Don&apos;t have an account yet?{" "}
              <Link
                href="/signup"
                className="font-medium text-brand-500 hover:text-brand-400"
              >
                Sign up for a free trial
              </Link>
            </p>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
