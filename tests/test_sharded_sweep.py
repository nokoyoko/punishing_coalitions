import concurrent.futures,json,multiprocessing
from dataclasses import asdict

import pytest

from punishment_sim.research_sweep import generate_tasks
from punishment_sim.sharded_sweep import (_run_population,_task_record,shard_for,
    specification_hash,validate_checkpoint,CHECKPOINT_SCHEMA)
from punishment_sim.coalition import MODEL_VERSION


def spec():
    return {'stage':'shard-test','seed':12,'repetitions':2,'accepted_blocks':30,
        'tpr':[1],'fpr':[0],'minimum_residual_power':.05,
        'authorized_environment_triplets':[[.3,1,0]],'aggregate':{},
        'composition':{'target_hash':[.3],'candidate_power':[.06],'gamma':[1],
          'natural_fork_rate':[0],'systematic':{'member_counts':[2,4,6],
          'power_step':.01,'minimum_member_power':.01,
          'sampling':{'mode':'hhi_quantiles','max_per_cell':1}}}}


def test_shard_assignment_is_stable_and_disjoint():
    tasks,_,_=generate_tasks(spec());ids=[_task_record(t,7)['task_id'] for t in tasks]
    assignment={i:{x for x in ids if shard_for(x,7)==i} for i in range(7)}
    assert set().union(*assignment.values())==set(ids)
    assert sum(map(len,assignment.values()))==len(ids)


def test_serial_and_spawn_worker_results_are_exactly_equal():
    task=generate_tasks(spec())[0][0];record=_task_record(task,3)
    serial=_run_population(record,2,[1],[0],None)
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
            parallel=pool.submit(_run_population,record,2,[1],[0],None).result()
    except PermissionError:
        pytest.skip('platform sandbox forbids multiprocessing semaphores')
    assert parallel==serial


def test_checkpoint_validation_rejects_truncation_and_wrong_config(tmp_path):
    task=generate_tasks(spec())[0][0];record=_task_record(task,3);path=tmp_path/'checkpoint.json'
    path.write_text('{truncated')
    assert validate_checkpoint(path,record,specification_hash(spec()),2)[0] is False
    audit,result=_run_population(record,2,[1],[0],None)
    path.write_text(json.dumps({'checkpoint_schema':CHECKPOINT_SCHEMA,'model_version':MODEL_VERSION,
        'configuration_hash':'wrong','configuration_id':record['task_id'],'cache_audit':audit,'result':result}))
    assert validate_checkpoint(path,record,specification_hash(spec()),2)==(False,'configuration_hash')
