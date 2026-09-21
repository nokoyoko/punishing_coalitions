# Persistent v2: 51% cutoff, stable five-repetition preview, ten-repetition final

This report preserves the prior combined 2–6 design. The current future production design is [core 2–4 with optional 5/6 extensions](persistent_v2_core_cardinalities.md). The configuration link below now resolves to the core compatibility alias; counts in this report describe the prior 2–6 inventory. It supersedes the
0.60 compact-production planning figures, while preserving their benchmark and
scope artifacts as historical evidence. Historical petty-v4 remains unchanged.

The [production configuration](../configs/persistent_v2_1pct_10rep.json) has
**47 coalition totals: 0.05, 0.06, …, 0.50, 0.51**, at exactly 0.01 spacing.
The target grid, gamma/lambda grids, member cardinalities/resolution/minimum,
HHI composition sampling, authorization, six variants, detector settings, seeds,
30,000-block target and final **ten repetitions** are otherwise unchanged.
There is no adaptive follow-up or selection of cells for extra repetitions.
Both phases cover the entire same task inventory.

## Exact inventory

[Scope evidence](persistent_v2_51pct_scope.json) comes from the actual native task
planner and indexed population plan, including deterministic shard ownership.
It is enumeration without mining, not a proportional estimate.

| Quantity | Previous 0.60 design | Revised 0.51 design | Reduction |
| --- | ---: | ---: | ---: |
| Coalition-total values | 56 | 47 | 9 |
| Feasible total/cardinality cells | 279 | 234 | 45 |
| Selected structures per authorized environment | 1,345 | 1,120 | 225 |
| Authorized target/gamma/lambda environments | 186 | 186 | 0 |
| Population/environment configurations | 250,170 | **208,320** | 41,850 (16.7286%) |
| Configurations across six variants | 1,501,020 | **1,249,920** | 251,100 (16.7286%) |
| Represented runs before H/S0 reuse | 119,802,600 | **99,714,600** | 20,088,000 (16.7676%) |
| Unique shared H/S0 runs | 5,003,400 | **4,166,400** | 837,000 (16.7286%) |
| Unique runs after reuse | 94,785,600 | **78,882,600** | 15,903,000 (16.7779%) |
| Nominal block work after reuse | 2,843,568,000,000 | **2,366,478,000,000** | 477,090,000,000 (16.7779%) |

The only infeasible total/cardinality cell is total .05 with six members at a
minimum .01 each. Selection/deduplication, including small cells with fewer than
five distinct sampled compositions, produces the exact 1,120 structures.

Each variant represents 16,619,100 conditions, of which 12,452,700 are its own
active-policy conditions. Common H/S0 form a separate shared cost. Each lambda
has 69,440 populations, 26,294,200 unique conditions and 788,826,000,000 nominal
block work. Cardinality 2/3/4/5/6 populations are 42,036 / 42,594 / 42,036 /
41,292 / 40,362. Both phases have exactly **39,441,300 unique simulations**,
including 2,083,200 baselines, and **1,183,239,000,000 block-work units**.
These are reference-height targets; existing atomic overshoot semantics remain.

## Execution and reporting boundaries

Repetition ranges are inclusive and **one-based in the CLI**. Native stored
indices remain 0–9; native seed is base seed plus that index. Range arguments do
not enter population/task/condition identities, the plan, or shard ownership.
No phase-specific seed offset exists.

Normal durable granularity remains one compact repetition, with individually
committed shared baselines and a derived task record after a reporting boundary.
All six variants of a population remain on the same independent shard database.

- Phase I runs repetitions **1–5** for every configuration. Its derived records
  use kind `preliminary_task`, and shard completion uses `preliminary_complete`.
  They are not final task/complete records.
- Phase II runs only missing repetitions **6–10**. Earlier repetitions are read,
  authenticated and checked, without native mining/replay. Missing earlier
  repetitions cause an error; corrupt committed data fails closed. It is not
  silently repaired, truncated or overwritten.
- Final `task` and `complete` records appear only after all ten repetitions have
  passed validation. Repetition inserts and task commits remain atomic.
