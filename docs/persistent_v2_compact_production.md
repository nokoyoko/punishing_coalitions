# Persistent v2: ten repetitions and compact production storage

Current production planning is documented in [the 0.51 cutoff and fixed 5+5 workflow](persistent_v2_51pct_phased_production.md). Earlier scope/runtime figures below remain historical evidence.

The intended design is now **ten independent repetitions for every configuration**,
at 30,000 reference-chain blocks, across all six variants. There is no staged
increase to twenty. Historical petty-v4 remains unchanged at its existing settings.

The new [configuration](../configs/persistent_v2_1pct_10rep.json) copies the existing
scientific grid, composition sampling, Eyal–Sirer authorization, detector grids,
bootstrap count and seed. Only persistent-study repetitions change. The network,
policies, common random streams, stopping, accounting and conservative terminal
bounds are unchanged. No production/remote sweep was launched, and no SSH or
`/xtra` access occurred. The only 30,000-block execution is the fixed local
benchmark described below.

## Exact scope and statistics

[Scope evidence](persistent_v2_10rep_scope.json) is produced by
[`analysis.plan_persistent_v2`](../analysis/plan_persistent_v2.py), which enumerates
and deduplicates the actual native task definitions without mining. It records
the configuration hash, plan hash, cardinality counts and deterministic 28-shard
allocation. The 1% target/total grids, gamma/lambda grids, cardinalities 2–6,
minimum member power .01 and selected HHI compositions are identical to the
historical grid; no historical checkpoint is imported.

| Quantity | Ten-repetition plan |
| --- | ---: |
| Distinct population/environment configurations | 250,170 |
| Top-level configurations across six variants | 1,501,020 |
| Represented simulations per variant | 19,967,100 |
| Six variants before baseline reuse | 119,802,600 |
| Unique shared H/S0 simulations | 5,003,400 |
| Policy-specific simulations per variant | 14,963,700 |
| Duplicate baselines saved | 25,017,000 |
| Unique simulations after reuse | **94,785,600** |
| Nominal block work before reuse | 3,594,078,000,000 |
| Nominal block work after reuse | **2,843,568,000,000** |

Each lambda has 83,390 populations, 6,655,700 represented runs per variant,
39,934,200 runs before reuse, **31,595,200 after reuse**, and
**947,856,000,000** nominal block work after reuse. Populations by cardinality
2/3/4/5/6 are 50,406 / 50,964 / 50,406 / 49,662 / 48,732.

Compared with the previous twenty-repetition plan, mining and block work halve
exactly; top-level counts do not change. The common baselines are a shared cost,
not six independent datasets. With the configured variant order, petty computes
the common baselines first (19,967,100 physical runs); each subsequent variant
adds 14,963,700 policy-specific runs. Six-way equal allocation of that shared cost
would be 15,797,600 runs per variant, an accounting allocation only.

The existing paired reducer already contains **t(0.975, df=9) = 2.262** (its
tabulated three-decimal precision). Ten paired observations use sample SD,
SE=SD/sqrt(10), and this t multiplier, not 1.96. Tests explicitly check that
distinction. Bootstrap sample indices use `len(rows)` and resample matched
(H,S0,SC) tuples; there is no hard-coded twenty-observation requirement. Existing
Student-t p-values take df=n−1. Strict coverage checks reject missing repetitions
instead of silently reducing n. Weak/strict classifications and CRN estimators
are unchanged. Stage C output is a review/selection table only and explicitly
sets `automatic_followup=false`; no additional experiment is scheduled.

## What is sufficient after a condition completes

The downstream consumption audit follows `coalition.study`, the persistent v2
statistical bridge, `tpr_threshold`, classification/threshold functions and the
new output adapter. These consumers need actor payoffs/counts, opportunity and
activation counts, natural-pair counts, paired condition coverage and terminal
diagnostics. They do not inspect parent links or replay a branch to calculate a
mean, CI, detector mixture, credibility or deviation margin.

Schema **`persistent-scientific-condition-v2-compact-1`** retains:

