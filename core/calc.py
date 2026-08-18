"""L7: derived conclusions. First real content, geometry-gating only.

P25's own scope, deliberately: prove the geometry-disabled refusal path
(I10), do not compute or persist a derived fact. Refusal is a typed
return value (I8) -- core/model.Result[T]/Refusal exist for exactly
this; this module returns them, never raises for the ordinary refusal
case (NotImplementedError below is a real, separate boundary -- see
that branch's own docstring).

WHY REFUSE-ONLY, NOT "REFUSE, OR COMPUTE": the first derived fact this
codebase ever writes would exercise I5/0029's licence-intersection
trigger, I2's derived branch (source_id NULL, snapshot_id NULL,
method_version NOT NULL -- fact_provenance_complete, 0006), and
fact_input lineage, all three at once, all three currently untested by
anything real. Building that safely is its own package, with its own
RED-first proof against each of those three surfaces -- not something to
absorb into a refusal-path package because the same function happens to
sit next to it. If a caller ever needs this module to compute a real
value (geometry_tier_enabled=True), that need is the trigger for that
package, not a reason to fake an answer here now.

I1: this module is jurisdiction-free. geometry_tier_enabled is a
PARAMETER, not a lookup -- this file contains no jurisdiction id, no
SQL, no database connection at all. The caller (today,
scripts/compose_property_file.py; eventually core/compose) owns reading
jurisdiction.geometry_tier_enabled and passes the bare boolean in.
"""
from typing import Final

from core.model import Refusal, Result

# §14.2's own two named geometry-dependent conclusion types ("Conceptual
# placement", "Cost scenario"). Only "placement" has a real caller today
# (scripts/compose_property_file.py) -- cost_scenario is named here as
# the sibling I10 also covers, not invoked yet, not scope creep: the
# function already generalizes over both without extra code for the
# second entry.
GEOMETRY_DEPENDENT_CONCLUSIONS: Final[tuple[str, ...]] = ("placement", "cost_scenario")


def evaluate_geometry_dependent_conclusion(conclusion: str, geometry_tier_enabled: bool) -> "Result[None]":
    """I10: "Placement and every geometry-dependent conclusion refuse by
    name; no fallback geometry is inferred." geometry_tier_enabled=False
    (the live default for every jurisdiction in this project today) is
    the only real code path here -- refuses with GEOMETRY_TIER_DISABLED
    (§9, stage L7; 3DEP gate not cleared), naming which conclusion was
    refused in `detail`, not merely that something was.

    geometry_tier_enabled=True raises NotImplementedError, deliberately,
    not a silent fabricated success: no real geometry-dependent
    computation exists anywhere in this codebase yet (LD-4/3DEP, I20's
    provider-slot validation -- see P24's own build-direction report).
    A loud failure here is correct, not a gap to paper over -- the
    alternative would be inventing a placement or cost-scenario answer
    nobody computed, exactly what I13 forbids. Not reachable by any real
    composition today: every jurisdiction defaults geometry_tier_enabled
    to false (0002_registries.sql), confirmed live, not assumed."""
    if conclusion not in GEOMETRY_DEPENDENT_CONCLUSIONS:
        raise ValueError(
            f"{conclusion!r} is not a known geometry-dependent conclusion -- "
            f"see this module's own GEOMETRY_DEPENDENT_CONCLUSIONS."
        )
    if not geometry_tier_enabled:
        return Result.refuse(Refusal(
            code="GEOMETRY_TIER_DISABLED",
            stage="L7",
            message=(
                f"{conclusion} requires a validated geometry tier, and this "
                f"jurisdiction's geometry tier is disabled (3DEP gate not "
                f"satisfied, I10)."
            ),
            detail={"conclusion": conclusion, "geometry_tier_enabled": False},
        ))
    raise NotImplementedError(
        f"{conclusion}: geometry_tier_enabled=True has no real computation "
        f"path yet (LD-4/3DEP, I20's provider slot). This module only "
        f"builds the disabled-tier refusal (P25) -- computing and "
        f"persisting a real geometry-dependent derived fact is its own, "
        f"separate package (see this module's own docstring)."
    )
