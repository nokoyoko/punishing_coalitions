# Prepared v4 targeted rerun — DO NOT RUN LOCALLY

This retained runbook describes the **historical coarse, 30-repetition design**.
The current [refined 1%-resolution design](oceanic_v4_1pct_design.md) uses exactly
**20 repetitions for every configuration**, with no staged follow-up. Its counts
and reuse restrictions supersede this runbook for that experiment: the existing
importer rejects both the expanded grid and the 30-to-20 repetition mismatch.
These coarse commands are not a launch plan for the refined sweep.

Status: code preparation and local tests only. Production storage/checkpoints are
not available in this workspace. No corrected production findings exist yet.
The commands below are for a future manual session on the production machine;
they do not invoke SSH. Do not execute them in the local workspace.

## Exact scope, determined without production data

The retained coarse v4 config differs from the sampled v3 config only in `stage` and
`expected_model_version`. It retains 14 analytically profitable target/gamma pairs
crossed with three lambda values, 2–6 members, identical HHI samples, the same
power grids, 30 repetitions, 30,000 accepted-block targets, seed 51000, detector
TPR/FPR grids, bootstrap and CRN methodology. Authorization remains strictly
alpha > (1-gamma)/(3-2*gamma); lambda is not an admission criterion.

| Lambda | Top-level configurations | Mining simulations | Accepted-block work units |
|---|---:|---:|---:|
| 0 | 3,934 | 942,060 | 28,261,800,000 |
| 0.005 | 3,934 | 942,060 | 28,261,800,000 |
| 0.02 | 3,934 | 942,060 | 28,261,800,000 |
| Positive-lambda recomputation | 7,868 | 1,884,120 | 56,523,600,000 |
| Full experiment represented | 11,802 | 2,826,180 | 84,785,400,000 |

For each full k-member coalition C and repetition the required distinct mining
conditions are H (honest, unflagged, empty active set), S0 (selfish, unflagged,
empty active set), HF(C), SC(C), and one flagged selfish S(C minus j) per member.
Thus a top-level configuration represents (4+k)*30 simulations: 180, 210, 240,
270 or 300 for k=2,3,4,5,6. Counts per lambda and cardinality are respectively
798, 798, 784, 784, 770. Work units multiply simulation count by stopping target;
they are neither exact discoveries nor wall-clock estimates. Recomputing zero
lambda instead of reuse adds 942,060 simulations / 28,261,800,000 work units,
50% additional work relative to the targeted positive-lambda rerun.

`docs/oceanic_v4_rerun_scope.json` is generated solely from definitions by
`analysis.plan_oceanic_v4_rerun`; it includes a digest of task populations/design.

## Provenance and strict merge

A new v4-compatible analysis artifact is not evidence of execution under v4.
Zero-lambda reuse is valid only for explicit v3, with exact matching population,
seed, stopping target, repetitions, coalition sets and conditional/detector
settings. Positive lambda and older model versions must be rejected.

The dedicated importer creates derived destination artifacts with original v3
execution identity, immutable source path/digest, compatibility-rule identity,
and separately identified v4 artifact compatibility. It leaves the source intact.
Validation must verify the source evidence and matching destination contents,
not just trust an `equivalent` flag. A generic converter is prepared and tested
with tiny synthetic fixtures, not actual production checkpoints. If the remote
schema/specification differs from supported validated input, stop and inspect;
do not relax validation or rewrite version strings.

The execution-only lambda filter is applied after full task generation and before
shard selection. It does not alter spec hashes, task IDs or shard assignments.
Full merge still requires all 11,802 valid records, including validated zero-lambda
imports. Repeating the same filtered command resumes completed valid tasks.

Strict merge uses an analysis-only mode which revalidates every checkpoint and
refuses missing files instead of falling back to mining. Output rows carry
artifact and simulation model identity; per-configuration provenance also has a
dedicated CSV/audit, and equal-hash comparisons identify both inputs. Aggregate
rows can be joined to their contributing configuration IDs. Never describe the
942,060 reused simulations as newly executed. Legacy `actual_*` cache counters
represent checkpoint history; the new executed-in-this-analysis counter is zero
for a strict merge.

