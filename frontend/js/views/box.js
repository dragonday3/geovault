// An opened box: owner truth, the cloak lens, photo, keys, settings.
import { api, blobUrl } from "../api.js";
import { clear, confirmDialog, copyText, empty, fmt, formError, h, icon, loading, plate, toast } from "../dom.js";
import * as mapView from "../map.js";
import { loadBoxes, PRECISIONS, segmented, VISIBILITY } from "./vault.js";

const LINK_HOURS = [[1, "1 hour"], [24, "1 day"], [72, "3 days"], [168, "7 days"], [720, "30 days"]];

function metresBetween(a, b) {
  const lat = ((a.lat + b.lat) / 2) * (Math.PI / 180);
  const dx = ((b.lon - a.lon) * Math.PI / 180) * Math.cos(lat) * 6_371_000;
  const dy = ((b.lat - a.lat) * Math.PI / 180) * 6_371_000;
  return Math.hypot(dx, dy);
}

export async function render(ctx, params) {
  const id = params.match[1];
  clear(ctx.body, loading("Opening the box…"));
  let boxes;
  let fav;
  try {
    [boxes, fav] = await Promise.all([loadBoxes(), api(`/api/favourites/${id}`)]);
  } catch (err) {
    clear(ctx.body, h("a", { class: "back-link", href: "#/vault" }, icon("back", "i i-sm"), "My vault"),
      empty("vault", err.status === 404 ? "There is no box with that number in your vault." : err.message));
    return null;
  }
  fav.number = boxes.find((b) => b.id === fav.id)?.number ?? 0;
  if (fav.region !== ctx.region.code) ctx.setRegion(fav.region, { silent: true });
  mapView.showBoxes(boxes.filter((b) => b.region === fav.region && b.id !== fav.id), (b) => ctx.navigate(`#/vault/${b.id}`));
  mapView.flyTo(fav.location.lat, fav.location.lon, 16);

  let previews = [];
  let lensMode = "owner";
  let photoUrl = null;
  let onceLink = null;

  const lensSlot = h("section", { class: "lens", "aria-labelledby": "lens-title" });
  const photoSlot = h("section");
  const keysSlot = h("section");
  const settingsSlot = h("section");
  const headSlot = h("div");

  // ---------------------------------------------------------------- head: owner truth
  function renderHead() {
    clear(headSlot,
      h("a", { class: "back-link", href: "#/vault" }, icon("back", "i i-sm"), "My vault"),
      h("div", { class: "box-head" },
        plate(fmt.boxNo(fav.number), "plate-solid plate-lg"),
        plate(VISIBILITY[fav.visibility].label, fav.visibility === "private" ? "plate-steel" : "")),
      h("h1", { class: "box-label", text: fav.label }),
      h("p", { class: "view-sub", text: `${ctx.regions.get(fav.region)?.name || fav.region} · deposited ${fmt.date(fav.created_at)}` }),
      h("div", { class: "coords" }, icon("pin"),
        h("span", { class: "mono", text: `${fmt.coord(fav.location.lat)}, ${fmt.coord(fav.location.lon)}` }),
        h("span", { class: "tag" }, icon("lock", "i i-sm"), "Only you see this")),
      fav.note
        ? h("p", { class: "note-slip", text: fav.note })
        : h("p", { class: "note-slip note-empty", text: "No private note." }));
  }

  // ---------------------------------------------------------------- the cloak lens
  async function loadPreview() {
    previews = await api(`/api/favourites/${fav.id}/cloak-preview`);
  }

  function renderLens() {
    const p = previews.find((x) => x.precision_m === fav.share_precision_m);
    const shared = lensMode === "shared";
    const modeSeg = segmented("Lens", [["owner", "Owner view"], ["shared", "Shared view"]], () => lensMode, (v) => { lensMode = v; renderLens(); });
    const precSeg = segmented("Share precision", PRECISIONS.map((x) => [x, fmt.metres(x)]), () => fav.share_precision_m, async (v) => {
      try {
        fav = await api(`/api/favourites/${fav.id}`, { method: "PATCH", body: { share_precision_m: v } });
        fav.number = boxes.find((b) => b.id === fav.id)?.number ?? 0;
        lensMode = "shared";
        renderLens();
        toast(`Shares now round to a ${fmt.metres(v)} cell.`);
      } catch (err) { toast(err.message, "error"); }
    });
    const offset = p ? metresBetween(fav.location, p.location) : 0;
    clear(lensSlot,
      h("h2", { id: "lens-title", class: "section-title", text: "Cloak lens" }),
      modeSeg.node,
      h("div", { class: "field" }, h("span", { class: "field-label", text: "Round shared views to" }), precSeg.node),
      shared && p
        ? h("div", {},
            h("div", { class: "lens-readout" }, h("span", { text: "Recipients see" }), h("span", { class: "mono", text: `${fmt.coord(p.location.lat)}, ${fmt.coord(p.location.lon)}` })),
            h("div", { class: "lens-readout" }, h("span", { text: "Distance from the true spot" }), h("span", { class: "mono", text: fmt.metres(offset) })),
            h("p", { class: "lens-key" }, h("span", { class: "true-dot", "aria-hidden": "true" }), "White dot on the map: your true spot, drawn only for you."),
            h("p", { class: "lens-explain", text: `The server snaps your spot to the centre of its ${fmt.metres(fav.share_precision_m)} grid cell (dashed square), measured in this city's metric map projection. Every view returns the same point, so repeat requests cannot be averaged back to the truth.` }))
        : h("p", { class: "lens-explain", text: "This is your exact spot. Switch to Shared view to see the only location anyone you share with will ever receive." }));
    mapView.showLens({ number: fav.number, exact: fav.location, preview: p, mode: lensMode });
  }

  // ---------------------------------------------------------------- photo
  async function renderPhoto() {
    if (photoUrl) { URL.revokeObjectURL(photoUrl); photoUrl = null; }
    const input = h("input", { class: "file-input", type: "file", accept: "image/jpeg,image/png,image/webp", "aria-label": "Choose a photo" });
    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) { toast("That photo is larger than 5 MB.", "error"); return; }
      const form = new FormData();
      form.append("file", file);
      clear(photoSlot, h("h2", { class: "section-title", text: "Photo" }), loading("Stripping metadata and storing…"));
      try {
        await api(`/api/favourites/${fav.id}/photo`, { method: "POST", form });
        fav.has_photo = true;
        toast("Photo stored. GPS and camera metadata were removed.");
      } catch (err) { toast(err.message, "error"); }
      renderPhoto();
    });
    const chooser = h("label", { class: "btn btn-ghost btn-sm file-label" }, icon("upload", "i i-sm"), fav.has_photo ? "Replace" : "Add a photo", input);

    let media;
    if (fav.has_photo) {
      try {
        photoUrl = await blobUrl(`/api/favourites/${fav.id}/photo`);
        media = h("img", { src: photoUrl, alt: `Photo in ${fmt.boxNo(fav.number)}: ${fav.label}` });
      } catch { media = h("div", { class: "photo-empty", text: "The photo could not be loaded." }); }
    } else {
      media = h("div", { class: "photo-empty" }, icon("photo", "i i-lg"), h("span", { text: "JPEG, PNG or WebP up to 5 MB." }));
    }
    clear(photoSlot,
      h("h2", { class: "section-title", text: "Photo" }),
      h("div", { class: "photo-slot" }, media),
      h("div", { class: "photo-meta" },
        h("span", { text: "Rebuilt from pixels on upload: no GPS, camera or other metadata survives." }),
        h("span", { class: "actions" }, chooser,
          fav.has_photo ? h("button", {
            class: "btn btn-danger btn-sm btn-icon", type: "button", "aria-label": "Remove photo",
            onClick: async () => {
              if (!(await confirmDialog({ title: "Remove this photo?", text: "The stored file is deleted.", confirmLabel: "Remove photo", danger: true }))) return;
              try { await api(`/api/favourites/${fav.id}/photo`, { method: "DELETE" }); fav.has_photo = false; renderPhoto(); }
              catch (err) { toast(err.message, "error"); }
            },
          }, icon("trash", "i i-sm")) : null)));
  }

  // ---------------------------------------------------------------- keys
  async function renderKeys() {
    clear(keysSlot, h("h2", { class: "section-title", text: "Keys" }), loading());
    let shares = [];
    try { shares = await api(`/api/favourites/${fav.id}/shares`); } catch (err) { toast(err.message, "error"); }
    const active = shares.filter((s) => !s.revoked_at && fmt.expiry(s.expires_at).state !== "dead");

    const tags = shares.map((s) => {
      const exp = fmt.expiry(s.expires_at);
      const dead = Boolean(s.revoked_at) || exp.state === "dead";
      const stamp = s.revoked_at ? h("span", { class: "stamp stamp-dead", text: `Revoked ${fmt.dateTime(s.revoked_at)}` })
        : h("span", { class: `stamp ${exp.state === "dead" ? "stamp-dead" : exp.state === "expiring" ? "stamp-expiring" : ""}`, text: exp.text });
      return h("div", { class: `key-tag${dead ? " is-dead" : ""}` },
        h("span", { class: "key-hole", "aria-hidden": "true" }),
        h("div", {},
          h("div", { class: "key-title", text: s.type === "user" ? `For ${s.recipient_display_name || "a deleted account"}` : "Link key" }),
          h("div", { class: "key-meta" }, `Issued ${fmt.date(s.created_at)} · `, stamp)),
        dead ? h("span", {}) : h("button", {
          class: "btn btn-danger btn-sm", type: "button",
          onClick: async () => {
            if (!(await confirmDialog({ title: "Revoke this key?", text: "It stops working immediately and cannot be re-enabled.", confirmLabel: "Revoke key", danger: true }))) return;
            try { await api(`/api/favourites/${fav.id}/shares/${s.id}`, { method: "DELETE" }); toast("Key revoked."); renderKeys(); }
            catch (err) { toast(err.message, "error"); }
          },
        }, "Revoke"));
    });

    clear(keysSlot,
      h("div", { class: "view-head" },
        h("h2", { class: "section-title", text: "Keys" }),
        h("span", { class: "capacity", title: "Active keys of the allowance per box", text: `${active.length} / 50 active` })),
      onceLink ? h("div", { class: "once-box", role: "status" },
        h("strong", { text: "Copy this link now. It is shown only once." }),
        h("span", { class: "mono", text: onceLink }),
        h("button", {
          class: "btn btn-brass btn-sm", type: "button",
          onClick: async () => toast((await copyText(onceLink)) ? "Link copied." : "Copy failed. Select the text instead.", "info"),
        }, icon("copy", "i i-sm"), "Copy link")) : null,
      tags.length ? tags : h("p", { class: "fine", text: "No keys issued for this box yet." }),
      fav.visibility === "private"
        ? h("div", { class: "empty" }, icon("lock", "i i-lg"),
            h("p", { text: "Private boxes cannot be shared. Set visibility to Shared to issue keys." }),
            h("button", { class: "btn btn-ghost btn-sm", type: "button", onClick: () => setVisibility("shared") }, "Make it Shared"))
        : issueForm());
  }

  function issueForm() {
    const state = { type: "link", hours: 72 };
    const errorSlot = h("div");
    const email = h("input", { class: "input", type: "email", maxlength: "254", placeholder: "their.email@example.com", "aria-label": "Recipient email" });
    const hours = h("select", { class: "select", "aria-label": "Link lifetime" },
      LINK_HOURS.map(([v, t]) => h("option", { value: String(v), selected: v === 72 ? true : null, text: t })));
    const body = h("div");
    const typeSeg = segmented("Key type", [["link", "Expiring link"], ["user", "Registered user"]], () => state.type, (v) => { state.type = v; drawBody(); });
    const issue = h("button", { class: "btn btn-brass btn-block", type: "submit" }, icon("key", "i i-sm"), "Issue key");
    function drawBody() {
      clear(body, state.type === "user"
        ? h("label", { class: "field" }, h("span", { text: "Their GeoVault email" }), email)
        : h("label", { class: "field" }, h("span", { text: "Link works for" }), hours));
    }
    drawBody();
    const form = h("form", {}, h("h2", { class: "section-title", text: "Issue a key" }), errorSlot,
      h("div", { class: "field" }, typeSeg.node), body,
      h("p", { class: "hint", text: `Recipients get the label, your display name and a ${fmt.metres(fav.share_precision_m)} cell. Never your note, your email or the exact spot.` }),
      issue);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(errorSlot);
      issue.disabled = true;
      try {
        const payload = state.type === "user"
          ? { type: "user", email: email.value.trim() }
          : { type: "link", expires_in_hours: Number(hours.value) };
        const share = await api(`/api/favourites/${fav.id}/share`, { method: "POST", body: payload });
        // The raw token is in the URL FRAGMENT: browsers never send it to the server.
        onceLink = share.token ? `${window.location.origin}/#/share/${share.token}` : null;
        toast(share.type === "user" ? `Key issued to ${share.recipient_display_name}.` : "Link key issued.");
        renderKeys();
      } catch (err) {
        clear(errorSlot, formError(err.message));
        issue.disabled = false;
      }
    });
    return form;
  }

  // ---------------------------------------------------------------- settings
  async function setVisibility(v) {
    try {
      fav = await api(`/api/favourites/${fav.id}`, { method: "PATCH", body: { visibility: v } });
      fav.number = boxes.find((b) => b.id === fav.id)?.number ?? 0;
      toast(v === "private" ? "Now private. Existing keys stop working." : `Now ${VISIBILITY[v].label.toLowerCase()}.`);
      renderHead(); renderKeys(); renderSettings();
    } catch (err) { toast(err.message, "error"); }
  }

  function renderSettings() {
    const visSeg = segmented("Visibility", Object.entries(VISIBILITY).map(([k, v]) => [k, v.label]), () => fav.visibility, (v) => { if (v !== fav.visibility) setVisibility(v); });
    const label = h("input", { class: "input", maxlength: "100", required: true, value: fav.label });
    const note = h("textarea", { class: "textarea", maxlength: "2000" });
    note.value = fav.note || "";
    const errorSlot = h("div");
    const save = h("button", { class: "btn btn-ghost", type: "submit" }, "Save details");
    const form = h("form", {}, errorSlot,
      h("label", { class: "field" }, h("span", { text: "Label" }), label),
      h("label", { class: "field" }, h("span", { text: "Private note" }), note),
      save);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(errorSlot);
      save.disabled = true;
      try {
        fav = await api(`/api/favourites/${fav.id}`, { method: "PATCH", body: { label: label.value, note: note.value || null } });
        fav.number = boxes.find((b) => b.id === fav.id)?.number ?? 0;
        toast("Details saved.");
        renderHead();
      } catch (err) { clear(errorSlot, formError(err.message)); }
      save.disabled = false;
    });

    clear(settingsSlot,
      h("h2", { class: "section-title", text: "Visibility" }),
      visSeg.node,
      h("p", { class: "hint", text: VISIBILITY[fav.visibility].help }),
      h("h2", { class: "section-title", text: "Details" }),
      form,
      h("div", { class: "danger-zone" },
        h("button", {
          class: "btn btn-danger", type: "button",
          onClick: async () => {
            const ok = await confirmDialog({
              title: `Empty ${fmt.boxNo(fav.number)}?`,
              text: "The box, its note, its photo and every key are deleted. This cannot be undone.",
              confirmLabel: "Delete box", danger: true,
            });
            if (!ok) return;
            try { await api(`/api/favourites/${fav.id}`, { method: "DELETE" }); toast("Box deleted."); ctx.navigate("#/vault"); }
            catch (err) { toast(err.message, "error"); }
          },
        }, icon("trash", "i i-sm"), "Delete this box")));
  }

  renderHead();
  clear(ctx.body, headSlot, lensSlot, photoSlot, keysSlot, settingsSlot);
  await loadPreview();
  renderLens();
  renderPhoto();
  renderKeys();
  renderSettings();

  return () => {
    mapView.clearLens();
    mapView.clearBoxes();
    if (photoUrl) URL.revokeObjectURL(photoUrl);
  };
}
