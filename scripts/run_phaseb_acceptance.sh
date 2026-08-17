#!/usr/bin/env bash
# Phase B acceptance run: load A, load B, load A again (plus a one-time
# zoning/permits baseline seed before B, so the disappearance cascade has
# real facts to react to).
#
# Self-contained: computes every fixture's digest from db/fixtures/phaseb/*
# at run time, uploads to OBJECT_STORE_*, and inserts its own snapshot
# rows -- nothing here is a hardcoded hash from a prior session. Requires
# DATABASE_URL pointed at an already-migrated database (any seeding is
# this script's own job: it inserts the minimal licence/jurisdiction/
# source/field_definition rows itself, ON CONFLICT DO NOTHING, so it works
# equally against a fresh migrations-only database or one already carrying
# db/seeds/day4_sources.sql).
set -euo pipefail
cd "$(dirname "$0")/.."

# .venv-ingest/ is gitignored -- a developer's local virtualenv, not
# something a CI runner has. Same override pattern as run_p5_acceptance.sh
# (P12) and the Makefile's own PYTHON/PSQL/PG_DUMP.
PYTHON="${PYTHON:-.venv-ingest/bin/python3}"

export OBJECT_STORE_URL="${OBJECT_STORE_URL:-http://localhost:19000}"
export OBJECT_STORE_ACCESS_KEY="${OBJECT_STORE_ACCESS_KEY:-scratchkey}"
export OBJECT_STORE_SECRET_KEY="${OBJECT_STORE_SECRET_KEY:-scratchsecret}"
export OBJECT_STORE_BUCKET="${OBJECT_STORE_BUCKET:-ledgex-snapshots-locked}"

FIXTURES="db/fixtures/phaseb"

echo "############################ SETUP (self-contained) ############################"
read -r A_SID B_SID <<< "$($PYTHON scripts/_phaseb_setup.py "$FIXTURES")"

# ingest_zoning_permits.py's phase_zoning_load/phase_permits_load read from
# its own hardcoded SCRATCHPAD constant (a pre-existing limitation of that
# script, not introduced here) -- copy the fixtures there under the exact
# filenames it expects.
SCRATCHPAD_REAL=$(grep -o 'SCRATCHPAD = "[^"]*"' scripts/ingest_zoning_permits.py | head -1 | cut -d'"' -f2)
mkdir -p "$SCRATCHPAD_REAL"
cp "$FIXTURES/phaseb_zoning.geojson" "$SCRATCHPAD_REAL/zoning_districts_fetch_1.geojson"
cp "$FIXTURES/phaseb_permits.csv" "$SCRATCHPAD_REAL/permits_fetch_1.csv"

echo "A snapshot: $A_SID"
echo "B snapshot: $B_SID"

echo ""
echo "############################ LOAD A (first time) ############################"
$PYTHON scripts/ingest_parcels.py --phase e --snapshot-id "$A_SID"

echo ""
echo "############################ SEED ZONING (once) ############################"
$PYTHON scripts/ingest_zoning_permits.py --source zoning --phase load

echo ""
echo "############################ SEED PERMITS (once) ############################"
$PYTHON scripts/ingest_zoning_permits.py --source permits --phase load

echo ""
echo "############################ LOAD B (reconcile) ############################"
$PYTHON scripts/ingest_parcels.py --phase e --snapshot-id "$B_SID"

echo ""
echo "############################ ASSERTIONS -- after B ############################"
A_SID="$A_SID" B_SID="$B_SID" $PYTHON scripts/check_phaseb_acceptance.py after-b

echo ""
echo "############################ LOAD A AGAIN (reconcile back) ############################"
$PYTHON scripts/ingest_parcels.py --phase e --snapshot-id "$A_SID"

echo ""
echo "############################ ASSERTIONS -- after second A ############################"
A_SID="$A_SID" B_SID="$B_SID" $PYTHON scripts/check_phaseb_acceptance.py after-a2
