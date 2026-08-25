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
# db/seeds/day4_sources.sql) -- THE FIRST TIME. Per CONVENTIONS.md's suite
# discipline: run three times, EACH AGAINST ITS OWN FRESH DATABASE (two
# plus one fresh migrations-only), never the same database twice.
#
# NOT SAFE TO RERUN against an already-populated (post-run) database (P23,
# README finding #30): this is an A->B->A state-transition script, not an
# idempotent one -- a completed run leaves the database already past the
# final A-again state, and a second run crashes outright, reproduced
# directly: psycopg2.errors.UniqueViolation on
# parcel_exception_one_open_per_detector_reason_coalesced, not a soft
# assertion failure.
set -euo pipefail
cd "$(dirname "$0")/.."

# .venv-ingest/ is gitignored -- a developer's local virtualenv, not
# something a CI runner has. Same override pattern as run_p5_acceptance.sh
# (P12) and the Makefile's own PYTHON/PSQL/PG_DUMP.
PYTHON="${PYTHON:-.venv-ingest/bin/python3}"

# P56 Phase 2 (B3, prompts/P56-fixture-contamination-boundary.md sec 3): same
# reasoning as ACCEPTANCE_OBJECT_STORE_BUCKET -> OBJECT_STORE_BUCKET below --
# NOT a "${DATABASE_URL:-...}" fallback, and NO DEFAULT (unlike
# GOLDEN_DATABASE_URL): this suite is NOT SAFE TO RERUN against a populated
# database (see this file's own header), so a default would be correct once
# and silently wrong every run after. Reads its own PHASEB_DATABASE_URL and
# exports DATABASE_URL FROM it, so every child process below -- including the
# inline heredocs -- inherits the correct target without being edited
# individually.
DATABASE_URL="$("$PYTHON" scripts/_acceptance_db_preflight.py PHASEB_DATABASE_URL)"
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
# _phaseb_setup.py and every function under test actually read) FROM it,
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

FIXTURES="db/fixtures/phaseb"

echo "############################ SETUP (self-contained) ############################"
# C22 (P59): `read ... <<< "$(cmd)"` does NOT propagate cmd's exit status
# under `set -e` -- the exit status of the whole statement is read's own,
# which succeeds even on empty/partial input. A crashing _phaseb_setup.py
# would previously go unnoticed here, silently continuing with empty/
# wrong SID variables instead of aborting (reproduced in isolation: `set
# -euo pipefail; read -r A B <<< "$(false; echo x)"` does not exit
# nonzero). Capturing to a plain variable first is the standard fix --
# `var=$(cmd)` IS one of the cases set -e correctly propagates.
setup_output="$($PYTHON scripts/_phaseb_setup.py "$FIXTURES")"
read -r A_SID B_SID ZONING_SID PERMITS_SID <<< "$setup_output"

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
echo "zoning snapshot: $ZONING_SID"
echo "permits snapshot: $PERMITS_SID"

echo ""
echo "############################ LOAD A (first time) ############################"
$PYTHON scripts/ingest_parcels.py --phase e --snapshot-id "$A_SID"

echo ""
echo "############################ SEED ZONING (once) ############################"
$PYTHON scripts/ingest_zoning_permits.py --source zoning --phase load --snapshot-id "$ZONING_SID"

echo ""
echo "############################ SEED PERMITS (once) ############################"
$PYTHON scripts/ingest_zoning_permits.py --source permits --phase load --snapshot-id "$PERMITS_SID"

echo ""
echo "############################ LOAD B (reconcile) ############################"
$PYTHON scripts/ingest_parcels.py --phase e --snapshot-id "$B_SID"

echo ""
echo "############################ ASSERTIONS -- after B ############################"
A_SID="$A_SID" B_SID="$B_SID" $PYTHON scripts/check_phaseb_acceptance.py after-b

echo ""
echo "############################ SOURCE-SCOPE CONFLICT SETUP (finding #21) ############################"
# source_feature_id 568's real (ca_san_jose.parcels) live parcel.apn is
# currently B's successor value ('23712199'), just written by LOAD B above.
# Plant a second, live parcel.apn fact for the SAME parcel from a different
# real source (ca_san_jose.zoning_districts, already has a snapshot row from
# the SEED ZONING step above) holding a value that differs from BOTH the
# real source's current live value ('23712199') AND the value the real
# source is about to reconcile back to on the next reload ('23712112', A's
# value) -- '99999999FOREIGN'. Unlike load_zoning/load_permits' live-map dict
# comprehension (arbitrary LAST-wins overwrite on a key collision),
# changed_rows' LEFT JOIN keeps every row: with BOTH fa rows now satisfying
# the CASE's "differs from incoming" condition, pre-fix code's unfiltered
# join yields TWO rows in changed_rows for this one feature -- the real one
# (correctly detected as changed) AND the foreign one (whose fa.id belongs
# to a fact from a DIFFERENT source_id). The processing loop attempts to
# supersede fa.id on the foreign row too, which 0017/I4's
# fact_supersession_target_validate() trigger rejects outright (a fact may
# only supersede a prior fact from its OWN source_id) -- pre-fix code
# crashes the whole job_run instead of silently misreconciling. So LOAD A
# AGAIN below is the one that must reconcile the real source correctly with
# a foreign source's live fact sitting on the same field, not a fourth
# snapshot application invented just for this check.
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
    SELECT gen_random_uuid(), f.parcel_id, f.field_key, '"99999999FOREIGN"'::jsonb, f.unit,
           f.local_verbatim, 'ca_san_jose.zoning_districts', f.source_url, f.layer_item_id,
           (SELECT id FROM snapshot WHERE source_id = 'ca_san_jose.zoning_districts'
            ORDER BY fetched_at DESC LIMIT 1),
           f.method, f.retrieved_at, f.source_published_at, f.source_cadence_stated,
           f.effective_from, f.effective_to, now(), f.superseded_at, 'cc_by_4_0', f.confidence,
           f.confidence_rule_id, f.conflict, f.method_version, f.ruleset_version, f.pack_version,
           f.jurisdiction_id, NULL, NULL, f.source_asserted_as_of
    FROM source_feature_identity sfi
    JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'parcel.apn'
                AND f.source_id = 'ca_san_jose.parcels' AND f.superseded_at IS NULL
    WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = '568'
""")
conn.commit()
conn.close()
PYEOF

echo ""
echo "############################ LOAD A AGAIN (reconcile back) ############################"
$PYTHON scripts/ingest_parcels.py --phase e --snapshot-id "$A_SID"

echo ""
echo "############################ ASSERTIONS -- after second A ############################"
A_SID="$A_SID" B_SID="$B_SID" $PYTHON scripts/check_phaseb_acceptance.py after-a2

echo ""
echo "############################ ASSERTIONS -- source-scope conflict (finding #21) ############################"
A_SID="$A_SID" B_SID="$B_SID" $PYTHON scripts/check_phaseb_acceptance.py after-source-scope
