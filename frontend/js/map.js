// The hall map: public places (category glyphs), private boxes (brass plates), the deposit
// picker, and the cloak lens (the signature interaction).
/* global L */
import { h } from "./dom.js";
import { glyph, groupOf } from "./categories.js";

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

let map;
let placesLayer;
let boxesLayer;
let lensLayer;
let pickLayer;
let activePlace = null;
const placeMarkers = new Map();
const boxMarkers = new Map();

export function initMap(el) {
  // maxBoundsViscosity 1 = a hard edge: each city is clamped at city zoom, so national and
  // international boundaries are never rendered (Survey of India depiction requirement).
  map = L.map(el, { zoomControl: false, maxBoundsViscosity: 1.0, attributionControl: true }).setView([0, 0], 3);
  L.control.zoom({ position: "bottomleft" }).addTo(map);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  placesLayer = L.layerGroup().addTo(map);
  boxesLayer = L.layerGroup().addTo(map);
  lensLayer = L.layerGroup().addTo(map);
  pickLayer = L.layerGroup().addTo(map);
  map.on("zoomend", () => { if (boxEntries.length) layoutBoxes(); });
  return map;
}

export const getMap = () => map;

export function setRegion(region) {
  const [minLon, minLat, maxLon, maxLat] = region.bbox;
  map.setMinZoom(region.min_zoom);
  map.setMaxBounds(L.latLngBounds([minLat, minLon], [maxLat, maxLon]));
  map.setView([region.centre[1], region.centre[0]], region.default_zoom, { animate: false });
}

export function viewBbox() {
  const b = map.getBounds();
  return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(6)).join(",");
}

export function onMove(fn) { map.on("moveend", fn); return () => map.off("moveend", fn); }

export function flyTo(lat, lon, zoom) {
  const z = Math.max(map.getZoom(), zoom || 16);
  if (reducedMotion.matches) map.setView([lat, lon], z);
  else map.flyTo([lat, lon], z, { duration: 0.6 });
}

// ---------------------------------------------------------------- public places
export function showPlaces(features, onSelect) {
  placesLayer.clearLayers();
  placeMarkers.clear();
  activePlace = null;
  for (const f of features) {
    const [lon, lat] = f.geometry.coordinates;
    // Each category group has its own hue AND shape (categories.js), so colour is never the only cue.
    const pin = glyph(groupOf(f.properties.category), "place-glyph");
    const icon = L.divIcon({ html: pin, className: "place-pin", iconSize: [16, 16], iconAnchor: [8, 8] });
    const marker = L.marker([lat, lon], { icon, keyboard: false, riseOnHover: true });
    // Tooltip content is a DOM node: Leaflet would treat a string as HTML.
    marker.bindTooltip(h("span", {}, h("span", { text: f.properties.name }), h("span", { class: "tip-cat", text: f.properties.category })),
      { direction: "top", offset: [0, -8] });
    marker.on("click", () => onSelect(f));
    marker.addTo(placesLayer);
    placeMarkers.set(f.id, marker);
  }
}

export function highlightPlace(id) {
  activePlace?.getElement()?.classList.remove("is-active");
  activePlace?.setZIndexOffset(0);
  activePlace = placeMarkers.get(id) || null;
  activePlace?.getElement()?.classList.add("is-active");
  activePlace?.setZIndexOffset(1000);
}

export function clearPlaces() { placesLayer.clearLayers(); placeMarkers.clear(); activePlace = null; }

// ---------------------------------------------------------------- private boxes
function boxIcon(number, extra = "", lift = 0) {
  const el = h("div", { class: `box-marker ${extra}`.trim(), text: String(number).padStart(3, "0") });
  return L.divIcon({ html: el, className: "", iconSize: [26, 22], iconAnchor: [13, 11 + lift] });
}

let boxEntries = [];

/** Plates that would overlap at this zoom stack upward in 24px steps, so none is hidden. */
function layoutBoxes() {
  const placed = [];
  for (const { marker, box } of boxEntries) {
    const p = map.latLngToLayerPoint([box.location.lat, box.location.lon]);
    let lift = 0;
    while (lift < 6 * 24 && placed.some((q) => Math.abs(q.x - p.x) < 30 && Math.abs(q.y - (p.y - lift)) < 24)) lift += 24;
    placed.push({ x: p.x, y: p.y - lift });
    marker.setIcon(boxIcon(box.number, "", lift));
  }
}

