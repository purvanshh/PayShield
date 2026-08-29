import { useEffect, useState } from "react";
import client from "../api/client";

interface ReviewItem {
  order_id: string;
  user_id: string;
  merchant_id: string;
  score: number | null;
  tier: string;
  timestamp: string;
  reviewed: boolean;
}

interface ReviewQueueData {
  items: ReviewItem[];
  count: number;
}

export function ReviewQueuePage() {
  const [data, setData] = useState<ReviewQueueData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const fetchQueue = async () => {
    try {
      const res = await client.get("/v1/meta/review-queue");
      setData(res.data);
      setError("");
    } catch {
      setError("Review queue unavailable — is the API reachable and has any MEDIUM orders been scored?");
    }
  };

  useEffect(() => {
    fetchQueue();
  }, []);

  const markReviewed = async (orderId: string) => {
    setBusy(orderId);
    try {
      await client.post(`/v1/meta/review-queue/${orderId}/mark`);
      setData((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((i) =>
                i.order_id === orderId ? { ...i, reviewed: true } : i
              ),
            }
          : prev
      );
    } catch {
      setError("Could not mark as reviewed — try again.");
    } finally {
      setBusy(null);
    }
  };

  const items = data?.items ?? [];

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          Human-Review Queue
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-3xl">
          The latest MEDIUM return-risk decisions from the tamper-evident audit
          chain. Each row is an order a reviewer should look at before dispatch —
          mark it reviewed once an operator has acted.
        </p>
      </div>

      {error && (
        <div className="border border-error/30 bg-error/5 text-error font-body-md text-body-md px-4 py-3 mb-6">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between mb-8 border-b border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <h3 className="font-headline-md text-headline-md text-on-surface">Pending Reviews</h3>
          <span className="font-label-caps text-label-caps px-2 py-1 rounded bg-primary/10 text-primary border border-primary/20 inline-block">
            {items.filter((i) => !i.reviewed).length} to review
          </span>
        </div>
        <span className="font-mono-data text-mono-data text-outline">
          {items.length} shown · from audit chain
        </span>
      </div>

      {!data && !error && (
        <div className="py-24 text-center text-outline font-body-md text-body-md">
          Loading review queue…
        </div>
      )}

      {items.length === 0 && data && (
        <div className="py-24 text-center text-outline font-body-md text-body-md border-b border-white/5">
          No MEDIUM return-risk decisions yet — score an order that lands in the
          review tier and it will appear here.
        </div>
      )}

      {items.length > 0 && (
        <div className="w-full">
          <div className="grid grid-cols-12 gap-4 py-4 border-b border-white/10 font-label-caps text-label-caps text-outline mb-2">
            <div className="col-span-12 md:col-span-3">Order</div>
            <div className="col-span-4 md:col-span-2">User</div>
            <div className="col-span-4 md:col-span-2">Score</div>
            <div className="col-span-4 md:col-span-2">Merchant</div>
            <div className="col-span-6 md:col-span-2 text-right">Status</div>
            <div className="col-span-6 md:col-span-1" />
          </div>

          {items.map((item) => (
            <div
              key={item.order_id}
              className="grid grid-cols-12 gap-4 py-4 border-b border-white/5 items-center hover:bg-surface-container-low transition-colors duration-200"
            >
              <div className="col-span-12 md:col-span-3">
                <p className="font-mono-data text-mono-data text-on-surface">{item.order_id}</p>
                <p className="font-body-md text-body-md text-outline">
                  {new Date(item.timestamp).toLocaleString()}
                </p>
              </div>
              <div className="col-span-4 md:col-span-2 font-body-md text-body-md text-on-surface-variant">
                {item.user_id}
              </div>
              <div className="col-span-4 md:col-span-2 font-mono-data text-mono-data text-primary">
                {item.score != null ? Number(item.score).toFixed(4) : "—"}
              </div>
              <div className="col-span-4 md:col-span-2 font-body-md text-body-md text-on-surface-variant">
                {item.merchant_id}
              </div>
              <div className="col-span-6 md:col-span-2 text-right">
                <span
                  className={`font-label-caps text-label-caps px-2 py-1 rounded inline-block ${
                    item.reviewed
                      ? "bg-secondary/10 text-secondary border border-secondary/20"
                      : "bg-primary/10 text-primary border border-primary/20"
                  }`}
                >
                  {item.reviewed ? "REVIEWED" : "PENDING"}
                </span>
              </div>
              <div className="col-span-6 md:col-span-1 text-right">
                {!item.reviewed && (
                  <button
                    onClick={() => markReviewed(item.order_id)}
                    disabled={busy === item.order_id}
                    className="font-label-caps text-label-caps uppercase tracking-widest px-3 py-1 border border-primary text-primary hover:bg-primary/10 disabled:opacity-30 transition-colors"
                  >
                    {busy === item.order_id ? "…" : "Mark"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ReviewQueuePage;
