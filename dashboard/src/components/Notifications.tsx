import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";

interface NotificationItem {
  txn_id: string;
  fraud_type?: string;
  recommended_action?: string;
  confidence?: string;
  generated_at?: string;
}

export function NotificationsButton() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await client.get("/v1/investigations");
        setItems(res.data.results || []);
      } catch {
        /* keep last known list */
      }
    };
    fetch();
    const interval = setInterval(fetch, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const unread = items.length - [...readIds].filter((id) => items.some((i) => i.txn_id === id)).length;
  const count = Math.max(unread, 0);

  const markAllRead = () => setReadIds(new Set(items.map((i) => i.txn_id)));
  const openItem = (id: string) => {
    setReadIds((prev) => new Set(prev).add(id));
    navigate("/transactions");
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex items-center justify-center w-10 h-10 rounded hover:bg-white/5 transition-colors"
        aria-label="Notifications"
      >
        <span className="material-symbols-outlined text-outline hover:text-primary transition-colors cursor-pointer">
          notifications
        </span>
        {count > 0 && (
          <span className="absolute top-0 right-0 min-w-[16px] h-4 px-1 rounded-full bg-error text-on-error text-[10px] font-label-caps flex items-center justify-center">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 md:w-96 bg-surface-container-high border border-subtle rounded shadow-2xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
            <h3 className="font-title-lg text-title-lg text-on-surface">Notifications</h3>
            <button
              onClick={markAllRead}
              className="font-label-caps text-label-caps text-primary hover:text-primary-fixed uppercase"
            >
              Mark all read
            </button>
          </div>

          <div className="max-h-[360px] overflow-y-auto">
            {items.length === 0 && (
              <div className="px-5 py-10 text-center text-outline font-body-md text-body-md">
                You're all caught up.
              </div>
            )}
            {items.map((item) => {
              const isRead = readIds.has(item.txn_id);
              return (
                <button
                  key={item.txn_id}
                  onClick={() => openItem(item.txn_id)}
                  className={`w-full text-left px-5 py-4 border-b border-white/5 hover:bg-surface-container-low transition-colors flex gap-3 ${
                    isRead ? "opacity-60" : ""
                  }`}
                >
                  <span
                    className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${
                      item.recommended_action?.toLowerCase().includes("block")
                        ? "bg-error-container"
                        : "bg-primary-container"
                    }`}
                  />
                  <div className="min-w-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-body-md text-body-md text-on-surface truncate">
                        {item.txn_id}
                      </span>
                      {!isRead && (
                        <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0 mt-1" />
                      )}
                    </div>
                    <p className="font-body-md text-body-md text-on-surface-variant text-[12px]">
                      {item.fraud_type || "Anomaly"} · {item.recommended_action || "Assessed"}
                    </p>
                    {item.generated_at && (
                      <p className="font-mono-data text-mono-data text-outline text-[11px]">
                        {new Date(item.generated_at).toLocaleString()}
                      </p>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          <button
            onClick={() => {
              setOpen(false);
              navigate("/transactions");
            }}
            className="w-full px-5 py-3 bg-surface-container-low border-t border-white/10 font-label-caps text-label-caps text-primary uppercase hover:bg-surface-container transition-colors"
          >
            View all activity
          </button>
        </div>
      )}
    </div>
  );
}