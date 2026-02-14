import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "PromptShield — AI-Powered Document Anonymization",
  description:
    "Automatically detect and redact PII from your documents. Offline, private, AI-powered. Free trial available.",
  keywords: ["document anonymization", "PII detection", "redaction", "privacy", "GDPR", "AI"],
  metadataBase: new URL("https://promptshield.ai"),
  openGraph: {
    title: "PromptShield — AI-Powered Document Anonymization",
    description:
      "Detect and redact PII from PDFs & images. 100% offline, 40+ entity types, GDPR-ready. Free 14-day trial.",
    url: "https://promptshield.ai",
    siteName: "PromptShield",
    type: "website",
    locale: "en_US",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "PromptShield — AI-Powered Document Anonymization",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "PromptShield — AI-Powered Document Anonymization",
    description:
      "Detect and redact PII from PDFs & images. 100% offline, 40+ entity types, GDPR-ready.",
    images: ["/og-image.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
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
