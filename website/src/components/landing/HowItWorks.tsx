import { Upload, ScanSearch, CheckCircle, Download } from "lucide-react";

const steps = [
  {
    icon: Upload,
    title: "Upload Your Document",
    description: "Drag & drop your PDF, Word, or scanned document into PromptShield.",
    color: "from-brand-600 to-blue-500",
  },
  {
    icon: ScanSearch,
    title: "AI Detects PII",
    description:
      "Our NER engine scans every page and highlights personal information — names, numbers, addresses, and more.",
    color: "from-blue-500 to-purple-500",
  },
  {
    icon: CheckCircle,
    title: "Review & Adjust",
    description:
      "Visually review each detection. Add, remove, or reclassify regions with an intuitive overlay editor.",
    color: "from-purple-500 to-pink-500",
  },
  {
    icon: Download,
    title: "Export Clean PDF",
    description:
      "Export your permanently redacted document. PII is burned out — no hidden layers, no metadata traces.",
    color: "from-pink-500 to-red-500",
  },
];

export default function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="relative border-t border-white/5 py-20 md:py-32"
    >
      <div className="mx-auto max-w-7xl px-6">
        {/* Header */}
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold md:text-4xl">
            How it <span className="gradient-text">works</span>
          </h2>
          <p className="mt-4 text-dark-400 md:text-lg">
            Four simple steps from sensitive document to clean, anonymized PDF.
          </p>
        </div>

        {/* Steps */}
        <div className="relative mt-16">
          {/* Connecting line */}
          <div className="absolute left-1/2 top-0 hidden h-full w-px -translate-x-1/2 bg-gradient-to-b from-brand-600/40 via-purple-500/40 to-pink-500/40 lg:block" />

          <div className="grid gap-12 lg:gap-0">
            {steps.map((step, i) => (
              <div
                key={step.title}
                className={`relative flex flex-col items-center gap-6 lg:flex-row lg:gap-16 ${
                  i % 2 === 1 ? "lg:flex-row-reverse" : ""
                }`}
              >
                {/* Content */}
                <div
                  className={`flex-1 ${
                    i % 2 === 0 ? "lg:text-right" : "lg:text-left"
                  }`}
                >
                  <div className="card-gradient p-6 md:p-8">
                    <div className="mb-3 text-xs font-bold uppercase tracking-widest text-dark-500">
                      Step {i + 1}
                    </div>
                    <h3 className="mb-2 text-xl font-semibold">{step.title}</h3>
                    <p className="text-sm leading-relaxed text-dark-400">
                      {step.description}
                    </p>
                  </div>
                </div>

                {/* Icon circle */}
                <div className="relative z-10 flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-dark-900 ring-4 ring-dark-950">
                  <div
                    className={`flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br ${step.color}`}
                  >
                    <step.icon className="h-6 w-6 text-white" />
                  </div>
                </div>

                {/* Empty spacer for alignment */}
                <div className="hidden flex-1 lg:block" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
