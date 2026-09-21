"""Current measured evidence and exact inventory are tied to the tested sources."""
import hashlib
import json
from pathlib import Path
from punishment_sim.persistent_v2_compact import runtime_identity
from punishment_sim.persistent_checkpoint import digest

ROOT=Path(__file__).resolve().parents[1]


def test_frozen_validator_matches_prior_source_hash():
    old=json.loads((ROOT/'docs/persistent_v2_production_benchmark.json').read_text())
    source=(ROOT/'analysis/_persistent_v2_compact_validation_reference.py').read_text().replace('from punishment_sim.','from .')
    assert hashlib.sha256(source.encode()).hexdigest()==old['source_hashes_before_and_after']['punishment_sim/persistent_v2_checkpoint.py']


def test_exact_51_inventory_and_configuration_identity():
    scope=json.loads((ROOT/'docs/persistent_v2_51pct_scope.json').read_text())
    design=json.loads((ROOT/'configs/persistent_v2_1pct_10rep.json').read_text())
    assert scope['configuration_sha256']==digest(design)
    assert scope['coalition_totals']==[i/100 for i in range(5,52)]
    assert scope['feasible_total_cardinality_cells']==234
    assert scope['sampled_structures_per_environment']==1120
    assert scope['authorized_environments']==186
    assert sum(scope['sampled_structures_per_total'].values())==1120
    assert scope['populations']==1120*186==208320
    assert scope['top_level_rule_configurations']==1249920
    assert scope['after_reuse']==sum(count*10*(2+6*(int(m)+2)) for m,count in scope['by_cardinality'].items())==78882600
    assert [x['repetitions'] for x in scope['execution_phases'].values()]==[[1,5],[6,10]]
    assert all(x['unique_simulations']==39441300 and x['nominal_block_work']==1183239000000 for x in scope['execution_phases'].values())


def test_completed_identical_input_benchmark_and_phase_projections():
    evidence=json.loads((ROOT/'docs/persistent_v2_51pct_benchmark.json').read_text())
    assert evidence['status']=='COMPLETE' and evidence['runtime']==runtime_identity()
    assert evidence['repetitions']==10 and evidence['horizon']==30000
    assert len(evidence['verified_conditions'])==len(set(evidence['verified_conditions']))==700
    assert len(evidence['validation_components'])==14
    assert all(s['scientific_outputs_match_prior'] and s['resume'].get('mining_simulations_executed',0)==0 for s in evidence['studies'])
    for study in evidence['studies']:
        assert study['phases']['Phase I']['metrics']['requested_repetitions']==[1,5]
        assert study['phases']['Phase II']['metrics']['requested_repetitions']==[6,10]
        assert study['phases']['Phase I']['exports']['analysis_status']=='PRELIMINARY_5_REPETITIONS'
        assert study['phases']['Phase II']['exports']['analysis_status']=='FINAL'
    assert not any(evidence[k] for k in ('production_sweep','ssh','xtra_access','remote_job'))
    projection=json.loads((ROOT/'docs/persistent_v2_51pct_projection.json').read_text())
    for m in ('2','6'):
        assert projection['runtime']['Full'][m]['single_worker_seconds']==sum(projection['runtime'][phase][m]['projected_single_worker_seconds'] for phase in ('Phase I','Phase II'))
    assert not projection['capacity_verified'] and not projection['production_launched']
