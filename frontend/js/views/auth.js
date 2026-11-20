// Sign in / register.
import { register, signIn } from "../api.js";
import { clear, formError, h, icon } from "../dom.js";

export async function render(ctx, params) {
  const isRegister = params.mode === "register";
  const next = params.query.get("next");
  const target = next && next.startsWith("#/") ? next : "#/vault";

  const errorSlot = h("div");
  const email = h("input", { class: "input", type: "email", name: "email", autocomplete: "email", required: true, maxlength: "254" });
  const password = h("input", {
    class: "input", type: "password", name: "password", required: true, maxlength: "128",
    autocomplete: isRegister ? "new-password" : "current-password", minlength: isRegister ? "12" : null,
    "aria-describedby": isRegister ? "pw-hint" : null,
  });
  const name = isRegister ? h("input", { class: "input", type: "text", name: "display_name", required: true, maxlength: "60", autocomplete: "nickname" }) : null;
  const submit = h("button", { class: "btn btn-brass btn-block", type: "submit" }, icon(isRegister ? "plus" : "vault", "i i-sm"), isRegister ? "Create my vault" : "Open my vault");

  const form = h("form", { novalidate: false },
    errorSlot,
    name ? h("label", { class: "field" }, h("span", { text: "Display name" }), name, h("small", { class: "hint", text: "Shown to people you share with. Your email never is." })) : null,
    h("label", { class: "field" }, h("span", { text: "Email" }), email),
    h("label", { class: "field" }, h("span", { text: "Password" }), password,
      isRegister ? h("small", { id: "pw-hint", class: "hint", text: "12 or more characters. Passwords found in known breaches are refused." }) : null),
    submit);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clear(errorSlot);
    submit.disabled = true;
    try {
      if (isRegister) await register(email.value.trim(), password.value, name.value.trim());
      await signIn(email.value.trim(), password.value);
      ctx.navigate(target);
    } catch (err) {
      // Login failures are deliberately generic: the server never says whether the email exists.
      clear(errorSlot, formError(err.message));
      submit.disabled = false;
      password.select();
    }
  });

  clear(ctx.body,
    h("div", { class: "auth-intro" },
      h("h1", { class: "view-title", text: isRegister ? "Create your vault" : "Open your vault" }),
      h("p", { text: isRegister
        ? "Keep your own places (home, work, a favourite stall) with exact coordinates only you can see."
        : "Sign in to see your boxes, keys and notes." })),
    form,
    h("p", { class: "switch-line" }, isRegister ? "Already have a vault? " : "New here? ",
      h("a", { href: isRegister ? "#/signin" : "#/register", text: isRegister ? "Sign in" : "Create a vault" })),
    h("ul", { class: "promise", "aria-label": "How your places are protected" },
      h("li", {}, icon("lock"), h("span", { text: "Exact coordinates are shown only to you. Anyone else gets the same answer as for a box that does not exist." })),
      h("li", {}, icon("cell"), h("span", { text: "When you share, the server snaps the location to a 100 m, 500 m or 1 km grid cell." })),
      h("li", {}, icon("photo"), h("span", { text: "Photos are rebuilt from pixels on upload, so GPS and camera metadata are gone." }))));
  (name || email).focus();
}
