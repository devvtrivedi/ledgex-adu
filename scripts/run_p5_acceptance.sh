#!/usr/bin/env bash
# P5 acceptance run: zoning and permits, each A->B->A, separately, against
# parcels loaded once (constant throughout -- P5 does not touch parcels).
#
# Self-contained, same terms as P3's run_phaseb_acceptance.sh: computes
# every fixture's digest at run time, uploads to OBJECT_STORE_*, inserts
# its own snapshot rows and reference data (ON CONFLICT DO NOTHING) --
# works equally against a fresh migrations-only database or one already
# seeded. Run this three times to satisfy CONVENTIONS.md's suite
# discipline: twice against a seeded scratch DB, once against a fresh
# migrations-only DB with no seed.
set -euo pipefail
cd "$(dirname "$0")/.."

export OBJECT_STORE_URL="${OBJECT_STORE_URL:-http://localhost:19000}"
export OBJECT_STORE_ACCESS_KEY="${OBJECT_STORE_ACCESS_KEY:-scratchkey}"
export OBJECT_STORE_SECRET_KEY="${OBJECT_STORE_SECRET_KEY:-scratchsecret}"
export OBJECT_STORE_BUCKET="${OBJECT_STORE_BUCKET:-ledgex-snapshots-locked}"

FIXTURES="db/fixtures/p5"
PHASEB_FIXTURES="db/fixtures/phaseb"

echo "############################ SETUP (self-contained) ############################"
read -r PARCELS_SID ZONING_A_SID ZONING_B_SID PERMITS_A_SID PERMITS_B_SID <<< \
    "$(.venv-ingest/bin/python3 scripts/_p5_setup.py "$FIXTURES" "$PHASEB_FIXTURES")"

# ingest_zoning_permits.py's phase_zoning_load/phase_permits_load read from
# its own hardcoded SCRATCHPAD constant -- copy fixtures there under the
# exact filenames it expects, same pattern run_phaseb_acceptance.sh uses.
SCRATCHPAD_REAL=$(grep -o 'SCRATCHPAD = "[^"]*"' scripts/ingest_zoning_permits.py | head -1 | cut -d'"' -f2)
mkdir -p "$SCRATCHPAD_REAL"

echo "parcels snapshot: $PARCELS_SID"
echo "zoning A: $ZONING_A_SID   zoning B: $ZONING_B_SID"
echo "permits A: $PERMITS_A_SID   permits B: $PERMITS_B_SID"

echo ""
echo "############################ LOAD PARCELS (once, constant throughout) ############################"
.venv-ingest/bin/python3 scripts/ingest_parcels.py --phase e --snapshot-id "$PARCELS_SID"

echo ""
echo "############################ ZONING A / PERMITS A (baseline) ############################"
cp "$FIXTURES/p5_zoning_A.geojson" "$SCRATCHPAD_REAL/zoning_districts_fetch_1.geojson"
cp "$FIXTURES/p5_permits_A.csv" "$SCRATCHPAD_REAL/permits_fetch_1.csv"
.venv-ingest/bin/python3 scripts/ingest_zoning_permits.py --source zoning --phase load
.venv-ingest/bin/python3 scripts/ingest_zoning_permits.py --source permits --phase load

echo ""
echo "############################ ZONING B / PERMITS B (reconcile) ############################"
cp "$FIXTURES/p5_zoning_B.geojson" "$SCRATCHPAD_REAL/zoning_districts_fetch_1.geojson"
cp "$FIXTURES/p5_permits_B.csv" "$SCRATCHPAD_REAL/permits_fetch_1.csv"
.venv-ingest/bin/python3 scripts/ingest_zoning_permits.py --source zoning --phase load
.venv-ingest/bin/python3 scripts/ingest_zoning_permits.py --source permits --phase load

echo ""
echo "############################ ASSERTIONS -- after B ############################"
.venv-ingest/bin/python3 scripts/check_p5_acceptance.py after-b

echo ""
echo "############################ ZONING A2 / PERMITS A2 (reconcile back) ############################"
cp "$FIXTURES/p5_zoning_A.geojson" "$SCRATCHPAD_REAL/zoning_districts_fetch_1.geojson"
cp "$FIXTURES/p5_permits_A.csv" "$SCRATCHPAD_REAL/permits_fetch_1.csv"
.venv-ingest/bin/python3 scripts/ingest_zoning_permits.py --source zoning --phase load
.venv-ingest/bin/python3 scripts/ingest_zoning_permits.py --source permits --phase load

echo ""
echo "############################ ASSERTIONS -- after second A ############################"
.venv-ingest/bin/python3 scripts/check_p5_acceptance.py after-a2

echo ""
echo "############################ SAME-SNAPSHOT RE-RUN (core safety property) ############################"
.venv-ingest/bin/python3 scripts/ingest_zoning_permits.py --source zoning --phase load
.venv-ingest/bin/python3 scripts/ingest_zoning_permits.py --source permits --phase load
.venv-ingest/bin/python3 scripts/check_p5_acceptance.py after-a2

echo ""
echo "P5 ACCEPTANCE: ALL CHECKPOINTS PASSED"
