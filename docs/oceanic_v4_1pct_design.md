# Refined v4 design: one-percentage-point powers

Prepared locally, without running production simulations or changing production results.
Model semantics/version remain `race-owner-oceanic-all-races-v4`.
The old coarse v3 and v4 configurations and their planning artifacts are retained.

New configuration:
`configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_1pct.json`.
Proposed future output directory (not created):
`results/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_1pct`.
The complete calculated inventory, including every environment and composition
cell, is `docs/oceanic_v4_1pct_scope.json`.

## Grid and authorization

The target powers are exactly:

```
0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18,
0.19, 0.20, 0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.27,
0.28, 0.29, 0.30, 0.31, 0.32, 0.33, 0.34, 0.35
```

The candidate-coalition totals are exactly:

```
0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13,
0.14, 0.15, 0.16, 0.17, 0.18, 0.19, 0.20, 0.21, 0.22,
0.23, 0.24, 0.25, 0.26, 0.27, 0.28, 0.29, 0.30, 0.31,
0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38, 0.39, 0.40,
0.41, 0.42, 0.43, 0.44, 0.45, 0.46, 0.47, 0.48, 0.49,
0.50, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58,
0.59, 0.60
```

They were constructed from integer hundredths via Decimal, not repeated float
addition. Gamma/lambda JSON numeric representations are retained from the coarse
config; raw task IDs are not silently recanonicalized. Individual member powers
remain on the 0.01 grid, with a 0.01 minimum and cardinalities 2–6.

The config declares `authorization_rule=analytic_vanilla_eyal_sirer`; admission is
computed directly from its target/gamma values. A simultaneous stored admission
file/list is rejected, preventing accidental restriction to the old 14 pairs.
Lambda is crossed after the strict rule alpha > (1-gamma)/(3-2*gamma).

| Gamma | Threshold | Authorized target powers, step 0.01 | Pair count |
|---|---|---|---:|
| 0 | 1/3 | 0.34–0.35 | 2 |
| 0.25 | 0.30 | 0.31–0.35 | 5 |
| 0.5 | 0.25 | 0.26–0.35 | 10 |
| 0.75 | 1/6 | 0.17–0.35 | 19 |
| 1 | 0 | 0.10–0.35 | 26 |

There are 26 target values, 130 target/gamma pairs evaluated, **62 authorized
pairs** and **186 environments** after crossing lambda 0, 0.005 and 0.02.
Break-even points 0.30/gamma=0.25 and 0.25/gamma=0.5 remain excluded.

Every authorized environment admits all **56 candidate totals** under the
unchanged residual floor 0.05. Even the largest alpha/total pair is .35+.60=.95.
Within those totals, the .05-total/6-member cell has no valid composition because
six miners require at least .06. No other total/cardinality cell is infeasible.

Every top-level configuration uses **exactly 20 independent repetitions**.
There is no staged follow-up or adaptive allocation of repetitions. The
accepted-block target remains 30,000, seed 51000, bootstrap samples 2,000,
workers 8, detector TPRs [0.5,0.7,0.9,1], FPRs [0,0.001,0.01,0.05,0.10],
and robustness bins [0.0001,0.0005].

Means, sample standard deviations, standard errors, paired CRN differences,
two-sided 95% confidence intervals, and supported/refuted/inconclusive rules
remain in place. The paired Student-t method now uses df=19 for 20 repetitions:
mean +/- 2.093 * sample_sd / sqrt(20). The missing df=19 entry was added to the
existing critical-value table so this design does not fall back to 1.96.
Historical 30-repetition intervals retain df=29 and critical value 2.045.
The paired tuple bootstrap and p-value/FDR methods are unchanged; p-values
already use the observed repetition count minus one for degrees of freedom.

## Composition coverage and exact work

The sampling rule is unchanged: sort all canonical compositions by
`(sum(member_power**2), member_vector)` and select up to five rank quantiles,
including the endpoints. These are quantiles in the ordering by HHI, not equally
spaced numerical HHI values. When at most five compositions exist, retain all.

Across 280 (total, cardinality) cells, 279 are feasible. Every feasible cell
includes a least-concentrated, approximately equal vector, a maximally concentrated
vector, and a vector containing a 1% miner. These categories can refer to the same
vector. Every cell with more than two available distinct HHI levels includes an
interior level; small cells cannot manufacture nonexistent interior alternatives.

