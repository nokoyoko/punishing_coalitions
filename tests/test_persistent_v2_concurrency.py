"""Tiny local fixtures for the fixed-workload concurrency procedure."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from analysis.benchmark_persistent_v2_concurrency import describe, run_benchmark, CONFIG, condition_group
from punishment_sim import persistent_v2_shards as shards
from test_persistent_v2_compact import design


def test_benchmark_description_never_mines_and_covers_variants_cardinality_lambda(monkeypatch):
    monkeypatch.setattr(shards, 'PersistentSimulation', Mock(side_effect=AssertionError('describe must not mine')))
    spec = json.loads(CONFIG.read_text())
    result = describe(spec, 5)
    assert result['scope']['populations'] == 108
    assert result['scope']['top_level_rule_configurations'] == 648
    assert set(result['scope']['by_cardinality']) == {'2', '3', '4'}
    assert set(result['scope']['by_lambda']) == {'0', '0.005', '0.02'}
    assert result['unique_conditions_per_trial'] == result['scope']['after_reuse']//2
    assert result['fixed_work_units'] == 216 and not result['mining_launched']
    assert spec['accepted_blocks'] == 30000 and spec['repetitions'] == 10


def test_identical_fixed_native_workload_at_different_concurrency_and_policies(tmp_path):
    spec = design(repetitions=2, horizon=8, workers=2)
    spec['validation_policy'] = {'mode': 'sampled'}
    result = run_benchmark(spec, tmp_path/'benchmark', workers=(1, 2), modes=('full', 'sampled'), rep_end=2)
    assert result['status'] == 'COMPLETE' and len(result['trials']) == 4
    assert len({t['native_results_sha256'] for t in result['trials']}) == 1
    for mode in ('full', 'sampled'):
        assert len({t['validation_selections_sha256'] for t in result['trials'] if t['validation_mode'] == mode}) == 1
    for row in result['trials']:
        assert row['conditions_completed'] == sum(row['distribution'].values()) == result['inventory']['unique_conditions_per_trial']
        assert row['replayed_conditions']+row['lightweight_only_conditions'] == row['conditions_completed']
        assert row['conditions_per_second'] == row['conditions_completed']/row['wall_seconds']
        assert row['average_busy_cores'] == row['worker_cpu_seconds']/row['wall_seconds']
        assert row['timings_summed_worker_seconds']['lightweight_validation_seconds'] > 0
        assert row['timings_summed_worker_seconds']['mining_seconds'] > 0
        if row['validation_mode'] == 'full':
            assert row['replay_fraction'] == 1 and row['timings_summed_worker_seconds']['sampled_replay_seconds'] == 0
        else:
            assert 0 < row['replay_fraction'] < 1 and row['timings_summed_worker_seconds']['full_replay_seconds'] == 0
        kinds = {json.loads(key)[-1] for key in row['distribution']}
        assert kinds == {'H', 'S0', 'HF', 'SC', 'SC_leaveout'}
    with pytest.raises(ValueError, match='destination exists'):
        run_benchmark(spec, tmp_path/'benchmark', workers=(1,), rep_end=2)
