import json
from pathlib import Path
from analysis.stage_b_racefix import DEFAULT_SOURCE,read_csv

T=DEFAULT_SOURCE/'analysis_tables';ROOT=Path(__file__).resolve().parents[1]

def test_profitability_uses_paired_unpunished_difference():
 source=(ROOT/'analysis/generate_profitable_domain.py').read_text()
 assert "punishment_reduction'])-float(r['deterrence'])" in source
 assert 'statistics.stdev(v)/math.sqrt(len(v))' in source

def test_domain_categories_and_primary_filter():
 rows=read_csv(T/'selfish_profitability_domain.csv');assert len(rows)==90
 counts={s:sum(r['statistically_supported_profitability_status']==s for r in rows) for s in ('SELFISH_PROFITABLE','SELFISH_NOT_PROFITABLE','SELFISH_PROFITABILITY_INCONCLUSIVE')}
 assert counts=={'SELFISH_PROFITABLE':15,'SELFISH_NOT_PROFITABLE':63,'SELFISH_PROFITABILITY_INCONCLUSIVE':12}
 coverage=read_csv(T/'profitable_environment_coverage.csv');assert len(coverage)==15
 assert all(r['statistically_supported_profitability_status']=='SELFISH_PROFITABLE' for r in coverage)

def test_supplement_contains_only_missing_profitable_cells():
 config=json.loads((ROOT/'configs/research_sweep_stage_b_profitable_core_supplement.json').read_text())
 allowed={tuple(x) for x in config['authorized_environment_triplets']};assert len(allowed)==15
 assert {x[0] for x in allowed}=={.35} and {x[1] for x in allowed}=={0,.25,.5,.75,1} and {x[2] for x in allowed}=={0,.005,.02}
 assert config['repetitions']==30 and config['accepted_blocks']==30000

def test_native_dry_run_and_corrected_reuse_audit():
 dry=json.loads((DEFAULT_SOURCE/'profitable_core_supplement_dry_run.json').read_text())
 reuse=json.loads((ROOT/'results/research_sweep_stage_b_profitable_core_supplement/checkpoint_reuse_audit.json').read_text())
 assert dry['native_dry_run'] and dry['unique_population_configurations']==540
 assert reuse['model_version']=='race-owner-precedence-v2' and not reuse['pre_fix_reuse'] and reuse['reused_corrected_checkpoints_total']==90

def test_no_stage_c_or_new_strategy_in_domain_pipeline():
 text='\n'.join((ROOT/'analysis'/p).read_text() for p in ('generate_profitable_domain.py','prepare_profitable_supplement_checkpoints.py'))
 assert 'class Punishment' not in text and 'stage_c_audit' not in text

def test_merged_provenance_and_profitable_only_conclusions():
 rows=read_csv(T/'core_profitable_composition_results.csv')
 assert rows and {r['source_provenance'] for r in rows}=={'original_corrected_stage_b','profitable_core_supplement'}
 core=read_csv(T/'core_environment_classification.csv')
 assert sum(r['core_classification']=='SELFISH_PROFITABLE_NO_FEASIBLE_COALITION' for r in core)==15
 assert sum(r['core_classification']=='SELFISH_PROFITABLE_FEASIBLE' for r in core)==0

def test_no_unprofitable_zero_minimum_or_numeric_tpr():
 mins=read_csv(T/'minimum_profitable_environment_coalitions.csv')
 assert len(mins)==15 and all(r['status']=='NO_FEASIBLE_COALITION_WITHIN_TESTED_GRID' for r in mins)
 assert read_csv(T/'profitable_environment_tpr_requirements.csv')==[]

def test_profitable_composition_and_lambda_are_conditioned():
 assert read_csv(T/'profitable_composition_changes_feasibility.csv')==[]
 robust=read_csv(T/'profitable_lambda_robustness.csv')
 assert all(float(r['target_hash_power'])==.35 for r in robust)

def test_focused_stage_c_maps_to_headline_and_never_runs():
 rows=read_csv(T/'profitable_core_stage_c_candidates.csv');assert len(rows)==15
 assert all(r['headline_conclusion_at_risk'] for r in rows)
 assert all(r['qualifying_coalition_exists']=='False' for r in rows)
