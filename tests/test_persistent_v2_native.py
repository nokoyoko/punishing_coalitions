"""Exact native trajectories and independent reference validation."""
from dataclasses import replace
import itertools
from pathlib import Path

import pytest

from punishment_sim import persistent_v2_native as native
from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import PersistentSimulation, Rule, CommonRandom
from punishment_sim.persistent_v2_compact import extract_validated
from punishment_sim.persistent_v2_checkpoint import validate_run
from punishment_sim.persistent_v2_validation import validate_lightweight


@pytest.fixture(scope='module', autouse=True)
def compiled_backend():
    # Explicit local fixture build; no production dispatcher is launched.
    from punishment_sim.build_native import build
    build()
    native._module=None
    return native.load_extension()


@pytest.mark.parametrize('seed',[-17,0,84,51000,2**90+7])
@pytest.mark.parametrize('stream',['discoveries','ties','natural'])
def test_exact_mt_draws_state_and_twist_boundaries(seed,stream):
    python=CommonRandom(seed,stream)
    draws,state=native.load_extension().rng_test(python.getstate()[1],10000)
    assert draws==[python.random() for _ in range(10000)]
    assert state==python.getstate()[1]
    # Continue from a non-twist-boundary state, including a zero-draw request.
    for count in (0,1,311,312,313,625):
        draws,state=native.load_extension().rng_test(state,count)
        assert draws==[python.random() for _ in range(count)]
        assert state==python.getstate()[1]


CONDITIONS=[(n,kind) for n in (2,3,4) for kind in ('H','S0','HF','SC',*range(n))]
@pytest.mark.parametrize('balanced',[False,True])
@pytest.mark.parametrize('rule',[Rule('petty'),Rule('counter_fork',1),Rule('counter_fork',2),Rule('counter_fork',3),Rule('ignore'),Rule('selfish')])
@pytest.mark.parametrize('n,kind',CONDITIONS)
@pytest.mark.parametrize('gamma,rate',[(0,0),(.5,.005),(1,.02),(.25,1)])
@pytest.mark.parametrize('seed,repetition',[(84,0),(51000,0),(51000,1)])
def test_native_complete_trajectory_compact_and_independent_validation(n,kind,gamma,rate,seed,repetition,rule,balanced):
    # Skewed powers exercise residual arithmetic and explicit member ordering.
    p=Population(.31,tuple((f'c{i+1}',.04 if balanced else .02*(i+1)) for i in range(n)),gamma,rate,60,seed)
    C=tuple(a for a,_ in p.candidates)
    strategy='honest' if kind in ('H','HF') else 'selfish'
    flagged=kind not in ('H','S0')
    active=tuple(a for i,a in enumerate(C) if i!=kind) if isinstance(kind,int) else C if flagged else ()
    reference=PersistentSimulation(p,strategy,flagged,active,rule,repetition=repetition,trace_mode=True).run()
    candidate=native.run(p,strategy,flagged,active,rule,repetition=repetition,production=False,trace=True)
    assert candidate.native==reference  # Includes every per-discovery state/RNG snapshot.
    expected=extract_validated(reference,'test-producer',{})
    del expected['producer'],expected['validation']
    assert candidate.compact_unattested==expected
    assert native.validate_lightweight(candidate.native,p,rule,repetition,strategy,flagged,active)==validate_lightweight(candidate.native,p,rule,repetition,strategy,flagged,active)
    validate_run(candidate.native,p,rule,repetition,strategy,flagged,active)
    production_record={k:v for k,v in reference.items() if k not in ('trace','public_events')}
    production_record['recording_mode']='production-v2'
    native.validate_replay(production_record,p,rule,repetition,strategy,flagged,active)


def compare_actions(actions, *, strategy='selfish', gamma=.5, rate=1, active=('c1',), rule=Rule('petty')):
    p=Population(.2,(('c1',.1),('c2',.1),('c3',.1)),gamma,rate,100,84)
    sim=PersistentSimulation(p,strategy,bool(active),active,rule,trace_mode=True)
    for i,action in enumerate(actions):
        if action[0]=='step':sim.step(action[1])
        elif action[0]=='discover':sim.discover(action[1],action[2],withheld=action[3],kind=action[4])
        else:sim.publish(action[1],action[2])
        candidate=native.run(p,strategy,bool(active),active,rule,production=False,trace=True,actions=actions[:i+1])
        assert candidate.native==sim.report()
    return sim


@pytest.mark.parametrize('lead',[1,2,3,12])
def test_private_prefix_multiblock_release_delayed_visibility_and_terminal_leads(lead):
    compare_actions([('step','target')]*lead+[('step','honest_residual'),('step','c1'),('step','c2')])


def test_visibility_window_is_consumed_by_private_discovery_and_explicit_owner_knows_own_tip():
    compare_actions([('step',a) for a in ('honest_residual','target','target','target','c1','c1')])


@pytest.mark.parametrize('gamma',[0,.5,1])
def test_target_present_and_absent_multiway_races_and_oceanic_residual(gamma):
    for first in ('target','c2'):
        actions=[('discover',first,None,False,'ordinary'),('discover','c2',None,False,'ordinary'),
                 ('discover','c3',None,False,'ordinary'),('step','c1'),('step','honest_residual')]
        compare_actions(actions,strategy='honest',gamma=gamma,rate=0)


def test_explicit_actor_prefers_latest_of_multiple_own_tips():
    compare_actions([('discover','c1',None,False,'ordinary'),('discover','c2',None,False,'ordinary'),
        ('discover','c1',None,False,'ordinary'),('step','c1')],strategy='honest',rate=0)