- Generic ranges may stop between reporting boundaries. There is no derived
  final result for an incomplete ten-repetition task. An available first-five
  preview always analyzes exactly those five repetitions, even after partial II.
- A one-shot 1–10 execution has identical final scientific results and native
  records to 1–5 followed by 6–10. Split runs additionally retain preview records.

Phase-I rows carry `analysis_status=PRELIMINARY_5_REPETITIONS`,
`analysis_repetitions=5`, and `planned_repetitions=10`. Final rows carry
`FINAL_10_REPETITIONS`, 10 and 10. This includes thresholds, detector outputs,
member outputs, repetition rows, boundary summaries and paired comparison tables.
The normal single-variant runner also reports execution status/range separately
from the unchanged final design count.

The existing paired reducer uses sample SD, SE and Student-t intervals with
**n=5 / df=4 / t=2.776** for the preview, and **n=10 / df=9 / t=2.262** for final
results. These are its existing tabulated critical values. Bootstrap resampling
uses the actual matched-vector length. Means, effectiveness, baseline credibility,
deviation-proofness, weak/strict feasibility and detector mixtures all use the
selected snapshot consistently. Minimum tested powers describe that snapshot;
they are not presented as established final thresholds. Phase splitting changes
neither trajectories nor final estimators.

## Local CLI interface and global orchestration

The following documents the interface; **none of these production commands were
executed for this task**. `STUDY` and destinations stand for a future deployment's
chosen local paths. Prepare once, then launch one worker per shard (0–27):

```text
python -m punishment_sim.persistent_v2_shards plan configs/persistent_v2_1pct_10rep.json STUDY
python -m punishment_sim.persistent_v2_shards run STUDY --shard SHARD --rep-start 1 --rep-end 5
```

Wait for **all 28 Phase-I workers**, then require a successful whole-grid preview
merge and export before starting Phase II:

```text
python -m punishment_sim.persistent_v2_shards merge STUDY PRELIMINARY_CATALOG --preliminary
python -m punishment_sim.persistent_v2_shards export STUDY PRELIMINARY_EXPORTS --preliminary
python -m punishment_sim.persistent_v2_shards run STUDY --shard SHARD --rep-start 6 --rep-end 10
```

The range is per worker; it does not automatically launch workers or enforce a
cross-worker scheduler barrier. The successful preliminary merge is the global
coverage check in this workflow. It checks every planned task's first five
repetitions. After all Phase-II workers finish:

```text
python -m punishment_sim.persistent_v2_shards merge STUDY FINAL_CATALOG
python -m punishment_sim.persistent_v2_shards export STUDY FINAL_EXPORTS
```

Final merge/export requires complete final records; five-repetition tasks cannot
pass as final. Preliminary analysis can also select the first five after a
one-shot run. `--include-repetitions` requests the larger detailed CSV export.
`run --analyze-only --preliminary` validates/reanalyzes a shard's first-five view
without mining. Different exports/catalogs use separate destinations. Do not
reuse a previous .60 directory: the design/plan fingerprint rejects it.

Readers hold shared shard locks and workers exclusive locks. Merge/export needs
quiescent workers; it fails rather than reading concurrently through a writer.
A partially completed but stopped Phase II leaves the preliminary snapshot stable.
No shared SQLite writer, remote scheduler, or background production launcher was
introduced. Code/Python fingerprints still require an exact compatible runtime;
retain the tested source and control/receipt files with the dataset.

## Safe native-validator changes

The pre-change validator is preserved as
[`_persistent_v2_compact_validation_reference.py`](../analysis/_persistent_v2_compact_validation_reference.py).
Native validation still runs once per fresh condition, before compaction and
receipt issuance. No sampling of trajectories or wholesale validator bypass was
implemented.

1. **One reaction reconstruction.** The event-by-event `PublicReplay` already
   reconstructs private discoveries, release/abandon decisions, all reaction
   opportunities, publication episodes and final private states. Its reconstructed
   history is compared with the complete recorded reaction history, detecting
   missing as well as altered reactions. The additional `replay_reactions` pass
   is removed from the normal validation path. Its release-label assertion is
   explicitly retained inside `apply_episode`.
