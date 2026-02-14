import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — PromptShield",
  description: "How PromptShield handles your data, privacy rights, and GDPR compliance.",
};

export default function PrivacyPage() {
  return (
    <>
      <Navbar />
      <main className="pt-28 pb-20">
        <div className="mx-auto max-w-3xl px-6">
          <h1 className="text-3xl font-bold md:text-4xl">Privacy Policy</h1>
          <p className="mt-2 text-sm text-dark-400">
            Last updated: {new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
          </p>

          <div className="mt-10 space-y-8 text-dark-300 leading-relaxed text-[15px]">
            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">1. Introduction</h2>
              <p>
                PromptShield (&quot;we&quot;, &quot;us&quot;, &quot;our&quot;) is a desktop application for
                AI-powered document anonymization. This Privacy Policy explains what data we collect,
                how we use it, and your rights regarding that data.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">2. Data We Collect</h2>
              <h3 className="mb-2 text-base font-medium text-dark-200">2.1 Account Data</h3>
              <p>
                When you create an account, we collect your email address and, if you subscribe to a
                paid plan, your payment information is processed by Stripe. We never store credit card
                numbers on our servers.
              </p>
              <h3 className="mb-2 mt-4 text-base font-medium text-dark-200">2.2 License &amp; Device Data</h3>
              <p>
                To enforce license limits, we generate a machine fingerprint (a SHA-256 hash of
                hardware identifiers). This fingerprint is stored on our licensing server to track
                device activations. We do not collect your computer name, IP address at rest, or
                other identifiable hardware details.
              </p>
              <h3 className="mb-2 mt-4 text-base font-medium text-dark-200">2.3 Document Data</h3>
              <p>
                <strong className="text-white">Your documents never leave your device.</strong>{" "}
                PromptShield processes all files locally using on-device AI models. No document
                content, PII detections, or anonymized output is ever transmitted to our servers or
                any third party.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">3. How We Use Your Data</h2>
              <ul className="list-disc space-y-1 pl-6">
                <li>Authenticate your account and manage your subscription.</li>
                <li>Issue and validate software license keys.</li>
                <li>Prevent abuse of free trials (one trial per device).</li>
                <li>Communicate important product updates (opt-out available).</li>
              </ul>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">4. Third-Party Services</h2>
              <p>We use the following external services:</p>
              <ul className="list-disc space-y-1 pl-6 mt-2">
                <li><strong className="text-dark-200">Firebase Authentication</strong> — account sign-in (Google OAuth, email/password).</li>
                <li><strong className="text-dark-200">Stripe</strong> — payment processing for Pro subscriptions.</li>
                <li><strong className="text-dark-200">Google Cloud Run</strong> — hosting the licensing server.</li>
              </ul>
              <p className="mt-2">
                Each service has its own privacy policy. We do not share your data with any other
                third parties.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">5. Data Retention</h2>
              <p>
                Account data is retained for as long as your account is active. Machine fingerprints
                associated with expired license keys are deleted automatically after 90 days. You may
                request deletion of your account and all associated data at any time by contacting us.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">6. Your Rights (GDPR)</h2>
              <p>
                If you are located in the European Economic Area, you have the right to access,
                rectify, delete, or export your personal data. You also have the right to restrict or
                object to processing and to lodge a complaint with your local data protection
                authority. To exercise these rights, contact us at the email below.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">7. Security</h2>
              <p>
                We use industry-standard security measures including TLS encryption in transit,
                Ed25519 digital signatures for license keys, and bcrypt-hashed passwords. All
                infrastructure runs on SOC 2-compliant cloud providers.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">8. Children&apos;s Privacy</h2>
              <p>
                PromptShield is not intended for use by individuals under 16 years of age. We do not
                knowingly collect personal data from children.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">9. Changes to This Policy</h2>
              <p>
                We may update this Privacy Policy from time to time. We will notify you of material
                changes via email or an in-app notice. Continued use of the service after changes
                constitutes acceptance.
              </p>
            </section>

            <section>
              <h2 className="mb-3 text-xl font-semibold text-white">10. Contact</h2>
              <p>
                If you have questions about this Privacy Policy, please contact us at{" "}
                <a href="mailto:privacy@promptshield.ai" className="text-brand-400 hover:underline">
                  privacy@promptshield.ai
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
