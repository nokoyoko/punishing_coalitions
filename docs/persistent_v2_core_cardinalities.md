# Persistent v2 core cardinalities 2–4 and optional extensions

This is the current **future** production design. It supersedes the cardinality
scope and resource totals in the [earlier 2–6 report](persistent_v2_51pct_phased_production.md).
No production sweep or new 30,000-block benchmark was executed for this update.
Historical petty-v4 configuration, code, results, and jobs were not changed.

## Configurations and preserved science

| Dataset | Configuration | Cardinalities |
| --- | --- | --- |
| Core paper experiment | [persistent_v2_core_2to4_1pct_10rep.json](../configs/persistent_v2_core_2to4_1pct_10rep.json) | 2, 3, 4 |
| Optional extension A | [persistent_v2_extension_5_1pct_10rep.json](../configs/persistent_v2_extension_5_1pct_10rep.json) | 5 only |
| Optional extension B | [persistent_v2_extension_6_1pct_10rep.json](../configs/persistent_v2_extension_6_1pct_10rep.json) | 6 only |

`configs/persistent_v2_1pct_10rep.json` is an identical compatibility alias of the
core configuration. Use one of those two names, not two separate core runs.
The only scientific difference from the previous combined design is the selected
cardinality set. All three configs retain:

- coalition total power 0.05–0.51 and target power 0.10–0.35, both at 0.01 spacing;
- gamma `[0, 0.25, 0.5, 0.75, 1]` and lambda `[0, 0.005, 0.02]`;
- 0.01 member resolution/minimum, HHI quantile sampling with at most five per cell,
  minimum residual power 0.05 and Eyal–Sirer analytical authorization;
- persistent-network-v2 with petty, counter-fork k=1/2/3, ignore, and selfish;
- seed 51000, 30,000 reference blocks, ten repetitions, bootstrap count 2000;
- TPR `[0.5, 0.7, 0.9, 1]`, FPR `[0, 0.001, 0.01, 0.05, 0.1]`, CRN pairing,
  uncertainty/classification machinery, native validation and shared H/S0;
- fixed global Phase I repetitions 1–5, followed by Phase II repetitions 6–10.

Each extension uses the same fixed phase convention when run later. Phase I
means **all configurations of that dataset**, followed by its complete Phase II;
there is no adaptive cell selection. Global phase scheduling remains an operator
responsibility: validate complete preliminary coverage before starting Phase II.

## Exact enumeration

`python -m analysis.plan_persistent_v2` enumerates the actual native SQLite plans
for the prior 2–6 design and each separate config, without mining. It checks that
the full plan hash still matches the retained .51 scope artifact. It compares
canonical population bodies and all six rule-task IDs, sorted by population ID,
for every cardinality against the full plan. Per-cardinality hashes, configuration
hashes, plan hashes, shard counts and phase counts are stored in:

- [Core exact scope](persistent_v2_core_2to4_scope.json)
- [Extension-5 exact scope](persistent_v2_extension_5_scope.json)
- [Extension-6 exact scope](persistent_v2_extension_6_scope.json)

| Quantity | Core 2–4 | Extension 5 | Extension 6 |
| --- | ---: | ---: | ---: |
| Feasible total/cardinality cells | 141 | 47 | 46 |
| Sampled structures per environment | 681 | 222 | 217 |
| Authorized environments | 186 | 186 | 186 |
| Population/environment configurations | 126,666 | 41,292 | 40,362 |
| Rule configurations, six variants | 759,996 | 247,752 | 242,172 |
| Represented simulations before reuse | 53,199,720 | 22,297,680 | 24,217,200 |
| Unique shared H/S0 simulations | 2,533,320 | 825,840 | 807,240 |
| Unique simulations after reuse | 40,533,120 | 18,168,480 | 20,181,000 |
| Nominal accepted-block work | 1,215,993,600,000 | 545,054,400,000 | 605,430,000,000 |