2. **Exact comparison fast path.** Native trees are compared using typed,
   non-memoized marshal-v2 byte encodings. Equal bytes imply the same ordered typed
   tree, including bool/int/float and signed-zero distinctions. One canonical JSON
   encoding still verifies JSON representability. Different encodings, ordering,
   tuple/list representation or unsupported types fall back to the original two
   canonical JSON comparisons. This preserves acceptance; marshal is neither
   persisted nor decoded, and SHA-256/HMAC provenance is unchanged. An initially
   tested Python recursive comparator was slower and was not retained.
3. **No unused production debug records.** Production validation no longer builds
   the per-event debug-description and choice dictionaries that only debug/trace
   comparison consumes. RNG draws, fork-choice calculations and all assertions
   still run. Debug/audit paths retain those dictionaries and comparisons.
4. **Immutable metadata cache.** A bounded cache holds immutable miner definitions
   for hashable frozen populations. List-valued/mutable caller inputs use the
   original uncached path. Result identity, population, seed and trajectory checks
   remain per result. No trajectory state is cached.
5. **Baseline references unchanged.** Their already-small validation cost did not
   justify additional complexity.

The consolidated pass preserves the former reaction contracts:

| Former assertion | Retained enforcement |
| --- | --- |
| Private owner, base visibility and chain parent | Discovery RNG/owner checks and expected parent/withholding at every event |
| Reaction frame ordering, observed publications, height, round and decisions | Complete independently reconstructed reaction-history comparison |
| Missing or extra reaction | `apply_episode` checks every opportunity and consumes all recorded publication batches |
| Atomic release, released IDs and ordering | Exact release batch/plan matching plus ledger publication sequence/batch checks |
| Target/member release labels | Explicit release-kind check before applying the batch |
| Terminal private and abandoned coverage | Reconstructed private states, hidden-block coverage and full terminal comparison |

Dedicated tests compare old/new acceptance on every variant, both lambdas,
production/debug modes and baselines/HF/SC. Tampering tests cover ownership,
missing reactions, duplicate/altered publications, valid-height wrong-parent fork
choices, release labels, actor accounting and terminal bounds. JSON equivalence
checks include reordered dictionaries, tuple/list values, bool/int/float changes,
signed zero, nonfinite values, Unicode escape equivalence and non-JSON values.

## Measurements and planning

The fixed local benchmark uses the **same 14 tasks and 700 unique conditions**
as the previous compact benchmark: all six variants at lambda 0/.02 for two
members, plus six-member ignore/selfish at lambda .02, ten repetitions each,
30,000-block targets, identical populations and seeds. It executes 5+5 and checks
all native-result hashes against prior compact records. Final scientific output
hashes match after removing only the new explicit reporting-status fields.

For the 14 full-SC repetition-1 cases, the frozen reference and individual
optimization candidates are timed separately in interleaved passes. All variants
must accept the same raw result. Full phase timings separate mining, validation,
extraction/hashing, aggregation and serialization/writes; comparison instrumentation
is excluded from production projections. An interrupted pilot and small isolated
comparison checks are retained separately in ignored local results.

[Benchmark evidence](persistent_v2_51pct_benchmark.json) and
[projection evidence](persistent_v2_51pct_projection.json) contain the measured
values. The completed measurements and final verification are recorded below.

Runtime projections use exact new condition counts and measured mixed workload
rates with ideal 28-way scaling. The two/six-member samples are representative
illustrations, not performance bounds on every grid cell or confidence intervals.
They exclude final merge/export, startup and untimed bookkeeping. High-power,
skewed populations, target hardware, worker imbalance and I/O remain uncertainties.

Storage uses actual 1,000-task SQLite packing of measured five/ten-repetition
records, exact ID lengths, shared baselines amortized over six variants, and
cardinality interpolation across the exact inventory. Final storage retains the
preliminary derived rows and both catalogs. Regular/detailed export projections
are reported separately; retaining both preview and final CSV snapshots costs
more. A factor-of-two allowance covers planning headroom, not a proven upper
bound. Backup space is separate. No previous 7.7-TB capacity figure is assumed.

