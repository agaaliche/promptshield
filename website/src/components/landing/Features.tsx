import {
  Shield,
  Brain,
  Wifi,
  FileSearch,
  Languages,
  Layers,
} from "lucide-react";

const features = [
  {
    icon: Brain,
    title: "AI-Powered Detection",
    description:
      "State-of-the-art NER models automatically detect names, addresses, phone numbers, SSNs, emails, and 40+ PII types.",
  },
  {
    icon: Wifi, // WifiOff not needed, Wifi with the "Off" in the text
    title: "100% Offline",
    description:
      "All processing happens locally on your machine. No cloud uploads, no third-party APIs, no data leaks. Ever.",
  },
  {
    icon: Shield,
    title: "Permanent Redaction",
    description:
      "Redactions are burned into the exported PDF. Unlike black boxes over text, our redactions are truly irreversible.",
  },
  {
    icon: FileSearch,
    title: "Smart OCR",
    description:
      "Scanned PDFs and images are automatically processed with built-in OCR so even non-searchable documents get analyzed.",
  },
  {
    icon: Languages,
    title: "Multilingual",
    description:
      "Detect PII in English, French, Italian, German, Spanish, and more. Our models understand context across languages.",
  },
  {
    icon: Layers,
    title: "Batch Processing",
    description:
      "Upload multiple documents at once. Detect, review, and export all your files in one streamlined workflow.",
  },
];

export default function Features() {
  return (
    <section
      id="features"
      className="relative border-t border-white/5 py-20 md:py-32"
    >
      <div className="mx-auto max-w-7xl px-6">
        {/* Section header */}
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold md:text-4xl">
            Redact smarter, <span className="gradient-text">not harder</span>
          </h2>
          <p className="mt-4 text-dark-400 md:text-lg">
            PromptShield combines cutting-edge AI models with a privacy-first
            architecture. Your documents stay on your device while our algorithms
            do the heavy lifting.
          </p>
        </div>

        {/* Feature grid */}
        <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.title}
              className="card-gradient p-6 transition hover:scale-[1.02]"
            >
              <div className="mb-4 inline-flex rounded-lg bg-brand-600/10 p-3">
                <f.icon className="h-6 w-6 text-brand-500" />
              </div>
              <h3 className="mb-2 text-lg font-semibold">{f.title}</h3>
              <p className="text-sm leading-relaxed text-dark-400">
                {f.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
