import type { FormEvent } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { useAuthStore } from "../store/authStore";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const authenticate = async (e?: FormEvent) => {
    if (e) e.preventDefault();
    if (!username || !password) {
      setError("Enter your username and password.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await client.post("/v1/auth/login", { username, password });
      login(res.data.access_token, res.data.refresh_token, {
        username,
        role: res.data.role,
      });
      navigate("/return-risk", { replace: true });
    } catch {
      setError("Invalid credentials. Check your username and password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-noise bg-background text-on-surface">
      {/* Ambient background */}
      <div className="absolute inset-0 pointer-events-none z-0 overflow-hidden" aria-hidden>
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/4 w-[32rem] h-[32rem] bg-secondary/5 rounded-full blur-[160px]" />
      </div>

      <main className="w-full max-w-md px-container-padding-mobile md:px-0 relative z-10">
        {/* Brand header */}
        <div className="text-center mb-12">
          <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-primary tracking-tight mb-2">
            PayShield
          </h1>
          <p className="font-label-caps text-label-caps text-outline uppercase tracking-widest">
            Return-Risk Intelligence
          </p>
        </div>

        {/* Card */}
        <div className="bg-surface border border-subtle rounded p-8 md:p-12 relative overflow-hidden shadow-2xl">
          <div className="flex items-center justify-center gap-2 mb-10 text-primary-fixed-dim/80">
            <span className="material-symbols-outlined text-[16px]">lock</span>
            <span className="font-label-caps text-label-caps uppercase">
              Secure Connection Required
            </span>
          </div>

          <h2 className="font-headline-md text-headline-md text-on-surface mb-8 text-center">
            Secure Access
          </h2>

          <form className="space-y-6 flex flex-col gap-y-2" onSubmit={authenticate}>
            {/* Username */}
            <div className="space-y-unit">
              <label
                className="font-label-caps text-label-caps text-on-surface-variant block uppercase"
                htmlFor="username"
              >
                Username
              </label>
              <input
                className="w-full bg-transparent border-b border-subtle pb-2 pt-1 font-mono-data text-mono-data text-on-surface focus:outline-none focus:border-primary transition-colors rounded-none placeholder-outline-variant"
                id="username"
                name="username"
                placeholder="institution.admin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
              />
            </div>

            {/* Password */}
            <div className="space-y-unit pt-4">
              <label
                className="font-label-caps text-label-caps text-on-surface-variant block uppercase"
                htmlFor="password"
              >
                Password
              </label>
              <input
                className="w-full bg-transparent border-b border-subtle pb-2 pt-1 font-mono-data text-mono-data text-on-surface focus:outline-none focus:border-primary transition-colors rounded-none placeholder-outline-variant"
                id="password"
                name="password"
                placeholder="••••••••"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div className="border border-error/30 bg-error/5 text-error font-body-md text-body-md px-4 py-3">
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="pt-10">
              <button
                className="w-full bg-primary text-on-primary font-label-caps text-label-caps uppercase py-4 rounded hover:bg-primary-fixed-dim transition-colors duration-300 disabled:opacity-50"
                type="submit"
                disabled={loading}
              >
                {loading ? "Signing in…" : "Login"}
              </button>
            </div>
          </form>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center flex justify-center gap-6">
          <a
            className="font-label-caps text-label-caps text-outline hover:text-primary transition-colors uppercase"
            href="#"
          >
            Help
          </a>
          <a
            className="font-label-caps text-label-caps text-outline hover:text-primary transition-colors uppercase"
            href="#"
          >
            Security
          </a>
          <a
            className="font-label-caps text-label-caps text-outline hover:text-primary transition-colors uppercase"
            href="#"
          >
            Contact
          </a>
        </div>
      </main>
    </div>
  );
}

export default LoginPage;