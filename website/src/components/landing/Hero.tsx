import Link from "next/link";
import { Shield, Lock, Zap } from "lucide-react";

export default function Hero() {
  return (
    <section className="relative overflow-hidden pt-32 pb-20 md:pt-44 md:pb-32">
      {/* Background glows */}
      <div className="hero-glow bg-brand-600 left-1/4 top-0" />
      <div className="hero-glow bg-purple-600 right-1/4 top-20" />

      <div className="relative mx-auto max-w-7xl px-6">
        <div className="mx-auto max-w-4xl text-center">
          {/* Badge */}
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-brand-500/20 bg-brand-500/10 px-4 py-1.5 text-sm text-brand-400">
            <Shield className="h-4 w-4" />
            AI-Powered Document Protection
          </div>

          {/* Headline */}
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl md:text-6xl lg:text-7xl">
            Anonymize your documents{" "}
            <span className="gradient-text">the smart way</span>
          </h1>

          {/* Subtitle */}
          <p className="mx-auto mt-6 max-w-2xl text-lg text-dark-300 md:text-xl">
            Automatically detect and redact personal information from PDFs and
            documents. Runs entirely on your machine — your data never leaves
            your device.
          </p>

          {/* CTA buttons */}
          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Link
              href="/signup"
              className="group inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-purple-600 px-8 py-3.5 text-base font-semibold text-white shadow-lg shadow-brand-600/25 transition hover:shadow-brand-600/40 hover:scale-[1.02]"
            >
              Start Free Trial
              <Zap className="h-4 w-4 transition group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/download"
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-8 py-3.5 text-base font-medium text-white transition hover:bg-white/10"
            >
              Download App
            </Link>
          </div>

          {/* Trust badges */}
          <div className="mt-10 flex flex-wrap items-center justify-center gap-6 text-sm text-dark-400">
            <span className="flex items-center gap-1.5">
              <Lock className="h-4 w-4 text-green-500" />
              100% Offline Processing
            </span>
            <span className="flex items-center gap-1.5">
              <Shield className="h-4 w-4 text-green-500" />
              No Data Leaves Your Device
            </span>
            <span className="flex items-center gap-1.5">
              <Zap className="h-4 w-4 text-green-500" />
              14-Day Free Trial
            </span>
          </div>
        </div>

        {/* Hero illustration — app screenshot mockup */}
        <div className="relative mx-auto mt-16 max-w-5xl">
          <div className="glow rounded-2xl border border-white/10 bg-dark-900 p-2">
            <div className="rounded-xl bg-dark-800 overflow-hidden">
              {/* Fake app chrome */}
              <div className="flex items-center gap-2 border-b border-white/5 px-4 py-3">
                <div className="h-3 w-3 rounded-full bg-red-500/60" />
                <div className="h-3 w-3 rounded-full bg-yellow-500/60" />
                <div className="h-3 w-3 rounded-full bg-green-500/60" />
                <div className="ml-4 flex-1 rounded-md bg-dark-700 px-4 py-1.5 text-xs text-dark-400">
                  PromptShield — Document Anonymizer
                </div>
              </div>
              {/* App content mockup */}
              <div className="flex min-h-[340px] md:min-h-[440px]">
                {/* Sidebar mockup */}
                <div className="hidden w-56 border-r border-white/5 bg-dark-900/50 p-4 md:block">
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 rounded-lg bg-brand-600/10 px-3 py-2 text-xs text-brand-400">
                      <div className="h-4 w-4 rounded bg-brand-600/30" />
                      Documents
                    </div>
                    <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-dark-500">
                      <div className="h-4 w-4 rounded bg-dark-700" />
                      Detection
                    </div>
                    <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-dark-500">
                      <div className="h-4 w-4 rounded bg-dark-700" />
                      Export
                    </div>
                    <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-dark-500">
                      <div className="h-4 w-4 rounded bg-dark-700" />
                      Settings
                    </div>
                  </div>
                </div>
                {/* Main area */}
                <div className="flex-1 p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="text-sm font-medium text-dark-300">
                      contract_2026.pdf
                    </div>
                    <div className="flex gap-2">
                      <div className="rounded-md bg-brand-600/20 px-3 py-1 text-xs text-brand-400">
                        Detect PII
                      </div>
                      <div className="rounded-md bg-dark-700 px-3 py-1 text-xs text-dark-400">
                        Export
                      </div>
                    </div>
                  </div>
                  {/* Fake document lines with redactions */}
                  <div className="space-y-2.5 font-mono text-xs text-dark-400">
                    <div>
                      <span>Dear </span>
                      <span className="rounded bg-red-500/20 px-1 text-red-400">
                        John Smith
                      </span>
                      <span>,</span>
                    </div>
                    <div>
                      <span>This agreement is between </span>
                      <span className="rounded bg-red-500/20 px-1 text-red-400">
                        Acme Corp
                      </span>
                      <span> and </span>
                      <span className="rounded bg-orange-500/20 px-1 text-orange-400">
                        Jane Doe
                      </span>
                      <span>.</span>
                    </div>
                    <div>
                      <span>SSN: </span>
                      <span className="rounded bg-red-500/20 px-1 text-red-400">
                        123-45-6789
                      </span>
                    </div>
                    <div>
                      <span>Phone: </span>
                      <span className="rounded bg-yellow-500/20 px-1 text-yellow-400">
                        (555) 012-3456
                      </span>
                    </div>
                    <div>
                      <span>Email: </span>
                      <span className="rounded bg-purple-500/20 px-1 text-purple-400">
                        john@acme.com
                      </span>
                    </div>
                    <div className="text-dark-500">
                      Section 2: Payment Terms...
                    </div>
                    <div className="text-dark-500">
                      The total amount of{" "}
                      <span className="rounded bg-blue-500/20 px-1 text-blue-400">
                        $45,000
                      </span>{" "}
                      shall be paid...
                    </div>
                  </div>
                </div>
                {/* Right sidebar mockup */}
                <div className="hidden w-48 border-l border-white/5 bg-dark-900/50 p-4 lg:block">
                  <div className="mb-3 text-xs font-semibold text-dark-300">
                    Detected PII
                  </div>
                  <div className="space-y-2">
                    {[
                      { label: "PERSON", count: 2, color: "bg-red-500/20 text-red-400" },
                      { label: "ORG", count: 1, color: "bg-red-500/20 text-red-400" },
                      { label: "SSN", count: 1, color: "bg-red-500/20 text-red-400" },
                      { label: "PHONE", count: 1, color: "bg-yellow-500/20 text-yellow-400" },
                      { label: "EMAIL", count: 1, color: "bg-purple-500/20 text-purple-400" },
                      { label: "MONEY", count: 1, color: "bg-blue-500/20 text-blue-400" },
                    ].map((item) => (
                      <div
                        key={item.label}
                        className="flex items-center justify-between rounded-md bg-dark-800 px-2 py-1.5 text-xs"
                      >
                        <span className={`rounded px-1.5 py-0.5 ${item.color}`}>
                          {item.label}
                        </span>
                        <span className="text-dark-500">{item.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
