-- 0030_licence_channel_pending_clearance.sql
-- Serves: I6, §7.3. Finding #3.
--
-- THE DEFECT. db/seeds/day4_sources.sql opened all four output_channel
-- values for both cc0 and cc_by_4_0 with allowed=true, while licence.
-- cleared_by, cleared_at and evidence_uri are all NULL for both rows. The
-- audit's own diligence register (Municipal Data & API Audit v1.1, p.36,
-- Evidence Index) lists "San José licence confirmations -- Per-resource
-- channel posture and counsel/owner sign-off" as status "Pending" -- the
-- same Pending status the seed file's own comment already recorded next
-- to cleared_by/cleared_at, without the licence_channel rows below it
-- actually reflecting it. The original advice to open these channels was
-- wrong; a second, independent review caught it and reversed it.
--
-- Licence IDENTIFICATION is not the same thing as CLEARANCE. Identification
-- is evidenced -- the audit records Parcels/Zoning Districts as CC BY 4.0
-- and Active Building Permits as CC0 as of its 2026-07-31 research
-- baseline -- but I6 gates on rights being actually cleared for the
-- channel, not merely on the licence's identity being known. Per §7.3,
-- licence_channel is the sole runtime authority for channel eligibility;
-- nothing else (source.phase_status, Plan 2.1.4 Appendix K) grants access.
-- An open licence_channel row for a licence with no counsel/owner sign-off
-- is exactly the class of silent rights-broadening B2 and this migration's
-- companion (0031-0033's lock) exist to close, applied here to actual data
-- rather than to the schema's mutability.
--
-- allowed=false, not a deleted row: absence already denies under
-- default-deny (0002), but an explicit false with a rationale records the
-- decision and preserves the audit trail; a deleted row records nothing.
-- Nothing composes or outputs today -- no ingestion has run, no composer
-- exists yet -- so this costs nothing now and forces a conscious
-- per-channel decision, with a written rationale, whenever the composer
-- arrives and sign-off has actually happened.
--
-- SEQUENCING. This migration must land, and be applied, BEFORE
-- 0033_licence_channel_immutability.sql locks licence_channel against
-- UPDATE. Correcting the rows has to happen while they are still mutable;
-- once 0033 applies, only a new licence row could ever supply a different
-- channel decision (see 0033's header). C9's new analytics/model_training
-- channel rows (0032) are seeded allowed=false from birth and need no
-- correction of their own, but land after this migration and before the
-- lock for the same reason.
--
-- GUARDED, not a blind UPDATE (0023's pattern): matches licence_id,
-- channel AND the specific old allowed=true value in the WHERE clause. A
-- database seeded from the now-corrected db/seeds/day4_sources.sql (same
-- commit as this migration) already has allowed=false for all eight rows,
-- so every WHERE clause below matches zero rows there -- this migration is
-- a true no-op on any database seeded from the corrected file, and a real
-- correction only on a database seeded before it. Confirmed directly, not
-- assumed: applying this migration twice in a row against the same
-- database is idempotent (second run touches 0 rows), the same property
-- 0023 and 0026 establish for their own guarded UPDATEs.
--
-- Rationale text matches the corrected seed file's wording exactly, so a
-- database corrected by this migration and a database seeded fresh from
-- the corrected file converge on byte-identical rows.

UPDATE licence_channel
SET allowed = false,
    rationale = 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'
WHERE licence_id = 'cc0'
  AND channel = 'free_snapshot'
  AND allowed = true
  AND rationale = 'CC0 1.0: no restriction on use, redistribution or commercial use';

UPDATE licence_channel
SET allowed = false,
    rationale = 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'
WHERE licence_id = 'cc0'
  AND channel = 'paid_property_file'
  AND allowed = true
  AND rationale = 'CC0 1.0: no restriction on use, redistribution or commercial use';

UPDATE licence_channel
SET allowed = false,
    rationale = 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'
WHERE licence_id = 'cc0'
  AND channel = 'api'
  AND allowed = true
  AND rationale = 'CC0 1.0: no restriction on use, redistribution or commercial use';

UPDATE licence_channel
SET allowed = false,
    rationale = 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'
WHERE licence_id = 'cc0'
  AND channel = 'bulk_export'
  AND allowed = true
  AND rationale = 'CC0 1.0: no restriction on use, redistribution or commercial use';

UPDATE licence_channel
SET allowed = false,
    rationale = 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'
WHERE licence_id = 'cc_by_4_0'
  AND channel = 'free_snapshot'
  AND allowed = true
  AND rationale = 'CC BY 4.0: permits commercial use and redistribution with attribution';

UPDATE licence_channel
SET allowed = false,
    rationale = 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'
WHERE licence_id = 'cc_by_4_0'
  AND channel = 'paid_property_file'
  AND allowed = true
  AND rationale = 'CC BY 4.0: permits commercial use and redistribution with attribution';

UPDATE licence_channel
SET allowed = false,
    rationale = 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'
WHERE licence_id = 'cc_by_4_0'
  AND channel = 'api'
  AND allowed = true
  AND rationale = 'CC BY 4.0: permits commercial use and redistribution with attribution';

UPDATE licence_channel
SET allowed = false,
    rationale = 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'
WHERE licence_id = 'cc_by_4_0'
  AND channel = 'bulk_export'
  AND allowed = true
  AND rationale = 'CC BY 4.0: permits commercial use and redistribution with attribution';

-- NOT corrected here, reported instead: licence.commercial_use and
-- licence.redistribution are both 'allowed' for cc0 and cc_by_4_0 against
-- cleared_by IS NULL -- 'unknown' is the honest value under I6 (unknown
-- rights block) and it blocks. licence_no_update (0027) raises
-- unconditionally on any UPDATE licence, with no carve-out for a row no
-- fact yet cites -- confirmed zero fact rows reference either id (no
-- ingestion has run) -- so the specific harm 0027 exists to prevent has
-- not occurred here, but the trigger does not check that; it still blocks.
-- Correcting these columns is therefore not possible via UPDATE, and not
-- possible via delete-and-reinsert either (licence_no_delete raises
-- unconditionally too). The only correction path under 0027's own rule --
-- "a changed licence is a new licence row with a new id, never an UPDATE"
-- -- is a new licence row (new id), fresh licence_channel rows for it, and
-- repointing source.licence_id (an ordinary mutable column) at the new id;
-- the old cc0/cc_by_4_0 rows would remain in the table forever, immutable
-- and orphaned. That is a materially bigger, separate change (new ids,
-- FK repointing across three source rows) than this migration's scope,
-- and this migration's own fix already makes it moot for today's output:
-- §7.3 makes licence_channel the sole channel-eligibility authority, and
-- with every channel above now denied, nothing composes regardless of
-- what commercial_use/redistribution claim. Flagged as a gap in 0027's
-- scope -- no carve-out for a licence row not yet cited by any fact --
-- not fixed here.
