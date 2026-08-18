"""L-none: the domain types. I2's Pydantic half -- §2 names this module's
scope explicitly: Fact, Parcel, Source, Licence, Exception, Refusal
("no queue, no task, no assignee types exist" -- I14, a constraint on
every model below, not a description of what's missing). Refusal and its
carrier, Result[T], are I8's typed-return-value half.

core/store.py's own docstring already named the gap this closes: its
positional 17-tuples are "exactly the kind of code that wants" a Fact
type. That adoption is NOT done here -- rewiring the three ingest
scripts and every acceptance suite onto these types is its own package,
reported not absorbed (P21). This package defines the types and proves
them against the real schema; nothing that already works is touched.

"Exception" is named ParcelException here, not Exception -- §2's own word
for it, but Python's builtin Exception would be shadowed by a domain
class of that name in every file that imports it unqualified, which is
a real hazard specifically on the one axis I8 cares about (Refusal is
NOT an exception; a domain type literally named Exception sitting next
to it would invite exactly the confusion I8 exists to prevent).

TWO DESIGN DECISIONS, reported before writing, not picked silently:

(a) REFUSAL IS NOT AN EXCEPTION (I8). Refusal is a plain BaseModel, no
    Exception in its MRO -- confirmed by construction (it inherits from
    BaseModel alone), not merely by convention. Result[T] is the typed
    return value I8 requires: a frozen wrapper holding EITHER a value of
    type T OR a Refusal, never both, never neither, constructed only via
    Result.ok()/Result.refuse(). The `.value`/`.refusal` accessors are
    GUARDED, not bare attributes: reading `.value` on a refused Result
    (or `.refusal` on an ok Result) raises RuntimeError immediately, at
    the point of misuse -- a caller cannot silently treat a refusal as a
    value, or a value as a refusal, without an explicit is_ok/is_refused
    check first (or a match on .is_ok). This is the closest Python gets
    to Rust's Result without a real sum type: not "unused return values
    are impossible" (no runtime type system forces that, exceptions
    included -- a caller that never touches the return value at all is a
    Python-level code-review problem, not one this type can force-catch
    from inside), but "using the return value WRONG is impossible to do
    quietly" -- the exact case CONVENTIONS worries about ("a return value
    is easier to drop on the floor than an exception").

    Refusal.code's vocabulary is §9's 19 codes, and duplicating that list
    a THIRD time (docs/LEDGEX_SPEC.md's own prose, 0038/0048's
    refusals_codes_valid() CHECK, now this file) is a real drift risk --
    build/qa_check.py's check_refusal_codes_match_spec() already diffs
    the first two; extended in this package (still two-way-diff-shaped,
    now run twice, spec-vs-migration and spec-vs-model) rather than
    invented as a new mechanism. See that function's own updated
    docstring.

(b) FACT AND fact_provenance_complete (0006) ARE NOT ONE SHARED OBJECT --
    THEY CANNOT BE. §0.2's "one invariant source" pattern
    (build/ledgex_source.py, imported by both build_spec.py and
    build_rules.py) works because both consumers are Python and can
    import the same object. fact_provenance_complete is a PostgreSQL
    CHECK constraint; Fact's equivalent validator is a Pydantic
    model_validator. SQL cannot import Python, and Python cannot embed a
    CHECK constraint's DDL as its own executable logic without
    reimplementing it -- the same mechanical wall that already forced
    refusal codes into an extract-and-diff pattern instead of literal
    §0.2-style sharing, except refusal codes are a flat set of string
    literals (diffable as text) and this is a boolean predicate over five
    fields (not meaningfully diffable as text without fragile
    parenthesis-balanced parsing of an immutable, forward-only migration
    file this package cannot retroactively instrument with extraction
    markers the way 0038 was built with them from the start).

    "Tests would catch it" is only true if a test asserts the
    equivalence -- so one does: tests/core/test_fact_provenance_equivalence.py
    runs every (method, source_id-present, snapshot_id-present,
    retrieved_at-present, source_url-present, method_version-present)
    combination through BOTH this file's Fact validator AND a real
    INSERT against the real, currently-migrated fact table, and asserts
    they agree on every single one -- stronger protection than a textual
    diff would give (it catches a LOGICALLY divergent rewrite of either
    side, not just a literal-text mismatch), and it stays correct even
    if a future migration DROPs+ADDs a redefined fact_provenance_complete
    (0048/0049/0050/0051's own established precedent for how a constraint
    changes here) -- the test re-derives against whatever the live
    database actually enforces, not a frozen copy of 0006's text.
"""
from __future__ import annotations

