// Register (admins): users and roles, and the access register (audit log).
import { api, session } from "../api.js";
import { clear, confirmDialog, empty, fmt, h, loading, plate, toast } from "../dom.js";
import { segmented } from "./vault.js";

const DANGER = /(failure|reuse|rate_limited|rejected|delete|revoke|denied)/;
const FILTERS = [["", "All"], ["auth", "Sign-ins"], ["favourite", "Boxes"], ["share", "Keys"], ["photo", "Photos"], ["user", "Accounts"], ["admin", "Admin"]];

/** "auth.login_success" -> text with <wbr> after each "." and "_": breaks only at boundaries. */
function breakable(action) {
  return action.split(/(?<=[._])/).flatMap((part, i) => (i ? [h("wbr"), part] : [part]));
}

export async function render(ctx, params) {
  const section = params.match[1] === "register" ? "register" : "users";
  const body = h("div");
  const tabs = segmented("Register section", [["users", "Users"], ["register", "Access register"]], () => section,
    (v) => ctx.navigate(v === "users" ? "#/admin" : "#/admin/register"));
  clear(ctx.body,
    h("div", { class: "view-head" }, h("div", {},
      h("h1", { class: "view-title", text: "Register" }),
      h("p", { class: "view-sub", text: "Every admin action, including reading this register, is itself recorded." }))),
    tabs.node, body);
  if (section === "users") await renderUsers(body);
  else await renderRegister(body);
}

async function renderUsers(host) {
  const search = h("input", { class: "input", type: "search", placeholder: "Search name or email", "aria-label": "Search users", maxlength: "100" });
  const table = h("div");
  let debounce;
  async function load() {
    clear(table, loading());
    try {
      const users = await api("/api/admin/users", { params: { q: search.value.trim(), limit: 100 } });
      if (!users.length) { clear(table, empty("user", "No accounts match.")); return; }
      clear(table, h("table", { class: "ledger" },
        h("thead", {}, h("tr", {}, h("th", { text: "Account" }), h("th", { text: "Role" }), h("th", { text: "Last sign-in" }), h("th", {}))),
        h("tbody", {}, users.map((u) => {
          const self = u.id === session.user.id;
          const next = u.role === "admin" ? "user" : "admin";
          return h("tr", {},
            h("td", {}, h("div", { text: u.display_name }), h("div", { class: "fine", text: u.email })),
            h("td", {}, plate(u.role, u.role === "admin" ? "plate-solid" : "plate-steel")),
            h("td", { class: "mono", text: fmt.dateTime(u.last_login_at) }),
            h("td", {}, self ? h("span", { class: "fine", text: "You" }) : h("button", {
              class: "btn btn-ghost btn-sm", type: "button",
              onClick: async () => {
                const ok = await confirmDialog({
                  title: next === "admin" ? `Make ${u.display_name} an administrator?` : `Remove ${u.display_name}'s admin role?`,
                  text: "Takes effect on their very next request. The change is recorded in the access register.",
                  confirmLabel: next === "admin" ? "Grant admin" : "Remove admin",
                  danger: next === "user",
                });
                if (!ok) return;
                try { await api(`/api/admin/users/${u.id}/role`, { method: "PATCH", body: { role: next } }); toast("Role updated."); load(); }
                catch (err) { toast(err.message, "error"); }
              },
            }, next === "admin" ? "Grant admin" : "Remove admin")));
        }))));
    } catch (err) { clear(table, h("p", { class: "form-error", text: err.message })); }
  }
  search.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(load, 250); });
  clear(host, h("div", { class: "field" }, h("span", { class: "visually-hidden", text: "Search" }), search), table);
  await load();
}

async function renderRegister(host) {
  let filter = "";
  let offset = 0;
  const rows = h("tbody");
  const more = h("button", { class: "btn btn-ghost btn-block", type: "button" }, "Load older entries");
  const filters = h("div", { class: "chips", role: "group", "aria-label": "Filter the register" });
  const drawFilters = () => clear(filters, FILTERS.map(([v, label]) => h("button", {
    class: "chip", type: "button", "aria-pressed": String(filter === v),
    onClick: () => { filter = v; offset = 0; clear(rows); drawFilters(); load(); },
  }, label)));
  drawFilters();

  async function load() {
    more.disabled = true;
    try {
      const entries = await api("/api/admin/audit", { params: { action: filter || null, limit: 50, offset } });
      offset += entries.length;
      for (const e of entries) {
        rows.append(h("tr", { class: DANGER.test(e.action) ? "is-danger" : "" },
          h("td", { class: "mono", text: fmt.dateTime(e.created_at) }),
          h("td", {}, h("span", { class: "action-cell" }, breakable(e.action))),
          h("td", { class: "who-cell", text: e.actor_display_name || "—" }),
          h("td", { class: "mono", text: e.ip || "—" })));
      }
      more.hidden = entries.length < 50;
      if (!rows.children.length) rows.append(h("tr", {}, h("td", { colspan: "4", class: "fine", text: "No entries for this filter." })));
    } catch (err) { toast(err.message, "error"); }
    more.disabled = false;
  }
  more.addEventListener("click", load);
  clear(host,
    filters,
    h("table", { class: "ledger" },
      h("thead", {}, h("tr", {}, h("th", { text: "When" }), h("th", { text: "Action" }), h("th", { text: "Actor" }), h("th", { text: "IP" }))),
      rows),
    h("div", { class: "actions" }, more));
  await load();
}
