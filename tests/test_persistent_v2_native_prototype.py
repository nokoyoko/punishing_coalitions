"""Exact, opt-in native subset tests. No production backend is registered."""
from dataclasses import replace
import itertools
from pathlib import Path

import pytest

from analysis import persistent_v2_native_prototype as native
from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import PersistentSimulation, Rule, CommonRandom
from punishment_sim.persistent_v2_compact import extract_validated
from punishment_sim.persistent_v2_checkpoint import validate_run
from punishment_sim.persistent_v2_validation import validate_lightweight


@pytest.fixture(scope='module', autouse=True)
def compiled_prototype():
    # Explicit test build; never alters the package/production backend registry.
    from analysis.build_persistent_v2_native_prototype import build
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
@pytest.mark.parametrize('n,kind',CONDITIONS)
@pytest.mark.parametrize('gamma,rate',[(0,0),(.5,.005),(1,.02),(.25,1)])
@pytest.mark.parametrize('seed,repetition',[(84,0),(51000,0),(51000,1)])
def test_native_complete_trajectory_compact_and_independent_validation(n,kind,gamma,rate,seed,repetition):
    # Skewed powers exercise residual arithmetic and explicit member ordering.
    p=Population(.31,tuple((f'c{i+1}',.02*(i+1)) for i in range(n)),gamma,rate,60,seed)
    C=tuple(a for a,_ in p.candidates)
    strategy='honest' if kind in ('H','HF') else 'selfish'
    flagged=kind not in ('H','S0')
    active=tuple(a for i,a in enumerate(C) if i!=kind) if isinstance(kind,int) else C if flagged else ()
    reference=PersistentSimulation(p,strategy,flagged,active,Rule('petty'),repetition=repetition,trace_mode=True).run()
    candidate=native.run(p,strategy,flagged,active,repetition=repetition,production=False,trace=True)
    assert candidate.native==reference  # Includes every per-discovery state/RNG snapshot.
    expected=extract_validated(reference,'test-producer',{})
    del expected['producer'],expected['validation']
    assert candidate.compact_unattested==expected
    validate_lightweight(candidate.native,p,Rule('petty'),repetition,strategy,flagged,active)
    validate_run(candidate.native,p,Rule('petty'),repetition,strategy,flagged,active)


def compare_actions(actions, *, strategy='selfish', gamma=.5, rate=1, active=('c1',)):
    p=Population(.2,(('c1',.1),('c2',.1),('c3',.1)),gamma,rate,100,84)
    sim=PersistentSimulation(p,strategy,bool(active),active,Rule('petty'),trace_mode=True)
    for i,action in enumerate(actions):
        if action[0]=='step':sim.step(action[1])
        elif action[0]=='discover':sim.discover(action[1],action[2],withheld=action[3],kind=action[4])
        else:sim.publish(action[1],action[2])
        candidate=native.run(p,strategy,bool(active),active,production=False,trace=True,actions=actions[:i+1])
        assert candidate.native==sim.report()


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
    with pytest.raises(ValueError,match='petty only'):native.run(p,strategy,True,('c1',),rule)


def test_resource_limit_is_not_attested_complete():
    p=Population(.2,(('c1',.1),('c2',.1)),.5,.02,40,84)
    candidate=native.run(p,'selfish',False,max_events=2)
    reference=PersistentSimulation(p,'selfish',False,(),Rule('petty'),production=True,max_events=2).run()
    assert candidate.native==reference
    assert candidate.native['status']=='INCOMPLETE_RESOURCE_LIMIT'
    assert 'validation' not in candidate.compact_unattested


def test_prototype_has_explicit_binary_source_and_build_provenance():
    provenance=native.backend_identity()
    assert provenance['backend']=='persistent-h-s0-petty-native-prototype-v1'
    assert set(provenance['sha256'])=={'native_source','wrapper','binary','build'}
    assert all(len(value)==64 for value in provenance['sha256'].values())


@pytest.mark.parametrize('name', ['c"one\\', 'c\n\t\x00\x7f'])
def test_native_canonical_json_preserves_ascii_identifier_escaping(name):
    p=Population(.2,((name,.1),('c2',.1)),.5,.02,40,84)
    raw=PersistentSimulation(p,'selfish',True,(name,),Rule('petty'),production=True).run()
    candidate=native.run(p,'selfish',True,(name,))
    assert candidate.native==raw
    assert candidate.compact_unattested['native_result_sha256']==digest(raw)
