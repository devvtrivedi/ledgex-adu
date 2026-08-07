--
-- PostgreSQL database dump
--

\restrict ledgexschemadumpfixedkey


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: postgis; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;


--
-- Name: EXTENSION postgis; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION postgis IS 'PostGIS geometry and geography spatial types and functions';


--
-- Name: access_method; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.access_method AS ENUM (
    'direct',
    'bulk',
    'portal',
    'manual',
    'derived'
);


--
-- Name: claim_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.claim_type AS ENUM (
    'public_record',
    'third_party_record',
    'estimate',
    'user_assumption',
    'derived_conclusion'
);


--
-- Name: confidence_level; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.confidence_level AS ENUM (
    'high',
    'medium',
    'low'
);


--
-- Name: conflict_state; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.conflict_state AS ENUM (
    'agree',
    'conflicts',
    'stale',
    'missing'
);


--
-- Name: exception_outcome; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.exception_outcome AS ENUM (
    'open',
    'confirmed',
    'false_positive',
    'unresolved'
);


--
-- Name: exception_severity; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.exception_severity AS ENUM (
    'info',
    'warning',
    'blocking'
);


--
-- Name: exception_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.exception_type AS ENUM (
    'record_to_ground',
    'cross_source',
    'staleness',
    'rule_boundary',
    'coverage_gap',
    'rights_gap'
);


--
-- Name: file_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.file_status AS ENUM (
    'composed',
    'partial',
    'refused'
);


--
-- Name: job_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.job_status AS ENUM (
    'running',
    'succeeded',
    'failed',
    'skipped_unchanged'
);


--
-- Name: jurisdiction_tier; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.jurisdiction_tier AS ENUM (
    'tier_1',
    'tier_2',
    'tier_3',
    'tier_4',
    'blocked'
);


--
-- Name: output_channel; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.output_channel AS ENUM (
    'free_snapshot',
    'paid_property_file',
    'api',
    'bulk_export',
    'analytics',
    'model_training'
);


--
-- Name: permission_state; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.permission_state AS ENUM (
    'allowed',
    'prohibited',
    'unknown'
);


--
-- Name: review_mode; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.review_mode AS ENUM (
    'independent',
    'solo_founder_attestation'
);


--
-- Name: source_phase_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.source_phase_status AS ENUM (
    'active',
    'blocked_rights',
    'blocked_engineering',
    'not_machine_readable',
    'deferred',
    'excluded'
);


--
-- Name: supersession_reason; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.supersession_reason AS ENUM (
    'world_change',
    'source_correction',
    'refetch_no_change',
    'ingestion_logic_change',
    'unknown'
);


--
-- Name: support_category; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.support_category AS ENUM (
    'data_dispute',
    'missing_field',
    'refusal_query',
    'billing',
    'usability',
    'other'
);


