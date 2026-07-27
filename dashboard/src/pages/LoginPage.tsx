import { useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { useAuthStore } from "../store/authStore";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const res = await client.post("/v1/auth/login", { username, password });
      login(res.data.access_token, res.data.refresh_token, { username, role: res.data.role });
      navigate("/");
    } catch {
      setError("Invalid credentials");
    }
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        height: "100vh",
        background: "#0f172a",
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          background: "#1e293b",
          padding: 32,
          borderRadius: 8,
          width: 360,
          border: "1px solid #334155",
        }}
      >
        <h1 style={{ color: "#f8fafc", fontSize: 24, marginBottom: 8 }}>PayShield</h1>
        <p style={{ color: "#94a3b8", marginBottom: 24, fontSize: 14 }}>Fraud Detection Dashboard</p>
        {error && (
          <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 12 }}>{error}</div>
        )}
        <div style={{ marginBottom: 16 }}>
          <label style={{ color: "#94a3b8", fontSize: 12, display: "block", marginBottom: 4 }}>Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 12px",
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: 4,
              color: "#f8fafc",
              fontSize: 14,
              boxSizing: "border-box",
            }}
          />
        </div>
        <div style={{ marginBottom: 24 }}>
          <label style={{ color: "#94a3b8", fontSize: 12, display: "block", marginBottom: 4 }}>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 12px",
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: 4,
              color: "#f8fafc",
              fontSize: 14,
              boxSizing: "border-box",
            }}
          />
        </div>
        <button
          type="submit"
          style={{
            width: "100%",
            padding: "10px 16px",
            background: "#0f766e",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Sign In
        </button>
      </form>
    </div>
  );
}