| Data | Retained representation / use |
| --- | --- |
| Every actor, including target, each candidate and residual | Role/power, discoveries, canonical rewards, public noncanonical count, hidden count, payoff, normalized revenue; exact accounting and every payoff calculation |
| Paired condition | Full native identity: population, seed, repetition, strategy, active coalition, rule/k, network/RNG/propagation/reaction/stopping versions; matched vectors and deterministic rerun |
| Horizon | Discovered events and actual accepted/reference height, including any atomic overshoot |
| Punishment | Opportunities, activations, natural pairs, episode outcomes/counts, reaction/publication/reorganization counts and hashes, reorganization-depth range |
| Terminal boundary | The existing complete `boundary` dictionary, unchanged—including conservative actor bounds and materiality/censoring interpretation |
| Public/private frontiers | Exact counts and hashes, owner counts, height/deficit count/min/max/sum, alternate path/common-ancestor/exposed-reward summaries |
| Private strategy state | Per-actor phase, private count/tip/base/height/lead, exposure status; sequence counts and hashes replace released/abandoned/private ID vectors |
| Active endpoint | Retaliation state (long list fields summarized), exact pending propagation window and reaction queue; ignore eligible-frontier summaries and deficits |
| Reproducibility/provenance | Canonical terminal and production-result hashes, terminal RNG snapshots, source/Python fingerprint, completed native-validation receipt |

Canonical block records, parent links, full publication/policy/reaction histories,
step traces and full frontier paths are useful for independent replay, inspection
and visualization. They are not stored in normal completed checkpoints. They can
be regenerated from the retained identity. `rerun_condition(..., trace=True)`
rebuilds the full result, validates it and requires an identical production-result
hash and compact scientific record. Tests perform this audit for all six variants.

No branch is pruned during mining. No approximation replaces the existing
unresolved-boundary treatment: material endpoints retain actor bounds [0,1], not
a smaller bound inferred from height deficits. Hashes commit to the omitted
structures; they are not asserted to prove that the omitted history is correct
without native validation or regeneration. Exact active propagation windows are
retained rather than inventing a smaller future-state abstraction.

## Checkpoint granularity and streaming

| Granularity | Storage / recovery tradeoff |
| --- | --- |
| Full condition tree | Megabytes per condition; detailed offline replay, but excessive durable storage and file count |
| Compact condition row | Small payload and minimal lost work; roughly 95 million condition rows and weaker cross-condition compression |
| **Compact configuration + repetition** | Chosen: compress active conditions together, retain baseline references, atomically commit a complete matched repetition |
| Compact whole configuration | Fewer rows, but an interruption can lose ten repetitions of active conditions instead of one |

Every new condition follows: mine → complete native ledger/RNG validation →
extract the compact scientific record → discard raw result/tree → continue.
Active conditions accumulate only for the current repetition. Shared H/S0 are
committed individually as soon as validated so a later interruption cannot lose
completed common baselines. Once all active conditions in a repetition exist,
one transaction commits its compact bundle plus the two baseline ID/hash references.

A killed condition restarts with the same seed. An interruption before repetition
commit loses at most that repetition's active conditions (m+2 for a full m-member
coalition); committed baselines and earlier repetitions survive. There is no
claim to resume partway through an engine trajectory. A completed task record
contains derived scientific summaries and the hashes of all its repetition
bundles. Repetition-level vectors are reconstructed from those bundles and shared
baselines, rather than stored again inside every derived task result.

## Independent writers, shared baselines and storage layout

```text
study.json                         immutable design/runtime/plan/key fingerprints
plan.sqlite3                       immutable, indexed population task ownership
receipts/shard-00.key ... -27.key   private native-validation receipt keys
shard-00.sqlite3 ... -27.sqlite3    one independent writer/database per shard
shard-00.lock ... -27.lock          exclusive worker / shared reader locks
merged.sqlite3                     validated catalog; baseline payloads remain shared
exports/                           optional derived CSVs, generated without mining
```

