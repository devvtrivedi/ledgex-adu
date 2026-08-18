"""RED-first shape tests for core/model.py (P21). No database needed --
every constraint here is a single-row Pydantic validation, mirroring a
real DB CHECK constraint (named in each test) but checkable in isolation.
Cross-row checks (fact_supersession_target_validate, fact_one_current_per_source,
licence-channel gates) are NOT here -- core/model.py's own docstring
explains why a Pydantic model cannot see other rows.

Each constraint gets a positive control (the valid shape is accepted) and
a negative control (the specific violation is rejected, and ONLY for the
reason under test -- pytest.raises(ValidationError) alone would also
pass if some unrelated field were wrong, so the negative controls below
that share a constructor with a positive control change exactly one
field from it).
"""
import datetime
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.model import (  # noqa: E402
    REFUSAL_CODES,
    Fact,
    Licence,
    ParcelException,
    Parcel,
    Refusal,
    Result,
    Source,
)

NOW = datetime.datetime.now(datetime.timezone.utc)
PARCEL_ID = "11111111-1111-1111-1111-111111111111"


def _retrieved_fact_kwargs(**overrides):
    kwargs = dict(
        parcel_id=PARCEL_ID,
        jurisdiction_id="test_jurisdiction",
        field_key="test.field",
        value='"v"',  # pre-encoded JSON text -- Fact.value, design decision (c) [P22]
        method="direct",
        source_id="test.source",
        source_url="https://example.com",
        snapshot_id="test.source:sha256:" + "0" * 64,
        retrieved_at=NOW,
        effective_from=NOW,
        licence_id="test.licence",
        confidence="high",
        confidence_rule_id="rule_1",
        pack_version="v1.0",
    )
    kwargs.update(overrides)
    return kwargs


