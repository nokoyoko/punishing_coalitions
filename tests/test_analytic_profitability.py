import csv,json

import pytest

from analysis.generate_eyal_sirer_domain import generate
from punishment_sim.research_sweep import generate_tasks
from punishment_sim.theory import eyal_sirer_profitability_threshold,vanilla_selfish_mining_profitable


@pytest.mark.parametrize('gamma,threshold',[(0,1/3),(.25,.30),(.5,.25),(.75,1/6),(1,0)])
def test_eyal_sirer_threshold_formula(gamma,threshold):
    assert eyal_sirer_profitability_threshold(gamma)==pytest.approx(threshold)


@pytest.mark.parametrize('alpha,gamma',[(1/3,0),(.30,.25),(.25,.5),(.0,1)])
def test_profitability_is_strict_at_the_boundary(alpha,gamma):
    assert not vanilla_selfish_mining_profitable(alpha,gamma)


def test_current_grid_has_14_pairs_and_42_lambda_environments(tmp_path):
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'aggregate':{
        'target_hash':[.10,.15,.20,.25,.30,.35],
        'coalition_power':[.05,.60],
        'gamma':[0,.25,.5,.75,1],
        'natural_fork_rate':[0,.005,.02]}}))
    summary=generate(config,tmp_path)
    assert summary['profitable_target_gamma_pairs']==14
    assert summary['authorized_punishment_environments']==42
    rows=list(csv.DictReader((tmp_path/'authorized_punishment_environments.csv').open()))
    assert len(rows)==42
    assert {(float(r['target_hash_power']),float(r['gamma'])) for r in rows}=={
        (.35,0),(.35,.25),(.30,.5),(.35,.5),
        (.20,.75),(.25,.75),(.30,.75),(.35,.75),
        (.10,1),(.15,1),(.20,1),(.25,1),(.30,1),(.35,1)}


def test_authorization_does_not_depend_on_candidate_power_or_lambda(tmp_path):
    config=tmp_path/'config.json'; config.write_text(json.dumps({'aggregate':{
        'target_hash':[.30], 'coalition_power':[.025,.60], 'gamma':[.5],
        'natural_fork_rate':[0,.005,.02]}}))
    generate(config,tmp_path)
    base={'stage':'test','accepted_blocks':10,'repetitions':1,'minimum_residual_power':.05,
          'tpr':[1],'fpr':[0],'authorized_environment_file':str(tmp_path/'authorized_punishment_environments.csv'),
          'aggregate':{'target_hash':[.30],'coalition_power':[.025,.60],'gamma':[.5],
                       'natural_fork_rate':[0,.005,.02]},'composition':{}}
    tasks,requested,valid=generate_tasks(base)
    assert requested==valid==len(tasks)==6
    assert {t.candidate_total for t in tasks}=={.025,.60}
    assert {t.population.natural_fork_rate for t in tasks}=={0,.005,.02}
