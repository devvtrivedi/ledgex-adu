# LedgeX / ADU.X
# Source of record: docs/LEDGEX_SPEC.md. See §1.2 for the seven make targets
# this project treats as its CI gate (D12, P59: corrected from "six", matching
# §1.2's own table title), and §3.13 for migration conventions.
#
# schema / schema-dump / conformance require a running PostgreSQL 16 +
# PostGIS 3.4 instance reachable at DATABASE_URL. site (and qa's
# check_website_current) requires pandoc. None of these are exercised by
# `make all`, which only needs Python. Unlike pdf, site does not degrade
# gracefully without pandoc — see build/build_website.py for why.
#
# db/schema.sql is generated from PostgreSQL 16 + PostGIS 3.4 per §3. A dump
# taken with pg_dump against any other server version will produce a false
# diff against the committed file — match PG_DUMP/DATABASE_URL to 16 before
# regenerating it.

.PHONY: docs pdf site qa all clean check-boundary schema migrate migrate-baseline migrate-verify schema-dump db-test conformance test golden viewer-test liveness state smoke-real local-up local-down test-qa-check test-guard-destructive test-centroid-interior test-apn-canonicalization test-zoning-ambiguity test-compose-collision test-refresh-failure test-reconcile-identity-verified test-load-parcels-identity test-parcel-flap flag-invalid-geometry test-flag-invalid-geometry test-load-permits-attribution

# `all: qa pdf`'s ordering (qa before the docs regeneration pdf triggers) is
# not guaranteed under `make -j`: parallel make can start pdf's docs
# prerequisite while qa_check.py is still reading docs/*.md, racing a
# rewrite against a read. This project has no target that benefits from
# parallel execution, so parallelism is disabled outright rather than
# chasing individual targets that would break under it.
.NOTPARALLEL:

PYTHON         ?= python3
LINT_IMPORTS   ?= lint-imports
PG_DUMP        ?= pg_dump
PSQL           ?= psql
MIGRATIONS_DIR := db/migrations
SCHEMA_DUMP    := db/schema.sql
DATABASE_URL   ?= postgresql://localhost/ledgex_schema_check

# P18, README finding #25: db-test's own default, independent of
# DATABASE_URL above -- schema/schema-dump/migrate/migrate-verify are
# UNCHANGED by this, still read DATABASE_URL exactly as before. P14
# argued a scoped default "affects every other target"; P17 tested that
# reasoning and it does not hold mechanically -- this variable is the
# proof, read by db-test's own recipe only. postgresql://localhost/
# ledgex_test does not exist on a fresh clone -- db-test now fails LOUD
# ("database does not exist") on a first run rather than succeeding
# silently against ledgex_schema_check, which is how that database was
# contaminated twice (findings #9, #24). Explicit override still works
# exactly like every other target's DATABASE_URL override: `make db-test
# DB_TEST_DATABASE_URL=postgresql://...` (or, from CI, see db.yml's own
# comment at its db-test step for why it passes this instead of
# DATABASE_URL).
DB_TEST_DATABASE_URL ?= postgresql://localhost/ledgex_test

# P56 containment (prompts/P56-fixture-contamination-boundary.md close-out):
# same shape as DB_TEST_DATABASE_URL above, same reason. `make golden`
# (scripts/check_golden.py) writes real snapshot/parcel/fact rows under the
# REAL ca_san_jose.parcels source id and the REAL current licence id --
# request='{}' every time, no job_run row, bypassing every provenance
# convention the real ingest path follows. Run bare against whatever
# DATABASE_URL a developer's shell already has pointed at a local database
# (exactly how this repo's own P55 rebuild was contaminated hours after
# being certified clean, 2026-08-23), that lands permanently (0021) on
# whatever database is live. scripts/check_golden.py now reads this
# variable and never falls back to DATABASE_URL -- see its own
# golden_get_db() for the refusal shape. Explicit override:
# `make golden GOLDEN_DATABASE_URL=postgresql://...` (or, from CI, db.yml's
# own golden step, which passes the same already-seeded ledgex_ci this way).
# One-time local setup (golden_get_db() names these same three commands in
# its own refusal text if you skip this and hit it live):
#     createdb ledgex_golden
#     make schema DATABASE_URL=postgresql://localhost/ledgex_golden
#     psql postgresql://localhost/ledgex_golden -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql
GOLDEN_DATABASE_URL ?= postgresql://localhost/ledgex_golden

# pg_dump >=16.10 wraps every dump in a \restrict/\unrestrict pair keyed by a
# fresh random token each run (a psql safety marker, unrelated to schema
# content). Left random, schema-dump would show a diff every single run even
# with zero schema changes. Pinning it makes the dump byte-reproducible so
# "no diff" actually means no diff. Must be alphanumeric only.
PG_DUMP_RESTRICT_KEY ?= ledgexschemadumpfixedkey

# Session orientation, one command instead of ten. Generated at call time
# from the live repo -- never written to a committed file; a cached state
# file is worse than none, since nothing would ever mark it stale.
state:
	@$(PYTHON) build/state.py

