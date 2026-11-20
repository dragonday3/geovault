// Public share-link view (#/share/<token>): no account needed. The token lives in the URL
// fragment, which the browser never sends to the server; only this fetch carries it.
import { api } from "../api.js";
import { clear, empty, fmt, h, icon, loading, plate } from "../dom.js";
import * as mapView from "../map.js";

export async function render(ctx, params) {
  const token = params.match[1];
  clear(ctx.body, loading("Trying the key…"));
  let share;
  try {
    share = await api(`/api/shared/${token}`, { auth: false });
  } catch {
    clear(ctx.body,
      h("div", { class: "view-head" }, h("h1", { class: "view-title", text: "This key no longer opens anything" })),
      empty("key", "The link may have expired, been revoked, or the box was made private. Ask the person who sent it for a new key."),
      h("div", { class: "actions" }, h("a", { class: "btn btn-ghost", href: "#/hall" }, icon("hall", "i i-sm"), "Explore the public hall")));
    return null;
  }
  ctx.setRegion(share.region, { silent: true });
  mapView.showCloakedCell(share.location.lat, share.location.lon, share.location.precision_m);
  const exp = fmt.expiry(share.expires_at);
  clear(ctx.body,
    h("div", { class: "view-head" }, h("div", {},
      h("h1", { class: "view-title", text: "A place shared with you" }),
      h("p", { class: "view-sub", text: `${share.owner_display_name} sent you a key.` }))),
    h("article", { class: "panel-light share-card" },
      h("div", { class: "actions" }, plate(`${fmt.metres(share.location.precision_m)} cell`), plate(exp.text, exp.state === "expiring" ? "" : "plate-steel")),
      h("h2", { text: share.label }),
      h("p", { class: "meta", text: `${ctx.regions.get(share.region)?.name || share.region} · shared ${fmt.date(share.shared_at)}` }),
      h("dl", { class: "kv" }, h("dt", { text: "Cell centre" }), h("dd", { class: "mono", text: `${fmt.coord(share.location.lat)}, ${fmt.coord(share.location.lon)}` })),
      share.has_photo ? h("img", { src: `/api/shared/${token}/photo`, alt: `Photo shared by ${share.owner_display_name}`, referrerpolicy: "no-referrer" }) : null,
      h("p", { class: "callout" }, icon("cell"), h("span", { text: `The location is the centre of a ${fmt.metres(share.location.precision_m)} grid cell. GeoVault never shares the exact spot, the owner's notes or their email.` }))));
  return () => mapView.clearLens();
}
