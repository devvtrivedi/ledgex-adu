## P30 — Prove make conformance red on the real runner, then report (b)'s two open decisions

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Steps 1–2 build; step 3
reports only.

Finding #33 (`make conformance` CI-wired but never proven red) is recorded in
`prompts/README.md`, cross-linked from `prompts/P26-jurisdictions-pack-format.md` section
4. Not duplicated here.

---

### 2. Closing #33 — prediction, then the real run

**The break, chosen to test the check's own real job, not a schema/import error**: change
`jurisdictions/ca_san_jose/sources.yaml`'s `ca_san_jose.zoning_districts` entry's
`licence:` from `cc_by_4_0` to `cc0` — both real, valid licence ids (both exist in
`licences.yaml` and the live `licence` table), so this is a pure pack-vs-database
disagreement, not a format error `check_schema_validity` would also catch.

**Exact assertion predicted to fire**: `scripts/check_conformance.py:259-261` —
`check(f"{sid!r}'s pack licence matches the live source row's own licence_id", s["licence"]
== db_licence_id, f"pack says {s['licence']!r}, database says {db_licence_id!r}")`.

**Exact error text predicted**: `[FAIL] 'ca_san_jose.zoning_districts''s pack licence
matches the live source row's own licence_id -- pack says 'cc0', database says
'cc_by_4_0'`.

**Predicted to stay green, and why**: the immediately preceding check on the same source
(`'ca_san_jose.zoning_districts''s licence 'cc0' exists in the live licence table`) — `cc0`
is a real row, so existence alone still passes; only the *match* fails. Both other active
sources (`parcels`, `building_permits_active`) untouched, all their checks stay green. JSON
Schema validation for both pack files stays green — `licence` is typed `string` with no
enum constraint, and `cc0` is validly declared in the pack's own `licences.yaml`.

