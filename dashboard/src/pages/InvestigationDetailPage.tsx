import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import client from "../api/client";
import type { InvestigationReport } from "../types";
import { SubgraphGraph } from "../components/SubgraphGraph";
import { InvestigationCard } from "../components/InvestigationCard";

export function InvestigationDetailPage() {
  const { txnId } = useParams<{ txnId: string }>();
  const [report, setReport] = useState<InvestigationReport | null>(null);

  useEffect(() => {
    if (!txnId) return;
    client.get(`/v1/investigation/${txnId}`).then((res) => setReport(res.data)).catch(() => {});
  }, [txnId]);

  if (!report) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "#0f172a", color: "#94a3b8" }}>
        Loading investigation...
      </div>
    );
  }

  return (
    <div style={{ padding: 24, background: "#0f172a", minHeight: "100vh" }}>
      <h1 style={{ color: "#f8fafc", fontSize: 24, marginBottom: 24 }}>
        Investigation: {report.txn_id}
      </h1>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 60%", minWidth: 400 }}>
          <SubgraphGraph nodes={[]} edges={[]} />
        </div>
        <div style={{ flex: "1 1 35%", minWidth: 300 }}>
          <InvestigationCard report={report} />
        </div>
      </div>
    </div>
  );
}
