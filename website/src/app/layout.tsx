import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "PromptShield — AI-Powered Document Anonymization",
  description:
    "Automatically detect and redact PII from your documents. Offline, private, AI-powered. Free trial available.",
  keywords: ["document anonymization", "PII detection", "redaction", "privacy", "GDPR", "AI"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
