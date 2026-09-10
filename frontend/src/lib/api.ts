const API = process.env.NEXT_PUBLIC_SRGE_API || "http://localhost:8001";

export async function login(email: string, password: string) {
  const r = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "login failed");
  return data as { token: string; role: string; email: string };
}

export async function me(token: string, path: string) {
  const r = await fetch(`${API}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error("request failed");
  return r.json();
}
