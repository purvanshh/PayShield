import { useEffect } from "react";
import { useUiStore } from "../store/uiStore";

export function AlertToast() {
  const alertQueue = useUiStore((s) => s.alertQueue);

  useEffect(() => {
    if (alertQueue.length === 0) return;
    const last = alertQueue[alertQueue.length - 1];
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(`Fraud Alert: ${last.fraud_type}`, {
        body: `${(last.fraud_probability * 100).toFixed(0)}% probability - ${last.decision}`,
      });
    }
  }, [alertQueue]);

  if (alertQueue.length === 0) return null;

  const latest = alertQueue[alertQueue.length - 1];
  const color = latest.fraud_probability > 0.85 ? "#dc2626" : "#f59e0b";

  return (
    <div
      style={{
        position: "fixed",
        top: 16,
        right: 16,
        zIndex: 9999,
        background: "#1e293b",
        border: `1px solid ${color}`,
        borderRadius: 8,
        padding: "12px 16px",
        maxWidth: 360,
        boxShadow: "0 10px 15px rgba(0,0,0,0.5)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <span style={{ color, fontWeight: 700, fontSize: 13, textTransform: "uppercase" }}>
          {latest.fraud_type} Alert
        </span>
        <span style={{ color: "#94a3b8", fontSize: 11 }}>
          {new Date(latest.timestamp).toLocaleTimeString()}
        </span>
      </div>
      <div style={{ color: "#f8fafc", fontSize: 14, fontWeight: 600 }}>
        {(latest.fraud_probability * 100).toFixed(0)}% — {latest.decision}
      </div>
      {latest.narrative_preview && (
        <div style={{ color: "#94a3b8", fontSize: 12, marginTop: 4 }}>
          {latest.narrative_preview.slice(0, 100)}...
        </div>
      )}
    </div>
  );
}
