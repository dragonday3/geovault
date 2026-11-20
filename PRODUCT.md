# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: technical reviewers.** Security and geospatial hiring panels, interviewers and
recruiters evaluating the developer's work. They click through a live local demo or study
screenshots, often in a short session. They want to judge two things quickly: does this feel
like a real, trustworthy product, and are the security and privacy controls real and visible?

**Secondary (the in-product persona): residents of Melbourne, Bengaluru and Ahmedabad.** They
explore public places and keep a private list of their own places: home, work, a favourite
chai stall. They attach notes and photos and share selected places with friends at a chosen
precision.

**Administrators** manage roles and inspect the audit trail.

## Product Purpose

GeoVault lets people save private locations and share them safely. The exact coordinates
never leave the owner. Shared and public views are snapped to a 100 m, 500 m or 1 km grid.
Photos are rebuilt so GPS metadata is gone, and every sensitive action is audited.

The product is also a security portfolio. A deliberately vulnerable **lab mode** (localhost
only) is attacked and then fixed. Success means a reviewer understands within minutes what is
protected and how, and the protections hold up under inspection.

## Positioning

A geospatial app where the privacy mechanism is the product:

- per-city metric-projection cloaking computed inside the database;
- owner-only exact locations, so other users get the same 404 as for a missing record;
- metadata-free photos;
- refresh-token rotation with reuse detection;
- secret-free audit logs.

Each one is backed by automated tests and mutation-verified.

## Operating Context

- Runs locally via Docker Compose on 127.0.0.1. A secure-mode AWS deployment (ap-south-1) is planned.
- Reviewers use desktop browsers mostly, with mobile screenshots also expected.
- Public open data: City of Melbourne (CC BY 4.0) and OpenStreetMap (ODbL) for Bengaluru and Ahmedabad.
- Indian maps must never render national or international borders. Every region is clamped to city zoom.

## Capabilities and Constraints

- **Regions:** Melbourne (AU), Bengaluru (IN), Ahmedabad (IN).
- **Public places explorer:** search, category filters, nearby search.
- **Accounts:** registration and login.
- **Favourites:** exact location plus a private note, visibility (private / shared / public), share precision.
- **Sharing:** with a registered user, or via an expiring link.
- **Photos:** one per favourite.
- **Settings:** shared-with-me, public share-link view, profile, data export, account deletion.
- **Admin:** users, roles, audit log.
- **Stack:** vanilla HTML/CSS/JS with vendored Leaflet 1.9.4, served same-origin by FastAPI.
- **Strict CSP:** no inline scripts or styles, no third-party origins except OSM tiles. Fonts and assets must be self-hosted.
- **DOM writes** of API data use `textContent` only.
- **Auth model:** the access token is held in memory only (never localStorage); the refresh token lives in an HttpOnly cookie, and refresh and logout send an `X-CSRF-Token` header.
- **Lab mode** must show a persistent "LAB MODE - INTENTIONALLY VULNERABLE" banner (milestone 11).

## Brand Commitments

The name **GeoVault** is binding. There is no existing logo, palette or typeface. Fonts must be
open-licence (OFL), vendored locally, and committed with their licence files.

## Evidence on Hand

- Real place data: 925 Melbourne and 1,995 Bengaluru places, with Ahmedabad being added.
- Test suite: 256 tests; documentation is in `docs/`.
- There are no testimonials, users, metrics or press. Never fabricate them.

## Product Principles

1. **Show the protection.** Where privacy is applied (cloaked precision, EXIF stripped,
   share expiry), make it legible in the UI rather than hidden.
2. **The owner sees truth, everyone else sees less.** Every view makes clear which kind
   of view it is.
3. **No dark corners.** Every action has a clear result, an error state and an undo or confirm
   where it is destructive.
4. **Real data, honest gaps.** Empty states and limits are stated plainly, never padded.

## Accessibility & Inclusion

WCAG 2.2 AA target: keyboard-operable map controls and dialogs, visible focus, sufficient
contrast, and reduced-motion respected.
