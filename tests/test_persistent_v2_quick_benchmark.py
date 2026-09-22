"""Planning and mocked orchestration only: these tests prohibit simulation."""
from collections import Counter
import json
import sqlite3
from unittest.mock import Mock, patch

import pytest

from analysis import benchmark_persistent_v2_quick as quick
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import PersistentSimulation, Rule, condition_identity
from punishment_sim.persistent_v2_validation import attestation, FULL, prepare_context


@pytest.fixture(autouse=True)
def forbid_simulation(monkeypatch):
    monkeypatch.setattr(PersistentSimulation, '__init__', Mock(side_effect=AssertionError('no simulations permitted')))


@pytest.fixture(scope='module')
def planned(tmp_path_factory):
    directory = tmp_path_factory.mktemp('quick-core-plan')
    with patch.object(PersistentSimulation, '__init__', side_effect=AssertionError('no simulations permitted')):
        manifest, jobs, inventory = quick.prepare_quick(directory)
    return directory, manifest, jobs, inventory


def fake_result(job, manifest):
    """Synthetic timing/results for control-flow tests; never call the engine."""
    p = quick.population(job['task']['population'])
    records, metrics = [], Counter()
    for strategy, flagged, coalition in job['conditions']:
        identity = condition_identity(p, job['repetition'], strategy, flagged, coalition, Rule(**job['rule']))
        cid = digest(identity)
        validation = attestation(identity, prepare_context(manifest['validation']), [])
        records.append((cid, digest(['fake-native', cid]), validation))
        metrics.update(mining_simulations_executed=1, mining_seconds=1.5,
            lightweight_validation_seconds=.1, sampled_replay_seconds=.5 if validation['level'] == FULL else 0)
    return {'metrics': dict(metrics), 'cpu_seconds': 2*len(records), 'records': records}


def test_actual_core_subset_identities_coverage_and_original_validation_context(planned):
    directory, manifest, jobs, inventory = planned
    assert inventory['unique_conditions_per_trial'] == 1152
    assert inventory['fixed_work_units'] == len(jobs) == 216
    assert len(inventory['populations']) == 18
    assert inventory['core_anchor_populations'] == 810
    assert inventory['selected_anchor_populations'] == 0
    assert inventory['known_replay_reasons_before_mining'] == {'hash_sample': 7}
    assert inventory['condition_ids_sha256'] == 'e4a67577af89eec7b7085860d1073cf174a1865998aa33e0f1e0fb7a4de275f3'
    assert inventory['validation_context_sha256'] == digest(manifest['validation'])
    scope = json.loads((quick.ROOT/'docs/persistent_v2_core_2to4_scope.json').read_text())
    assert inventory['core_plan_sha256'] == scope['native_task_plan_sha256']
    assert manifest['design']['repetitions'] == 10 and manifest['design']['accepted_blocks'] == 30000
    with sqlite3.connect(directory/'plan.sqlite3') as db:
        for row in inventory['populations']:
            body, owner = db.execute('SELECT body,owner FROM tasks WHERE population_key=?', (row['population_id'],)).fetchone()
            assert json.loads(body) == row['task'] and owner == row['owner']
    cells = Counter((len(j['task']['population']['candidates']), j['task']['population']['natural_fork_rate'], j['composition']) for j in jobs)
    assert set(cells.values()) == {12}  # Six variants, two native repetitions.
    assert set(cells) == {(m, rate, kind) for m in (2, 3, 4) for rate in (0, .005, .02) for kind in ('balanced', 'skewed')}
    assert {j['repetition'] for j in jobs} == {0, 1}
    assert {tuple(sorted(j['rule'].items())) for j in jobs} == {tuple(sorted(r.items())) for r in manifest['design']['variants']}
    results = [fake_result(job, manifest) for job in jobs]
    ids = [r[0] for result in results for r in result['records']]
    assert len(ids) == len(set(ids)) == 1152
    groups = Counter()
    for key, count in inventory['distribution'].items():
        group = json.loads(key)
        groups[group[-1]] += count
    assert groups == {'H': 36, 'S0': 36, 'HF': 216, 'SC': 216, 'SC_leaveout': 648}
    assert inventory['selected_anchor_populations'] < len(inventory['populations'])
    assert sum(inventory['known_replay_reasons_before_mining'].values()) < .05*1152


def test_selection_and_queue_do_not_depend_on_plan_row_order(planned, monkeypatch):
    directory, manifest, jobs, inventory = planned
    connect = sqlite3.connect
    class ReverseConnection(sqlite3.Connection):
        def execute(self, query, *args):
            if query == 'SELECT population_key,body,owner FROM tasks':
                query += ' ORDER BY ordinal DESC'
            return super().execute(query, *args)
    monkeypatch.setattr(quick.sqlite3, 'connect', lambda *a, **k: connect(*a, **k, factory=ReverseConnection))
    assert quick.select_jobs(directory, manifest) == (jobs, inventory)


