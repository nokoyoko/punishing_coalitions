import csv,json
from pathlib import Path
from punishment_sim.coalition import MODEL_VERSION
from analysis.stage_b_racefix import read_csv

A=Path('results/research_sweep_stage_b_oceanic_v3');R=Path('results/research_sweep_stage_b_oceanic_v3_profitable_core');T=R/'analysis_tables'

def test_v3_version_and_cache_separation():
 assert MODEL_VERSION=='race-owner-oceanic-residual-v3'
 assert {r['model_version'] for r in read_csv(A/'mining_configurations.csv')}=={MODEL_VERSION}
 assert {r['model_version'] for r in read_csv(R/'mining_configurations.csv')}=={MODEL_VERSION}
 audit=json.loads((R/'checkpoint_reuse_audit.json').read_text());assert not audit['pre_v3_reuse'] and audit['v3_aggregate_checkpoints_reused']==198

def test_benchmark_matches_and_critical_point_profitable():
 rows=read_csv(Path('results/residual_oceanic_validation/eyal_sirer_threshold_validation.csv'))
 assert len(rows)==15 and all(r['match']=='True' for r in rows)
 x=next(r for r in rows if float(r['alpha'])==.3 and float(r['gamma'])==.5)
 assert x['simulated_classification']=='PROFITABLE' and float(x['ci95_low'])>0

def test_v3_profitability_domain_counts():
 rows=read_csv(A/'analysis_tables/selfish_profitability_domain.csv')
 assert sum(r['statistically_supported_profitability_status']=='SELFISH_PROFITABLE' for r in rows)==33
 assert sum(r['statistically_supported_profitability_status']=='SELFISH_NOT_PROFITABLE' for r in rows)==42
 assert sum(r['statistically_supported_profitability_status']=='SELFISH_PROFITABILITY_INCONCLUSIVE' for r in rows)==15

def test_v3_core_feasibility_and_tied_active_hash_minima():
 rows=read_csv(T/'minimum_profitable_environment_coalitions.csv');yes=[r for r in rows if r['qualifying_coalition_exists']=='True'];no=[r for r in rows if r['qualifying_coalition_exists']=='False']
 assert len(yes)==6 and len(no)==32
 assert {(float(r['target_hash_power']),float(r['gamma']),float(r['natural_fork_rate'])) for r in yes}=={(.2,1,0)}
 assert all(float(r['minimum_active_coalition_power'])==.3 for r in yes)
 assert len({r['structure'] for r in yes})==6 and all(r['strictly_jointly_feasible']=='False' for r in yes)

def test_v3_tpr_composition_lambda_and_stage_c():
 tpr=read_csv(T/'profitable_environment_tpr_requirements.csv');assert len(tpr)==6 and all(.8<float(r['continuous_tpr_min'])<.9 for r in tpr)
 assert read_csv(T/'profitable_composition_changes_feasibility.csv')==[]
 assert len(read_csv(T/'profitable_lambda_robustness.csv'))==8
 c=read_csv(T/'profitable_core_stage_c_candidates.csv');assert len(c)==38 and all(r['headline_conclusion_at_risk'] for r in c)

def test_no_residual_internal_fork_or_stage_c_execution():
 source=(Path('punishment_sim/coalition.py')).read_text();assert 'residual_residual' not in source
 assert not (R/'stage_c_results').exists()
