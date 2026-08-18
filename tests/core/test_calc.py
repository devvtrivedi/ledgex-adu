"""RED-first shape tests for core/calc.py (P25). No database needed --
evaluate_geometry_dependent_conclusion() takes geometry_tier_enabled as
a bare parameter (I1: jurisdiction-free), so its whole behavior is
checkable in isolation, same shape as core/model.py's own tests.
"""
import pytest

from core.calc import GEOMETRY_DEPENDENT_CONCLUSIONS, evaluate_geometry_dependent_conclusion
from core.model import Result


class TestEvaluateGeometryDependentConclusion:
    def test_disabled_tier_refuses_with_geometry_tier_disabled(self):
        result = evaluate_geometry_dependent_conclusion("placement", False)
        assert result.is_refused
        assert result.refusal.code == "GEOMETRY_TIER_DISABLED"
        assert result.refusal.stage == "L7"

    def test_refusal_names_which_conclusion_was_refused(self):
        """I10: 'refuse BY NAME' -- the refusal must identify which
        conclusion, not merely that something was refused."""
        result = evaluate_geometry_dependent_conclusion("cost_scenario", False)
        assert result.refusal.detail["conclusion"] == "cost_scenario"
        assert "cost_scenario" in result.refusal.message

    def test_enabled_tier_raises_not_implemented(self):
        """No real geometry-dependent computation exists anywhere in this
        codebase yet (P25's own scope boundary) -- a loud failure, not a
        silently fabricated value."""
        with pytest.raises(NotImplementedError, match="placement"):
            evaluate_geometry_dependent_conclusion("placement", True)

    def test_unknown_conclusion_rejected(self):
        with pytest.raises(ValueError, match="not a known geometry-dependent conclusion"):
            evaluate_geometry_dependent_conclusion("not_a_real_conclusion", False)

    def test_both_named_conclusions_refuse_when_disabled(self):
        for conclusion in GEOMETRY_DEPENDENT_CONCLUSIONS:
            result = evaluate_geometry_dependent_conclusion(conclusion, False)
            assert result.is_refused
            assert result.refusal.code == "GEOMETRY_TIER_DISABLED"

    def test_result_is_never_ok_for_either_input(self):
        """Documents the current, honest shape: neither input value
        produces a successful Result today -- disabled refuses, enabled
        raises. Not a Result.ok(...) path anywhere yet."""
        result = evaluate_geometry_dependent_conclusion("placement", False)
        assert not result.is_ok