# Regenerate the markdown files of record from build/ledgex_source.py and
# text/*.txt. Never hand-edit docs/LEDGEX_SPEC.md or docs/LEDGEX_RULES.md.
docs:
	$(PYTHON) build/build_spec.py
	$(PYTHON) build/build_rules.py
	$(PYTHON) build/build_spec_index.py

# Presentation artifact rendered from the regenerated markdown. No-ops with
# exit 0 if pandoc isn't installed — the markdown is the file of record.
pdf: docs
	$(PYTHON) build/make_pdf.py

# website/spec.html and website/rules.html, regenerated from docs/*.md via
# pandoc. Unlike `pdf`, this does NOT no-op without pandoc: a stale website
# with no reproducible source was exactly the bug this target exists to
# close (it published two mangled-prose invariant blocks and a duplicate
# make-targets table for two weeks after docs/LEDGEX_RULES.md was fixed,
# because nothing rebuilt it and qa_check.py only read docs/*.md). See
# build/build_website.py for the full history and the reverse-derived
# pandoc invocation.
site: docs
	$(PYTHON) build/build_website.py

# P59 sweep (pre-review verification, not part of the original C16 fix):
# build/test_qa_check_refusal_digits.py was added by C16 and proven RED/GREEN
# once, by hand, at fix time -- but never wired into this Makefile or
# .github/workflows/db.yml, so nothing would catch a future regression of
# the digit-blind-regex bug it exists to guard against. Found during the
# sweep's own wiring check (grep for the filename in Makefile/db.yml came
# back empty, the same shape as C20's own defect class); wired here rather
# than only reported, since the fix itself was a two-line addition.
test-qa-check:
	$(PYTHON) build/test_qa_check_refusal_digits.py

# Document QA — the drift gate. Fails on missing/duplicated invariants,
# mangled prose duplicates, a stale (hand-edited) generated file, or
# website/*.html that no longer matches what `make site` would produce from
# the current docs.
qa: test-qa-check
	$(PYTHON) build/qa_check.py

# qa must run before docs is regenerated, not after: if docs runs first, the
# staleness check in qa compares freshly-rebuilt markdown against the
# builders that just rebuilt it, which can never fail. It only has teeth run
# standalone against a committed tree — which is what CI does (CI calls
# `make qa` on its own, never `make docs` first). pdf still depends on docs
# for its own input, so `make all` still regenerates docs; it just does so
# after qa has already checked the tree as committed, not before.
all: qa pdf

# --- Seven make targets (spec §1.2) ---
# D12 (P59): corrected from "Six" -- check-boundary/schema/schema-dump/
# conformance/test/golden/liveness are the seven §1.2 names (liveness is
# scheduled/workflow_dispatch-only, not push/PR-gated like the other six,
# but it is still one of the seven -- see make liveness's own target
# below and §1.2's own row for it); `docs`/`pdf`/`qa`/`all`/`clean` above
# are this repo's own convenience targets, not part of that seven.

# Spec §1.2 make check-boundary: "Jurisdiction-name grep, import-linter,
# public-to-commerce catalogue query, filesystem authority, no-graph and
# Track B no-render checks." Three of those six pieces now run for real:
# import-linter (.importlinter -- I1's import-graph half, I15's import
# half), the jurisdiction-name grep (build/check_jurisdiction_names.py --
# I1's other half, the one import-linter structurally cannot see: a bare
# string literal with no import attached), and qa_check.py (document QA,
# I17's filesystem-authority piece). Still missing: the public-to-commerce
# catalogue query (I15's database half) and the no-graph / Track B
# no-render checks (I17/I19) -- .graphify/ and commerce/'s real schema
# don't exist yet either.
check-boundary:
	@command -v $(LINT_IMPORTS) >/dev/null 2>&1 || { echo "$(LINT_IMPORTS) not found — pip install -r scripts/requirements.txt"; exit 1; }
	$(LINT_IMPORTS)
	$(PYTHON) build/check_jurisdiction_names.py
	$(PYTHON) build/qa_check.py

