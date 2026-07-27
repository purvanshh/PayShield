import { useEffect, useRef, useCallback } from "react";
import { useUiStore } from "../store/uiStore";
import type { AlertPayload } from "../types";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const pushAlert = useUiStore((s) => s.pushAlert);
  const maxRetries = 3;

  const connect = useCallback(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) return;

    const wsUrl = `${import.meta.env.VITE_WS_URL || "ws://localhost:8000"}/v1/stream?token=${token}`;

    try {
      const ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        retriesRef.current = 0;
        ws.send(JSON.stringify({ action: "subscribe", filter: { min_probability: 0.5 } }));
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as AlertPayload;
          if (data.fraud_probability) {
            pushAlert(data);
          }
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        if (retriesRef.current < maxRetries) {
          retriesRef.current++;
          setTimeout(connect, 3000 * retriesRef.current);
        }
      };
      ws.onerror = () => {
        ws.close();
      };
      wsRef.current = ws;
    } catch {
      /* WebSocket not supported */
    }
  }, [pushAlert]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  return { ws: wsRef.current };
}