def test_kernel_profile_uses_real_identities_and_complete_stratum_coverage(planned, monkeypatch):
    from analysis import profile_persistent_v2_kernel as profile
    directory, manifest, jobs, inventory = planned
    monkeypatch.setattr(profile, 'prepare_quick', lambda _: (manifest, jobs, inventory))
    observed, cases = profile.corpus(directory)
    assert observed == manifest
    assert len(cases) == len({c['condition_id'] for c in cases}) == 230
    assert Counter(c['kind'] for c in cases) == {'H':19, 'S0':19, 'HF':24, 'SC':114, 'SC_leaveout':54}
    for case in cases:
        p = quick.population(case['task']['population'])
        identity = condition_identity(p, 0, case['strategy'], case['flagged'], case['coalition'], Rule(**case['rule']))
        assert case['identity'] == identity and case['condition_id'] == digest(identity)
        assert p.target_accepted_blocks == 30000 and p.seed == 51000
    cells = {(len(c['task']['population']['candidates']), c['task']['population']['natural_fork_rate'],
              c['composition'], c['rule']['punishment_rule'], c['rule']['counter_fork_k'])
             for c in cases if c['kind'] == 'SC' and c['composition'] != 'gamma_zero_control'}
    assert cells == {(m, rate, composition, r.punishment_rule, r.counter_fork_k)
                     for m in (2,3,4) for rate in (0,.005,.02) for composition in ('balanced','skewed')
                     for r in profile.VARIANTS}
    assert {c['task']['population']['gamma'] for c in cases} == {0,.25,.5,.75,1}


def test_native_backend_benchmark_covers_every_required_condition(planned, monkeypatch):
    from analysis import profile_persistent_v2_kernel as profile
    from analysis.benchmark_persistent_v2_native import inventory, source_goldens
    from punishment_sim.persistent_study import required_conditions
    directory, manifest, jobs, selected = planned
    monkeypatch.setattr(profile, 'prepare_quick', lambda _: (manifest, jobs, selected))
    _, source = profile.corpus(directory)
    cases = inventory(source)
    assert len(cases) == len({c['condition_id'] for c in cases}) == 608
    assert Counter(c['kind'] for c in cases) == {'H':19, 'S0':19, 'HF':114, 'SC':114, 'SC_leaveout':342}
    assert len(source_goldens()) == 229
    for case in cases:
        p = quick.population(case['task']['population'])
        assert (case['strategy'], case['flagged'], tuple(case['coalition'])) in required_conditions(case['task']['coalitions'])
        assert case['condition_id'] == digest(condition_identity(p, 0, case['strategy'], case['flagged'], case['coalition'], Rule(**case['rule'])))
        assert p.seed == 51000 and p.target_accepted_blocks == 30000
    assert {c['condition_id'] for c in source} <= {c['condition_id'] for c in cases}


def test_quick_worker_calls_native_condition_pipeline_without_changing_context(planned, tmp_path, monkeypatch):
    core, manifest, jobs, _ = planned
    job = next(j for j in jobs if any(not c[1] for c in j['conditions']))
    expected = fake_result(job, manifest)
    calls = []
    def condition(store, p, rule, repetition, c, analyze_only, hook, baseline_cache):
        assert store.manifest == manifest and store.validation == prepare_context(manifest['validation'])
        assert store.shard == job['owner'] and repetition == job['repetition'] and not analyze_only
        calls.append(c)
        identity = condition_identity(p, repetition, *c, rule)
        record = next(r for r in expected['records'] if r[0] == digest(identity))
        store.metrics['mining_simulations_executed'] += 1
        return dict(zip(('condition_id', 'native_result_sha256', 'validation'), record))
    monkeypatch.setattr(quick, '_condition', condition)
    result = quick._quick_worker((core, tmp_path, 0, manifest, job))
    assert result['records'] == expected['records']
    assert len(calls) == len(job['conditions'])
    assert result['metrics']['mining_simulations_executed'] == len(calls)