import datetime
from typing import Any, Final, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --------------------------------------------------------------------------
# Refusal + Result[T] -- I8
# --------------------------------------------------------------------------

# §9's refusal-code vocabulary, verbatim -- kept in sync with
# db/migrations/0048_refusals_codes_valid_reject_null_shapes.sql's
# REFUSAL_CODES_BEGIN/END list and docs/LEDGEX_SPEC.md's own §9 table by
# build/qa_check.py's check_refusal_codes_match_spec(), extended in this
# package to a second, identically-shaped diff against this tuple. Do not
# hand-edit one list without the other two -- qa_check will catch it, but
# catching a mistake is not the same as it being free to make.
REFUSAL_CODES: Final[tuple[str, ...]] = (
    "JURISDICTION_UNRESOLVED",
    "JURISDICTION_UNSUPPORTED",
    "JURISDICTION_BOUNDARY_CONFLICT",
    "PARCEL_NOT_FOUND",
    "SOURCE_UNVERIFIED",
    "SOURCE_UNAVAILABLE",
    "SOURCE_NOT_MACHINE_READABLE",
    "SOURCE_DEFERRED",
    "CROSSWALK_UNMAPPED",
    "RULE_UNAVAILABLE",
    "PERMIT_SERIES_TOO_SHALLOW",
    "GEOMETRY_TIER_DISABLED",
    "COVERAGE_GAP",
    "PERMIT_LAYER_UNAVAILABLE",
    "RIGHTS_BLOCKED",
    "LICENCE_UNKNOWN",
    "INSUFFICIENT_COVERAGE",
    "DISCLOSURE_NOT_ACCEPTED",
    "ACCESS_NOT_ENTITLED",
)
RefusalCode = Literal[REFUSAL_CODES]  # type: ignore[valid-type]


class Refusal(BaseModel):
    """A typed return value (I8), never raised, never subclassing
    Exception -- confirmed by this class's own bases, not asserted in
    prose. Shape matches property_file.refusals' own jsonb array element
    shape (payload assembled by scripts/compose_property_file.py today);
    `stage` is a plain non-empty string, deliberately not itself a closed
    vocabulary here -- 0038/0048's own refusals_codes_valid() CHECK only
    validates `code`, never `stage`, so a stricter Python-side stage
    enum would be a NEW contract the database does not already enforce,
    inventing a fourth vocabulary to keep in sync for a guarantee nobody
    asked this package to add."""

    model_config = ConfigDict(frozen=True)

    code: RefusalCode
    stage: str = Field(min_length=1)
    message: str = Field(min_length=1)
    detail: dict[str, Any] = Field(default_factory=dict)


T = TypeVar("T")


class Result(Generic[T]):
    """I8's Result[T] -- NOT a BaseModel (it wraps an arbitrary T, which
    may or may not itself be a BaseModel; Pydantic generics validate on
    construction, which is the wrong shape for a plain in-process
    control-flow wrapper that never crosses a serialization boundary
    itself). Construct only via Result.ok()/Result.refuse() -- the
    __init__ signature is deliberately unfriendly (two positional
    Nones) to make constructing an invalid one-of-neither/one-of-both
    Result by accident awkward, not merely undocumented.

    .value and .refusal are GUARDED accessors, not bare attributes:
    reading the wrong one raises RuntimeError immediately, naming which
    check (is_ok/is_refused) the caller skipped -- see this module's own
    docstring, decision (a), for why this is the shape I8 needs. No
    __bool__ -- `if result:` would tempt exactly the silent-drop shortcut
    this type exists to prevent; is_ok/is_refused must be named."""

    __slots__ = ("_value", "_refusal")

    def __init__(self, value: T | None, refusal: Refusal | None) -> None:
        if (value is None) == (refusal is None):
            raise RuntimeError(
                "Result must hold exactly one of value/refusal -- "
                "use Result.ok(value) or Result.refuse(refusal), not this constructor directly"
            )
        self._value = value
        self._refusal = refusal

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value, None)

    @classmethod
    def refuse(cls, refusal: Refusal) -> "Result[T]":
        return cls(None, refusal)

    @property
    def is_ok(self) -> bool:
        return self._refusal is None

    @property
    def is_refused(self) -> bool:
        return self._refusal is not None

    @property
    def value(self) -> T:
        if self._refusal is not None:
            raise RuntimeError(
                "Result.value accessed on a refused Result -- check is_ok/is_refused "
                "first, or read .refusal instead"
            )
        return self._value  # type: ignore[return-value]

    @property
    def refusal(self) -> Refusal:
        if self._refusal is None:
            raise RuntimeError(
                "Result.refusal accessed on an ok Result -- check is_ok/is_refused "
                "first, or read .value instead"
            )
        return self._refusal

    def __repr__(self) -> str:
        if self.is_ok:
            return f"Result.ok({self._value!r})"
        return f"Result.refuse({self._refusal!r})"