--
-- Name: use_restriction; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.use_restriction AS ENUM (
    'open',
    'attribution',
    'noncommercial',
    'no_resale',
    'unknown'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: fact; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fact (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    parcel_id uuid NOT NULL,
    field_key text NOT NULL,
    value jsonb NOT NULL,
    unit text,
    local_verbatim text,
    source_id text,
    source_url text,
    layer_item_id text,
    snapshot_id text,
    method public.access_method NOT NULL,
    retrieved_at timestamp with time zone,
    source_published_at timestamp with time zone,
    source_cadence_stated text,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    recorded_at timestamp with time zone DEFAULT now() NOT NULL,
    superseded_at timestamp with time zone,
    licence_id text NOT NULL,
    confidence public.confidence_level NOT NULL,
    confidence_rule_id text NOT NULL,
    conflict public.conflict_state DEFAULT 'agree'::public.conflict_state NOT NULL,
    method_version text,
    ruleset_version text,
    pack_version text NOT NULL,
    jurisdiction_id text NOT NULL,
    supersedes_fact_id uuid,
    supersession_reason public.supersession_reason,
    source_asserted_as_of timestamp with time zone,
    CONSTRAINT fact_method_automated CHECK ((method = ANY (ARRAY['direct'::public.access_method, 'bulk'::public.access_method, 'derived'::public.access_method]))),
    CONSTRAINT fact_provenance_complete CHECK ((((method = 'derived'::public.access_method) AND (source_id IS NULL) AND (snapshot_id IS NULL) AND (method_version IS NOT NULL)) OR ((method <> 'derived'::public.access_method) AND (source_id IS NOT NULL) AND (snapshot_id IS NOT NULL) AND (retrieved_at IS NOT NULL) AND (source_url IS NOT NULL)))),
    CONSTRAINT fact_supersedes_not_self CHECK ((supersedes_fact_id <> id)),
    CONSTRAINT fact_supersession_reason_biconditional CHECK ((((supersedes_fact_id IS NULL) AND (supersession_reason IS NULL)) OR ((supersedes_fact_id IS NOT NULL) AND (supersession_reason IS NOT NULL)))),
    CONSTRAINT fact_txn_time CHECK (((superseded_at IS NULL) OR (superseded_at >= recorded_at))),
    CONSTRAINT fact_valid_time CHECK (((effective_to IS NULL) OR (effective_to > effective_from)))
);


--
-- Name: current_fact_at(timestamp with time zone); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.current_fact_at(ts timestamp with time zone) RETURNS SETOF public.fact
    LANGUAGE sql STABLE
    AS $$
    SELECT DISTINCT ON (f.parcel_id, f.field_key)
           f.*
      FROM fact f
      JOIN parcel p ON p.id = f.parcel_id
      LEFT JOIN source_rank sr
             ON sr.jurisdiction_id = p.jurisdiction_id
            AND sr.field_key       = f.field_key
            AND sr.source_id       = f.source_id
     WHERE f.recorded_at <= ts
       AND (f.superseded_at IS NULL OR f.superseded_at > ts)
       AND f.effective_from <= ts
       AND (f.effective_to IS NULL OR f.effective_to > ts)
     ORDER BY f.parcel_id, f.field_key,
              COALESCE(sr.rank, 999) ASC,
              f.confidence ASC,                      -- enum order: high < medium < low
              f.retrieved_at DESC NULLS LAST,
              f.id;                                   -- deterministic tiebreak; no ranking meaning
$$;


--
-- Name: fact_licence_validate(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fact_licence_validate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    target_fact_id            uuid;
    actual_licence             text;
    has_inputs                 boolean;
    over_permitted_channel     public.output_channel;
    commercial_violation       boolean;
    redistribution_violation   boolean;
    any_input_requires_attrib  boolean;
BEGIN
    target_fact_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.fact_id ELSE NEW.fact_id END;

    SELECT EXISTS (SELECT 1 FROM fact_input WHERE fact_id = target_fact_id) INTO has_inputs;
    IF NOT has_inputs THEN
        RETURN NULL;  -- I5c: no inputs recorded yet; nothing to validate against.
    END IF;

    SELECT licence_id INTO actual_licence FROM fact WHERE id = target_fact_id;

    -- Channel dimension: a channel the derived licence permits, that at
    -- least one input's licence does not permit (no matching allowed=true
    -- row for that input), is a violation.
    SELECT lc.channel INTO over_permitted_channel
      FROM licence_channel lc
     WHERE lc.licence_id = actual_licence
       AND lc.allowed = true
       AND EXISTS (
           SELECT 1
             FROM fact_input fi
             JOIN fact f ON f.id = fi.input_fact_id
            WHERE fi.fact_id = target_fact_id
              AND NOT EXISTS (
                  SELECT 1 FROM licence_channel lc2
                   WHERE lc2.licence_id = f.licence_id
                     AND lc2.channel = lc.channel
                     AND lc2.allowed = true
              )
       )
     LIMIT 1;

    IF over_permitted_channel IS NOT NULL THEN
        RAISE EXCEPTION
            'I5 violated: derived fact % licence % permits channel %, which at '
            'least one input does not permit. A derived fact''s licence may '
            'permit a channel only if every input''s licence also permits it.',
            target_fact_id, actual_licence, over_permitted_channel;
    END IF;

    -- commercial_use: derived may claim 'allowed' only if every input does.
    IF (SELECT commercial_use FROM licence WHERE id = actual_licence) = 'allowed' THEN
        SELECT EXISTS (
            SELECT 1
              FROM fact_input fi
              JOIN fact    f ON f.id = fi.input_fact_id
              JOIN licence l ON l.id = f.licence_id
             WHERE fi.fact_id = target_fact_id
               AND l.commercial_use <> 'allowed'
        ) INTO commercial_violation;

        IF commercial_violation THEN
            RAISE EXCEPTION
                'I5 violated: derived fact % licence % claims commercial_use='
                'allowed, but at least one input does not.',
                target_fact_id, actual_licence;
        END IF;
    END IF;

    -- redistribution: same shape as commercial_use.
    IF (SELECT redistribution FROM licence WHERE id = actual_licence) = 'allowed' THEN
        SELECT EXISTS (
            SELECT 1
              FROM fact_input fi
              JOIN fact    f ON f.id = fi.input_fact_id
              JOIN licence l ON l.id = f.licence_id
             WHERE fi.fact_id = target_fact_id
               AND l.redistribution <> 'allowed'
        ) INTO redistribution_violation;

        IF redistribution_violation THEN
            RAISE EXCEPTION
                'I5 violated: derived fact % licence % claims redistribution='
                'allowed, but at least one input does not.',
                target_fact_id, actual_licence;
        END IF;
    END IF;

    -- attribution: sticky, not a permission subset. If any input requires
    -- it, the derived fact must require it too.
    SELECT EXISTS (
        SELECT 1
          FROM fact_input fi
          JOIN fact    f ON f.id = fi.input_fact_id
          JOIN licence l ON l.id = f.licence_id
         WHERE fi.fact_id = target_fact_id
           AND l.restriction = 'attribution'
    ) INTO any_input_requires_attrib;

    IF any_input_requires_attrib
       AND (SELECT restriction FROM licence WHERE id = actual_licence) <> 'attribution'
    THEN
        RAISE EXCEPTION
            'I5 violated: derived fact % licence % does not require '
            'attribution, but at least one input does.',
            target_fact_id, actual_licence;
    END IF;

    RETURN NULL;                             -- ignored for an AFTER trigger
END;
$$;


--
-- Name: fact_no_delete(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fact_no_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION
        'I4 violated: fact % cannot be deleted. Corrections supersede, '
        'never delete.', OLD.id;
END;
$$;


--
-- Name: fact_no_destructive_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fact_no_destructive_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF OLD.superseded_at IS NOT NULL THEN
        RAISE EXCEPTION
            'I4 violated: fact % is already superseded and cannot be '
            'modified again.', OLD.id;
    END IF;

    IF NEW.superseded_at IS NULL THEN
        RAISE EXCEPTION
            'I4 violated: fact % cannot be updated. Supersede it (set '
            'superseded_at) and insert a new fact row for a correction '
            'instead.', OLD.id;
    END IF;

    IF NEW.id                       IS DISTINCT FROM OLD.id
       OR NEW.parcel_id             IS DISTINCT FROM OLD.parcel_id
       OR NEW.field_key             IS DISTINCT FROM OLD.field_key
       OR NEW.value                 IS DISTINCT FROM OLD.value
       OR NEW.unit                  IS DISTINCT FROM OLD.unit
       OR NEW.local_verbatim        IS DISTINCT FROM OLD.local_verbatim
       OR NEW.source_id             IS DISTINCT FROM OLD.source_id
       OR NEW.source_url            IS DISTINCT FROM OLD.source_url
       OR NEW.layer_item_id         IS DISTINCT FROM OLD.layer_item_id
       OR NEW.snapshot_id           IS DISTINCT FROM OLD.snapshot_id
       OR NEW.method                IS DISTINCT FROM OLD.method
       OR NEW.retrieved_at          IS DISTINCT FROM OLD.retrieved_at
       OR NEW.source_published_at   IS DISTINCT FROM OLD.source_published_at
       OR NEW.source_cadence_stated IS DISTINCT FROM OLD.source_cadence_stated
       OR NEW.effective_from        IS DISTINCT FROM OLD.effective_from
       OR NEW.effective_to          IS DISTINCT FROM OLD.effective_to
       OR NEW.recorded_at           IS DISTINCT FROM OLD.recorded_at
       OR NEW.licence_id            IS DISTINCT FROM OLD.licence_id
       OR NEW.confidence            IS DISTINCT FROM OLD.confidence
       OR NEW.confidence_rule_id    IS DISTINCT FROM OLD.confidence_rule_id
       OR NEW.conflict              IS DISTINCT FROM OLD.conflict
       OR NEW.method_version        IS DISTINCT FROM OLD.method_version
       OR NEW.ruleset_version       IS DISTINCT FROM OLD.ruleset_version
       OR NEW.pack_version          IS DISTINCT FROM OLD.pack_version
    THEN
        RAISE EXCEPTION
            'I4 violated: fact % is immutable. Only superseded_at may be '
            'set (NULL -> now, once). Insert a new fact row for a '
            'correction.', OLD.id;
    END IF;

    RETURN NEW;
END;
$$;


--
-- Name: licence_channel_no_delete(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.licence_channel_no_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION
        'B2/I6 violated: licence_channel row (%, %) cannot be deleted. '
        'Every fact that cites this licence depends on it for the '
        'channel-eligibility record; deleting it would invalidate their '
        'rights history without touching them, and would also silently '
        'fall back to licence_channel''s own default-deny rather than '
        'leaving a decision on record.', OLD.licence_id, OLD.channel;
END;
$$;


--
-- Name: licence_channel_no_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.licence_channel_no_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION
        'B2/I6 violated: licence_channel row (%, %) is immutable. A '
        'changed channel decision is a new licence row with a new id, '
        'never an UPDATE to an existing licence_channel row -- every fact '
        'that already cites this licence depends on its rights position '
        'staying exactly as recorded.', OLD.licence_id, OLD.channel;
END;
$$;


--
-- Name: licence_no_delete(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.licence_no_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION
        'B2/I3 violated: licence % cannot be deleted. Every fact and '
        'snapshot that cites it depends on it for provenance; deleting '
        'it would invalidate their rights history without touching '
        'them.', OLD.id;
END;
$$;


--
-- Name: licence_no_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.licence_no_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION
        'B2/I3 violated: licence % is immutable. A changed licence is a '
        'new licence row with a new id, never an UPDATE to an existing '
        'one -- every fact that already cites this licence depends on '
        'its terms staying exactly as recorded.', OLD.id;
END;
$$;


--
-- Name: refusals_codes_valid(jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.refusals_codes_valid(refusals jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM jsonb_array_elements(refusals) AS elem
        WHERE elem ->> 'code' NOT IN (
            'JURISDICTION_UNRESOLVED',
            'JURISDICTION_UNSUPPORTED',
            'JURISDICTION_BOUNDARY_CONFLICT',
            'PARCEL_NOT_FOUND',
            'SOURCE_UNVERIFIED',
            'SOURCE_UNAVAILABLE',
            'SOURCE_NOT_MACHINE_READABLE',
            'SOURCE_DEFERRED',
            'CROSSWALK_UNMAPPED',
            'RULE_UNAVAILABLE',
            'PERMIT_SERIES_TOO_SHALLOW',
            'GEOMETRY_TIER_DISABLED',
            'COVERAGE_GAP',
            'PERMIT_LAYER_UNAVAILABLE',
            'RIGHTS_BLOCKED',
            'LICENCE_UNKNOWN',
            'INSUFFICIENT_COVERAGE',
            'DISCLOSURE_NOT_ACCEPTED',
            'ACCESS_NOT_ENTITLED'
        )
    );
$$;


--
-- Name: rule_no_delete(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.rule_no_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION
        'I18 violated: rule % cannot be deleted. A correction is a new '
        'rule row at version + 1, never a DELETE.', OLD.id;
END;
$$;


--
-- Name: rule_no_destructive_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.rule_no_destructive_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- One-way retirement: NULL -> a date is the only permitted change.
    -- Once effective_to is set, IS NOT NULL is true for every subsequent
    -- update attempt, so this single guard rejects both date -> NULL and
    -- date -> a different date; it never fires for the NULL -> date case,
    -- since OLD.effective_to is NULL there.
    IF NEW.effective_to IS DISTINCT FROM OLD.effective_to
       AND OLD.effective_to IS NOT NULL
    THEN
        RAISE EXCEPTION
            'I18 violated: rule % effective_to is already set to % and '
            'cannot be changed again (attempted %). A correction is a new '
            'rule row at version + 1, never an UPDATE.',
            OLD.id, OLD.effective_to, NEW.effective_to;
    END IF;

    IF NEW.id                IS DISTINCT FROM OLD.id
       OR NEW.jurisdiction_id IS DISTINCT FROM OLD.jurisdiction_id
       OR NEW.rule_key        IS DISTINCT FROM OLD.rule_key
       OR NEW.version         IS DISTINCT FROM OLD.version
       OR NEW.effective_from  IS DISTINCT FROM OLD.effective_from
       OR NEW.citation        IS DISTINCT FROM OLD.citation
       OR NEW.source_text_uri IS DISTINCT FROM OLD.source_text_uri
       OR NEW.params          IS DISTINCT FROM OLD.params
       OR NEW.pack_version    IS DISTINCT FROM OLD.pack_version
       OR NEW.authored_by     IS DISTINCT FROM OLD.authored_by
       OR NEW.reviewed_by     IS DISTINCT FROM OLD.reviewed_by
       OR NEW.review_mode     IS DISTINCT FROM OLD.review_mode
       OR NEW.reviewed_at     IS DISTINCT FROM OLD.reviewed_at
       OR NEW.attestation_uri IS DISTINCT FROM OLD.attestation_uri
    THEN
        RAISE EXCEPTION
            'I18 violated: rule % is immutable. Only effective_to may be '
            'set (NULL -> a date, once). A correction is a new rule row at '
            'version + 1, never an UPDATE.', OLD.id;
    END IF;

    RETURN NEW;
END;
$$;


--
-- Name: snapshot_no_delete(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.snapshot_no_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION
        'C2 violated: snapshot % cannot be deleted. Every fact that cites '
        'it depends on it for reconstruction; deleting it would '
        'invalidate those facts'' provenance without touching them.', OLD.id;
END;
$$;


--
-- Name: snapshot_no_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.snapshot_no_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION
        'C2 violated: snapshot % is immutable. There is no supersession '
        'concept for a snapshot -- fetch again and insert a new snapshot '
        'row instead of editing this one.', OLD.id;
END;
$$;


--
-- Name: current_fact; Type: MATERIALIZED VIEW; Schema: public; Owner: -
--

CREATE MATERIALIZED VIEW public.current_fact AS
 SELECT id,
    parcel_id,
    field_key,
    value,
    unit,
    local_verbatim,
    source_id,
    source_url,
    layer_item_id,
    snapshot_id,
    method,
    retrieved_at,
    source_published_at,
    source_cadence_stated,
    effective_from,
    effective_to,
    recorded_at,
    superseded_at,
    licence_id,
    confidence,
    confidence_rule_id,
    conflict,
    method_version,
    ruleset_version,
    pack_version,
    jurisdiction_id,
    supersedes_fact_id,
    supersession_reason,
    source_asserted_as_of
   FROM public.current_fact_at(now()) current_fact_at(id, parcel_id, field_key, value, unit, local_verbatim, source_id, source_url, layer_item_id, snapshot_id, method, retrieved_at, source_published_at, source_cadence_stated, effective_from, effective_to, recorded_at, superseded_at, licence_id, confidence, confidence_rule_id, conflict, method_version, ruleset_version, pack_version, jurisdiction_id, supersedes_fact_id, supersession_reason, source_asserted_as_of)
  WITH NO DATA;


--
-- Name: exception_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exception_evidence (
    exception_id uuid NOT NULL,
    fact_id uuid NOT NULL,
    role text NOT NULL,
    parcel_id uuid NOT NULL
);


--
-- Name: fact_input; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fact_input (
    fact_id uuid NOT NULL,
    input_fact_id uuid NOT NULL,
    ordinal smallint NOT NULL,
    role text NOT NULL,
    CONSTRAINT fact_input_not_self CHECK ((fact_id <> input_fact_id))
);


--
-- Name: field_definition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.field_definition (
    field_key text NOT NULL,
    display_name text NOT NULL,
    claim public.claim_type NOT NULL,
    value_type text NOT NULL,
    unit text,
    enum_values text[],
    category text NOT NULL,
    stale_after_days integer,
    required_for_file boolean DEFAULT false NOT NULL,
    phase1_deferred boolean DEFAULT false NOT NULL,
    deferral_reason text,
    description text NOT NULL,
    CONSTRAINT field_deferral_reason_present CHECK (((phase1_deferred = false) OR (deferral_reason IS NOT NULL))),
    CONSTRAINT field_deferred_not_required CHECK (((phase1_deferred = false) OR (required_for_file = false))),
    CONSTRAINT field_definition_value_type_check CHECK ((value_type = ANY (ARRAY['string'::text, 'number'::text, 'boolean'::text, 'date'::text, 'geometry'::text, 'enum'::text, 'object'::text]))),
    CONSTRAINT field_enum_values_present CHECK (((value_type <> 'enum'::text) OR (enum_values IS NOT NULL))),
    CONSTRAINT field_unit_for_number CHECK (((value_type <> 'number'::text) OR (unit IS NOT NULL)))
);


--
-- Name: job_run; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_run (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_key text NOT NULL,
    jurisdiction_id text,
    source_id text,
    status public.job_status DEFAULT 'running'::public.job_status NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    snapshot_id text,
    rows_in integer,
    rows_out integer,
    schema_drift jsonb,
    error text,
    CONSTRAINT job_run_finished_after_started CHECK (((finished_at IS NULL) OR (finished_at >= started_at))),
    CONSTRAINT job_run_rows_in_nonnegative CHECK (((rows_in IS NULL) OR (rows_in >= 0))),
    CONSTRAINT job_run_rows_out_nonnegative CHECK (((rows_out IS NULL) OR (rows_out >= 0))),
    CONSTRAINT job_run_status_finished_at_biconditional CHECK ((((status = 'running'::public.job_status) AND (finished_at IS NULL)) OR ((status <> 'running'::public.job_status) AND (finished_at IS NOT NULL))))
);


--
-- Name: jurisdiction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jurisdiction (
    id text NOT NULL,
    display_name text NOT NULL,
    kind text NOT NULL,
    parent_id text,
    state_code character(2) NOT NULL,
    tier public.jurisdiction_tier DEFAULT 'blocked'::public.jurisdiction_tier NOT NULL,
    pack_version text NOT NULL,
    boundary_source_id text,
    geometry_tier_enabled boolean DEFAULT false NOT NULL,
    supported boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT jurisdiction_kind_check CHECK ((kind = ANY (ARRAY['city'::text, 'county'::text, 'state'::text])))
);


--
-- Name: licence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.licence (
    id text NOT NULL,
    display_name text NOT NULL,
    restriction public.use_restriction NOT NULL,
    commercial_use public.permission_state DEFAULT 'unknown'::public.permission_state NOT NULL,
    redistribution public.permission_state DEFAULT 'unknown'::public.permission_state NOT NULL,
    attribution_text text,
    terms_url text,
    evidence_uri text,
    observed_at timestamp with time zone NOT NULL,
    cleared_by text,
    cleared_at timestamp with time zone,
    notes text,
    CONSTRAINT licence_attribution_present CHECK (((restriction <> 'attribution'::public.use_restriction) OR (attribution_text IS NOT NULL)))
);


--
-- Name: licence_channel; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.licence_channel (
    licence_id text NOT NULL,
    channel public.output_channel NOT NULL,
    allowed boolean NOT NULL,
    rationale text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: parcel; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parcel (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    jurisdiction_id text NOT NULL,
    apn text,
    situs_address text,
    geom public.geometry(MultiPolygon,4326),
    centroid public.geometry(Point,4326),
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: COLUMN parcel.apn; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.parcel.apn IS 'Non-authoritative cache of the most recently observed parcel.apn fact -- NOT unique (49 confirmed source collisions), NOT required (9 confirmed source blanks; also NULL for a parcel whose only identifying feature carried an unresolved "???" placeholder, per policy: no fact is written for a non-value, so no cache value exists either). The fact ledger (query current_fact / fact for field_key=''parcel.apn'') is authoritative; this column reflects it only as of the last write and does not update on supersession. See 0034 for the evidence this was demoted on.';


--
-- Name: COLUMN parcel.situs_address; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.parcel.situs_address IS 'Non-authoritative cache of the most recently observed parcel.situs_address fact, same status as parcel.apn -- see its comment. Currently always NULL: ca_san_jose.parcels does not supply an address-shaped property (0026), so no fact and no cache value exists yet for any row.';


--
-- Name: parcel_exception; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parcel_exception (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    parcel_id uuid NOT NULL,
    jurisdiction_id text NOT NULL,
    type public.exception_type NOT NULL,
    severity public.exception_severity NOT NULL,
    detector_key text NOT NULL,
    detector_version text NOT NULL,
    ruleset_version text,
    detail jsonb NOT NULL,
    detected_at timestamp with time zone DEFAULT now() NOT NULL,
    outcome public.exception_outcome DEFAULT 'open'::public.exception_outcome NOT NULL,
    resolved_at timestamp with time zone,
    resolved_by text,
    resolution_notes text,
    CONSTRAINT parcel_exception_outcome_resolution_biconditional CHECK ((((outcome = 'open'::public.exception_outcome) AND (resolved_at IS NULL) AND (resolved_by IS NULL)) OR ((outcome <> 'open'::public.exception_outcome) AND (resolved_at IS NOT NULL) AND (resolved_by IS NOT NULL)))),
    CONSTRAINT parcel_exception_resolved_after_detected CHECK (((resolved_at IS NULL) OR (resolved_at >= detected_at)))
);


--
-- Name: property_file; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.property_file (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    parcel_id uuid NOT NULL,
    jurisdiction_id text NOT NULL,
    channel public.output_channel NOT NULL,
    status public.file_status NOT NULL,
    composed_at timestamp with time zone DEFAULT now() NOT NULL,
    as_of timestamp with time zone NOT NULL,
    pack_version text NOT NULL,
    ruleset_version text NOT NULL,
    composer_version text NOT NULL,
    geometry_tier_used boolean NOT NULL,
    assumptions jsonb DEFAULT '{}'::jsonb NOT NULL,
    refusals jsonb DEFAULT '[]'::jsonb NOT NULL,
    omitted_for_rights jsonb DEFAULT '[]'::jsonb NOT NULL,
    attribution text[] DEFAULT '{}'::text[] NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    delivered_at timestamp with time zone,
    compose_ms integer NOT NULL,
    source_calls integer DEFAULT 0 NOT NULL,
    compute_cost_micros bigint DEFAULT 0 NOT NULL,
    storage_cost_micros bigint DEFAULT 0 NOT NULL,
    unmet_fields text[] DEFAULT '{}'::text[] NOT NULL,
    CONSTRAINT file_partial_declares_gap CHECK (((status <> 'partial'::public.file_status) OR (cardinality(unmet_fields) > 0) OR (jsonb_array_length(refusals) > 0))),
    CONSTRAINT file_refusal_reason CHECK (((status <> 'refused'::public.file_status) OR (jsonb_array_length(refusals) > 0))),
    CONSTRAINT file_refused_not_delivered CHECK (((status <> 'refused'::public.file_status) OR (delivered_at IS NULL))),
    CONSTRAINT property_file_compose_ms_nonnegative CHECK ((compose_ms >= 0)),
    CONSTRAINT property_file_compute_cost_micros_nonnegative CHECK ((compute_cost_micros >= 0)),
    CONSTRAINT property_file_refusal_codes_known CHECK (public.refusals_codes_valid(refusals)),
    CONSTRAINT property_file_source_calls_nonnegative CHECK ((source_calls >= 0)),
    CONSTRAINT property_file_storage_cost_micros_nonnegative CHECK ((storage_cost_micros >= 0))
);


--
-- Name: property_file_fact; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.property_file_fact (
    property_file_id uuid NOT NULL,
    fact_id uuid NOT NULL,
    use text DEFAULT 'rendered'::text NOT NULL,
    parcel_id uuid NOT NULL,
    CONSTRAINT property_file_fact_use_check CHECK ((use = ANY (ARRAY['rendered'::text, 'gate'::text, 'input'::text])))
);


--
-- Name: rule; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rule (
    id text NOT NULL,
    jurisdiction_id text NOT NULL,
    rule_key text NOT NULL,
    version integer NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    citation text NOT NULL,
    source_text_uri text NOT NULL,
    params jsonb NOT NULL,
    pack_version text NOT NULL,
    authored_by text NOT NULL,
    reviewed_by text NOT NULL,
    review_mode public.review_mode DEFAULT 'independent'::public.review_mode NOT NULL,
    reviewed_at timestamp with time zone NOT NULL,
    attestation_uri text,
    CONSTRAINT rule_check CHECK (((effective_to IS NULL) OR (effective_to > effective_from))),
    CONSTRAINT rule_check1 CHECK ((((review_mode = 'independent'::public.review_mode) AND (reviewed_by <> authored_by) AND (attestation_uri IS NULL)) OR ((review_mode = 'solo_founder_attestation'::public.review_mode) AND (reviewed_by = authored_by) AND (attestation_uri IS NOT NULL) AND (length(TRIM(BOTH FROM attestation_uri)) > 0)))),
    CONSTRAINT rule_version_check CHECK ((version > 0))
);


--
-- Name: snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.snapshot (
    id text NOT NULL,
    source_id text NOT NULL,
    object_uri text NOT NULL,
    content_hash text NOT NULL,
    media_type text NOT NULL,
    byte_size bigint NOT NULL,
    request jsonb NOT NULL,
    http_status integer,
    fetched_at timestamp with time zone NOT NULL,
    licence_observed_id text NOT NULL,
    CONSTRAINT snapshot_byte_size_check CHECK ((byte_size >= 0)),
    CONSTRAINT snapshot_content_hash_format CHECK ((content_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT snapshot_id_format CHECK ((id = ((source_id || ':sha256:'::text) || content_hash))),
    CONSTRAINT snapshot_media_type_not_blank CHECK ((length(TRIM(BOTH FROM media_type)) > 0)),
    CONSTRAINT snapshot_object_uri_not_blank CHECK ((length(TRIM(BOTH FROM object_uri)) > 0))
);


--
-- Name: source; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source (
    id text NOT NULL,
    jurisdiction_id text NOT NULL,
    display_name text NOT NULL,
    steward text NOT NULL,
    method public.access_method NOT NULL,
    phase_status public.source_phase_status DEFAULT 'blocked_rights'::public.source_phase_status NOT NULL,
    phase_status_reason text NOT NULL,
    endpoint_url text,
    layer_item_id text,
    query_params jsonb DEFAULT '{}'::jsonb NOT NULL,
    licence_id text NOT NULL,
    cadence_stated text,
    cadence_observed_s integer,
    earliest_record_date date,
    expected_fields jsonb DEFAULT '[]'::jsonb NOT NULL,
    url_verified_at timestamp with time zone,
    active boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT source_active_matches_phase CHECK (((active = false) OR (phase_status = 'active'::public.source_phase_status))),
    CONSTRAINT source_active_requires_machine_access CHECK (((active = false) OR (method = ANY (ARRAY['direct'::public.access_method, 'bulk'::public.access_method])))),
    CONSTRAINT source_active_requires_verification CHECK (((active = false) OR (url_verified_at IS NOT NULL))),
    CONSTRAINT source_endpoint_required CHECK (((method = 'manual'::public.access_method) OR (endpoint_url IS NOT NULL)))
);


--
-- Name: source_rank; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_rank (
    jurisdiction_id text NOT NULL,
    field_key text NOT NULL,
    source_id text NOT NULL,
    rank smallint NOT NULL,
    rationale text NOT NULL,
    CONSTRAINT source_rank_rank_check CHECK ((rank > 0))
);


--
-- Name: support_request; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.support_request (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_file_id uuid,
    jurisdiction_id text NOT NULL,
    category public.support_category NOT NULL,
    field_key text,
    opened_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    caused_correction boolean DEFAULT false NOT NULL,
    correcting_fact_id uuid,
    detail text,
    CONSTRAINT support_request_correction_consistent_biconditional CHECK ((((caused_correction = false) AND (correcting_fact_id IS NULL)) OR ((caused_correction = true) AND (correcting_fact_id IS NOT NULL))))
);


--
-- Name: exception_evidence exception_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exception_evidence
    ADD CONSTRAINT exception_evidence_pkey PRIMARY KEY (exception_id, fact_id);


--
-- Name: fact fact_id_parcel_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_id_parcel_id_unique UNIQUE (id, parcel_id);


--
-- Name: fact_input fact_input_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_input
    ADD CONSTRAINT fact_input_pkey PRIMARY KEY (fact_id, input_fact_id);


--
-- Name: fact fact_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_pkey PRIMARY KEY (id);


--
-- Name: field_definition field_definition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.field_definition
    ADD CONSTRAINT field_definition_pkey PRIMARY KEY (field_key);


--
-- Name: job_run job_run_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_run
    ADD CONSTRAINT job_run_pkey PRIMARY KEY (id);


--
-- Name: jurisdiction jurisdiction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jurisdiction
    ADD CONSTRAINT jurisdiction_pkey PRIMARY KEY (id);


--
-- Name: licence_channel licence_channel_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licence_channel
    ADD CONSTRAINT licence_channel_pkey PRIMARY KEY (licence_id, channel);


--
-- Name: licence licence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licence
    ADD CONSTRAINT licence_pkey PRIMARY KEY (id);


--
-- Name: parcel_exception parcel_exception_id_parcel_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parcel_exception
    ADD CONSTRAINT parcel_exception_id_parcel_id_unique UNIQUE (id, parcel_id);


--
-- Name: parcel_exception parcel_exception_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parcel_exception
    ADD CONSTRAINT parcel_exception_pkey PRIMARY KEY (id);


--
-- Name: parcel parcel_id_jurisdiction_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parcel
    ADD CONSTRAINT parcel_id_jurisdiction_id_unique UNIQUE (id, jurisdiction_id);


--
-- Name: parcel parcel_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parcel
    ADD CONSTRAINT parcel_pkey PRIMARY KEY (id);


--
-- Name: property_file_fact property_file_fact_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file_fact
    ADD CONSTRAINT property_file_fact_pkey PRIMARY KEY (property_file_id, fact_id);


--
-- Name: property_file property_file_id_parcel_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file
    ADD CONSTRAINT property_file_id_parcel_id_unique UNIQUE (id, parcel_id);


--
-- Name: property_file property_file_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file
    ADD CONSTRAINT property_file_pkey PRIMARY KEY (id);


--
-- Name: rule rule_jurisdiction_id_rule_key_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule
    ADD CONSTRAINT rule_jurisdiction_id_rule_key_version_key UNIQUE (jurisdiction_id, rule_key, version);


--
-- Name: rule rule_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule
    ADD CONSTRAINT rule_pkey PRIMARY KEY (id);


--
-- Name: snapshot snapshot_content_hash_source_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshot
    ADD CONSTRAINT snapshot_content_hash_source_id_key UNIQUE (content_hash, source_id);


--
-- Name: snapshot snapshot_id_licence_observed_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshot
    ADD CONSTRAINT snapshot_id_licence_observed_id_unique UNIQUE (id, licence_observed_id);


--
-- Name: snapshot snapshot_id_source_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshot
    ADD CONSTRAINT snapshot_id_source_id_unique UNIQUE (id, source_id);


--
-- Name: snapshot snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshot
    ADD CONSTRAINT snapshot_pkey PRIMARY KEY (id);


--
-- Name: source source_id_jurisdiction_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source
    ADD CONSTRAINT source_id_jurisdiction_id_unique UNIQUE (id, jurisdiction_id);


--
-- Name: source source_id_method_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source
    ADD CONSTRAINT source_id_method_unique UNIQUE (id, method);


--
-- Name: source source_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source
    ADD CONSTRAINT source_pkey PRIMARY KEY (id);


--
-- Name: source_rank source_rank_jurisdiction_id_field_key_rank_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_rank
    ADD CONSTRAINT source_rank_jurisdiction_id_field_key_rank_key UNIQUE (jurisdiction_id, field_key, rank);


--
-- Name: source_rank source_rank_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_rank
    ADD CONSTRAINT source_rank_pkey PRIMARY KEY (jurisdiction_id, field_key, source_id);


--
-- Name: support_request support_request_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_request
    ADD CONSTRAINT support_request_pkey PRIMARY KEY (id);


--
-- Name: current_fact_field; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX current_fact_field ON public.current_fact USING btree (field_key);


--
-- Name: current_fact_pk; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX current_fact_pk ON public.current_fact USING btree (parcel_id, field_key);


--
-- Name: fact_by_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX fact_by_source ON public.fact USING btree (source_id, retrieved_at DESC);


--
-- Name: fact_conflicts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX fact_conflicts ON public.fact USING btree (conflict) WHERE (conflict <> 'agree'::public.conflict_state);


--
-- Name: fact_current; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX fact_current ON public.fact USING btree (parcel_id, field_key) WHERE (superseded_at IS NULL);


--
-- Name: fact_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX fact_lookup ON public.fact USING btree (parcel_id, field_key, recorded_at DESC);


--
-- Name: fact_one_current_per_source; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX fact_one_current_per_source ON public.fact USING btree (parcel_id, field_key, COALESCE(source_id, '~derived'::text), COALESCE(method_version, '~'::text)) WHERE (superseded_at IS NULL);


--
-- Name: job_run_recent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX job_run_recent ON public.job_run USING btree (job_key, started_at DESC);


--
-- Name: parcel_apn_prefix; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX parcel_apn_prefix ON public.parcel USING btree (apn text_pattern_ops);


--
-- Name: parcel_centroid_gix; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX parcel_centroid_gix ON public.parcel USING gist (centroid);


--
-- Name: parcel_geom_gix; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX parcel_geom_gix ON public.parcel USING gist (geom);


--
-- Name: snapshot_source_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX snapshot_source_time ON public.snapshot USING btree (source_id, fetched_at DESC);


--
-- Name: support_by_file; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX support_by_file ON public.support_request USING btree (property_file_id);


--
-- Name: support_rate_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX support_rate_idx ON public.support_request USING btree (jurisdiction_id, opened_at);


--
-- Name: fact_input fact_licence_inheritance; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER fact_licence_inheritance AFTER INSERT OR DELETE OR UPDATE ON public.fact_input DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.fact_licence_validate();


--
-- Name: fact fact_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER fact_no_delete BEFORE DELETE ON public.fact FOR EACH ROW EXECUTE FUNCTION public.fact_no_delete();


--
-- Name: fact fact_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER fact_no_update BEFORE UPDATE ON public.fact FOR EACH ROW EXECUTE FUNCTION public.fact_no_destructive_update();


--
-- Name: licence_channel licence_channel_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER licence_channel_no_delete BEFORE DELETE ON public.licence_channel FOR EACH ROW EXECUTE FUNCTION public.licence_channel_no_delete();


--
-- Name: licence_channel licence_channel_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER licence_channel_no_update BEFORE UPDATE ON public.licence_channel FOR EACH ROW EXECUTE FUNCTION public.licence_channel_no_update();


--
-- Name: licence licence_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER licence_no_delete BEFORE DELETE ON public.licence FOR EACH ROW EXECUTE FUNCTION public.licence_no_delete();


--
-- Name: licence licence_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER licence_no_update BEFORE UPDATE ON public.licence FOR EACH ROW EXECUTE FUNCTION public.licence_no_update();


--
-- Name: rule rule_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER rule_no_delete BEFORE DELETE ON public.rule FOR EACH ROW EXECUTE FUNCTION public.rule_no_delete();


--
-- Name: rule rule_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER rule_no_update BEFORE UPDATE ON public.rule FOR EACH ROW EXECUTE FUNCTION public.rule_no_destructive_update();


--
-- Name: snapshot snapshot_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER snapshot_no_delete BEFORE DELETE ON public.snapshot FOR EACH ROW EXECUTE FUNCTION public.snapshot_no_delete();


--
-- Name: snapshot snapshot_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER snapshot_no_update BEFORE UPDATE ON public.snapshot FOR EACH ROW EXECUTE FUNCTION public.snapshot_no_update();


--
-- Name: exception_evidence exception_evidence_exception_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exception_evidence
    ADD CONSTRAINT exception_evidence_exception_id_fkey FOREIGN KEY (exception_id) REFERENCES public.parcel_exception(id) ON DELETE CASCADE;


--
-- Name: exception_evidence exception_evidence_exception_parcel_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exception_evidence
    ADD CONSTRAINT exception_evidence_exception_parcel_fk FOREIGN KEY (exception_id, parcel_id) REFERENCES public.parcel_exception(id, parcel_id);


--
-- Name: exception_evidence exception_evidence_fact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exception_evidence
    ADD CONSTRAINT exception_evidence_fact_id_fkey FOREIGN KEY (fact_id) REFERENCES public.fact(id);


--
-- Name: exception_evidence exception_evidence_fact_parcel_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exception_evidence
    ADD CONSTRAINT exception_evidence_fact_parcel_fk FOREIGN KEY (fact_id, parcel_id) REFERENCES public.fact(id, parcel_id);


--
-- Name: fact fact_field_key_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_field_key_fkey FOREIGN KEY (field_key) REFERENCES public.field_definition(field_key);


--
-- Name: fact_input fact_input_fact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_input
    ADD CONSTRAINT fact_input_fact_id_fkey FOREIGN KEY (fact_id) REFERENCES public.fact(id) ON DELETE CASCADE;


--
-- Name: fact_input fact_input_input_fact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_input
    ADD CONSTRAINT fact_input_input_fact_id_fkey FOREIGN KEY (input_fact_id) REFERENCES public.fact(id);


--
-- Name: fact fact_licence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_licence_id_fkey FOREIGN KEY (licence_id) REFERENCES public.licence(id);


--
-- Name: fact fact_parcel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES public.parcel(id);


--
-- Name: fact fact_parcel_jurisdiction_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_parcel_jurisdiction_fk FOREIGN KEY (parcel_id, jurisdiction_id) REFERENCES public.parcel(id, jurisdiction_id);


--
-- Name: fact fact_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.snapshot(id);


--
-- Name: fact fact_snapshot_licence_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_snapshot_licence_fk FOREIGN KEY (snapshot_id, licence_id) REFERENCES public.snapshot(id, licence_observed_id);


--
-- Name: fact fact_snapshot_source_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_snapshot_source_fk FOREIGN KEY (snapshot_id, source_id) REFERENCES public.snapshot(id, source_id);


--
-- Name: fact fact_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.source(id);


--
-- Name: fact fact_source_jurisdiction_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_source_jurisdiction_fk FOREIGN KEY (source_id, jurisdiction_id) REFERENCES public.source(id, jurisdiction_id);


--
-- Name: fact fact_source_method_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_source_method_fk FOREIGN KEY (source_id, method) REFERENCES public.source(id, method);


--
-- Name: fact fact_supersedes_fact_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_supersedes_fact_fk FOREIGN KEY (supersedes_fact_id) REFERENCES public.fact(id);


--
-- Name: job_run job_run_jurisdiction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_run
    ADD CONSTRAINT job_run_jurisdiction_id_fkey FOREIGN KEY (jurisdiction_id) REFERENCES public.jurisdiction(id);


--
-- Name: job_run job_run_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_run
    ADD CONSTRAINT job_run_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.snapshot(id);


--
-- Name: job_run job_run_snapshot_source_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_run
    ADD CONSTRAINT job_run_snapshot_source_fk FOREIGN KEY (snapshot_id, source_id) REFERENCES public.snapshot(id, source_id);


--
-- Name: job_run job_run_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_run
    ADD CONSTRAINT job_run_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.source(id);


--
-- Name: jurisdiction jurisdiction_boundary_source_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jurisdiction
    ADD CONSTRAINT jurisdiction_boundary_source_fk FOREIGN KEY (boundary_source_id) REFERENCES public.source(id);


--
-- Name: jurisdiction jurisdiction_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jurisdiction
    ADD CONSTRAINT jurisdiction_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.jurisdiction(id);


--
-- Name: licence_channel licence_channel_licence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licence_channel
    ADD CONSTRAINT licence_channel_licence_id_fkey FOREIGN KEY (licence_id) REFERENCES public.licence(id) ON DELETE CASCADE;


--
-- Name: parcel_exception parcel_exception_jurisdiction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parcel_exception
    ADD CONSTRAINT parcel_exception_jurisdiction_id_fkey FOREIGN KEY (jurisdiction_id) REFERENCES public.jurisdiction(id);


--
-- Name: parcel_exception parcel_exception_parcel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parcel_exception
    ADD CONSTRAINT parcel_exception_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES public.parcel(id);


--
-- Name: parcel_exception parcel_exception_parcel_jurisdiction_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parcel_exception
    ADD CONSTRAINT parcel_exception_parcel_jurisdiction_fk FOREIGN KEY (parcel_id, jurisdiction_id) REFERENCES public.parcel(id, jurisdiction_id);


--
-- Name: parcel parcel_jurisdiction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parcel
    ADD CONSTRAINT parcel_jurisdiction_id_fkey FOREIGN KEY (jurisdiction_id) REFERENCES public.jurisdiction(id);


--
-- Name: property_file_fact property_file_fact_fact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file_fact
    ADD CONSTRAINT property_file_fact_fact_id_fkey FOREIGN KEY (fact_id) REFERENCES public.fact(id);


--
-- Name: property_file_fact property_file_fact_fact_parcel_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file_fact
    ADD CONSTRAINT property_file_fact_fact_parcel_fk FOREIGN KEY (fact_id, parcel_id) REFERENCES public.fact(id, parcel_id);


--
-- Name: property_file_fact property_file_fact_property_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file_fact
    ADD CONSTRAINT property_file_fact_property_file_id_fkey FOREIGN KEY (property_file_id) REFERENCES public.property_file(id) ON DELETE CASCADE;


--
-- Name: property_file_fact property_file_fact_property_file_parcel_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file_fact
    ADD CONSTRAINT property_file_fact_property_file_parcel_fk FOREIGN KEY (property_file_id, parcel_id) REFERENCES public.property_file(id, parcel_id);


--
-- Name: property_file property_file_jurisdiction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file
    ADD CONSTRAINT property_file_jurisdiction_id_fkey FOREIGN KEY (jurisdiction_id) REFERENCES public.jurisdiction(id);


--
-- Name: property_file property_file_parcel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file
    ADD CONSTRAINT property_file_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES public.parcel(id);


--
-- Name: property_file property_file_parcel_jurisdiction_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.property_file
    ADD CONSTRAINT property_file_parcel_jurisdiction_fk FOREIGN KEY (parcel_id, jurisdiction_id) REFERENCES public.parcel(id, jurisdiction_id);


--
-- Name: rule rule_jurisdiction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule
    ADD CONSTRAINT rule_jurisdiction_id_fkey FOREIGN KEY (jurisdiction_id) REFERENCES public.jurisdiction(id);


--
-- Name: snapshot snapshot_licence_observed_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshot
    ADD CONSTRAINT snapshot_licence_observed_id_fkey FOREIGN KEY (licence_observed_id) REFERENCES public.licence(id);


--
-- Name: snapshot snapshot_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshot
    ADD CONSTRAINT snapshot_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.source(id);


--
-- Name: source source_jurisdiction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source
    ADD CONSTRAINT source_jurisdiction_id_fkey FOREIGN KEY (jurisdiction_id) REFERENCES public.jurisdiction(id);


--
-- Name: source source_licence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source
    ADD CONSTRAINT source_licence_id_fkey FOREIGN KEY (licence_id) REFERENCES public.licence(id);


--
-- Name: source_rank source_rank_field_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_rank
    ADD CONSTRAINT source_rank_field_fk FOREIGN KEY (field_key) REFERENCES public.field_definition(field_key);


--
-- Name: source_rank source_rank_jurisdiction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_rank
    ADD CONSTRAINT source_rank_jurisdiction_id_fkey FOREIGN KEY (jurisdiction_id) REFERENCES public.jurisdiction(id);


--
-- Name: source_rank source_rank_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_rank
    ADD CONSTRAINT source_rank_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.source(id);


--
-- Name: support_request support_property_file_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_request
    ADD CONSTRAINT support_property_file_fk FOREIGN KEY (property_file_id) REFERENCES public.property_file(id);


--
-- Name: support_request support_request_correcting_fact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_request
    ADD CONSTRAINT support_request_correcting_fact_id_fkey FOREIGN KEY (correcting_fact_id) REFERENCES public.fact(id);


--
-- Name: support_request support_request_field_key_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_request
    ADD CONSTRAINT support_request_field_key_fkey FOREIGN KEY (field_key) REFERENCES public.field_definition(field_key);


--
-- Name: support_request support_request_jurisdiction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_request
    ADD CONSTRAINT support_request_jurisdiction_id_fkey FOREIGN KEY (jurisdiction_id) REFERENCES public.jurisdiction(id);


--
-- PostgreSQL database dump complete
--

\unrestrict ledgexschemadumpfixedkey

