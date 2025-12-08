// Centralized API helper so frontend doesn't hard-code localhost/ports in many places
// Default behavior: use same-origin (empty base), which works with Vite's dev proxy
// on port 3003 to reach the Django backend (127.0.0.1:8000) without exposing it
// publicly or hitting CORS issues from remote browsers.
//
// To bypass the proxy and point directly to a backend, set VITE_API_BASE in a .env:
//   VITE_API_BASE=http://127.0.0.1:8000   (local-only)
//   VITE_API_BASE=http://turing.cs.olemiss.edu:8000   (if publicly reachable)
//   VITE_API_BASE=""   (explicitly force same-origin + proxy)

let _envBase = (import.meta.env?.VITE_API_BASE ?? "").trim();

// Safety guard: if someone configured VITE_API_BASE to a loopback address
// (http://127.0.0.1 or http://localhost), that only works when the browser
// itself is on the same machine. For remote access (e.g., visiting
// http://turing.cs.olemiss.edu:3003 from your laptop), a loopback base will
// refuse connections. In that scenario, auto-fall back to same-origin so the
// Vite proxy can forward to the backend running on the server.
try {
  if (_envBase) {
    const u = new URL(_envBase);
    const isLoopback = (h) => h === "127.0.0.1" || h === "localhost";
    const onRemoteHost = typeof window !== "undefined" && !isLoopback(window.location.hostname);
    if (isLoopback(u.hostname) && onRemoteHost) {
      _envBase = ""; // Use same-origin + proxy
    }
  }
} catch (_) {
  // Ignore malformed URL in env; keep as-is
}

export const API_BASE = _envBase;

// Join helper that ensures single slash between base and path
export function apiUrl(path) {
  const base = API_BASE.replace(/\/$/, "");
  const p = String(path || "");
  return p.startsWith("/") ? `${base}${p}` : `${base}/${p}`;
}

// Lightweight fetch wrapper with JSON defaults
export async function apiFetch(path, { method = "GET", headers = {}, body, ...rest } = {}) {
  const url = apiUrl(path);
  const init = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    ...rest,
  };
  if (body !== undefined && body !== null && typeof body !== "string") {
    init.body = JSON.stringify(body);
  } else if (body !== undefined) {
    init.body = body;
  }

  const res = await fetch(url, init);
  let data = null;
  try {
    data = await res.json();
  } catch {}
  if (!res.ok) {
    const detail = (data && (data.error?.detail || data.error || data.message)) || `HTTP ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : `HTTP error! Status: ${res.status}`);
  }
  return data;
}