| Representatives retained | Cells |
|---|---:|
| 0 | 1 |
| 1 | 5 |
| 2 | 5 |
| 3 | 6 |
| 4 | 3 |
| 5 | 260 |

This gives **1,345 distinct sampled structures per authorized environment**:
271 with two members, 274 with three, 271 with four, 267 with five and 262 with six.
The selection is cached once per total/cardinality cell during task generation;
this removes repeated sorting across environments without changing representatives
or their order. The full production task list was materialized and checked locally
as a planning computation only: all 250,170 IDs are distinct.

Each full k-member top-level configuration represents H, S0, HF(C), SC(C), and k
selfish flagged leave-one-out conditions per repetition: (4+k)*20 mining runs.
For cardinalities 2–6 these are 120, 140, 160, 180 and 200 runs respectively.

| Scope | Configurations | Mining simulations | Accepted-block work units |
|---|---:|---:|---:|
| Lambda 0 | 83,390 | 13,311,400 | 399,342,000,000 |
| Lambda 0.005 | 83,390 | 13,311,400 | 399,342,000,000 |
| Lambda 0.02 | 83,390 | 13,311,400 | 399,342,000,000 |
| Full refined design | **250,170** | **39,934,200** | **1,198,026,000,000** |
| Historical reuse supported by current importer | **0** | **0** | **0** |
| Fresh v4 with current importer | **250,170** | **39,934,200** | **1,198,026,000,000** |

Work units are simulation count times the accepted-block stopping target, not an
elapsed-time estimate or the exact number of discoveries/accepted blocks after
race finalization. The scope script counts conditions combinatorially rather than
materializing roughly 40 million cache keys. Do not use the old generic dry-run's
large key set merely to obtain these counts.

## Historical-grid audit and downstream implications

The current coarse arrays originate in:

- `configs/research_sweep_stage_b_oceanic_v3_expanded_composition_sampled.json:17–18`
  and the corresponding retained coarse v4 config's `composition.target_hash`
  and `composition.candidate_power`.
- `configs/research_sweep_stage_b_oceanic_v3_expanded_aggregate.json:15–18`
  supplied the old authorization exporter with the coarse target grid. Its
  coalition list also includes 0.025-spaced low-power points; it is a separate
  historical aggregate experiment, not the sampled-composition total grid.
- Historical core report builders also encode coarse target/power lists:
  `analysis/generate_petty_core_results.py:9,143` and
  `analysis/generate_profitable_domain.py:44,51`.
- Historical v2 plotting uses six target rows and 6×5 heatmaps:
  `analysis/generate_petty_core_figures.py:17–23` and
  `analysis/generate_profitable_core_figures.py:14–19`.

Those historical scripts/configurations remain unchanged. They must not be pointed
at the refined output. Generic threshold, boundary, equal-power grouping and
Stage C selection functions use actual observed values rather than 0.05 spacing.
The 0.05 residual floor, FPR and significance constants are not grid increments.

The authorization exporter previously read only `aggregate`; it now handles
aggregate and composition grids, including this composition-only design. The
legacy definition-only helper can still materialize analytical admission while
avoiding a conflicting dynamic-rule field. Generic analysis need not alter its
threshold arithmetic or Stage C priorities.

`minimum_thresholds.csv` remains a compatibility filename. Its values must be
reported as **minimum observed/tested powers**, with no interpolation or claim
about a continuous optimum. Its groups include `structure`; systematic structure
names encode the complete member vector, so per-structure minima usually have
only one total-power observation. They are not the environment-wide minimum over
all sampled compositions. Future headline analysis must aggregate qualifying
coalitions across structures within each environment and retain tied witnesses.
For example: “minimum observed winning coalition power: 0.24 on the tested 0.01
grid” when .23 fails and .24 succeeds. This still does not establish a continuous
threshold or exclude an untested composition winning at a smaller total.

The old `analysis/compare_oceanic_v4.py` is intentionally a same-design comparator.
It cannot consume coarse v3 and refined v4 full datasets directly. Future analysis
must validate each full design independently, report v3/v4 correction effects only
on exact common configurations, and report refined-grid discoveries separately.
Otherwise changes in tested minima conflate the semantic correction with grid
expansion. Preserve the existing comparator's rejection of mismatched scopes.

## Reuse and future execution boundaries

