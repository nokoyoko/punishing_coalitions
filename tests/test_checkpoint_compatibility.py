"""Synthetic batch fixtures only; no historical production data or remote access."""
import copy
import hashlib
import json

import pytest

from punishment_sim.coalition import MODEL_VERSION
from punishment_sim.checkpoint_compatibility import (
    SOURCE_MODEL_VERSION, import_zero_lambda, versioned_specification_hash,
    checkpoint_provenance, check_spec_compatibility)
from punishment_sim.research_sweep import generate_tasks, run_sweep
from punishment_sim.sharded_sweep import (
    CHECKPOINT_SCHEMA, _atomic_json, _run_population, _task_record,
    _validate_checkpoint_payload, specification_hash, validate_checkpoint, merge_shards)


def tiny_spec():
    return {'stage':'synthetic-test','expected_model_version':SOURCE_MODEL_VERSION,
        'seed':12,'repetitions':2,'accepted_blocks':20,'bootstrap_samples':10,
        'tpr':[1],'fpr':[0],'stage_c_max_candidates':0,'robustness_bins':[.0001,.0005],
        'aggregate':{},'composition':{'target_hash':[.2],'candidate_power':[.06],
            'gamma':[1],'natural_fork_rate':[0,.005],
            'systematic':{'member_counts':[2],'power_step':.01,'minimum_member_power':.01,
                'sampling':{'mode':'hhi_quantiles','max_per_cell':1}}}}


