// My vault: the drawer of numbered boxes, and depositing a new box.
import { api } from "../api.js";
import { clear, empty, fmt, formError, h, icon, loading, plate, toast } from "../dom.js";
import * as mapView from "../map.js";

const CAPACITY = 1000;
export const VISIBILITY = {
  private: { label: "Private", help: "Only you. Existing keys stop working." },
  shared: { label: "Shared", help: "People you give a key to, at the chosen precision." },
  public: { label: "Public", help: "Listed for every signed-in user, cloaked." },
};
export const PRECISIONS = [100, 500, 1000];

/** All of the user's boxes, numbered by deposit order (Box 001 = first ever deposited). */
export async function loadBoxes() {
  const all = [];
  for (let offset = 0; offset < CAPACITY; offset += 100) {
    const page = await api("/api/favourites", { params: { limit: 100, offset } });
    all.push(...page);
    if (page.length < 100) break;
  }
  all.sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
  all.forEach((b, i) => { b.number = i + 1; });
  return all;
}

export async function render(ctx, params) {
  return params.mode === "new" ? renderDeposit(ctx, params) : renderList(ctx);
}

async function renderList(ctx) {
  clear(ctx.body, loading("Opening your vault…"));
  const boxes = await loadBoxes();
  const inRegion = boxes.filter((b) => b.region === ctx.region.code);
  mapView.showBoxes(inRegion, (b) => ctx.navigate(`#/vault/${b.id}`));

  const elsewhere = boxes.length - inRegion.length;
  clear(ctx.body,
    h("div", { class: "view-head" },
      h("div", {},
        h("h1", { class: "view-title", text: "My vault" }),
        h("p", { class: "view-sub", text: `${ctx.region.name}: ${inRegion.length} ${inRegion.length === 1 ? "box" : "boxes"}${elsewhere ? `, ${elsewhere} in other cities` : ""}` })),
      h("span", { class: "capacity", title: "Boxes used of your allowance", text: `${fmt.count(boxes.length)} / ${fmt.count(CAPACITY)}` })),
    h("a", { class: "btn btn-brass btn-block", href: "#/vault/new" }, icon("plus", "i i-sm"), "Deposit a place"),
    h("h2", { class: "section-title", text: "Boxes" }),
    boxes.length
      ? h("ul", { class: "list", "aria-label": "Your boxes" }, boxes.map((b) => h("li", {}, boxRow(ctx, b))))
      : empty("vault", "Your vault is empty. Deposit a place: click the map, or open a public place in the Hall and choose Deposit."),
  );
  const off = ctx.onRegion(() => ctx.navigate("#/vault"));
  return () => { off(); mapView.clearBoxes(); };
}

function boxRow(ctx, b) {
  const city = ctx.regions.get(b.region)?.name || b.region;
  const meta = [city, VISIBILITY[b.visibility].label, b.visibility === "private" ? null : `${fmt.metres(b.share_precision_m)} cell`].filter(Boolean).join(" · ");
  return h("button", {
    class: "row box-row", type: "button",
    onClick: () => { if (b.region !== ctx.region.code) ctx.setRegion(b.region, { silent: true }); ctx.navigate(`#/vault/${b.id}`); },
  },
  plate(fmt.boxNo(b.number), "box-no"),
  h("span", {}, h("span", { class: "row-title", text: b.label }), h("span", { class: "row-meta", text: meta })),
  h("span", { class: "row-end" }, b.has_photo ? icon("photo", "i i-sm") : null, b.visibility === "private" ? icon("lock", "i i-sm") : icon("key", "i i-sm")));
}

