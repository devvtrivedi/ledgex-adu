## One thing none of this touches

Every composition still refuses, correctly, because `licence_channel` has all channels
`allowed = false` with `cleared_by`, `cleared_at` and `evidence_uri` NULL, and
`ca_san_jose.city_limits` carries `licence: unknown` — annotated **"LD-1 — BLOCKS
EVERYTHING"** in the spec, which is the INTENDED posture, not a description of what the
machine currently enforces. See the correction below before reading "LD-1 — BLOCKS
EVERYTHING" as a live control.

P1, P2 and P3 all make the machine correct. None of them make it able to emit a Property
File. That gate is a signature, not a commit.

---

**CORRECTION (P52 Phase 1, commit `bc4ea9e`; `prompts/P52-rights-vs-diligence.md` §5)** —
the LD-1 / `city_limits` sentence above describes intent recorded in
`jurisdictions/ca_san_jose/sources.yaml`, not an enforced control. Confirmed directly,
twice (against the real local database and an independent from-scratch schema+seed
build): `db/seeds/day4_sources.sql` seeds zero `ca_san_jose.city_limits` source rows and
zero `jurisdiction.incorporated` field_definition or fact rows, and
`scripts/compose_property_file.py`'s own header says outright that nothing ingested plays
that role. `_compose()` reads `parcel.jurisdiction_id` straight off the parcel row — never
via a spatial lookup against a city-limits-shaped fact — so there is no code path in this
composer that ever touches, requires, or gates on a `jurisdiction.incorporated` fact. If
`cc0`/`cc_by_4_0`'s channels were cleared today, composition would proceed straight
through L0 with the LD-1 gate never evaluated. **The only thing actually blocking every
composition right now is `licence_channel.allowed = false` on `cc0`/`cc_by_4_0` (0030).**
Giving LD-1 a real runtime representation (a `city_limits` source row, a
`jurisdiction.incorporated` fact the composer actually touches, and a test that goes red
if that touch is removed) is PASS 1 of the P52 roadmap and has not landed yet — do not
treat LD-1 as a live control until it has.
