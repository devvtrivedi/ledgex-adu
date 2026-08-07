-- 0032_licence_channel_analytics_model_training.sql
-- Serves: I6, §7.3. C9.
--
-- Adds licence_channel rows for the two channel values 0031 just added
-- (analytics, model_training), for the two live licences (cc0,
-- cc_by_4_0). Split from 0031, not combined: PostgreSQL 12+ forbids using
-- an enum value added by ALTER TYPE ... ADD VALUE within the same
-- transaction that added it, so a migration that both adds the values and
-- inserts rows naming them would fail outright.
--
-- Both start allowed=false, the same Pending-clearance posture
-- 0030/finding #3 gives the four pre-existing channels: identification is
-- evidenced (Municipal Data & API Audit v1.1, observed 2026-07-31) but
-- counsel/owner sign-off is Pending per the audit's diligence register
-- (Evidence Index, p.36). model_training in particular stays denied for a
-- second, independent reason beyond sign-off: nobody has yet read either
-- licence's terms as applied specifically to model-training use, and
-- "open licence text implies open training use" is exactly the kind of
-- assumption finding #3 exists to stop making without evidence -- it
-- requires its own rationale before it can flip, not just the general
-- sign-off the other channels are waiting on.
--
-- db/seeds/day4_sources.sql is corrected in the same commit to seed these
-- same four rows going forward (this migration's own comment, and 0026's
-- precedent, both establish why a migration alone would otherwise be a
-- permanent no-op on every future fresh install: a fresh database applies
-- migrations before any seed runs, and a guarded UPDATE/INSERT here would
-- match nothing against an empty licence table, after which the
-- still-unedited seed file would insert the four rows without these two
-- new channels, forever). This migration exists for a database that was
-- ALREADY seeded (from any prior version of day4_sources.sql, since cc0/
-- cc_by_4_0 predate this commit) before 0031/0032 landed.
--
-- FK-SAFE, not a blind INSERT: a database that has only ever had
-- migrations applied -- CI's ledgex_ci, in particular; db.yml never runs
-- db/seeds/day4_sources.sql -- has no licence row with id 'cc0' or
-- 'cc_by_4_0' at all yet. A literal
--   INSERT INTO licence_channel (licence_id, channel, ...) VALUES ('cc0', ...)
-- would raise a foreign_key_violation on that database, not a harmless
-- no-op, since ON CONFLICT only suppresses a unique-constraint conflict,
-- not a missing parent row. INSERT ... SELECT ... FROM licence WHERE id IN
-- (...) instead: on a database where neither id exists, the SELECT
-- returns zero rows and the INSERT does nothing; on a database seeded
-- with the real San José licences, it inserts exactly the two new rows
-- per matching licence. Confirmed directly, not assumed: applied this
-- migration against both a migrations-only database and a fully-seeded
-- one before writing this comment.

INSERT INTO licence_channel (licence_id, channel, allowed, rationale)
SELECT l.id,
       c.channel,
       false,
       CASE c.channel
           WHEN 'model_training' THEN
               'Denied pending review: no one has yet read ' || l.id || '''s terms as applied specifically to model-training use, separately from counsel/owner sign-off on the licence generally. Requires its own rationale before this can flip.'
           ELSE
               'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'
       END
  FROM licence l
 CROSS JOIN unnest(ARRAY['analytics', 'model_training']::output_channel[]) AS c(channel)
 WHERE l.id IN ('cc0', 'cc_by_4_0')
ON CONFLICT (licence_id, channel) DO NOTHING;