All 11,802 old coarse task populations/IDs are present unchanged in the refined
plan. Their **3,934 zero-lambda** populations are the only potential v3 reuse
overlap; the remaining 7,868 old positive-lambda configurations are stale. The
refinement adds 238,368 configurations: 79,456 at zero lambda and 158,912 at
positive lambda. Population IDs omit repetition count, but specification hashes,
checkpoint envelopes, row metadata and repetition coverage include it.

**The current importer cannot reuse a 30-repetition checkpoint for this
20-repetition design.** `check_spec_compatibility` requires identical scientific
settings, including repetitions, and the importer also requires identical full
task manifests. Grid expansion already violates that contract; 30 versus 20 is
an independent rejection even for otherwise identical designs. The checkpoint
validator requires exactly the requested repetitions and cache accounting.
Compatibility envelopes additionally require the complete source result and
cache audit to remain unchanged. No prefix importer was implemented, validation
was not weakened, and no historical observations were silently truncated.

The first 20 repetitions are seed-compatible in principle. `study` constructs
each repetition independently with `population.seed + repetition`, and named
discovery/tie/natural streams depend on that seed, not the total repetition
count. Indices 0–19 therefore use seeds 51000–51019 in both designs, with the same
within-repetition CRN pairing. Tests check this prefix across every overlapping
zero-lambda population and all its conditional mining keys. The existing v3/v4
zero-lambda equivalence evidence still applies to those mining conditions.
This establishes a deterministic prefix opportunity, not provenance-valid reuse.

A future dedicated overlap/prefix importer would need to validate the full
30-repetition source and both manifests, select indices 0–19 without consulting
outcomes, and recompute every summary, SD, SE, paired interval, detector metric,
bootstrap result and classification from those 20 tuples and leave-outs. It must
preserve the immutable source checksum, v3 execution identity, source count/hash,
selected indices/seeds and derived destination count/hash. Relabeling the old
30-repetition summaries would be invalid. No production checkpoint was inspected.

| Conditional reuse scope (not currently available) | Configurations | Mining simulations | Accepted-block work units |
|---|---:|---:|---:|
| Full historical overlap at 30 repetitions | 3,934 | 942,060 | 28,261,800,000 |
| Potential first-20 prefix saving | 3,934 | 628,040 | 18,841,200,000 |
| New zero-lambda work after validated prefix reuse | 79,456 | 12,683,360 | 380,500,800,000 |
| Positive-lambda work in either case | 166,780 | 26,622,800 | 798,684,000,000 |
| Fresh v4 only if a prefix importer is implemented and validated | 246,236 | 39,306,160 | 1,179,184,800,000 |

The executable code currently provides **no historical reuse for this refined
design**, so plan for all 83,390 zero-lambda configurations plus all 166,780
positive-lambda configurations: the full fresh-work total above. The scope JSON
keeps `current_importer_reuse` and `fresh_v4` separate from `theoretical_reuse`
and `fresh_v4_if_validated_prefix_reuse`. A possible future prefix saving must
not be deducted from the current plan. The coarse positive-lambda-only runbook
does not cover this design; no refined import/launch sequence is supplied.
Strict merge continues to reject missing or unprovenanced historical records.

Existing coarse configurations, scope JSON and runbook remain historical planning
artifacts. No production result directory was created. Full-merge memory/storage
and execution capacity need review for this much larger design before any launch;
no production runtime or storage benchmark was performed here.

## Local validation

The full local suite, `.venv/bin/python -m pytest -q`, passed: **323 tests in
43.84 seconds**. Coverage includes exact 20-repetition configuration and scope,
all per-lambda and conditional reuse counts, the regenerated scope artifact,
coarse overlap/ID/shard and seed-prefix identity, complete 20-repetition
statistical outputs with df=19, and rejection of a valid synthetic
30-repetition checkpoint for a 20-repetition destination. Existing grid,
authorization, HHI coverage, threshold, checkpoint and v4 semantic tests passed.
The suite used local simulation fixtures; simulation run/step methods were
prohibited in the planning-only design tests. A byte comparison confirmed that
the only configuration edit is `repetitions: 30` to `repetitions: 20`.
`git diff --check` passed.

No production simulations, SSH commands, remote jobs, `/xtra` access, production
imports, production merges or production result changes were performed in this
task. The refined sweep was not launched.
