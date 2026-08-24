import { useNavigate } from "react-router-dom";

interface NewAnalysisModalProps {
  open: boolean;
  onClose: () => void;
}

const WORKFLOWS = [
  {
    key: "fraud",
    title: "Fraud Transaction",
    description: "Score a live transaction across velocity, geo and device vectors.",
    icon: "gpp_maybe",
    to: "/",
  },
  {
    key: "return-risk",
    title: "Return Risk Order",
    description: "Assess an order's return probability before it ships.",
    icon: "receipt_long",
    to: "/return-risk",
  },
  {
    key: "chargeback",
    title: "Chargeback Dispute",
    description: "Compile evidence and build a merchant rebuttal.",
    icon: "shield",
    to: "/chargeback",
  },
];

export function NewAnalysisModal({ open, onClose }: NewAnalysisModalProps) {
  const navigate = useNavigate();

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="New Analysis"
    >
      <div
        className="w-full max-w-md bg-surface-container-low border border-subtle rounded p-8 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="font-headline-md text-headline-md text-on-surface">New Analysis</h2>
            <p className="font-body-md text-body-md text-outline mt-1">
              Choose a risk surface to begin.
            </p>
          </div>
          <button
            onClick={onClose}
            className="material-symbols-outlined text-outline hover:text-primary transition-colors"
            aria-label="Close"
          >
            close
          </button>
        </div>

        <div className="flex flex-col gap-3">
          {WORKFLOWS.map((w) => (
            <button
              key={w.key}
              onClick={() => {
                onClose();
                navigate(w.to);
              }}
              className="group flex items-start gap-4 p-5 border border-subtle rounded bg-surface hover:border-primary transition-colors text-left"
            >
              <span className="material-symbols-outlined text-primary mt-0.5">{w.icon}</span>
              <span>
                <span className="block font-title-lg text-title-lg text-on-surface">
                  {w.title}
                </span>
                <span className="block font-body-md text-body-md text-on-surface-variant mt-1">
                  {w.description}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}