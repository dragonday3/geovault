// DOM helpers. SECURITY RULE: API data only ever reaches the page through textContent
// (via h()), never innerHTML, so names, labels and notes cannot inject markup or script.

const SVG_NS = "http://www.w3.org/2000/svg";

/** h("div", {class: "x", onClick: fn, "aria-label": "y"}, "text", childNode, [more]) */
export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "href") node.setAttribute("href", safeHref(value));
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

/** Only same-origin paths, fragments and https URLs may become links. */
export function safeHref(value) {
  const s = String(value);
  if (s.startsWith("#") || (s.startsWith("/") && !s.startsWith("//"))) return s;
  try {
    const url = new URL(s);
    if (url.protocol === "https:") return url.href;
  } catch { /* fall through */ }
  return "#";
}

export function clear(node, ...children) {
  node.replaceChildren();
  append(node, children);
  return node;
}

export function icon(name, cls = "i") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `/icons.svg#${name}`);
  svg.append(use);
  return svg;
}

export function plate(text, variant = "") {
  return h("span", { class: `plate ${variant}`.trim() }, text);
}

export function loading(text = "Loading…") {
  return h("div", { class: "loading", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), text);
}

export function empty(iconName, message, action) {
  return h("div", { class: "empty" }, icon(iconName, "i i-lg"), h("p", { text: message }), action || null);
}

export function formError(message) {
  return h("div", { class: "form-error", role: "alert" }, icon("shield", "i i-sm"), h("span", { text: message }));
}

// ---------------------------------------------------------------- toasts
export function toast(message, kind = "info") {
  const host = document.getElementById("toasts");
  const node = h("div", { class: `toast${kind === "error" ? " is-error" : ""}` },
    icon(kind === "error" ? "shield" : "check"), h("span", { text: message }));
  host.append(node);
  setTimeout(() => node.remove(), kind === "error" ? 6000 : 3500);
}

// ---------------------------------------------------------------- dialog
/** Native <dialog>: focus is trapped and Escape cancels. Resolves true on confirm. */
export function confirmDialog({ title, text, confirmLabel = "Confirm", danger = false, body = null }) {
  const dialog = document.getElementById("dialog");
  return new Promise((resolve) => {
    const cancel = h("button", { class: "btn btn-ghost", type: "button", value: "cancel" }, "Cancel");
    const ok = h("button", { class: `btn ${danger ? "btn-danger" : "btn-brass"}`, type: "submit", value: "ok" }, confirmLabel);
    const form = h("form", { method: "dialog" },
      h("div", { class: "dialog-body" },
        h("h2", { class: "dialog-title", text: title }),
        text ? h("p", { class: "dialog-text", text }) : null,
        body),
      h("div", { class: "dialog-actions" }, cancel, ok));
    clear(dialog, form);
    cancel.addEventListener("click", () => dialog.close("cancel"));
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok"), { once: true });
    dialog.returnValue = "";
    dialog.showModal();
    (danger ? cancel : ok).focus();
  });
}

// ---------------------------------------------------------------- formatting
const dateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

export const fmt = {
  date: (iso) => (iso ? dateFmt.format(new Date(iso)) : "—"),
  dateTime: (iso) => (iso ? dateTimeFmt.format(new Date(iso)) : "—"),
  coord: (n) => Number(n).toFixed(5),
  metres: (m) => (m >= 1000 ? `${(m / 1000).toFixed(m % 1000 ? 1 : 0)} km` : `${Math.round(m)} m`),
  boxNo: (n) => `Box ${String(n).padStart(3, "0")}`,
  count: (n) => new Intl.NumberFormat().format(n),
  /** "expires in 3 h", "expired 2 d ago", "no expiry" */
  expiry(iso) {
    if (!iso) return { text: "No expiry", state: "open" };
    const ms = new Date(iso) - Date.now();
    const abs = Math.abs(ms);
    const unit = abs >= 86_400_000 ? [Math.round(abs / 86_400_000), "d"] : abs >= 3_600_000 ? [Math.round(abs / 3_600_000), "h"] : [Math.max(1, Math.round(abs / 60_000)), "min"];
    if (ms <= 0) return { text: `Expired ${unit[0]} ${unit[1]} ago`, state: "dead" };
    return { text: `Expires in ${unit[0]} ${unit[1]}`, state: ms < 86_400_000 ? "expiring" : "open" };
  },
};

export function copyText(text) {
  return navigator.clipboard.writeText(text).then(() => true, () => false);
}
