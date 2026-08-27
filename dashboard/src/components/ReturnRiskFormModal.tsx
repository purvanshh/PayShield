import { useState } from "react";
import client from "../api/client";
import type { ReturnScoreData } from "../types";

interface ReturnRiskFormModalProps {
  open: boolean;
  onClose: () => void;
  onScored?: (result: ReturnScoreData) => void;
}

const CATEGORIES = ["fashion", "electronics", "grocery", "home", "beauty", "books", "sports"];
const PAYMENT_METHODS = ["UPI", "CARD", "COD", "NETBANKING", "WALLET"];

interface FormState {
  order_id: string;
  user_id: string;
  merchant_id: string;
  amount: string;
  category: string;
  payment_method: string;
  cod_flag: boolean;
  device_fingerprint: string;
}

const INITIAL: FormState = {
  order_id: "",
  user_id: "",
  merchant_id: "",
  amount: "",
  category: "fashion",
  payment_method: "UPI",
  cod_flag: false,
  device_fingerprint: "",
};

const inputCls =
  "w-full bg-surface px-3 py-2 border border-subtle rounded-sm text-on-surface font-body-md text-body-md focus:outline-none focus:border-primary transition-colors placeholder:text-outline/60";

const labelCls = "block font-label-caps text-label-caps text-outline mb-1.5 uppercase";

