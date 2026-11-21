// API client and session. Token storage design (docs/authentication.md):
//   * access token: kept ONLY in this module's memory (never localStorage/sessionStorage),
//     so a page reload or XSS cannot read a persisted token; it lives 15 minutes;
//   * refresh token: HttpOnly cookie the browser sends to /api/auth only; JS cannot read it;
//   * refresh and logout send X-CSRF-Token copied from the __Host-gv_csrf cookie.

let accessToken = null;
let refreshTimer = null;
const listeners = new Set();

export const session = {
  user: null,
  get signedIn() { return Boolean(accessToken && this.user); },
  get isAdmin() { return this.user?.role === "admin"; },
  onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
};

function emit() { for (const fn of listeners) fn(session); }

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)__Host-gv_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function messageFrom(body, status) {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) {
    return body.detail.map((d) => String(d.msg || "").replace(/^Value error, /, "")).filter(Boolean).join(" ") || "Check the highlighted fields.";
  }
  if (status === 429) return "Too many attempts. Wait a moment and try again.";
  if (status >= 500) return "The server hit an error. Try again in a moment.";
  return `Request failed (${status}).`;
}

/** fetch() wrapper: JSON in/out, bearer auth, one silent refresh-and-retry on 401. */
export async function api(path, options = {}) {
  const { method = "GET", body, form, params, raw = false, auth = true, retry = true } = options;
  const url = new URL(path, window.location.origin);
  for (const [k, v] of Object.entries(params || {})) {
    if (Array.isArray(v)) v.forEach((item) => url.searchParams.append(k, item));
    else if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
  }
  const headers = { Accept: "application/json" };
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }

  const res = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
  if (res.status === 401 && auth && retry && accessToken && (await refresh())) {
    return api(path, { ...options, retry: false });
  }
  if (!res.ok) {
    let data = null;
    try { data = await res.json(); } catch { /* not JSON */ }
    throw new ApiError(res.status, messageFrom(data, res.status));
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

/** Authenticated binary GET (photos) -> object URL. Caller revokes it when done. */
export async function blobUrl(path) {
  const res = await api(path, { raw: true });
  return URL.createObjectURL(await res.blob());
}

function setTokens(data) {
  clearTimeout(refreshTimer);
  if (!data) { accessToken = null; session.user = null; emit(); return; }
  accessToken = data.access_token;
  // Refresh a minute before expiry so the user never sees a 401 mid-task.
  refreshTimer = setTimeout(refresh, Math.max(30, data.expires_in - 60) * 1000);
}

let refreshing = null;
export function refresh() {
  if (refreshing) return refreshing; // collapse concurrent refreshes: rotation allows one
  const token = csrfToken();
  if (!token) return Promise.resolve(false);
  refreshing = fetch("/api/auth/refresh", { method: "POST", headers: { "X-CSRF-Token": token }, credentials: "same-origin" })
    .then(async (res) => {
      if (!res.ok) { setTokens(null); return false; }
      setTokens(await res.json());
      return true;
    })
    .catch(() => false)
    .finally(() => { refreshing = null; });
  return refreshing;
}

export async function loadUser() {
  session.user = await api("/api/users/me");
  emit();
}

export async function restoreSession() {
  if (await refresh()) {
    try { await loadUser(); } catch { setTokens(null); }
  }
}

export async function signIn(email, password) {
  const data = await api("/api/auth/login", { method: "POST", body: { email, password }, auth: false });
  setTokens(data);
  await loadUser();
}

export async function register(email, password, displayName) {
  await api("/api/auth/register", { method: "POST", body: { email, password, display_name: displayName }, auth: false });
}

export async function signOut() {
  const token = csrfToken();
  try {
    await fetch("/api/auth/logout", { method: "POST", headers: token ? { "X-CSRF-Token": token } : {}, credentials: "same-origin" });
  } finally {
    setTokens(null);
  }
}

/** Account deletion ends the session locally too (server already cleared the cookies). */
export function forgetSession() { setTokens(null); }