def _derived_fact_kwargs(**overrides):
    kwargs = dict(
        parcel_id=PARCEL_ID,
        jurisdiction_id="test_jurisdiction",
        field_key="test.field",
        value='"v"',  # pre-encoded JSON text -- Fact.value, design decision (c) [P22]
        method="derived",
        method_version="v1",
        effective_from=NOW,
        licence_id="test.licence",
        confidence="high",
        confidence_rule_id="rule_1",
        pack_version="v1.0",
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# Fact -- fact_provenance_complete (0006, I2)
# ---------------------------------------------------------------------------


class TestFactProvenanceComplete:
    def test_retrieved_fact_with_full_provenance_accepted(self):
        Fact(**_retrieved_fact_kwargs())

    def test_derived_fact_with_method_version_accepted(self):
        Fact(**_derived_fact_kwargs())

    def test_retrieved_fact_missing_source_id_rejected(self):
        with pytest.raises(ValidationError, match="source_id and snapshot_id"):
            Fact(**_retrieved_fact_kwargs(source_id=None))

    def test_retrieved_fact_missing_snapshot_id_rejected(self):
        with pytest.raises(ValidationError, match="source_id and snapshot_id"):
            Fact(**_retrieved_fact_kwargs(snapshot_id=None))

    def test_retrieved_fact_missing_retrieved_at_rejected(self):
        with pytest.raises(ValidationError, match="retrieved_at and source_url"):
            Fact(**_retrieved_fact_kwargs(retrieved_at=None))

    def test_retrieved_fact_missing_source_url_rejected(self):
        with pytest.raises(ValidationError, match="retrieved_at and source_url"):
            Fact(**_retrieved_fact_kwargs(source_url=None))

    def test_derived_fact_missing_method_version_rejected(self):
        with pytest.raises(ValidationError, match="method_version"):
            Fact(**_derived_fact_kwargs(method_version=None))

    def test_derived_fact_with_source_id_rejected(self):
        with pytest.raises(ValidationError, match="must not carry source_id"):
            Fact(**_derived_fact_kwargs(source_id="test.source"))

    def test_derived_fact_with_snapshot_id_rejected(self):
        with pytest.raises(ValidationError, match="must not carry source_id"):
            Fact(**_derived_fact_kwargs(snapshot_id="test.source:sha256:" + "0" * 64))


# ---------------------------------------------------------------------------
# Fact.value's encoding contract -- P22, design decision (c). Formalizes the
# five-case reproduction recorded in core/model.py's own module docstring;
# see that docstring for why value is str, not Any, and why a native
# bool/dict/None each fail differently without it.
# ---------------------------------------------------------------------------


class TestFactValueEncoding:
    def test_pre_encoded_json_string_accepted(self):
        f = Fact(**_retrieved_fact_kwargs(value='"some val"'))
        assert f.value == '"some val"'

    def test_native_bool_rejected(self):
        with pytest.raises(ValidationError, match="value"):
            Fact(**_retrieved_fact_kwargs(value=True))

    def test_native_str_that_is_not_valid_json_rejected(self):
        with pytest.raises(ValidationError, match="must be valid JSON text"):
            Fact(**_retrieved_fact_kwargs(value="hello"))

    def test_native_dict_rejected(self):
        with pytest.raises(ValidationError, match="value"):
            Fact(**_retrieved_fact_kwargs(value={"a": 1}))

    def test_none_rejected(self):
        with pytest.raises(ValidationError, match="value"):
            Fact(**_retrieved_fact_kwargs(value=None))


# ---------------------------------------------------------------------------
# Fact -- the other single-row CHECKs
# ---------------------------------------------------------------------------


class TestFactOtherConstraints:
    def test_valid_time_ordered_accepted(self):
        Fact(**_retrieved_fact_kwargs(effective_to=NOW + datetime.timedelta(days=1)))

    def test_valid_time_equal_rejected(self):
        with pytest.raises(ValidationError, match="fact_valid_time"):
            Fact(**_retrieved_fact_kwargs(effective_to=NOW))

    def test_valid_time_before_rejected(self):
        with pytest.raises(ValidationError, match="fact_valid_time"):
            Fact(**_retrieved_fact_kwargs(effective_to=NOW - datetime.timedelta(days=1)))

    def test_supersession_pair_both_set_accepted(self):
        Fact(**_retrieved_fact_kwargs(
            supersedes_fact_id="22222222-2222-2222-2222-222222222222",
            supersession_reason="world_change",
        ))

    def test_supersession_pair_both_null_accepted(self):
        Fact(**_retrieved_fact_kwargs())

    def test_supersession_id_without_reason_rejected(self):
        with pytest.raises(ValidationError, match="fact_supersession_reason_biconditional"):
            Fact(**_retrieved_fact_kwargs(supersedes_fact_id="22222222-2222-2222-2222-222222222222"))

    def test_supersession_reason_without_id_rejected(self):
        with pytest.raises(ValidationError, match="fact_supersession_reason_biconditional"):
            Fact(**_retrieved_fact_kwargs(supersession_reason="world_change"))

    def test_method_outside_i13_automated_set_rejected(self):
        with pytest.raises(ValidationError):
            Fact(**_retrieved_fact_kwargs(method="portal"))


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


def _active_source_kwargs(**overrides):
    kwargs = dict(
        id="test.source",
        jurisdiction_id="test_jurisdiction",
        display_name="Test Source",
        steward="Test Steward",
        method="bulk",
        phase_status="active",
        phase_status_reason="test",
        endpoint_url="https://example.com",
        licence_id="test.licence",
        url_verified_at=NOW,
        active=True,
    )
    kwargs.update(overrides)
    return kwargs


class TestSourceConstraints:
    def test_active_source_fully_qualified_accepted(self):
        Source(**_active_source_kwargs())

    def test_inactive_source_minimal_accepted(self):
        Source(id="s", jurisdiction_id="j", display_name="d", steward="s", method="manual",
               phase_status_reason="r", licence_id="l")

    def test_active_without_verification_rejected(self):
        with pytest.raises(ValidationError, match="source_active_requires_verification"):
            Source(**_active_source_kwargs(url_verified_at=None))

    def test_active_with_non_active_phase_rejected(self):
        with pytest.raises(ValidationError, match="source_active_matches_phase"):
            Source(**_active_source_kwargs(phase_status="blocked_rights"))

    def test_active_with_portal_method_rejected(self):
        with pytest.raises(ValidationError, match="source_active_requires_machine_access"):
            Source(**_active_source_kwargs(method="portal"))

    def test_non_manual_without_endpoint_rejected(self):
        with pytest.raises(ValidationError, match="source_endpoint_required"):
            Source(id="s", jurisdiction_id="j", display_name="d", steward="s", method="bulk",
                   phase_status_reason="r", licence_id="l", endpoint_url=None)

    def test_manual_without_endpoint_accepted(self):
        Source(id="s", jurisdiction_id="j", display_name="d", steward="s", method="manual",
               phase_status_reason="r", licence_id="l", endpoint_url=None)


# ---------------------------------------------------------------------------
# Licence
# ---------------------------------------------------------------------------


class TestLicenceConstraints:
    def test_attribution_restriction_with_text_accepted(self):
        Licence(id="l", display_name="L", restriction="attribution",
                attribution_text="Attribute me", observed_at=NOW)

    def test_open_restriction_without_text_accepted(self):
        Licence(id="l", display_name="L", restriction="open", observed_at=NOW)

    def test_attribution_restriction_without_text_rejected(self):
        with pytest.raises(ValidationError, match="licence_attribution_present"):
            Licence(id="l", display_name="L", restriction="attribution", observed_at=NOW)


# ---------------------------------------------------------------------------
# ParcelException
# ---------------------------------------------------------------------------


def _exception_kwargs(**overrides):
    kwargs = dict(
        parcel_id=PARCEL_ID,
        jurisdiction_id="test_jurisdiction",
        type="coverage_gap",
        severity="info",
        detector_key="test_detector",
        detector_version="1.0",
    )
    kwargs.update(overrides)
    return kwargs


class TestParcelExceptionConstraints:
    def test_open_with_no_resolution_accepted(self):
        ParcelException(**_exception_kwargs())

    def test_resolved_with_both_fields_accepted(self):
        ParcelException(**_exception_kwargs(
            outcome="condition_cleared", resolved_at=NOW, resolved_by="test_detector"))

    def test_open_with_resolved_at_rejected(self):
        with pytest.raises(ValidationError, match="parcel_exception_outcome_resolution_biconditional"):
            ParcelException(**_exception_kwargs(resolved_at=NOW))

    def test_resolved_without_resolved_by_rejected(self):
        with pytest.raises(ValidationError, match="parcel_exception_outcome_resolution_biconditional"):
            ParcelException(**_exception_kwargs(outcome="condition_cleared", resolved_at=NOW))

    def test_resolved_at_before_detected_at_rejected(self):
        with pytest.raises(ValidationError, match="parcel_exception_resolved_after_detected"):
            ParcelException(**_exception_kwargs(
                detected_at=NOW, outcome="condition_cleared",
                resolved_at=NOW - datetime.timedelta(days=1), resolved_by="x"))

    def test_version_retired_outcome_accepted(self):
        """0050 (P16) -- confirms the model's ExceptionOutcome literal was
        updated past 0001's original four values."""
        ParcelException(**_exception_kwargs(
            outcome="version_retired", resolved_at=NOW, resolved_by="system:detector_version_retired"))


# ---------------------------------------------------------------------------
# ParcelException.detail's encoding contract -- P24, design decision (d).
# Settled separately from Fact.value's (P22, decision (c)), not inherited --
# see core/model.py's own module docstring for the reproduction this
# formalizes.
# ---------------------------------------------------------------------------


class TestParcelExceptionDetailEncoding:
    def test_native_dict_accepted(self):
        pe = ParcelException(**_exception_kwargs(detail={"reason": "x"}))
        assert pe.detail == {"reason": "x"}

    def test_default_empty_dict_accepted(self):
        pe = ParcelException(**_exception_kwargs())
        assert pe.detail == {}

    def test_pre_encoded_json_string_rejected(self):
        """The opposite of Fact.value's contract, deliberately: detail is
        dict[str, Any], so a pre-encoded string is the WRONG type here,
        not the right one."""
        with pytest.raises(ValidationError, match="detail"):
            ParcelException(**_exception_kwargs(detail='{"reason": "x"}'))

    def test_non_json_serializable_value_rejected(self):
        with pytest.raises(ValidationError, match="must be JSON-serializable"):
            ParcelException(**_exception_kwargs(detail={"bad": {1, 2, 3}}))


# ---------------------------------------------------------------------------
# Refusal -- I8
# ---------------------------------------------------------------------------


class TestRefusal:
    def test_known_code_accepted(self):
        Refusal(code="RIGHTS_BLOCKED", stage="L8", message="blocked")

    def test_unknown_code_rejected(self):
        with pytest.raises(ValidationError):
            Refusal(code="NOT_A_REAL_CODE", stage="L8", message="x")

    def test_all_19_spec_codes_individually_accepted(self):
        """Exercises every code in REFUSAL_CODES, not just one -- a typo
        in the middle of the tuple would not be caught by testing only
        the first/last entries."""
        for code in REFUSAL_CODES:
            Refusal(code=code, stage="L0", message="x")

    def test_refusal_is_not_an_exception(self):
        """I8: 'Refusal is a typed return value, not an exception.'"""
        assert not issubclass(Refusal, BaseException)
        refusal = Refusal(code="RIGHTS_BLOCKED", stage="L8", message="blocked")
        assert not isinstance(refusal, BaseException)


# ---------------------------------------------------------------------------
# Result[T] -- I8
# ---------------------------------------------------------------------------


class TestResult:
    def test_ok_holds_value(self):
        r = Result.ok(5)
        assert r.is_ok is True
        assert r.is_refused is False
        assert r.value == 5

    def test_refuse_holds_refusal(self):
        refusal = Refusal(code="RIGHTS_BLOCKED", stage="L8", message="blocked")
        r = Result.refuse(refusal)
        assert r.is_ok is False
        assert r.is_refused is True
        assert r.refusal is refusal

    def test_accessing_value_on_a_refused_result_raises(self):
        refusal = Refusal(code="RIGHTS_BLOCKED", stage="L8", message="blocked")
        r = Result.refuse(refusal)
        with pytest.raises(RuntimeError, match="check is_ok/is_refused"):
            r.value

    def test_accessing_refusal_on_an_ok_result_raises(self):
        r = Result.ok(5)
        with pytest.raises(RuntimeError, match="check is_ok/is_refused"):
            r.refusal

    def test_direct_construction_with_both_raises(self):
        refusal = Refusal(code="RIGHTS_BLOCKED", stage="L8", message="blocked")
        with pytest.raises(RuntimeError, match="exactly one"):
            Result(5, refusal)

    def test_direct_construction_with_neither_raises(self):
        with pytest.raises(RuntimeError, match="exactly one"):
            Result(None, None)

    def test_no_bool_shortcut(self):
        """Deliberately no __bool__ -- `if result:` must not compile into
        a silent is_ok check. bool() falls back to the default (always
        True for a non-collection object without __len__/__bool__), which
        would be actively misleading if anyone relied on it -- this test
        exists to make removing __bool__ a deliberate, visible decision
        if anyone ever adds one back."""
        refusal = Refusal(code="RIGHTS_BLOCKED", stage="L8", message="blocked")
        r = Result.refuse(refusal)
        assert "__bool__" not in type(r).__dict__


# ---------------------------------------------------------------------------
# Parcel -- no CHECK constraints of its own beyond NOT NULL/type shape
# ---------------------------------------------------------------------------


class TestParcel:
    def test_minimal_parcel_accepted(self):
        Parcel(jurisdiction_id="test_jurisdiction")

    def test_null_apn_accepted(self):
        """0034 (P13): apn is nullable -- a parcel with no resolvable APN
        is real, not a shape error."""
        Parcel(jurisdiction_id="test_jurisdiction", apn=None)
