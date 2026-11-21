// GeoVault app shell: city plates, account plate, rail tabs and a tiny hash router.
// Routes use the URL fragment, which browsers never send to the server: share-link tokens
// (#/share/<token>) therefore never appear in server logs or Referer headers.
import { api, restoreSession, session, signOut } from "./api.js";
import { clear, h, icon, toast } from "./dom.js";
import { initMap, setRegion } from "./map.js";
import * as account from "./views/account.js";
import * as admin from "./views/admin.js";
import * as auth from "./views/auth.js";
import * as box from "./views/box.js";
import * as hall from "./views/hall.js";
import * as keys from "./views/keys.js";
import * as share from "./views/share.js";
import * as vault from "./views/vault.js";

const CITY_CODES = { melbourne: "MEL", bengaluru: "BLR", ahmedabad: "AMD" };
const CITY_ORDER = ["melbourne", "bengaluru", "ahmedabad"];

const ctx = {
  regions: new Map(),
  region: null,
  sources: [],
  body: document.getElementById("rail-body"),
  navigate(hash) { if (window.location.hash === hash) route(); else window.location.hash = hash; },
  setRegion(code, { silent = false } = {}) {
    const r = ctx.regions.get(code);
    if (!r || ctx.region?.code === code) return;
    ctx.region = r;
    setRegion(r);
    renderCityPlates();
    // Snapshot: a listener re-renders its view, which unsubscribes and re-subscribes. Iterating
    // the live Set would visit the new subscription too, forever (froze the tab on city switch).
    if (!silent) for (const fn of [...regionListeners]) fn(r);
  },
  onRegion(fn) { regionListeners.add(fn); return () => regionListeners.delete(fn); },
};
const regionListeners = new Set();

// ---------------------------------------------------------------- header
function renderCityPlates() {
  const host = document.getElementById("city-plates");
  const codes = [...ctx.regions.keys()].sort((a, b) => (CITY_ORDER.indexOf(a) + 99) % 99 - (CITY_ORDER.indexOf(b) + 99) % 99);
  clear(host, codes.map((code) => {
    const r = ctx.regions.get(code);
    const checked = ctx.region?.code === code;
    return h("button", {
      class: "city-plate", type: "button", role: "radio", "aria-checked": String(checked),
      "aria-label": `${r.name}, ${r.country_code === "IN" ? "India" : "Australia"}`,
      tabindex: checked ? "0" : "-1",
      onClick: () => ctx.setRegion(code),
      onKeydown: (e) => {
        if (!["ArrowRight", "ArrowLeft"].includes(e.key)) return;
        const i = codes.indexOf(code) + (e.key === "ArrowRight" ? 1 : -1);
        const next = codes[(i + codes.length) % codes.length];
        ctx.setRegion(next);
        host.querySelector('[aria-checked="true"]')?.focus();
      },
    }, h("span", { class: "city-code", text: CITY_CODES[code] || code.slice(0, 3).toUpperCase() }), h("span", { class: "city-name", text: r.name }));
  }));
}

function renderAccountPlate() {
  const host = document.getElementById("account-plate");
  if (!session.signedIn) {
    clear(host, h("a", { class: "btn btn-brass btn-sm", href: "#/signin" }, icon("vault", "i i-sm"), "Open your vault"));
    return;
  }
  clear(host,
    h("div", { class: "who" },
      h("span", { class: "who-name", text: session.user.display_name }),
      h("span", { class: "who-role", text: session.isAdmin ? "Administrator" : "Box holder" })),
    h("a", { class: "btn btn-ghost btn-sm btn-icon", href: "#/account", "aria-label": "Account settings", title: "Account" }, icon("user", "i i-sm")),
    h("button", {
      class: "btn btn-ghost btn-sm btn-icon", type: "button", "aria-label": "Sign out", title: "Sign out",
      onClick: async () => { await signOut(); toast("Signed out. Your vault is locked."); ctx.navigate("#/hall"); },
    }, icon("logout", "i i-sm")));
}

function renderTabs(active) {
  const tabs = [
    ["hall", "#/hall", "hall", "Hall"],
    ["vault", session.signedIn ? "#/vault" : "#/signin", "vault", "My vault"],
    ["keys", session.signedIn ? "#/keys" : "#/signin", "key", "Keys"],
  ];
  if (session.isAdmin) tabs.push(["admin", "#/admin", "register", "Register"]);
  clear(document.getElementById("rail-tabs"), tabs.map(([id, href, ic, label]) =>
    h("a", { class: "rail-tab", href, "aria-current": id === active ? "page" : null }, icon(ic, "i i-sm"), h("span", { text: label }))));
}

// ---------------------------------------------------------------- router
const ROUTES = [
  [/^#\/share\/([A-Za-z0-9_-]{20,100})$/, share, null, false],
  [/^#\/signin$/, auth, "vault", false, { mode: "signin" }],
  [/^#\/register$/, auth, "vault", false, { mode: "register" }],
  [/^#\/vault$/, vault, "vault", true],
  [/^#\/vault\/new$/, vault, "vault", true, { mode: "new" }],
  [/^#\/vault\/([0-9a-f-]{36})$/, box, "vault", true],
  [/^#\/keys$/, keys, "keys", true],
  [/^#\/account$/, account, "account", true],
  [/^#\/admin(?:\/(users|register))?$/, admin, "admin", true],
];

let cleanup = null;
let routeSeq = 0;

async function route() {
  const hash = window.location.hash || "#/hall";
  const [path, query = ""] = hash.split("?");
  let view = hall;
  let tab = "hall";
  let params = { query: new URLSearchParams(query) };
  for (const [pattern, mod, tabId, needsAuth, extra] of ROUTES) {
    const m = path.match(pattern);
    if (!m) continue;
    if (needsAuth && !session.signedIn) { ctx.navigate(`#/signin?next=${encodeURIComponent(path)}`); return; }
    if (mod === admin && !session.isAdmin) { toast("The register is for administrators.", "error"); ctx.navigate("#/hall"); return; }
    view = mod; tab = tabId; params = { ...params, ...extra, match: m };
    break;
  }
  const seq = ++routeSeq;
  if (cleanup) { try { cleanup(); } catch { /* view already gone */ } cleanup = null; }
  renderTabs(tab);
  // A fresh body element replays the drawer motion on every navigation.
  const fresh = h("div", { id: "rail-body", class: "rail-body" });
  ctx.body.replaceWith(fresh);
  ctx.body = fresh;
  try {
    const result = await view.render(ctx, params);
    if (seq === routeSeq) cleanup = result || null;
    else if (typeof result === "function") result();
  } catch (err) {
    clear(ctx.body, h("div", { class: "form-error", role: "alert" }, err.message || "Something went wrong."));
  }
}

// ---------------------------------------------------------------- boot
async function boot() {
  initMap(document.getElementById("map"));
  const [regions, sources] = await Promise.all([api("/api/regions", { auth: false }), api("/api/sources", { auth: false })]);
  for (const r of regions) ctx.regions.set(r.code, r);
  ctx.sources = sources;
  ctx.setRegion(ctx.regions.has("bengaluru") ? "bengaluru" : regions[0].code, { silent: true });
  await restoreSession();
  session.onChange(() => { renderAccountPlate(); });
  renderAccountPlate();
  window.addEventListener("hashchange", route);
  route();
}

boot().catch(() => {
  clear(document.getElementById("rail-body"), h("div", { class: "form-error", role: "alert" }, "GeoVault could not reach its API. Is the server running?"));
});
