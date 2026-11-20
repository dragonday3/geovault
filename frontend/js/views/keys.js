// Keys: boxes other people have shared with you (cloaked).
import { api, blobUrl } from "../api.js";
import { clear, empty, fmt, h, icon, loading, plate } from "../dom.js";
import * as mapView from "../map.js";

export async function render(ctx) {
  clear(ctx.body, loading("Checking your key ring…"));
  const received = await api("/api/shared/with-me");
  let photoUrl = null;
  const detail = h("div");

  async function open(share) {
    if (share.region !== ctx.region.code) ctx.setRegion(share.region, { silent: true });
    mapView.showCloakedCell(share.location.lat, share.location.lon, share.location.precision_m);
    if (photoUrl) { URL.revokeObjectURL(photoUrl); photoUrl = null; }
    let photo = null;
    if (share.has_photo) {
      try {
        photoUrl = await blobUrl(`/api/shared/with-me/${share.share_id}/photo`);
        photo = h("img", { src: photoUrl, alt: `Photo shared by ${share.owner_display_name}` });
      } catch { photo = null; }
    }
    const exp = fmt.expiry(share.expires_at);
    clear(detail, h("article", { class: "panel-light share-card" },
      h("div", { class: "actions" }, plate(`${fmt.metres(share.location.precision_m)} cell`), plate(exp.text, exp.state === "expiring" ? "" : "plate-steel")),
      h("h2", { text: share.label }),
      h("p", { class: "meta", text: `From ${share.owner_display_name} · ${ctx.regions.get(share.region)?.name || share.region}` }),
      h("dl", { class: "kv" }, h("dt", { text: "Cell centre" }), h("dd", { class: "mono", text: `${fmt.coord(share.location.lat)}, ${fmt.coord(share.location.lon)}` })),
      photo,
      h("p", { class: "callout" }, icon("cell"), h("span", { text: `You see the centre of a ${fmt.metres(share.location.precision_m)} grid cell. ${share.owner_display_name}'s exact spot, note and email are never shared.` }))));
  }

  clear(ctx.body,
    h("div", { class: "view-head" }, h("div", {},
      h("h1", { class: "view-title", text: "Keys" }),
      h("p", { class: "view-sub", text: "Places other people have shared with you." }))),
    detail,
    received.length
      ? h("div", {}, received.map((s) => {
          const exp = fmt.expiry(s.expires_at);
          return h("button", { class: "key-tag is-button", type: "button", onClick: () => open(s) },
            h("span", { class: "key-hole", "aria-hidden": "true" }),
            h("span", {},
              h("span", { class: "key-title", text: s.label }),
              h("span", { class: "key-meta" }, `${s.owner_display_name} · ${ctx.regions.get(s.region)?.name || s.region} · `,
                h("span", { class: `stamp ${exp.state === "expiring" ? "stamp-expiring" : ""}`, text: exp.text }))),
            h("span", { class: "row-end" }, s.has_photo ? icon("photo", "i i-sm") : null, icon("chevron", "i i-sm")));
        }))
      : empty("key", "No one has shared a place with you yet. When they do, their key appears here."));

  return () => { mapView.clearLens(); if (photoUrl) URL.revokeObjectURL(photoUrl); };
}
