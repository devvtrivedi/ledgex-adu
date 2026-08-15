# prompts/ — the work queue

One package per file. **Read this index plus the one active package. Nothing else.**
Finished packages move to `done/` and are not read again unless something contradicts them.

| # | Package | Status | Landed as |
|---|---|---|---|
| P1 | [Refresh-failure hole](done/P1-refresh-failure.md) | done, pushed | `3bee5bd` |
| P2 | [Three correctness fixes](done/P2-correctness-fixes.md) | done, pushed | `40b953d`, `bd5db19`, `6cebdaf` |
| P3 | [Phase B — changed / new / disappeared](P3-phase-b.md) | done, reviewed, **unpushed** | `62cf90f` |
| P4 | [Source-scoped reconciliation](P4-source-scoped-reconciliation.md) | done, **unpushed** | `46a24c2`, `a62b4a7` |
| P5 | [Zoning + permits reconciliation](P5-zoning-permits-reconciliation.md) | **gated** — see below | — |

**P5 gate.** Three small items first: push the five local commits; close the `§6` hole in
`docs/SPEC_INDEX.md` (§6 has no top-level heading, was dropped from the index, and is the
section the spec's own reading order at line 19 sends every new task to — §6.1 task shapes,
§6.2 the jurisdiction rule CLAUDE.md itself cites, §6.3 definition of done); and settle
whether `§8` is empty by accident, since an open finding still cites it.

**Current blocking state:** three commits local-only. `origin/main` is at `6cebdaf`.
Nothing is externally verifiable at a SHA until they are pushed, and the standing
multiple-checkouts hazard applies. Push before starting P5.

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
