import pytest

from punishment_sim.coalition import ExplicitSimulation, Population
from punishment_sim.model import RaceOrigin


def race(gamma=.5,active=(),flagged=True,target_owner="target",other_owner="c1"):
    pop=Population(.2,(("c1",.1),("c2",.1),("c3",.1)),gamma,0,10,101)
    sim=ExplicitSimulation(pop,"selfish",flagged,active)
    a=sim._new(target_owner,None); b=sim._new(other_owner,None)
    sim._begin_race(a,b,RaceOrigin.SELFISH_RELEASE if target_owner=="target" else RaceOrigin.NATURAL_PROPAGATION)
    return sim,a,b


def test_target_and_competing_owner_always_extend_owned_branch():
    for gamma in (0,1):
        sim,a,b=race(gamma)
        assert sim._choose_race_branch("target")== (a,"OWN_TARGET_BRANCH")
        assert sim._choose_race_branch("c1")== (b,"OWN_EXPLICIT_COMPETING_BRANCH")


def test_neutral_punisher_inactive_leaveout_and_residual_rules():
    sim,a,b=race(1,active=("c2",))
    assert sim._choose_race_branch("c2")== (b,"PETTY_PUNISH_TARGET")
    assert sim._choose_race_branch("c3")== (a,"NEUTRAL_EXPLICIT_GAMMA_TARGET")
    assert sim._choose_race_branch("honest_residual")== (a,"OCEANIC_GAMMA_TARGET")
    leaveout,a,b=race(0,active=("c2",))
    assert leaveout._choose_race_branch("c3")== (b,"NEUTRAL_EXPLICIT_GAMMA_COMPETING")


def test_residual_owner_is_oceanic_but_explicit_ownership_precedes_punishment():
    sim,a,b=race(1,active=("c1",),other_owner="honest_residual")
    assert sim._choose_race_branch("honest_residual")== (a,"OCEANIC_GAMMA_TARGET")
    sim,a,b=race(1,active=("c1",),other_owner="c1")
    assert sim._choose_race_branch("c1")== (b,"OWN_EXPLICIT_COMPETING_BRANCH")


def test_only_random_decisions_consume_tie_stream():
    sim,a,b=race(.5,active=("c2",))
    state=sim.tie_rng.getstate(); sim._choose_race_branch("target"); assert sim.tie_rng.getstate()==state
    sim._choose_race_branch("c1"); assert sim.tie_rng.getstate()==state
    sim._choose_race_branch("c2"); assert sim.tie_rng.getstate()==state
    sim._choose_race_branch("c3"); assert sim.tie_rng.getstate()!=state

def test_oceanic_residual_gamma_endpoints_and_stream_consumption():
    for gamma,expected,reason in ((0,"other","OCEANIC_GAMMA_COMPETING"),(1,"target","OCEANIC_GAMMA_TARGET")):
        sim,a,b=race(gamma,other_owner="honest_residual");state=sim.tie_rng.getstate()
        chosen,why=sim._choose_race_branch("honest_residual")
        assert chosen==(a if expected=="target" else b) and why==reason
        assert sim.tie_rng.getstate()!=state

def test_oceanic_residual_half_split_is_deterministic_and_near_half():
    sim,a,b=race(.5,other_owner="honest_residual"); counts={a:0,b:0}
    for _ in range(10000):counts[sim._choose_race_branch("honest_residual")[0]]+=1
    assert .48 < counts[a]/10000 < .52

def test_actor_kind_helpers_are_explicit():
    sim,_,_=race()
    assert sim.is_oceanic_residual("honest_residual")
    assert not sim.is_persistent_explicit_actor("honest_residual")
    assert sim.is_persistent_explicit_actor("target") and sim.is_persistent_explicit_actor("c1")


def test_benign_owner_loyalty_and_neutral_half_choice():
    sim,a,b=race(.9,target_owner="c2",other_owner="c1")
    assert sim._choose_race_branch("c2")== (a,"OWN_BRANCH_A")
    assert sim._choose_race_branch("c1")== (b,"OWN_BRANCH_B")
    state=sim.tie_rng.getstate(); chosen,reason=sim._choose_race_branch("c3")
    assert chosen in (a,b) and reason in ("BENIGN_NEUTRAL_A","BENIGN_NEUTRAL_B")
    assert sim.tie_rng.getstate()!=state


def test_no_residual_self_fork_path_and_target_sibling_owner_unreachable():
    pop=Population(.2,(("c1",.1),))
    assert [m.id for m in pop.miners].count("honest_residual")==1
    with pytest.raises(ValueError):
        Population(.2,(("target",.1),))


def test_terminal_private_lead_and_omitted_bound():
    pop=Population(.2,(("c1",.1),),.5,0,1,5)
    sim=ExplicitSimulation(pop,"selfish",False,(),discoverers=["target","target","target","c1"])
    out=sim.run()
    assert out["terminal_private_lead"]==2
    assert out["terminal_uncredited_private_blocks"]==2
    assert out["terminal_omitted_selfish_share_bound"]==pytest.approx(2/out["accepted_blocks"])
    honest=ExplicitSimulation(pop,"honest",False,(),discoverers=["c1"]).run()
    assert honest["terminal_private_lead"]==0
    assert honest["terminal_omitted_selfish_share_bound"]==0
