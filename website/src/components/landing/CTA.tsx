import Link from "next/link";
import { Shield, ArrowRight } from "lucide-react";

export default function CTA() {
  return (
    <section className="relative border-t border-white/5 py-20 md:py-32">
      {/* Background glow */}
      <div className="hero-glow bg-brand-600 left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" />

      <div className="relative mx-auto max-w-4xl px-6 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-brand-500/20 bg-brand-500/10 px-4 py-1.5 text-sm text-brand-400 mb-6">
          <Shield className="h-4 w-4" />
          Ready to get started?
        </div>

        <h2 className="text-3xl font-bold md:text-5xl">
          Protect sensitive documents{" "}
          <span className="gradient-text">in minutes</span>
        </h2>
        <p className="mx-auto mt-6 max-w-xl text-lg text-dark-300">
          Start your 14-day free trial today. No credit card required, no data
          uploaded to the cloud.
        </p>

        <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
          <Link
            href="/signup"
            className="group inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-purple-600 px-8 py-3.5 text-base font-semibold text-white shadow-lg shadow-brand-600/25 transition hover:shadow-brand-600/40 hover:scale-[1.02]"
          >
            Get Started Free
            <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
          </Link>
          <Link
            href="/download"
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-8 py-3.5 text-base font-medium text-white transition hover:bg-white/10"
          >
            Download for Desktop
          </Link>
        </div>
      </div>
    </section>
  );
}