export function showBoxes(boxes, onSelect) {
  boxesLayer.clearLayers();
  boxMarkers.clear();
  boxEntries = [];
  for (const box of boxes) {
    const marker = L.marker([box.location.lat, box.location.lon], { icon: boxIcon(box.number), keyboard: true, title: box.label });
    marker.on("click", () => onSelect(box));
    marker.addTo(boxesLayer);
    boxMarkers.set(box.id, marker);
    boxEntries.push({ marker, box });
  }
  layoutBoxes();
}

export function clearBoxes() { boxesLayer.clearLayers(); boxMarkers.clear(); boxEntries = []; }

// ---------------------------------------------------------------- deposit picker
export function startPick(onPick) {
  const el = map.getContainer();
  el.classList.add("picking");
  pickLayer.clearLayers();
  const handler = (e) => {
    pickLayer.clearLayers();
    L.marker(e.latlng, { icon: L.divIcon({ html: h("div", { class: "pick-marker" }), className: "", iconSize: [18, 18] }) }).addTo(pickLayer);
    onPick({ lat: e.latlng.lat, lon: e.latlng.lng });
  };
  map.on("click", handler);
  return () => {
    map.off("click", handler);
    el.classList.remove("picking");
    pickLayer.clearLayers();
  };
}

// ---------------------------------------------------------------- the cloak lens
let lensMarker = null;
let lensAnim = null;

function tween(marker, from, to, ms = 600) {
  cancelAnimationFrame(lensAnim);
  if (reducedMotion.matches) { marker.setLatLng(to); return; }
  const start = performance.now();
  const ease = (t) => 1 - Math.pow(2, -10 * t); // exponential ease-out
  const step = (now) => {
    const t = Math.min(1, (now - start) / ms);
    const k = ease(t);
    marker.setLatLng([from[0] + (to[0] - from[0]) * k, from[1] + (to[1] - from[1]) * k]);
    if (t < 1) lensAnim = requestAnimationFrame(step);
  };
  lensAnim = requestAnimationFrame(step);
}

/**
 * Owner view: the box sits on its exact point.
 * Shared view: the server-computed grid cell is drawn and the box slides into its centre,
 * which is exactly the point a share recipient receives.
 */
export function showLens({ number, exact, preview, mode }) {
  lensLayer.clearLayers();
  const exactLL = [exact.lat, exact.lon];
  if (mode === "shared" && preview) {
    const ring = preview.cell.map(([lon, lat]) => [lat, lon]);
    L.polygon(ring, {
      color: "#b08a3e", weight: 2, dashArray: "6 5", fillColor: "#dcb86c", fillOpacity: 0.16, interactive: false,
    }).addTo(lensLayer);
    L.circleMarker(exactLL, { radius: 4, color: "#7a5c22", weight: 1.5, fillColor: "#ffffff", fillOpacity: 1, interactive: false })
      .bindTooltip(h("span", { text: "True spot · only you" }), { permanent: true, direction: "right", offset: [8, 0], className: "true-spot-label" })
      .addTo(lensLayer);
  }
  const from = lensMarker ? [lensMarker.getLatLng().lat, lensMarker.getLatLng().lng] : exactLL;
  const target = mode === "shared" && preview ? [preview.location.lat, preview.location.lon] : exactLL;
  lensMarker = L.marker(from, {
    icon: boxIcon(number, mode === "shared" ? "is-cloaked" : "is-active"),
    interactive: false,
    zIndexOffset: 1000,
  }).addTo(lensLayer);
  tween(lensMarker, from, target);
  if (mode === "shared" && preview) {
    map.fitBounds(L.latLngBounds(preview.cell.map(([lon, lat]) => [lat, lon])).pad(0.35), { maxZoom: 17, animate: !reducedMotion.matches });
  }
}

/** A share recipient only knows the cloaked centre and precision: draw that cell. */
export function showCloakedCell(lat, lon, precisionM) {
  lensLayer.clearLayers();
  const dLat = precisionM / 2 / 111_320;
  const dLon = precisionM / 2 / (111_320 * Math.cos((lat * Math.PI) / 180));
  const bounds = L.latLngBounds([lat - dLat, lon - dLon], [lat + dLat, lon + dLon]);
  L.rectangle(bounds, { color: "#b08a3e", weight: 2, dashArray: "6 5", fillColor: "#dcb86c", fillOpacity: 0.16, interactive: false })
    .addTo(lensLayer);
  L.circleMarker([lat, lon], { radius: 6, color: "#16352c", weight: 2, fillColor: "#dcb86c", fillOpacity: 1, interactive: false })
    .addTo(lensLayer);
  map.fitBounds(bounds.pad(0.6), { maxZoom: 17, animate: !reducedMotion.matches });
}

export function clearLens() {
  cancelAnimationFrame(lensAnim);
  lensLayer.clearLayers();
  lensMarker = null;
}
