# Persistent v2 production-readiness changes — 2026-09-21

Current production planning is documented in [the 0.51 cutoff and fixed 5+5 workflow](persistent_v2_51pct_phased_production.md). Earlier scope/runtime figures below remain historical evidence.

This report describes the **previous twenty-repetition/full-ledger plan**.
The [ten-repetition compact-storage follow-up](persistent_v2_compact_production.md)
supersedes its planning counts and storage architecture. Its measured timings,
source hashes and scientific-semantics checks remain preserved for comparison.

The counter-fork owner gap is closed, `persistent-petty-v2` is implemented, and
the shared engine uses exact indexes and a disk-backed production recording
mode. All twelve authorized local 30,000-block cases completed and passed strict
validation. **The full six-variant 1% grid is not yet an operationally justified
launch.** Remaining compute, storage and endpoint questions are described below.
No production grid, remote job, SSH command or `/xtra` access occurred.

Evidence: [benchmark program](../analysis/benchmark_persistent_v2_production.py),
[measurements/source hashes](persistent_v2_production_benchmark.json), and
[regression tests](../tests/test_persistent_v2_production.py). The
[earlier audit](persistent_v2_readiness_audit.md) records the pre-change state;
its owner-gap reproduction now uses the frozen pre-change reference engine.

## Counter-fork enforcement and cross-branch refresh

V2 has its own `CounterForkPolicy` subclass. For the current trigger T, each
defending descendant stores its parent's weighted depth plus one exactly when
its owner is neither the target nor an active punishment member. Episode depth
is the maximum weighted depth on a defending path. Parallel siblings do not add
across paths. An active member's defending block contributes zero; a subsequent
ordinary child contributes only one, without charging skipped member heights.
Leave-one-out candidates remain explicit independent miners and count as
ordinary actors. Counter-branch and unrelated work do not consume k. Native
k=1,2,3 behavior is unchanged; direct/replayed publications enforce ownership too.

The preserved cross-branch convention is:

- A newly published target block is competitive if it is an ancestor of any
  globally maximum-height public tip in the complete post-batch public tree.
  A shorter stale target publication does not qualify.
- Process qualifying target blocks in publication order before timeout accounting.
  The last qualifying block in an atomic batch becomes the current trigger.
- Each supersedes any open episode, recording `REFRESHED`. The replacement
  anchors at the new trigger's exact parent, resets depth to zero, and increments
  refresh count. Further work in the batch is measured relative to that trigger.
- Strict reference overtake excluding the trigger succeeds before the depth
  deadline is tested; otherwise depth reaching k capitulates.

A reachable k=2/3 fixture has `T1→H2`, counter-branch `C3→C4`, then T5 on C4.
H2 and C4 are tied before T5; the target selects C4 using ordinary non-owned
tie choice. T5 is competitive on the other branch. The T1 episode is `REFRESHED`,
the new anchor is C4, and depth is zero. This treats a new competitive target
publication as a new offense, consistently with the existing refresh rule.
No semantic contradiction was found. Tests also cover stale targets, successive
refreshes, siblings, active-owner exclusions and leave-out/residual advancement.

## Persistent petty and baseline equality

`punishment_rule="petty"` selects **`persistent-petty-v2`** under unchanged
`persistent-network-v2` discovery, propagation, reaction, accounting and stopping
rules. Historical `race-owner-oceanic-all-races-v4` remains a separate family.

For each flagged active member's actual visible maximum-height eligible set:

1. If a tie contains exactly one target-owned tip, remove that tip.
2. If the member owns a remaining tip, preserve explicit-owner preference.
3. Otherwise use the common neutral rule restricted to the remaining tips:
   uniform selection when several remain, no tie draw when only one remains.
   There is no coalition gamma, pooled ownership, hash power or reward sharing.
4. Target-absent ties, historical target ancestry under another owner's tip, and
   a unique longest target tip do not trigger petty. Delayed visibility can
   remove the target race from the actual choice. Multiple target-owned leading
   tips retain the common explicit unsupported-state check.

S0 and detector misses have no punishment instance. SC and falsely flagged
honest targets (HF) activate petty. Leave-one-out members retain identity, power
and rewards but follow ordinary fork choice. Global petty race openings/closings
are recorded; activations count openings per member. Opportunities retain the
common pre-discovery active-policy convention. The publication's petty label
reflects actual punishment in the member's visible view.

