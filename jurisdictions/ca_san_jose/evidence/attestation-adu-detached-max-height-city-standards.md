# Attestation — rule `ca_san_jose.adu_detached_max_height_city_standards`, version 1

**review_mode**: `solo_founder_attestation` (`reviewed_by = authored_by`, per
`db/migrations/0009_rules.sql`'s own CHECK constraint and §3.9's Phase 1 bootstrap
allowance).

**Author / reviewer**: devtrivedi06@gmail.com

**Date**: 2026-08-18

**What was reviewed**: `jurisdictions/ca_san_jose/evidence/
bulletin-210-adu-universal-checklist-2026-03-05.pdf` (City of San José, Planning, Building
and Code Enforcement, Bulletin #210, "ADU Universal Checklist," header dated
`UPDATED 03/05/2026`, `SUBJECT TO CHANGE`), page 3, "Part 3. Choose the City or State ADU
Development Standards," Single-Family Properties table, "City Development Standards"
column, "Detached ADU (New or Conversion)" row, the "Maximum Height" cell: `1st Story: 18
ft / 2nd Story: 25 ft`.

**What this attestation does and does not claim**: I read this bulletin's page 3 table
directly and confirm the `params` on the rule row this attestation covers
(`first_story_max_ft: 18`, `second_story_max_ft: 25`, `max_stories: 2`) match that cell's
own stated values exactly. I did **not** read San José Municipal Code §20.80.175 itself —
every attempt to reach it from the environment available at the time (Municode's
JS-rendered viewer, `records.sanjoseca.gov`'s direct ordinance PDF, `sanjoseca.gov`'s own
pages) failed; see `prompts/README.md` finding #34 for the specific URLs and failure modes.
This rule's `citation` states plainly that it summarizes §20.80.175 via a City-published
bulletin, not the ordinance text itself — this attestation does not claim otherwise.

**Why this bulletin is admissible as this rule's source, for now**: it is the City of San
José's own current, dated, publicly issued guidance to applicants, self-consistent with
the municipal code section it names (§20.80.175), not a third-party paraphrase. It states
plainly that it is subject to change and that the Code itself is the governing law — this
rule's own `effective_from` (2026-03-05) is scoped to the date the City *published* this
standard, not any claim about the ordinance's own legal effective date, which remains
unknown. When the ordinance text itself becomes readable, this rule version is retired
(`effective_to` set, per `0013`'s one-way supersession) and a new version, citing the Code
directly, replaces it.

**What a reader in 2030 does with this**: `git show <the commit this file was introduced
in>:jurisdictions/ca_san_jose/evidence/bulletin-210-adu-universal-checklist-2026-03-05.pdf`
resolves the exact bytes reviewed — immutable by construction (a git object's content and
its hash are the same fact), readable with nothing but this repository's own history, no
external service, no account, no retention policy to outlive. The `rule.attestation_uri`
column stores this file's own commit-pinned path in that same form.
