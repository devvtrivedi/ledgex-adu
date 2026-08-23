#!/usr/bin/env python3
"""P55 Phase 2 -- T1-T4, T7, T9: the scoped-unblock acceptance tests.

Asserts against REBUILT REAL DATA (ledgex_schema_check or ledgex_smoke, via
DATABASE_URL -- the same env-var convention every other script here uses),
never a synthetic fixture. scripts/test_viewer_rights_gate.py owns the P42
internal_test.* fixture; this file is deliberately separate, per Phase 2
Stage 1's own instruction, because folding the two would make a real-data
assertion look interchangeable with a synthetic one.

Route functions (api.main.get_parcel_facts, api.main.get_rights) are called
directly, as plain Python -- same convention scripts/test_viewer_rights_gate.py
already uses, for the same reason (no httpx/TestClient dependency needed to
reach code this script can call in-process).

T9 is the odd one out: it calls scripts/smoke_real.py's own step functions
directly against SMOKE_DATABASE_URL, independently of `make smoke-real`'s
full 15-step run (which also needs Docker/MinIO/network/a live viewer
process on :8420) -- see T9's own docstring below for what that does and
does not require.

RED-FIRST: this file is expected to fail loudly, for named reasons, against
the pre-Phase-2 database. That failure transcript is Phase 2 Stage 1's own
required evidence, captured before any implementation exists.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from infra.env import get_db  # noqa: E402
import api.main as viewer  # noqa: E402
from core.rights import KNOWN_CHANNELS  # noqa: E402

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


NEW_CC_BY = "cc_by_4_0_api_2026_08"
NEW_CC0 = "cc0_api_2026_08"
OLD_IDS = ("cc_by_4_0", "cc0")


def test_T1_existing_facts_become_viewable():
    """C3's acceptance test. Checked in the order Phase 1's corrections pass
    found most likely to fail silently: ingest constants first (a rebuild
    that ran without updating them reproduces 1.1M facts under the OLD ids
    and every check below would fail for a confusing, expensive-to-diagnose
    reason), then source.licence_id, then the licence_channel row, then --
    only once those hold -- the actual viewer-visibility assertion."""
    conn = get_db()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM fact WHERE licence_id IN (%s, %s)",
            (NEW_CC_BY, NEW_CC0),
        )
        new_id_fact_count = cur.fetchone()[0]
    check(
        "ingest constants updated: at least one fact cites a new licence id",
        new_id_fact_count > 0,
        f"0 facts cite {NEW_CC_BY!r} or {NEW_CC0!r} -- scripts/ingest_parcels.py:88 "
        f"LICENCE_ID / scripts/ingest_zoning_permits.py:134,141 were not updated before "
        f"the rebuild's re-ingest step (design §4.5 step 9), or the rebuild has not run.",
    )

    with conn.cursor() as cur:
        cur.execute("SELECT licence_id FROM source WHERE id = 'ca_san_jose.parcels'")
        row = cur.fetchone()
    check(
        "source.licence_id repointed (ca_san_jose.parcels)",
        row is not None and row[0] == NEW_CC_BY,
        f"got {row} -- design §4.5 step 8",
    )

    with conn.cursor() as cur:
        cur.execute(
            "SELECT allowed FROM licence_channel WHERE licence_id = %s AND channel = 'api'",
            (NEW_CC_BY,),
        )
        row = cur.fetchone()
    check(
        f"licence_channel ({NEW_CC_BY!r}, 'api') exists and allowed=true",
        row is not None and row[0] is True,
        f"got {row} -- design §4.3/§4.4, or db/seeds/day4_sources.sql was not (re)applied",
    )

    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.id FROM parcel p JOIN current_fact_at(now()) cf ON cf.parcel_id = p.id "
            "WHERE p.jurisdiction_id = 'ca_san_jose' AND cf.field_key = 'parcel.apn' "
            "ORDER BY p.apn LIMIT 1"
        )
        row = cur.fetchone()
    if row is None:
        check(
            "a ca_san_jose parcel with a current parcel.apn fact exists",
            False,
            "none found -- has the rebuild (design §4.5) actually run against this "
            "database (DATABASE_URL)?",
        )
        conn.close()
        return

    parcel_id = str(row[0])
    result = viewer.get_parcel_facts(parcel_id, as_of=None, conn=conn)
    facts_keys = {f["field_key"] for f in result["facts"]}
    check(
        "parcel.apn is in facts[], not omitted_for_rights[] (C3)",
        "parcel.apn" in facts_keys,
        f"omitted_for_rights={result['omitted_for_rights']}",
    )
    check(
        "parcel.geometry is in facts[], not omitted_for_rights[] (C3)",
        "parcel.geometry" in facts_keys,
        f"omitted_for_rights={result['omitted_for_rights']}",
    )
    conn.close()


def test_T2_diligence_independence():
    """C1's guard, the single most important test in this file: opening a
    channel must never be conflatable with diligence being complete. Two
    independent routes to the same fact -- the API surface a real consumer
    would see, and the database directly -- because a bug that fabricates
    cleared_by only on one of those paths (e.g. a copy-paste of
    seed_internal_test_licences.py's own cleared_by='internal_test_seed'
    pattern into the real seed) should be caught by at least one."""
    conn = get_db()
    for lic_id in (NEW_CC_BY, NEW_CC0):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cleared_by, cleared_at, evidence_uri FROM licence WHERE id = %s",
                (lic_id,),
            )
            row = cur.fetchone()
        if row is None:
            check(f"licence row {lic_id!r} exists", False, "not seeded yet")
            continue
        cleared_by, cleared_at, evidence_uri = row
        check(f"{lic_id}: licence.cleared_by IS NULL", cleared_by is None, f"got {cleared_by!r}")
        check(f"{lic_id}: licence.cleared_at IS NULL", cleared_at is None, f"got {cleared_at!r}")
        check(f"{lic_id}: licence.evidence_uri IS NULL", evidence_uri is None, f"got {evidence_uri!r}")

        rights = viewer.get_rights(conn=conn)
        api_row = next(
            (r for r in rights["data"] if r["licence_id"] == lic_id and r["channel"] == "api"),
            None,
        )
        check(
            f"{lic_id}: GET /v1/rights diligence == 'written_confirmation_pending' for channel 'api'",
            api_row is not None and api_row["diligence"] == "written_confirmation_pending",
            f"got {api_row}",
        )
    conn.close()


def test_T3_channel_scope():
    """Negative control, C2's channel guard: 'api' alone is allowed=true for
    each new licence id; the other five channels stay allowed=false."""
    conn = get_db()
    for lic_id in (NEW_CC_BY, NEW_CC0):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT channel, allowed FROM licence_channel WHERE licence_id = %s",
                (lic_id,),
            )
            rows = dict(cur.fetchall())
        check(
            f"{lic_id}: exactly channel 'api' allowed=true, all other {len(KNOWN_CHANNELS) - 1} false",
            rows.get("api") is True
            and all(rows.get(ch) is False for ch in KNOWN_CHANNELS if ch != "api"),
            f"got {rows}",
        )
    conn.close()


def test_T4_source_scope_unaffected():
    """Negative control, C2's source guard: opening the two new licence ids
    must not widen evaluate_rights_gate's behaviour for any OTHER licence.
    The gate reads licence_channel per-id so this structurally cannot
    happen -- this test exists to prove that empirically rather than assume
    it, using the OLD cc_by_4_0/cc0 rows (still seeded, per §4.8, orphaned
    forever) as the licences that must remain untouched."""
    conn = get_db()
    for lic_id in OLD_IDS:
        with conn.cursor() as cur:
            cur.execute("SELECT allowed FROM licence_channel WHERE licence_id = %s", (lic_id,))
            rows = [r[0] for r in cur.fetchall()]
        check(
            f"{lic_id} (old id, untouched): every licence_channel row still allowed=false",
            len(rows) == 6 and all(r is False for r in rows),
            f"got {rows}",
        )
    conn.close()


def test_T7_attribution_banner():
    """Q5: the banner is built, not deferred. Two checks: the rendering
    logic exists in the template (grepped, not executed -- this repo's own
    established viewer-testing style, see scripts/test_viewer_rights_gate.py's
    own docstring for why no browser/HTTP harness is used here), and the
    value it would render is actually available from the API it reads from
    (§6.6: 'the same attribution_text the Rights tab already fetches')."""
    # A marker unique to the Stage 3 Facts-tab banner, chosen before Stage 3
    # exists specifically so this check cannot pass by coincidence the way a
    # loose substring count on "attribution" already did once (the existing
    # Rights-tab line at viewer.html:205 contains that substring twice on
    # its own -- 'attribution' the literal, attribution_text the field --
    # and a >=2 threshold passed against it before any banner existed).
    viewer_html_path = os.path.join(REPO_ROOT, "api", "static", "viewer.html")
    with open(viewer_html_path, "r") as f:
        html = f.read()
    check(
        "viewer.html's Facts tab contains the id=\"facts-attribution-banner\" element (§6.6)",
        'id="facts-attribution-banner"' in html,
        "not found -- §6.6 banner not built yet",
    )

    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT restriction, attribution_text FROM licence WHERE id = %s", (NEW_CC_BY,)
        )
        row = cur.fetchone()
    conn.close()
    check(
        f"{NEW_CC_BY}: restriction='attribution' and attribution_text is set (source for the banner)",
        row is not None and row[0] == "attribution" and row[1],
        f"got {row}",
    )


def test_T9_smoke_step15_two_sided():
    """The re-scoped step 15's own two-sided assertion (design §11), run
    directly against SMOKE_DATABASE_URL -- independently of `make
    smoke-real`'s full 15-step run. Still requires real infrastructure this
    call does NOT set up for you: a already-loaded ledgex_smoke database
    (steps 1-12) and a viewer process bound to it on :8420 (or
    LEDGEX_VIEWER_URL) -- if either is missing this fails loudly by name,
    which is itself correct: this is a regression test for step 15's own
    logic, not a replacement for `make smoke-real`."""
    import smoke_real  # noqa: E402  -- scripts/ is on sys.path via REPO_ROOT/scripts below

    smoke_url = os.environ.get("SMOKE_DATABASE_URL") or smoke_real.DEFAULT_SMOKE_DB
    viewer_url = (os.environ.get("LEDGEX_VIEWER_URL") or smoke_real.DEFAULT_VIEWER).rstrip("/")

    import psycopg2
    try:
        conn = psycopg2.connect(smoke_url)
    except Exception as e:
        check("connect to SMOKE_DATABASE_URL", False, f"{e} -- run `make smoke-real` first")
        return
    conn.autocommit = False
    ctx = {"conn": conn, "viewer": viewer_url}

    try:
        detail13 = smoke_real.step_query_sql(ctx)
        print(f"     (step 13 reused) {detail13}")
        detail14 = smoke_real.step_query_viewer(ctx)
        print(f"     (step 14 reused) {detail14}")
    except smoke_real.StepFailed as e:
        check("steps 13-14 (prerequisites for step 15) succeed", False, str(e))
        conn.close()
        return

    try:
        result = smoke_real.step_rights_gate(ctx)
    except smoke_real.StepFailed as e:
        check("step 15 (re-scoped) does not raise StepFailed", False, str(e))
        conn.close()
        return
    detail = result[1] if isinstance(result, tuple) else result
    status = result[0] if isinstance(result, tuple) else smoke_real.PASS
    check(
        "step 15 returns PASS, not SKIP (0.4: SKIP must be eliminated)",
        status == smoke_real.PASS,
        f"got status={status!r}, detail={detail!r}",
    )
    check(
        "step 15's own detail names both directions (allowed AND blocked)",
        isinstance(detail, str) and "allowed" in detail.lower() and "blocked" in detail.lower(),
        f"got {detail!r}",
    )
    conn.close()


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    tests = [
        test_T1_existing_facts_become_viewable,
        test_T2_diligence_independence,
        test_T3_channel_scope,
        test_T4_source_scope_unaffected,
        test_T7_attribution_banner,
        test_T9_smoke_step15_two_sided,
    ]
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        t()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)
