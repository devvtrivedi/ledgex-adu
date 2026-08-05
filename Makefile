# LedgeX / ADU.X
# Source of record: docs/LEDGEX_SPEC.md. See §1.2 for the six make targets
# this project treats as its CI gate, and §3.13 for migration conventions.
#
# schema / schema-dump / conformance require a running PostgreSQL 16 +
# PostGIS 3.4 instance reachable at DATABASE_URL. They are not exercised by
# `make all`, which only needs Python.

.PHONY: docs pdf qa all schema schema-dump conformance clean

PYTHON         ?= python3
MIGRATIONS_DIR := db/migrations
SCHEMA_DUMP    := db/schema.sql
DATABASE_URL   ?= postgresql://localhost/ledgex_schema_check

# Regenerate the markdown files of record from build/ledgex_source.py and
# text/*.txt. Never hand-edit docs/LEDGEX_SPEC.md or docs/LEDGEX_RULES.md.
docs:
	$(PYTHON) build/build_spec_v1_7.py
	$(PYTHON) build/build_rules_v1_4.py

# Presentation artifact rendered from the regenerated markdown. No-ops with
# exit 0 if pandoc isn't installed — the markdown is the file of record.
pdf: docs
	$(PYTHON) build/make_pdf.py

# Document QA — the drift gate. Fails on missing/duplicated invariants,
# mangled prose duplicates, or a stale (hand-edited) generated file.
qa:
	$(PYTHON) build/qa_check.py

all: docs qa

# Apply every forward-only migration to an empty database, in order.
# Spec §1.2 make schema: "Clean apply; constraints, functions and triggers
# compile."
schema:
	@command -v psql >/dev/null 2>&1 || { echo "psql not found — install PostgreSQL 16 client tools"; exit 1; }
	@for f in $(MIGRATIONS_DIR)/*.sql; do \
		echo "applying $$f"; \
		psql "$(DATABASE_URL)" -v ON_ERROR_STOP=1 -f "$$f" || exit 1; \
	done

# Regenerate db/schema.sql from whatever schema is live at DATABASE_URL and
# diff it against the committed dump. Run `make schema` against an empty
# database first for a true "clean apply" dump.
# Spec §1.2 make schema-dump: "No diff; missing or stale generated DDL
# fails."
schema-dump:
	@command -v pg_dump >/dev/null 2>&1 || { echo "pg_dump not found — install PostgreSQL 16 client tools"; exit 1; }
	pg_dump "$(DATABASE_URL)" --schema-only --no-owner --no-privileges > $(SCHEMA_DUMP).tmp
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

# Parameterized pack suite for sources, mappings, rights and dependency
# cascades. Spec §1.2 make conformance: "Every enabled pack passes; no
# rights broadening or silent missing dependency."
conformance:
	@if [ -d tests/conformance ]; then \
		$(PYTHON) -m pytest tests/conformance -q; \
	else \
		echo "tests/conformance does not exist yet — no conformance packs to run."; \
	fi

clean:
	rm -rf dist build/__pycache__ $(SCHEMA_DUMP).tmp
