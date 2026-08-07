"""
LedgeX / ADU.X — ONE INVARIANT SOURCE.

This module is the single source of truth for the invariant table (I1-I20) and
the six make targets. build_spec_v1_13.py and build_rules_v1_4.py both import
from here. Neither builder may contain a copied invariant table.

Spec v1.13 sec 0.2 "One invariant source" and A-1 "Structural drift prevention".
Invariant I17: these strings are authoritative only when read verbatim from the
filesystem. Change the text HERE, once, then regenerate both artifacts.
"""

SPEC_VERSION = "1.13"
RULES_VERSION = "1.4"
PHASE = "Phase 1, Step 1 - City of San Jose"
REVISION_DATE = "August 2026"

# --------------------------------------------------------------------------
# INVARIANTS - I1 to I20. (id, invariant_body, enforcement)
# Verbatim from Engineering Reference Spec v1.13 sec 1.
# --------------------------------------------------------------------------
INVARIANTS = [
    ("I1",
     "core/ contains no jurisdiction name, local rule or local field name.",
     "make check-boundary; import-linter"),
    ("I2",
     "A Fact cannot exist without source_id + snapshot_id when retrieved, or "
     "method_version + complete lineage when derived.",
     "DB CHECK; Pydantic model"),
    ("I3",
     "Every fact carries a non-null licence_id.",
     "DB NOT NULL + FK"),
    ("I4",
     "Facts are immutable. Corrections supersede prior facts; they never "
     "overwrite or destructively update them.",
     "fact_no_update trigger"),
    ("I5",
     "A derived fact inherits the most restrictive licence of every input. "
     "Application code computes it at write time and the database validates it.",
     "derive(); licence trigger; CI"),
    ("I6",
     "The composer omits or refuses every fact whose licence forbids the output "
     "channel, including facts used only internally for resolution. Unknown "
     "rights block. Rights and confidence are independent gates.",
     "rights gate; touched-fact test"),
    ("I7",
     "Stated source cadence, source publication date and retrieval date are "
     "separate stored fields and are never conflated.",
     "schema; cadence test"),
    ("I8",
     "Refusal is a typed return value, not an exception. Every runtime stage "
     "can refuse deterministically.",
     "Result[T]; refusal tests"),
    ("I9",
     "A derived conclusion never renders in the visual or structural treatment "
     "reserved for a retrieved fact.",
     "claim renderer; isolation test"),
    ("I10",
     "Base Core remains composable when the geometry module is disabled, "
     "provided its own dependencies clear. Placement and every "
     "geometry-dependent conclusion refuse by name; no fallback geometry is "
     "inferred.",
     "base-core / no-fallback tests"),
    ("I11",
     "Every rule application records the exact ruleset_version and a "
     "human-readable citation.",
     "schema NOT NULL; citation test"),
    ("I12",
     "Every detected exception is a stored, measurable row with evidence and a "
     "closeable internal outcome.",
     "schema; exception metrics"),
    ("I13",
     "Only direct, bulk and deterministic derived facts may exist. No human "
     "observation, portal reading, manual lookup or request-time LLM judgment "
     "becomes a fact.",
     "method CHECK; no-human-facts test"),
    ("I14",
     "Customer delivery is automated end to end. No stage may block on, queue "
     "for, assign to, route to or be supplemented by a person. A "
     "machine-unavailable field is omitted, downgraded or refused.",
     "no queue schema; delivery-path test"),
    ("I15",
     "commerce may reference public; public may never reference commerce. A "
     "commerce row cannot create, alter or supply a property fact or conclusion.",
     "catalogue query; import-linter"),
    ("I16",
     "Subscription billing is independent of Property File outcome. Composed, "
     "partial and refused never create an individual-file charge, price "
     "adjustment, credit, settlement, refund or confidence exception.",
     "billing-independence tests"),
    ("I17",
     "The Spec and Rules are authoritative only when read verbatim from the "
     "filesystem. A graph, summary or derived context artifact cannot supply a "
     "rule, citation, licence term or CI gate.",
     "check-boundary; no-graph test"),
    ("I18",
     "Rule and disclosure review evidence is immutable and uses either "
     "independent review or same-identity solo-founder attestation with a "
     "non-null attestation URI. Review never enters customer delivery.",
     "DB CHECKs; review-mode matrix"),
    ("I19",
     "Evaluation-to-permit outcome observations exist only in commerce as "
     "Track B measurement. They never enter core/compose, never render in a "
     "Property File and never become public facts or provenance inputs.",
     "schema separation; no-render test"),
    ("I20",
     "A footprint provider cannot occupy the active geometry slot unless an "
     "immutable approved measured-error record exists for the same provider "
     "version, method and jurisdiction. Runtime substitution is forbidden.",
     "constraint trigger; provider-slot tests"),
]

# --------------------------------------------------------------------------
# MAKE_TARGETS - the six targets. (target, execution_surface, pass_condition)
# --------------------------------------------------------------------------
MAKE_TARGETS = [
    ("make check-boundary",
     "Jurisdiction-name grep, import-linter, public-to-commerce catalogue "
     "query, filesystem authority, no-graph and Track B no-render checks.",
     "I1, I15, I17 and I19 pass; zero forbidden imports, FKs or derived "
     "authority."),
    ("make schema",
     "Apply every forward-only migration to an empty database.",
     "Clean apply; constraints, functions and triggers compile."),
    ("make schema-dump",
     "Regenerate db/schema.sql from the applied database and compare the "
     "committed dump.",
     "No diff; missing or stale generated DDL fails."),
    ("make conformance",
     "Parameterized pack suite for sources, mappings, rights, dependency "
     "cascades and endpoint liveness.",
     "Every enabled pack passes; no rights broadening or silent missing "
     "dependency."),
    ("make test",
     "Unit and integration suites, including review, entitlement, outcome "
     "observation, provider slot, edge guard and billing independence.",
     "All required tests pass with zero skips and no external network "
     "dependency in CI."),
    ("make golden",
     "Normalized composed, partial, refused and geometry-disabled Base Core "
     "fixtures.",
     "Output matches approved fixtures; intended changes require reviewed "
     "fixture updates."),
]

# --------------------------------------------------------------------------
# A-1 Architecture Addendum scope items.
# --------------------------------------------------------------------------
A1_SCOPE = [
    ("A-1.1", "Control recovery / canonical invariants",
     "Canonical I1-I20, internal-fact licence-gate rationale and six make targets."),
    ("A-1.2", "Evaluation-to-permit outcome loop",
     "Immutable Track B evaluation-to-permit observations in commerce only."),
    ("A-1.3", "Validated footprint-provider slot",
     "One validated footprint-provider slot; switching is controlled, never "
     "runtime fallback. No activation without approved measured-error evidence."),
    ("A-1.4", "Edge request guard",
     "Edge infrastructure protection before entitlement and core/compose; "
     "rejection is HTTP 429, not a file outcome and not a fourth outcome."),
]


def md_table(headers, rows, bold_first=False):
    """Render a markdown table. Used by both builders - never duplicated."""
    def esc(s):
        return str(s).replace("|", "\\|").replace("\n", " ").strip()
    out = ["| " + " | ".join(esc(h) for h in headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        cells = [esc(c) for c in r]
        if bold_first:
            cells[0] = f"**{cells[0]}**"
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def invariant_table_md():
    return md_table(["ID", "Invariant", "Required enforcement"],
                    INVARIANTS, bold_first=True)


def make_target_table_md():
    return md_table(["Target", "Execution surface", "Pass condition"],
                    MAKE_TARGETS, bold_first=True)
