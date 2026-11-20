// Account: profile, data export, sign out, account deletion.
import { api, forgetSession, loadUser, session } from "../api.js";
import { clear, confirmDialog, fmt, formError, h, icon, plate, toast } from "../dom.js";

export async function render(ctx) {
  const user = await api("/api/users/me");
  const errorSlot = h("div");
  const name = h("input", { class: "input", maxlength: "60", required: true, value: user.display_name, autocomplete: "nickname" });
  const save = h("button", { class: "btn btn-ghost", type: "submit" }, "Save name");
  const profile = h("form", {}, errorSlot,
    h("label", { class: "field" }, h("span", { text: "Display name" }), name,
      h("small", { class: "hint", text: "The only identity people you share with ever see." })),
    save);
  profile.addEventListener("submit", async (e) => {
    e.preventDefault();
    clear(errorSlot);
    save.disabled = true;
    try {
      await api("/api/users/me", { method: "PATCH", body: { display_name: name.value } });
      await loadUser();
      toast("Display name saved.");
    } catch (err) { clear(errorSlot, formError(err.message)); }
    save.disabled = false;
  });

  async function exportData() {
    try {
      const res = await api("/api/users/me/export", { raw: true });
      const url = URL.createObjectURL(await res.blob());
      const a = h("a", { href: "#", download: "geovault-export.json" });
      a.href = url; // object URL from our own fetch (h() only accepts http(s)/same-origin)
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast("Export downloaded: everything GeoVault holds about you.");
    } catch (err) { toast(err.message, "error"); }
  }

  async function deleteAccount() {
    const password = h("input", { class: "input", type: "password", autocomplete: "current-password", "aria-label": "Your password" });
    const ok = await confirmDialog({
      title: "Delete your account?",
      text: "Every box, note, photo and key is erased. Security records stay, de-identified. This cannot be undone.",
      confirmLabel: "Delete my account",
      danger: true,
      body: h("label", { class: "field" }, h("span", { text: "Confirm with your password" }), password),
    });
    if (!ok) return;
    try {
      await api("/api/users/me", { method: "DELETE", body: { password: password.value } });
      forgetSession();
      toast("Your account and everything in it has been deleted.");
      ctx.navigate("#/hall");
    } catch (err) { toast(err.message, "error"); }
  }

  clear(ctx.body,
    h("div", { class: "view-head" }, h("div", {},
      h("h1", { class: "view-title", text: "Account" }),
      h("p", { class: "view-sub", text: `${user.email} · since ${fmt.date(user.created_at)}` })),
      plate(session.isAdmin ? "Administrator" : "Box holder", session.isAdmin ? "plate-solid" : "")),
    profile,
    h("h2", { class: "section-title", text: "Your data" }),
    h("p", { class: "muted", text: "Download a JSON file with your profile, every box (with exact coordinates and notes), your keys, photo records, sessions and your own activity." }),
    h("div", { class: "actions" }, h("button", { class: "btn btn-ghost", type: "button", onClick: exportData }, icon("download", "i i-sm"), "Export my data")),
    h("div", { class: "danger-zone" },
      h("p", { class: "fine", text: "Deleting asks for your password, so a stolen session alone cannot erase your account." }),
      h("div", { class: "actions" }, h("button", { class: "btn btn-danger", type: "button", onClick: deleteAccount }, icon("trash", "i i-sm"), "Delete my account"))));
}