“Before reuse” counts six independent rule runs, each containing H/S0. Each
population actually stores H/S0 once per repetition. Different cardinalities
are distinct populations; baselines are not incorrectly shared between them.
The three inventories are disjoint and sum exactly to the previous 2–6 totals.
All counts are exact; block work is the nominal reference-height target, with
existing atomic overshoot semantics unchanged.

| Reduction from prior 2–6 to core | Absolute | Percent |
| --- | ---: | ---: |
| Populations | 81,654 | 39.196428571% |
| Rule configurations | 489,924 | 39.196428571% |
| Before-reuse simulations | 46,514,880 | 46.648013430% |
| Shared baselines | 1,633,080 | 39.196428571% |
| Unique simulations | 38,349,480 | 48.615892478% |
| Nominal block work | 1,150,484,400,000 | 48.615892478% |

Core population and rule-count reduction is exactly 81,654/208,320;
unique-simulation and block-work reduction is exactly 38,349,480/78,882,600.
Percentages above are rounded representations of those exact ratios.

| Work in **each** phase (I or II) | Core 2–4 | Extension 5 | Extension 6 |
| --- | ---: | ---: | ---: |
| Unique simulations | 20,266,560 | 9,084,240 | 10,090,500 |
| Shared H/S0 | 1,266,660 | 412,920 | 403,620 |
| Nominal block work | 607,996,800,000 | 272,527,200,000 | 302,715,000,000 |

Each lambda has the same counts within a dataset:

| Per lambda, all 10 repetitions | Core 2–4 | Extension 5 | Extension 6 |
| --- | ---: | ---: | ---: |
| Populations | 42,222 | 13,764 | 13,454 |
| Unique simulations | 13,511,040 | 6,056,160 | 6,727,000 |
| Nominal block work | 405,331,200,000 | 181,684,800,000 | 201,810,000,000 |

## Runtime projections from existing evidence

`python -m analysis.project_persistent_v2_cardinalities` reuses the completed
[local .51 benchmark](persistent_v2_51pct_benchmark.json). Its runtime fingerprint
still matches the current mining/validation/reduction pipeline: those source
files are unchanged. No benchmark was rerun. The new collection layer is analysis
only and has a separate source fingerprint. Detailed artifacts:
[core](persistent_v2_core_2to4_projection.json),
[extension 5](persistent_v2_extension_5_projection.json), and
[extension 6](persistent_v2_extension_6_projection.json).

Ranges use the measured mixed two-member/all-rule and six-member/ignore/selfish
rates: Phase I 1.658081–2.011482 seconds per unique condition; Phase II
1.647644–2.035289. These are representative scenarios, not confidence bounds or
measured full-grid throughput. They include mining, native validation, extraction,
compact validation, aggregation and checkpoint serialization/write. They exclude
setup, final merge/export, untimed bookkeeping, and target-machine effects.
High-power/skewed cells remain unmeasured.

| Ideal 28-worker elapsed days | Core 2–4 | Extension 5 | Extension 6 |
| --- | ---: | ---: | ---: |
| Phase I | 13.89–16.85 | 6.23–7.55 | 6.92–8.39 |
| Phase II | 13.80–17.05 | 6.19–7.64 | 6.87–8.49 |
| Full | 27.69–33.90 | 12.41–15.20 | 13.79–16.88 |

Kinakuta hardware is **user-supplied information**, not remotely verified:
32 logical CPUs, 16 physical cores. Running 28 workers uses SMT/hyperthreads;
the table assumes ideal 28-worker scaling and is not a guaranteed wall-clock
schedule. As a rough alternative, assuming throughput equal to only 16 of the
measured local workers gives these full-run days (also not a bound):

| 16-worker-equivalent capacity | Core 2–4 | Extension 5 | Extension 6 |
| --- | ---: | ---: | ---: |
| Full | 48.46–59.33 | 21.72–26.59 | 24.13–29.54 |

## Storage projections

All values below are **decimal GB** (10^9 bytes), estimates rather than exact disk
requirements. The JSON artifacts retain unrounded byte projections. The model
uses measured 1,000-task SQLite packing and two/six-member cardinality interpolation,
plus exact generated plan sizes. Primary storage includes shard databases and
source catalogs; final primary retains preliminary task records and both catalog
snapshots. The new logical collection manifest adds no baseline payload copies.

