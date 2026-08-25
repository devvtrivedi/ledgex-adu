#!/usr/bin/env bash
# P5 acceptance run: zoning and permits, each A->B->A, separately, against
# parcels loaded once (constant throughout -- P5 does not touch parcels).
#
# Self-contained, same terms as P3's run_phaseb_acceptance.sh: computes
# every fixture's digest at run time, uploads to OBJECT_STORE_*, inserts
# its own snapshot rows and reference data (ON CONFLICT DO NOTHING) --
# works equally against a fresh migrations-only database or one already
# seeded, THE FIRST TIME. Run this three times to satisfy CONVENTIONS.md's
# suite discipline: twice, EACH AGAINST ITS OWN FRESH DATABASE, plus once
# more against a fresh migrations-only DB with no seed -- three fresh
# databases total, never the same database run twice.
#
# NOT SAFE TO RERUN against an already-populated (post-run) database (P23,
# README finding #30): this script's own assertions (check_p5_acceptance.py)
# assert a first-run A->B->A shape; a completed run leaves the database
# already past that shape, and a second run against it produces a real
# failed assertion, not a false alarm -- reproduced directly, not assumed.
set -euo pipefail
cd "$(dirname "$0")/.."

# .venv-ingest/ is gitignored -- a developer's local virtualenv, not
# something a CI runner has. Same shape as the Makefile's PYTHON/PSQL/
# PG_DUMP overrides: default to the local convention, let the caller
# override it (P12: CI sets PYTHON=python3, whatever setup-python put on
# PATH after `pip install -r scripts/requirements.txt`).
PYTHON="${PYTHON:-.venv-ingest/bin/python3}"

# P56 Phase 2 (B3, prompts/P56-fixture-contamination-boundary.md sec 3): same
# reasoning as ACCEPTANCE_OBJECT_STORE_BUCKET -> OBJECT_STORE_BUCKET below --
# NOT a "${DATABASE_URL:-...}" fallback. .env unconditionally exports the
# real DATABASE_URL (a live remote database, README finding #43), and a
# developer who sourced .env for other work would have it already set before
# this script runs, silently defeating a same-named fallback -- finding #53's
# own mechanism, in miniature, for the database instead of the bucket. This
# suite is also NOT SAFE TO RERUN against a populated database (see this
# file's own header), so unlike GOLDEN_DATABASE_URL it has NO DEFAULT either
# -- a default would be correct once and silently wrong every run after.
# Reads its own P5_DATABASE_URL and exports DATABASE_URL FROM it (what
# _p5_setup.py and every function under test actually read), so every child
# process below -- including the inline heredocs -- inherits the correct
# target without being edited individually.
DATABASE_URL="$("$PYTHON" scripts/_acceptance_db_preflight.py P5_DATABASE_URL)"
export DATABASE_URL

export OBJECT_STORE_URL="${OBJECT_STORE_URL:-http://localhost:19000}"
export OBJECT_STORE_ACCESS_KEY="${OBJECT_STORE_ACCESS_KEY:-scratchkey}"
export OBJECT_STORE_SECRET_KEY="${OBJECT_STORE_SECRET_KEY:-scratchsecret}"

# P20, README finding #28: NOT "${OBJECT_STORE_BUCKET:-...}" -- .env
# unconditionally exports the real OBJECT_STORE_BUCKET
# (ledgex-snapshots-locked), and a developer who has sourced .env for
# other real work (real credentials live nowhere else) would have that
# value already set before this script ever runs, silently defeating a
# same-named fallback. ledgex-snapshots-locked is Object-Locked (WORM,
# COMPLIANCE mode, ~100yr retention, confirmed live in P19/P20) --
# permanently unrecoverable if fixture objects land there, not even by
# the account root. This script reads its OWN variable,
# ACCEPTANCE_OBJECT_STORE_BUCKET, and sets OBJECT_STORE_BUCKET (what
# _p5_setup.py and every function under test actually read) FROM it,
# overriding whatever a sourced .env already exported.
export OBJECT_STORE_BUCKET="${ACCEPTANCE_OBJECT_STORE_BUCKET:-ledgex-acceptance-scratch}"

# Create the scratch bucket if it doesn't exist yet -- same idempotent
# create-if-missing shape db.yml's own "Create the object store bucket"
# step already uses for ledgex-snapshots-ci, so a first-time bare
# invocation works instead of merely failing safe.
"$PYTHON" - <<PYEOF
import boto3, botocore.exceptions
s3 = boto3.client("s3", endpoint_url="$OBJECT_STORE_URL",
                   aws_access_key_id="$OBJECT_STORE_ACCESS_KEY",
                   aws_secret_access_key="$OBJECT_STORE_SECRET_KEY")
try:
    s3.create_bucket(Bucket="$OBJECT_STORE_BUCKET")
    print("bucket created: $OBJECT_STORE_BUCKET")
except botocore.exceptions.ClientError as e:
    if e.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
        raise
    print("bucket already exists: $OBJECT_STORE_BUCKET")
PYEOF

FIXTURES="db/fixtures/p5"
PHASEB_FIXTURES="db/fixtures/phaseb"

echo "############################ SETUP (self-contained) ############################"
# C22 (P59): same fix as run_phaseb_acceptance.sh -- `read ... <<< "$(cmd)"`
# does not propagate cmd's exit status under set -e; a crashing
# _p5_setup.py would previously go unnoticed, silently continuing with
# empty/wrong SID variables. Capture to a plain variable first.
setup_output="$($PYTHON scripts/_p5_setup.py "$FIXTURES" "$PHASEB_FIXTURES")"
read -r PARCELS_SID ZONING_A_SID ZONING_B_SID PERMITS_A_SID PERMITS_B_SID <<< "$setup_output"

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
$PYTHON scripts/ingest_parcels.py --phase e --snapshot-id "$PARCELS_SID"

