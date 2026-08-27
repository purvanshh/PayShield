import { Link, useParams } from "react-router-dom";

const CONTENT: Record<string, { title: string; updated: string; sections: Array<[string, string]> }> = {
  privacy: {
    title: "Privacy Policy",
    updated: "Last updated: August 2026",
    sections: [
      [
        "Data we process",
        "PayShield processes order, payment and return events routed through the merchant's Razorpay account: identifiers (account id, device fingerprint), transaction metadata (amount, category, method), and return outcomes. No raw card numbers are ever stored.",
      ],
      [
        "How data is protected",
        "Personal identifiers are masked at ingest (device ids, PII fields) before the tamper-evident audit chain is written. Access is role-based and API-key/JWT-gated with per-key rate limits.",
      ],
      [
        "Retention",
        "Feature profiles are retained for the merchant's configured window (default 6 months); audit records are immutable by design. Deletion requests are processed within 30 days via the compliance endpoints.",
      ],
      [
        "Your rights",
        "Merchants may export their decision history at any time. End users should contact the merchant for their own rights; PayShield operates as a processor on their behalf.",
      ],
    ],
  },
  terms: {
    title: "Terms of Service",
    updated: "Last updated: August 2026",
    sections: [
      [
        "Service",
        "PayShield provides a return-risk scoring service for Indian e-commerce merchants, delivered as an API and web dashboard.",
      ],
      [
        "Usage",
        "Scoring is available within the API rate limits configured for your key (1,000 requests/hour by default). Fair use applies to the dashboard and nightly reflection features.",
      ],
      [
        "Merchant responsibility",
        "The merchant retains responsibility for final dispatch decisions. PayShield outputs are recommendations — MEDIUM orders are flagged for review, not silently blocked, unless the merchant configures an automatic gate.",
      ],
      [
        "Liability",
        "Service is provided as-is for the buildathon evaluation context. Operational SLAs, error budgets and runbooks are documented in docs/ — this preview build carries no commercial SLA.",
      ],
    ],
  },
  security: {
    title: "Security Disclosure",
    updated: "Last updated: August 2026",
    sections: [
      [
        "Responsible disclosure",
        "Found a vulnerability? Report it privately at security@payshield.in with a clear reproduction. We acknowledge within 48 hours and aim for a fix within 14 days.",
      ],
      [
        "Controls",
        "PCI-DSS 90/100 · RBI 83/100 · EU AI Act 100/100 (programmatic checkers in compliance/). AES-256 at rest, TLS in transit, tamper-evident JSONL audit chain, RBAC + TOTP support.",
      ],
      [
        "Data residency",
        "All data is processed in region IN (DATA_REGION=IN). Cross-border replication is disabled by default.",
      ],
      [
        "Deployment",
        "The stack runs in Docker Compose locally and Kubernetes via ArgoCD in production. Secrets are never committed — see .env.example for the contract.",
      ],
    ],
  },
  regulatory: {
    title: "Regulatory Information",
    updated: "Last updated: August 2026",
    sections: [
      [
        "PCI-DSS",
        "90/100 score — no high-severity findings. Card data is tokenized at the gateway; PayShield never touches PAN or CVV.",
      ],
      [
        "RBI",
        "83/100 — aligned with data-localization and explainability expectations for payment risk systems. Every score carries a transparent feature breakdown for auditability.",
      ],
      [
        "EU AI Act",
        "100/100 in the programmatic checker — risk management, data governance, transparency, human oversight, accuracy, robustness and post-market monitoring controls are implemented.",
      ],
      [
        "Fairness",
        "SPD/EOD audits run on the decision surface; threshold selection is documented as a cost optimisation, not a demographic preference.",
      ],
    ],
  },
};

export function LegalPage() {
  const { slug = "privacy" } = useParams();
  const doc = CONTENT[slug] ?? CONTENT.privacy;

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          {doc.title}
        </h1>
        <p className="font-body-lg text-body-lg text-outline">{doc.updated}</p>
      </div>

      <div className="flex flex-wrap gap-3 mb-section-gap">
        {Object.entries(CONTENT).map(([key, d]) => (
          <Link
            key={key}
            to={`/legal/${key}`}
            className={`px-4 py-2 font-label-caps text-label-caps uppercase tracking-widest transition-colors duration-300 ${
              slug === key
                ? "bg-primary text-on-primary"
                : "border border-subtle text-on-surface-variant hover:border-primary hover:text-primary"
            }`}
          >
            {d.title}
          </Link>
        ))}
      </div>

      <div className="max-w-3xl flex flex-col gap-10">
        {doc.sections.map(([heading, body]) => (
          <section key={heading}>
            <h2 className="font-headline-md text-headline-md text-on-surface mb-3">{heading}</h2>
            <p className="font-body-lg text-body-lg text-on-surface-variant leading-relaxed">
              {body}
            </p>
          </section>
        ))}
      </div>
    </div>
  );
}

export default LegalPage;