Complete H/S0 traces and initial/final RNG states agree exactly across petty,
counter-fork k=1/2/3, ignore and selfish at lambda 0, .005, .02 and 1. Inactive
policy selection changes neither baseline identity nor RNG namespace. Eighty
native before/after comparisons cover both target strategies, active/inactive
conditions, five existing variants, 1/2/3/6 members, gamma 0/.5/1 and lambda
0/.005/.02/1. They compare entire results including full traces, rewards and RNG
consumption. Existing frozen v2 fixtures remain unchanged and pass.

## Shared H/S0 and exact represented-work savings

The baseline identity includes ordered population, environment, seed/repetition,
horizon and common network/RNG semantics, but omits consumer rule/k. Six-variant
tests reuse the same immutable baseline files and reproduce analysis-only output
with mining disabled. Historical petty-v4/v1 data are ineligible, including at
lambda zero; no historical importer or relabeling was added.

For six identical copies of the existing refined design (250,170 configurations
per variant, 20 repetitions, 30,000-block target), arithmetic gives:

| Quantity | Mining simulations |
| --- | ---: |
| One variant, before cross-rule reuse | 39,934,200 |
| Six variants independently | 239,605,200 |
| Unique shared H/S0 runs | 10,006,800 |
| Duplicate H/S0 runs saved | **50,034,000** |
| Remaining unique runs | **189,571,200** |
| Remaining per lambda (0, .005, .02) | **63,190,400** |

Baseline-only savings are 5/6 = 83.333%; overall savings are **20.88185%**.
Remaining nominal accepted-block work is **5,687,136,000,000**, or
1,895,712,000,000 per lambda. These are reference-height targets, not discoveries;
atomic releases can overshoot. This arithmetic does not authorize or launch a
production design. Reuse requires matched inputs and a shared native v2 store.

## Exact indexes and bounded execution

Height indexes retain all public nodes by height, including interior prefixes
needed under tip delay. Ignore maintains a non-rejected index; counter-fork
indexes the anchor subtree excluding the trigger subtree and rebuilds that
eligible subtree on refresh. Binary ancestor jumps replace repeated parent walks.
Publication updates the public leaf frontier and maximum incrementally. Visibility
is a membership view instead of a copied public set. Sorting, parent choices,
RNG draws and sticky reference adoption are unchanged. **No branch is pruned.**
The ancestry index adds approximately O(N log N) memory of its own.

`PersistentSimulation(..., production=True)` omits the reconstructible
`public_events` log and disallows full traces. Diagnostic mode retains that log
and optionally full step traces. Both retain complete block records, publication
batches, reaction records, policy history, reorganizations, private/abandoned
state, full terminal ancestry/frontier, accounting, RNG and payoff bounds.
Production memory is bounded across tasks; it is not constant within a growing
tree. Full diagnostic traces can grow quadratically and are for small audits.

Production studies retain compact statistical inputs and references to full
validated checkpoints, reducing one population's repetitions at a time. SQLite
holds the deduplicated task plan and scientific rows; threshold reduction uses
one scientific group at a time, and CSV exports stream from disk. The runner
does not retain every task's raw results or duplicate full terminal trees.

The CLI defaults to this production **recording layout**, with `--diagnostic`
for the previous layout. The Python API opts in through
`run_sweep(..., production=True)`. No production configuration was added.
`persistent_v2_results.json` is an explicit dataset manifest pointing to SQLite
and the scientific CSV families. Repetition rows contain terminal summaries and
condition references; full terminal data remain in those files. Consumers of the
old giant results JSON must adapt or use diagnostic mode. Output manifests reject
mixed designs/layouts, and status remains INCOMPLETE until exports finish.

On resume, outputs are rebuilt from condition checkpoints. Existing conditions
are strictly checked before missing mining within each task; corruption aborts
instead of becoming a cache miss. Analyze-only has no mining fallback.

## Validation, serialization and provenance

Each condition is natively validated once on the study's normal boundary: memory
input, disk load, fresh disk save, or fresh no-store result. Public `analyze()`
still validates raw inputs; the private statistical reducer receives only those
validated process-local records. Overwrite protection also validates an existing
file. Call-count, no-mining resume, corruption and format-separation tests cover
these paths. Unchanged uncertainty machinery includes paired CRN differences,
sample SD/SE, Student-t 95% CIs, classifications and detector/bootstrap analysis.