# Apply every forward-only migration to an empty database, in order, AND
# record each one in schema_migrations as it goes (P6 follow-up). Still
# "builds from nothing" -- still fails outright on a non-empty database,
# ledgered or not, same as before this pass -- CI's guarantee is unchanged;
# what changed is that the database it produces is no longer the one
# condition scripts/migrate_verify.py exists to catch (applied, unrecorded).
# Spec §1.2 make schema: "Clean apply; constraints, functions and triggers
# compile." Making this idempotent (silently apply just what's missing) is
# still not done here and still deliberately not: that is `make migrate`'s
# job below, a different, weaker guarantee ("whatever's missing applies" vs
# "this builds from nothing"), kept as a separate tool for that reason.
#
# 0046_schema_migrations_ledger.sql is applied FIRST, out of numeric order,
# unconditionally, before the loop below -- it has to exist before anything
# can be recorded into it, and it has no FK to anything else in the schema
# so running it first is safe regardless of its own number (same reasoning
# scripts/migrate.py's bootstrap_ledger() already documents; this loop is
# the bash-only equivalent of that same bootstrap, not a second design).
#
# Each migration's own SQL and its ledger INSERT run as ONE psql invocation
# --single-transaction (confirmed directly: -f file.sql -c "INSERT ..." in
# one invocation commits both together on success, and a failure in the -f
# half runs the -c half not at all and commits nothing -- verified against a
# real deliberate failure before relying on it here) -- the same atomicity
# guarantee scripts/migrate.py's own psycopg2 transaction gives `make
# migrate`, just via psql instead of Python, so this target adds no new
# dependency to CI (db.yml has no Python setup step; it only ever needed
# psql/pg_dump).
#
# --single-transaction is exactly why 0031_output_channel_analytics_model_
# training.sql is split from 0032_licence_channel_analytics_model_training.sql
# rather than combined: PostgreSQL 12+ allows ALTER TYPE ... ADD VALUE inside
# a transaction, but forbids USING the new value (any DML referencing it)
# within that same transaction. 0031 only adds the two enum values; 0032, a
# separate migration and therefore a separate --single-transaction
# invocation here, is what references them. Do not undo that split to
# "simplify" -- combining them would fail outright the moment this target
# wraps each file in its own transaction, which it does, deliberately, as of
# this pass.
LEDGER_MIGRATION := 0046_schema_migrations_ledger.sql
# C9 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): make schema and make
# schema-dump ran raw psql/pg_dump against $(DATABASE_URL) with NO locality
# guard at all -- P56a's refuse_remote() closed this exact hole for the
# migrate toolchain (register #55) but never reached these two recipes,
# which never touch Python. Both now preflight through infra.env's own
# refuse_remote() -- REUSED, not a second hand-rolled host check (register
# #44 is the standing record of what that costs; C23 separately notes the
# reused guard is itself incomplete relative to full libpq semantics --
# accepted here, inherited, not re-litigated by this fix). DATABASE_URL
# travels via the environment, not interpolated into the -c string, so a
# value containing shell-special characters can never break the quoting.
schema:
	@DATABASE_URL="$(DATABASE_URL)" $(PYTHON) -c "import os, sys; sys.path.insert(0, '.'); from infra.env import refuse_remote; refuse_remote(os.environ['DATABASE_URL'])"
	@command -v $(PSQL) >/dev/null 2>&1 || { echo "$(PSQL) not found — install PostgreSQL 16 client tools"; exit 1; }
	@command -v shasum >/dev/null 2>&1 || { echo "shasum not found"; exit 1; }
	@echo "applying $(MIGRATIONS_DIR)/$(LEDGER_MIGRATION) (bootstrapped first -- see this target's own comment)"
	@hash0=$$(shasum -a 256 "$(MIGRATIONS_DIR)/$(LEDGER_MIGRATION)" | cut -d' ' -f1); \
	 $(PSQL) "$(DATABASE_URL)" -v ON_ERROR_STOP=1 --single-transaction \
		-f "$(MIGRATIONS_DIR)/$(LEDGER_MIGRATION)" \
		-c "INSERT INTO schema_migrations (version, file_sha256) VALUES ('0046', '$$hash0')" \
		|| exit 1
	@for f in $(MIGRATIONS_DIR)/*.sql; do \
		base=$$(basename "$$f"); \
		if [ "$$base" = "$(LEDGER_MIGRATION)" ]; then continue; fi; \
		echo "applying $$f"; \
		version=$$(echo "$$base" | cut -d_ -f1); \
		hash=$$(shasum -a 256 "$$f" | cut -d' ' -f1); \
		$(PSQL) "$(DATABASE_URL)" -v ON_ERROR_STOP=1 --single-transaction \
			-f "$$f" \
			-c "INSERT INTO schema_migrations (version, file_sha256) VALUES ('$$version', '$$hash')" \
			|| exit 1; \
	done

# P6: bring an already-partially-migrated database forward, safely, which
# `make schema` above cannot do (it only works against an empty database).
# Applies only migrations not yet recorded in schema_migrations, each atomic
# with its own ledger row -- see scripts/migrate.py's own docstring for the
# three things it checks on every run: a migration applied but unrecorded,
# one recorded whose file changed since (refuses -- migrations are
# forward-only), and a pre-ledger database with no ledger AND no way to
# safely guess what already ran (refuses -- see `make migrate-baseline`).
# P56a: DATABASE_URL passed explicitly, same shape db-test/test/golden
# already use for their own dedicated variables -- this one is DATABASE_URL
# itself, not a scoped variable, because migrate.py's whole job is applying
# DDL to whatever database DATABASE_URL already names. Without this, the
# Makefile's own local default was never reachable by this recipe at all
# (no `export` directive exists in this file) -- confirmed live, and closed
# together with infra.env.refuse_remote() now guarding the actual connection
# (see infra/env.py's own P56a correction). This closes the "no shell
# variable set, so .env's remote host wins" path; it does NOT close a
# shell already pointing DATABASE_URL at a local-but-wrong database, which
# --DATABASE_URL's own semantics can never distinguish from "the database
# you meant."
migrate:
	DATABASE_URL="$(DATABASE_URL)" $(PYTHON) scripts/migrate.py

# P6, one-time only: adopt a pre-ledger database (schema_migrations does not
# exist, but the database is not empty either -- `make migrate` refuses this
# case outright rather than guess). Builds a disposable reference database,
# applies every migration to it from empty, and only records this database's
# ledger if a real schema diff against that reference is byte-identical. See
# scripts/migrate_baseline.py's own docstring for the full argument.
migrate-baseline:
	DATABASE_URL="$(DATABASE_URL)" PG_DUMP=$(PG_DUMP) $(PYTHON) scripts/migrate_baseline.py

# P6: independent check that a database's LIVE schema actually matches what
# its own schema_migrations ledger claims -- catches a ledger row with no
# matching DDL, or DDL with no matching ledger row, neither of which
# migrate.py's own read-the-ledger logic can see (both are impossible to
# produce through migrate.py itself; this is for a database touched some
# other way). See scripts/migrate_verify.py's own docstring.
migrate-verify:
	DATABASE_URL="$(DATABASE_URL)" PG_DUMP=$(PG_DUMP) $(PYTHON) scripts/migrate_verify.py

# Regenerate db/schema.sql from whatever schema is live at DATABASE_URL and
# diff it against the committed dump. Run `make schema` against an empty
# database first for a true "clean apply" dump.
# Spec §1.2 make schema-dump: "No diff; missing or stale generated DDL
# fails."
schema-dump:
	@DATABASE_URL="$(DATABASE_URL)" $(PYTHON) -c "import os, sys; sys.path.insert(0, '.'); from infra.env import refuse_remote; refuse_remote(os.environ['DATABASE_URL'])"
	@command -v $(PG_DUMP) >/dev/null 2>&1 || { echo "$(PG_DUMP) not found — install PostgreSQL 16 client tools"; exit 1; }
	@command -v $(PSQL) >/dev/null 2>&1 || { echo "$(PSQL) not found — install PostgreSQL 16 client tools"; exit 1; }
	@# postgis/postgis:16-3.4 is a floating tag: it can rebuild on a new 16.x
	@# point release at any time, with zero schema change, and the dump's own
	@# "-- Dumped from database version" line (stripped below, same reason as
	@# the pg_dump build-string strip) would otherwise be the only thing that
	@# noticed. Assert the major version directly against the server instead
	@# of inferring it from dump text that no longer exists.
	@ver=$$($(PSQL) "$(DATABASE_URL)" -tAc "SHOW server_version_num;" | tr -d '[:space:]'); \
	 case "$$ver" in \
	   16????) ;; \
	   *) echo "schema-dump: DATABASE_URL is PostgreSQL server_version_num=$$ver, not 16.x -- refusing to dump (§3 requires PostgreSQL 16)."; exit 1;; \
	 esac
	$(PG_DUMP) "$(DATABASE_URL)" --schema-only --no-owner --no-privileges --restrict-key=$(PG_DUMP_RESTRICT_KEY) > $(SCHEMA_DUMP).tmp
	@# pg_dump embeds its own build string in "-- Dumped by pg_dump version
	@# X.Y (Platform)" -- Homebrew's build and Ubuntu PGDG's build report
	@# different platform text even at the identical version (hit this for
	@# real: local 16.14 Homebrew vs CI 16.14 Ubuntu produced an otherwise
	@# byte-identical dump that still "differed"). Strip it: it documents
	@# which pg_dump binary ran, not anything about the schema. Same for
	@# "-- Dumped from database version": it documents the exact point
	@# release (e.g. 16.4 vs 16.5) of a floating tag, not a schema property --
	@# the server_version_num assertion above is the real guarantee now.
	@sed -i.bak -e '/^-- Dumped by pg_dump version/d' -e '/^-- Dumped from database version/d' $(SCHEMA_DUMP).tmp && rm -f $(SCHEMA_DUMP).tmp.bak
	@if [ ! -f $(SCHEMA_DUMP) ]; then \
		mv $(SCHEMA_DUMP).tmp $(SCHEMA_DUMP); \
		echo "wrote $(SCHEMA_DUMP) (no prior committed dump to compare)"; \
	elif diff -q $(SCHEMA_DUMP) $(SCHEMA_DUMP).tmp >/dev/null; then \
		rm $(SCHEMA_DUMP).tmp; \
		echo "$(SCHEMA_DUMP) is current — no diff."; \
	else \
		diff -u $(SCHEMA_DUMP) $(SCHEMA_DUMP).tmp || true; \
		mv $(SCHEMA_DUMP).tmp $(SCHEMA_DUMP); \
		echo "$(SCHEMA_DUMP) regenerated — review and commit the diff."; \
		exit 1; \
	fi

# Run the invariant test suite (I2-I5, I13, I18, and the parcel_exception
# outcome/resolution biconditional) against DATABASE_URL. Every test is a
# self-asserting DO block; ON_ERROR_STOP makes a failed assertion abort the
# script with a nonzero exit code rather than print a misleading pass.
#
# POINT THIS AT A DISPOSABLE DATABASE. This target reads
# DB_TEST_DATABASE_URL, NOT DATABASE_URL (P18, README finding #25 --
# closed) -- with no argument, it runs against DB_TEST_DATABASE_URL's own
# default above, postgresql://localhost/ledgex_test, a database that does
# not exist on a fresh clone (create it with `make schema
# DATABASE_URL=postgresql://localhost/ledgex_test` first, or point
# DB_TEST_DATABASE_URL at whatever scratch database you already have).
# This is a DIFFERENT default than schema/schema-dump/migrate/
# migrate-verify use, deliberately -- P17 confirmed a scoped default is
# mechanically independent of those four, and this variable is that
# independence: none of them read DB_TEST_DATABASE_URL, and this target
# does not read DATABASE_URL. Every run of db/tests/invariants.sql writes
# one or more permanent parcels plus every fact any test writes against
# them (0017/I4 make both undeletable by design -- see that file's own
# precondition comment at the top) -- that is exactly how
# ledgex_schema_check (the OLD default) was contaminated twice (findings
# #9, #24). A developer who explicitly still wants to run this against
# ledgex_schema_check can: `make db-test
# DB_TEST_DATABASE_URL=postgresql://localhost/ledgex_schema_check` --
# explicit, not a silent default.
#
# P17, finding #26: db/tests/teardown.sql now runs UNCONDITIONALLY, as its
# own separate psql invocation, after the suite -- pass or fail. The
# suite's own exit code ($$suite_exit below), not teardown's, is what
# this target ultimately exits with: a passing suite stays a passing
# `make db-test` even if teardown finds nothing to do, and a failing
# suite stays a failing `make db-test` even though teardown still runs
# and still cleans up. Getting this backwards -- letting teardown's exit
# code win, or skipping teardown on failure -- is exactly the
# silently-passing-gate failure this repo has already found elsewhere
# (qa_check, conformance, golden): a green `make db-test` on a red suite.
db-test:
	@command -v $(PSQL) >/dev/null 2>&1 || { echo "$(PSQL) not found"; exit 1; }
	@$(PSQL) "$(DB_TEST_DATABASE_URL)" -v ON_ERROR_STOP=1 -f db/tests/invariants.sql; \
	 suite_exit=$$?; \
	 echo ""; \
	 echo "db-test: suite exited $$suite_exit -- running db/tests/teardown.sql unconditionally (P17, finding #26)"; \
	 $(PSQL) "$(DB_TEST_DATABASE_URL)" -v ON_ERROR_STOP=1 -f db/tests/teardown.sql; \
	 teardown_exit=$$?; \
	 if [ "$$teardown_exit" -ne 0 ]; then \
		echo "db-test: WARNING -- teardown itself exited $$teardown_exit (see output above)."; \
		echo "db-test: this target still reports the SUITE's own exit code ($$suite_exit), not teardown's --"; \
		echo "db-test: a teardown problem never masks a passing suite, and a passing teardown never masks a failing one."; \
	 fi; \
	 exit $$suite_exit

# P59, C1 (LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): the geometry-interior-point
# regression fixture -- same wiring shape as db.yml's own
# scripts/test_snapshot_race_invariant.py step (no pytest-postgresql, needs
# a real, schema-migrated DATABASE_URL, .venv-ingest for psycopg2). Not
# folded into db-test/invariants.sql: that suite is single-connection psql,
# this needs a real Python process to import
# scripts/ingest_zoning_permits.populate_interior_centroids() directly,
# same reason the snapshot-race test isn't in invariants.sql either.
test-centroid-interior:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_centroid_interior_invariant.py

# Parameterized pack suite for sources, mappings, rights and dependency
# cascades. Spec §1.2 make conformance: "Every enabled pack passes; no
# rights broadening or silent missing dependency." P26: real for the one
# real pack, jurisdictions/ca_san_jose -- schema validity plus every
# active, ca_san_jose-owned source's licence/field_definition/
# expected_fields agreement with the live database. D8 (P59): mappings,
# rights broadening against Plan 2.1.4 Appendix K, and dependency
# cascades are NOT yet checked -- scripts/check_conformance.py names all
# THREE explicitly on every run, same coverage-honesty discipline P20/P21
# already established for make golden/make test. Endpoint liveness is
# real (P28, make liveness, its own separate scheduled-only gate) and is
# NOT one of these three -- this comment previously said "all four...
# including liveness," which check_conformance.py's own docstring has
# never claimed. The exit code here means ONLY that those real checks
# passed, not that §1.2's full contract is satisfied.
conformance:
	DATABASE_URL="$(DATABASE_URL)" $(PYTHON) scripts/check_conformance.py

# C20 (P59): 4 pre-existing invariant-test scripts, found unwired into
# either make or db.yml, and 2 of them (apn/ambiguity, below) with real
# defects on top of that -- fixed as part of the same finding, not
# separately: an unwired test with a coverage gap is still unwired once
# wired, so both had to be fixed together to make wiring worth doing.
#
# scripts/test_apn_canonicalization_invariant.py: had a hardcoded, session-
# specific absolute scratchpad path (unrunnable outside the session that
# wrote it) AND derived its parcel-side APN by hand rather than through the
# real canonicalize_identifier() -- bypassing the exact function this test
# exists to exercise. Both fixed: portable tempfile, and the parcel apn is
# now produced by canonicalize_identifier() from a raw value carrying the
# real observed parcels-side artifact (trailing whitespace), independent
# of the permits-side artifact (leading apostrophe) so neither side's
# fixture is derived from the other's output.
test-apn-canonicalization:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_apn_canonicalization_invariant.py

# scripts/test_zoning_ambiguity_invariant.py: same hardcoded absolute-path
# defect as above (fixed the same way), plus a coverage gap -- it checked
# the fact resolved correctly and wasn't falsely flagged ambiguous, but
# never checked that the non-blocking "companion polygon" anomaly
# (REASON_MULTIPLE_POLYGONS_AGREE) is actually recorded, even though its
# own fixture is exactly the shape that must trigger it. A regression that
# silently dropped that detection would have passed this test unnoticed.
# Now asserts the anomaly exception is present and names both real
# FACILITYIDs.
test-zoning-ambiguity:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_zoning_ambiguity_invariant.py

# scripts/test_compose_collision_invariant.py: no defect found in the test
# itself -- just never wired into make or db.yml.
test-compose-collision:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_compose_collision_invariant.py

# scripts/test_refresh_failure_invariant.py: no defect found in the test
# itself -- just never wired into make or db.yml. Needs a real object
# store (OBJECT_STORE_* -- see .env), same as test-parcel-flap above.
test-refresh-failure:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_refresh_failure_invariant.py

# C19 (P59): Phase E same_as_previous fast path must actually verify
# identity presence, not just non-blank PARCELID. Needs day4_sources.sql
# applied plus a reachable object store (real MinIO-backed snapshot, same
# requirement as test-parcel-flap above).
test-reconcile-identity-verified:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_c19_reconcile_identity_verified.py

# C10 (P59): Phase D canonicalization/identity/single-transaction fixture.
# Needs day4_sources.sql applied (real ca_san_jose.parcels source).
test-load-parcels-identity:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_load_parcels_identity.py

# C5 (P59): the disappear/reappear/disappear-again flap regression. Needs
# a real object store (OBJECT_STORE_* -- see .env) and a database with
# day4_sources.sql applied; run against a scratch database, never a
# database carrying real bulk parcels data (phase_e reconciles the WHOLE
# parcel table under SOURCE_ID every run -- see the script's own
# docstring).
test-parcel-flap:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_parcel_flap_invariant.py

# C4 (P59): scripts/flag_invalid_geometry.py was wired into no Makefile
# target and no CI workflow -- the 28 known-invalid parcels on the real
# database were discovered once, by hand, and never re-detected since. Runs
# both detectors (parcel geometry + zoning-source geometry); local use only
# needs $(DATABASE_URL). See db.yml's own step for the CI variant, which
# skips the zoning-source half (its own scratch-file dependency, unrelated
# to this target).
flag-invalid-geometry:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/flag_invalid_geometry.py

# C4 (P59): regression fixture -- a self-intersecting polygon proves the
# detector fires and the closure path (added this pass) actually closes.
test-flag-invalid-geometry:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_flag_invalid_geometry.py

# C2 (P59): two-run regression fixture -- a permit's APN going blank must
# never fabricate permits.active=false. Needs day4_sources.sql applied
# (real ca_san_jose.building_permits_active source + cc0_api_2026_08
# licence) and NO pre-existing real permits data in DATABASE_URL -- see
# the script's own docstring: load_permits reconciles against the FULL
# live permits.active/series_earliest set, so running it against a
# database that already has real bulk permits facts turns every one of
# them into an "attribution lost" exception this run. Safe against
# ledgex_test/ledgex_ci; NOT safe against ledgex_schema_check.
test-load-permits-attribution:
	DATABASE_URL="$(DATABASE_URL)" .venv-ingest/bin/python3 scripts/test_load_permits_attribution.py

# Spec §6.4 make liveness: "every active source responds with expected
# fields." P28: real for the pack's three active, ca_san_jose-owned
# sources -- a bounded-prefix GET (never a full ingest), checked for the
# raw key(s) each declared field_key actually depends on. Writes no
# snapshot row (not a fetch in C7's sense -- see
# scripts/check_liveness.py's own module docstring); writes a job_run row
# per source using job_run.schema_drift for its own already-declared
# meaning. NOT wired into db.yml/docs.yml -- scheduled
# (.github/workflows/liveness.yml) plus workflow_dispatch, not push-gated
# (an external city government endpoint has no SLA to this project; see
# prompts/P28-liveness.md section 2 for the full argument against gating
# every push on it). Federal sources and non-active sources are named,
# not silently skipped -- see the script's own summary output.
liveness:
	DATABASE_URL="$(DATABASE_URL)" $(PYTHON) scripts/check_liveness.py

# Spec §1.2 make test: "Unit and integration suites, including review,
# entitlement, outcome observation, provider slot, edge guard and billing
# independence." P21: core/model's own real pytest suite exists now
# (tests/core/) -- review, entitlement, outcome observation, provider
# slot, edge guard and billing independence do not, and this target says
# so explicitly on every run, same resolution P20 already applied to
# `make golden` rather than a second convention: the exit code tracks
# ONLY whether the real, built suite passes (0 = it passed, 1 = it
# failed), never a blanket 1 regardless of correctness (which would make
# a real pass indistinguishable from a broken one, and make a
# break-then-revert proof meaningless) and never a blanket 0 once any
# slice passes (which would claim coverage this target does not have).
#
# TEST_DATABASE_URL, not DATABASE_URL -- same reason db-test got its own
# DB_TEST_DATABASE_URL (P18, finding #25): the fact_provenance_complete
# equivalence test (tests/core/test_fact_provenance_equivalence.py)
# writes real fact/parcel rows, and DATABASE_URL's own default points at
# ledgex_schema_check, the shared local dev database. Defaults to the
# same disposable ledgex_test db-test already uses -- one shared scratch
# database for both, not a second one to create.
TEST_DATABASE_URL ?= postgresql://localhost/ledgex_test
test:
	@echo "TEST: running core/model's real suite (P21) -- tests/core/ (Fact/Parcel/Source/Licence/ParcelException/Refusal/Result shape validation, plus the fact_provenance_complete equivalence proof)."
	@echo "TEST: NOT covered (SPEC.md sec 1.2's own list, none of core/'s or commerce/'s remaining scope exists yet): review, entitlement, outcome observation, provider slot, edge guard, billing independence."
	DATABASE_URL="$(TEST_DATABASE_URL)" $(PYTHON) -m pytest tests/core/ -v

# D7 (P59): corrected -- was quoting an already-stale spec row, omitted
# the third fixture, and repeated D6's own two miscounts (see
# scripts/check_golden.py's own module docstring, which had the same two
# errors and was fixed alongside this).
#
# Spec §1.2 make golden: "Normalized composed, partial, refused and
# geometry-disabled Base Core fixtures." P20 made refused real; P25 makes
# geometry-disabled real too, via scripts/check_golden.py and
# tests/golden/ca_san_jose/{refused,geometry_disabled}.json -- composed
# and partial are still not (would mean fabricating a licence clearance
# STANDING-BLOCKER.md says does not exist for the paid_property_file
# channel these two fixtures compose on). P34 added a THIRD fixture,
# election_required (README finding #35) -- checked alongside the other
# two, not a fifth taxonomy member (see the script's own docstring).
# refused/geometry-disabled carry THREE refusals each (RIGHTS_BLOCKED,
# GEOMETRY_TIER_DISABLED and, since P53, LICENCE_UNKNOWN -- the L0/LD-1
# jurisdiction gate given a real runtime representation,
# prompts/P53-l0-gate.md); election_required carries FOUR (those three
# plus its own ELECTION_REQUIRED) -- P25's own report settles why
# refusals accumulate across stages rather than short-circuiting. This
# target's own exit code tracks ONLY those three fixtures' own
# correctness (0 = all three passed, 1 = any failed) -- it does NOT mean
# "all four §1.2 classes covered." scripts/check_golden.py prints the two
# missing classes explicitly on every single run, pass or fail -- see
# that script's own module docstring for the full argument against
# either silently inflating this to "done" or silently keeping it at
# an uninformative permanent exit 1.
golden:
	GOLDEN_DATABASE_URL="$(GOLDEN_DATABASE_URL)" $(PYTHON) scripts/check_golden.py

# P43. scripts/test_viewer_rights_gate.py (P42) proves the I6 rights gate
# holds on api/'s one fact-rendering route (GET /v1/parcels/{id}/facts) --
# calls the route directly, serializes the result through the SAME
# Pydantic response_model FastAPI itself uses to build the real wire
# response, then asserts a rights-blocked fact's value is absent from
# those exact bytes, not merely absent from a Python dict. This target
# does NOT seed its own fixture: scripts/seed_internal_test_licences.py's
# own opt-in gate (SEED_INTERNAL_TEST_LICENCES=1) exists precisely so
# nothing -- including a test target -- triggers that permanent write
# (licence/licence_channel rows, immutable, 0027/0033) as a side effect.
# The script itself refuses loudly, naming the exact seed command, if its
# expected parcel is not there. Run the seed first, as its own separate,
# explicit step -- db.yml does this the same way it already does for
# db/seeds/day4_sources.sql, a different seed-dependent step with the
# identical shape.
viewer-test:
	@echo "VIEWER-TEST: proves the I6 rights gate on api/'s ONE fact-rendering route (GET /v1/parcels/{id}/facts) -- one parcel, one channel ('api'), the internal_test.* licence pair plus one real cc_by_4_0 fixture fact (scripts/seed_internal_test_licences.py, P42). Asserts the blocked fact's value is absent from the real serialized response body, not eyeballed."
	@echo "VIEWER-TEST: NOT covered -- the other six api/ routes (rights, sources, job-runs, exceptions, property-files, schema), any channel but 'api', any parcel but the one the seed script creates, and whether the HTML viewer itself renders correctly. This proves the gate does not leak on the seeded fixture; it does not prove the viewer is correct."
	DATABASE_URL="$(DATABASE_URL)" $(PYTHON) scripts/test_viewer_rights_gate.py

# P50. The one command that answers "is this machine wired up right now, and
# does a real byte from a real San Jose endpoint still reach a rights-gated
# answer?" -- Docker, Postgres, the object store, the viewer and outbound
# internet checked first, then fetch -> sha-256 -> snapshot -> 20-parcel
# ingest -> read one back in SQL and over HTTP -> I6 gate, PASS or FAIL.
#
# SMOKE_DATABASE_URL, not DATABASE_URL, and no fallback to it -- the same
# resolution DB_TEST_DATABASE_URL (P18, finding #25) and TEST_DATABASE_URL
# (P21) already reached, for a stronger version of the same reason: this
# target makes PERMANENT writes. fact_no_delete/fact_no_update (0017,
# 0007/0040) and snapshot immutability (0021) mean a row written into the
# wrong database cannot be taken back by anything, migration included. On a
# fresh clone postgresql://localhost/ledgex_smoke does not exist and step 4
# fails LOUD with the createdb/make schema/seed commands -- rather than
# succeeding quietly against ledgex_schema_check, which is how that database
# was contaminated twice (CLAUDE.md; findings #9, #24).
#
# scripts/smoke_real.py refuses a non-local SMOKE_DATABASE_URL outright and
# gives itself no override flag. infra.env.get_db()'s LEDGEX_ALLOW_REMOTE_DB
# escape hatch exists for a deliberate operator; a smoke test is never that.
#
# SMOKE_PYTHON exists because this script needs scripts/requirements.txt
# (psycopg2, requests, boto3), not just core/'s. Step 1 names the exact fix
# if the interpreter it is given cannot import them:
#     make smoke-real SMOKE_PYTHON=.venv-ingest/bin/python3
#
# WHAT IT DOES NOT PROVE is printed on every single run, pass or fail --
# same coverage-honesty discipline as `make test`, `make golden` and
# `make viewer-test`. It runs none of those and does not stand in for them,
# it never runs --phase e, and it never triggers
# scripts/seed_internal_test_licences.py (a permanent licence write, gated
# by SEED_INTERNAL_TEST_LICENCES=1 for exactly that reason). D2 (P59):
# step 15 has been a both-outcomes proof (refusal AND permission, via its
# own deterministic self-seeded blocked fact) since P55 Phase 2 Stage 4 --
# not refusal-only. `make viewer-test` proves the same gate on a
# DIFFERENT route (GET /v1/parcels/{id}/facts, one internal_test.* fixture
# pair) -- the two are complementary coverage, not "the other half" of a
# refusal-only step 15.
SMOKE_DATABASE_URL ?= postgresql://localhost/ledgex_smoke
SMOKE_PYTHON       ?= $(PYTHON)
smoke-real:
	SMOKE_DATABASE_URL="$(SMOKE_DATABASE_URL)" $(SMOKE_PYTHON) scripts/smoke_real.py

# P51. The manual walkthrough this replaces: derive PGPASSWORD from the
# `ledgex` container by hand, export it into one shell, run uvicorn with a
# hand-typed DATABASE_URL -- brittle exactly where it matters, because a new
# terminal or a `cd` loses the exports and a relative .venv-api/bin/python3
# silently resolves to nothing (exit 127). scripts/local_up.py fixes both:
# it resolves its own repo root from its own file path (never cwd, never an
# env var) and re-execs itself under .venv-api's own interpreter the moment
# it notices it isn't already running there -- so it works invoked by
# absolute path from anywhere, under whatever python3 happens to be on
# PATH. `make -C ~/Desktop/ledgex-adu local-up` (or the absolute-path
# invocation above) is the equivalent from another directory -- `make`
# itself still needs a Makefile in the cwd; this target does not change
# that.
#
# Reuses P50's env-binding and refusal logic rather than a second copy of
# the same judgment: infra.env._is_local/resolved_host, imported the same
# way scripts/smoke_real.py's own step_env() already does (P47 finding #44
# is on record about what a second hand-rolled copy costs). Binds only
# SMOKE_DATABASE_URL, defaulting to the local smoke database -- NEVER
# DATABASE_URL, under any name, for the identical P39/finding #43 reason
# smoke-real above never reads it either.
#
# Idempotent: a second `make local-up` while the viewer is already healthy
# reports that and exits 0 without starting a second process. `make
# local-down` stops ONLY the one pid it recorded, and only after confirming
# that pid's own command line still looks like our uvicorn invocation --
# never a pattern-matched pkill, never anything else.
local-up:
	$(PYTHON) scripts/local_up.py

local-down:
	$(PYTHON) scripts/local_up.py --down

# P59 sweep (pre-review verification, not part of the original C24.1 fix):
# .claude/hooks/test_guard_destructive.py (48 MUST_BLOCK/MUST_ALLOW cases)
# was added by C24.1 and proven 48/48 once, by hand, at fix time -- but
# never wired into this Makefile or any .github/workflows/*.yml, so nothing
# would catch a future regression of the guard's psql -h/PGHOST coverage.
# Found during the sweep's own wiring check (grep for the filename came
# back empty everywhere, the same shape as C20's own defect class); not
# folded into qa/check-boundary/all since guard_destructive.py is Claude
# Code dev-tooling (a PreToolUse hook, .claude/settings.json), not one of
# §1.2's seven spec-defined targets -- a standalone target instead, run
# deliberately, same reasoning as local-up/local-down above.
test-guard-destructive:
	$(PYTHON) .claude/hooks/test_guard_destructive.py

clean:
	rm -rf dist build/__pycache__ $(SCHEMA_DUMP).tmp
