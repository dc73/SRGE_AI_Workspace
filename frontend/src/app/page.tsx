"use client";

import { useEffect, useState } from "react";
import { login } from "../lib/api";

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [usage, setUsage] = useState<Record<string, number | number[]> | null>(null);
  const [error, setError] = useState<string>("");

  async function doLogin() {
    setError("");
    try {
      const res = await login(email, password);
      localStorage.setItem("srge_token", res.token);
      setToken(res.token);
      const u = await fetchUsage(res.token);
      setUsage(u);
    } catch (e) {
      setError(String(e));
    }
  }

  async function fetchUsage(tok: string) {
    const r = await fetch(`${process.env.NEXT_PUBLIC_SRGE_API || "http://localhost:8001"}/user/usage`, {
      headers: { Authorization: `Bearer ${tok}` },
    });
    return r.ok ? r.json() : null;
  }

  useEffect(() => {
    const t = localStorage.getItem("srge_token");
    if (t) {
      setToken(t);
      fetchUsage(t).then(setUsage);
    }
  }, []);

  if (token) {
    return (
      <main style={{ maxWidth: 720, margin: "40px auto", padding: "0 16px" }}>
        <h1>SRGE AI Workspace</h1>
        {usage ? (
          <section>
            <h2>Your usage</h2>
            <p>
              Requests: {usage.requests} · Prompt tokens: {usage.prompt_tokens} ·
              Completion tokens: {usage.completion_tokens} · Total: {usage.total_tokens}
            </p>
            {Array.isArray(usage.recent) && usage.recent.length > 0 && (
              <ul>
                {(usage.recent as unknown[]).slice(0, 10).map((item, i) => {
                  const r = item as { model: string; prompt: number; completion: number; ts: string };
                  return (
                    <li key={i}>
                      {r.model} — {r.prompt}+{r.completion} tokens @ {r.ts}
                    </li>
                  );
                })}
              </ul>
            )}
            <button onClick={() => { localStorage.removeItem("srge_token"); setToken(null); setUsage(null); }}>
              Log out
            </button>
          </section>
        ) : (
          <p>No usage recorded yet.</p>
        )}
      </main>
    );
  }

  return (
    <main style={{ maxWidth: 360, margin: "80px auto" }}>
      <h1>SRGE AI Workspace</h1>
      <form onSubmit={(e) => { e.preventDefault(); doLogin(); }}>
        <label>Email <input value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Password <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <button type="submit">Sign in</button>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </form>
    </main>
  );
}
