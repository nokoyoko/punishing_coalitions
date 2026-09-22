"""Profiling must preserve validator results, failure behavior and restoration."""
import pytest

from analysis.profile_persistent_v2_boundary import STAGES, validation_timers
from punishment_sim import persistent_v2_shards as shards


@pytest.mark.parametrize('failure', [False, True])
def test_stage_timers_preserve_validator_calls_and_restore_on_error(monkeypatch, failure):
    calls = []
    sentinel = object()

    def validator(*args, **kwargs):
        calls.append((args, kwargs))
        if failure:
            raise ValueError('fixture validation failed')
        return sentinel

    for name in STAGES:
        monkeypatch.setattr(shards, name, validator)
    times = {}
    try:
        with validation_timers(times):
            if failure:
                with pytest.raises(ValueError, match='fixture validation failed'):
                    shards.validate_run('raw', strict=True)
                raise RuntimeError('abort profiling')
            assert shards.validate_run('raw', strict=True) is sentinel
    except RuntimeError:
        assert failure
    assert calls == [(('raw',), {'strict': True})]
    assert set(times) == {'replay'}
    assert times['replay']['cpu_seconds'] >= 0
    assert all(getattr(shards, name) is validator for name in STAGES)
