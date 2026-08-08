"""Intentionally empty. Scaffold only -- not the start of core/model.

import-linter's "forbidden" contract type requires source_modules to be
a real, importable package; a not-yet-existing "core" can only appear
as a forbidden_modules target (an external reference), never as the
source side of a contract. I1 and I15 both need core/ as a SOURCE
("core must not import X"), so there is no way to draft those two
contracts as something lint-imports can actually run -- as opposed to
error out on -- without this file existing. Confirmed directly: with no
core/__init__.py, `lint-imports` fails outright with "Module 'core'
does not exist," not a vacuous pass.

No domain code belongs here yet. core/model (Fact, Parcel, Source,
Licence, Exception, Refusal) is a separate, not-yet-made decision --
seeing this file present is not evidence that decision has been made.
"""
