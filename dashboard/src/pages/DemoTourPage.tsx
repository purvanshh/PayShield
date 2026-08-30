import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";

interface DemoStep {
  minute: string;
  title: string;
  page: string;
  description: string;
  action: string;
}

interface DemoGuide {
  title: string;
  duration_minutes: number;
  auto_advance_seconds: number;
  steps: DemoStep[];
}

const DEFAULT_ADVANCE = 60;

export function DemoTourPage() {
  const navigate = useNavigate();
  const [guide, setGuide] = useState<DemoGuide | null>(null);
  const [index, setIndex] = useState(0);
  const [countdown, setCountdown] = useState(DEFAULT_ADVANCE);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await client.get("/v1/meta/demo/guide");
        setGuide(res.data);
        setCountdown(res.data.auto_advance_seconds ?? DEFAULT_ADVANCE);
        setError("");
      } catch {
        setError("Demo guide unavailable — is the API reachable?");
      }
    };
    fetch();
  }, []);

  // Auto-advance: one timeout navigates to the step's page; a separate
  // interval only drives the visible countdown. Navigation is never called
  // from inside a state updater (pure function), so it fires exactly once per
  // step even under React StrictMode's double-invoked updaters.
  useEffect(() => {
    if (!guide) return;
    const seconds = guide.auto_advance_seconds ?? DEFAULT_ADVANCE;
    setCountdown(seconds);
    const navTimer = window.setTimeout(
      () => navigate(guide.steps[index].page),
      seconds * 1000,
    );
    const tick = window.setInterval(() => setCountdown((c) => Math.max(0, c - 1)), 1000);
    return () => {
      window.clearTimeout(navTimer);
      window.clearInterval(tick);
    };
  }, [guide, index, navigate]);

  const go = (next: number) => {
    setIndex(Math.max(0, Math.min((guide?.steps.length ?? 1) - 1, next)));
    setCountdown(guide?.auto_advance_seconds ?? DEFAULT_ADVANCE);
  };

  if (error) {
    return (
      <div className="border border-error/30 bg-error/5 text-error font-body-md text-body-md px-4 py-3 max-w-3xl">
        {error}
      </div>
    );
  }
  if (!guide) {
    return (
      <div className="py-24 text-center text-outline font-body-md text-body-md">
        Loading demo tour…
      </div>
    );
  }

  const step = guide.steps[index];
  const progress = Math.round(((index + 1) / guide.steps.length) * 100);

  return (
    <div className="flex flex-col max-w-3xl">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          {guide.title}
        </h1>
        <p className="font-body-lg text-body-lg text-outline">
          {guide.steps.length} stops · auto-opens each surface after{" "}
          {guide.auto_advance_seconds ?? DEFAULT_ADVANCE}s, or step through manually.
        </p>
      </div>

      {/* Progress */}
      <div className="mb-8">
        <div className="flex justify-between mb-2 font-label-caps text-label-caps text-outline">
          <span>
            Step {index + 1} of {guide.steps.length} · Minute {step.minute}
          </span>
          <span>{progress}%</span>
        </div>
        <div className="h-2 bg-surface-variant/40 rounded-sm overflow-hidden">
          <div className="h-full bg-primary transition-all duration-500" style={{ width: `${progress}%` }} />
        </div>
      </div>

      {/* Step card */}
      <div className="bg-surface-container-low border-subtle p-8 mb-8">
        <div className="flex items-start justify-between gap-6 mb-4">
          <div>
            <span className="font-label-caps text-label-caps text-primary uppercase tracking-widest">
              Minute {step.minute}
            </span>
            <h2 className="font-headline-md text-headline-md text-on-surface mt-1">
              {step.title}
            </h2>
          </div>
          <span className="font-mono-data text-mono-data text-outline shrink-0">
            auto in {countdown}s
          </span>
        </div>
        <p className="font-body-lg text-body-lg text-outline mb-6">{step.description}</p>
        <div className="border-t border-white/10 pt-4 flex items-center gap-3">
          <span className="material-symbols-outlined text-primary">flag</span>
          <p className="font-body-md text-body-md text-on-surface">{step.action}</p>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => go(index - 1)}
          disabled={index === 0}
          className="px-6 py-2 font-label-caps text-label-caps uppercase tracking-widest border border-subtle text-on-surface-variant hover:border-primary hover:text-primary disabled:opacity-30 transition-colors"
        >
          Previous
        </button>
        <div className="flex gap-4">
          <button
            onClick={() => navigate(step.page)}
            className="px-6 py-2 font-label-caps text-label-caps uppercase tracking-widest border border-primary text-primary hover:bg-primary/10 transition-colors"
          >
            Open this page
          </button>
          <button
            onClick={() => go(index + 1)}
            disabled={index === guide.steps.length - 1}
            className="px-6 py-2 font-label-caps text-label-caps uppercase tracking-widest bg-primary text-on-primary hover:bg-primary-fixed disabled:opacity-30 transition-colors"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

export default DemoTourPage;