## Verification and deployment limits

The local tests establish phase ranges, native seed/identity invariance, exact
split/one-shot final equality, stable first-five outputs after partial II,
correct df=4/9, nonfinal marking in every preliminary CSV, final-merge rejection
of incomplete tasks, interruption recovery, baseline reuse and validator rejection
equivalence. Full native simulation semantics and historical petty-v4 source/config
hashes are preserved.

Before even a small remote deployment test, the operator must select a compatible
runtime/source snapshot and check available capacity, local SQLite/file-lock/fsync
behavior, RAM and worker isolation on the intended host. Those environmental checks
were intentionally not performed here. A bounded deployment test would still be
needed before treating ideal 28-core estimates as scheduling commitments.

No production sweep, SSH, `/xtra` access, remote job, historical checkpoint import,
or interaction with the running historical petty-v4 experiment occurred. Only
unit fixtures and the explicitly bounded local benchmark executed simulations.


## Completed benchmark and projections

All **700 unique conditions / 14 tasks** completed in the fixed 5+5 benchmark.
Every native production-result hash matched the old compact checkpoint, and all
fourteen final scientific output hashes matched the old one-shot result after
removing only the newly added reporting-status fields. All fourteen frozen/current
native-validator comparisons accepted identical raw inputs. No first-phase mining
was repeated in Phase II; completed compact-only resume also mined zero conditions.

| Measured workload | Previous validation / condition | Current validation / condition | Previous total timed phases / condition | Current total timed phases / condition | Validation fraction, before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Two members, all variants / both lambdas | 0.895 s | **0.808 s** | 1.732 s | **1.653 s** | 51.69% → **48.90%** |
| Six members, ignore/selfish at lambda .02 | 1.111 s | **0.993 s** | 2.132 s | **2.023 s** | 52.11% → **49.10%** |

Full benchmark mining totals were 342.111 / 143.056 seconds for the two/six-member
studies; native validation 420.284 / 178.814; extraction/hashing 96.559 / 42.161;
aggregation 0.224 / 0.079; and serialization/writes 0.253 / 0.075. Compact validation
counters added 0.057 / 0.025 seconds. Peak process RSS was **850.4 MiB**, including
reference-validation instrumentation. The counters use elapsed worker time, not
isolated CPU-time profiling, and exclude diagnostic reference/comparison timing.

Separately, interleaved candidate timing on the fourteen fixed full-SC cases gives
these sums of per-case median validation times:

| Comparator / candidate | Summed medians | Change from current unoptimized control |
| --- | ---: | ---: |
| Frozen pre-change validator | 14.927 s | reference |
| Current control with optimization flags disabled | 15.159 s | 0% |
| Exact comparison fast path alone | 14.798 s | −2.38% |
| Consolidated reaction pass alone | 14.284 s | −5.77% |
| Omit unused production debug structures alone | 15.025 s | −0.89% |
| Immutable miner cache alone | 15.166 s | +0.04% |
| All implemented changes | **13.712 s** | **−9.54%** |

The combined change is **8.14% faster than the frozen reference** in this paired
measurement. The metadata-cache difference is negligible; no measurable isolated
speed benefit is claimed. Small differences between control/reference and among
individual candidates are sensitive to timing noise. The historical whole-benchmark
averages and this paired experiment are distinct comparisons; neither is presented
as a guaranteed speedup for every grid cell. Native trajectory checking is still
about half of timed execution and is never replaced by summary-only validation.

| Production phase | Unique simulations | Nominal block work | Projected single-worker days | Ideal 28-core days |
| --- | ---: | ---: | ---: | ---: |
| I: repetitions 1–5 | **39,441,300** | **1,183,239,000,000** | 756.91–918.23 | **27.03–32.79** |
| II: repetitions 6–10 | **39,441,300** | **1,183,239,000,000** | 752.14–929.10 | **26.86–33.18** |
| Full ten repetitions | **78,882,600** | **2,366,478,000,000** | 1,509.05–1,847.34 | **53.89–65.98** |

