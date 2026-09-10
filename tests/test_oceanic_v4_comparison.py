import json
from pathlib import Path

import pytest

from analysis.compare_oceanic_v4 import compare, read, write
from analysis.plan_oceanic_v4_rerun import analytical_spec
from punishment_sim.research_sweep import generate_tasks
from punishment_sim.sharded_sweep import task_id


def fixture_data(tmp_path):
    spec=json.loads(Path('configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_sampled.json').read_text())
    # Tiny synthetic composition, keeping the 42-environment authorization grid.
    spec['composition']['candidate_power']=[.06]
    spec['composition']['systematic']['member_counts']=[2]
    spec['composition']['systematic']['sampling']['max_per_cell']=1
    tasks=generate_tasks(analytical_spec(spec))[0]
    old=tmp_path/'old';new=tmp_path/'new';out=tmp_path/'comparison'
    for dest,version in ((old,'race-owner-oceanic-residual-v3'),(new,'race-owner-oceanic-all-races-v4')):
        dest.mkdir();mining=[];coalitions=[];members=[]
        for t in tasks:
            p=t.population;cid=task_id(t);coal='|'.join(t.coalitions[0])
            common={'configuration_id':cid,'target_hash_power':p.target_hash_power,'gamma':p.gamma,'natural_fork_rate':p.natural_fork_rate,'model_version':version}
            mining.append({**common,'candidate_distribution':json.dumps(dict(p.candidates)),
                'repetitions':spec['repetitions'],'accepted_blocks':spec['accepted_blocks']})
            changed=dest==new and p.natural_fork_rate==.005
            stat=json.dumps({'mean':.02,'ci95_low':.01,'ci95_high':.03})
            coalitions.append({**common,'coalition':coal,'members':json.dumps(list(t.coalitions[0])),
                'active_hash_power':.06,'effectiveness_status':'SUPPORTED','winning':changed,
                'deterrence':stat,'punishment_reduction':stat})
            for m,h in p.candidates:
                # Baseline refuted, so raw pipeline winning != joint feasibility.
                baseline=json.dumps({'mean':-.01,'ci95_low':-.02,'ci95_high':-.005})
                members.append({**common,'coalition':coal,'member_id':m,'baseline':baseline,'deviation':stat})
        write(dest/'mining_configurations.csv',mining);write(dest/'coalition_results.csv',coalitions);write(dest/'member_credibility.csv',members)
        (dest/'equal_hash_comparisons.csv').write_text('left_configuration_id,left_coalition,right_configuration_id,right_coalition,metric\n')
    return old,new,out,spec


def test_all_42_environments_and_winning_definition_distinction(tmp_path):
    old,new,out,spec=fixture_data(tmp_path)
    audit=compare(old,new,out,spec)
    assert audit['environment_count']==42 and audit['zero_lambda_scientific_rows_equal']
    assert not audit['positive_lambda_no_pipeline_winner_under_v4']
    rows=read(out/'environment_feasibility_comparison.csv')
    assert len(rows)==42
    changed=[r for r in rows if float(r['natural_fork_rate'])==.005]
    assert len(changed)==14
    assert all(r['pipeline_winning_changed']=='True' and r['v4_weak_joint_exists']=='False' for r in changed)
    assert all(float(r['v4_effective_min_power'])==.06 for r in rows)


def test_zero_lambda_change_fails_comparison_audit(tmp_path):
    old,new,out,spec=fixture_data(tmp_path)
    rows=read(new/'coalition_results.csv');row=next(r for r in rows if float(r['natural_fork_rate'])==0)
    row['winning']='True';write(new/'coalition_results.csv',rows)
    assert compare(old,new,out,spec)['status']=='ZERO_LAMBDA_MISMATCH'


def test_scope_and_source_directory_protection(tmp_path):
    old,new,out,spec=fixture_data(tmp_path)
    with pytest.raises(ValueError,match='separate'):compare(old,new,old/'comparison',spec)
    rows=read(new/'mining_configurations.csv');write(new/'mining_configurations.csv',rows[1:])
    with pytest.raises(ValueError,match='scope'):compare(old,new,out,spec)