Population ownership is `int(population_digest[:16],16) % 28`. All six variants
and all repetitions for a population go to that owner, so H/S0 are physically
stored and computed once. There are no cross-shard baseline writes or twenty-eight
writers contending for one SQLite database. Local tests run twenty-eight isolated
workers, including empty shards. A second writer for the same shard fails at the
file lock. Plan/design mismatches, different source/Python fingerprints and wrong
receipt keys fail before processing.

Each database has one keyed `records` table containing `baseline`, `repetition`,
`task` and shard `complete` records. Payloads use canonical JSON, zlib compression,
SHA-256 and HMAC receipts bound to study/shard/kind/key/checksum. SQLite uses
rollback journals and `synchronous=FULL`; inserts and completion records are
transactional and immutable. No scientific outputs depend on wall-clock times.

The private receipt keys authenticate the trusted worker's completed native
validation. They prevent a changed compact record with a merely recomputed public
checksum from masquerading as a validated trajectory. Keep the control manifest,
keys and databases together, with the keys restricted to trusted operators.
This is not a proof against a compromised signing worker/key. Unauthenticated
external summaries and historical v4/v1 checkpoints are not accepted. The keys
do not enter mining RNG or scientific identities.

Strict merge holds shared locks, requires every shard complete, checks ownership,
integrity, authenticated records, exact repetition/condition coverage, baseline
references and conservation, reconstructs scientific analyses and checks them
against the signed task records. Extra/missing rows and duplicate task IDs fail.
The merged catalog is published by atomic rename; source baselines are referenced
without copying their payloads. Source shards/control files remain part of the
dataset. An interrupted merge leaves the authoritative shard checkpoints intact.

## Validation cost and analysis compatibility

Newly mined results still receive the complete native validator once. That cost
is not bypassed by trusting an accounting total. Population/task/runtime checks
sit at outer boundaries. Baselines loaded within one population are validated
once and reused for all variants; subsequent uses check their identities and
references. Durable compact reads verify the native receipt, checksum, identity,
actor/global conservation, exact payoff arithmetic, horizon, RNG draw count and
unchanged conservative bounds. They do not reconstruct tens of thousands of
blocks again. Full replay is available through explicit deterministic auditing.

`persistent_v2_outputs` produces coalition results, member credibility, detector
evaluations, continuous TPR/bootstrap thresholds, false-positive costs, weakest
member summaries, boundary diagnostics, minimal winning coalitions among supplied
coalitions, minimum tested thresholds, review-only Stage C candidates, and paired
composition/rule comparisons. Export streams one bounded environment/total group
at a time; threshold reduction is disk-backed. Detailed repetition exports are
optional to avoid duplicating shared actor/terminal summaries in a large CSV.
Their exact vectors always remain available in compact checkpoints.

A ten-repetition fixture covers both lambdas, two different compositions and all
six variants. Its complete scientific output collections—including terminal
summaries, false-positive costs, thresholds, Stage C candidates, and cross-rule
and equal-power paired comparisons—match the full/debug analysis exactly. The
comparison uses the existing full-result reducer before terminal summarization.
No production legacy-mining fallback is possible.

Normal `persistent_v2_sweep` production mode now uses compact shards. The prior
full-ledger runner remains explicitly named `run_full_ledger_production` for
diagnostic compatibility; diagnostic full traces/checkpoints remain available.
Old output layouts are not silently converted or mixed with compact stores.

## Local benchmark and remaining readiness checks

The fixed [benchmark](../analysis/benchmark_persistent_v2_compact.py) uses fourteen
top-level tasks, ten repetitions and a 30,000-block target: all six variants at
lambda 0/.02 for one two-member composition, plus six-member ignore/selfish cases
at lambda .02. It is 700 unique conditional runs with common H/S0 reused, not the
research grid. Source/config identities and detailed phase timings/sizes are in
[benchmark evidence](persistent_v2_compact_benchmark.json). Full-ledger byte sizes
are measured only by transient encoding in memory; no full tree checkpoint is
written. SQLite growth is also measured by an isolated 1,000-task packing probe
using actual compact blobs, clearly distinguished from mining.

