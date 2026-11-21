// The Hall: public places of the selected city.
import { api, session } from "../api.js";
import { clear, copyText, fmt, h, icon, loading, plate, toast } from "../dom.js";
import * as mapView from "../map.js";
import { GROUPS, glyph, groupOf } from "../categories.js";

const LIST_LIMIT = 500;
const SHOWN_ROWS = 150;
const RADII = [250, 500, 1000, 2000, 5000];
const BHUVAN = "https://bhuvan-app1.nrsc.gov.in/bhuvan2d/bhuvan/bhuvan2d.php";

export async function render(ctx) {
  const state = { q: "", group: null, near: null, radius: 1000, selected: null, categories: [] };
  let seq = 0;
  let debounce;

  const placeSlot = h("div");
  const searchInput = h("input", {
    class: "input", type: "search", placeholder: "Search places by name", maxlength: "100",
    "aria-label": "Search places by name", autocomplete: "off",
  });
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Map key and category filter" });
  const statusLine = h("div", { class: "status-line", role: "status" });
  const list = h("ul", { class: "list", "aria-label": "Places" });

  const sourceList = h("ul");
  for (const s of ctx.sources.filter((x) => x.region === ctx.region.code)) {
    sourceList.append(h("li", {}, h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer", text: s.dataset }), ` — ${s.attribution}`));
  }

  clear(ctx.body,
    h("div", { class: "view-head" },
      h("div", {},
        h("h1", { class: "view-title", text: `${ctx.region.name} public hall` }),
        h("p", { class: "view-sub", text: "Open data anyone may see. Your own places stay in your vault." }))),
    placeSlot,
    h("div", { class: "search" }, icon("search"), searchInput),
    chips,
    statusLine,
    list,
    h("div", { class: "sources" }, h("h2", { class: "section-title", text: "Data sources" }), sourceList));

  // ---------------------------------------------------------------- categories
  async function loadCategories() {
    state.categories = await api("/api/categories", { params: { region: ctx.region.code }, auth: false });
    renderChips();
  }

  // The chips are the map key: each group's glyph (hue + shape) as drawn on the map, its count,
  // and a filter. Groups follow the fixed order in categories.js so a hue never changes meaning.
  function groupTotals() {
    const totals = new Map();
    for (const c of state.categories) {
      const g = groupOf(c.category);
      const t = totals.get(g) || { count: 0, categories: [] };
      t.count += c.count;
      t.categories.push(c.category);
      totals.set(g, t);
    }
    return totals;
  }

  function selectedCategories() {
    return state.group ? groupTotals().get(state.group)?.categories : null;
  }

  function renderChips() {
    const totals = groupTotals();
    const chip = (key, label, count) => h("button", {
      class: "chip", type: "button", "aria-pressed": String(state.group === key),
      title: key ? totals.get(key).categories.join(", ") : null,
      onClick: () => { state.group = key; renderChips(); refresh(); },
    }, key ? glyph(key, "glyph") : null, label, count !== undefined ? h("span", { class: "count", text: fmt.count(count) }) : null);
    clear(chips, chip(null, "All"),
      Object.entries(GROUPS).filter(([key]) => totals.has(key)).map(([key, g]) => chip(key, g.label, totals.get(key).count)));
  }

  // ---------------------------------------------------------------- results
  async function refresh() {
    const mine = ++seq;
    clear(statusLine, loading("Searching the hall…"));
    try {
      let data;
      if (state.near) {
        data = await api("/api/places/near", {
          auth: false,
          params: { lat: state.near.lat, lon: state.near.lon, radius_m: state.radius, limit: 100, region: ctx.region.code, category: selectedCategories() },
        });
      } else {
        data = await api("/api/places", {
          auth: false,
          params: { region: ctx.region.code, category: selectedCategories(), q: state.q, bbox: mapView.viewBbox(), limit: LIST_LIMIT },
        });
      }
      if (mine !== seq) return;
      renderResults(data.features);
    } catch (err) {
      if (mine === seq) clear(statusLine, h("span", { text: err.message }));
    }
  }

  function renderResults(features) {
    mapView.showPlaces(features, (f) => select(f));
    const n = features.length;
    let text;
    if (state.near) text = `${fmt.count(n)} within ${fmt.metres(state.radius)} of ${state.near.name}`;
    else if (n >= LIST_LIMIT) text = `First ${fmt.count(LIST_LIMIT)} in view. Zoom in or filter for the rest`;
    else text = `${fmt.count(n)} ${n === 1 ? "place" : "places"} in view`;
    clear(statusLine, h("span", { text }), state.near ? h("button", {
      class: "btn btn-quiet btn-sm", type: "button", onClick: () => { state.near = null; renderPlace(); refresh(); },
    }, "Clear nearby") : null);

    clear(list, features.slice(0, SHOWN_ROWS).map((f) => h("li", {},
      h("button", {
        class: "row", type: "button", "aria-current": state.selected?.id === f.id ? "true" : null,
        onClick: () => { select(f); mapView.flyTo(f.geometry.coordinates[1], f.geometry.coordinates[0], 16); },
      },
      h("span", { class: "row-main" }, glyph(groupOf(f.properties.category), "glyph"), h("span", {}, h("span", { class: "row-title", text: f.properties.name }), plate(f.properties.category, "plate-steel"))),
      h("span", { class: "row-end" }, typeof f.properties.distance_m === "number" ? h("span", { class: "mono", text: fmt.metres(f.properties.distance_m) }) : null, icon("chevron", "i i-sm"))))));
    if (!n) list.append(h("li", { class: "empty" }, "No places here. Pan the map, clear the filter or try another search."));
    else if (n > SHOWN_ROWS) list.append(h("li", { class: "fine", text: `${fmt.count(n - SHOWN_ROWS)} more on the map.` }));
  }

  // ---------------------------------------------------------------- selected place
  function select(f) {
    state.selected = f;
    mapView.highlightPlace(f.id);
    renderPlace();
    for (const row of list.querySelectorAll(".row")) row.removeAttribute("aria-current");
  }

  function renderPlace() {
    const f = state.selected;
    if (!f) { clear(placeSlot); return; }
    const [lon, lat] = f.geometry.coordinates;
    const source = ctx.sources.find((s) => s.key === f.properties.source);
    const india = ctx.region.country_code === "IN";
    clear(placeSlot, h("article", { class: "panel-light place-card", "aria-label": "Selected place" },
      h("div", { class: "view-head" },
        plate(f.properties.category),
        h("button", { class: "btn btn-ghost btn-sm btn-icon", type: "button", "aria-label": "Close place", onClick: () => { state.selected = null; mapView.highlightPlace(null); renderPlace(); } }, icon("close", "i i-sm"))),
      h("h3", { text: f.properties.name }),
      h("dl", { class: "kv" },
        h("dt", { text: "Position" }), h("dd", { class: "mono", text: `${fmt.coord(lat)}, ${fmt.coord(lon)}` }),
        h("dt", { text: "Source" }), h("dd", { text: source ? `${source.publisher} · ${source.licence}` : f.properties.source }),
        typeof f.properties.distance_m === "number" ? [h("dt", { text: "Distance" }), h("dd", { class: "mono", text: fmt.metres(f.properties.distance_m) })] : null),
      h("div", { class: "actions" },
        session.signedIn
          ? h("a", { class: "btn btn-brass btn-sm", href: `#/vault/new?place=${f.id}` }, icon("plus", "i i-sm"), "Deposit in my vault")
          : h("a", { class: "btn btn-brass btn-sm", href: "#/signin" }, icon("vault", "i i-sm"), "Sign in to deposit"),
        h("button", {
          class: "btn btn-ghost btn-sm", type: "button",
          onClick: () => { state.near = { lat, lon, name: f.properties.name }; renderPlace(); refresh(); },
        }, icon("crosshair", "i i-sm"), "Nearby")),
      india ? h("div", { class: "actions" },
        // Link-out only: Bhuvan's terms do not cover embedding its tiles in third-party apps.
        h("a", { class: "btn btn-ghost btn-sm", href: BHUVAN, target: "_blank", rel: "noopener noreferrer" }, icon("globe", "i i-sm"), "Open Bhuvan 2D"),
        h("button", {
          class: "btn btn-ghost btn-sm", type: "button",
          onClick: async () => toast((await copyText(`${lat.toFixed(6)}, ${lon.toFixed(6)}`)) ? "Coordinates copied for Bhuvan's find tool." : "Copy failed.", "info"),
        }, icon("copy", "i i-sm"), "Copy coordinates")) : null,
      state.near ? renderRadius() : null));
  }

  function renderRadius() {
    return h("div", { class: "actions" }, h("div", { class: "segmented", role: "group", "aria-label": "Nearby radius" },
      RADII.map((r) => h("button", {
        type: "button", "aria-pressed": String(state.radius === r),
        onClick: () => { state.radius = r; renderPlace(); refresh(); },
      }, fmt.metres(r)))));
  }

  // ---------------------------------------------------------------- wiring
  searchInput.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.q = searchInput.value.trim(); state.near = null; renderPlace(); refresh(); }, 250);
  });
  const offMove = mapView.onMove(() => { if (!state.near) { clearTimeout(debounce); debounce = setTimeout(refresh, 250); } });
  const offRegion = ctx.onRegion(() => ctx.navigate("#/hall"));

  await loadCategories();
  await refresh();

  return () => { offMove(); offRegion(); clearTimeout(debounce); mapView.clearPlaces(); };
}
