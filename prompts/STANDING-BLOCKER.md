## One thing none of this touches

Every composition still refuses, correctly, because `licence_channel` has all channels
`allowed = false` with `cleared_by`, `cleared_at` and `evidence_uri` NULL, and
`ca_san_jose.city_limits` carries `licence: unknown` — annotated **"LD-1 — BLOCKS
EVERYTHING"** in the spec.

P1, P2 and P3 all make the machine correct. None of them make it able to emit a Property
File. That gate is a signature, not a commit.
