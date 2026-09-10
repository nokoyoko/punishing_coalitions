"""Race-specific propagation, ownership, and reachable-state regressions."""
import itertools
from unittest.mock import Mock

import pytest

from punishment_sim.coalition import ExplicitSimulation, Population, MODEL_VERSION
from punishment_sim.config import SimulationConfig
from punishment_sim.model import Actor, RaceOrigin
from punishment_sim.simulation import Simulation
from punishment_sim.sharded_sweep import validate_checkpoint
import json

R = 'honest_residual'


def explicit(owners, gamma=.5, active=(), actor='c3', draw=.25, strategy='selfish'):
    pop = Population(.2, (('c1', .1), ('c2', .1), ('c3', .1)), gamma, 1, 10, 101)
    sim = ExplicitSimulation(pop, strategy, True, active)
    a, b = [sim._new(owner, None) for owner in owners]
    sim._begin_race(a, b, RaceOrigin.NATURAL_PROPAGATION)
    sim.tie_rng = Mock(random=Mock(return_value=draw))
    return sim, a, b


@pytest.mark.parametrize('owners', [(R, 'c1'), ('c1', R)])
@pytest.mark.parametrize('draw', [0, .499, .5, .999])
def test_benign_residual_never_owns(owners, draw):
    sim, a, b = explicit(owners, draw=draw)
    assert sim._choose_race_branch(R) == ((a, 'BENIGN_NEUTRAL_A') if draw < .5 else (b, 'BENIGN_NEUTRAL_B'))
    sim.tie_rng.random.assert_called_once_with()


@pytest.mark.parametrize('owners', [(R, 'target'), ('target', R)])
@pytest.mark.parametrize('gamma', [0, .5, 1])
@pytest.mark.parametrize('draw', [.25, .5, .75])
def test_target_residual_gamma_both_orders(owners, gamma, draw):
    sim, a, b = explicit(owners, gamma=gamma, draw=draw)
    target = a if owners[0] == 'target' else b
    other = b if target == a else a
    chosen, reason = sim._choose_race_branch(R)
    assert chosen == (target if draw < gamma else other)
    assert reason == ('OCEANIC_GAMMA_TARGET' if draw < gamma else 'OCEANIC_GAMMA_COMPETING')
    sim.tie_rng.random.assert_called_once_with()


@pytest.mark.parametrize('actor,active', [('c3', ()), ('c3', ('c2',)), ('c3', ('c2', 'c3')), ('target', ()), (R, ())])
@pytest.mark.parametrize('gamma', [0, .5, 1])
@pytest.mark.parametrize('draw', [.25, .75])
def test_benign_gamma_isolation_and_leaveout(actor, active, gamma, draw):
    sim, a, b = explicit(('c1', R), gamma, active, draw=draw)
    assert sim._choose_race_branch(actor)[0] == (a if draw < .5 else b)
    sim.tie_rng.random.assert_called_once_with()


@pytest.mark.parametrize('other', ['target', 'c2'])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('active', [(), ('c1',)])
@pytest.mark.parametrize('gamma', [0, 1])
def test_explicit_ownership_no_draw(other, reverse, active, gamma):
    owners = ('c1', other) if not reverse else (other, 'c1')
    sim, a, b = explicit(owners, gamma, active)
    assert sim._choose_race_branch('c1')[0] == (a if owners[0] == 'c1' else b)
    sim.tie_rng.random.assert_not_called()


@pytest.mark.parametrize('active', [(), ('c2',), ('c2', 'c3')])
def test_punishment_and_leaveout(active):
    sim, a, b = explicit(('target', R), gamma=1, active=active)
    chosen, reason = sim._choose_race_branch('c3')
    if 'c3' in active:
        assert (chosen, reason) == (b, 'PETTY_PUNISH_TARGET')
        sim.tie_rng.random.assert_not_called()
    else:
        assert (chosen, reason) == (a, 'NEUTRAL_EXPLICIT_GAMMA_TARGET')
        sim.tie_rng.random.assert_called_once_with()