The validator reconstructs every discovery RNG choice, parent, propagation trial,
required strategy reaction, policy transition, reward and terminal field from
the ledger; it never calls mining methods. Production omits an event-log comparison,
not behavioral validation. Diagnostic `.json` schemas remain supported. Production
uses deterministic gzip and separate schemas:

```text
baselines/<condition_id>.json.gz   persistent-common-baseline-production-checkpoint-v2
conditions/<condition_id>.json.gz  persistent-policy-production-checkpoint-v2
```

Native identity is unchanged. Both encodings may not coexist for one condition;
ambiguous duplicates and schema/mode mismatches fail. Production studies can
reuse validated diagnostic files already present. References hash the exact raw
result; envelope checksums additionally cover schema and identity. Encoding
serializes the envelope body once, hashes its bytes and compresses them. Full
terminal state lives in its checkpoint rather than every statistical row. No
unproved smaller replacement for reachable scientific history was assumed.

## Before/after 500-block performance

Python 3.13.3, macOS arm64; alpha=.20, gamma=.5, c1=c2=.10, residual=.60,
seed 701, repetition 0, SC. Each case uses a fresh local subprocess. Timing
wrappers and completed-event peak counters are included in mining time. One
measurement per case is a performance diagnostic, not a statistical timing study.
Full traces are off here; exact full-trace comparisons are in the test suite.

Means cover the same ten cases: five existing variants at lambda 0/.02. Petty
has no pre-change implementation; its current measurements are in the evidence.
Every before/optimized diagnostic pair has an identical complete result hash.
All twelve debug/production pairs agree after removing only the recording label
and omitted derived event log.

| Mean metric | Before | Indexed diagnostic | Indexed production |
| --- | ---: | ---: | ---: |
| Simulation + terminal report (ms) | 52.395 | 11.908 | 11.674 |
| Eligibility + fork choice / mining time | 70.91% | 18.38% | 18.26% |
| Strict validation (ms) | 70.680 | 18.086 | 13.568 |
| Terminal report construction (ms) | 1.489 | 1.459 | 1.469 |
| Raw result JSON serialization (ms) | 2.577 | 2.562 | 1.396 |
| Checkpoint encoding (ms) | 5.382 | 2.828 | 3.241 |
| Raw result JSON bytes | 476,455 | 476,455 | 279,404 |
| Stored checkpoint bytes | 477,281 | 477,281 | 33,544 |
| Peak RSS through reporting (MiB) | 26.07 | 26.52 | 25.80 |
| Peak RSS through validation/encoding (MiB) | 28.37 | 29.77 | 28.33 |

Run time fell 77.3% in diagnostic mode and 77.7% in production. Production
validation fell 80.8%. Compressed checkpoints are 93.0% smaller than the original
uncompressed files; removing event records reduces raw result bytes by 41.4%.
Gzip costs more than indexed diagnostic encoding. Terminal construction is largely
unchanged. Individual-process RSS reduction is slight at this horizon; indexes
increase diagnostic RSS. The main runner memory improvement removes retention
and duplication across conditions/tasks, not the necessary per-engine tree.

## Twelve local 30,000-block cases

Same two-member SC environment, one repetition per row. Every case reaches
exactly 30,000 reference blocks, retains all discovered blocks, and validates.
Run includes terminal reporting; encoding excludes disk I/O. MB is decimal.

| Variant | lambda | Discovered / retained | Public leaves | Reorgs / max depth | Run s | Validate s | Encode s | Gzip MB | Peak RSS MiB* |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Petty | 0 | 35,278 | 5,060 | 3,088 / 7 | .585 | .806 | .161 | 1.51 | 256.4 |
| Petty | .02 | 35,650 | 5,457 | 3,270 / 6 | .588 | .819 | .162 | 1.54 | 257.1 |
| Counter k=1 | 0 | 35,700 | 5,503 | 3,273 / 4 | .621 | .848 | .163 | 1.56 | 257.5 |
| Counter k=1 | .02 | 36,090 | 5,865 | 3,439 / 6 | .638 | .897 | .172 | 1.59 | 263.6 |
| Counter k=2 | 0 | 36,458 | 5,829 | 3,456 / 4 | .656 | .882 | .170 | 1.60 | 263.0 |
| Counter k=2 | .02 | 36,841 | 6,207 | 3,634 / 4 | .666 | .886 | .172 | 1.63 | 269.8 |
| Counter k=3 | 0 | 37,033 | 6,061 | 3,552 / 5 | .700 | .915 | .175 | 1.63 | 265.5 |
| Counter k=3 | .02 | 37,433 | 6,440 | 3,712 / 5 | .707 | .930 | .198 | 1.66 | 273.5 |
| Ignore | 0 | 45,705 | 6,277 | 4,605 / 5 | .814 | 1.032 | .221 | 1.96 | 311.9 |
| Ignore | .02 | 46,026 | 6,508 | 4,741 / 6 | .769 | 1.058 | .240 | 1.99 | 312.5 |
| Selfish | 0 | 41,964 | 11,410 | 6,449 / 6 | .697 | .971 | .217 | 1.92 | 303.6 |
| Selfish | .02 | 42,174 | 11,634 | 6,531 / 5 | .720 | 1.008 | .218 | 1.94 | 307.7 |

