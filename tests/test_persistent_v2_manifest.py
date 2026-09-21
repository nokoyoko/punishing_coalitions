"""Manifest round trips and worker startup, with simulation construction forbidden."""
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import Mock

import pytest

from punishment_sim import persistent_v2_shards as shards
from punishment_sim.persistent_checkpoint import atomic_json, canonical_json, digest
from punishment_sim.persistent_v2 import NETWORK_VERSION, Rule, condition_identity, model_version

ROOT = Path(__file__).resolve().parents[1]


def design():
    # Enough real populations to exercise numeric versus lexical ordering of
    # occupied shard IDs, unlike a two-population / 28-shard fixture.
    return {'expected_network_version': NETWORK_VERSION, 'repetitions': 10,
            'accepted_blocks': 8, 'seed': 701, 'bootstrap_samples': 20,
            'shard_count': 28, 'variants': [asdict(rule) for rule in shards.VARIANTS],
            'tpr': [.5, .9], 'fpr': [0, .01],
            'composition': {'target_hash': [.2], 'candidate_power': [.2, .3, .4],
                'gamma': [.5], 'natural_fork_rate': [0, .02],
                'systematic': {'power_step': .01, 'minimum_member_power': .01,
                    'member_counts': [2, 3, 4],
                    'sampling': {'mode': 'hhi_quantiles', 'max_per_cell': 2}}}}


def unsigned(manifest):
    return {k: v for k, v in manifest.items() if k not in ('study_id', 'receipt_key_sha256')}


@pytest.fixture(autouse=True)
def no_simulations(monkeypatch):
    sentinel = Mock(side_effect=AssertionError('manifest/startup tests must never construct a simulation'))
    monkeypatch.setattr(shards, 'PersistentSimulation', sentinel)
    yield
    sentinel.assert_not_called()


def test_fresh_manifest_round_trip_design_scope_and_resume(tmp_path):
    requested = design()
    prepared = shards.prepare_study(requested, tmp_path)
    loaded = shards.load_manifest(tmp_path)
    assert loaded == prepared == json.loads((tmp_path/'study.json').read_text())
    assert loaded['design'] == shards.normalize_design(requested)
    assert loaded['scope']['by_cardinality'] == {'2': 12, '3': 12, '4': 12}
    assert loaded['scope']['populations'] == 36
    assert loaded['scope']['top_level_rule_configurations'] == 216
    assert loaded['scope']['shared_baseline_simulations'] == 720
    assert loaded['scope']['before_reuse'] == 15120
    assert loaded['scope']['after_reuse'] == 11520
    with sqlite3.connect(tmp_path/'plan.sqlite3') as plan:
        owners = Counter(str(owner) for owner, in plan.execute('SELECT owner FROM tasks'))
    assert loaded['scope']['populations_by_shard'] == dict(owners)
    assert {'2', '10'} <= owners.keys()
    assert all(type(k) is str for field in ('by_cardinality', 'populations_by_shard')
               for k in prepared['scope'][field])
    assert loaded['study_id'] == digest(unsigned(loaded))
    # Reconstruct the pre-fix Python representation, proving this fixture detects
    # the original bug instead of merely exercising a benign key ordering.
    original = json.loads(canonical_json(unsigned(loaded)))
    for field in ('by_cardinality', 'populations_by_shard'):
        original['scope'][field] = {int(k): v for k, v in original['scope'][field].items()}
    assert digest(original) != loaded['study_id']
    assert digest(json.loads(canonical_json(original))) == loaded['study_id']
    assert shards.prepare_study(requested, tmp_path) == loaded


def test_normalization_covers_entire_unsigned_manifest(tmp_path, monkeypatch):
    normalizer = shards.normalize_design
    # Stand-in for future nested metadata: normalization must not be limited to
    # today's two integer-keyed scope maps. Lists/tuples normalize as JSON too.
    def with_metadata(spec):
        return {**normalizer(spec), 'future_metadata': {'nested': [{10: (2, 3), 2: (4, 5)}]}}
    monkeypatch.setattr(shards, 'normalize_design', with_metadata)
    prepared = shards.prepare_study(design(), tmp_path)
    loaded = shards.load_manifest(tmp_path)
    assert prepared == loaded
    assert loaded['design']['future_metadata'] == {'nested': [{'10': [2, 3], '2': [4, 5]}]}
    assert loaded['study_id'] == digest(unsigned(loaded))


@pytest.mark.parametrize('field', ['design', 'scope', 'by_cardinality', 'populations_by_shard', 'runtime', 'plan_sha256'])
def test_manifest_tampering_still_fails_checksum(tmp_path, field):
    manifest = shards.prepare_study(design(), tmp_path)
    if field in ('by_cardinality', 'populations_by_shard'):
        values = manifest['scope'][field]
        values[next(iter(values))] += 1
    elif field == 'design':
        manifest['design']['seed'] += 1
    elif field == 'scope':
        manifest['scope']['populations'] += 1
    elif field == 'runtime':
        manifest['runtime']['python'] = 'tampered'
    else:
        manifest['plan_sha256'] = '0'*64
    atomic_json(tmp_path/'study.json', manifest)
    with pytest.raises(ValueError, match='study manifest checksum'):
        shards.load_manifest(tmp_path)


def test_receipt_keys_excluded_but_key_provenance_still_checked(tmp_path):
    first = shards.prepare_study(design(), tmp_path/'first')
    second = shards.prepare_study(design(), tmp_path/'second')
    assert first['receipt_key_sha256'] != second['receipt_key_sha256']
    assert first['study_id'] == second['study_id']
    assert first['study_id'] == digest(unsigned(first))
    assert first['study_id'] != digest({k: v for k, v in first.items() if k != 'study_id'})
    first['receipt_key_sha256']['0'] = '0'*64
    atomic_json(tmp_path/'first/study.json', first)
    loaded = shards.load_manifest(tmp_path/'first')
    assert loaded['study_id'] == second['study_id']
    with pytest.raises(ValueError, match='receipt key provenance'):
        shards.ShardStore(tmp_path/'first', loaded, 0)


