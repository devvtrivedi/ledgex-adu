"""P59 C13: api/main.py's GET /v1/exceptions must gate parcel_exception.detail
through the SAME rights implementation (core.rights.evaluate_rights_gate) the
facts route already uses, not serve licence-gated data values ungated.

Exercises api.main._gate_exception_details() directly against a fake cursor --
no live database. A live-DB integration test would have to toggle a real
ca_san_jose source's licence_channel row to prove the blocked branch, which
is impossible: licence_channel is immutable (0033, no UPDATE/DELETE), exactly
the property this repository's own tests must never route around. A fake
cursor lets both the allowed and blocked cases be asserted deterministically
without touching immutable rows -- same technique tests/core/test_rights.py
already established for C14.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import api.main as viewer  # noqa: E402


class _FakeExceptionsCursor:
    """source_by_id: {source_id: licence_id}. channel_rows: [(licence_id,
    channel, allowed), ...]. Handles exactly the two queries
    _gate_exception_details/evaluate_rights_gate issue, in order."""

    def __init__(self, source_by_id, channel_rows):
        self._source_by_id = source_by_id
        self._channel_rows = channel_rows
        self._result = []

    def execute(self, sql, params):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT id, licence_id FROM source"):
            (source_ids,) = params
            self._result = [
                (sid, self._source_by_id[sid]) for sid in source_ids if sid in self._source_by_id
            ]
        elif normalized.startswith("SELECT licence_id, allowed FROM licence_channel"):
            licence_ids, channel = params
            self._result = [
                (lic, allowed)
                for lic, ch, allowed in self._channel_rows
                if lic in licence_ids and ch == channel
            ]
        else:
            raise AssertionError(f"unexpected query in fake cursor: {sql!r}")

    def fetchall(self):
        return self._result


def _rows():
    return [
        {
            "id": "exc-blocked-1",
            "detector_key": "parcel_apn_unresolvable",  # -> ca_san_jose.parcels
            "detail": {"apn": "SENSITIVE-RAW-APN-1"},
        },
        {
            "id": "exc-allowed-1",
            "detector_key": "zoning_spatial_join_unresolvable",  # -> ca_san_jose.zoning_districts
            "detail": {"reason": "multiple_containing_polygons_agree", "zoning": "R-1"},
        },
        {
            "id": "exc-unmapped-1",
            "detector_key": "some_future_detector_not_yet_mapped",
            "detail": {"anything": "here"},
        },
    ]


def test_blocked_source_licence_redacts_detail():
    source_by_id = {
        "ca_san_jose.parcels": "test_licence_parcels_blocked",
        "ca_san_jose.zoning_districts": "test_licence_zoning_allowed",
    }
    channel_rows = [
        ("test_licence_parcels_blocked", "api", False),
        ("test_licence_zoning_allowed", "api", True),
    ]
    cur = _FakeExceptionsCursor(source_by_id, channel_rows)

    result = viewer._gate_exception_details(cur, _rows())
    by_id = {r["id"]: r for r in result}

    assert by_id["exc-blocked-1"]["detail"] == viewer.REDACTED_DETAIL
    assert by_id["exc-allowed-1"]["detail"] == {
        "reason": "multiple_containing_polygons_agree",
        "zoning": "R-1",
    }


def test_an7_new_detectors_are_mapped_and_gated():
    """A-N7 (P59C): parcel_centroid_not_interior and permit_attribution_lost
    (both new in P59) were missing from DETECTOR_KEY_SOURCE, so their detail
    was permanently redacted regardless of licence -- fail-closed, but their
    detail could never be served even to a caller a real licence allows.
    Proves both directions: served (gated) when the governing source's
    licence allows channel 'api', redacted when it does not."""
    source_by_id = {
        "ca_san_jose.parcels": "test_licence_parcels_allowed",
        "ca_san_jose.building_permits_active": "test_licence_permits_blocked",
    }
    channel_rows = [
        ("test_licence_parcels_allowed", "api", True),
        ("test_licence_permits_blocked", "api", False),
    ]
    rows = [
        {
            "id": "exc-centroid-1",
            "detector_key": "parcel_centroid_not_interior",
            "detail": {"reason": "centroid_not_interior_after_fallback"},
        },
        {
            "id": "exc-permit-1",
            "detector_key": "permit_attribution_lost",
            "detail": {"reason": "no_fresh_apn_match_this_run"},
        },
    ]
    cur = _FakeExceptionsCursor(source_by_id, channel_rows)

    result = viewer._gate_exception_details(cur, rows)
    by_id = {r["id"]: r for r in result}

    assert by_id["exc-centroid-1"]["detail"] == {"reason": "centroid_not_interior_after_fallback"}
    assert by_id["exc-permit-1"]["detail"] == viewer.REDACTED_DETAIL


def test_unmapped_detector_key_fails_closed():
    """A detector_key this route does not yet know how to map to a source
    must be redacted, not served ungated -- fail closed, never open."""
    source_by_id = {}
    channel_rows = []
    cur = _FakeExceptionsCursor(source_by_id, channel_rows)

    result = viewer._gate_exception_details(cur, _rows())
    by_id = {r["id"]: r for r in result}

    assert by_id["exc-unmapped-1"]["detail"] == viewer.REDACTED_DETAIL


_EXCEPTION_COLUMNS = [
    "id", "parcel_id", "jurisdiction_id", "type", "severity", "detector_key",
    "detector_version", "ruleset_version", "detail", "detected_at", "outcome",
    "resolved_at", "resolved_by", "resolution_notes", "reopened_from_id",
]


class _FakeRouteCursor(_FakeExceptionsCursor):
    """Extends _FakeExceptionsCursor to also serve get_exceptions()'s own
    listing query, with a real `.description` so _rows_as_dicts(cur) works
    unmodified -- this is what proves the ROUTE actually calls
    _gate_exception_details, not just that the helper works in isolation."""

    def __init__(self, source_by_id, channel_rows, exception_rows):
        super().__init__(source_by_id, channel_rows)
        self._exception_rows = exception_rows
        self.description = None

    def execute(self, sql, params):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT id, parcel_id, jurisdiction_id"):
            self.description = [(c,) for c in _EXCEPTION_COLUMNS]
            self._result = [tuple(row[c] for c in _EXCEPTION_COLUMNS) for row in self._exception_rows]
        else:
            self.description = None
            super().execute(sql, params)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur


def _exception_row(id_, detector_key, detail):
    return {
        "id": id_, "parcel_id": "00000000-0000-0000-0000-000000000000",
        "jurisdiction_id": "test_ca_san_jose", "type": "coverage_gap", "severity": "info",
        "detector_key": detector_key, "detector_version": "v1", "ruleset_version": None,
        "detail": detail, "detected_at": None, "outcome": "open",
        "resolved_at": None, "resolved_by": None, "resolution_notes": None,
        "reopened_from_id": None,
    }


def test_route_wiring_redacts_blocked_detail_end_to_end():
    """Calls api.main.get_exceptions() itself (not the helper) -- proves the
    route is actually wired to the gate, not merely that the gate works when
    called directly. Would go RED if the route's call to
    _gate_exception_details were ever removed or bypassed."""
    source_by_id = {"ca_san_jose.parcels": "test_licence_parcels_blocked"}
    channel_rows = [("test_licence_parcels_blocked", "api", False)]
    exception_rows = [
        _exception_row("exc-1", "parcel_apn_unresolvable", {"apn": "SENSITIVE-RAW-APN-1"})
    ]
    cur = _FakeRouteCursor(source_by_id, channel_rows, exception_rows)
    conn = _FakeConn(cur)

    response = viewer.get_exceptions(outcome="open", detector_key=None, detector_version=None, conn=conn)

    assert response["data"][0]["detail"] == viewer.REDACTED_DETAIL
    assert "SENSITIVE-RAW-APN-1" not in str(response)
