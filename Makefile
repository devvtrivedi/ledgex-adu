# LedgeX / ADU.X
# Source of record: docs/LEDGEX_SPEC.md. See §1.2 for the six make targets
# this project treats as its CI gate, and §3.13 for migration conventions.
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

.PHONY: docs pdf site qa all clean check-boundary schema migrate migrate-baseline migrate-verify schema-dump db-test conformance test golden state

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

# Document QA — the drift gate. Fails on missing/duplicated invariants,
# mangled prose duplicates, a stale (hand-edited) generated file, or
# website/*.html that no longer matches what `make site` would produce from
# the current docs.
qa:
	$(PYTHON) build/qa_check.py

# qa must run before docs is regenerated, not after: if docs runs first, the
# staleness check in qa compares freshly-rebuilt markdown against the
# builders that just rebuilt it, which can never fail. It only has teeth run
# standalone against a committed tree — which is what CI does (CI calls
# `make qa` on its own, never `make docs` first). pdf still depends on docs
# for its own input, so `make all` still regenerates docs; it just does so
# after qa has already checked the tree as committed, not before.
all: qa pdf

# --- Six make targets (spec §1.2) ---
# The spec's CI gate. check-boundary/schema/schema-dump/conformance/test/golden
# are the six; `docs`/`pdf`/`qa`/`all`/`clean` above are this repo's own
# convenience targets, not part of that six.

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
schema:
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
migrate:
	$(PYTHON) scripts/migrate.py

# P6, one-time only: adopt a pre-ledger database (schema_migrations does not
# exist, but the database is not empty either -- `make migrate` refuses this
# case outright rather than guess). Builds a disposable reference database,
# applies every migration to it from empty, and only records this database's
# ledger if a real schema diff against that reference is byte-identical. See
# scripts/migrate_baseline.py's own docstring for the full argument.
migrate-baseline:
	PG_DUMP=$(PG_DUMP) $(PYTHON) scripts/migrate_baseline.py

# P6: independent check that a database's LIVE schema actually matches what
# its own schema_migrations ledger claims -- catches a ledger row with no
# matching DDL, or DDL with no matching ledger row, neither of which
# migrate.py's own read-the-ledger logic can see (both are impossible to
# produce through migrate.py itself; this is for a database touched some
# other way). See scripts/migrate_verify.py's own docstring.
migrate-verify:
	PG_DUMP=$(PG_DUMP) $(PYTHON) scripts/migrate_verify.py

# Regenerate db/schema.sql from whatever schema is live at DATABASE_URL and
# diff it against the committed dump. Run `make schema` against an empty
# database first for a true "clean apply" dump.
# Spec §1.2 make schema-dump: "No diff; missing or stale generated DDL
# fails."
schema-dump:
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

# Parameterized pack suite for sources, mappings, rights and dependency
# cascades. Spec §1.2 make conformance: "Every enabled pack passes; no
# rights broadening or silent missing dependency." Fails rather than
# reporting a pass: no conformance packs exist in this repo yet, and a
# target that exits 0 having run nothing is indistinguishable from a target
# that ran everything and it all passed -- the same defect test and golden
# were already fixed for. Must keep failing until real packs back it.
conformance:
	@echo "conformance: not implemented in Phase 1 (no packs exist)" && exit 1

# Spec §1.2 make test: "Unit and integration suites, including review,
# entitlement, outcome observation, provider slot, edge guard and billing
# independence." Fails rather than reporting a pass: none of core/,
# commerce/ or their test suites exist in this repo yet, and a target that
# exits 0 having run nothing is indistinguishable from a target that ran
# everything and it all passed. This must keep failing until a real suite
# backs it. (The database invariant suite does exist -- see `make db-test`.)
test:
	@echo "test: not implemented in Phase 1 (core/, commerce/ suites). Database invariants are covered separately -- see 'make db-test'." && exit 1

# Spec §1.2 make golden: "Normalized composed, partial, refused and
# geometry-disabled Base Core fixtures." P20: one of the four classes is
# real now -- refused, via scripts/check_golden.py and tests/golden/
# ca_san_jose/refused.json -- the other three are not (composed/partial
# would mean fabricating a licence clearance STANDING-BLOCKER.md says
# does not exist; geometry-disabled needs its own decision). This
# target's own exit code tracks ONLY the refused-path check's own
# correctness (0 = it passed, 1 = it failed) -- it does NOT mean "all
# four classes covered." scripts/check_golden.py prints the three
# missing classes explicitly on every single run, pass or fail -- see
# that script's own module docstring for the full argument against
# either silently inflating this to "done" or silently keeping it at
# an uninformative permanent exit 1.
golden:
	$(PYTHON) scripts/check_golden.py

clean:
	rm -rf dist build/__pycache__ $(SCHEMA_DUMP).tmp
