"""Independent cardinality datasets, unchanged IDs, explicit scope and provenance."""
import copy
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil

import pytest

from punishment_sim import persistent_v2_collection as collection
from punishment_sim import persistent_v2_shards as shards
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import PersistentSimulation
from test_persistent_v2_compact import design, logical_rows

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'core_2to4': [2, 3, 4], 'extension_5': [5], 'extension_6': [6]}


def tiny_design(members):
    result = design(10, horizon=12)
    result['composition'].update(candidate_power=[.06], natural_fork_rate=[.02])
    result['composition']['systematic'] = {'member_counts': members, 'power_step': .01,
        'minimum_member_power': .01, 'sampling': {'mode': 'hhi_quantiles', 'max_per_cell': 1}}
    return result


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def test_configs_scopes_and_unchanged_science():
    core = json.loads((ROOT/'configs/persistent_v2_1pct_10rep.json').read_text())
    historical = json.loads((ROOT/'configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_1pct.json').read_text())
    assert hashlib.sha256((ROOT/'configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_1pct.json').read_bytes()).hexdigest() == '29ef8c1071f7eb2fd0b30979a62c0bf23d39ab50c6616e6ab58e010e562b44d1'
    assert historical['composition']['systematic']['member_counts'] == [2, 3, 4, 5, 6]
    assert historical['repetitions'] == 20 and historical['composition']['candidate_power'][-1] == .60
    totals = dict(populations=0, top_level_rule_configurations=0, after_reuse=0)
    for label, members in LABELS.items():
        config = json.loads((ROOT/f'configs/persistent_v2_{label}_1pct_10rep.json').read_text())
        assert config['composition']['systematic']['member_counts'] == members
        expected = copy.deepcopy(core)
        expected['composition']['systematic']['member_counts'] = members
        assert config == expected
        assert config['repetitions'] == 10 and config['accepted_blocks'] == 30000
        scope = json.loads((ROOT/f'docs/persistent_v2_{label}_scope.json').read_text())
        assert scope['configuration_sha256'] == digest(config)
        assert set(map(int, scope['by_cardinality'])) == set(members)
        assert scope['exact_enumeration'] and scope['final_repetitions'] == 10
        assert scope['populations'] == scope['sampled_structures_per_environment']*186
        assert scope['after_reuse'] == sum(count*10*(2+6*(int(m)+2)) for m, count in scope['by_cardinality'].items())
        assert scope['accepted_block_work_after_reuse'] == scope['after_reuse']*30000
        assert scope['identity_audit']['full_plan_matches_prior_51pct_plan']
        for m, fingerprint in scope['identity_sha256_by_cardinality'].items():
            assert fingerprint == scope['identity_audit']['reference_identity_sha256_by_cardinality'][m]
        for phase, bounds in [('Phase I', [1, 5]), ('Phase II', [6, 10])]:
            assert scope['execution_phases'][phase]['repetitions'] == bounds
            assert scope['execution_phases'][phase]['unique_simulations']*2 == scope['after_reuse']
        for key in totals:
            totals[key] += scope[key]
    assert totals == dict(populations=208320, top_level_rule_configurations=1249920, after_reuse=78882600)


def test_population_local_ids_and_complete_nonoverlapping_partition(tmp_path):
    def inventory(members, directory):
        manifest = shards.prepare_study(tiny_design(members), directory)
        result = {}
        for task in shards.task_rows(directory, manifest, 0):
            assert len(task.population.candidates) in members
            pid = digest(asdict(task.population))
            result[pid] = (asdict(task), [shards.task_key(task, rule) for rule in shards.VARIANTS])
        return result
    full = inventory([2, 3, 4, 5, 6], tmp_path/'full')
    union = {}
    for label, members in LABELS.items():
        part = inventory(members, tmp_path/label)
        assert not set(part).intersection(union)
        assert all(full[pid] == task for pid, task in part.items())
        union.update(part)
    assert union == full


@pytest.fixture(scope='module')
def completed_sources(tmp_path_factory):
    root = tmp_path_factory.mktemp('cardinality-fixtures')
    sources = {}
    for role, members in collection.ROLE_MEMBERS.items():
        directory = root/role
        spec = tiny_design(members)
        spec['shard_count'] = 2 if role == 'extension_6' else 1
        manifest = shards.prepare_study(spec, directory)
        first = [shards.run_shard(directory, shard, rep_end=5) for shard in range(spec['shard_count'])]
        second = [shards.run_shard(directory, shard, rep_start=6, rep_end=10) for shard in range(spec['shard_count'])]
        assert sum(r.get('mining_simulations_executed', 0) for r in first) == sum(r.get('mining_simulations_executed', 0) for r in second) == manifest['scope']['after_reuse']//2
        assert sum(r['baselines'] for r in first)*2 == sum(r['baselines'] for r in second) == manifest['scope']['populations']*20
        sources[role] = directory
    return sources


