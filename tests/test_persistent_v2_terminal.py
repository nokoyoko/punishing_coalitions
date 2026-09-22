"""Exact terminal serialization equivalence, including shared branch prefixes."""
from dataclasses import asdict
from unittest.mock import patch

import pytest

from punishment_sim.persistent_v2_terminal import terminal_state
from punishment_sim.coalition import Population
from punishment_sim.persistent import PersistentSimulation as TreeEngine
from punishment_sim.persistent_v2 import PersistentSimulation, Rule
from punishment_sim.persistent_v2_checkpoint import validate_run

RULES = (Rule('petty'), Rule('counter_fork', 1), Rule('counter_fork', 2),
         Rule('counter_fork', 3), Rule('ignore'), Rule('selfish'))


@pytest.mark.parametrize('rule', RULES)
@pytest.mark.parametrize('n,rate,gamma', [(2,0,0), (2,.005,.5), (3,.02,1), (4,0,.5), (4,.02,0)])
@pytest.mark.parametrize('kind', ['H','S0','HF','SC','leave_first','leave_last'])
def test_complete_native_and_stepwise_terminal_exact(rule, n, rate, gamma, kind):
    p = Population(.27, tuple((f'c{i}', .30/n) for i in range(n)), gamma, rate, 60, 51000)
    C = tuple(a for a, _ in p.candidates)
    strategy = 'honest' if kind in ('H','HF') else 'selfish'
    flagged = kind not in ('H','S0')
    active = (() if not flagged else C[1:] if kind == 'leave_first' else C[:-1] if kind == 'leave_last' else C)
    sim = PersistentSimulation(p, strategy, flagged, active, rule, production=True)
    for _ in range(35):
        sim.step()
        before = TreeEngine.terminal_state(sim)
        assert terminal_state(sim) == before
    while sim.public_height < p.target_accepted_blocks:
        sim.step()
    with patch('punishment_sim.persistent_v2.base_terminal_state', TreeEngine.terminal_state):
        expected = sim.report()
    actual = sim.report()
    assert actual == expected
    validate_run(actual, p, rule, 0, strategy, flagged, active)


def test_shared_prefix_is_serialized_once_and_cache_never_survives_snapshot():
    p = Population(.2, (('c1',.1),('c2',.1)), .5, 0, 20, 84)
    sim = PersistentSimulation(p, 'honest', False, (), RULES[0], production=True)
    tip = None
    for _ in range(10):
        tip = sim.discover('honest_residual', tip)
    prefix = None
    for _ in range(4):
        prefix = sim.discover('target', prefix)
    for _ in range(12):
        sim.discover('c1', prefix)
    expected = TreeEngine.terminal_state(sim)
    with patch('punishment_sim.persistent_v2_terminal.asdict', wraps=asdict) as serialize:
        assert terminal_state(sim) == expected
        assert serialize.call_count == len(expected['canonical_blocks']) + len(expected['frontier_blocks'])
    sim.discover('c2', prefix)
    assert terminal_state(sim) == TreeEngine.terminal_state(sim)
