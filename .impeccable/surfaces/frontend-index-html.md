---
version: 1
slug: "frontend-index-html"
primary_target: "frontend/index.html"
related_targets: ["frontend/app.js","frontend/styles.css"]
---

# Surface brief: GeoVault app shell (frontend/index.html)

Scope: the whole single-page app. Hall (public places explorer for Melbourne, Bengaluru and
Ahmedabad), sign-in/register, My vault (favourites list and detail, photo, sharing), Keys
(shared with me), public share-link view, account settings, admin (users, roles, access
register).

Visitor mode: **Operate**. Reviewers complete real tasks fast. Expression lives in precise
details and never obscures task, state or affordance.

Constraints:
- strict CSP: self-hosted only, no inline script or style;
- textContent-only DOM;
- access token in memory only;
- every region clamped to city zoom;
- WCAG 2.2 AA;
- the lab-mode banner slot is reserved.

## Direction contract

THESIS: GeoVault is a safe-deposit hall. The city map is the public hall, your places are
numbered private boxes, a share is a key with a stamped expiry, and the audit trail is the
access register. It refuses both category defaults: the white sidebar with a blue-accent list
over a map, and the dark neon security dashboard.

OWN-WORLD: vault-green enamel owns the header and the drawer rail at region scale. Brushed
steel neutrals carry panels and the map frame. Brass is reserved for number plates, the
primary action and focus. Ledger-ink text, with oxide red only for revoked or expired.
Engraved plates use condensed caps with tabular figures and a 1px inset double rule.
Coordinates are set in a monospaced face. Corners are 2px at most and there are no soft
shadows. Key tags carry a punched hole and a stamped expiry. Register rows are ruled.

STORY: the reviewer lands in the hall of a city and explores real places. They open their
vault, deposit a place by clicking the map, and see owner truth: exact coordinates, note,
photo. The cloak lens shows what everyone else sees. They issue a key, then watch it appear
in the access register.

FIRST VIEWPORT: a 56px vault-green header holds the engraved GeoVault wordmark, segmented
brass city plates (MEL / BLR / AMD) and the account plate at the right. The map fills about
70% at the left. A 400px vault-green drawer rail on the right carries tabs (Hall, My vault,
Keys, Register for admins) and below them search, category chips and a list of plates. The
brass "Deposit a place" action sits at the top of My vault. On mobile, the map takes the top
55vh and the rail becomes a sheet below it.
SIGNATURE: the cloak lens. In box detail, switching Owner view to Shared view slides the pin
from its exact spot into its server-computed grid cell, which is drawn at the chosen precision.
MOTION: drawers move on one axis, plates press 1px, the pin tween runs 600ms, and
reduced-motion is honoured.

FORM: Safe-deposit Hall, position 7 of the ordered grounded list, seed key 00bf38e4.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