The final complete local suite passed **997 tests with nine expected historical-v1
failures in 70.27 seconds**. Resume tests inject interruptions midway
through a condition, after condition completion, before/after repetition commit,
after task completion and during database flush. A subprocess also exits abruptly
inside an uncommitted SQLite write. Resumed scientific records equal uninterrupted
records, committed baselines are not mined again, and duplicate rows do not appear.
Corruption with recomputed public checksums is rejected by receipt validation;
incomplete shards cannot merge.

The benchmark completed all **14 tasks / 700 unique conditions**. Every task used
ten repetitions and a 30,000-block target. Actual reference heights were
30,000–30,001 because the existing atomic stopping semantics permit overshoot;
discoveries ranged from 30,000 to 46,288. These measurements are operational
diagnostics and are not scientific findings about punishment effectiveness.

| Measured phase | 12 two-member tasks, 520 unique conditions | Two six-member tasks, 180 unique conditions |
| --- | ---: | ---: |
| Mining | 337.464 s | 140.838 s |
| Full native validation, once per new condition | 465.522 s | 200.003 s |
| Compact extraction and trajectory/terminal hashing | 97.271 s | 42.870 s |
| Statistical aggregation | 0.132 s | 0.049 s |
| Compact validation during execution | 0.039 s | 0.017 s |
| Compact serialization / database writes | 0.221 s | 0.067 s |
| Complete compact-only resume, including analysis | **0.245 s** | **0.113 s** |
| Strict merge | 0.259 s | 0.111 s |
| All CSV exports, including repetitions | 0.316 s | 0.279 s |

The former full-ledger audit measured 0.806–1.058 seconds of validation per
condition. Fresh native validation remains expensive: the new mixed benchmark
averages 0.895 seconds per two-member condition and 1.111 seconds per six-member
condition. It independently reconstructs ledger ownership, ancestry, strategy
transitions, RNG streams and fork choices; summary conservation alone cannot
replace those checks. The improvement is avoiding repeated native validation and
large JSON/tree reconstruction on reuse, resume and analysis. Compact resume's
record validation alone took 0.035 / 0.018 seconds for the two studies. The
measurements do not claim a speedup in the native validator itself.

| Payload / physical storage | Measured size, decimal units |
| --- | ---: |
| One shared H/S0 compact record | 1,766–2,606 bytes compressed; mean 2,255 |
| One rule-specific compact condition, measured separately | 1,843–3,235 bytes compressed; mean 2,605 |
| One two-member repetition bundle | 4,822–6,965 bytes |
| One six-member repetition bundle | 12,470–14,071 bytes |
| Ten-repetition two-member task, bundles + derived task record | 52,616–72,958 bytes, excluding shared baselines |
| Ten-repetition six-member task, bundles + derived task record | 133,440–145,560 bytes, excluding shared baselines |
| Shared baseline payload for all ten repetitions of a population | 40,776–49,790 bytes, once for all six variants |
| Former full-condition checkpoint payloads per two-member task | 76.81–91.06 MB, including H/S0 |
| Former full-condition checkpoint payloads per six-member task | 170.88–171.14 MB, including H/S0 |
| SQLite packing per 1,000 two-member tasks | **106.16 MB** |
| SQLite packing per 1,000 six-member tasks | **174.67 MB** |

Compact task payloads plus a one-sixth allocation of common baselines are about
59–80 KB for two members and 142–154 KB for six members. These payload comparisons
exclude SQLite page/index overhead. The physical packing probe includes that
overhead and amortizes twenty baseline records across six task records. It uses
measured compressed blobs, with synthetic keys slightly shorter than real
baseline IDs; it is a storage probe, not another thousand mining tasks. Across
the actual fourteen-task benchmark, compact databases occupied 1.692 MB; unique
full-condition payloads alone would occupy 1.098 GB before database overhead.

Peak process RSS was **932,839,424 bytes (889.6 MiB)**. This high-water mark
includes validation and in-memory encoding of old checkpoint payloads for the
size comparison. It is not an isolated per-task peak. Multiplying it by 28 gives
24.3 GiB before operating-system and other workloads; high-power/skewed cells can
need more. Full raw state exists transiently for one condition, never as an
accumulating durable collection.

