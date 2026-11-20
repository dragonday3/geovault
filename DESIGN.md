---
name: GeoVault
description: A safe-deposit hall for private places. Numbered brass boxes over a steel city map, inside a vault-green enamel frame.
colors:
  vault-950: "#0b1f1a"
  vault-900: "#10291f"
  vault-800: "#16352c"
  vault-700: "#1d4337"
  vault-650: "#234d40"
  vault-600: "#2b5a4b"
  vault-rule: "#3a6b5b"
  on-vault: "#eaf1ec"
  on-vault-2: "#b3c9be"
  on-vault-3: "#8fad9f"
  steel-25: "#f7f8f8"
  steel-50: "#f0f2f2"
  steel-100: "#e3e7e7"
  steel-200: "#cdd3d4"
  steel-300: "#aab3b5"
  steel-500: "#6b767a"
  steel-700: "#444e52"
  ink: "#111617"
  ink-2: "#3c4649"
  brass-200: "#ecd49c"
  brass-300: "#dcb86c"
  brass-400: "#c9a050"
  brass-500: "#b08a3e"
  brass-700: "#7a5c22"
  brass-900: "#4a3712"
  oxide-300: "#e7978f"
  oxide-500: "#a8322c"
  oxide-700: "#7d221e"
  oxide-rule: "#6a2a26"
typography:
  headline:
    fontFamily: "Archivo, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "24px"
    fontWeight: 720
    lineHeight: 1.12
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Archivo, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Archivo, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tnum"
  row-title:
    fontFamily: "Archivo, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "14.5px"
    fontWeight: 600
  label:
    fontFamily: "Archivo, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "12px"
    fontWeight: 720
    letterSpacing: "0.14em"
    fontVariation: "'wdth' 76"
  plate:
    fontFamily: "Archivo, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "12px"
    fontWeight: 740
    lineHeight: 1.35
    letterSpacing: "0.13em"
    fontVariation: "'wdth' 70"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Mono, Consolas, monospace"
    fontSize: "14.5px"
    letterSpacing: "-0.01em"
    fontFeature: "tnum"
rounded:
  plate: "1px"
  r: "2px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "14px"
  xl: "18px"
  rail-pad: "20px 18px 28px"
  section-gap: "26px"
components:
  button-brass:
    backgroundColor: "{colors.brass-400}"
    textColor: "{colors.vault-950}"
    rounded: "{rounded.r}"
    padding: "0 14px"
    height: "38px"
  button-brass-hover:
    backgroundColor: "{colors.brass-300}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.on-vault}"
    rounded: "{rounded.r}"
    padding: "0 14px"
    height: "38px"
  button-ghost-hover:
    backgroundColor: "{colors.vault-700}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.on-vault-2}"
    padding: "0 10px"
    height: "38px"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.oxide-300}"
    rounded: "{rounded.r}"
    height: "38px"
  button-danger-hover:
    backgroundColor: "{colors.oxide-700}"
    textColor: "#ffffff"
  plate:
    backgroundColor: "transparent"
    textColor: "{colors.brass-300}"
    typography: "{typography.plate}"
    rounded: "{rounded.plate}"
    padding: "3px 8px 2px"
  plate-solid:
    backgroundColor: "{colors.brass-400}"
    textColor: "{colors.vault-950}"
    typography: "{typography.plate}"
    rounded: "{rounded.plate}"
  plate-steel:
    backgroundColor: "transparent"
    textColor: "{colors.on-vault-2}"
    typography: "{typography.plate}"
    rounded: "{rounded.plate}"
  plate-oxide:
    backgroundColor: "transparent"
    textColor: "{colors.oxide-300}"
    typography: "{typography.plate}"
    rounded: "{rounded.plate}"
  city-plate-selected:
    backgroundColor: "{colors.brass-400}"
    textColor: "{colors.vault-950}"
    padding: "6px 12px"
    height: "36px"
  segment:
    backgroundColor: "transparent"
    textColor: "{colors.on-vault-2}"
    height: "36px"
  segment-selected:
    backgroundColor: "{colors.on-vault}"
    textColor: "{colors.vault-900}"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.on-vault-2}"
    rounded: "{rounded.r}"
    padding: "0 10px"
    height: "30px"
  chip-selected:
    backgroundColor: "{colors.on-vault}"
    textColor: "{colors.vault-900}"
  input:
    backgroundColor: "{colors.vault-900}"
    textColor: "{colors.on-vault}"
    rounded: "{rounded.r}"
    padding: "8px 11px"
    height: "40px"
  input-focus:
    backgroundColor: "{colors.vault-950}"
  panel-light:
    backgroundColor: "{colors.steel-50}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r}"
    padding: "16px"
  key-tag:
    backgroundColor: "{colors.vault-900}"
    textColor: "{colors.on-vault}"
    rounded: "{rounded.r}"
    padding: "10px 10px 10px 12px"
  box-marker:
    backgroundColor: "{colors.brass-400}"
    textColor: "{colors.vault-950}"
    rounded: "{rounded.plate}"
    width: "26px"
    height: "22px"
  box-marker-cloaked:
    backgroundColor: "{colors.vault-800}"
    textColor: "{colors.brass-200}"