*RSS includes validation and serialization with engine/result objects resident.
Through reporting alone it is 104.0–121.1 MiB. These are process measurements,
including Python. Terminal construction takes .071–.100 s; raw result JSON is
14.76–19.60 MB; eligibility/fork choice takes 18.5–20.8% of mining time. All rows
retain zero derived event logs or full traces.

Completed-event peak private blocks are 6–8 for petty/counter/ignore (one selfish
actor), and 13 for selfish (up to three simultaneous private actors). Peak private
leads are 6–8. These peaks exclude transient states inside atomic reaction cascades.
At all observed horizons active private chains and propagation windows are empty;
ignore remains armed. Nevertheless every boundary is potentially material:
alternative branches expose up to 29,993 canonical blocks (29,999 for selfish)
and retain conservative owner payoff bounds [0,1]. Old public leaves are not
silently finalized. These measurements support no scientific payoff conclusion.

## Readiness limits and verification

The engine is faster and the runner no longer retains the full raw dataset.
That does not make 189,571,200 runs a reasonable local job. Uniformly applying
the twelve-case mean of run + one validation + checkpoint encoding implies
roughly **10.76 single-core years** and **324 TB** of compressed condition
payloads, before file overhead, exports, baseline reloads, resumption, I/O,
statistics or scheduling. This is only an order-of-magnitude illustration, not
a forecast. Other powers, unequal compositions, up to six members, H/S0/HF and
leave-outs can behave differently; they were not benchmarked at 30,000 here.

Remaining launch blockers: a costed compute/storage plan including the condition
file count; bounded sharding with exclusive output/shared-store writer ownership;
stress coverage of difficult grid cells; and explicit scientific treatment of
the unresolved horizon bounds. The runner is serial within one output directory
and does not implement a distributed scheduler or concurrent writer coordination.
Multiple-target-tip unsupported states and resource limits still fail closed.
No scientific grid, horizon, repetition count, detector setting, analytical
authorization, estimator or uncertainty machinery was changed.

Before the 30,000-block benchmark, the full local suite passed **960 tests with
9 expected historical-v1 failures**. The benchmark verifies source hashes before
and after and matches all eight historical-v1 runtime hashes to the prior audit.
Historical petty-v4 files/configuration and all frozen fixtures remain untouched.
Final `.venv/bin/python -m pytest -q`: **966 passed, 9 expected historical-v1
failures in 54.79 s**. `git diff --check` and explicit `git diff --no-index
--check` checks on all 16 new/updated files passed, including untracked additions.
All 29 historical/non-v2 source and refined-config hashes match the earlier
readiness audit. All benchmarked runtime, reference, fixture and configuration
hashes still match the recorded evidence. Only local unit fixtures and the fixed
tiny benchmark were executed.

Files added or updated for this task:

- Engine and policies: `punishment_sim/persistent_v2.py`,
  `persistent_v2_index.py`, `persistent_v2_policies.py`.
- Checkpoints and runner: `punishment_sim/persistent_v2_checkpoint.py`,
  `persistent_v2_study.py`, `persistent_v2_sweep.py`, `persistent_v2_production.py`.
- Tests and references: `tests/test_persistent_v2_production.py`,
  `analysis/_persistent_v2_reference.py`, `_persistent_v2_reference_checkpoint.py`,
  `audit_persistent_v2_readiness.py`, `benchmark_persistent_v2_production.py`.
- Documentation/evidence: `docs/persistent_network_v2.md`,
  `persistent_v2_readiness_audit.md`, `persistent_v2_production_readiness.md`,
  `persistent_v2_production_benchmark.json`.
