"use strict";
// GeoVault frontend. SECURITY RULE: API data is only ever written with textContent /
// DOM APIs — never innerHTML — so place names cannot inject markup or script.

(() => {
  const PALETTE = ["#2563eb", "#16a34a", "#d97706", "#9333ea", "#dc2626", "#0891b2", "#db2777", "#65a30d"];

  const $ = (id) => document.getElementById(id);
  const state = { region: null, category: null, q: "", near: null };
  const regions = new Map();
  const colours = new Map();

  // Each region clamps the map to its bounds at city zoom (maxBoundsViscosity 1 = hard edge).
  // For India this guarantees national/international boundaries are never rendered.
  const map = L.map("map", { zoomControl: true, maxBoundsViscosity: 1.0 }).setView([0, 0], 3);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  const markers = L.layerGroup().addTo(map);
  let nearCircle = null;

  function colourFor(category) {
    if (!colours.has(category)) colours.set(category, PALETTE[colours.size % PALETTE.length]);
    return colours.get(category);
  }

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  async function api(path, params = {}) {
    const url = new URL(path, window.location.origin);
    for (const [k, v] of Object.entries(params)) {
      if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
    }
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    return res.json();
  }

  function setStatus(text) { $("status").textContent = text; }

  function showDetail(feature) {
    const [lon, lat] = feature.geometry.coordinates;
    const p = feature.properties;
    $("detail-name").textContent = p.name;
    $("detail-category").textContent = p.category;
    $("detail-category").style.background = colourFor(p.category);
    $("detail-coords").textContent = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    $("detail-source").textContent = p.source;
    const hasDist = typeof p.distance_m === "number";
    $("detail-distance-label").hidden = !hasDist;
    $("detail-distance").hidden = !hasDist;
    if (hasDist) $("detail-distance").textContent = `${Math.round(p.distance_m)} m`;
    $("detail").hidden = false;
  }

  function render(features) {
    markers.clearLayers();
    const list = $("results");
    list.replaceChildren();
    $("count").textContent = `(${features.length})`;

    for (const f of features) {
      const [lon, lat] = f.geometry.coordinates;
      const colour = colourFor(f.properties.category);
      const marker = L.circleMarker([lat, lon], {
        radius: 8, color: "#fff", weight: 2, fillColor: colour, fillOpacity: 0.95,
      });
      // bindTooltip with a DOM node (not a string) — Leaflet would treat a string as HTML.
      marker.bindTooltip(el("span", f.properties.name));
      marker.on("click", () => showDetail(f));
      markers.addLayer(marker);

      const item = el("li");
      const btn = el("button", undefined, "result");
      btn.type = "button";
      const dot = el("span", undefined, "dot");
      dot.style.background = colour;
      btn.append(dot, el("span", f.properties.name, "result-name"));
      if (typeof f.properties.distance_m === "number") {
        btn.append(el("span", `${Math.round(f.properties.distance_m)} m`, "result-dist"));
      }
      btn.addEventListener("click", () => {
        map.setView([lat, lon], Math.max(map.getZoom(), 16));
        showDetail(f);
      });
      item.append(btn);
      list.append(item);
    }
    setStatus(features.length ? "" : "No places match.");
  }

  async function refresh() {
    setStatus("Loading…");
    try {
      let data;
      if (state.near) {
        data = await api("/api/places/near", {
          lat: state.near.lat, lon: state.near.lng,
          radius_m: $("radius").value, limit: 100, category: state.category, region: state.region,
        });
      } else {
        data = await api("/api/places", {
          region: state.region, category: state.category, q: state.q, limit: 500,
        });
      }
      render(data.features);
    } catch (err) {
      setStatus("Could not load places. Is the API running?");
    }
  }

  async function loadCategories() {
    const box = $("categories");
    try {
      const cats = await api("/api/categories", { region: state.region });
      const all = el("button", "All", "chip active");
      all.type = "button";
      all.addEventListener("click", () => selectCategory(null, all));
      box.replaceChildren(all);
      for (const c of cats) {
        const chip = el("button", undefined, "chip");
        chip.type = "button";
        const dot = el("span", undefined, "dot");
        dot.style.background = colourFor(c.category);
        chip.append(dot, el("span", `${c.category} (${c.count})`));
        chip.addEventListener("click", () => selectCategory(c.category, chip));
        box.append(chip);
      }
    } catch {
      box.replaceChildren(el("span", "Categories unavailable", "hint"));
    }
  }

  function selectCategory(category, chip) {
    state.category = category;
    for (const c of document.querySelectorAll(".chip")) c.classList.remove("active");
    chip.classList.add("active");
    refresh();
  }

  function searchNear(latlng) {
    state.near = latlng;
    if (nearCircle) nearCircle.remove();
    nearCircle = L.circle(latlng, {
      radius: Number($("radius").value), color: "#2563eb", weight: 1, fillOpacity: 0.06,
    }).addTo(map);
    refresh();
  }

  let debounce;
  $("search").addEventListener("input", (e) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.q = e.target.value.trim();
      state.near = null;
      if (nearCircle) { nearCircle.remove(); nearCircle = null; }
      refresh();
    }, 250);
  });
  $("search-form").addEventListener("submit", (e) => e.preventDefault());
  $("near-btn").addEventListener("click", () => searchNear(map.getCenter()));
  $("radius").addEventListener("change", () => { if (state.near) searchNear(state.near); });
  map.on("click", (e) => searchNear(e.latlng));
  $("clear-btn").addEventListener("click", () => {
    resetSearch();
    loadCategories().then(refresh);
  });

  function resetSearch() {
    state.near = null; state.q = ""; state.category = null; $("search").value = "";
    if (nearCircle) { nearCircle.remove(); nearCircle = null; }
    $("detail").hidden = true;
  }

  function applyRegion(code) {
    const r = regions.get(code);
    if (!r) return;
    state.region = code;
    const [minLon, minLat, maxLon, maxLat] = r.bbox;
    const bounds = L.latLngBounds([minLat, minLon], [maxLat, maxLon]);
    map.setMinZoom(r.min_zoom);
    map.setMaxBounds(bounds);
    map.setView([r.centre[1], r.centre[0]], r.default_zoom);
    $("subtitle").textContent = `${r.name} public places`;
    resetSearch();
    loadCategories().then(refresh);
  }

  async function init() {
    try {
      const list = await api("/api/regions");
      const select = $("region");
      for (const r of list) {
        regions.set(r.code, r);
        const opt = el("option", `${r.name} (${r.country_code})`);
        opt.value = r.code;
        select.append(opt);
      }
      select.addEventListener("change", () => applyRegion(select.value));
      if (list.length) applyRegion(list[0].code);
    } catch {
      setStatus("Could not load regions. Is the API running?");
    }
  }

  init();
})();