---

# Design System: GeoVault

## Overview

**Creative North Star: "The Safe-Deposit Hall"**

GeoVault is a bank's deposit hall rendered as an interface. The city map is the public hall floor, the user's places are numbered private boxes, a share is a key tag with a stamped expiry, and the audit log is the access register. Vault-green enamel owns the frame at region scale (the 56px header and the 400px drawer rail); brushed-steel neutrals carry the map frame and the light panels that hold owner truth; brass is the engraved metal, used sparingly so every brass object reads as a plate or a handle.

The surface is dense and ruled rather than airy: rows sit on 1px rules, register tables are ruled ledgers, labels are condensed engraved caps, and figures are tabular everywhere. Depth comes from enamel versus steel versus brass, and from edges, never from soft shadow. The world rejects both category defaults: the white sidebar with a blue-accent list over a map, and the dark neon security dashboard.

The signature is the cloak lens: in box detail, switching Owner view to Shared view slides the brass box plate from the true spot into the centre of a dashed brass grid cell. Privacy is shown as a physical move, not described.

**Key Characteristics:**
- Enamel frame, steel map, brass plates, ledger ink, oxide red only for loss.
- Engraved plates: condensed caps, tabular figures, a 1px inset double rule.
- Coordinates and stamps in a monospaced face.
- Corners at 2px or less; no soft shadows anywhere.
- One-axis motion with a single exponential ease-out; reduced motion honoured.
- Self-hosted everything under a strict CSP; DOM text set via textContent only.

## Colors

A deep green enamel field with brushed-steel panels, one warm metal accent and one alarm red.

### Primary
- **Plate Brass** (brass-400, with brass-300 as its bright face and brass-500 as its engraved edge): number plates, the primary action, the selected city plate, map box markers, the cloak cell outline, and focus (brass-300 outline). Brass-200 is the lit highlight for an active row title and register action codes; brass-700 and brass-900 are brass set on steel panels (plate ink, links).

### Tertiary
- **Oxide Red** (oxide-500; oxide-300 for text on enamel; oxide-700 for the destructive hover fill; oxide-rule for its 1px borders): revoked or expired keys, register rows that record destructive actions, error toasts and form errors, the danger zone and danger buttons. Nothing else.

### Neutral
- **Vault Enamel** (vault-950 to vault-600): vault-950 is the header, toasts, map banner and focused inputs; vault-900 the tab strip, inputs, lens and key tags; vault-800 the rail and dialog; vault-700 hover; vault-650 row rules; vault-600 the current row.
- **Enamel Rule** (vault-rule): every 1px border on the green.
- **Enamel Text** (on-vault, on-vault-2, on-vault-3): primary, secondary and tertiary text on green. On-vault is also the selected-segment and selected-chip fill.
- **Brushed Steel** (steel-25 to steel-700): the map frame (steel-200), map background (steel-100), light panels (steel-50), the note slip (steel-25), panel rules and steel labels.
- **Ledger Ink** (ink, ink-2): text on steel panels.

### Named Rules
**The Brass Reservation Rule.** Brass is reserved for number plates, the primary action, the city plates and focus (plus the map objects that are plates: box markers and the cloak cell). Selected segments and selected chips use the enamel state: on-vault fill with vault-900 ink, never brass.

**The Oxide Means Loss Rule.** Oxide red marks revoked or expired states and destructive actions only. It is never decoration and never a generic accent.

**The Grey Hall Rule.** Map tiles are desaturated (grayscale 0.88) so brass boxes and green public places carry the colour on the map.

## Typography

**Display / UI Font:** Archivo variable, weight and width axes (with Segoe UI, system-ui)
**Mono Font:** JetBrains Mono (with ui-monospace, Cascadia Mono, Consolas)

