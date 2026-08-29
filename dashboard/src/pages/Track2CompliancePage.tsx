import { useEffect, useState } from "react";
import client from "../api/client";

interface Requirement {
  name: string;
  status: "done" | "planned";
  implementation: string;
  evidence: string;
}

interface ComplianceData {
  requirements: Requirement[];
  overall: string;
}

function statusPill(status: string) {
  if (status === "done") {
    return (
      <span className="font-label-caps text-label-caps px-2 py-1 rounded bg-secondary/10 text-secondary border border-secondary/20 inline-block">
        DONE
      </span>
    );
  }
  return (
    <span className="font-label-caps text-label-caps px-2 py-1 rounded bg-primary/10 text-primary border border-primary/20 inline-block">
      PLANNED
    </span>
  );
}

export function Track2CompliancePage() {
  const [data, setData] = useState<ComplianceData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await client.get("/v1/meta/track2-compliance");
        setData(res.data);
        setError("");
      } catch {
        setError("Compliance map unavailable — is the API reachable?");
      }
    };
    fetch();
  }, []);

  const done = data?.requirements.filter((r) => r.status === "done").length ?? 0;
  const total = data?.requirements.length ?? 0;

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          Track 2 Compliance
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-3xl">
          Every Track 2 requirement mapped to its implementation and its proof.
          Nothing is marked complete before it exists — planned enhancements are
          flagged honestly. Mirrors <code>docs/TRACK2_COMPLIANCE.md</code>.
        </p>
      </div>

      {error && (
        <div className="border border-error/30 bg-error/5 text-error font-body-md text-body-md px-4 py-3 mb-6">
          {error}
        </div>
      )}

      {data && (
        <div className="border border-secondary/30 bg-secondary/5 text-on-surface font-body-md text-body-md px-4 py-3 mb-8 rounded">
          <span className="font-bold">Overall:</span> {data.overall}
        </div>
      )}

      <div className="flex items-center justify-between mb-8 border-b border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <h3 className="font-headline-md text-headline-md text-on-surface">
            Requirement Map
          </h3>
          <span className="font-label-caps text-label-caps px-2 py-1 rounded bg-secondary/10 text-secondary border border-secondary/20 inline-block">
            {done}/{total} verified
          </span>
        </div>
        <span className="font-mono-data text-mono-data text-outline">
          core surfaces · evidence-backed
        </span>
      </div>

      {!data && !error && (
        <div className="py-10 text-center text-outline font-body-md text-body-md border-b border-white/5">
          Loading compliance map…
        </div>
      )}

      {data && (
        <div className="w-full">
          <div className="grid grid-cols-12 gap-4 py-4 border-b border-white/10 font-label-caps text-label-caps text-outline mb-2">
            <div className="col-span-12 md:col-span-3">Requirement</div>
            <div className="col-span-4 md:col-span-1">Status</div>
            <div className="col-span-8 md:col-span-4">Implementation</div>
            <div className="col-span-12 md:col-span-4">Evidence</div>
          </div>

          {data.requirements.map((req, idx) => (
            <div
              key={idx}
              className="grid grid-cols-12 gap-4 py-4 border-b border-white/5 items-center hover:bg-surface-container-low transition-colors duration-200"
            >
              <div className="col-span-12 md:col-span-3">
                <p className="font-body-md text-body-md text-on-surface">
                  {req.name}
                </p>
              </div>
              <div className="col-span-4 md:col-span-1">
                {statusPill(req.status)}
              </div>
              <div className="col-span-8 md:col-span-4">
                <p className="font-body-md text-body-md text-on-surface-variant">
                  {req.implementation}
                </p>
              </div>
              <div className="col-span-12 md:col-span-4">
                <p className="font-mono-data text-mono-data text-on-surface-variant text-sm">
                  {req.evidence}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Track2CompliancePage;
