#!/usr/bin/env python3
"""make liveness -- P28: every active, ca_san_jose-owned source responds
with the fields jurisdictions/ca_san_jose/sources.yaml declares.

NOT an ingest, and NOT a fetch in C7's sense -- see
prompts/P28-liveness.md section 1 for the full argument. A liveness probe
reads at most PREFIX_BYTES of each response, never the complete artifact,
so it can never correctly compute a snapshot.content_hash (that would
either hash a truncated prefix and call it a content-address -- a claim
nothing durable backs -- or require a full fetch, which is exactly the
disallowed "225k-feature download as a liveness probe"). This script
writes NO snapshot row, ever. It writes a job_run row per source, per
run, using job_run.schema_drift for its own, already-declared meaning
("fields expected but missing" -- db/schema.sql's own COMMENT ON COLUMN,
0051) -- a real writer for a column that has had none since 0051 removed
its two improper ones.

Scope: only sources whose id starts with "ca_san_jose." AND whose pack
phase_status is "active" (the pack's own three: parcels, zoning_districts,
building_permits_active) are probed -- same precedent make conformance
(P26) already set for excluding sources with no known-good crosswalk or
endpoint. The two active federal sources (us_fema.nfhl, us_nrcs.soil_survey)
get a NOTE, not a probe -- no ingest script exists for either, so there is
no real endpoint constant or raw-key crosswalk to check against.

Endpoint URLs and the field_key -> raw key crosswalk are NOT read from the
live database (avoiding a repeat of P26's own found seeding-order bug --
two independent seed functions racing to populate the same source row).
They come directly from ingest_parcels.py/ingest_zoning_permits.py's own
already-real ENDPOINT_URL* constants, the single owner of this knowledge --
LIVENESS_FIELD_CHECKS below is this script's own small, explicit crosswalk,
cross-referenced against the exact line in each ingest script that reads
that same raw key (not field_map.yaml, which P26 deliberately left
undesigned -- see prompts/P28-liveness.md section 3).

Not push-gated -- scheduled (.github/workflows/liveness.yml), plus
workflow_dispatch for a manual run. See prompts/P28-liveness.md section 2
for the full argument (P12's "scheduled, non-blocking" rejection was about
an INTERNAL regression silently persisting; this checks an EXTERNAL
dependency this project cannot fix by reverting a commit).

Usage:
  DATABASE_URL=... python3 scripts/check_liveness.py

Exit code 0 = every probed source responded with every field it declares.
Exit code 1 = at least one probed source failed (unreachable, non-200, or
missing a declared field).
"""
import os
import sys

import psycopg2
import requests
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import ingest_parcels as ip  # noqa: E402
import ingest_zoning_permits as izp  # noqa: E402
from infra.env import get_db  # noqa: E402
from check_conformance import seed_reference_rows  # noqa: E402 -- reused, not duplicated: same jurisdiction/source FK rows make conformance already needs seeded on a fresh, migrations-only database

PACK_PATH = os.path.join(REPO_ROOT, "jurisdictions", "ca_san_jose", "sources.yaml")
JURISDICTION_PREFIX = "ca_san_jose."

PREFIX_BYTES = 262144  # 256 KiB -- see module docstring; never a full fetch
REQUEST_TIMEOUT = 15   # seconds -- P27: an external endpoint is exactly what hangs


def geojson_property(key):
    def check(buf):
        return f'"{key}"'.encode() in buf
    return check


def geojson_geometry_structural():
    def check(buf):
        return b'"geometry"' in buf and b'"type"' in buf
    return check


def csv_header_column(key):
    def check(buf):
        first_line = buf.split(b"\n", 1)[0]
        cols = [c.strip().strip(b'"') for c in first_line.split(b",")]
        return key.encode() in cols
    return check


# field_key -> callable(buf) -> bool. See module docstring for why this
# duplicates a small amount of knowledge already in the ingest scripts
# rather than importing a shared crosswalk that doesn't exist.
LIVENESS_FIELD_CHECKS = {
    ip.SOURCE_ID: {
        "parcel.apn": geojson_property("APN"),                    # ingest_parcels.py: props.get("APN")
        "parcel.geometry": geojson_geometry_structural(),         # ingest_parcels.py: feat["geometry"], GeoJSON structural member
        "parcel.source_parcel_id": geojson_property("PARCELID"),  # ingest_parcels.py: props.get("PARCELID")
    },
    izp.SOURCE_ID_ZONING: {
        "zoning.district": geojson_property("ZONING"),                    # ingest_zoning_permits.py: props.get("ZONING")
        "zoning.district_verbatim": geojson_property("ZONINGABBREV"),     # ingest_zoning_permits.py: props.get("ZONINGABBREV")
    },
    izp.SOURCE_ID_PERMITS: {
        # permits.active/permits.series_earliest are not literal columns --
        # see ingest_zoning_permits.py's load_permits() -- they are derived
        # from row presence and ISSUEDATE respectively. Checked here via the
        # two raw columns that derivation actually depends on.
        "permits.active": csv_header_column("ASSESSORS_PARCEL_NUMBER"),
        "permits.series_earliest": csv_header_column("ISSUEDATE"),
    },
}