@pytest.fixture
def batches(tmp_path):
    old=tiny_spec();new={**old,'stage':'synthetic-v4','expected_model_version':MODEL_VERSION}
    source=tmp_path/'source';dest=tmp_path/'dest';source.mkdir()
    tasks,requested,valid=generate_tasks(old);records=sorted([_task_record(t,2) for t in tasks],key=lambda r:r['task_id'])
    shash=versioned_specification_hash(old,SOURCE_MODEL_VERSION)
    _atomic_json(source/'manifest_audit.json',{'schema':'sharded-sweep-manifest-v1',
        'model_version':SOURCE_MODEL_VERSION,'configuration_hash':shash,'num_shards':2,
        'requested_population_configurations':requested,'valid_population_requests':valid,
        'unique_population_configurations':len(records),
        'tasks_by_shard':{str(i):sum(r['shard_index']==i for r in records) for i in range(2)}})
    (source/'task_manifest.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    for record in records:
        # Construct synthetic data in the historical envelope to test validation.
        # This does not assert that these test fixtures were executed under v3.
        audit,result=_run_population(record,2,[1],[0],None)
        _atomic_json(source/'checkpoints'/f"{record['task_id']}.json",{
            'checkpoint_schema':CHECKPOINT_SCHEMA,'model_version':SOURCE_MODEL_VERSION,
            'configuration_hash':shash,'configuration_id':record['task_id'],
            'num_shards':2,'shard_index':record['shard_index'],'population':record['population'],
            'coalitions':record['coalitions'],'repetitions':2,'cache_audit':audit,'result':result})
    return old,new,source,dest,tasks


def test_import_resume_preserves_source_and_strict_mixed_merge(batches,monkeypatch):
    old,new,source,dest,tasks=batches
    checksums={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    audit=import_zero_lambda(old,new,source,dest,3)
    assert audit['created_compatibility_checkpoints']==1
    assert audit['mining_simulations_executed_by_import']==0
    assert audit['mining_simulations_represented_by_selected_source_tasks']==12
    assert len(list((dest/'checkpoints').glob('*.json')))==1
    zero=next(t for t in tasks if t.population.natural_fork_rate==0);record=_task_record(zero,3)
    path=dest/'checkpoints'/f"{record['task_id']}.json"
    assert validate_checkpoint(path,record,specification_hash(new),2)==(True,'valid')
    saved=json.loads(path.read_text());p=checkpoint_provenance(saved)
    assert p['artifact_model_version']==MODEL_VERSION and p['simulation_model_version']==SOURCE_MODEL_VERSION
    assert p['execution_provenance']=='reused_from_behaviorally_equivalent_v3_zero_lambda'
    assert import_zero_lambda(old,new,source,dest,3)['already_valid_destination_checkpoints']==1
    assert checksums=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    positive=next(t for t in tasks if t.population.natural_fork_rate>0);r=_task_record(positive,3)
    a,result=_run_population(r,2,[1],[0],None)
    _atomic_json(dest/'checkpoints'/f"{r['task_id']}.json",{
        'checkpoint_schema':CHECKPOINT_SCHEMA,'model_version':MODEL_VERSION,'simulation_model_version':MODEL_VERSION,
        'configuration_hash':specification_hash(new),'configuration_id':r['task_id'],
        'num_shards':3,'shard_index':r['shard_index'],'population':r['population'],
        'coalitions':r['coalitions'],'repetitions':2,'cache_audit':a,'result':result})
    def no_mining(*a,**kw):raise AssertionError('merge/import must not mine')
    monkeypatch.setattr('punishment_sim.research_sweep.study',no_mining)
    merged=merge_shards(new,dest,3)
    assert merged['mining_simulations_executed_by_merge']==0
    assert merged['checkpoints_by_execution_provenance']=={
        'executed_under_v4':1,'reused_from_behaviorally_equivalent_v3_zero_lambda':1}
    output=json.loads((dest/'results.json').read_text())
    assert output['cache_audit']['mining_simulations_executed_in_this_analysis_invocation']==0
    assert {r['simulation_model_version'] for r in output['coalitions']}=={SOURCE_MODEL_VERSION,MODEL_VERSION}


@pytest.mark.parametrize('tamper', ['population','duplicate_rep','payoff','result','checksum','positive','source_changed'])
def test_imported_tampering_rejected(batches,tamper):
    old,new,source,dest,tasks=batches;import_zero_lambda(old,new,source,dest,3)
    task=next(t for t in tasks if t.population.natural_fork_rate==0);r=_task_record(task,3)
    path=dest/'checkpoints'/f"{r['task_id']}.json";saved=json.loads(path.read_text())
    if tamper=='population':saved['population']['seed']+=1
    elif tamper=='duplicate_rep':saved['result']['repetitions'][1]=saved['result']['repetitions'][0]
    elif tamper=='payoff':saved['result']['repetitions'][0]['U_H']['target']['payoff']=.9
    elif tamper=='result':saved['result']['summary'][0]['winning']=not saved['result']['summary'][0]['winning']
    elif tamper=='checksum':saved['compatibility_provenance']['source_checkpoint_sha256']='0'*64
    elif tamper=='source_changed':
        src=source/'checkpoints'/path.name;src.write_text(src.read_text()+' ')
    elif tamper=='positive':
        # A valid positive-lambda payload cannot use the zero-lambda compatibility rule.
        positive=next(t for t in tasks if t.population.natural_fork_rate>0);r=_task_record(positive,3)
        positive_saved=json.loads((source/'checkpoints'/f"{r['task_id']}.json").read_text())
        saved={**positive_saved,'model_version':MODEL_VERSION,'simulation_model_version':SOURCE_MODEL_VERSION,
            'num_shards':3,'shard_index':r['shard_index'],'configuration_hash':specification_hash(new),
            'compatibility_provenance':saved['compatibility_provenance']}
    path.write_text(json.dumps(saved))
    assert validate_checkpoint(path,r,specification_hash(new),2)[0] is False


def test_import_rejects_unversioned_source_and_changed_science(batches):
    old,new,source,dest,tasks=batches
    changed=copy.deepcopy(new);changed['tpr']=[.9]
    with pytest.raises(ValueError,match='scientific'):check_spec_compatibility(old,changed)
    zero=next(t for t in tasks if t.population.natural_fork_rate==0);r=_task_record(zero,2)
    path=source/'checkpoints'/f"{r['task_id']}.json";saved=json.loads(path.read_text());saved.pop('model_version');path.write_text(json.dumps(saved))
    with pytest.raises(ValueError,match='model_version'):import_zero_lambda(old,new,source,dest,3)
    assert not dest.exists()


def test_import_refuses_source_destination_overlap(batches):
    old,new,source,dest,tasks=batches
    with pytest.raises(ValueError,match='nonnested'):import_zero_lambda(old,new,source,source/'new',3)


def test_valid_thirty_repetition_checkpoint_cannot_supply_twenty(tmp_path,monkeypatch):
    old={**tiny_spec(),'repetitions':30}
    new={**old,'repetitions':20,'expected_model_version':MODEL_VERSION}
    task=next(t for t in generate_tasks(old)[0] if t.population.natural_fork_rate==0)
    record=_task_record(task,2);source_hash=versioned_specification_hash(old,SOURCE_MODEL_VERSION)
    # Local unit-test fixture: only 20 accepted blocks, never a production run.
    audit,result=_run_population(record,30,old['tpr'],old['fpr'],None)
    saved={'checkpoint_schema':CHECKPOINT_SCHEMA,'model_version':SOURCE_MODEL_VERSION,
        'configuration_hash':source_hash,'configuration_id':record['task_id'],
        'num_shards':2,'shard_index':record['shard_index'],'population':record['population'],
        'coalitions':record['coalitions'],'repetitions':30,'cache_audit':audit,'result':result}
    original=copy.deepcopy(saved)
    assert _validate_checkpoint_payload(saved,record,source_hash,30,SOURCE_MODEL_VERSION)==(True,'valid')
    assert _validate_checkpoint_payload(saved,record,source_hash,20,SOURCE_MODEL_VERSION)==(False,'repetitions')
    # Rewriting only the envelope cannot make 30 observations into 20.
    assert _validate_checkpoint_payload({**saved,'repetitions':20},record,source_hash,20,
        SOURCE_MODEL_VERSION)==(False,'repetition_coverage')
    def no_source_access(*a,**k):pytest.fail('repetition mismatch must be rejected before source access')
    monkeypatch.setattr('punishment_sim.checkpoint_compatibility._source_manifest',no_source_access)
    with pytest.raises(ValueError,match='scientific configurations differ'):
        import_zero_lambda(old,new,tmp_path/'source',tmp_path/'destination',2)
    assert saved==original and not (tmp_path/'destination').exists()


def test_analysis_only_mode_never_falls_back_to_mining(tmp_path,monkeypatch):
    spec={**tiny_spec(),'expected_model_version':MODEL_VERSION}
    monkeypatch.setattr('punishment_sim.research_sweep.study',lambda *a,**k:pytest.fail('mining called'))
    with pytest.raises(RuntimeError,match='mining is disabled'):run_sweep(spec,tmp_path,require_checkpoints=True)
