import copy
import json
from pathlib import Path

import pytest

from analysis.plan_oceanic_v4_rerun import plan, analytical_spec
from punishment_sim.research_sweep import generate_tasks
from punishment_sim.sharded_sweep import _task_record, select_execution_records, specification_hash, build_manifest

OLD=Path('configs/research_sweep_stage_b_oceanic_v3_expanded_composition_sampled.json')
NEW=Path('configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_sampled.json')


def test_exact_production_scope_without_mining():
    report=plan(json.loads(OLD.read_text()),json.loads(NEW.read_text()))
    assert report['authorized_environment_count']==42
    assert report['top_level_configurations']==11802
    assert report['zero_lambda_configurations']==3934
    assert report['positive_lambda_configurations']==7868
    assert report['represented_mining_simulations']==2826180
    assert report['future_positive_lambda_mining_simulations']==1884120
    assert report['zero_lambda_mining_simulations_eligible_for_reuse']==942060
    assert {r['accepted_block_work_units'] for r in report['by_lambda']}=={28261800000}


def test_filter_keeps_full_spec_ids_shards_and_does_not_mutate():
    spec=json.loads(NEW.read_text());before=copy.deepcopy(spec)
    tasks=generate_tasks(analytical_spec(spec))[0];records=[_task_record(t,7) for t in tasks]
    original_hash=specification_hash(spec)
    selected=select_execution_records(records,[.005,.02]);zero=select_execution_records(records,[0])
    assert len(selected)==7868 and len(zero)==3934
    assert spec==before and specification_hash(spec)==original_hash
    assert {r['task_id'] for r in selected}.isdisjoint(r['task_id'] for r in zero)
    assert {r['task_id'] for r in selected+zero}=={r['task_id'] for r in records}
    original={r['task_id']:r for r in records}
    assert all(r is original[r['task_id']] for r in selected)
    assert select_execution_records(records) is records
    for rates in ([],[.1],[float('nan')]):
        with pytest.raises(ValueError):select_execution_records(records,rates)


def test_plan_rejects_design_change():
    old=json.loads(OLD.read_text());new=json.loads(NEW.read_text());new['repetitions']=31
    with pytest.raises(ValueError,match='specification changed'):plan(old,new)


def test_old_version_manifest_rejected_before_writes(tmp_path):
    with pytest.raises(ValueError,match='model version'):
        build_manifest(json.loads(OLD.read_text()),tmp_path/'must_not_exist',1)
    assert not (tmp_path/'must_not_exist').exists()
