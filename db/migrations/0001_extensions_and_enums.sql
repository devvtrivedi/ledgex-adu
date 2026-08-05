-- 0001_extensions_and_enums.sql
-- Serves: C1-C9, I2, I3, I13.
-- Source: docs/LEDGEX_SPEC.md §3.1.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- portal / manual classify a SOURCE that cannot be machine-read. They are never
-- a fact method: no fact may originate from a human reading a portal (I13).
CREATE TYPE access_method     AS ENUM ('direct','bulk','portal','manual','derived');
CREATE TYPE use_restriction   AS ENUM ('open','attribution','noncommercial','no_resale','unknown');
CREATE TYPE permission_state  AS ENUM ('allowed','prohibited','unknown');
CREATE TYPE output_channel    AS ENUM ('free_snapshot','paid_property_file','api','bulk_export');
CREATE TYPE claim_type        AS ENUM ('public_record','third_party_record','estimate',
                                        'user_assumption','derived_conclusion');

CREATE TYPE conflict_state    AS ENUM ('agree','conflicts','stale','missing');
CREATE TYPE jurisdiction_tier AS ENUM ('tier_1','tier_2','tier_3','tier_4','blocked');
CREATE TYPE exception_type    AS ENUM ('record_to_ground','cross_source','staleness',
                                        'rule_boundary','coverage_gap','rights_gap');
CREATE TYPE exception_severity AS ENUM ('info','warning','blocking');
CREATE TYPE exception_outcome  AS ENUM ('open','confirmed','false_positive','unresolved');
CREATE TYPE file_status         AS ENUM ('composed','partial','refused');
CREATE TYPE job_status          AS ENUM ('running','succeeded','failed','skipped_unchanged');
CREATE TYPE support_category    AS ENUM ('data_dispute','missing_field','refusal_query',
                                          'billing','usability','other');

-- v1.2: Phase 1 posture for a declared source. 'deferred' means the source is
-- real and known but out of scope for Phase 1; its fields are declared coverage
-- gaps rather than silent omissions. See §7.4.
CREATE TYPE source_phase_status AS ENUM ('active','blocked_rights','blocked_engineering',
                                          'not_machine_readable','deferred','excluded');

-- fact.confidence (§3.6) is typed confidence_level in the spec text but no
-- CREATE TYPE for it appears anywhere in §3.1-§3.12. §3.8's current_fact view
-- relies on ascending enum declaration order to mean high < medium < low, so
-- that ordering is declared here, in the enum block 0006_fact.sql depends on.
CREATE TYPE confidence_level AS ENUM ('high','medium','low');

-- Removed in v1.2: there is no confidence_floor concept and no
-- CONFIDENCE_BELOW_THRESHOLD refusal. See §9.1.