def test_plan_content_hash_is_still_required(tmp_path):
    shards.prepare_study(design(), tmp_path)
    with sqlite3.connect(tmp_path/'plan.sqlite3') as plan:
        plan.execute('UPDATE tasks SET owner=(owner+1)%28 WHERE ordinal=(SELECT MIN(ordinal) FROM tasks)')
        assert plan.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    with pytest.raises(ValueError, match='plan content mismatch'):
        shards.load_manifest(tmp_path)


def test_corrupt_sqlite_is_still_rejected(tmp_path):
    shards.prepare_study(design(), tmp_path)
    with (tmp_path/'plan.sqlite3').open('r+b') as stream:
        stream.write(b'corrupt database')
    with pytest.raises(sqlite3.DatabaseError):
        shards.load_manifest(tmp_path)


def test_all_workers_reach_normal_startup_without_mining(tmp_path):
    manifest = shards.prepare_study(design(), tmp_path)
    reached = []
    class ReadyToMine(Exception):
        pass
    def stop_before_mining(event, value):
        if event == 'before_condition':
            reached.append(value)
            raise ReadyToMine
    for shard in range(28):
        if manifest['scope']['populations_by_shard'].get(str(shard), 0):
            with pytest.raises(ReadyToMine):
                shards.run_shard(tmp_path, shard, rep_end=5, hook=stop_before_mining)
        else:
            result = shards.run_shard(tmp_path, shard, rep_end=5, hook=stop_before_mining)
            assert result['tasks'] == 0 and result.get('mining_simulations_executed', 0) == 0
        with sqlite3.connect(tmp_path/f'shard-{shard:02d}.sqlite3') as db:
            assert db.execute("SELECT COUNT(*) FROM records WHERE kind IN ('baseline','repetition','task')").fetchone()[0] == 0
    assert len(reached) == len(manifest['scope']['populations_by_shard'])
    assert all(row['actual_seed'] == 701 and row['repetition'] == 0 for row in reached)


def test_real_plan_cli_then_worker_cli_startup(tmp_path):
    config, study = tmp_path/'config.json', tmp_path/'study'
    atomic_json(config, design())
    command = subprocess.run([sys.executable, '-m', 'punishment_sim.persistent_v2_shards',
                              'plan', str(config), str(study)], cwd=ROOT, text=True, capture_output=True, check=True)
    assert json.loads(command.stdout)['populations'] == 36
    manifest = shards.load_manifest(study)
    owner = min(map(int, manifest['scope']['populations_by_shard']))
    # Invoke the same CLI parser/runner in a separate interpreter. Stop via its
    # normal pre-condition hook, and forbid even simulation construction.
    driver = '''
import sys
from punishment_sim import persistent_v2_shards as s
class StartupReady(Exception): pass
def stop(event, value):
    if event == 'before_condition': raise StartupReady
def forbid(*args, **kwargs): raise AssertionError('simulation forbidden')
s.PersistentSimulation = forbid
run = s.run_shard
s.run_shard = lambda *args, **kwargs: run(*args, hook=stop, **kwargs)
sys.argv = ['persistent_v2_shards', 'run', sys.argv[1], '--shard', sys.argv[2], '--rep-start', '1', '--rep-end', '5']
try: s.main()
except StartupReady: print('WORKER_STARTUP_OK_NO_MINING')
else: raise AssertionError('populated worker did not reach normal condition path')
'''
    result = subprocess.run([sys.executable, '-c', driver, str(study), str(owner)],
                            cwd=ROOT, text=True, capture_output=True, check=True)
    assert result.stdout.strip() == 'WORKER_STARTUP_OK_NO_MINING'


def test_population_task_conditions_seeds_owners_and_models_unchanged(tmp_path, monkeypatch):
    captured = []
    actual_digest = shards.digest
    def capture_unsigned(value):
        if isinstance(value, dict) and value.get('layout') == shards.LAYOUT:
            captured.append(json.loads(canonical_json(value)))
        return actual_digest(value)
    monkeypatch.setattr(shards, 'digest', capture_unsigned)
    manifest = shards.prepare_study(design(), tmp_path)
    assert len(captured) == 1 and captured[0] == unsigned(manifest)
    # Current identities use only the same native population/rule/coalitions,
    # never study ID, receipt keys or manifest normalization.
    tasks = []
    for owner in range(28):
        for task in shards.task_rows(tmp_path, manifest, owner):
            p = task.population
            pid = digest(asdict(p))
            assert owner == int(pid[:16], 16)%28
            conditions = []
            for rule in shards.VARIANTS:
                for repetition in (0, 4, 5, 9):
                    identity = condition_identity(p, repetition, 'selfish', True, task.coalitions[0], rule)
                    assert identity['actual_seed'] == p.seed+repetition
                    assert identity['model_version'] == model_version(rule)
                    conditions.append(identity)
            tasks.append([pid, asdict(task), owner,
                          [shards.task_key(task, rule) for rule in shards.VARIANTS], conditions])
    # Pre-fix native plan fixture, generated without mining from the original
    # revision. Includes task/population IDs, all six models, phase-boundary
    # repetition seeds/condition IDs and ownership of every test population.
    assert digest(tasks) == 'af9cce44b4c369465b70e23ed46481c01a3b5990084bfd78707621e847599594'