The model is the sum of measured mining, native validation, extraction, compact
validation, aggregation and write seconds, divided by measured unique conditions,
times the exact phase count. Phase II includes re-reading the first five compact
repetitions and producing ten-repetition statistics. No native-validation phase is
subtracted hypothetically. Final merge/export times are separately measured in the
benchmark evidence and excluded from these throughput illustrations.

**Phase I plausibly takes approximately a month under ideal 28-core scaling, but
has no comfortable one-month margin.** The higher-cost illustration is already
32.79 days before host differences, stragglers, merge/export and high-power tails.
This is not a promised deadline. The full study's measured illustrations fall from
the previous 67.86–83.55 days to 53.89–65.98 days with the cutoff and safe changes.

All storage figures below are decimal GB/TB. Catalog estimates include the
preliminary catalog, and full completion additionally retains the final catalog.

| Artifact / allowance | After Phase I | Full completion |
| --- | ---: | ---: |
| Shard databases | 91.75 GB | 183.54 GB |
| Catalogs | 14.01 GB | 28.23 GB |
| Primary dataset | **105.76 GB** | **211.77 GB** |
| Regular CSV exports of the selected snapshot | 208.56 GB | 207.68 GB |
| Optional detailed repetition CSV | 324.48 GB | 647.87 GB |
| Dataset + regular exports | 314.32 GB | 419.45 GB |
| Dataset + all exports | 638.80 GB | 1,067.32 GB |
| 2× allowance, regular exports | **628.64 GB** | **838.90 GB** |
| 2× allowance, detailed exports included | **1.278 TB** | **2.135 TB** |

Phase II adds about **106.01 GB** to the primary dataset. Measured packing per
1,000 tasks is 55.21–92.01 MB after five repetitions and 111.05–183.44 MB at final
completion. The comparison tables contain exactly 73,321,200 equal-power rows and
15,624,000 cross-rule rows; the CSV projection allows 919 bytes per comparison row.
Plan/control files are small relative to these forecasts and are covered by the
planning headroom; backup copies still need their own capacity allowance.

Compared with the earlier 227.13-GB / 942.65-GB / 2.499-TB projections, the new
primary dataset falls **6.76%**, regular-export allowance **11.01%**, and detailed-
export allowance **14.59%**. The storage decrease is smaller than the simulation
count decrease because the phased workflow retains additional derived snapshots.
If both preliminary and final CSV exports are retained, full-completion allowances
rise to **1.256 TB** with regular exports or **3.201 TB** with both detailed exports.
Thus keeping every preview export can exceed the old detailed-export allowance.
These are projected requirements; no available capacity was assumed or checked.


## Final verification and changed files

The complete local command `.venv/bin/python -m pytest -q` passed with
**1,042 passed, 9 xfailed in 78.15 seconds**. The nine expected failures remain
historical-v1 limitations. The fixed benchmark completed and its runtime/source
fingerprint matches the tested code. `git diff --check` and explicit whitespace
checks of all new/modified untracked files pass. A before/after hash guard confirms
**65 protected historical engine/configuration/fixture files are unchanged**.

Modified existing files: the persistent ten-repetition config;
`persistent_v2_checkpoint.py`, `persistent_v2_shards.py`, `persistent_v2_outputs.py`,
`persistent_v2_sweep.py`, `persistent_v2_production.py`; the compact config/evidence
tests; the exact scope planner and frozen old projection script; and links in the
three previous v2 design/readiness reports.

New files: the frozen validation reference; the fixed phased benchmark and its
projection script; three phase/validation/evidence test modules; this report;
and the .51 scope, benchmark and projection JSON evidence. Existing .60 benchmark
and scope measurements remain preserved. No production/remote commands were run.

No known local correctness blocker remains for preparing a **separately authorized,
bounded deployment test**. That test still needs the intended host's runtime,
filesystem, capacity and memory checks. Full production scheduling remains
conditional on those checks and representative high-power/skewed throughput;
the local ideal-scaling projection is not a deployment-time guarantee.
