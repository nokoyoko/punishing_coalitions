"""Diagnostic budget failures cannot become completed native validation."""
from dataclasses import asdict
from unittest.mock import Mock

import pytest

from analysis import profile_persistent_v2_kernel as profile
from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import Rule, condition_identity


def test_censored_trajectory_never_attests_or_persists(tmp_path, monkeypatch):
    p = Population(.2, (('c1',.1),('c2',.1)), .5, 0, 30, 51000)
    rule = Rule('petty')
    identity = condition_identity(p, 0, 'honest', False, (), rule)
    case = {'task':{'population':asdict(p)}, 'rule':asdict(rule), 'identity':identity,
            'condition_id':digest(identity), 'strategy':'honest', 'flagged':False,
            'coalition':[], 'composition':'balanced', 'kind':'H', 'owner':0, 'profile':False}
    monkeypatch.setattr(profile, 'corpus', lambda _: ({'runtime':{}}, [case]))
    def limited(sim):
        raise profile.PhaseLimit('deliberate diagnostic limit')
    monkeypatch.setattr(profile, 'trajectory', limited)
    forbid = Mock(side_effect=AssertionError('censored state cannot be validated or stored'))
    monkeypatch.setattr(profile, '_validate_fresh', forbid)
    monkeypatch.setattr(profile, 'ShardStore', forbid)
    result = profile.run(tmp_path/'censored')
    assert result['status'] == 'COMPLETE_WITH_CENSORING'
    row = result['cases'][0]
    assert row['status'] == 'PHASE_CENSORED' and row['censored_phase'] == 'trajectory'
    assert not {'native_result_sha256', 'validation', 'exact_reference_match'} & row.keys()
    forbid.assert_not_called()


def test_structural_expansion_counts_match_reference_paths():
    p = Population(.2, (('c1',.1),('c2',.1)), .5, 0, 30, 51000)
    sim = profile.PersistentSimulation(p, 'selfish', False, (), Rule('petty'))
    for actor in ('target','honest_residual','c1','c2')*4:
        sim.step(actor)
    # Create abandoned/private and public side branches as well as the main path.
    parent = sim.discover('target', None, withheld=True)
    sim.discover('target', parent, withheld=True)
    sim.discover('c1', None)
    branches = sim.terminal_state()['alternative_branches']
    shape = profile.ledger_shape(sim)
    assert shape['terminal_branches'] == len(branches)
    assert shape['terminal_path_entries'] == sum(len(b['path']) for b in branches)
    assert shape['maximum_terminal_path'] == max(len(b['path']) for b in branches)


@pytest.mark.parametrize('options', [{'phase_seconds':0}, {'total_seconds':-1}, {'max_path_entries':-1}])
def test_invalid_limits_do_not_create_output(tmp_path, options):
    destination = tmp_path/'invalid'
    with pytest.raises(ValueError, match='budgets'):
        profile.run(destination, **options)
    assert not destination.exists()
