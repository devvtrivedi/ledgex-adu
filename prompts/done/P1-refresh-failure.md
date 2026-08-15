## P1 — The refresh-failure hole

### What is actually wrong (verified, `scripts/ingest_parcels.py` L1038–1050)

```python
conn.commit()                                    # facts permanent HERE. 0017 forbids deletion.
refresh_current_fact(conn)                       # if this raises...
finish_job_run_full(conn, job_run_id, "succeeded", ...)   # ...never runs
except Exception as e:
    conn.rollback()                              # no-op, already committed
    fail_job_run(conn, job_run_id, e)            # job_run -> 'failed'
```

And the anchor the next run uses (`previous_successful_snapshot`, L173–188) filters on
`status = 'succeeded'`. So the next run's idea of "where I left off" points at a snapshot
*older* than facts that are permanently in the ledger.

Worse: `fact` has `snapshot_id` but **no `job_run_id`** (`0006_fact.sql`). The only way to
ask "which facts landed under a non-successful job" is to join out through `snapshot`.

### The prompt

```
Fix the refresh-failure hole in the ingest commit sequence. Report before writing.

--- 1. Establish the bad state first, do not fix anything yet ---
In ingest_parcels.py phase_e, facts COMMIT, then refresh_current_fact runs, then
finish_job_run_full marks the job succeeded. If the refresh raises, the facts are
permanent (0017 forbids deletion) under a job_run with status='failed'.

Reproduce it deliberately on a scratch database. Force refresh_current_fact to
raise -- take an ACCESS EXCLUSIVE lock on current_fact from a second session,
or inject a failure, your choice, but say which. Then show me, with query output:
  a) the count of facts whose snapshot_id belongs to that failed job_run
  b) what previous_successful_snapshot() returns afterwards
  c) what the NEXT phase_e run does when handed the same snapshot -- predict the
     exit code before you run it, then run it

Do not proceed to a fix until (a), (b) and (c) are on screen as real output.

--- 2. Report the design options before writing ---
State the invariant you are enforcing in one sentence. My candidate, argue with it
if it is wrong: the reconciliation anchor must never point at a moment earlier than
facts that are already permanently committed.

Give me at least two ways to satisfy it and the cost of each. I expect one of them
to be "mark job_run successful inside the ledger transaction and track read-model
staleness separately," but I want your reasoning, not my guess.

fact has no job_run_id. Say explicitly whether your fix needs one, and if it does,
say so BEFORE writing the migration -- that is a schema change and the report-first
rule applies.

--- 3. Then implement ---
Same fix in ingest_zoning_permits.py if it has the same shape. Check; do not assume.

--- 4. Prove it can fail ---
Re-run the exact reproduction from step 1 against the fixed code. The refresh must
still be able to fail -- I am not asking you to make refreshes infallible, I am
asking that a failed refresh leave a state the next run can reason about correctly.
Show the same three outputs (a), (b), (c) and state what changed in each.

Add an invariant test that goes RED without your fix and GREEN with it. Show me both
runs, with the diff of what you changed to make it red.

--- Hard rules ---
No relaxing an existing constraint to make anything pass. If the honest answer is
"this needs a migration and a spec bump," stop and tell me rather than working
around it.
```

### In plain terms

You write a cheque and it clears — the money is gone and cannot be un-spent (that is
`0017`: facts are immutable, you cannot delete them). Then you're supposed to update your
cheque register, and *then* write "done" in your logbook.

The register update fails. So your logbook says "this attempt failed." Next month you open
the logbook, find the last entry marked *done* — which is from before this cheque — and
start from there. The money left the account, but your books insist it never did.

The fix isn't "make the register never fail." It's "write *done* in the logbook at the same
instant the cheque clears, and keep a separate note saying the register is behind."

---