Regular exports include composition/rule comparisons and scoped thresholds;
detailed repetition CSVs are optional. Exact comparison-row counts are recalculated
within each dataset, so independent extension budgets exclude cross-cardinality
pairs with core. Scoped columns receive 200 bytes per row and pooled threshold
rows 32 KiB per row of additional allowance. These are planning allowances, not
worst-case proofs. The 2× columns cover the listed dataset/exports plus headroom
for journals, temporary per-source merge catalogs and reduction indexes; independent
backup copies require additional space.

| Phase-I snapshot, GB | Core 2–4 | Extension 5 | Extension 6 |
| --- | ---: | ---: | ---: |
| Primary databases/control/catalogs | 55.65 | 23.97 | 26.28 |
| Regular CSV exports | 114.03 | 38.77 | 41.96 |
| Detailed repetition CSV exports | 150.75 | 80.69 | 94.29 |
| 2× primary + regular | 339.35 | 125.49 | 136.48 |
| 2× primary + regular + detailed | 640.84 | 286.87 | 325.07 |

| Final 10-repetition snapshot, GB | Core 2–4 | Extension 5 | Extension 6 |
| --- | ---: | ---: | ---: |
| Primary databases/control/catalogs | 111.65 | 47.86 | 52.39 |
| Regular CSV exports | 113.61 | 38.56 | 41.71 |
| Detailed repetition CSV exports | 301.17 | 161.05 | 188.15 |
| 2× primary + regular | 450.52 | 172.84 | 188.20 |
| 2× primary + regular + detailed | 1,052.85 | 494.94 | 564.50 |

If retaining **both Phase-I and final CSVs**, the final 2× budgets are:

| Final retained-output allowance, GB | Core 2–4 | Extension 5 | Extension 6 |
| --- | ---: | ---: | ---: |
| Regular CSVs at both snapshots | 678.58 | 250.39 | 272.13 |
| Regular + detailed at both snapshots | 1,582.40 | 733.87 | 837.01 |

These extension costs are incremental independent datasets. A later **combined**
export has additional cross-cardinality equal-power comparisons and its own output
budget; summing the separate export budgets does not include those pairs. Existing
core CSVs are preserved because every export requires a new destination.

## Appendability and analysis semantics

Population IDs hash only the native population; rule-task IDs hash the network,
population-local configuration, rule and selected coalition set. Removing another
cardinality changes the overall study ID/plan, but not an existing population,
seed, repetition stream, condition ID, or rule-task ID. No identity implementation
needed changing. Exhaustive enumeration verifies this for every production task.
H/S0 reuse remains population-local across all six variants within each source.

Do not rewrite core's `study.json` to append more cardinalities. Prepare extensions
in independent directories and keep original plans, manifests, shards and receipt
keys. The new `punishment_sim.persistent_v2_collection` creates a **logical merge**:
its manifest references these source studies. It validates each selected source
using the existing strict authenticated merger, checks matching scientific designs
(except member counts and shard allocation), and rejects population/task collisions.
Receipts are never imported, reassigned or re-signed. Collection exports revalidate
the selected source studies, require their original study IDs and current runtime
fingerprints, and use analysis-only reconstruction. Missing/corrupt data cannot
trigger mining. Reader locks require source writers to be quiescent.

The default scope is always `core`, even when supplied extension directories or
an extended collection. No filesystem discovery is used. Allowed explicit scopes:

| Analysis scope | Selected datasets |
| --- | --- |
| `core` (default) | core 2–4 |
| `extended_2to5` | core + extension 5 |
| `extended_2to6` | core + extension 5 + extension 6 |
| `extension_5` | extension 5 only |
| `extension_6` | extension 6 only |