def test_private_abandonment_and_terminal_hidden_blocks():
    compare_actions([('step','target'),('discover','c2',None,False,'ordinary'),
        ('discover','c2',2,False,'ordinary'),('step','target')],active=(),rate=0)


@pytest.mark.parametrize('strategy',['honest','selfish'])
@pytest.mark.parametrize('rule',[Rule('counter_fork',1),Rule('counter_fork',2),Rule('counter_fork',3),Rule('ignore'),Rule('selfish')])
def test_baselines_stay_common_across_rule_labels(strategy,rule):
    p=Population(.2,(('c1',.1),('c2',.1)),.5,.02,40,84)
    assert native.run(p,strategy,False,('c1',),rule).native==PersistentSimulation(p,strategy,False,('c1',),rule,production=True).run()


def test_resource_limit_is_not_attested_complete():
    p=Population(.2,(('c1',.1),('c2',.1)),.5,.02,40,84)
    candidate=native.run(p,'selfish',False,max_events=2)
    reference=PersistentSimulation(p,'selfish',False,(),Rule('petty'),production=True,max_events=2).run()
    assert candidate.native==reference
    assert candidate.native['status']=='INCOMPLETE_RESOURCE_LIMIT'
    assert 'validation' not in candidate.compact_unattested


def test_native_has_explicit_binary_source_and_build_provenance():
    provenance=native.backend_identity()
    assert provenance['backend']=='persistent-native-v2-1'
    assert set(provenance['sha256'])=={'native_source','wrapper','binary','build',
        'header:path_emission.hpp','header:json_value.hpp','header:lightweight.hpp','header:replay.hpp'}
    assert all(len(value)==64 for value in provenance['sha256'].values())


@pytest.mark.parametrize('name', ['c"one\\', 'c\n\t\x00\x7f'])
def test_native_canonical_json_preserves_ascii_identifier_escaping(name):
    p=Population(.2,((name,.1),('c2',.1)),.5,.02,40,84)
    raw=PersistentSimulation(p,'selfish',True,(name,),Rule('petty'),production=True).run()
    candidate=native.run(p,'selfish',True,(name,))
    assert candidate.native==raw
    assert candidate.compact_unattested['native_result_sha256']==digest(raw)


@pytest.mark.parametrize('k',[1,2,3])
def test_counter_depth_exhaustion_refresh_and_reanchor_steps(k):
    actions=[('discover','target',None,False,'ordinary'),('step','c1')]
    parent=1
    for _ in range(k):
        actions.append(('discover','honest_residual',parent,False,'ordinary'))
        parent=len(actions)
    actions.extend([('discover','target',parent,False,'ordinary'),
                    ('discover','target',parent+1,False,'ordinary')])
    sim=compare_actions(actions,strategy='honest',rate=0,active=('c1','c2'),rule=Rule('counter_fork',k))
    assert any(e['outcome']=='CAPITULATED' for e in sim.punishment.history)
    assert sim.punishment.episode.refresh_count==1


@pytest.mark.parametrize('k',[1,2,3])
def test_counter_success_and_atomic_last_target_refresh(k):
    sim=compare_actions([('step','target'),('step','c1'),('discover','c2',2,False,'ordinary')],
                        strategy='honest',rate=0,rule=Rule('counter_fork',k))
    assert sim.punishment.history[-1]['outcome']=='SUCCEEDED'
    sim=compare_actions([('step','target')]*3+[('publish',[1,2,3],'target_selfish_release')],
                        rate=0,rule=Rule('counter_fork',k))
    assert sim.punishment.episode.trigger==3 and sim.punishment.episode.refresh_count==2


def test_ostracism_descendants_multiple_roots_and_interior_frontier():
    actions=[('step','target')]+[('discover','honest_residual',i,False,'ordinary') for i in range(1,9)]
    actions.extend([('discover','target',9,False,'ordinary'),('step','c1'),
                    ('discover','target',11,False,'ordinary')])
    sim=compare_actions(actions,strategy='honest',rate=0,active=('c1','c2'),rule=Rule('ignore'))
    assert sim.punishment.rejected_roots=={1,10,12}
    assert sim.punishment.minimal_rejected_roots=={1,12}


def test_simultaneous_and_cascading_independent_reaction_rounds():
    sim=compare_actions([('step',a) for a in ('c2','c1','target','honest_residual','c1')],
                        rate=0,active=('c1','c2'),rule=Rule('selfish'))
    assert len(sim.selfish.history[0]['decisions'])==3
    sim=compare_actions([('step','target')]*5+[('step','c1')]*3+[('step','c2')]*2+[('step','honest_residual')],
                        rate=0,active=('c1','c2'),rule=Rule('selfish'))
    assert len(sim.selfish.history)==3 and sim.selfish.states['target'].private_chain==[4,5]


def test_deep_reorganization_reward_reversal_and_retained_private_chains():
    # Independent hidden chains followed by a long public branch and its overtake.
    actions=[('step','target')]*12+[('step','c1')]*10+[('step','c2')]*8
    actions += [('discover','honest_residual',None,False,'ordinary')]
    actions += [('discover','honest_residual',i,False,'ordinary') for i in range(31,44)]
    sim=compare_actions(actions,rate=0,active=('c1','c2'),rule=Rule('selfish'))
    assert sim.reorganizations
    assert sum(sim.rewards.values())==sim.public_height
