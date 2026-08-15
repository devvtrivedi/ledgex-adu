# prompts/ — the work queue

One package per file. **Read this index plus the one active package. Nothing else.**
Finished packages move to `done/` and are not read again unless something contradicts them.

| # | Package | Status | Landed as |
|---|---|---|---|
| P1 | [Refresh-failure hole](done/P1-refresh-failure.md) | done, pushed | `3bee5bd` |
| P2 | [Three correctness fixes](done/P2-correctness-fixes.md) | done, pushed | `40b953d`, `bd5db19`, `6cebdaf` |
| P3 | [Phase B — changed / new / disappeared](P3-phase-b.md) | done, reviewed, pushed | `62cf90f` |
| P4 | [Source-scoped reconciliation](P4-source-scoped-reconciliation.md) | done, pushed | `46a24c2`, `a62b4a7` |
| P5 | [Zoning + permits reconciliation](P5-zoning-permits-reconciliation.md) | gate resolved, not started | — |

**P5 gate — resolved.** Three items:

- Five local commits pushed (`37def22`, tracking `prompts/` itself).
- `§6` hole closed: SECTION_INDEX carries a `6` row again (build/ledgex_source.py
  `SECTION_INDEX` + `UNINDEXED_SUBSECTIONS`), verified against real `### 6.N` headings by
  `build_spec_index.py` rather than dropped from the index. Restoring §6's own top-level
  heading is still out of scope — the region immediately before it in
  `text/LedgeX_Engineering_Reference_Spec_v1_28.txt` is pdftotext-mangled — but a reader
  following the index now reaches §6.1 instead of finding nothing. SPEC_VERSION 1.28.
- `§8`: never real. Confirmed against `text/LedgeX_Engineering_Reference_Spec_v1_7.txt`
  (the earliest version this repo's git history has — the initial commit), whose own
  "Section N —" markers already jump 5 → 7 → 9 with nothing between them. Every version
  since does the same. The "open finding" citing `§8` was always pointing at a section
  number with no corresponding section, not at content that went missing — most likely a
  stale reference to §3.3 (Canonical field vocabulary, which the same migration's own
  header names one line below its "§8" citation, and which is what actually defines
  `stale_after_days`/`required_for_file`, I7/I9). Two dangling `§8` cross-references remain
  unfixed, both out of scope for this pass: `db/migrations/0003_fields.sql`'s own header
  comment (a migration file — no changes under `db/` this pass) and the raw text's task-shape
  B step 1 (inside the same mangled region §6's heading sits in). Do not write §8 content to
  close this — there is nothing it was ever supposed to say.

**Current blocking state:** none. `origin/main` is at `37def22`, matching HEAD — everything
above is pushed. The §6/§8/CLAUDE.md work that resolved the P5 gate (this session) is still
local-only pending review; check `git log --oneline origin/main..HEAD` before trusting a SHA
named above it in conversation, per the standing multiple-checkouts hazard.

**Also current:** `load_zoning` and `load_permits` raise `UniqueViolation` on
`fact_one_current_per_source` against any changed snapshot, roll back cleanly and mark
`job_run` failed (established in P4 step 4, no silent duplication). Two of three sources
therefore cannot re-ingest at all until P5. This is safe, not broken — but it is the
operating state, and P5 exists to lift it.

Standing context that does not belong to any package:

- [CONVENTIONS.md](CONVENTIONS.md) — the hard rules every package inherits. Prompts reference
  it instead of restating it.
- [STANDING-BLOCKER.md](STANDING-BLOCKER.md) — why every composition still refuses. Not an
  engineering task.

## Session hygiene

Context is the scarcest resource in this project and most of it is spent before any work
starts. Measured:

| What | Size | Loaded when |
|---|---|---|
| `docs/LEDGEX_SPEC.md` | 209 KB (~52k tokens) | **every session** — CLAUDE.md says "in full" |
| `db/tests/invariants.sql` | 199 KB | whenever a test is added |
| `db/schema.sql` | 63 KB | whenever schema is checked |
| all of `prompts/` | 49 KB | — |
| README + CONVENTIONS + one package | ~14 KB | what a session should actually load |

So: **one session per package, started cold.** Read this index, `CONVENTIONS.md`, and the
one active package. Do not carry a finished package's conversation into the next one — the
Review findings section exists so the next session does not need the transcript.

Grep `invariants.sql` and `schema.sql`; never read them whole. Same for the spec until
`docs/SPEC_INDEX.md` exists.

## How a package is written

Each file has three parts, in this order:

1. **What is actually wrong** — verified against a named commit, with file and line
   references. Never carried over from an earlier document without re-checking.
2. **The prompt** — a fenced block, paste-ready, nothing above or below it to edit out.
3. **In plain terms** — analogies. Skip when acting; read when deciding.

Packages landed under review also carry a **Review findings** section appended after the
fact. That section is the record of what the package got wrong, and it is what seeds the
next package.

## Adding a package

New file `P<n>-<slug>.md`, new row in the table above. Do not extend an existing package
once it has landed — findings go in its Review findings section and the fix goes in a new
package. Same forward-only discipline as `db/migrations/`, for the same reason: a package
that gets edited after it ran stops being a record of what was actually asked.