export function ReturnRiskFormModal({ open, onClose, onScored }: ReturnRiskFormModalProps) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ReturnScoreData | null>(null);

  if (!open) return null;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const reset = () => {
    setForm(INITIAL);
    setError("");
    setResult(null);
    setSubmitting(false);
  };

  const close = () => {
    reset();
    onClose();
  };

  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const res = await client.post("/v1/return/score", {
        order_id: form.order_id.trim(),
        user_id: form.user_id.trim(),
        merchant_id: form.merchant_id.trim(),
        amount: Number(form.amount),
        category: form.category,
        payment_method: form.payment_method,
        cod_flag: form.cod_flag,
        device_fingerprint: form.device_fingerprint.trim(),
      });
      setResult(res.data.data);
      onScored?.(res.data.data);
    } catch {
      setError("Scoring failed — verify your session and inputs, then retry.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={close}
      role="dialog"
      aria-modal="true"
      aria-label="New Return Risk Analysis"
    >
      <div
        className="w-full max-w-lg bg-surface-container-low border border-subtle rounded p-8 shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="font-headline-md text-headline-md text-on-surface">
              New Return Risk Analysis
            </h2>
            <p className="font-body-md text-body-md text-outline mt-1">
              Assess an order's return probability before it ships.
            </p>
          </div>
          <button
            onClick={close}
            className="material-symbols-outlined text-outline hover:text-primary transition-colors"
            aria-label="Close"
          >
            close
          </button>
        </div>

        {result ? (
          <div>
            <div className="border-subtle bg-surface p-6 mb-6">
              <div className="flex items-center justify-between mb-4">
                <span className="font-label-caps text-label-caps text-outline uppercase">
                  {result.order_id}
                </span>
                <span
                  className={`font-label-caps text-label-caps px-2 py-1 rounded ${
                    result.risk_tier === "HIGH"
                      ? "bg-error/10 text-error"
                      : result.risk_tier === "MEDIUM"
                        ? "bg-primary/10 text-primary"
                        : "bg-secondary/10 text-secondary"
                  }`}
                >
                  {result.risk_tier} RISK
                </span>
              </div>
              <p className="font-display-lg-mobile text-display-lg-mobile text-on-surface leading-none mb-2">
                {(result.return_risk_score * 100).toFixed(0)}%
              </p>
              <p className="font-body-md text-body-md text-on-surface-variant">
                Return risk score · confidence {(result.confidence * 100).toFixed(1)}%
              </p>
              <ul className="mt-4 space-y-2">
                {result.recommendations.slice(0, 3).map((rec) => (
                  <li key={rec} className="flex items-start gap-2 font-body-md text-body-md text-on-surface-variant">
                    <span className="material-symbols-outlined text-primary text-[16px] mt-0.5">
                      check_circle
                    </span>
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex gap-3">
              <button
                onClick={close}
                className="flex-1 border border-subtle text-on-surface-variant font-label-caps text-label-caps py-2 px-4 uppercase hover:border-primary hover:text-primary transition-colors"
              >
                Done
              </button>
              <button
                onClick={() => {
                  const next = result;
                  reset();
                  onScored?.(next);
                  onClose();
                }}
                className="flex-1 bg-primary text-on-primary font-label-caps text-label-caps py-2 px-4 uppercase hover:bg-primary-container transition-colors"
              >
                New Analysis
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="rr-order-id" className={labelCls}>Order ID *</label>
                <input
                  id="rr-order-id"
                  className={inputCls}
                  value={form.order_id}
                  onChange={(e) => set("order_id", e.target.value)}
                  placeholder="ORD_CUSTOM_001"
                />
              </div>
              <div>
                <label htmlFor="rr-user-id" className={labelCls}>User ID *</label>
                <input
                  id="rr-user-id"
                  className={inputCls}
                  value={form.user_id}
                  onChange={(e) => set("user_id", e.target.value)}
                  placeholder="U_CUSTOM_001"
                />
              </div>
              <div>
                <label htmlFor="rr-merchant-id" className={labelCls}>Merchant ID *</label>
                <input
                  id="rr-merchant-id"
                  className={inputCls}
                  value={form.merchant_id}
                  onChange={(e) => set("merchant_id", e.target.value)}
                  placeholder="M_FASHION_001"
                />
              </div>
              <div>
                <label htmlFor="rr-amount" className={labelCls}>Amount (₹) *</label>
                <input
                  id="rr-amount"
                  type="number"
                  min="1"
                  className={inputCls}
                  value={form.amount}
                  onChange={(e) => set("amount", e.target.value)}
                  placeholder="2500"
                />
              </div>
              <div>
                <label htmlFor="rr-category" className={labelCls}>Category</label>
                <select
                  id="rr-category"
                  className={inputCls}
                  value={form.category}
                  onChange={(e) => set("category", e.target.value)}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="rr-payment" className={labelCls}>Payment Method</label>
                <select
                  id="rr-payment"
                  className={inputCls}
                  value={form.payment_method}
                  onChange={(e) => set("payment_method", e.target.value)}
                >
                  {PAYMENT_METHODS.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="rr-device" className={labelCls}>Device Fingerprint</label>
                <input
                  id="rr-device"
                  className={inputCls}
                  value={form.device_fingerprint}
                  onChange={(e) => set("device_fingerprint", e.target.value)}
                  placeholder="optional"
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-3 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={form.cod_flag}
                    onChange={(e) => set("cod_flag", e.target.checked)}
                    className="w-4 h-4 accent-primary"
                  />
                  <span className="font-body-md text-body-md text-on-surface">Cash on Delivery</span>
                </label>
              </div>
            </div>

            {error && (
              <div className="border border-error/30 bg-error/5 text-error font-body-md text-body-md px-4 py-3">
                {error}
              </div>
            )}

            <div className="flex gap-3 mt-2">
              <button
                onClick={close}
                className="flex-1 border border-subtle text-on-surface-variant font-label-caps text-label-caps py-2 px-4 uppercase hover:border-primary hover:text-primary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={submit}
                disabled={
                  submitting ||
                  !form.order_id.trim() ||
                  !form.user_id.trim() ||
                  !form.merchant_id.trim() ||
                  !Number(form.amount) ||
                  Number(form.amount) <= 0
                }
                className="flex-1 bg-primary text-on-primary font-label-caps text-label-caps py-2 px-4 uppercase hover:bg-primary-container transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {submitting ? "Scoring…" : "Analyze Risk"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ReturnRiskFormModal;