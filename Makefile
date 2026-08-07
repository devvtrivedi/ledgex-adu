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

.PHONY: docs pdf site qa all clean check-boundary schema schema-dump db-test conformance test golden

# `all: qa pdf`'s ordering (qa before the docs regeneration pdf triggers) is
# not guaranteed under `make -j`: parallel make can start pdf's docs
# prerequisite while qa_check.py is still reading docs/*.md, racing a
# rewrite against a read. This project has no target that benefits from
# parallel execution, so parallelism is disabled outright rather than
# chasing individual targets that would break under it.
.NOTPARALLEL:

PYTHON         ?= python3
PG_DUMP        ?= pg_dump
PSQL           ?= psql
MIGRATIONS_DIR := db/migrations
SCHEMA_DUMP    := db/schema.sql
DATABASE_URL   ?= postgresql://localhost/ledgex_schema_check

# pg_dump >=16.10 wraps every dump in a \restrict/\unrestrict pair keyed by a
# fresh random token each run (a psql safety marker, unrelated to schema
# content). Left random, schema-dump would show a diff every single run even
# with zero schema changes. Pinning it makes the dump byte-reproducible so
# "no diff" actually means no diff. Must be alphanumeric only.
PG_DUMP_RESTRICT_KEY ?= ledgexschemadumpfixedkey

# Regenerate the markdown files of record from build/ledgex_source.py and
# text/*.txt. Never hand-edit docs/LEDGEX_SPEC.md or docs/LEDGEX_RULES.md.
docs:
	$(PYTHON) build/build_spec_v1_11.py
	$(PYTHON) build/build_rules_v1_4.py

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
# Track B no-render checks." None of that infrastructure (core/, commerce/,
# .graphify/) exists in this repo yet, so this currently only runs the
# document QA gate — the one piece of check-boundary's scope (I17,
# filesystem authority) that's implemented so far.
check-boundary:
	$(PYTHON) build/qa_check.py

# Apply every forward-only migration to an empty database, in order.
# Spec §1.2 make schema: "Clean apply; constraints, functions and triggers
# compile."
schema:
	@command -v $(PSQL) >/dev/null 2>&1 || { echo "$(PSQL) not found — install PostgreSQL 16 client tools"; exit 1; }
	@for f in $(MIGRATIONS_DIR)/*.sql; do \
		echo "applying $$f"; \
		$(PSQL) "$(DATABASE_URL)" -v ON_ERROR_STOP=1 -f "$$f" || exit 1; \
	done

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
db-test:
	@command -v $(PSQL) >/dev/null 2>&1 || { echo "$(PSQL) not found"; exit 1; }
	$(PSQL) "$(DATABASE_URL)" -v ON_ERROR_STOP=1 -f db/tests/invariants.sql

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
# geometry-disabled Base Core fixtures." Fails rather than reporting a pass:
# the composer and tests/golden/ca_san_jose fixtures don't exist in this
# repo yet. Must keep failing until a real fixture suite backs it.
golden:
	@echo "golden: not implemented in Phase 1" && exit 1

clean:
	rm -rf dist build/__pycache__ $(SCHEMA_DUMP).tmp