## Outputs to regenerate only after checkpoints are complete

The strict merge regenerates mining configurations, coalition_results.csv,
member_credibility.csv, detector_evaluations.csv, continuous_tpr_thresholds.csv,
false_positive_vectors.csv, equal_hash_comparisons.csv, minimum_thresholds.csv,
minimal_winning_coalitions.csv, repetition_metrics.csv, baseline/deviation/slack
surfaces, weakest_member_summaries.csv, terminal_boundary_diagnostics.csv,
Stage C candidate inputs, cache/provenance audits, output completeness audits,
and results.json. Aggregate-only surfaces can legitimately be empty for this
composition-only experiment.

The downstream validation module regenerates refined weak/strict credibility,
adjusted equal-hash comparisons and composition summaries, threshold audits,
statistical/metric/output checks and reasoned/ranked Stage C candidate inputs.
Its historical throughput estimates are not a measured prediction for this rerun.
No Stage C confirmation simulation is included.

The empty stage_c_candidates.csv issue was a downstream slice: a configured zero
cap produced [:0]. Zero now means uncapped, while positive caps/default 250 and
existing reason/priority rules are preserved. This is independent of mining.

## Future comparison

Use identical matched task/coalition/member identities and all 42 authorized
environments. Report supported effectiveness, the pipeline's winning definition,
weak joint feasibility and strict joint feasibility separately, with their
minimum observed tested powers and tied witnesses. The pipeline's `winning`
combines effectiveness and deviation credibility; do not silently substitute a
baseline-plus-deviation joint criterion. Keep existing epsilon-based refined
credibility definitions explicitly labeled.

Compare zero-lambda underlying metrics exactly (provenance metadata differs);
classification/minimum changes there are a failed reuse/regression audit. At each
positive lambda report changed environments, payoff and credibility margins,
and equal-power composition comparisons. Cross-version same seed is not enough
for paired inference because the fix changes tie-draw consumption. Use descriptive
v3/v4 deltas, and retain existing within-model CIs/FDR treatment. No new inference
or causal magnitude should be invented. The claim that no positive-lambda
coalition wins remains provisional until corrected production evidence exists.

## Manual production commands

The completed command sequence will use only the prepared CLI interfaces below.
It assumes the code/tests have separately been made available on the production
machine. It does not deploy code, contact a machine, or copy historical results.

**DO NOT RUN LOCALLY.** Run these blocks manually, in order, only on the production
machine when authorized to begin the future rerun. Use a terminal/session that
survives disconnects. Do not edit the v3 config or its result directory.