The reproducible [projection script](../analysis/project_persistent_v2_compact.py)
and [projection evidence](persistent_v2_compact_projection.json) combine exact
cardinality counts with linear interpolation between measured two/six-member
storage. They also count **88,387,200 equal-power comparison rows** and
**18,762,750 cross-rule comparison rows**, allowing 892 bytes per plain comparison
CSV row (largest measured row plus 256 bytes). Decimal storage estimates are:

| Full-study artifact | Projected size |
| --- | ---: |
| 28 shard databases | 210.29 GB |
| Merged derived catalog | 16.84 GB |
| Primary dataset | **227.13 GB** |
| Regular plain CSV exports, including comparisons | 244.20 GB additional |
| Optional detailed repetition CSV | 778.30 GB additional |
| Dataset + regular exports | 471.33 GB |
| Dataset + all plain exports | 1.250 TB |
| Working-space allowance, twice dataset + regular exports | **942.65 GB** |
| Working-space allowance, twice dataset + all exports | **2.499 TB** |

The factor of two is a planning allowance for workload variation, temporary
outputs and headroom, not a proven upper bound. Backups require a separate budget.
Empty winning/Stage C tables in this diagnostic sample and unmeasured endpoint
variation are additional reasons not to treat point estimates as capacity bounds.
The primary compact dataset always retains the paired vectors; declining a large
repetition CSV does not remove statistical information.

Measured fresh execution phases give 1.732 seconds per unique condition in the
two-member mix. Applying that rate to 94,785,600 unique conditions gives 5.20
CPU-years, or **67.86 days at ideal 28-way scaling**. Applying the six-member
ignore/selfish rate of 2.132 seconds gives **83.55 days**. These are throughput
illustrations, not lower/upper confidence limits or a fitted full-grid forecast:
the full grid has a different baseline/active/cardinality mix. High-power and
skewed populations, different hardware, shard stragglers, shared I/O, final merge
and exports can increase elapsed time. Diagnostic old-checkpoint encoding time
is excluded from these projections. Fresh strict validation remains the largest
measured cost and has not been disabled to improve the estimate.

## Verification and operational status

`python -m pytest -q` completed with **997 passed, 9 xfailed**. The added coverage
checks n=10 / df=9, exact full/compact scientific equality, deterministic trace
regeneration at repetitions 0 and 9, all interruption points, abrupt process exit
inside a SQLite transaction, baseline reuse, provenance/tamper rejection,
recomputed derived analyses at merge, extra/missing rows, and unchanged scientific
results under different shard counts and execution order. Twenty-eight isolated
worker databases and same-shard writer exclusion are exercised locally. The
completed 30,000-block evidence is also checked against the current runtime
fingerprint. `git diff --check` and explicit whitespace checks of the new
untracked files pass.

The compact workflow is implemented and locally validated. **The full study is
not yet cleared for deployment.** Remaining checks are actual capacity for the
chosen export/backup policy, SQLite/file-lock/fsync support on the intended
filesystem, adequate worker memory, acceptable compute budget, and throughput/
memory measurements for higher-power/skewed grid cells. No remote capacity is
assumed from the earlier 7.7-TB report. Conservative unresolved-state flags remain
scientific interpretation limits and are preserved without changing the endpoint.

Historical petty-v4 configuration and tracked sources remain unchanged. Recorded
hashes also confirm the historical persistent engines, native v2 engine and
fixtures are unchanged; the existing v2 entry points changed only to select the
compact runner and ten-repetition default. No historical checkpoint was imported
or relabeled. No production sweep, SSH, `/xtra` access, remote job, or interaction
with the running historical experiment occurred.

Implementation files added are `persistent_v2_compact.py`,
`persistent_v2_shards.py`, `persistent_v2_outputs.py`, the ten-repetition config,
the three plan/benchmark/projection scripts, this report and its three JSON
evidence files, and `test_persistent_v2_compact.py`. Existing v2 production/sweep
entry points, their compatibility/default tests, and v2 design/readiness
documentation were updated.
