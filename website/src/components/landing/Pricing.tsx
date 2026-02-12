"use client";

import Link from "next/link";
import { Check, X } from "lucide-react";

const plans = [
  {
    name: "Free Trial",
    price: "$0",
    period: "14 days",
    description: "Try PromptShield risk-free. No credit card required.",
    featured: false,
    cta: "Start Free Trial",
    ctaHref: "/signup",
    features: [
      { text: "Full PII detection engine", included: true },
      { text: "All 40+ entity types", included: true },
      { text: "PDF & image support", included: true },
      { text: "OCR for scanned docs", included: true },
      { text: "1 device activation", included: true },
      { text: "Export redacted PDFs", included: true },
      { text: "Priority support", included: false },
      { text: "Multiple devices", included: false },
    ],
  },
  {
    name: "Pro",
    price: "$14",
    period: "/month",
    description: "Full power for professionals who handle sensitive documents daily.",
    featured: true,
    cta: "Subscribe Now",
    ctaHref: "/signup?plan=pro",
    features: [
      { text: "Full PII detection engine", included: true },
      { text: "All 40+ entity types", included: true },
      { text: "PDF & image support", included: true },
      { text: "OCR for scanned docs", included: true },
      { text: "Up to 3 device activations", included: true },
      { text: "Export redacted PDFs", included: true },
      { text: "Priority email support", included: true },
      { text: "Early access to new features", included: true },
    ],
  },
];

export default function Pricing() {
  return (
    <section
      id="pricing"
      className="relative border-t border-white/5 py-20 md:py-32"
    >
      <div className="mx-auto max-w-7xl px-6">
        {/* Header */}
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold md:text-4xl">
            Simple, <span className="gradient-text">fair pricing</span>
          </h2>
          <p className="mt-4 text-dark-400 md:text-lg">
            Start free for 14 days. Upgrade to Pro when you&apos;re ready — cancel
            anytime.
          </p>
        </div>

        {/* Cards */}
        <div className="mx-auto mt-16 grid max-w-4xl gap-8 lg:grid-cols-2">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`relative rounded-2xl p-8 ${
                plan.featured
                  ? "border-2 border-brand-500/40 bg-dark-900 glow"
                  : "card-gradient"
              }`}
            >
              {plan.featured && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gradient-to-r from-brand-600 to-purple-600 px-4 py-1 text-xs font-bold uppercase tracking-wider text-white">
                  Most Popular
                </div>
              )}

              <div className="mb-1 text-sm font-semibold text-dark-400">
                {plan.name}
              </div>
              <div className="flex items-baseline gap-1">
                <span className="text-4xl font-extrabold">{plan.price}</span>
                <span className="text-dark-400">{plan.period}</span>
              </div>
              <p className="mt-2 text-sm text-dark-400">{plan.description}</p>

              <Link
                href={plan.ctaHref}
                className={`mt-6 block w-full rounded-xl py-3 text-center text-sm font-semibold transition ${
                  plan.featured
                    ? "bg-gradient-to-r from-brand-600 to-purple-600 text-white hover:shadow-lg hover:shadow-brand-600/25"
                    : "border border-white/10 bg-white/5 text-white hover:bg-white/10"
                }`}
              >
                {plan.cta}
              </Link>

              <ul className="mt-8 space-y-3">
                {plan.features.map((f) => (
                  <li key={f.text} className="flex items-center gap-3 text-sm">
                    {f.included ? (
                      <Check className="h-4 w-4 shrink-0 text-green-500" />
                    ) : (
                      <X className="h-4 w-4 shrink-0 text-dark-600" />
                    )}
                    <span
                      className={f.included ? "text-dark-200" : "text-dark-600"}
                    >
                      {f.text}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Trust note */}
        <p className="mt-10 text-center text-sm text-dark-500">
          Secured payment with Stripe. Cancel anytime from your dashboard.
        </p>
      </div>
    </section>
  );
}