**Ordering-trap check (finding #32), before pushing**: `check_golden.py`'s own
`seed_reference_rows()` — read directly, not assumed — only seeds `ip.SOURCE_ID`
(`ca_san_jose.parcels`); it never touches `ca_san_jose.zoning_districts` at all. This break
targets `zoning_districts` exclusively, so `make golden` running first in `db.yml`'s
`schema` job cannot confound this result the way it could have for a `parcels`-scoped
break.

**Predicted unaffected, to be confirmed from the run, not by reasoning alone**: `make
schema`, `make migrate-verify`, `make db-test`, `scripts/test_snapshot_race_invariant.py`,
`make golden`, `scripts/test_compose_geometry_tier_used.py`, `make test`, `make
schema-dump` — none of these read `jurisdictions/ca_san_jose/sources.yaml` at all; only
`make conformance` does.

**Verified locally first**, fresh migrations-only scratch database: every prediction above
held exactly — the one named assertion failed with the exact predicted text, every other
check (including both other sources' full four-check set) passed, exit 1.

**On the real runner**: pushed as a real commit, confirmed red with the run ID, reverted in
the immediately following commit, confirmed green with the second run ID — see the commit
history and `prompts/README.md` finding #33 for both. **Prediction held exactly, both
locally and on the real runner** — recorded here, not asserted without the run evidence.

---

### 3. Report only — (b)'s two undesigned sub-decisions

Held in full below. Nothing in this section was built — no `core/rules.py`, no seeded
`rule` row, no `conclusions.yaml`.

#### Facts (b) rests on, re-confirmed against the files directly, not from P29's summary

- `db/migrations/0009_rules.sql`'s `rule` table: no `licence_id` column, no FK to
  `licence` — read directly, unchanged since P29.
- `scripts/compose_property_file.py:284` (offset may have shifted by a line or two since
  P29; matched by content, not line number) still persists the literal string
  `"unevaluated -- L5 Rules not yet built"` into `property_file.ruleset_version` on every
  refused file — read directly, unchanged.

Neither fact has changed. (b)'s premise stands.

#### (i) What `attestation_uri` actually points at

`db/migrations/0009_rules.sql`'s own CHECK requires `attestation_uri IS NOT NULL AND
length(trim(attestation_uri)) > 0` under `solo_founder_attestation`; §3.9 calls it an
*"immutable evidence URI."* Nothing in this repo defines what "immutable" means for this
specific artifact — checked directly: no existing code reads, writes or validates
`attestation_uri` beyond the CHECK constraint's non-blank test. Four real candidates,
weighed against "immutable" and I17 ("read verbatim from the filesystem"):

**A git object or signed tag** (e.g. `git rev-parse HEAD` of a commit containing the
attestation text, or an annotated/signed tag pinned to it). *Cost*: none — no new
infrastructure, this repository already is the git object store. *What breaks if the
target moves*: nothing can move a commit's own content without changing its SHA — the URI
and the content are the same fact, by construction. *What a 2030 reader needs*: `git show
<sha>:<path>` against this repo's own history (or a fork/mirror of it) — works exactly as
long as this repository's git history exists, `.git/objects` intact. Direct match for I17:
verbatim from the filesystem is what a git object literally is.

**A file in the repo, referenced by a plain (non-pinned) path**. *Cost*: none to create.
*What breaks if the target moves*: everything — an un-pinned path is mutable by definition;
a later commit could edit the same file's content out from under the URI with no signal
that the attestation changed. This fails "immutable" outright unless pinned to a commit
SHA, at which point it collapses into the git-object candidate above with extra
indirection, not a genuinely different option.

**An object in the WORM bucket** (`ledgex-snapshots-locked`, `COMPLIANCE` mode, ~100yr
retention, confirmed live — P19/P20). *Cost*: real — this bucket already required its own
remediation once (finding #28, P20) because fixture traffic was writing into it by
accident; using it for attestations reopens exactly the surface that finding closed,
deliberately this time rather than by accident, so it would need its own explicit,
narrowly-scoped write path, not a shared default. *Undeletability, asked directly — feature
or hazard here*: **a hazard for this specific use, not a feature.** P20's own fix moved
acceptance traffic *off* this bucket precisely because ~100-year COMPLIANCE-mode retention
on every object written — test fixture or not — is unrecoverable by any principal,
including the bucket's own owner. An attestation URI is meant to be a durable *pointer to a
review decision*, not a claim that the decision itself can never be corrected or retired;
`0013`'s own trigger design already handles correction the honest way (a new rule
version, `effective_to` retiring the old one) — pairing that retirement model with an
attestation artifact that cannot ever be superseded, deleted or even reasoned about as
historical-and-superseded is a mismatch, not a strength. *What a 2030 reader needs*: AWS/S3
credentials with read access to a bucket this project may or may not still be paying for a
decade on — a real, ongoing operational dependency the git-object candidate does not have.

**Something else — a dated, signed document (e.g. a PGP/age-signed text file) stored
alongside the rule pack, referenced the same commit-pinned way as the plain-file
candidate.** *Cost*: real — requires the founder to hold and use a signing key, and this
repository has no existing precedent for one (no `.asc`/signature files anywhere today).
*What breaks if the target moves*: nothing, once commit-pinned, for the same reason as the
git-object candidate — but the signature adds a SECOND immutability mechanism on top of
git's own, which is redundant unless the threat model specifically includes "this git
repository's own history could be rewritten or is not trusted as evidence on its own,"
which nothing else in this project currently assumes (I17 already treats the filesystem —
i.e., this repo — as authoritative). *What a 2030 reader needs*: the same git access as
the git-object candidate, plus a public key and working PGP/age tooling — strictly more
than the git-object candidate for no capability this project's own trust model requires.

**Recommendation, for the founder to decide, not decided here**: the git-object/commit-pinned
candidate. It is the only option that is genuinely immutable by construction (not by
policy, not by a third party's retention setting), costs nothing new to build, matches I17's
own "verbatim from the filesystem" standard exactly, and avoids reopening the WORM-bucket
surface P20 deliberately closed. The concrete shape this would take: a markdown file
(e.g. `rules/attestations/<rule_id>.md`) stating what was reviewed, against which citation,
by whom, and when; `attestation_uri` stores this repository's own raw-content URL pinned to
the commit SHA that introduced it (`https://github.com/<org>/<repo>/blob/<sha>/rules/
attestations/<rule_id>.md`) or, if independence from GitHub specifically is wanted, the bare
`<sha>:<path>` form a `git show` can resolve without any hosting provider at all. Either
form is a decision, not an implementation detail — left to the founder.

#### (ii) The `conclusions.yaml` gap — two shapes, scoped concretely enough to choose between

§7.4 names `jurisdictions/ca_san_jose/conclusions.yaml` as part of the build contract; it
does not exist. Confirmed again, not assumed: `grep -rn "rule_key\|conclusions.yaml"
scripts/compose_property_file.py` returns nothing — zero references, unchanged since P29.

**Shape 1 — a hardcoded, narrowly-scoped constant (P25-style: one real thing).**
`core/calc.py`'s own `GEOMETRY_DEPENDENT_CONCLUSIONS` tuple is the direct precedent: a
literal Python constant naming exactly the conclusions this codebase currently knows about,
extended only when a real second one is needed. The L5-equivalent would be a single module-
level mapping in whichever module owns rule selection —
`CONCLUSION_RULE_KEYS = {"placement": "ca_san_jose.adu_setback_v1"}` (illustrative name;
the real key would match whatever rule is actually seeded) — literally one dict entry, no
file, no schema, no loader. **L5's signature under this shape**:
`select_effective_rule(cur, jurisdiction_id, rule_key, as_of) -> Result[Rule]`, called
once per conclusion with a hardcoded `rule_key` looked up from the constant above — the
caller (`compose_property_file.py`) passes a literal string, the same way it already passes
`geometry_tier_enabled` as a bare parameter to `core/calc.py` today, no jurisdiction-name
leakage into `core/` (I1 unaffected, matching that precedent exactly). **What forces a
rewrite for a second jurisdiction**: the constant itself — a second jurisdiction's own
`rule_key` for the same conclusion (`"other_city.adu_setback_v1"`, a different id, likely a
different rule shape entirely) means either branching this same dict on
`jurisdiction_id` too (`CONCLUSION_RULE_KEYS[jurisdiction_id][conclusion]`, a real but small
shape change) or accepting that the constant was only ever jurisdiction-scoped by
convenience and needs restructuring. Small rewrite, contained to one file.

**Shape 2 — a minimal `conclusions.yaml`, scoped to exactly one conclusion (P26's own
`field_map.yaml` boundary applied here).** A real YAML file,
`jurisdictions/ca_san_jose/conclusions.yaml`, containing exactly one entry:
```yaml
jurisdiction: ca_san_jose
conclusions:
  - conclusion: placement
    required_rule_keys: [ca_san_jose.adu_setback_v1]
```
— no schema beyond what one entry needs, the same "one real pack, not the whole
catalogue" restraint P26 used for `sources.yaml`/`licences.yaml`, and the same "format
named in the spec but never drafted" status `field_map.yaml` still carries (§7.4 names this
file; nothing anywhere drafts its shape, unlike §7.1/§7.2's fully-drafted source/licence
pack content — this file's format would be invented here, for the first time, not
transcribed). **L5's signature under this shape**:
`select_effective_rules(cur, jurisdiction_id, conclusion, as_of) -> Result[list[Rule]]` —
takes a `conclusion` name, not a bare `rule_key`; internally loads (or is handed) the
parsed `conclusions.yaml`, looks up `required_rule_keys` for that conclusion, resolves each
against the live `rule` table. This needs its own loader (a `PACK_PATH`/`load_yaml` pair,
the same small pattern `check_conformance.py` already uses) and, if it is to be trustworthy
rather than merely present, its own `make conformance`-style drift check confirming the
declared `required_rule_keys` actually exist in `rule` — real, additional surface area
Shape 1 does not need at all. **What forces a rewrite for a second jurisdiction**: nothing
in the *shape* — a second jurisdiction adds its own `jurisdictions/<other>/conclusions.yaml`
file, structurally identical, no code change to the loader or to L5's own signature. This is
the one genuine advantage Shape 2 has over Shape 1: the multi-jurisdiction case is additive,
not a rewrite.

**Recommendation**: **Shape 1**, for now, narrowly scoped to the one real conclusion this
codebase already names (`placement`) and the one real rule this package would seed —
matching P25's own precedent of proving the smallest real shape before generalizing, and
avoiding building a second undesigned file format (`conclusions.yaml`'s own schema, its own
conformance check) to serve a single dict entry. Shape 2's real advantage — multi-
jurisdiction additivity — is a second-jurisdiction problem this project does not have yet;
building it now would be exactly the "anticipated, not forced by need" scope this
codebase's own conventions argue against elsewhere. If or when a second jurisdiction's rule
pack is actually being built, that is Shape 2's real trigger event, not a guess made now.
This is the founder's call, not decided here — presented for a decision.

---

### 4. Close-out

`make migrate-verify` and a clean `make schema-dump`, both against `ledgex_schema_check` —
no schema change. All four `db.yml`/`docs.yml` jobs green on the close-out commit. P30 row
added, its own close-out commit.