echo ""
echo "############################ ZONING A / PERMITS A (baseline) ############################"
cp "$FIXTURES/p5_zoning_A.geojson" "$SCRATCHPAD_REAL/zoning_districts_fetch_1.geojson"
cp "$FIXTURES/p5_permits_A.csv" "$SCRATCHPAD_REAL/permits_fetch_1.csv"
$PYTHON scripts/ingest_zoning_permits.py --source zoning --phase load --snapshot-id "$ZONING_A_SID"
$PYTHON scripts/ingest_zoning_permits.py --source permits --phase load --snapshot-id "$PERMITS_A_SID"

echo ""
echo "############################ ZONING B / PERMITS B (reconcile) ############################"
cp "$FIXTURES/p5_zoning_B.geojson" "$SCRATCHPAD_REAL/zoning_districts_fetch_1.geojson"
cp "$FIXTURES/p5_permits_B.csv" "$SCRATCHPAD_REAL/permits_fetch_1.csv"
$PYTHON scripts/ingest_zoning_permits.py --source zoning --phase load --snapshot-id "$ZONING_B_SID"
$PYTHON scripts/ingest_zoning_permits.py --source permits --phase load --snapshot-id "$PERMITS_B_SID"

echo ""
echo "############################ ASSERTIONS -- after B ############################"
$PYTHON scripts/check_p5_acceptance.py after-b

echo ""
echo "############################ ZONING A2 / PERMITS A2 (reconcile back) ############################"
cp "$FIXTURES/p5_zoning_A.geojson" "$SCRATCHPAD_REAL/zoning_districts_fetch_1.geojson"
cp "$FIXTURES/p5_permits_A.csv" "$SCRATCHPAD_REAL/permits_fetch_1.csv"
$PYTHON scripts/ingest_zoning_permits.py --source zoning --phase load --snapshot-id "$ZONING_A_SID"
$PYTHON scripts/ingest_zoning_permits.py --source permits --phase load --snapshot-id "$PERMITS_A_SID"

echo ""
echo "############################ ASSERTIONS -- after second A ############################"
$PYTHON scripts/check_p5_acceptance.py after-a2

echo ""
echo "############################ SAME-SNAPSHOT RE-RUN (core safety property) ############################"
$PYTHON scripts/ingest_zoning_permits.py --source zoning --phase load --snapshot-id "$ZONING_A_SID"
$PYTHON scripts/ingest_zoning_permits.py --source permits --phase load --snapshot-id "$PERMITS_A_SID"
$PYTHON scripts/check_p5_acceptance.py after-a2

echo ""
echo "############################ SOURCE-SCOPE CONFLICT (finding #21) ############################"
# 58705049 is back at zoning.district = 'R-2' from ca_san_jose.zoning_districts
# (the A2/re-run state just checked above). Plant a second, live fact for the
# SAME (parcel, field) from a different real source (ca_san_jose.building_
# permits_active, already has a snapshot row from the PERMITS A/B loads above)
# -- then reload fixture B again and prove load_zoning's own source reconciles
# correctly even with a foreign source's live fact sitting on the same field.
$PYTHON - <<'PYEOF'
import os, sys
sys.path.insert(0, os.getcwd())
from infra.env import get_db

conn = get_db()
cur = conn.cursor()
cur.execute("""
    INSERT INTO fact (id, parcel_id, field_key, value, unit, local_verbatim, source_id,
                       source_url, layer_item_id, snapshot_id, method, retrieved_at,
                       source_published_at, source_cadence_stated, effective_from, effective_to,
                       recorded_at, superseded_at, licence_id, confidence, confidence_rule_id,
                       conflict, method_version, ruleset_version, pack_version, jurisdiction_id,
                       supersedes_fact_id, supersession_reason, source_asserted_as_of)
    SELECT gen_random_uuid(), f.parcel_id, f.field_key, '"R-3"'::jsonb, f.unit, f.local_verbatim,
           'ca_san_jose.building_permits_active', f.source_url, f.layer_item_id,
           (SELECT id FROM snapshot WHERE source_id = 'ca_san_jose.building_permits_active'
            ORDER BY fetched_at DESC LIMIT 1),
           f.method, f.retrieved_at, f.source_published_at, f.source_cadence_stated,
           f.effective_from, f.effective_to, now(), f.superseded_at, 'cc0', f.confidence,
           f.confidence_rule_id, f.conflict, f.method_version, f.ruleset_version, f.pack_version,
           f.jurisdiction_id, NULL, NULL, f.source_asserted_as_of
    FROM fact f JOIN parcel p ON p.id = f.parcel_id
    WHERE p.apn = '58705049' AND f.field_key = 'zoning.district' AND f.superseded_at IS NULL
""")
conn.commit()
conn.close()
PYEOF
cp "$FIXTURES/p5_zoning_B.geojson" "$SCRATCHPAD_REAL/zoning_districts_fetch_1.geojson"
$PYTHON scripts/ingest_zoning_permits.py --source zoning --phase load --snapshot-id "$ZONING_B_SID"
$PYTHON scripts/check_p5_acceptance.py after-source-scope

echo ""
echo "P5 ACCEPTANCE: ALL CHECKPOINTS PASSED"
