// Place-category groups: one fixed hue AND shape per group (colour is never the only cue).
// Hues come from the validated reference palette (dataviz skill). With up to 8 groups on one map
// every pair can sit side by side, and the validator showed some hue pairs too close for
// colour-blind (and even normal) vision. So any two groups whose hues clash get different
// shapes, every marker has a dark ink ring for contrast on the light basemap, each marker's
// tooltip names it, and the chips double as legend and filter.
//   clashing pairs (validator): rail–edu, bus–park, bus–culture, bus–health, bus–community,
//   culture–health. Shapes below keep every one of those pairs apart.

const SVG_NS = "http://www.w3.org/2000/svg";

export const GROUPS = {
  rail: { label: "Rail, metro & tram", shape: "square" },
  bus: { label: "Bus & BRT", shape: "diamond" },
  park: { label: "Parks, play & sport", shape: "circle" },
  culture: { label: "Culture & landmarks", shape: "circle" },
  health: { label: "Health & emergency", shape: "triangle" },
  edu: { label: "Education", shape: "circle" },
  community: { label: "Worship, community & markets", shape: "square" },
  amenity: { label: "Everyday amenities", shape: "circle" },
};

const CATEGORY_GROUP = {
  "Rail, metro and tram": "rail",
  "Bus and BRT": "bus",
  "Park and garden": "park",
  Playground: "park",
  "Sport and recreation": "park",
  Library: "culture",
  "Museum and gallery": "culture",
  "Theatre and venue": "culture",
  "Public art and monument": "culture",
  Landmark: "culture",
  Health: "health",
  "Emergency services": "health",
  Education: "edu",
  "Place of worship": "community",
  "Community centre": "community",
  "Market and shopping": "community",
  "Public toilet": "amenity",
  "Drinking water": "amenity",
  "EV charging": "amenity",
  "Post office": "amenity",
};

export const groupOf = (category) => CATEGORY_GROUP[category] || "amenity";

const SHAPES = {
  circle: () => el("circle", { cx: 8, cy: 8, r: 6 }),
  square: () => el("rect", { x: 2.25, y: 2.25, width: 11.5, height: 11.5, rx: 1 }),
  diamond: () => el("polygon", { points: "8,0.9 15.1,8 8,15.1 0.9,8" }),
  triangle: () => el("polygon", { points: "8,1.2 15,14.4 1,14.4" }),
};

function el(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

/** The group's glyph: shape + hue + ink ring. */
export function glyph(group, cls = "glyph") {
  const g = GROUPS[group] || GROUPS.amenity;
  const svg = el("svg", { viewBox: "0 0 16 16", class: cls, "aria-hidden": "true" });
  const shape = SHAPES[g.shape]();
  shape.setAttribute("class", `shape g-${group}`);
  svg.append(shape);
  return svg;
}