**Character:** Archivo does double duty: at normal width it is a plain, sturdy grotesque for titles and text; pulled to 68 to 80% width in heavy uppercase with wide tracking it becomes the engraved plate face. JetBrains Mono sets anything that is a measurement or a record: coordinates, expiry stamps, capacity counts, register action codes.

### Hierarchy
- **Headline** (720, 24px, 1.12): the box label on an opened box.
- **Title** (700, 22px, 1.15, balanced wrap): view titles in the rail and share card titles; 18px for place cards and dialog titles.
- **Body** (400, 15px root, 1.45): running text; rail secondary text sits at 13 to 14px. Auth intro copy caps at 46ch.
- **Row title** (600, 14.5px): list rows and key tags, single line with ellipsis.
- **Label** (700 to 720, 11 to 12.5px, 0.12 to 0.14em, uppercase, 74 to 78% width): section titles, field labels, tabs, ledger headers, key-value terms.
- **Plate** (740, 12px, 0.13em, uppercase, 70% width): engraved plates; 15px at 0.16em for the large box number; 10.5px inside rows.
- **Mono** (14.5px for coordinates; 11.5 to 12px for stamps, counts and register cells; -0.01em tracking).

### Named Rules
**The Tabular Everywhere Rule.** The root sets tabular numerals; every figure in the product lines up.

**The Engraving Rule.** Condensed caps come from Archivo's width axis, not a second family, and appear only on plates, tabs and labels that name a section or field.

## Layout

A three-row body grid: optional lab banner, a 56px header, then the hall. The hall is the map at the left (minmax(0, 1fr)) and a 400px drawer rail at the right (360px under 1100px, where city names collapse to their three-letter codes). The rail holds a 48px tab strip and a scrolling body padded 20px 18px 28px.

Spacing runs on a small, tight rhythm: 6 and 8px inside controls and chip rows, 10 to 14px between fields and rows, 18px around cards, 26px above section titles, 36px before the danger zone. Lists are ruled, not carded: a top rule, then 48px-minimum rows on 1px rules.

Under 760px the page scrolls: the header wraps with the city plates on their own full-width row, the map takes the top 52dvh, the rail becomes a sheet below with sticky tabs, and the ledger header sticks under them.

**The Stacked Plates Rule.** Box plates that collide on the map stack upward in 24px steps (up to six steps), so no box is ever hidden under another.

## Elevation & Depth

There are no soft shadows. Floating layers (map banner, toasts, dialog, box markers, Leaflet controls and tooltips) are separated by edge and colour: a vault-950 or steel fill against the layer beneath, and a 1px rule in enamel, brass or oxide. Leaflet's own shadows are explicitly removed. The dialog backdrop is a 62% vault-950 wash.

**The Edge Not Shadow Rule.** If a layer needs to lift, give it a darker enamel fill and a 1px rule; an active box marker takes a 2px brass outline at 2px offset.

## Shapes

