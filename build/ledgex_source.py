"""
LedgeX / ADU.X — ONE INVARIANT SOURCE.

This module is the single source of truth for the invariant table (I1-I20) and
the six make targets. build_spec.py and build_rules.py both import
from here. Neither builder may contain a copied invariant table. This is also
the only place SPEC_VERSION/RULES_VERSION are set -- every other reference to
either version, anywhere in build/ or text/*.txt, is derived from these two
constants rather than hand-swept on every bump.

Spec sec 0.2 "One invariant source" and A-1 "Structural drift prevention".
Invariant I17: these strings are authoritative only when read verbatim from the
filesystem. Change the text HERE, once, then regenerate both artifacts.
"""

SPEC_VERSION = "1.27"
RULES_VERSION = "1.4"
PHASE = "Phase 1, Step 1 - City of San Jose"
REVISION_DATE = "August 2026"

# --------------------------------------------------------------------------
# INVARIANTS - I1 to I20. (id, invariant_body, enforcement)
# Verbatim from the Engineering Reference Spec, current SPEC_VERSION, sec 1.
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
     "A derived fact's licence is no broader than the intersection of every "
     "input's rights, on every dimension: channel, use and obligation. "
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


# --------------------------------------------------------------------------
# SECTION_INDEX - one row per top-level section of the Spec. (number,
# governs, use-when). Previously a private list named CONTENTS inside
# build_spec.py, used only to render the "Section index" table embedded in
# the Spec itself -- moved here so build_spec_index.py (docs/SPEC_INDEX.md,
# a session-cost-hygiene artifact) can share the identical data instead of
# hand-copying it, the same "one source, two artifacts" shape sec 0.2
# already establishes for INVARIANTS/MAKE_TARGETS.
#
# Two rows REMOVED here, not merely relocated: CONTENTS carried "6 Coding
# workflow" and "8 Canonical field vocabulary and dependencies" listed as
# if they were real top-level sections. Confirmed directly, not assumed,
# while building docs/SPEC_INDEX.md's cross-check -- grep '^## '
# docs/LEDGEX_SPEC.md has no "## 6." or "## 8." heading -- but the two are
# NOT the same kind of gap, and only one is fixed here:
#
#   §8 has no content anywhere. text/LedgeX_Engineering_Reference_Spec_
#   v1_26.txt's own "Section N —" markers jump 5 -> 7 -> 9; nothing
#   between them describes field-vocabulary dependencies as its own
#   section. §3.3 (Canonical field vocabulary, the field_definition DDL)
#   still cites "§8" in its own "Serves:" line -- a genuinely dangling
#   cross-reference, corrected in the same pass this comment landed in
#   (removed the "§8" token; nothing left to point at). Row dropped: there
#   is no content to index.
#
#   §6 is NOT the same gap. Its subsections are real and present --
#   "### 6.1" through "### 6.7" all exist in docs/LEDGEX_SPEC.md, inside
#   the byte range between §5's heading and §7's -- only the top-level
#   "## 6. Coding workflow" heading that should wrap them is missing, and
#   the raw text at that exact boundary (search "6.1 Task shapes" in the
#   .txt source) is visibly pdftotext-mangled: task-shape items A-D
#   interleave in an order that does not read as originally intended.
#   Restoring the heading correctly means untangling that mangled region
#   first, not inserting one line -- real content surgery, not an index
#   fix, and out of scope for a context-hygiene pass whose own hard rule
#   is "if you find yourself doing more than this, you have misread the
#   scope." Row dropped for now, reported here rather than silently
#   worked around: §6's content is real and reachable by reading §5/§7's
#   surrounding text, just not indexable by number until its heading is
#   restored in its own pass.
#
# SPEC_VERSION bumped (1.26 -> 1.27) and a change-record row added for
# this correction, per CLAUDE.md: it changes what docs/LEDGEX_SPEC.md's
# own embedded index table says, and removes a dangling cross-reference.
SECTION_INDEX = [
    ("0",  "How to use this file",                      "Always, before any change."),
    ("1",  "Invariants and internal-fact gate",         "Always. Every change is checked against these."),
    ("2",  "Repository layout",                         "Deciding where a file goes."),
    ("3",  "Database schema",                           "Any data-model change."),
    ("4",  "API endpoints",                             "Any interface change."),
    ("5",  "Runtime workflow",                          "Implementing or debugging a pipeline stage."),
    ("7",  "San José source list",                      "Adding or fixing an ingestion."),
    ("9",  "Refusal and error codes",                   "Anywhere something can fail."),
    ("10", "Track A / Track B measurement",             "Anything that touches evidence."),
    ("11", "Environment and configuration",             "Setup and deployment."),
    ("12", "Change record",                             "Amending this spec."),
    ("13", "Subscription commerce schema",               "Billing, entitlement or plan work."),
    ("14", "Launch dependencies and Base Core",          "Scoping what must ship."),
    ("15", "Architecture Addendum A-1",                  "A-1.1 to A-1.4 gates."),
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