// ---------------------------------------------------------------- deposit
async function renderDeposit(ctx, params) {
  const placeId = params.query.get("place");
  let place = null;
  if (placeId && /^\d+$/.test(placeId)) {
    try { place = await api(`/api/places/${placeId}`, { auth: false }); } catch { place = null; }
  }
  const state = {
    location: place ? { lat: place.geometry.coordinates[1], lon: place.geometry.coordinates[0] } : null,
    visibility: "private",
    precision: 500,
  };

  const errorSlot = h("div");
  const label = h("input", { class: "input", name: "label", required: true, maxlength: "100", value: place ? place.properties.name : "" });
  const note = h("textarea", { class: "textarea", name: "note", maxlength: "2000", placeholder: "Only you will ever see this note." });
  const where = h("div", { class: "coords" });
  const save = h("button", { class: "btn btn-brass btn-block", type: "submit" }, icon("vault", "i i-sm"), "Lock it in the vault");
  const visSeg = segmented("Visibility", Object.entries(VISIBILITY).map(([k, v]) => [k, v.label]), () => state.visibility, (v) => { state.visibility = v; });
  const precSeg = segmented("Share precision", PRECISIONS.map((p) => [p, fmt.metres(p)]), () => state.precision, (v) => { state.precision = v; });

  function renderWhere() {
    clear(where, icon(state.location ? "pin" : "crosshair"),
      state.location
        ? h("span", { class: "mono", text: `${fmt.coord(state.location.lat)}, ${fmt.coord(state.location.lon)}` })
        : h("span", { class: "coords-hint", text: "Click the map to set the spot" }),
      h("span", { class: "tag" }, icon("lock", "i i-sm"), "Exact, owner only"));
    save.disabled = !state.location;
  }

  let stopPick = () => {};
  const banner = document.getElementById("map-banner");
  if (!place) {
    stopPick = mapView.startPick((loc) => { state.location = loc; renderWhere(); });
    clear(banner, icon("crosshair"), h("span", { text: "Click the map where this place is" }));
    banner.hidden = false;
  } else {
    mapView.flyTo(state.location.lat, state.location.lon, 17);
  }

  const form = h("form", {},
    errorSlot,
    h("label", { class: "field" }, h("span", { text: "Label" }), label),
    h("div", { class: "field" }, h("span", { class: "field-label", text: "Exact spot" }), where,
      place ? h("small", { class: "hint", text: `From the public place “${place.properties.name}”. Shared views never reveal this link.` }) : null),
    h("label", { class: "field" }, h("span", { text: "Private note" }), note),
    h("div", { class: "field" }, h("span", { class: "field-label", text: "Visibility" }), visSeg.node, h("small", { class: "hint", text: "Private by default. You can change this any time." })),
    h("div", { class: "field" }, h("span", { class: "field-label", text: "When shared, round to" }), precSeg.node),
    save);
  renderWhere();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.location) return;
    save.disabled = true;
    clear(errorSlot);
    const body = { label: label.value, note: note.value || null, visibility: state.visibility, share_precision_m: state.precision };
    if (place) body.place_id = place.id; else body.location = state.location;
    try {
      const fav = await api("/api/favourites", { method: "POST", body });
      toast("Deposited. The exact spot is visible only to you.");
      ctx.navigate(`#/vault/${fav.id}`);
    } catch (err) {
      clear(errorSlot, formError(err.message));
      save.disabled = false;
    }
  });

  clear(ctx.body,
    h("a", { class: "back-link", href: "#/vault" }, icon("back", "i i-sm"), "My vault"),
    h("div", { class: "view-head" }, h("h1", { class: "view-title", text: "Deposit a place" })),
    form);
  label.focus();
  return () => { stopPick(); banner.hidden = true; };
}

/** Plate-style segmented control. options: [[value, label], ...] */
export function segmented(ariaLabel, options, get, set) {
  const node = h("div", { class: "segmented", role: "group", "aria-label": ariaLabel });
  const draw = () => clear(node, options.map(([value, text]) => h("button", {
    type: "button", "aria-pressed": String(get() === value),
    onClick: () => { set(value); draw(); },
  }, text)));
  draw();
  return { node, redraw: draw };
}
