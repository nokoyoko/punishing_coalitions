# Quick sampled-production throughput: 16 versus 28 workers

Run from the updated checkout on an otherwise idle Kinakuta, using its existing
Python environment. This explicitly runs the bounded benchmark, never a production
sweep. The output directory must be new.

```bash
.venv/bin/python -m analysis.benchmark_persistent_v2_quick --run --output results/persistent_v2_quick_16_vs_28
```

Print the saved result with:

```bash
.venv/bin/python -m analysis.benchmark_persistent_v2_quick --result results/persistent_v2_quick_16_vs_28/benchmark.json
```

There are exactly **two trials: 16 workers, then 28 workers**, both using sampled
validation. No 8/24-worker trial, full-validation comparison, or automatic repeat
is included. The earlier larger benchmark remains an optional historical tool;
it is not invoked by this entry point.

## Fixed workload: 1,152 unique conditions per trial

The benchmark prepares and validates the actual
`configs/persistent_v2_core_2to4_1pct_10rep.json` scientific plan without changing
the configuration. It selects 18 existing populations: one near-balanced and one
skewed composition for each of the nine cardinality/lambda pairs, where cardinality
is 2/3/4 and lambda is 0/.005/.02. Near-balanced means maximum/minimum member power
at most 1.5; skewed means at least 4. Within each cell, the minimum
`(SHA256(["persistent-v2-quick-concurrency-v1", population_id]), population_id)`
selects the population. Selection uses no simulation RNG and no validation outcome.

Run the first **two existing repetitions** at every selected population, for petty,
counter-fork k=1/2/3 separately, ignore and selfish. Include H, S0, HF, SC and every
leave-one-out; H/S0 are mined once per population/repetition, not once per rule.
All conditions retain the production 30,000-block horizon and their exact native
population/task/condition identity, seed, rule, gamma, composition and lambda.
The underlying production design still specifies ten repetitions; the benchmark
executes a subset and does not produce a two-repetition scientific study.

| Cardinality | Populations | Unique conditions, two repetitions |
| --- | ---: | ---: |
| 2 | 6 | 312 |
| 3 | 6 | 384 |
| 4 | 6 | 456 |
| Total | 18 | **1,152** |

Each lambda contributes 384 conditions. Totals by condition type are H=36,
S0=36, HF=216, SC=216, leave-one-out SC=648. This is a deliberately small,
stratified operational comparison, not a frequency-weighted estimate of the
entire production grid.

The **complete core plan's validation policy and 810 anchors are retained**.
No validation anchors are reselected on the 18-population subset. Its native
hash sampling and actual-path risk overrides therefore make exactly the same
decision as production for each chosen condition. Actual replay count/fraction
is measured; neither a 1% total replay fraction nor any speedup is assumed.
The current deterministic subset contains **zero core anchor populations and
seven hash-selected replay conditions**, before actual-path overrides. Anchors
were not excluded from selection; none happened to win these 18 population draws.
The condition-ID inventory SHA-256 is
`e4a67577af89eec7b7085860d1073cf174a1865998aa33e0f1e0fb7a4de275f3`.

Both pools receive the same deterministically interleaved 216 work units
(population × repetition × rule), so concurrency is not limited to 18 population
jobs. Workers call the existing production `_condition` function, including native
mining, lightweight checks, sampled native replay, compaction and authenticated
storage. Separate benchmark unit stores prevent writer contention. Their flagged
records use a benchmark-only record kind and are not production checkpoints for
import/merge. Production shard ownership, code and validation semantics are unchanged.
This measures the CPU-bound condition pipeline; production shard scheduling and
five/ten-repetition statistical reductions are not reproduced in this short test.

## Output and runtime budget

Immediately after each trial, one compact JSON summary reports workers, unique
conditions, wall seconds, conditions/second, summed mining/lightweight/native-replay
seconds, actual replay count/fraction and average busy cores. Wall time includes
process startup, dispatch, per-worker provenance checks, unit storage and shutdown.
Full-plan preparation and subset selection happen once, before either trial, and
their elapsed time is reported separately. Phase timers and CPU seconds are summed
worker times; they must not be mistaken for wall time.

The final lines print the rates at 16 and 28 workers and the ratio/percentage
change, `28/16`. Condition coverage must exactly match the planned IDs; native
result hashes and validation-selection hashes must agree between both trials.
A failure stops the benchmark, marks its report failed and prevents automatic
retry/resume. No production-duration extrapolation is printed.

There are **2,304 conditions / 432 rule-repetition records in total**. At the
previously reported 1,923 records/hour, that is about **13.5 minutes** of work if
aggregate throughput were equal at both counts. If one trial were twice as slow
as that reference, the total would be about **20.2 minutes** plus planning/startup.
These are workload-sizing checks, not measured performance or assumptions of
linear scaling; actual subset costs and contention can differ. The workload has
been reduced fifteenfold from 17,280 to 1,152 conditions per worker count.

If the rates are within roughly 5%, an optional **later** invocation may add
`--reverse` and use a different fresh output directory. It runs 28 then 16, still
only two trials. It is never triggered automatically.

`--describe` enumerates the complete plan and prints the subset/known replay
selection without constructing a simulator. Local regression tests for this
entry point prohibit simulator construction and use synthetic results to check
execution order, native-pipeline wiring, identical queues, failure handling,
summary fields and result printing. No simulations were run for this update.