Every nonempty CSV row records `analysis_scope`, `analysis_cardinalities`, and
`source_dataset_role` (`core`, `extension_5`, `extension_6`, or `selected_scope`
for reductions/comparisons). `status.json` pins the selected source study IDs and
collection analysis-code hash. Presence of unselected extensions has no effect,
even if an unselected path is unavailable. No scientific model/version is changed.

`minimum_tested_thresholds.csv` retains existing structure-specific grouping.
The additional `scope_minimum_tested_thresholds.csv` applies the same supported /
winning / weakly-feasible / strictly-feasible predicates across all structures
in the **selected** cardinality scope, preserving model/rule/k, target, gamma,
lambda, horizon and repetition distinctions. It is a minimum over tested points,
not a new hypothesis-test correction or an exhaustive-coalition claim. A winning
five-member coalition can lower an explicitly extended threshold; core exports
remain byte-for-byte unchanged. Equal-power comparisons span selected datasets;
cross-rule comparisons still compare the same population across its rules.

### Future local commands (prepared, not executed as production)

Planning alone does not mine:

```bash
python -m punishment_sim.persistent_v2_shards plan configs/persistent_v2_core_2to4_1pct_10rep.json CORE
python -m punishment_sim.persistent_v2_shards plan configs/persistent_v2_extension_5_1pct_10rep.json EXT5
python -m punishment_sim.persistent_v2_shards plan configs/persistent_v2_extension_6_1pct_10rep.json EXT6
```

Each dataset retains the existing per-shard `--rep-start 1 --rep-end 5` then
`--rep-start 6 --rep-end 10` execution contract. No worker launcher was added.
After all selected sources have five repetitions, a preliminary extended merge
and a deliberately core-only export can be requested without mining:

```bash
python -m punishment_sim.persistent_v2_collection merge preview.json --core CORE --extension-5 EXT5 --extension-6 EXT6 --analysis-scope extended_2to6 --preliminary
python -m punishment_sim.persistent_v2_collection export-collection core-preview --collection preview.json
python -m punishment_sim.persistent_v2_collection export-collection extended-preview --collection preview.json --analysis-scope extended_2to6
```

The default core export needs only core data; extensions need not be run first:

```bash
python -m punishment_sim.persistent_v2_collection export core-preview --core CORE --preliminary
```

Final examples (all selected sources must have all ten repetitions):

```bash
python -m punishment_sim.persistent_v2_collection merge final.json --core CORE --extension-5 EXT5 --extension-6 EXT6 --analysis-scope extended_2to6
python -m punishment_sim.persistent_v2_collection export-collection core-final --collection final.json
python -m punishment_sim.persistent_v2_collection export-collection extended-5-final --collection final.json --analysis-scope extended_2to5
python -m punishment_sim.persistent_v2_collection export-collection extended-6-final --collection final.json --analysis-scope extended_2to6 --include-repetitions
```

A preliminary collection permanently selects repetitions 1–5, including after
Phase II is present. It reports `PRELIMINARY_5_REPETITIONS`, n=5, df=4 and Student-t
critical value 2.776. Final rows report `FINAL_10_REPETITIONS`, n=10, df=9 and 2.262.
Means, sample SDs, SEs, paired CRN differences, 95% confidence intervals and existing
supported/refuted/inconclusive classifications are unchanged. Collections never
mix five-repetition and ten-repetition vectors.

## Validation

Tests cover config partitioning and unchanged science, native identity partitioning,
fixed phases, population-local baseline reuse, authenticated source rejection,
noncolliding combined merges, stable core outputs with present/unavailable extensions,
explicit extended thresholds, preliminary first-five reconstruction, and unchanged
historical petty-v4 configuration. The prior .51 benchmark remains frozen and its
runtime fingerprint still matches the unchanged simulation/validation/reduction code.

Verification: `.venv/bin/python -m pytest -q` completed with **1,055 passed, 9 expected failures** in 93.29 seconds. The nine expected failures are the retained historical-v1 cases. `git diff --check` passed; new-file whitespace checks also passed. The CLI help check passed.
No production sweep, new production benchmark, SSH, `/xtra` access, or remote job
was performed. Only temporary plan enumeration and small local test fixtures ran.
