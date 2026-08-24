import { useEffect, useState } from "react";
import client from "../api/client";

interface AgentInfo {
  status?: string;
  last_seen?: number;
  detail?: string;
}

interface AgentsReport {
  agents?: Record<string, AgentInfo>;
  count?: number;
  timestamp?: string;
}

function AgentRow({ name, info }: { name: string; info: AgentInfo }) {
  const status = (info.status || "not_started").toUpperCase();
  const ok = status === "HEALTHY";
  const stale = status === "STALE" || status === "ERROR";
  return (
    <div className="flex items-center justify-between py-4 border-b border-white/5 hover:bg-surface-container-low transition-colors duration-200">
      <div className="flex items-center gap-4">
        <span
          className={`w-2 h-2 rounded-full ${
            ok ? "bg-secondary" : stale ? "bg-error" : "bg-outline"
          }`}
        />
        <div>
          <p className="font-body-md text-body-md text-on-surface">{name}</p>
          <p className="font-mono-data text-mono-data text-outline text-[12px]">
            {info.last_seen ? `last seen ${new Date(info.last_seen * 1000).toLocaleTimeString()}` : "no heartbeat yet"}
          </p>
        </div>
      </div>
      <span className="font-label-caps text-label-caps px-2 py-1 rounded border-subtle text-on-surface-variant inline-block">
        {status}
      </span>
    </div>
  );
}

export function AgentsPage() {
  const [report, setReport] = useState<AgentsReport>({});
  const [error, setError] = useState("");

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await client.get("/admin/agents/health");
        setReport(res.data);
        setError("");
      } catch {
        setError("Agent health unavailable.");
      }
    };
    fetch();
    const interval = setInterval(fetch, 20000);
    return () => clearInterval(interval);
  }, []);

  const agents = Object.entries(report.agents ?? {});

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          Agent Orchestration
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-3xl">
          The four live agents that power the risk path — each one deliberately
          small, with its responsibilities documented and its health exposed here.
        </p>
      </div>

      {error && (
        <div className="border border-error/30 bg-error/5 text-error font-body-md text-body-md px-4 py-3 mb-6">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between mb-8 border-b border-white/10 pb-4">
        <h3 className="font-headline-md text-headline-md text-on-surface">Live Agents</h3>
        <span className="font-mono-data text-mono-data text-secondary">
          {report.count ?? agents.length} monitored
        </span>
      </div>

      {agents.length === 0 && !error && (
        <div className="py-10 text-center text-outline font-body-md text-body-md border-b border-white/5">
          No agent heartbeats recorded yet.
        </div>
      )}

      {agents.map(([name, info]) => (
        <AgentRow key={name} name={name} info={info} />
      ))}
    </div>
  );
}

export default AgentsPage;