def forbid_mining(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail('analysis must never mine')
    monkeypatch.setattr(PersistentSimulation, 'run', fail)


def test_combined_merge_default_core_isolation_and_explicit_extensions(completed_sources, tmp_path, monkeypatch):
    forbid_mining(monkeypatch)
    sources = completed_sources
    before = {role: logical_rows(directory) for role, directory in sources.items()}
    collection.export_studies({'core': sources['core']}, tmp_path/'original')
    collection.export_studies(sources, tmp_path/'with_extensions')
    # Also ignore an unselected source that is unavailable or corrupt.
    collection.export_studies({**sources, 'extension_5': tmp_path/'missing'}, tmp_path/'unavailable_extension')
    merged = collection.merge_studies(sources, tmp_path/'collection.json', analysis_scope='extended_2to6')
    assert merged['tasks'] == 30 and merged['populations'] == 5
    assert merged['mining_simulations_executed'] == merged['baseline_payloads_duplicated'] == 0
    collection.export_collection(tmp_path/'collection.json', tmp_path/'default_core')
    for file in (tmp_path/'original').iterdir():
        for other in ('with_extensions', 'unavailable_extension', 'default_core'):
            assert file.read_bytes() == (tmp_path/other/file.name).read_bytes()
    for scope, roles, populations in [('extended_2to5', {'core', 'extension_5'}, 4),
                                      ('extended_2to6', set(sources), 5)]:
        out = tmp_path/scope
        status = collection.export_collection(tmp_path/'collection.json', out, analysis_scope=scope, include_repetitions=True)
        assert status['analysis_repetitions'] == 10 and set(status['sources']) == roles
        rows = read_csv(out/'summary.csv')
        assert len(rows) == populations*6
        assert {r['source_dataset_role'] for r in rows} == roles
        assert {r['analysis_scope'] for r in rows} == {scope}
        assert {r['analysis_status'] for r in rows} == {'FINAL_10_REPETITIONS'}
        assert len(read_csv(out/'six_variant_comparisons.csv')) == populations*15*5
        assert len(read_csv(out/'equal_power_comparisons.csv')) == populations*(populations-1)//2*6*5
    assert {role: logical_rows(directory) for role, directory in sources.items()} == before


def test_preliminary_collection_first_five_survive_final_data(completed_sources, tmp_path, monkeypatch):
    forbid_mining(monkeypatch)
    merged = collection.merge_studies(completed_sources, tmp_path/'preview.json', analysis_scope='extended_2to6', preliminary=True)
    assert merged['analysis_status'] == 'PRELIMINARY_5_REPETITIONS'
    status = collection.export_collection(tmp_path/'preview.json', tmp_path/'preview', analysis_scope='extended_2to6', include_repetitions=True)
    assert status['analysis_repetitions'] == 5
    for file in (tmp_path/'preview').glob('*.csv'):
        for row in read_csv(file):
            assert row['analysis_status'] == 'PRELIMINARY_5_REPETITIONS'
            assert row['analysis_repetitions'] == '5' and row['planned_repetitions'] == '10'
    assert {r['repetition'] for r in read_csv(tmp_path/'preview/repetitions.csv')} == {'0', '1', '2', '3', '4'}


def test_scope_threshold_changes_only_with_requested_extension(completed_sources, tmp_path, monkeypatch):
    forbid_mining(monkeypatch)
    actual = collection.task_analysis
    def controlled_threshold(*args, **kwargs):
        output = actual(*args, **kwargs)
        for row in output['summary']:
            # Controlled reducer fixture: only a five-member coalition wins.
            row['winning'] = len(row['members']) == 5
        return output
    monkeypatch.setattr(collection, 'task_analysis', controlled_threshold)
    for scope in ('core', 'extended_2to5'):
        collection.export_studies(completed_sources, tmp_path/scope, analysis_scope=scope)
    core = [r for r in read_csv(tmp_path/'core/scope_minimum_tested_thresholds.csv') if r['threshold_kind'] == 'winning']
    extended = [r for r in read_csv(tmp_path/'extended_2to5/scope_minimum_tested_thresholds.csv') if r['threshold_kind'] == 'winning']
    assert all(r['hash_power'] == '' for r in core)
    assert all(float(r['hash_power']) == pytest.approx(.06) for r in extended)


def test_missing_wrong_role_incompatible_and_changed_sources_rejected(completed_sources, tmp_path, monkeypatch):
    forbid_mining(monkeypatch)
    with pytest.raises(ValueError, match='missing source'):
        collection.merge_studies({'core': completed_sources['core']}, tmp_path/'missing.json', analysis_scope='extended_2to5')
    with pytest.raises(ValueError, match='source cardinalities'):
        collection.merge_studies({**completed_sources, 'extension_5': completed_sources['core']}, tmp_path/'wrong.json', analysis_scope='extended_2to5')
    changed = tiny_design([5]); changed['seed'] += 1
    shards.prepare_study(changed, tmp_path/'different')
    with pytest.raises(ValueError, match='incompatible scientific designs'):
        collection.merge_studies({**completed_sources, 'extension_5': tmp_path/'different'}, tmp_path/'bad.json', analysis_scope='extended_2to5')
    collection.merge_studies(completed_sources, tmp_path/'collection.json')
    manifest = json.loads((tmp_path/'collection.json').read_text())
    manifest['sources']['core']['study_id'] = 'wrong'
    manifest['collection_id'] = digest({k: v for k, v in manifest.items() if k != 'collection_id'})
    (tmp_path/'collection.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='collection source study changed'):
        collection.export_collection(tmp_path/'collection.json', tmp_path/'changed')


def test_projection_reproducible_from_existing_measurements():
    from analysis.project_persistent_v2_cardinalities import project_cardinalities
    for label in LABELS:
        scope = json.loads((ROOT/f'docs/persistent_v2_{label}_scope.json').read_text())
        recorded = json.loads((ROOT/f'docs/persistent_v2_{label}_projection.json').read_text())
        assert recorded == project_cardinalities(scope)
        assert not recorded['timing_evidence']['new_benchmark_executed']
        assert recorded['kinakuta_planning']['physical_cores'] == 16
        for phase, storage in recorded['storage'].items():
            assert storage['planning_allowance_all_exports_bytes'] == 2*(storage['primary_dataset_bytes']+storage['regular_exports_bytes']+storage['detailed_repetition_exports_bytes'])


@pytest.mark.parametrize('damage', ['receipt', 'missing_repetition', 'extra_record'])
def test_collection_preserves_strict_source_validation(completed_sources, tmp_path, monkeypatch, damage):
    forbid_mining(monkeypatch)
    source = tmp_path/'tampered'
    shutil.copytree(completed_sources['core'], source)
    with sqlite3.connect(source/'shard-00.sqlite3') as db:
        if damage == 'receipt':
            db.execute("UPDATE records SET receipt='invalid' WHERE kind='baseline'")
        elif damage == 'missing_repetition':
            db.execute("DELETE FROM records WHERE kind='repetition' AND id=(SELECT id FROM records WHERE kind='repetition' LIMIT 1)")
        else:
            db.execute("INSERT INTO records SELECT 'foreign',id,body,sha256,receipt FROM records LIMIT 1")
    with pytest.raises(ValueError):
        collection.merge_studies({'core': source}, tmp_path/'merged.json')
    assert not (tmp_path/'merged.json').exists()


def test_core_phased_checkpoint_matches_one_shot(completed_sources, tmp_path):
    manifest = shards.prepare_study(tiny_design([2, 3, 4]), tmp_path)
    result = shards.run_shard(tmp_path, 0)
    assert result['mining_simulations_executed'] == manifest['scope']['after_reuse']
    expected = {key: value for key, value in logical_rows(completed_sources['core']).items()
                if not key[0].startswith('preliminary_')}
    assert logical_rows(tmp_path) == expected


@pytest.mark.parametrize('role', ['extension_5', 'extension_6'])
def test_independent_extension_export_needs_no_core(completed_sources, tmp_path, monkeypatch, role):
    forbid_mining(monkeypatch)
    result = collection.export_studies({role: completed_sources[role]}, tmp_path/'exports', analysis_scope=role)
    assert result['analysis_cardinalities'] == collection.ROLE_MEMBERS[role]
    assert set(result['sources']) == {role}
