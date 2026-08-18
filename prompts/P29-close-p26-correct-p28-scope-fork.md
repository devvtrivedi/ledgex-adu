## P29 — Close P26 properly, correct P28's close-out, then decide the fork

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Report before writing on any
design decision; this package does not start building the fork it scopes.

Steps 1 and 2 (P26's bookkeeping, P28's over-claim) are recorded in their own packages'
files — `prompts/P26-jurisdictions-pack-format.md` section 5, `prompts/README.md`'s
findings #31/#32 and package-table row, `prompts/P28-liveness.md` section 6 — not
duplicated here. This doc covers step 3 (scoping the fork) and step 4 (close-out).

---

### 3. Scoping the fork

#### (a) `commerce/` + §13 — cited, not re-derived, plus the one thing P28 didn't test

P28's argument stands and is not relitigated here: building any of `make test`'s six named
areas means writing `commerce/` schema and code against zero real rows, zero real review
evidence, and zero real entitlement state. §13 itself is more thoroughly drafted than P28's
framing implied — §13.1–13.3 already carry complete, ready-to-transcribe DDL
(`commerce.customer`, `commerce.plan_version`, `commerce.subscription`,
`commerce.billing_event`, `commerce.access_entitlement`), the same "spec already drafted
it, transcribe don't design" shape P26 used for `sources.yaml`/`licences.yaml`. That lowers
the *schema-design* cost of `commerce/` but does not touch P28's actual blocker: zero real
customers, zero real subscriptions, zero real payment provider integration exist, and none
can exist until `STANDING-BLOCKER.md`'s signature clears the product to take a paying
customer at all.

**The one thing P28 did not test, checked directly**: is *"a refused file creates no
charge"* (I16) assertable today, with no payment integration? **No — not meaningfully.**
There is no `commerce.billing_event` table, no `commerce.subscription` table — nothing
capable of creating a charge exists in this schema at all. Asserting "no charge occurred"
today would mean querying a table that doesn't exist, or asserting a vacuous truth (nothing
CAN charge, so of course nothing did) — exactly the "coincidence that can never prove the
fix" shape README finding #22 already named, and the same reasoning P25's own `core/calc.py`
docstring gives for why `geometry_tier_enabled=True` needs a real stub rather than trusting
"both false today." I16 needs `commerce.billing_event`/`commerce.subscription` (§13.1/13.3)
to exist, at minimum, before there is anything to assert against.

