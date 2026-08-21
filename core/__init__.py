"""core/store (L4) and core/exceptions (L6) were the first real modules
here -- both took a shared, byte-identical execute_values primitive out
of scripts/*.py, keeping the source-specific tuple-building mapping
outside core/ (I1). core/model.py, core/calc.py and core/rules.py
followed (P21/P25/P31). core/rights.py (layer X) is the newest, P47 --
moved from scripts/compose_property_file.py once .importlinter's
commerce/core contract was repaired to actually gate a new core/
submodule (README finding #45). Still unbuilt: core/connectors, and
core/compose beyond what already lives in scripts/compose_property_file.py.

This package started as an empty scaffold (see git history) purely so
import-linter's "forbidden" contracts (I1, I15) had a real package to
use as a source_modules entry -- a not-yet-existing "core" can only
appear as a forbidden_modules target (external reference), never as a
contract's source side; confirmed directly, lint-imports fails outright
("Module 'core' does not exist") without this file, rather than passing
vacuously.
"""
