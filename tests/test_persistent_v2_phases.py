"""Stable first-five snapshots and exact final 5+5/10 scientific equivalence."""
import copy
import csv
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

import pytest
from punishment_sim import persistent_v2_shards as s
from punishment_sim.coalition import paired_stats
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import Rule
from tests.test_persistent_v2_compact import design, logical_rows


def test_five_and_ten_student_t():
    for n,critical in ((5,2.776),(10,2.262)):
        values=[i/100 for i in range(n)]
        stats=paired_stats(values)
        assert stats['n']==n
        assert stats['ci95_high']-stats['mean']==pytest.approx(critical*stats['standard_error'])


def snapshots(directory, preliminary=False):
    manifest=s.load_manifest(directory)
    result={}
    for shard in range(manifest['design']['shard_count']):
        store=s.ShardStore(directory,manifest,shard,readonly=True)
        try:
            for task in s.task_rows(directory,manifest,shard):
                for v in manifest['design']['variants']:
                    rule=Rule(**v)
                    result[s.task_key(task,rule)]=s.task_analysis(store,task,rule,analyze_only=True,preliminary=preliminary)
        finally: store.close()
    return result


def test_split_global_phases_equal_one_shot_and_preliminary_stays_stable(tmp_path,monkeypatch):
    spec=design(10,workers=3)
    whole,split=tmp_path/'whole',tmp_path/'split'
    mw=s.prepare_study(spec,whole);ms=s.prepare_study(spec,split)
    assert mw['plan_sha256']==ms['plan_sha256']
    for shard in range(3): s.run_shard(whole,shard)
    seen=[]
    original=s.PersistentSimulation
    def observe(*args,**kwargs):
        sim=original(*args,**kwargs);seen.append(copy.deepcopy(sim.identity));return sim
    monkeypatch.setattr(s,'PersistentSimulation',observe)
    first=[s.run_shard(split,i,rep_start=1,rep_end=5) for i in reversed(range(3))]
    assert {r['repetition'] for r in seen}==set(range(5))
    assert sum(r.get('mining_simulations_executed',0) for r in first)==ms['scope']['after_reuse']//2
    assert all(r['analysis_status']=='PRELIMINARY_5_REPETITIONS' for r in first)
    assert not any(kind in ('task','complete') for kind,key in logical_rows(split))
    with pytest.raises(ValueError,match='incomplete'): s.merge_shards(split,tmp_path/'bad-final.sqlite3')
    preliminary=snapshots(split,True)
    for output in preliminary.values():
        for rows in output.values():
            for row in rows:
                assert row['analysis_status']=='PRELIMINARY_5_REPETITIONS'
                assert row['analysis_repetitions']==5 and row['planned_repetitions']==10
        assert all(row['deterrence']['n']==5 for row in output['summary'])
    merged=s.merge_shards(split,tmp_path/'preliminary.sqlite3',preliminary=True)
    assert merged['analysis_status']=='PRELIMINARY_5_REPETITIONS'
    exported=s.export_study(split,tmp_path/'preliminary',preliminary=True,include_repetitions=True)
    assert exported['status']=='PRELIMINARY_5_REPETITIONS'
    for path in (tmp_path/'preliminary').glob('*.csv'):
        for row in csv.DictReader(path.open()): assert row['analysis_status']=='PRELIMINARY_5_REPETITIONS'
    seen.clear()
    # One shard progresses; first-five snapshots and scientific comparisons stay fixed.
    s.run_shard(split,0,rep_start=6,rep_end=7)
    assert snapshots(split,True)==preliminary
    for shard in range(3): s.run_shard(split,shard,rep_start=6,rep_end=10)
    assert {r['repetition'] for r in seen}==set(range(5,10))
    assert len(seen)==ms['scope']['after_reuse']//2
    assert all(r['actual_seed']==r['base_seed']+r['repetition'] for r in seen)
    assert snapshots(split)==snapshots(whole)
    assert snapshots(split,True)==preliminary
    for output in snapshots(split).values():
        assert all(row['analysis_status']=='FINAL_10_REPETITIONS' and row['deterrence']['n']==10 for row in output['summary'])
    logical_split=logical_rows(split); logical_whole=logical_rows(whole)
    assert {k:v for k,v in logical_split.items() if not k[0].startswith('preliminary_')}==logical_whole
    assert sum(k[0]=='baseline' for k in logical_split)==ms['scope']['shared_baseline_simulations']
    s.merge_shards(split,tmp_path/'final.sqlite3')
    monkeypatch.setattr(s,'PersistentSimulation',Mock(side_effect=AssertionError('no repeat mining')))
    for shard in range(3): s.run_shard(split,shard,rep_start=6,rep_end=10)


@pytest.mark.parametrize('start,end',[(0,5),(1,11),(6,5),(True,5),(1,4.5)])
def test_invalid_ranges(tmp_path,start,end):
    s.prepare_study(design(10),tmp_path)
    with pytest.raises(ValueError,match='range'): s.run_shard(tmp_path,0,rep_start=start,rep_end=end)


def test_phase_two_requires_valid_phase_one_and_partial_resume(tmp_path,monkeypatch):
    s.prepare_study(design(10,variants=(Rule('petty'),)),tmp_path)
    with pytest.raises(ValueError,match='earlier repetition'): s.run_shard(tmp_path,0,rep_start=6,rep_end=10)
    s.run_shard(tmp_path,0,rep_end=5)
    def fail(event,value):
        if event=='after_repetition_commit' and value['repetition']==6: raise InterruptedError('Phase II interruption')
    with pytest.raises(InterruptedError): s.run_shard(tmp_path,0,rep_start=6,rep_end=10,hook=fail)
    before=logical_rows(tmp_path)
    original=s.PersistentSimulation
    def observed(*args,**kwargs):
        sim=original(*args,**kwargs)
        assert ('baseline',digest(sim.identity)) not in before
        assert sim.identity['repetition']>=5
        return sim
    monkeypatch.setattr(s,'PersistentSimulation',observed)
    s.run_shard(tmp_path,0,rep_start=6,rep_end=10)


def test_normal_entry_reports_preliminary_execution_explicitly(tmp_path):
    from punishment_sim.persistent_v2_production import run_production
    spec=design(10,variants=(Rule('petty'),))
    spec.pop('variants');spec.pop('shard_count')
    spec.update(punishment_rule='petty',counter_fork_k=None,expected_model_version='persistent-petty-v2')
    result=run_production(spec,tmp_path,rep_start=1,rep_end=5)
    assert result['metadata']['analysis_status']=='PRELIMINARY_5_REPETITIONS'
    assert result['metadata']['requested_repetitions']==[1,5]
    assert result['metadata']['repetitions']==10


def test_preliminary_requires_all_first_five_and_final_ignores_fake_completion(tmp_path):
    manifest=s.prepare_study(design(10,variants=(Rule('petty'),)),tmp_path)
    s.run_shard(tmp_path,0,rep_end=4)
    with pytest.raises(ValueError,match='missing repetition'):
        s.merge_shards(tmp_path,tmp_path/'too-early.sqlite3',preliminary=True)
    s.run_shard(tmp_path,0,rep_start=5,rep_end=5)
    store=s.ShardStore(tmp_path,manifest,0)
    try:
        store.put('complete','0',{'tasks':2,'baselines':40,'repetitions':20,'study_id':manifest['study_id'],'shard':0})
    finally:store.close()
    with pytest.raises(ValueError,match='missing repetition'):
        s.merge_shards(tmp_path,tmp_path/'false-final.sqlite3')
