import { useState } from "react";

const FAQS = [
  {
    q: "How do I score an order for return risk?",
    a: "Open Return Risk from the top navigation and choose a preset, or POST /v1/return/score with your order details. The response includes the full feature breakdown and recommendations.",
  },
  {
    q: "What do the risk tiers mean?",
    a: "LOW ships normally. MEDIUM flags for merchant review before dispatch. HIGH requires prepaid / signature-on-delivery. Thresholds are config-driven in configs/return_risk_rules.yaml.",
  },
  {
    q: "How is the cost model computed?",
    a: "The Cost Model page translates precision and recall into rupees using Indian e-commerce unit economics — see docs/COST_MODEL.md for the assumptions and calculator.",
  },
  {
    q: "Why does the fraud dashboard look empty?",
    a: "It lists investigated anomalies. Score a suspicious transaction or seed the demo data (python scripts/seed_demo_data.py) to populate it.",
  },
  {
    q: "How do I reset my password?",
    a: "Contact your institutional administrator. Default local credentials are documented in .env.example under ADMIN_USERNAME / ADMIN_PASSWORD.",
  },
  {
    q: "Where can I see the drift / agent health?",
    a: "Both are in the sidebar under Operations: Drift Monitor streams PSI across the feature surface, and Agents shows the four live orchestration agents.",
  },
];

const CHANNELS = [
  {
    icon: "forum",
    title: "Documentation",
    body: "docs/API_REFERENCE.md and docs/TRACK2_ARCHITECTURE.md",
  },
  {
    icon: "mail",
    title: "Institutional Support",
    body: "support@payshield.in — monitored during business hours",
  },
  {
    icon: "bug_report",
    title: "Report an issue",
    body: "Every decision leaves an audit trail; attach the order or txn id",
  },
];

export function SupportPage() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          Support
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-2xl">
          Answers, channels and system status — everything an institutional
          operator needs to stay unblocked.
        </p>
      </div>

      {/* Channels */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-gutter mb-section-gap">
        {CHANNELS.map((c) => (
          <div key={c.title} className="border-subtle bg-surface p-8">
            <span className="material-symbols-outlined text-primary mb-4">{c.icon}</span>
            <h4 className="font-title-lg text-title-lg text-on-surface mb-2">{c.title}</h4>
            <p className="font-body-md text-body-md text-on-surface-variant">{c.body}</p>
          </div>
        ))}
      </section>

      {/* FAQ */}
      <section className="mb-section-gap">
        <div className="flex justify-between items-end mb-8 border-b border-white/10 pb-4">
          <h3 className="font-headline-md text-headline-md text-on-surface">
            Frequently Asked Questions
          </h3>
        </div>
        <div className="flex flex-col">
          {FAQS.map((faq, i) => (
            <div key={faq.q} className="border-b border-white/5">
              <button
                onClick={() => setOpen(open === i ? null : i)}
                className="w-full flex items-center justify-between py-5 text-left hover:bg-surface-container-low transition-colors px-4"
              >
                <span className="font-title-lg text-title-lg text-on-surface">{faq.q}</span>
                <span
                  className={`material-symbols-outlined text-outline transition-transform ${
                    open === i ? "rotate-180" : ""
                  }`}
                >
                  expand_more
                </span>
              </button>
              {open === i && (
                <p className="font-body-md text-body-md text-on-surface-variant px-4 pb-6 max-w-3xl">
                  {faq.a}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* System snapshot */}
      <section className="border-subtle bg-surface p-8">
        <h3 className="font-title-lg text-title-lg text-on-surface mb-2 mb-4">System Snapshot</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
          <div className="flex items-center gap-4">
            <span className="w-2 h-2 rounded-full bg-secondary" />
            <span className="font-body-md text-body-md text-on-surface-variant">
              Scoring engines nominal
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span className="w-2 h-2 rounded-full bg-secondary" />
            <span className="font-body-md text-body-md text-on-surface-variant">
              Audit chain tamper-proof
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span className="w-2 h-2 rounded-full bg-primary" />
            <span className="font-body-md text-body-md text-on-surface-variant">
              Reflection running nightly
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}

export default SupportPage;