@pytest.mark.parametrize('engine', ['explicit', 'basic'])
@pytest.mark.parametrize('target_present', [False, True])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('gamma', [0, .5, 1])
@pytest.mark.parametrize('draw', [.25, .75])
def test_reachable_natural_residual_resolution(engine, target_present, reverse, gamma, draw):
    other = 'target' if target_present else 'c1'
    owners = [R, other] if not reverse else [other, R]
    if engine == 'explicit':
        pop = Population(.2, (('c1', .1),), gamma, 1, 2, 17)
        sim = ExplicitSimulation(pop, 'honest', True, ('c1',), discoverers=owners + [R])
        sim.tie_rng = rng = Mock(random=Mock(return_value=draw))
    else:
        mapping = {R: Actor.HONEST, 'c1': Actor.COALITION, 'target': Actor.TARGET}
        cfg = SimulationConfig(gamma=gamma, natural_fork_rate=1, strategy='honest', forced_label=True)
        sim = Simulation(cfg, discoverers=[mapping[x] for x in owners + [R]])
        sim.honest_tie_rng = rng = Mock(random=Mock(return_value=draw))
    sim.step(); sim.step()
    assert sim.race and not sim.private
    sim.step()
    probability_a = (gamma if owners[0] == 'target' else 1-gamma) if target_present else .5
    # Target draws select T when draw < gamma, irrespective of ordering.
    choose_a = ((owners[0] == 'target') == (draw < gamma)) if target_present else draw < probability_a
    chosen = 1 if choose_a else 2
    assert sim.blocks[3].parent_id == chosen
    assert not sim.race and not sim.private
    rng.random.assert_called_once_with()


@pytest.mark.parametrize('engine', ['explicit', 'basic'])
def test_normal_state_invariants(engine):
    # Exhaust all four-discovery sequences: windows, races, lead 1, 2 and >2.
    for strategy in ('honest', 'selfish'):
        for sequence in itertools.product(('target', 'c1', R), repeat=4):
            if engine == 'explicit':
                sim = ExplicitSimulation(Population(.2, (('c1', .1),), .5, 1), strategy, True, ('c1',), discoverers=sequence)
            else:
                mapping = {'target': Actor.TARGET, 'c1': Actor.COALITION, R: Actor.HONEST}
                sim = Simulation(SimulationConfig(strategy=strategy, natural_fork_rate=1), discoverers=[mapping[x] for x in sequence])
            for _ in sequence:
                sim.step()
                assert not (sim.race and sim.private)
                pending = sim.pending if engine == 'explicit' else sim.propagation_pending
                assert not (pending and sim.private)


def test_reject_injected_race_with_private_chain():
    sim, a, b = explicit(('c1', R))
    sim.private.append(a)
    with pytest.raises(AssertionError, match='empty private chain'):
        sim._begin_race(a, b, RaceOrigin.NATURAL_PROPAGATION)
    basic = Simulation(SimulationConfig())
    basic.private.append(1)
    with pytest.raises(AssertionError, match='empty private chain'):
        basic._begin_race(1, 2, RaceOrigin.NATURAL_PROPAGATION)


@pytest.mark.parametrize('flagged', [False, True])
def test_basic_coalition_target_policy_preserved(flagged):
    sim = Simulation(SimulationConfig(gamma=1, forced_label=flagged), discoverers=[Actor.COALITION])
    a, b = sim.inject_public_race(competing_owner=Actor.COALITION)
    sim.coalition_tie_rng = Mock(random=Mock(return_value=.25))
    sim.step()
    assert sim.blocks[3].parent_id == (b if flagged else a)
    sim.coalition_tie_rng.random.assert_called_once_with()


def test_v3_checkpoint_rejected_even_at_zero_lambda(tmp_path):
    from punishment_sim.sharded_sweep import CHECKPOINT_SCHEMA
    path = tmp_path / 'v3.json'
    path.write_text(json.dumps({'checkpoint_schema': CHECKPOINT_SCHEMA, 'model_version': 'race-owner-oceanic-residual-v3', 'natural_fork_rate': 0}))
    assert MODEL_VERSION == 'race-owner-oceanic-all-races-v4'
    assert validate_checkpoint(path, {}, '', 1) == (False, 'model_version')


def test_zero_lambda_matches_frozen_prepatch_v3_outputs():
    import hashlib
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / 'fixtures/oceanic_v3_zero_lambda.json').read_text())
    assert fixture['source_model'] == 'race-owner-oceanic-residual-v3'
    for case in fixture['cases']:
        pop = Population(fixture['target_hash_power'], tuple(map(tuple, fixture['candidates'])), case['gamma'], 0, fixture['target_accepted_blocks'], case['seed'])
        result = ExplicitSimulation(pop, case['strategy'], fixture['flagged'], case['active'], trace_mode=fixture['trace_mode']).run()
        digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        assert digest == case['sha256'], case
