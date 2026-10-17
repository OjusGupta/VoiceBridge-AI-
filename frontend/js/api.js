// Thin fetch wrapper. All conversation logic lives in the Python backend.
async function request(method, path, body, timeoutMs = 20000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method, signal: ctl.signal,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch { /* non-JSON body */ }
    if (!res.ok) {
      const detail = data && data.detail;
      const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? "Invalid message." : `Server error (${res.status})`;
      const err = new Error(msg); err.status = res.status; throw err;
    }
    if (data === null) throw new Error("Malformed response from server.");
    return data;
  } catch (e) {
    if (e.name === "AbortError") throw new Error("The server took too long to respond.");
    if (e instanceof TypeError) throw new Error("Cannot reach the backend. Is the server running?");
    throw e;
  } finally { clearTimeout(t); }
}
export const api = {
  status: () => request("GET", "/api/status"),
  create: (prompt_version) => request("POST", "/api/conversations", { prompt_version }),
  send: (id, message) => request("POST", `/api/conversations/${id}/messages`, { message }),
  restart: (id) => request("POST", `/api/conversations/${id}/restart`),
  end: (id) => request("POST", `/api/conversations/${id}/end`),
};
