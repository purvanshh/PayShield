import { useEffect, useState } from "react";
import client from "../api/client";

interface DriftFeature {
  psi: number;
  status: string;
  samples: number;
  baseline_samples: number;
}

interface DriftReport {
  overall_status?: string;
  features?: Record<string, DriftFeature>;
}

function statusPill(status: string) {
  if (status === "DRIFT") {
    return (
      <span className="font-label-caps text-label-caps px-2 py-1 rounded bg-error/10 text-error border border-error/20 inline-block">
        DRIFT
      </span>
    );
  }
  if (status === "WARNING") {
    return (
      <span className="font-label-caps text-label-caps px-2 py-1 rounded bg-primary/10 text-primary border border-primary/20 inline-block">
        WARNING
      </span>
    );
  }
  return (
    <span className="font-label-caps text-label-caps px-2 py-1 rounded bg-secondary/10 text-secondary border border-secondary/20 inline-block">
      STABLE
    </span>
  );
}

export function DriftPage() {
  const [report, setReport] = useState<DriftReport>({});
  const [error, setError] = useState("");

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await client.get("/admin/drift/return-risk");
        setReport(res.data);
        setError("");
      } catch {
        setError("Drift report unavailable — need recent scoring samples.");
      }
    };
    fetch();
    const interval = setInterval(fetch, 20000);
    return () => clearInterval(interval);
  }, []);

  const features = Object.entries(report.features ?? {});

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          Drift Monitor
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-3xl">
          Population Stability Index across the return-risk feature surface,
          comparing the current scoring window against baseline. A detector is
          only trustworthy when it degrades honestly.
        </p>
      </div>

      {error && (
        <div className="border border-error/30 bg-error/5 text-error font-body-md text-body-md px-4 py-3 mb-6">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between mb-8 border-b border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <h3 className="font-headline-md text-headline-md text-on-surface">Feature Distribution</h3>
          {report.overall_status && statusPill(report.overall_status)}
        </div>
        <span className="font-mono-data text-mono-data text-outline">
          {features.length} features · 24h window
        </span>
      </div>

      <div className="w-full">
        <div className="grid grid-cols-12 gap-4 py-4 border-b border-white/10 font-label-caps text-label-caps text-outline mb-2">
          <div className="col-span-4 md:col-span-5">Feature</div>
          <div className="col-span-3 md:col-span-2">PSI</div>
          <div className="col-span-2 md:col-span-2 text-right">Samples</div>
          <div className="col-span-3 md:col-span-3 flex justify-end">Status</div>
        </div>

        {features.length === 0 && !error && (
          <div className="py-10 text-center text-outline font-body-md text-body-md border-b border-white/5">
            No feature samples recorded yet — score some orders to populate the monitor.
          </div>
        )}

        {features.map(([name, f]) => {
          const intensity = Math.min(1, Math.abs(f.psi) / 5);
          return (
            <div
              key={name}
              className="grid grid-cols-12 gap-4 py-4 border-b border-white/5 items-center hover:bg-surface-container-low transition-colors duration-200"
            >
              <div className="col-span-4 md:col-span-5">
                <p className="font-body-md text-body-md text-on-surface">{name}</p>
              </div>
              <div className="col-span-3 md:col-span-2 flex items-center gap-3">
                <div className="w-full h-[1px] bg-white/10 relative">
                  <div
                    className={`absolute top-0 left-0 h-full ${
                      f.status === "DRIFT" ? "bg-error-container" : "bg-primary-container"
                    }`}
                    style={{ width: `${intensity * 100}%` }}
                  />
                </div>
                <span className="font-mono-data text-mono-data text-on-surface w-14">
                  {f.psi.toFixed(4)}
                </span>
              </div>
              <div className="col-span-2 md:col-span-2 text-right font-mono-data text-mono-data text-on-surface-variant">
                {f.samples}
              </div>
              <div className="col-span-3 md:col-span-3 flex justify-end">
                {statusPill(f.status)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default DriftPage;