# --------------------------------------------------------------------------
# Fact -- I2, I3, I4, I7, I13
# --------------------------------------------------------------------------

# fact.method is access_method's full range in the enum (0001) --
# ('direct','bulk','portal','manual','derived') -- but fact_method_automated
# (0006, I13) narrows what a FACT specifically may carry to three of the
# five. This Literal matches the CHECK, not the enum's full range --
# confirmed by reading db/schema.sql directly, not assumed from the enum
# name alone.
FactMethod = Literal["direct", "bulk", "derived"]
ConfidenceLevel = Literal["high", "medium", "low"]
ConflictState = Literal["agree", "conflicts", "stale", "missing"]
SupersessionReason = Literal[
    "world_change", "source_correction", "refetch_no_change", "ingestion_logic_change", "unknown"
]


class Fact(BaseModel):
    """Mirrors db/schema.sql's live `fact` table -- read directly from
    db/schema.sql, not from 0006_fact.sql alone, since later migrations
    (0025 supersedes_fact_id/supersession_reason, jurisdiction_id
    denormalisation, source_asserted_as_of) widened it. Single-row shape
    validation only: fact_supersession_target_validate() (0042) and
    fact_one_current_per_source (0006) are CROSS-ROW checks -- they
    compare this fact against OTHER rows already in the database, which
    no Pydantic model can see in isolation. Out of scope by construction,
    not by oversight; the database remains the only authority for those
    two."""

    model_config = ConfigDict(frozen=True)

    id: UUID | None = None
    parcel_id: UUID
    jurisdiction_id: str = Field(min_length=1)
    field_key: str = Field(min_length=1)
    value: Any
    unit: str | None = None
    local_verbatim: str | None = None

    source_id: str | None = None
    source_url: str | None = None
    layer_item_id: str | None = None
    snapshot_id: str | None = None
    method: FactMethod

    retrieved_at: datetime.datetime | None = None
    source_published_at: datetime.datetime | None = None
    source_cadence_stated: str | None = None
    effective_from: datetime.datetime
    effective_to: datetime.datetime | None = None
    recorded_at: datetime.datetime | None = None
    superseded_at: datetime.datetime | None = None

    licence_id: str = Field(min_length=1)

    confidence: ConfidenceLevel
    confidence_rule_id: str = Field(min_length=1)
    conflict: ConflictState = "agree"

    method_version: str | None = None
    ruleset_version: str | None = None
    pack_version: str = Field(min_length=1)

    supersedes_fact_id: UUID | None = None
    supersession_reason: SupersessionReason | None = None
    source_asserted_as_of: datetime.datetime | None = None

    @model_validator(mode="after")
    def _check_provenance_complete(self) -> "Fact":
        """I2, mirroring fact_provenance_complete (0006) exactly -- see
        this module's own docstring, decision (b), for why this cannot be
        the SAME object as the CHECK constraint, and
        tests/core/test_fact_provenance_equivalence.py for the real,
        RED-first proof that the two agree."""
        if self.method == "derived":
            if self.source_id is not None or self.snapshot_id is not None:
                raise ValueError(
                    "a derived fact must not carry source_id or snapshot_id "
                    "(fact_provenance_complete, I2)"
                )
            if self.method_version is None:
                raise ValueError(
                    "a derived fact requires method_version (fact_provenance_complete, I2)"
                )
        else:
            if self.source_id is None or self.snapshot_id is None:
                raise ValueError(
                    "a retrieved fact (method != 'derived') requires both source_id "
                    "and snapshot_id (fact_provenance_complete, I2)"
                )
            if self.retrieved_at is None or self.source_url is None:
                raise ValueError(
                    "a retrieved fact (method != 'derived') requires both retrieved_at "
                    "and source_url (fact_provenance_complete, I2)"
                )
        return self

    @model_validator(mode="after")
    def _check_valid_time(self) -> "Fact":
        """fact_valid_time (0006)."""
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be strictly after effective_from (fact_valid_time)")
        return self

    @model_validator(mode="after")
    def _check_txn_time(self) -> "Fact":
        """fact_txn_time (0006) -- only checkable when both sides are
        already known; recorded_at is server-defaulted (now()) on most
        real rows, so this only fires when the caller supplied both
        explicitly."""
        if (
            self.superseded_at is not None
            and self.recorded_at is not None
            and self.superseded_at < self.recorded_at
        ):
            raise ValueError("superseded_at must be at or after recorded_at (fact_txn_time)")
        return self

    @model_validator(mode="after")
    def _check_supersession_reason_biconditional(self) -> "Fact":
        """fact_supersession_reason_biconditional (0025): both set or
        both NULL, never one alone."""
        if (self.supersedes_fact_id is None) != (self.supersession_reason is None):
            raise ValueError(
                "supersedes_fact_id and supersession_reason must both be set or both "
                "be NULL (fact_supersession_reason_biconditional)"
            )
        return self

    @model_validator(mode="after")
    def _check_supersedes_not_self(self) -> "Fact":
        """fact_supersedes_not_self (0042) -- only checkable once id is
        known; most callers construct a Fact before an id is assigned by
        the database, so this is a defensive check for the case where a
        caller supplies both explicitly."""
        if self.id is not None and self.supersedes_fact_id == self.id:
            raise ValueError("a fact cannot supersede itself (fact_supersedes_not_self)")
        return self