Corners are 2px at most: 2px for controls, panels, inputs, tooltips and the dialog; 1px for plates and box markers. Circles are reserved for literal objects: the punched hole on a key tag, the true-spot dot, public place dots, the spinner. Plates carry an inset second rule 2px inside the outer border (a 1px line at low alpha of the plate's own colour), which is what makes them read as engraved. Dashed lines mean "boundary that is not a wall": the cloak cell, the empty photo slot, empty states, and the danger-zone divider.

## Components

### Buttons
Short, firm and metallic; they press rather than glow.
- **Shape:** 2px corners, 38px tall (32px small), 620 weight, 14px.
- **Primary (brass):** brass-400 fill, vault-950 ink, brass-300 edge; hover brightens to brass-300. One per view.
- **Ghost:** transparent with an enamel-rule edge; hover fills vault-700. On steel panels it takes ink text and a steel-300 edge.
- **Quiet:** no edge, on-vault-2 text, for low-stakes actions.
- **Danger:** oxide-300 text on an oxide-rule edge; hover fills oxide-700 with white text.
- **Press / Focus:** every button presses 1px down on active; focus is the global 2px brass-300 outline at 2px offset. Disabled is 45% opacity.

### Plates
The engraved object, and the system's unit of identity.
- **Default:** brass-300 text, brass-500 edge, inset rule. **Solid:** brass-400 fill for box numbers (BOX 005). **Steel:** on-vault-2 text on an enamel rule, for neutral facts such as a private visibility or a hall row's category. **Oxide:** for revoked and expired.
- On steel panels a plate takes brass-700 ink.
- Hall rows carry a condensed-caps category plate under the row title.

### City Plates and Segmented Controls
- **City plates:** a joined strip of three-letter code (condensed caps) plus city name in the header; the selected city is solid brass.
- **Segmented controls** (visibility, precision, lens view): joined 36px cells on enamel rules; the selected cell is the enamel state (on-vault fill, vault-900 ink).

### Chips
- **Style:** 30px, transparent, enamel-rule edge, 12.5px, a mono count at 75% opacity.
- **State:** selected chips use the enamel state (on-vault fill, vault-900 ink, on-vault edge).

### Cards / Containers
- **Light panels:** steel-50 fill, steel-200 edge, 2px corners, 16 to 18px padding, ink text; they hold place cards and the public share card. A key-value list uses condensed-caps steel-700 terms.
- **Note slip:** steel-25 paper inside the enamel, 22px line height, pre-wrapped.
- **Coordinates bar:** vault-950 strip with mono coordinates and a brass "only you" lock tag.
- Shadow strategy: none (see Elevation & Depth).

### Inputs / Fields
- **Style:** 40px, vault-900 fill, enamel-rule edge, 2px corners, condensed-caps label above.
- **Focus:** edge turns brass-300 and the fill deepens to vault-950; the caret is brass-500.
- **Error:** an oxide-tinted block with an oxide-rule edge and light-red text above the form.

### Navigation
- **Rail tabs:** four equal tabs, 48px, condensed caps at 12.5px with an icon from the authored sprite; on-vault-3 at rest, on-vault on hover, current page in brass-300 with a 2px brass underline.
- **Rows:** hover vault-700; the current row fills vault-600 and its title turns brass-200.
- On mobile the tab strip sticks to the top of the sheet.

### Key Tags
A key tag has a punched hole (a 12px brass-ringed circle), a title, a meta line and a mono expiry stamp. Expiring stamps are brass-300; revoked or expired tags drop to 62% opacity with an oxide hole and an oxide stamp. A newly issued link is shown once in a brass-edged box tinted with 12% brass.

### Access Register
A ruled ledger: condensed-caps sticky headers on a vault-rule underline, 12.5px cells on vault-650 rules, mono timestamps, and action codes in brass-200 mono; destructive actions turn oxide-300.

### Map Objects
- **Box markers:** 26 by 22px brass plates with a 1.5px vault-950 edge and a mono box number; active adds a brass-500 outline; cloaked (shared view) inverts to vault-800 with brass-200 numerals.
- **Public places:** 5px enamel-green dots with a white edge; the active place grows to a brass dot.
- **Map banner:** vault-950 bar with a brass-500 edge, centred 14px from the top, for picking mode.

### Cloak Lens (signature)
In box detail, a vault-900 panel holds two segmented controls (Owner view / Shared view, and 100 m / 500 m / 1 km). In Shared view the map draws the server-computed cell as a dashed brass square (brass-500, 2px, 6-5 dash, 16% brass-300 fill), and the box plate slides from the true spot to the cell centre over 600ms with an exponential ease-out (1 - 2^(-10t)). The true spot stays as a small white dot ringed in brass-700, labelled on a steel tooltip: "True spot · only you". Under reduced motion the plate jumps and the map does not animate.

## Do's and Don'ts

### Do:
- **Do** keep brass on plates, the primary action, the selected city plate, map plates, the cloak cell and focus only.
- **Do** show selected segments and chips in the enamel state (on-vault fill, vault-900 ink).
- **Do** separate floating layers with a darker fill and a 1px rule.
- **Do** set every coordinate, stamp, count and register code in JetBrains Mono with tabular figures.
- **Do** build engraved labels from Archivo's width axis (68 to 80%) in uppercase with 0.12 to 0.16em tracking.
- **Do** run motion on one axis with the 0.16, 1, 0.3, 1 ease-out (140ms for state, 260ms for drawers and toasts, 600ms for the cloak tween), and honour reduced motion.
- **Do** stack colliding box plates upward in 24px steps.
- **Do** use icons from the authored sprite (frontend/icons.svg) and self-hosted fonts only; write API data with textContent only.

### Don't:
- **Don't** use soft shadows on anything, including map controls and tooltips.
- **Don't** use brass for selected states, generic highlights or decoration.
- **Don't** use oxide red for anything other than revoked or expired states, destructive actions and errors.
- **Don't** round corners past 2px or use pill shapes; circles are only for literal holes, dots and the spinner.
- **Don't** build the white-sidebar-with-blue-accent map layout or a dark neon security dashboard.
- **Don't** load fonts, scripts, styles or images from third-party origins (OSM tiles excepted), and don't use inline style or script.
