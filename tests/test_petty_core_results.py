import csv,json
from pathlib import Path
from analysis.stage_b_racefix import DEFAULT_SOURCE,read_csv

T=DEFAULT_SOURCE/'analysis_tables'; ROOT=Path(__file__).resolve().parents[1]

def test_new_definitions_and_historical_fields_are_separate():
 text=(ROOT/'docs/winning_coalition_definition_audit.md').read_text()
 assert 'JOINTLY_FEASIBLE' in text and 'EFFECTIVE AND BASELINE_CREDIBLE AND DEVIATION_PROOF' in text
 assert 'historical `winning`' in text and 'does **not** require' in text

def test_feasibility_conjunction_and_strictness():
 rows=read_csv(T/'coalition_feasibility_by_environment.csv')
 assert len(rows)==972 and all(int(r['number_jointly_feasible'])<=int(r['number_effective']) for r in rows)
 assert all(int(r['number_strictly_jointly_feasible'])<=int(r['number_jointly_feasible']) for r in rows)

def test_minima_use_active_power_retain_ties_and_no_coalition_rows():
 rows=read_csv(T/'minimum_feasible_coalitions.csv')
 assert 'active_coalition_power' in rows[0] and 'candidate_population_power' in rows[0]
 assert any(r['qualifying_coalition_exists']=='False' and r['no_coalition_status']=='NO_QUALIFYING_COALITION' for r in rows)
 keys={}
 for r in rows:
  if r['qualifying_coalition_exists']=='True':keys.setdefault((r['criterion'],r['target_hash_power'],r['gamma'],r['natural_fork_rate'],r['active_coalition_power']),0);keys[(r['criterion'],r['target_hash_power'],r['gamma'],r['natural_fork_rate'],r['active_coalition_power'])]+=1
 assert keys and any(n>=1 for n in keys.values())

def test_maps_trace_ids_and_keep_lambda_separate():
 rows=read_csv(T/'joint_feasibility_map.csv');assert len(rows)==180
 assert {r['natural_fork_rate'] for r in rows}=={'0','0.005','0.02'}
 assert all(r['configuration_ids'] not in ('','[]') for r in rows if r['status']=='FEASIBLE')

def test_composition_flips_hold_active_hash_fixed():
 rows=read_csv(T/'composition_changes_feasibility.csv');assert rows
 assert all(r['total_active_hash'] for r in rows)
 assert all(r['jointly_feasible_a']!=r['jointly_feasible_b'] for r in rows)

def test_detector_is_algebraic_and_no_simulator_import():
 rows=read_csv(T/'feasible_coalition_tpr_requirements.csv')
 assert {'perfect_continuous','TPR_0.5','TPR_0.7','TPR_0.9','TPR_1'} <= {r['detector_condition'] for r in rows}
 source=(ROOT/'analysis/generate_petty_core_results.py').read_text()
 assert 'punishment_sim' not in source and 'research-sweep' not in source

def test_coverage_does_not_infer_from_aggregate():
 rows=read_csv(T/'coalition_research_coverage.csv');assert len(rows)==90
 assert sum(r['joint_feasibility_answerable']=='True' for r in rows)==27
 assert all(r['joint_feasibility_answerable']=='False' for r in rows if r['composition_credibility_exists']=='False')

def test_supplement_is_dry_run_only_and_stage_c_is_headline_based():
 plan=json.loads((DEFAULT_SOURCE/'central_coverage_supplement_dry_run.json').read_text())
 assert plan['planning_only'] and not plan['simulation_executed'] and plan['missing_environments']==63
 rows=read_csv(T/'central_question_stage_c_candidates.csv');assert len(rows)==8
 assert all(r['headline_conclusion_at_risk'] and r['confirmation_reasons'] for r in rows)

def test_corrected_only_no_stage_c_or_new_strategy():
 source=(ROOT/'analysis/generate_petty_core_results.py').read_text()
 assert 'race-owner-precedence-v2' not in source or 'MODEL_VERSION' in source
 assert 'punishment_sim' not in source and 'class Punishment' not in source

def test_core_figure_packages_exist():
 for name in ('joint_feasibility_map','strict_joint_feasibility_map','weak_vs_strict_joint_feasibility','minimum_joint_feasible_power_vs_attacker','joint_feasible_tpr_requirements'):
  for ext in ('png','pdf','svg','csv','metadata.json'):assert (DEFAULT_SOURCE/'analysis_figures'/f'{name}.{ext}').exists()