# --------------------------------------------------------------------------
# Parcel -- §3.4
# --------------------------------------------------------------------------


class Parcel(BaseModel):
    """Mirrors db/schema.sql's live `parcel` table. apn is nullable and
    NOT unique (0034, P13: dropped UNIQUE (jurisdiction_id, apn) after
    real collisions and blanks confirmed in a real export) -- id is the
    only identifier this model, or any real caller, may trust. geom/centroid are PostGIS
    geometry columns; represented here as opaque strings (WKT/GeoJSON,
    caller's choice) rather than a geometry type this package does not
    need to model precisely -- core/calc doesn't exist yet to consume a
    richer representation, and inventing one now would be exactly the
    "anticipated, not forced by need" scope core/store.py's own docstring
    already argues against for a different column."""

    model_config = ConfigDict(frozen=True)

    id: UUID | None = None
    jurisdiction_id: str = Field(min_length=1)
    apn: str | None = None
    situs_address: str | None = None
    geom: str | None = None
    centroid: str | None = None
    first_seen_at: datetime.datetime | None = None
    last_seen_at: datetime.datetime | None = None


# --------------------------------------------------------------------------
# Source -- §3.2
# --------------------------------------------------------------------------

AccessMethod = Literal["direct", "bulk", "portal", "manual", "derived"]
SourcePhaseStatus = Literal[
    "active", "blocked_rights", "blocked_engineering", "not_machine_readable", "deferred", "excluded"
]