@pytest.mark.parametrize('reverse', [False, True])
def test_exactly_two_sampled_trials_and_compact_result_output(planned, tmp_path, monkeypatch, capsys, reverse):
    _, manifest, jobs, inventory = planned
    monkeypatch.setattr(quick, 'prepare_quick', lambda directory: (manifest, jobs, inventory))
    seen, queues = [], []
    class FakePool:
        def __init__(self, *, max_workers, mp_context):
            seen.append(max_workers)
        def map(self, worker, arguments):
            assert worker is quick._quick_worker
            arguments = list(arguments)
            queues.append([a[-1] for a in arguments])
            return [fake_result(a[-1], a[-2]) for a in arguments]
        def shutdown(self, **kwargs):
            assert kwargs == {'wait': True, 'cancel_futures': True}
    monkeypatch.setattr(quick, 'ProcessPoolExecutor', FakePool)
    destination = tmp_path/'comparison'
    report = quick.run_quick(destination, reverse=reverse)
    assert seen == ([28, 16] if reverse else [16, 28])
    assert queues == [jobs, jobs]
    assert report['status'] == 'COMPLETE' and report['validation_mode'] == 'sampled'
    assert len(report['trials']) == 2
    for key in ('native_results_sha256', 'validation_selections_sha256'):
        assert report['trials'][0][key] == report['trials'][1][key]
    for row in report['trials']:
        assert row['unique_conditions'] == 1152
        assert row['total_mining_seconds'] == 1152*1.5
        assert row['lightweight_validation_seconds'] > 0
        assert row['native_replay_seconds'] > 0
        assert row['conditions_per_second'] == 1152/row['wall_seconds']
        assert row['replay_fraction'] == row['replay_count']/1152
        assert row['average_busy_cores'] == 1152*2/row['wall_seconds']
    output = capsys.readouterr().out
    assert '16 workers:' in output and '28 workers:' in output and 'relative throughput:' in output
    assert 'total_mining_seconds' in output and 'native_replay_seconds' in output and 'replay_count' in output
    monkeypatch.setattr('sys.argv', ['quick', '--result', str(destination/'benchmark.json')])
    quick.main()
    assert 'relative throughput:' in capsys.readouterr().out
    with pytest.raises(FileExistsError): quick.run_quick(destination)


def test_duplicate_or_altered_condition_results_rejected(planned):
    _, manifest, jobs, inventory = planned
    results = [fake_result(j, manifest) for j in jobs]
    results[0]['records'][0] = results[1]['records'][0]
    with pytest.raises(ValueError, match='changed or duplicated conditions'):
        quick.summarize_trial(16, 10, results, inventory)


def test_worker_failure_is_fatal_and_does_not_launch_second_trial(planned, tmp_path, monkeypatch):
    _, manifest, jobs, inventory = planned
    monkeypatch.setattr(quick, 'prepare_quick', lambda directory: (manifest, jobs, inventory))
    calls = []
    class FailedPool:
        def __init__(self, *, max_workers, mp_context): calls.append(max_workers)
        def map(self, *args): raise ValueError('injected worker failure')
        def shutdown(self, **kwargs): assert kwargs['cancel_futures']
    monkeypatch.setattr(quick, 'ProcessPoolExecutor', FailedPool)
    with pytest.raises(ValueError, match='injected worker failure'): quick.run_quick(tmp_path/'failed')
    assert calls == [16]
    assert json.loads((tmp_path/'failed/benchmark.json').read_text())['status'] == 'FAILED'


def test_describe_cli_does_not_create_worker_pool(planned, monkeypatch, capsys):
    _, manifest, jobs, inventory = planned
    monkeypatch.setattr(quick, 'prepare_quick', lambda directory: (manifest, jobs, inventory))
    monkeypatch.setattr(quick, 'ProcessPoolExecutor', Mock(side_effect=AssertionError('describe cannot launch workers')))
    monkeypatch.setattr('sys.argv', ['quick', '--describe'])
    quick.main()
    assert json.loads(capsys.readouterr().out)['unique_conditions_per_trial'] == 1152


@pytest.mark.parametrize('field', ['native', 'validation'])
def test_cross_trial_result_or_validation_drift_is_fatal(planned, tmp_path, monkeypatch, field):
    _, manifest, jobs, inventory = planned
    monkeypatch.setattr(quick, 'prepare_quick', lambda directory: (manifest, jobs, inventory))
    class ChangedPool:
        def __init__(self, *, max_workers, mp_context): self.workers = max_workers
        def map(self, worker, arguments):
            results = [fake_result(a[-1], a[-2]) for a in arguments]
            if self.workers == 28:
                cid, native, validation = results[0]['records'][0]
                if field == 'native': native = 'changed'
                else: validation = {**validation, 'policy_sha256': 'changed'}
                results[0]['records'][0] = (cid, native, validation)
            return results
        def shutdown(self, **kwargs): pass
    monkeypatch.setattr(quick, 'ProcessPoolExecutor', ChangedPool)
    with pytest.raises(ValueError, match='quick comparison changed'):
        quick.run_quick(tmp_path/'changed')
    assert json.loads((tmp_path/'changed/benchmark.json').read_text())['status'] == 'FAILED'


def test_cli_cannot_request_other_worker_counts_or_full_mode(monkeypatch):
    monkeypatch.setattr(quick, 'run_quick', Mock(side_effect=AssertionError('must not run')))
    for arguments in (['--workers', '8'], ['--workers', '24'], ['--modes', 'full'], ['--trials', '2']):
        monkeypatch.setattr('sys.argv', ['quick', '--run', '--output', 'unused', *arguments])
        with pytest.raises(SystemExit) as exc: quick.main()
        assert exc.value.code == 2
