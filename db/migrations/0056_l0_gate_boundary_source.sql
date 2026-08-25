-- 0056_l0_gate_boundary_source.sql
-- Serves: I1.1, I6, sec 9 (LICENCE_UNKNOWN). prompts/P53-l0-gate.md.
--
-- THE PROBLEM. prompts/P52-rights-vs-diligence.md sec 5 and prompts/
-- P53-l0-gate.md sec 1 confirmed, live, twice: zero ca_san_jose.city_limits
-- source rows, zero jurisdiction.incorporated facts or field_definition
-- rows, zero licence rows with id='unknown', jurisdiction.boundary_source_id
-- NULL everywhere. STANDING-BLOCKER.md's "LD-1 -- BLOCKS EVERYTHING" (now
-- corrected there, P52) described intent, not enforced behaviour: nothing in
-- this repo ever gave the L0/LD-1 jurisdiction gate a runtime representation.
-- The only thing actually blocking every composition today is cc0/cc_by_4_0's
-- own licence_channel.allowed=false (0030).
--
-- THE DESIGN (P53-l0-gate.md sec 3, D-C, approved). Refuse-on-absence: if a
-- jurisdiction declares jurisdiction.boundary_source_id, the composer
-- requires a current jurisdiction.incorporated fact for the parcel or it
-- refuses LICENCE_UNKNOWN (an existing, correct, never-yet-emitted sec 9
-- code -- no new code, no spec bump). boundary_source_id is the activation
-- switch: NULL for every jurisdiction except ca_san_jose (set below), so
-- every test.*/internal_test.* fixture jurisdiction elsewhere in this
-- database stays completely unaffected. The composer-side check itself
-- (scripts/compose_property_file.py) is not this migration's job -- it
-- lands in the same commit, in Python, alongside this data.
--
-- THIS MIGRATION CLEARS NOTHING. It does not touch cc0, cc_by_4_0, or any
-- of their licence_channel rows. It introduces a THIRD, separately-unknown
-- licence for a fourth source, blocked the same way LD-1's own declared
-- intent already says it should be.
--
-- WHY A MIGRATION, NOT SEED-ONLY (P53-l0-gate.md sec 6/sec 9 Q2). New
-- reference data belongs in db/seeds/day4_sources.sql (cc0/cc_by_4_0/
-- ca_san_jose were never introduced via migration either) -- and it is
-- ALSO added there, in the same commit, for every fresh install after this
-- point. This migration exists ONLY because of a real ordering problem
-- Q2 could not wave away: jurisdiction.boundary_source_id's FK target must
-- exist before the UPDATE that sets it, and any database that was already
-- seeded BEFORE this pass (ledgex_schema_check, ledgex_smoke, every
-- reachable scratch database) has a ca_san_jose jurisdiction row from an
-- OLD day4_sources.sql run, with no city_limits source and no 'unknown'
-- licence sitting next to it -- CLAUDE.md's own "both halves" rule (0026):
-- the seed alone fixes every future install; only a migration fixes a
-- database that already exists.
--
-- THE ORDERING PROBLEM, RESOLVED EXPLICITLY (P53-l0-gate.md sec 2). Every
-- statement below is guarded so it never errors -- no FK violation
-- possible -- on a FRESH, migrations-only database:
--
-- **Corrected (D16, P59):** "TRUE no-op -- zero rows touched" above
-- overstates what actually happens. Steps 1-3 (licence 'unknown', its six
-- licence_channel rows, and the field_definition row) are unconditional
-- INSERTs that DO touch rows on a fresh database -- eight rows total,
-- every time. "No-op" there means "never errors, never violates a
-- constraint" (ON CONFLICT DO NOTHING makes a RE-run a no-op, not the
-- first run) -- it does not mean zero rows written. Only steps 4-5 (the
-- FK-guarded source INSERT and jurisdiction UPDATE) are genuine zero-row
-- no-ops on a fresh database, because ca_san_jose does not exist yet at
-- migration time. The migration's own BEHAVIOUR is correct and intended
-- either way -- this corrects only the summary line's claim about it,
-- forward-only migrations are not rewritten after the fact.
--   1. licence 'unknown': no FK dependency on jurisdiction/source at all.
--      INSERT ... ON CONFLICT (id) DO NOTHING is safe unconditionally, same
--      shape cc0/cc_by_4_0 already use. licence is immutable (0027) with NO
--      IS NOT DISTINCT FROM carve-out in licence_no_update() -- confirmed by
--      reading the trigger body directly, not assumed -- so this can NEVER
--      be DO UPDATE; every seeder of this row must write byte-identical
--      values, forever, the same discipline check_golden.py's own
--      seed_reference_rows() already follows for cc_by_4_0.
--   2. licence_channel (six rows): FK to the licence row created in step 1,
--      within this same migration/transaction -- always satisfied. Also
--      ON CONFLICT DO NOTHING (licence_channel is immutable too, 0033, same
--      unconditional-raise shape -- confirmed by reading its trigger body).
--   3. field_definition 'jurisdiction.incorporated': no FK dependency on
--      jurisdiction/source. field_definition is NOT immutable (0026's own
--      precedent: correctable in place) -- ON CONFLICT DO NOTHING here is a
--      choice, not a constraint; nothing about this field's declaration is
--      expected to need correcting, so DO NOTHING matches every other new
--      field_definition row this repo has ever seeded.
--   4. source 'ca_san_jose.city_limits': jurisdiction_id has a real FK to
--      jurisdiction(id) (source_jurisdiction_id_fkey) -- and jurisdiction
--      rows are NEVER created by any migration in this repo's history
--      (confirmed: zero `INSERT INTO jurisdiction` across db/migrations/,
--      grepped directly). On a fresh database ca_san_jose does not exist
--      yet at migration time, so this INSERT is guarded with an EXISTS
--      check against jurisdiction -- CLAUDE.md's own documented pattern for
--      exactly this FK shape (0032: "Use INSERT ... SELECT ... WHERE id IN
--      (...) (or an equivalent existence guard) instead"). Zero rows
--      matched on a fresh database = true no-op, no FK violation. source
--      carries NO immutability trigger (confirmed directly -- no
--      source_no_update exists) -- ON CONFLICT (id) DO UPDATE is safe and
--      is the correct choice here: check_conformance.py already uses this
--      exact pattern for its own source rows (finding #32's fix, "so
--      seeding order can never matter to it"), and the SAME property
--      matters here between this migration and db/seeds/day4_sources.sql.
--   5. jurisdiction.boundary_source_id: guarded UPDATE, matching the
--      specific old value (IS NULL) in the WHERE clause -- the 0023/0026/
--      0030 pattern, not a blind UPDATE. On a fresh database ca_san_jose
--      does not exist yet, so zero rows match: true no-op. On an
--      already-seeded database, step 4 (same migration, same transaction)
--      has already guaranteed the FK target exists by the time this runs.
--      jurisdiction carries no immutability trigger either (confirmed
--      directly) -- this UPDATE is legal.
--
-- method='manual' on the city_limits source row, not sources.yaml's own
-- declared method: direct -- sources.yaml is a research lead ("every entry
-- ... not a verified production contract", sec 7), and no real, verified
-- San Jose city-limits endpoint has been found (P53-l0-gate.md Obstacle 2).
-- method='manual' satisfies source_endpoint_required (endpoint_url may be
-- NULL) without fabricating one. I13 then makes this source permanently
-- unable to produce a fact (FactMethod excludes 'manual') -- not a defect
-- for this design (P53-l0-gate.md Obstacle 3): D-C never needs this source
-- to produce a fact, only to exist as boundary_source_id's declared FK
-- target. It remains mutable (source carries no immutability trigger) --
-- correcting method/endpoint_url once a real endpoint is verified (a future
-- D-A pass) is an ordinary UPDATE, not a new-row-and-repoint operation.
--
-- observed_at on the 'unknown' licence: NOT the audit's own 2026-07-31
-- research baseline cc0/cc_by_4_0 use (that date is specific to the audit's
-- confirmed findings for Parcels/Zoning Districts/Active Building Permits --
-- no evidence ties city_limits to that same dated attempt, and reusing it
-- would misrepresent a shared provenance that has not been confirmed) --
-- this migration's own landing date instead, per the reading blessed in
-- P53-l0-gate.md sec 9 Q1: observed_at on an 'unknown' licence records the
-- date its UNKNOWN-NESS was recorded, never a date terms were read. The
-- disambiguation lives in `notes`, not only here, because a comment does
-- not travel with the row into a query result.

INSERT INTO licence (
  id, display_name, restriction, commercial_use, redistribution,
  attribution_text, terms_url, evidence_uri, observed_at, cleared_by, cleared_at, notes
) VALUES (
  'unknown',
  'Licence not yet observed',
  'unknown', 'unknown', 'unknown',
  NULL, NULL, NULL,
  '2026-08-22'::timestamptz,
  NULL, NULL,
  'LD-1 gate source (jurisdictions/ca_san_jose/sources.yaml: ca_san_jose.city_limits). '
  'Licence text never observed -- id, display_name and every restriction/commercial_use/'
  'redistribution value match jurisdictions/ca_san_jose/licences.yaml (docs/LEDGEX_SPEC.md '
  'sec 7.2, id=unknown) verbatim, not independently invented. '
  'observed_at records the date this row was created (the date its UNKNOWN-NESS was '
  'recorded), never a date on which the licence''s actual terms were read -- no such '
  'reading has ever happened. See prompts/P53-l0-gate.md.'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO licence_channel (licence_id, channel, allowed, rationale) VALUES
  ('unknown', 'free_snapshot', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'paid_property_file', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'api', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'bulk_export', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'analytics', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'model_training', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.')
ON CONFLICT (licence_id, channel) DO NOTHING;

INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
VALUES (
  'jurisdiction.incorporated', 'Jurisdiction incorporated', 'public_record', 'boolean',
  'jurisdiction',
  'Whether this parcel resolves within the jurisdiction''s incorporated boundary, per '
  'jurisdictions/ca_san_jose/sources.yaml''s own ca_san_jose.city_limits declaration '
  '(the L0 gate, sec 1.1). No source currently supplies this field as a fact -- see '
  'prompts/P53-l0-gate.md; the field is declared so the composer''s absence-check has a '
  'real field_key to require, not so a value exists yet.'
) ON CONFLICT (field_key) DO NOTHING;

INSERT INTO source (
  id, jurisdiction_id, display_name, steward, method, phase_status, phase_status_reason,
  endpoint_url, licence_id, active
)
SELECT
  'ca_san_jose.city_limits', 'ca_san_jose', 'City limits / jurisdiction boundary',
  'City of San José', 'manual', 'blocked_rights',
  'Licence not observed. Supplies the L0 gate, so under I6 this blocks ALL channels '
  'including free_snapshot. Launch dependency LD-1. Plan App K: "Blocked for paid output '
  '-- required for the jurisdiction gate; confirm licence." method=''manual'' here, not '
  'sources.yaml''s own declared method: direct -- no real, verified endpoint exists yet '
  '(P53-l0-gate.md Obstacle 2); this row exists as jurisdiction.boundary_source_id''s FK '
  'target, never as an ingest path (I13 forbids a manual source from ever producing a '
  'fact, by design -- see P53-l0-gate.md Obstacle 3).',
  NULL, 'unknown', false
WHERE EXISTS (SELECT 1 FROM jurisdiction WHERE id = 'ca_san_jose')
ON CONFLICT (id) DO UPDATE SET
  jurisdiction_id = EXCLUDED.jurisdiction_id,
  display_name = EXCLUDED.display_name,
  steward = EXCLUDED.steward,
  method = EXCLUDED.method,
  phase_status = EXCLUDED.phase_status,
  phase_status_reason = EXCLUDED.phase_status_reason,
  endpoint_url = EXCLUDED.endpoint_url,
  licence_id = EXCLUDED.licence_id,
  active = EXCLUDED.active;

UPDATE jurisdiction
   SET boundary_source_id = 'ca_san_jose.city_limits'
 WHERE id = 'ca_san_jose'
   AND boundary_source_id IS NULL;