ENDPOINT_URLS = {
    ip.SOURCE_ID: ip.ENDPOINT_URL,
    izp.SOURCE_ID_ZONING: izp.ENDPOINT_URL_ZONING,
    izp.SOURCE_ID_PERMITS: izp.ENDPOINT_URL_PERMITS,
}

failures = []


def load_pack():
    with open(PACK_PATH) as f:
        return yaml.safe_load(f)


def fetch_prefix(url):
    """Bounded GET: read at most PREFIX_BYTES then stop, whatever the
    server had left to send. Returns (status_code, bytes)."""
    with requests.get(url, stream=True, allow_redirects=True, timeout=REQUEST_TIMEOUT) as resp:
        status = resp.status_code
        buf = b""
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            buf += chunk
            if len(buf) >= PREFIX_BYTES:
                break
        return status, buf


def probe_source(conn, source_id, url, field_checks):
    print(f"\n[liveness] {source_id}: GET {url} (first {PREFIX_BYTES} bytes)")
    job_run_id = izp.start_job_run(conn, "liveness", source_id)
    try:
        status, buf = fetch_prefix(url)
    except requests.RequestException as e:
        izp.fail_job_run(conn, job_run_id, str(e))
        print(f"[FAIL] {source_id}: request error -- {e}")
        failures.append(source_id)
        return

    if status != 200:
        error = f"HTTP {status}"
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE job_run SET status = 'failed', finished_at = clock_timestamp(), error = %s WHERE id = %s",
                (error, job_run_id),
            )
        conn.commit()
        print(f"[FAIL] {source_id}: {error}")
        failures.append(source_id)
        return

    missing = [fk for fk, check in field_checks.items() if not check(buf)]
    if missing:
        import json
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE job_run
                SET status = 'failed', finished_at = clock_timestamp(),
                    error = %s, schema_drift = %s::jsonb
                WHERE id = %s
                """,
                (f"missing declared field(s): {missing}", json.dumps({"missing_fields": missing}), job_run_id),
            )
        conn.commit()
        print(f"[FAIL] {source_id}: responded 200 but missing declared field(s): {missing}")
        failures.append(source_id)
        return

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE job_run SET status = 'succeeded', finished_at = clock_timestamp() WHERE id = %s",
            (job_run_id,),
        )
    conn.commit()
    print(f"[PASS] {source_id}: 200, every declared field present in the first {len(buf):,} bytes")


def main():
    pack = load_pack()
    jurisdiction = pack["jurisdiction"]
    owned_active = [
        s for s in pack["sources"]
        if s["id"].startswith(JURISDICTION_PREFIX) and s.get("phase_status") == "active"
    ]
    other_active = [
        s for s in pack["sources"]
        if s.get("phase_status") == "active" and not s["id"].startswith(JURISDICTION_PREFIX)
    ]

    print(f"[liveness] pack: {jurisdiction} ({pack['pack_version']})")
    print(f"[liveness] probing {len(owned_active)} active, {jurisdiction}-owned source(s): "
          f"{[s['id'] for s in owned_active]}")
    for s in other_active:
        print(f"[liveness] NOTE: {s['id']} is active but not {jurisdiction}-owned -- "
              f"no ingest script or endpoint constant exists to probe it yet. Not covered.")

    conn = get_db()
    seed_reference_rows(conn)  # job_run.jurisdiction_id/source_id are FK-constrained; CI never runs db/seeds/
    for s in owned_active:
        source_id = s["id"]
        url = ENDPOINT_URLS.get(source_id)
        checks = LIVENESS_FIELD_CHECKS.get(source_id)
        if url is None or checks is None:
            print(f"[FAIL] {source_id}: declared active in the pack but this script has no "
                  f"endpoint/field-check entry for it -- treat as a real gap, not a pass.")
            failures.append(source_id)
            continue
        probe_source(conn, source_id, url, checks)
    conn.close()

    print("\n=== LIVENESS SUMMARY ===")
    print("NOT covered by this run (real gaps, not silently counted as passing):")
    print("  - non-active/non-ca_san_jose-owned sources in this pack (federal sources: NOTE only, above)")
    print("  - deep content validation beyond raw-key presence in the first "
          f"{PREFIX_BYTES:,} bytes (a field present but corrupted mid-file would not be caught)")
    if failures:
        print(f"\n{len(failures)} failure(s): {failures}")
    else:
        print(f"\nAll {len(owned_active)} probed source(s) passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