```bash
set -euo pipefail
cd /home/brigh169/punishing_coalitions
export RERUN_PY=.venv/bin/python
export RERUN_OLD_CONFIG=configs/research_sweep_stage_b_oceanic_v3_expanded_composition_sampled.json
export RERUN_NEW_CONFIG=configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_sampled.json
export RERUN_OLD=results/research_sweep_stage_b_oceanic_v3_expanded_composition_sampled
export RERUN_NEW=results/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_sampled
export RERUN_COMPARISON=results/oceanic_v3_vs_all_races_v4_sampled_comparison

# Read-only sanity: correct machine/storage, model, unchanged design/admission,
# complete historical manifest, and compatible existing destination if resuming.
"$RERUN_PY" - <<'PY'
import json, os
from pathlib import Path
from dataclasses import asdict
from analysis.plan_oceanic_v4_rerun import analytical_spec, plan
from punishment_sim.coalition import MODEL_VERSION
from punishment_sim.research_sweep import generate_tasks
from punishment_sim.sharded_sweep import specification_hash
from punishment_sim.checkpoint_compatibility import _source_manifest
assert Path.cwd() == Path('/home/brigh169/punishing_coalitions')
resolved = Path('results').resolve(strict=True)
assert resolved == Path('/xtra') or Path('/xtra') in resolved.parents
assert MODEL_VERSION == 'race-owner-oceanic-all-races-v4'
old = json.loads(Path(os.environ['RERUN_OLD_CONFIG']).read_text())
new = json.loads(Path(os.environ['RERUN_NEW_CONFIG']).read_text())
report = plan(old,new)
assert report['top_level_configurations'] == 11802
assert report['authorized_environment_count'] == 42
# The actual configured authorization file must equal the formula-derived scope.
serialize = lambda tasks: sorted(json.dumps(asdict(t),sort_keys=True) for t in tasks)
assert serialize(generate_tasks(new)[0]) == serialize(generate_tasks(analytical_spec(new))[0])
_source_manifest(Path(os.environ['RERUN_OLD']),old)
out = Path(os.environ['RERUN_NEW'])
assert out.resolve() != Path(os.environ['RERUN_OLD']).resolve()
if out.exists():
    audit=json.loads((out/'manifest_audit.json').read_text())
    assert audit['model_version']==MODEL_VERSION
    assert audit['configuration_hash']==specification_hash(new)
print(json.dumps(report,indent=2))
PY

export RERUN_SHARDS=$("$RERUN_PY" -c 'import json,os; from pathlib import Path; print(json.loads((Path(os.environ["RERUN_OLD"])/"manifest_audit.json").read_text())["num_shards"])')

# Full v4 manifest: 11,802 tasks. This command performs no mining.
"$RERUN_PY" -m punishment_sim research-shard-plan \
  --config "$RERUN_NEW_CONFIG" --output-dir "$RERUN_NEW" \
  --num-shards "$RERUN_SHARDS"

# Validated derived artifacts only; no mining, no edits to source checkpoints.
# Stop on any schema/config/checksum error; do not relax validation.
"$RERUN_PY" -m punishment_sim.checkpoint_compatibility \
  --source-config "$RERUN_OLD_CONFIG" --destination-config "$RERUN_NEW_CONFIG" \
  --source-dir "$RERUN_OLD" --destination-dir "$RERUN_NEW" \
  --num-shards "$RERUN_SHARDS"

"$RERUN_PY" - <<'PY'
import json,os
from pathlib import Path
out=Path(os.environ['RERUN_NEW'])
a=json.loads((out/'zero_lambda_import_audit.json').read_text())
assert a['status']=='COMPLETE' and a['zero_lambda_tasks']==3934
assert a['mining_simulations_represented_by_selected_source_tasks']==942060
assert a['mining_simulations_executed_by_import']==0
print(json.dumps(a,indent=2))
PY

# FUTURE PRODUCTION LAUNCH: selected 7,868 tasks only.
# One supervisor with eight workers, retaining deterministic shard assignments.
# Repeating this identical command resumes valid completed selected checkpoints.
"$RERUN_PY" -m punishment_sim research-shard-run \
  --config "$RERUN_NEW_CONFIG" --output-dir "$RERUN_NEW" \
  --num-shards "$RERUN_SHARDS" --workers 8 \
  --natural-fork-rates 0.005 0.02
```

In a second production terminal, monitor without changing data:

```bash
cd /home/brigh169/punishing_coalitions
cat results/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_sampled/run_status.json
tail -n 5 results/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_sampled/progress.log
```

After the selected run reports complete and no failures, use the original shell
variables and continue. These commands are still **DO NOT RUN LOCALLY**:

```bash
"$RERUN_PY" - <<'PY'
import json,os
from pathlib import Path
s=json.loads((Path(os.environ['RERUN_NEW'])/'run_status.json').read_text())
assert s['status']=='COMPLETE' and s['failed_tasks']==0 and s['remaining_tasks']==0
assert s['total_tasks']==7868 and s['manifest_total_tasks']==11802
assert s['execution_natural_fork_rates']==[0.005,0.02]
print(json.dumps(s,indent=2))
PY

# Strict full merge/regeneration: validates all 11,802 checkpoint envelopes.
# Missing/invalid checkpoints are errors; this merge cannot invoke mining.
"$RERUN_PY" -m punishment_sim research-shard-merge \
  --config "$RERUN_NEW_CONFIG" --output-dir "$RERUN_NEW" \
  --num-shards "$RERUN_SHARDS"

# Existing downstream statistical/credibility/Stage C selection analysis only.
"$RERUN_PY" -m punishment_sim.stage_b_validation --stage-b-dir "$RERUN_NEW"

# Read v3 and v4; write to a separate comparison directory. No old-output changes.
"$RERUN_PY" -m analysis.compare_oceanic_v4 \
  --old-dir "$RERUN_OLD" --new-dir "$RERUN_NEW" \
  --output-dir "$RERUN_COMPARISON" --config "$RERUN_NEW_CONFIG"

"$RERUN_PY" - <<'PY'
import csv,json,os
from pathlib import Path
out=Path(os.environ['RERUN_NEW'])
a=json.loads((out/'merge_audit.json').read_text())
assert a['analysis_ready'] and a['status']=='COMPLETE'
assert a['expected_task_count']==a['valid_checkpoint_count']==11802
assert a['expected_authorized_environment_count']==42 and a['problem_count']==0
assert a['mining_simulations_executed_by_merge']==0
assert a['checkpoints_by_execution_provenance']=={
    'executed_under_v4':7868,'reused_from_behaviorally_equivalent_v3_zero_lambda':3934}
assert a['represented_simulations_by_execution_provenance']=={
    'executed_under_v4':1884120,'reused_from_behaviorally_equivalent_v3_zero_lambda':942060}
c=json.loads((Path(os.environ['RERUN_COMPARISON'])/'comparison_audit.json').read_text())
assert c['status']=='PASS' and c['environment_count']==42
assert c['zero_lambda_scientific_rows_equal']
print(json.dumps(a,indent=2))
print(json.dumps(c,indent=2))
# Review deficiencies rather than treating empty classification outputs as success.
print((out/'output_completeness_audit.json').read_text())
print((out/'model_consistency_checks.csv').read_text())
PY
```

The comparison writes `environment_feasibility_comparison.csv` (42 rows),
`lambda_feasibility_summary.csv`, `payoff_margin_changes.csv`,
`equal_power_composition_changes.csv` when comparisons exist, and
`comparison_audit.json`. These files do not exist for production until that future
workflow runs. The strict/weak classifications use the current epsilon and
component intervals, not new confirmation simulations. Minimal powers are minima
among tested samples, not proven thresholds over all possible compositions.

If reuse fails because historical provenance/schema is unsupported, stop. A fully
native fallback adds the zero-lambda work quantified above and needs a deliberate
choice before launch; it is not an automatic fallback. Run the same runner with
`--natural-fork-rates 0` only if that fallback is later chosen, and adapt the final
provenance audit to 11,802 native records. Do not label native zero-lambda runs as
imports or manufacture import evidence. Imported artifact validation intentionally
requires the original source files to remain available at their recorded paths.

Do not run simultaneous supervisors writing the same tasks. A single supervisor
already uses the configured worker parallelism. For independently scheduled
shards, use disjoint `--shard-index` values and retain the same full config and
`--num-shards`; monitor the corresponding per-shard status files instead. Account
for full-merge memory/storage separately from mining; this preparation did not
benchmark the 11,802-task merge on production hardware.

## Local preparation validation

The full local suite passed: **308 tests in 39.69 seconds**. New checks cover the
exact structural counts/design, execution-filter identity preservation, synthetic
source checksum preservation, import idempotence, source/config/positive-lambda
rejection, provenance propagation through a tiny synthetic mixed merge, absence
of mining fallback, uncapped Stage C selection, evidence-based audit statuses,
and a synthetic 42-environment comparison with a zero-lambda mismatch detector.
The earlier fixed-seed 36-case v3/v4 zero-lambda regression remains in that suite.
No production files were available or used for importer/comparison validation.
