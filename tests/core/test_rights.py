"""P59: core/rights.evaluate_rights_gate() -- C18 (fails open on a one-shot
iterator) and C14 (the channel dimension is guarded by row order, not by
assertion).

Both tests exercise the real evaluate_rights_gate() function against a fake
cursor -- deliberately, not a live database. C14 in particular needs to be
ordering-independent: LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md's own residue is
that a live Postgres fetchall() never happens to return the one allowed=true
row last under any realistic query plan, so a live-DB version of this test
would pass today for the same accidental reason the audit flagged. _FakeCursor
instead inspects the actual SQL text evaluate_rights_gate() executes: if the
"AND channel = %s" predicate is present, it filters server-side by channel
(what a real, correct query does); if the predicate has been deleted, it
returns every channel row for the touched licences in a fixed order chosen so
that Python's last-write-wins dict comprehension in evaluate_rights_gate()
produces the WRONG (unblocked) answer -- deterministic on every run, no
database required.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.rights import evaluate_rights_gate  # noqa: E402


class _FakeCursor:
    """Simulates licence_channel's real columns (licence_id, channel,
    allowed) without a database. execute()'s SQL text decides whether the
    channel predicate was honored -- see module docstring."""

    def __init__(self, rows):
        self._rows = rows  # [(licence_id, channel, allowed), ...]
        self._result = []

    def execute(self, sql, params):
        normalized = " ".join(sql.split())
        channel_filtered = "channel = %s" in normalized or "channel=%s" in normalized
        # Real psycopg2 requires params to match the SQL's own placeholder
        # count -- a predicate deletion that leaves the channel param behind
        # would error before ever reaching a real database, so a faithful
        # mutation drops both together. Unpack defensively so this fake
        # mirrors that: with the predicate gone, only licence_ids travels.
        if channel_filtered:
            licence_ids, channel = params
        else:
            licence_ids = params[0]
        if channel_filtered:
            self._result = [
                (lic, allowed)
                for lic, ch, allowed in self._rows
                if lic in licence_ids and ch == channel
            ]
        else:
            # What removing the predicate actually does: every channel row
            # for the touched licences comes back. Fixed order (not shuffled)
            # so the test is deterministic: the allowed=true row for a
            # different channel is placed LAST, which is exactly the
            # last-write-wins shape the audit's C14 finding names.
            self._result = [
                (lic, allowed)
                for lic, ch, allowed in self._rows
                if lic in licence_ids
            ]

    def fetchall(self):
        return self._result


def test_c14_channel_predicate_blocks_when_only_other_channel_allowed():
    """Fixture licence: the REQUESTED channel ('api') is allowed=false; a
    DIFFERENT channel ('bulk_export') is allowed=true. With the channel
    predicate intact, evaluate_rights_gate must block on 'api' regardless of
    what the licence permits elsewhere -- exactly I6's per-channel gate."""
    rows = [
        ("test_licence_c14", "api", False),
        ("test_licence_c14", "bulk_export", True),
    ]
    touched = [("fact-1", "zoning.district", "test_licence_c14", "R-1")]
    cur = _FakeCursor(rows)

    allowed_by_licence, blocked_by_licence = evaluate_rights_gate(cur, touched, "api")

    assert allowed_by_licence.get("test_licence_c14") is False
    assert blocked_by_licence == {"test_licence_c14": ["zoning.district"]}


def test_c18_generator_input_blocks_identically_to_list_input():
    """A one-shot iterator (e.g. a generator) must produce the same blocking
    decision as the equivalent list -- the audit found the pre-fix function
    silently returned blocked_by_licence == {} (fail OPEN) for a generator
    because touched was consumed by the first of its two passes."""
    rows = [("test_licence_c18", "api", False)]
    touched_rows = [("fact-1", "zoning.district", "test_licence_c18", "R-1")]

    list_allowed, list_blocked = evaluate_rights_gate(
        _FakeCursor(rows), list(touched_rows), "api"
    )
    gen_allowed, gen_blocked = evaluate_rights_gate(
        _FakeCursor(rows), (row for row in touched_rows), "api"
    )

    assert list_blocked == gen_blocked
    assert gen_blocked == {"test_licence_c18": ["zoning.district"]}