One honest nuance worth naming, not resolving here: I16 is a system-correctness invariant
("billing never fires on this outcome"), not a rights-clearance claim — a MINIMAL
`commerce/` slice tested against synthetic `test-*`-namespaced fixtures (the same legitimate
pattern `db/tests/invariants.sql` already uses for I18's 35 synthetic `rule` rows) would not
require fabricating a real customer or a real rights clearance the way composing a real
Property File would. Whether that minimal slice is worth building on its own, ahead of the
rest of `commerce/`, is a real, unscoped design question this package does not answer —
noted, not decided, matching how P26 left `field_map.yaml` named but undesigned rather than
guessing at its shape.

---

#### (b) A rule pack + L5 — scoped for the first time

**What's actually blocking it, checked against the schema, not assumed**: nothing that
`STANDING-BLOCKER.md` gates. `db/migrations/0009_rules.sql`'s `rule` table has no
`licence_id` column and no FK to `licence` at all — confirmed by reading the migration
directly, not inferred. Its own CHECK constraint is satisfied by
`review_mode = 'solo_founder_attestation'` with `reviewed_by = authored_by` and a non-null
`attestation_uri` — the header calls this the Phase 1 path, and §3.9 states the identical
contract verbatim: *"Phase 1 may use a controlled solo-founder attestation only when the
same identity authors and reviews and an immutable evidence URI is stored."* This is the
founder's own attestation of a rule's citation and interpretation — a different axis
entirely from `licence_channel`'s rights clearance for *data sources*, which is what
`STANDING-BLOCKER.md` actually gates (§1.1's own internal-fact rights argument is scoped to
facts derived from *sourced data*, never to rule text cited from public jurisdiction
ordinances). Checked live, not assumed: `rule` already has 35 real rows in
`ledgex_schema_check` today — every one of them a `test-*`/`test.*` synthetic fixture from
`db/tests/invariants.sql`'s own I18 tests, confirming `0013`'s `rule_no_update`/
`rule_no_delete` triggers fire and are exercised mechanically, but never yet against a real,
production rule row representing actual San José ordinance content.

**What real content would seed it**: San José's own published Municipal Code — e.g., an ADU
setback, height or parking-standard section, cited by its real, publicly available
`source_text_uri` (the city's own municode.com or equivalent published ordinance page),
`citation` naming the exact code section, `params` carrying the cited numeric/enum values,
`effective_from` the ordinance's own stated effective date. One real rule is enough to prove
the shape — this does not need the full ADU ordinance transcribed, the same "one real pack,
not the whole catalogue" discipline P26 already used for `jurisdictions/ca_san_jose`.

**What `attestation_uri` would have to point at — a real, unmade decision, not glossed
over**: nothing in this codebase has ever created an "attestation" artifact before. Two
honest candidates, neither built: (i) an object-store URI, matching `snapshot`'s own
content-addressed pattern — a founder-authored, dated document stating what was reviewed
and against what citation; (ii) a commit-pinned URL into this git repository itself (e.g., a
markdown file, committed, referenced by its raw GitHub URL at a specific SHA) — immutable by
construction via git history, no new infrastructure. (ii) is the lower-cost option given
this codebase's own established preference for not adding infrastructure ahead of need, but
this is a real design decision this scoping surfaces and does not resolve — the same
"named, not designed" status `field_map.yaml` and `jurisdictions/ca_san_jose/conclusions.yaml`
already carry.

**What L5 must actually do**: given `jurisdiction_id`, an `as_of` date and a required
`rule_key`, select the effective rule — `effective_from <= as_of AND (effective_to IS NULL
OR effective_to > as_of)`, highest `version` — and refuse `RULE_UNAVAILABLE` (already a real
member of `core/model.REFUSAL_CODES`, stage `L5` per §9, never yet raised by any code) when
none is effective. This can be built refuse-first, the identical shape P25 used for
`core/calc.py`'s L7 gate: prove the refusal path for real before anything computes with a
matched rule's `params`.

**The real, honest gap this scoping surfaces, checked not assumed**: nothing in this
codebase today declares *which* `rule_key` a given conclusion depends on.
`jurisdictions/ca_san_jose/conclusions.yaml` is named in §7.4's own text ("Migration 0003a
and jurisdictions/ca_san_jose/conclusions.yaml are part of the build contract... Required
inputs are declared before code runs") but does not exist — grepped, not assumed:
`compose_property_file.py` has zero references to `rule_key` or `conclusions.yaml`
anywhere. Without that declaration, L5 has no principled way to know which rule to look up
for a given composition — it would need either a hardcoded, narrowly-scoped rule_key (P25-
style: one real thing, not the general mechanism) or a minimal stand-in for
`conclusions.yaml` scoped to exactly one conclusion, the same "format doesn't exist yet, one
real pack only" boundary P26 already drew for `field_map.yaml`. Either is buildable; neither
is free, and this package does not choose between them.

**Be honest about the limit, as asked**: the rights gate (`RIGHTS_BLOCKED`, L8) still
refuses every real composition regardless of what L5 does — `licence_channel` has every
channel `allowed = false`, checked fresh in P28's own report and unchanged since. No rule
*application* reaches a composed file whether or not L5 exists. **Recording a real
`ruleset_version` on a refused file is only half of I11.** I11's own text is "every rule
*application* records the exact ruleset_version and a human-readable citation" — a refused
file never applies a rule to compute anything; L5, on the refused path, only ever *selects*
(or fails to find) a rule, never applies one. Replacing today's placeholder string with a
real selected-rule stamp exercises the *recording* half genuinely, for the first time, and
gives `0013`'s triggers their first real row to protect — but the *application* half of I11
stays exactly as unexercised as it is today, because nothing in this codebase computes a
rule-dependent conclusion yet (`core/calc.py`'s own docstring names this as a separate,
future package: "the first derived fact this codebase ever writes would exercise
I5/0029's... trigger... Building that safely is its own package"). This option closes one
real, named gap — it does not, and should not be described as if it, unblock composition.

---

#### (c) Stop and wait — argued honestly, not by default

The strongest case for (c): after P26/P27/P28, the marginal value of each additional
infrastructure-hardening package is genuinely lower than it was — three consecutive
packages have now been spent making CI, timeouts and gate-coverage honest rather than
moving the product itself. There is a real risk that continuing to find and close small,
adjacent gaps becomes its own kind of activity that feels like progress without being the
thing actually gated: `STANDING-BLOCKER.md`'s signature. If the founder's own next move is
better spent pursuing that signature than reviewing another engineering package, no amount
of buildable-today scope changes that calculus — but that is a real-world resourcing
question this repository's own evidence cannot answer, and is not decided here.

Two secondary concerns, both real, both addressed rather than dismissed: building L5 could
read, to a future skim, as more progress toward a composed file than it actually is — fully
mitigated by reporting the limit explicitly, as this section does, not by declining to
build. And L5 is new surface area (a query function, a seeded rule row, an attestation
mechanism) built to serve a column that currently has exactly one real consumer
(`property_file.ruleset_version` on the refused path) — a legitimate "is this forced by
need or anticipated" question this codebase's own conventions take seriously elsewhere. Set
against that: I11 is already *partially* enforced (`rule.citation NOT NULL` plus 0013's
triggers, exercised only by synthetic fixtures) — this closes the specific, already-named
gap (a literal placeholder string committed into every refused file's own stored data, not
merely an untested code path) rather than inventing a new requirement.

**Per the instruction: since (b) is genuinely startable, (c) does not win on "everything is
blocked."** Its remaining arguments are about founder time allocation (outside this
repository's evidence) and scope discipline (addressed by (b)'s own narrow, P25-shaped
scoping above, not by refusing to scope it at all).

---

### Recommendation

**(b), narrowly scoped exactly as above — one real rule, refuse-first, both paths proven —
not started here.** It is the only option confirmed startable today without fabricating
anything STANDING-BLOCKER.md would need to clear, it replaces an actual placeholder lie
sitting in production data right now, and it follows a scoping pattern (P25's) already
proven to work in this codebase. The honest limits are stated above, not hidden: it does
not unblock composition, it only half-exercises I11, and two real sub-decisions
(`attestation_uri`'s target, a minimal `conclusions.yaml`-equivalent) remain genuinely
undesigned and would need their own "report before writing" pass before any of this is
built.

---

### 4. Close-out

No schema change expected — `make migrate-verify` and a clean `make schema-dump`, both
against `ledgex_schema_check`, confirm this. All four `db.yml`/`docs.yml` jobs green on the
close-out commit. P29 row added to `prompts/README.md`, this package's own close-out
commit, since that is the step P26 skipped.