class Source(BaseModel):
    """Mirrors db/schema.sql's live `source` table."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    jurisdiction_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    steward: str = Field(min_length=1)
    method: AccessMethod
    phase_status: SourcePhaseStatus = "blocked_rights"
    phase_status_reason: str = Field(min_length=1)
    endpoint_url: str | None = None
    layer_item_id: str | None = None
    query_params: dict[str, Any] = Field(default_factory=dict)
    licence_id: str = Field(min_length=1)
    cadence_stated: str | None = None
    cadence_observed_s: int | None = None
    earliest_record_date: datetime.date | None = None
    expected_fields: list[Any] = Field(default_factory=list)
    url_verified_at: datetime.datetime | None = None
    active: bool = False
    created_at: datetime.datetime | None = None

    @model_validator(mode="after")
    def _check_active_requires_verification(self) -> "Source":
        """source_active_requires_verification (0021)."""
        if self.active and self.url_verified_at is None:
            raise ValueError("an active source requires url_verified_at (source_active_requires_verification)")
        return self

    @model_validator(mode="after")
    def _check_active_matches_phase(self) -> "Source":
        """source_active_matches_phase (0021)."""
        if self.active and self.phase_status != "active":
            raise ValueError("an active source requires phase_status='active' (source_active_matches_phase)")
        return self

    @model_validator(mode="after")
    def _check_active_requires_machine_access(self) -> "Source":
        """source_active_requires_machine_access (0021)."""
        if self.active and self.method not in ("direct", "bulk"):
            raise ValueError(
                "an active source requires method in ('direct','bulk') "
                "(source_active_requires_machine_access)"
            )
        return self

    @model_validator(mode="after")
    def _check_endpoint_required(self) -> "Source":
        """source_endpoint_required (0021)."""
        if self.method != "manual" and self.endpoint_url is None:
            raise ValueError(
                "endpoint_url is required unless method='manual' (source_endpoint_required)"
            )
        return self


# --------------------------------------------------------------------------
# Licence -- §3.2, I3, I5, I6
# --------------------------------------------------------------------------

UseRestriction = Literal["open", "attribution", "noncommercial", "no_resale", "unknown"]
PermissionState = Literal["allowed", "prohibited", "unknown"]


class Licence(BaseModel):
    """Mirrors db/schema.sql's live `licence` table."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    restriction: UseRestriction
    commercial_use: PermissionState = "unknown"
    redistribution: PermissionState = "unknown"
    attribution_text: str | None = None
    terms_url: str | None = None
    evidence_uri: str | None = None
    observed_at: datetime.datetime
    cleared_by: str | None = None
    cleared_at: datetime.datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_attribution_present(self) -> "Licence":
        """licence_attribution_present (0002)."""
        if self.restriction == "attribution" and self.attribution_text is None:
            raise ValueError(
                "restriction='attribution' requires attribution_text (licence_attribution_present)"
            )
        return self


# --------------------------------------------------------------------------
# ParcelException -- §2's "Exception", I12. Named ParcelException, not
# Exception -- see this module's own top-of-file docstring for why.
# --------------------------------------------------------------------------

ExceptionType = Literal["record_to_ground", "cross_source", "staleness", "rule_boundary", "coverage_gap", "rights_gap"]
ExceptionSeverity = Literal["info", "warning", "blocking"]
# 0001's original four plus 0047's condition_cleared and 0050's
# version_retired (P16/P18, README findings #9's teardown-adjacent work
# and #18) -- the live enum, not the 0001 migration's own original list.
ExceptionOutcome = Literal[
    "open", "confirmed", "false_positive", "unresolved", "condition_cleared", "version_retired"
]


class ParcelException(BaseModel):
    """Mirrors db/schema.sql's live `parcel_exception` table."""

    model_config = ConfigDict(frozen=True)

    id: UUID | None = None
    parcel_id: UUID
    jurisdiction_id: str = Field(min_length=1)
    type: ExceptionType
    severity: ExceptionSeverity
    detector_key: str = Field(min_length=1)
    detector_version: str = Field(min_length=1)
    ruleset_version: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime.datetime | None = None
    outcome: ExceptionOutcome = "open"
    resolved_at: datetime.datetime | None = None
    resolved_by: str | None = None
    resolution_notes: str | None = None
    reopened_from_id: UUID | None = None

    @model_validator(mode="after")
    def _check_outcome_resolution_biconditional(self) -> "ParcelException":
        """parcel_exception_outcome_resolution_biconditional (0015)."""
        if self.outcome == "open":
            if self.resolved_at is not None or self.resolved_by is not None:
                raise ValueError(
                    "outcome='open' requires resolved_at and resolved_by both NULL "
                    "(parcel_exception_outcome_resolution_biconditional)"
                )
        else:
            if self.resolved_at is None or self.resolved_by is None:
                raise ValueError(
                    "a non-open outcome requires resolved_at and resolved_by both set "
                    "(parcel_exception_outcome_resolution_biconditional)"
                )
        return self

    @model_validator(mode="after")
    def _check_resolved_after_detected(self) -> "ParcelException":
        """parcel_exception_resolved_after_detected (0020) -- only
        checkable when both sides are already known; detected_at is
        server-defaulted (now()) on most real rows."""
        if (
            self.resolved_at is not None
            and self.detected_at is not None
            and self.resolved_at < self.detected_at
        ):
            raise ValueError(
                "resolved_at must be at or after detected_at (parcel_exception_resolved_after_detected)"
            )
        return self
