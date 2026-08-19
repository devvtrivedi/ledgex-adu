-- 0052_property_file_election.sql
-- Serves: I11, I13, I14. README finding #35. P34.
-- Source: docs/LEDGEX_SPEC.md §3.12, §7 field vocabulary.
--
-- THE GAP. README finding #35 (P32): Bulletin #210 page 3 states an
-- applicant electing an ADU under San Jose Municipal Code 20.80.175 (City
-- standards) or 20.80.176 (State standards) gets materially different
-- answers for the same conclusion (detached ADU max height: 25 ft City,
-- 18 ft State) and must choose one -- "the standards cannot be mixed."
-- Nothing in this schema recorded which regime produced a given
-- property_file. P33 chose the design (election-as-request-parameter,
-- refusal as fallback); this migration is the storage half.
--
-- WHY A COLUMN, NOT JUST A REQUEST PARAMETER. scripts/compose_property_file.py's
-- compose() gains an `election` parameter (P34) that is read once, at
-- request time, and never persisted to the fact ledger (I13: an election
-- is the applicant's own design choice about their project, not a claim
-- about the world -- see prompts/P33-correct-36-close-37-design-35.md
-- section 3's verbatim §7 precedent argument). But the FILE this request
-- produces is a durable, auditable row. Checked against §6.6's own
-- normalize() (scripts/check_golden.py) before deciding this, not
-- assumed: normalize() has no special handling for any column outside
-- STRIPPED_FIELDS/TS_FIELDS/as_of -- everything else, including this new
-- column, falls through compared literally. Without recording which
-- election produced a property_file, a stored file whose ruleset_version
-- depended on that election would be unreproducible -- nothing in the row
-- would say which regime applied, so a later audit or re-derivation would
-- be guessing. Same class of gap I11 exists to prevent for rules
-- generally, applied here to the one input that decides WHICH rule
-- applied.
--
-- NULLABLE, ON PURPOSE, AND WHAT NULL MEANS -- stated explicitly per
-- CONVENTIONS.md's "NULL inside a constraint silently disables it" rule
-- (README findings #8/#19 precedent). election is NULL whenever this
-- composition never touched a conclusion whose rule depends on an
-- election at all -- a real, legitimate, common state (every conclusion
-- this composer knows about today besides "placement" needs no election),
-- NOT "unknown" and NOT "defaulted to city". The CHECK below is written
-- as an explicit `election IS NULL OR election IN (...)` guard, so NULL
-- always passes -- this is the "possible and handled" branch CONVENTIONS
-- requires naming: NULL is not silently unconstrained-but-pretending-to-
-- validate here, it is the documented, correct value for the
-- election-irrelevant case, and the CHECK still fully constrains every
-- non-NULL value to exactly the two literal regimes Bulletin #210 names.
-- A composition that DOES touch an election-dependent conclusion with no
-- election supplied does not leave this column NULL by omission -- it
-- refuses ELECTION_REQUIRED (0053, same package) before ever reaching the
-- INSERT; NULL here never means "the applicant should have picked one and
-- didn't," only "picking one was never relevant to this file."
--
-- TEXT + CHECK, not a new enum type -- same pattern this schema already
-- uses for jurisdiction.kind (0002) rather than inventing a two-value
-- Postgres ENUM type whose name would collide in spirit with the column
-- it types. Two literal values only, matching Bulletin #210's own
-- vocabulary exactly ("City Standards" / "State Standards") and the
-- `.city_standards` / `.state_standards` rule_key suffix shape finding
-- #35 already established.
--
-- EXISTING ROWS. Checked before writing this migration, not assumed:
-- every property_file row on every database reachable from this session
-- today predates this column entirely (ADD COLUMN with no default backs
-- every existing row with NULL, not a fabricated election) -- correct,
-- since every property_file composed so far touched no election-dependent
-- conclusion at all (P31's own placement rule_key was still keyed
-- city-only, unconditionally, until this package).

ALTER TABLE property_file ADD COLUMN election text;

ALTER TABLE property_file ADD CONSTRAINT property_file_election_known
    CHECK (election IS NULL OR election IN ('city', 'state'));

COMMENT ON COLUMN property_file.election IS
    'Which of Bulletin #210''s two ADU development-standards regimes (City, Municipal Code 20.80.175; State, 20.80.176) this composition used, when relevant. NULL means no conclusion in this file depended on an election, not "unknown" and not a silent default to city -- a composition that DOES touch an election-dependent conclusion with no election supplied refuses ELECTION_REQUIRED (0053) before this row is ever written. Read-only provenance of a request-scoped parameter (scripts/compose_property_file.py''s compose(), I13) -- never itself a fact, never written back to the fact ledger. See README finding #35 and 0052''s own header for the full argument.';
