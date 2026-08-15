## P2 — Three correctness bugs in current data

All three confirmed in code at `5f95a59`. They're independent; the prompt keeps them
independent on purpose so one going wrong doesn't contaminate the others.

| Bug | Where | What it actually does |
|---|---|---|
| Leading apostrophe in APN | `ingest_zoning_permits.py` L525 `.strip()` only; `ingest_parcels.py` L801 `is_unresolvable_apn` checks blank + `?` only | `'67620002` never matches `67620002`, so a real active permit is silently dropped |
| Null-zoning polygon | `ingest_zoning_permits.py` L424–426, `if n > 1: ambiguous` | `n` counts intersecting polygon *rows*. `FACILITYID=30392` has null `ZONING`, so ten parcels are called ambiguous when there is exactly one real classification |
| Compose by APN | `compose_property_file.py` L131–132, `WHERE apn = %s` + `fetchone()` | `0034` removed APN uniqueness; 49 APNs collide. Silently composes the wrong parcel |

### The prompt

```
Three independent correctness fixes. One commit each. Do not batch them.

--- FIX 1: APN canonicalisation ---
Permit APN '67620002 (leading apostrophe, from a spreadsheet export) never matches
parcel APN 67620002, so a real active permit is dropped.

Today there are two different APN handlers: ingest_parcels.is_unresolvable_apn
(blank / contains '?') and a bare .strip() in ingest_zoning_permits. Build ONE
shared canonicaliser and route both through it. Put it where a third source would
find it -- core/ or infra/, argue for which.

DECIDED -- canonicalisation applies at WRITE, not only at match time. Note that
phase_e writes the raw APN TWICE: to the parcel.apn cache column (L951-953) and,
separately, as the fact VALUE (L983, json.dumps(apn_raw)). 0034 defines the cache
column as a non-authoritative cache OF the parcel.apn fact, so the cache must
follow the fact. This decision is therefore about fact.value, not about a cache
column, and it is binding on all three conditions below.

  (1) The raw source string goes in fact.local_verbatim, which has existed since
      0006 and which NO script currently writes -- core/store.py's FACT_COLUMNS is
      a 14-column tuple with no local_verbatim, shared by phase_e, load_zoning and
      load_permits. Widening that shared primitive is part of this fix. Report the
      call-site blast radius before writing. If local_verbatim is NOT carried, this
      fix destroys information and you must stop and tell me, because then
      match-time-only becomes the correct answer instead.

  (2) The paired question, per CLAUDE.md: a fix at source does not clean up data
      already loaded. fact is immutable (0017 forbids deletion, 0040 whole-row
      immutability), so no migration can touch the already-loaded rows. The only
      path is supersession, and 0025 already minted the right value for it:
      'ingestion_logic_change' -- "our own parsing/mapping logic changed." That
      machinery is Phase B. So state explicitly which you are choosing: carry the
      affected rows as a named open item until P3 discharges them, or rebuild the
      dev database. Do not leave it implicit.

  (3) Two numbers before writing, taken from the snapshot bytes and NOT from the
      already-loaded parcel table (the loaded table has already been through
      is_blank):
        a) how many of the 225,039 features change RESOLVABILITY under
           canonicalisation. The claim is zero. I want the query output.
        b) the APN collision count before and after. Canonicalisation merges
           strings; if '67620002 and 67620002 were distinct keys they now collide.
           49 collisions are already known. P2 Fix 3 makes the composer ERROR on
           collisions, so this number is load-bearing.

Also state the ordering of canonicalisation against is_unresolvable_apn, which
today tests "?" in apn against the RAW string. Neither option specifies it.

Before writing: report every distinct shape of malformed APN actually present in
both sources -- query it, do not reason about it. I want counts. If the apostrophe
and trailing whitespace are not the only ones, that is a finding.
Do NOT invent normalisation rules for shapes you have not observed.

--- FIX 2: zoning ambiguity is counting the wrong thing ---
The LATERAL join counts intersecting polygon ROWS (count(*) OVER () AS n). One
polygon, FACILITYID=30392, has null ZONING/ZONINGABBREV, so ten parcels get n=2
and are recorded ambiguous when there is exactly one real classification.

Count DISTINCT NON-BLANK classifications instead. A parcel whose only intersecting
polygon is the null one is not "ambiguous" -- decide what it is, say why, and say
whether it needs an exception row rather than a fact.

Report the before/after counts for matched / zero-match / ambiguous. If the delta
is not exactly the ten parcels, stop and tell me -- that means something else is
going on too.

DECIDED (after the delta came back as 11, not 10 -- two distinct source artifacts,
the null polygon 30392 affecting 10 parcels and overlapping polygons 6207/6206
carrying the identical value 'A' affecting parcel 5072c848). Proceed with
distinct-classification counting: a parcel is ambiguous iff it has >= 2 DISTINCT
real classifications, regardless of how many polygon rows produced them. Three
things this decision does NOT yet settle, all of which must be answered before
writing:

  (1) DISTINCT ON WHICH COLUMN. load_zoning writes TWO facts per matched parcel:
      zoning.district from ZONING, and zoning.district_verbatim from ZONINGABBREV
      (L440-452). Despite the name, zoning_verbatim is a SECOND SOURCE COLUMN, not
      the raw form of the first. So "distinct classifications" is underspecified.
      If polygons 6207 and 6206 agree on ZONING but DISAGREE on ZONINGABBREV, then
      distinct-on-ZONING is 1 while the two candidate rows disagree about a value
      that still becomes a fact -- and matched[parcel_id] = (zoning,
      zoning_verbatim) would pick whichever row the join happened to return. That
      is scripts/compose_property_file.py's fetchone() bug wearing a different hat.
      Report ZONINGABBREV for 6207 and 6206 specifically. State the distinctness
      key you are using and what happens when the pair disagrees. Arbitrary pick is
      not an available answer.

  (2) THE ARTIFACT MUST NOT VANISH. Today 5072c848 carries a coverage_gap exception
      with reason 'multiple_containing_districts'. Under this fix it gets a clean
      fact and no exception, and the fact that the source has overlapping polygons
      becomes invisible. Record it -- a distinct, non-blocking observation
      (reason 'overlapping_districts_same_classification' or similar) that does not
      withhold the fact. Resolving the value and recording the anomaly are separate
      obligations; do both.

  (3) ZERO-MATCH IS MISSING FROM THE REPORT. matched 214,892 -> 214,903 and
      ambiguous 12 -> 1 balance at 11, which implies zero-match did not move -- i.e.
      all 10 null-polygon parcels had exactly one real polygon as well. Confirm that
      with output rather than by arithmetic. A parcel whose ONLY candidate is the
      null polygon has zero non-blank classifications and belongs in zero-match with
      'no_containing_district', not in matched.

Rejected: the narrow null-polygon-only fix. "Ambiguous" must mean "we cannot
determine the answer," not "the source data had an unusual shape." Two polygons
that agree do not make the answer uncertain, and special-casing one FACILITYID
pattern encodes a specific source defect where a general rule belongs.

--- FIX 3: compose by parcel.id ---
compose_property_file.compose() does SELECT id, jurisdiction_id FROM parcel WHERE
apn = %s then fetchone(). 0034 removed APN uniqueness and 49 APNs collide, so this
silently picks an arbitrary one.

Take --parcel-id. If you keep --parcel-apn as a convenience, it must ERROR on a
collision naming the candidate ids, never pick one. Show me it erroring on a real
colliding APN.

--- For each fix ---
A test that goes RED before and GREEN after. Show both runs and the deliberate
break. A fix with only a green run is not yet known to be a fix.

--- Hard rules ---
No schema changes. If one of these genuinely needs a migration, stop and report
rather than writing it. Fix 1 touches two loaders -- if the shared canonicaliser
changes what parcels ingest considers resolvable, that changes existing data, and
you must tell me before writing, not after.
```

### In plain terms

**Fix 1** — Excel puts an invisible apostrophe in front of a number so it stays a number and
doesn't lose leading zeros. Two lists of house numbers, one typed by hand and one exported
from Excel; you're matching them by eye and one list has a stray tick mark in front of every
entry. You need one agreed rule for tidying a house number, used on both lists — not a
different rule per list. And you keep the original scrap of paper (`local_verbatim`) so you
can always prove what was really written.

**Fix 2** — You ask "how many zones is this lot in?" by counting the map sheets it appears
on. But one map sheet is *blank* — someone printed it with no label. It still overlaps the
lot, so your count says two, so you flag the lot as confusing. There was never any confusion:
count the *labels*, not the *sheets*.

**Fix 3** — Two people in the building are both called "J. Smith." A package arrives for
J. Smith and the mailroom just hands it to whoever it finds first. It doesn't ask, doesn't
complain — the package simply goes to the wrong flat and no one ever knows. Use the flat
number (`parcel.id`), and if someone insists on using the name, the mailroom must *refuse*
and say "there are two of them."

---

