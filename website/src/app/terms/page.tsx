import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — PromptShield",
  description: "Terms and conditions for using the PromptShield document anonymization software.",
};

export default function TermsPage() {
  return (
    <>
      <Navbar />
      <main className="pt-28 pb-20">
        <div className="mx-auto max-w-3xl px-6">
          <h1 className="text-3xl font-bold md:text-4xl">Terms of Service</h1>
          <p className="mt-2 text-sm text-dark-400">
            Last updated: {new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
          </p>

          <div className="mt-10 space-y-8 text-dark-300 leading-relaxed text-[15px]">
            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">1. Acceptance of Terms</h2>
              <p>
                By downloading, installing, or using PromptShield (&quot;the Software&quot;), you
                agree to be bound by these Terms of Service (&quot;Terms&quot;). If you do not agree,
                do not use the Software.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">2. Description of Service</h2>
              <p>
                PromptShield is a desktop application that uses on-device AI models to detect and
                redact personally identifiable information (PII) in documents. All document processing
                occurs locally on your device. The Software requires a valid license key obtained
                through our licensing server.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">3. License Grant</h2>
              <p>
                Subject to these Terms, we grant you a limited, non-exclusive, non-transferable,
                revocable license to use the Software on up to the number of devices permitted by
                your subscription plan (1 device for Free Trial, up to 3 for Pro).
              </p>
              <p className="mt-2">You may not:</p>
              <ul className="list-disc space-y-1 pl-6 mt-1">
                <li>Reverse engineer, decompile, or disassemble the Software.</li>
                <li>Redistribute, sublicense, or resell the Software.</li>
                <li>Circumvent or tamper with the licensing mechanism.</li>
                <li>Use the Software for any unlawful purpose.</li>
              </ul>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">4. Free Trial</h2>
              <p>
                New users receive a 14-day free trial with full functionality. The trial is limited
                to one per device. If you do not subscribe to a paid plan before the trial expires,
                your access to the Software will be suspended.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">5. Subscriptions &amp; Billing</h2>
              <p>
                Pro subscriptions are billed monthly or annually through Stripe. Prices are listed on
                our website and may change with 30 days&apos; notice. All payments are non-refundable
                except where required by law.
              </p>
              <p className="mt-2">
                You may cancel your subscription at any time from your dashboard. Cancellation takes
                effect at the end of the current billing period. Your license key will remain valid
                until the period ends.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">6. Account Responsibilities</h2>
              <p>
                You are responsible for maintaining the confidentiality of your account credentials.
                You must not share your license key or account with others. We reserve the right to
                revoke licenses if we detect unauthorized sharing or abuse.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">7. Intellectual Property</h2>
              <p>
                The Software, including all code, models, documentation, and branding, is owned by
                PromptShield and protected by copyright and intellectual property laws. Your
                subscription grants a usage license only — no ownership of any part of the Software
                is transferred.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">8. Disclaimer of Warranties</h2>
              <p>
                THE SOFTWARE IS PROVIDED &quot;AS IS&quot; WITHOUT WARRANTY OF ANY KIND. WHILE WE
                STRIVE FOR ACCURATE PII DETECTION, WE DO NOT GUARANTEE THAT ALL SENSITIVE
                INFORMATION WILL BE IDENTIFIED. YOU ARE RESPONSIBLE FOR REVIEWING ANONYMIZED OUTPUT
                BEFORE SHARING.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">9. Limitation of Liability</h2>
              <p>
                TO THE MAXIMUM EXTENT PERMITTED BY LAW, PROMPTSHIELD SHALL NOT BE LIABLE FOR ANY
                INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES ARISING FROM YOUR
                USE OF THE SOFTWARE. OUR TOTAL LIABILITY SHALL NOT EXCEED THE AMOUNT YOU PAID IN THE
                12 MONTHS PRECEDING THE CLAIM.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">10. Termination</h2>
              <p>
                We may suspend or terminate your access to the Software if you violate these Terms.
                Upon termination, your license key will be revoked and you must uninstall the
                Software. Sections 7–9 survive termination.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">11. Governing Law</h2>
              <p>
                These Terms are governed by the laws of France. Any disputes shall be resolved in the
                courts of Paris, France.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">12. Changes to These Terms</h2>
              <p>
                We may update these Terms from time to time. Material changes will be communicated
                via email or in-app notice at least 30 days before taking effect. Continued use after
                changes constitutes acceptance.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">13. Contact</h2>
              <p>
                For questions about these Terms, contact us at{" "}
                <a href="mailto:legal@promptshield.ai" className="text-brand-400 hover:underline">
                  legal@promptshield.ai
                </a>.
              </p>
            </section>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
