"""Explicit sampled validation, scientific invariance and fail-closed storage."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import random
import sqlite3
from unittest.mock import Mock
import zlib

import pytest

from punishment_sim import persistent_v2_shards as shards
from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import atomic_json, digest
from punishment_sim.persistent_v2 import PersistentSimulation, CommonRandom, Rule, condition_identity
from punishment_sim.persistent_v2_checkpoint import validate_run
from punishment_sim.persistent_v2_compact import (extract_validated, validate_compact, runtime_identity, compact_run)
from punishment_sim.persistent_v2_validation import (normalize_policy, validation_context, prepare_context,
    add_anchor, stratum, attestation, replay_reasons, validate_lightweight, LIGHT, FULL)
from test_persistent_v2_compact import design


def sampled_design():
    spec = design(repetitions=10, horizon=12)
    spec['composition']['natural_fork_rate'] = [0]
    spec['validation_policy'] = {'mode': 'sampled', 'sample_per_million': 10000}
    return spec


def records(directory):
    output = {}
    for path in Path(directory).glob('shard-*.sqlite3'):
        with sqlite3.connect(path) as db:
            for kind, blob in db.execute("SELECT kind,body FROM records WHERE kind IN ('baseline','repetition')"):
                value = json.loads(zlib.decompress(blob))
                for record in [value] if kind == 'baseline' else value['conditions']:
                    output[record['condition_id']] = record
    return output


def test_selection_is_deterministic_order_independent_and_does_not_touch_rng(monkeypatch):
    p = Population(.2, (('c1', .1), ('c2', .1)), .5, .02, 12, 701)
    context = validation_context({'mode': 'sampled'})
    identities = [condition_identity(p, rep, 'selfish', True, ('c1', 'c2'), Rule('petty')) for rep in range(10000)]
    monkeypatch.setattr(CommonRandom, 'random', Mock(side_effect=AssertionError('audit must not draw')))
    first = {digest(i): attestation(i, context, []) for i in identities}
    second = {digest(i): attestation(i, prepare_context(context), []) for i in reversed(identities)}
    assert first == second
    selected = sum(value['level'] == FULL for value in first.values())
    assert 60 < selected < 150  # fixed IDs, approximately the requested 1%
    changed = validation_context({'mode': 'sampled', 'salt': 'different-fixed-salt'})
    assert any(replay_reasons(i, context) != replay_reasons(i, changed) for i in identities)


def test_shared_baselines_ignore_first_rule_and_counter_depth():
    p = Population(.2, (('c1', .1), ('c2', .1)), .5, .02, 12, 701)
    context = validation_context({'mode': 'sampled'})
    for strategy in ('honest', 'selfish'):
        ids = [condition_identity(p, 7, strategy, False, (), rule) for rule in shards.VARIANTS]
        assert len({digest(i) for i in ids}) == 1
        assert all(attestation(i, context, []) == attestation(ids[0], context, []) for i in ids)


def test_forced_strata_are_order_independent_and_cover_every_condition_type():
    populations = [Population(a, tuple((f'c{i}', total/m) for i in range(m)), gamma, rate, 10, seed)
        for a in (.15, .25, .35) for total in (.1, .3, .5) for m in (2, 3, 4, 5, 6)
        for gamma in (0., .5, 1.) for rate in (0., .005, .02) for seed in (701, 702)]
    policy = normalize_policy({'mode': 'sampled', 'sample_per_million': 0})
    first, second = {}, {}
    for p in populations: add_anchor(first, p, policy)
    for p in reversed(populations): add_anchor(second, p, policy)
    assert first == second and len(first) == 3*3*5*3*3
    context = validation_context(policy, first)
    for p in populations:
        if digest(asdict(p)) not in context['anchors'].values(): continue
        C = tuple(a for a, _ in p.candidates)
        for rule in shards.VARIANTS:
            for rep in (0, 5):
                for strategy, flagged, coalition in [('honest', False, ()), ('selfish', False, ()),
                    ('honest', True, C), ('selfish', True, C), *[('selfish', True, tuple(x for x in C if x != j)) for j in C]]:
                    identity = condition_identity(p, rep, strategy, flagged, coalition, rule)
                    assert replay_reasons(identity, context) == ['stratum_anchor']


@pytest.mark.parametrize('rule', shards.VARIANTS)
@pytest.mark.parametrize('rate', [0, .02])
def test_lightweight_accepts_native_full_validator_cases_and_does_not_replay(rule, rate, monkeypatch):
    p = Population(.2, (('c1', .05), ('c2', .15)), .5, rate, 100, 84)
    for strategy, flagged, C in [('honest', False, ()), ('selfish', False, ()),
                                  ('honest', True, ('c1', 'c2')), ('selfish', True, ('c1', 'c2')),
                                  ('selfish', True, ('c2',))]:
        raw = PersistentSimulation(p, strategy, flagged, C, rule, production=True).run()
        validate_run(raw, p, rule, 0, strategy, flagged, C)
        with monkeypatch.context() as context:
            context.setattr(CommonRandom, 'random', Mock(side_effect=AssertionError('lightweight cannot replay RNG')))
            validate_lightweight(raw, p, rule, 0, strategy, flagged, C)


@pytest.mark.parametrize('damage', ['seed', 'condition_id', 'owner', 'parent', 'height', 'accepted', 'payoff', 'nan', 'boundary', 'private', 'canonical'])
def test_lightweight_rejects_invalid_output(damage):
    p = Population(.2, (('c1', .1), ('c2', .1)), .5, .02, 30, 701)
    rule = Rule('petty'); C = ('c1', 'c2')
    raw = PersistentSimulation(p, 'selfish', True, C, rule, production=True).run()
    if damage == 'seed': raw['identity']['actual_seed'] += 1
    elif damage == 'condition_id': raw['condition_id'] = '0'*64
    elif damage == 'owner': raw['terminal']['canonical_blocks'][0]['owner_id'] = 'foreign'
    elif damage == 'parent': raw['terminal']['canonical_blocks'][0]['parent_id'] = 999999
    elif damage == 'height': raw['terminal']['canonical_blocks'][0]['height'] += 1
    elif damage == 'accepted': raw['actors']['target']['accepted'] += 1
    elif damage == 'payoff': raw['actors']['target']['payoff'] += .01
    elif damage == 'nan': raw['member_activations']['c1'] = float('nan')
    elif damage == 'boundary': raw['terminal']['boundary']['max_exposed_canonical_blocks'] += 1
    elif damage == 'private': raw['terminal']['private_states']['target']['private_block_count'] += 1
    else: raw['terminal']['canonical_chain'].pop()
    with pytest.raises(ValueError): validate_lightweight(raw, p, rule, 0, 'selfish', True, C)


def test_lightweight_and_full_attestations_enforced_by_readers():
    p = Population(.2, (('c1', .1), ('c2', .1)), .5, 0, 10, 701)
    rule = Rule('petty')
    raw = PersistentSimulation(p, 'honest', False, (), rule, production=True, repetition=2).run()
    context = validation_context({'mode': 'sampled', 'sample_per_million': 0})
    producer = digest(runtime_identity())
    risks = validate_lightweight(raw, p, rule, 2, 'honest', False, ())
    record = extract_validated(raw, producer, attestation(raw['identity'], context, risks))
    assert record['validation']['level'] == LIGHT
    validate_compact(record, p, rule, 2, 'honest', False, (), producer, context)
    with pytest.raises(ValueError): validate_compact(record, p, rule, 2, 'honest', False, (), producer)
    fake = copy.deepcopy(record); fake['validation']['level'] = FULL
    with pytest.raises(ValueError): validate_compact(fake, p, rule, 2, 'honest', False, (), producer, context)
    full = compact_run(raw, p, rule, 2, 'honest', False, (), producer)
    assert full['validation']['level'] == FULL
    validate_compact(full, p, rule, 2, 'honest', False, (), producer)
    with pytest.raises(ValueError): validate_compact(full, p, rule, 2, 'honest', False, (), producer, context)


def test_observed_risk_paths_force_full_replay_even_without_hash_or_anchor():
    p = Population(.2, (('c1', .1), ('c2', .1)), .5, 0, 10, 701)
    identity = condition_identity(p, 2, 'selfish', True, ('c1', 'c2'), Rule('selfish'))
    context = validation_context({'mode': 'sampled', 'sample_per_million': 0})
    for risk in ('simultaneous_selfish_reactions', 'cascading_selfish_reactions'):
        result = attestation(identity, context, [risk])
        assert result['level'] == FULL and result['replay_reasons'] == ['risk:'+risk]


def test_sampled_replay_failure_is_fatal_and_blocks_resume_and_merge(tmp_path, monkeypatch):
    shards.prepare_study(sampled_design(), tmp_path)
    monkeypatch.setattr(shards, 'validate_run', Mock(side_effect=ValueError('injected sampled replay failure')))
    with pytest.raises(ValueError, match='injected sampled replay failure'): shards.run_shard(tmp_path, 0, rep_end=5)
    with sqlite3.connect(tmp_path/'shard-00.sqlite3') as db:
        assert dict(db.execute('SELECT kind,COUNT(*) FROM records GROUP BY kind')) == {'validation_failure': 1}
    assert len(list((tmp_path/'validation_failures').glob('*.json'))) == 1
    monkeypatch.setattr(shards, 'PersistentSimulation', Mock(side_effect=AssertionError('must not retry')))
    with pytest.raises(ValueError, match='prior validation failure'): shards.run_shard(tmp_path, 0, rep_end=5)
    with pytest.raises(ValueError, match='prior validation failure'): shards.merge_shards(tmp_path, tmp_path/'bad.sqlite3', preliminary=True)


def test_full_sampled_science_identical_resume_and_immutable_policy(tmp_path, monkeypatch):
    sampled = sampled_design(); full = copy.deepcopy(sampled); full['validation_policy']['mode'] = 'full'
    sm = shards.prepare_study(sampled, tmp_path/'sampled'); fm = shards.prepare_study(full, tmp_path/'full')
    assert sm['plan_sha256'] == fm['plan_sha256'] and sm['scope'] == fm['scope']
    first = shards.run_shard(tmp_path/'sampled', 0, rep_end=5)
    second = shards.run_shard(tmp_path/'sampled', 0, rep_start=6)
    complete = shards.run_shard(tmp_path/'full', 0)
    sr, fr = records(tmp_path/'sampled'), records(tmp_path/'full')
    assert set(sr) == set(fr)
    for key in sr:
        assert {k: v for k, v in sr[key].items() if k != 'validation'} == {k: v for k, v in fr[key].items() if k != 'validation'}
    assert first['replayed_conditions']+second['replayed_conditions'] < complete['replayed_conditions']
    with sqlite3.connect(tmp_path/'sampled/shard-00.sqlite3') as a, sqlite3.connect(tmp_path/'full/shard-00.sqlite3') as b:
        def scientific(db):
            return {key: json.loads(zlib.decompress(body))['outputs'] for key, body in db.execute("SELECT id,body FROM records WHERE kind='task'")}
        assert scientific(a) == scientific(b)
    for change in ({'mode': 'full'}, {'salt': 'other'}, {'sample_per_million': 20000}):
        changed = copy.deepcopy(sampled); changed['validation_policy'].update(change)
        with pytest.raises(ValueError, match='different study design'): shards.prepare_study(changed, tmp_path/'sampled')
    monkeypatch.setattr(shards, 'PersistentSimulation', Mock(side_effect=AssertionError('resume must not mine')))
    monkeypatch.setattr(shards, 'validate_run', Mock(side_effect=AssertionError('resume must not replay')))
    assert shards.run_shard(tmp_path/'sampled', 0).get('mining_simulations_executed', 0) == 0
    shards.merge_shards(tmp_path/'sampled', tmp_path/'merged.sqlite3')
    shards.export_study(tmp_path/'sampled', tmp_path/'exports')


def test_old_contract_not_migrated_and_provenance_remains_strict(tmp_path):
    manifest = shards.prepare_study(sampled_design(), tmp_path)
    for field, value in [('layout', 'persistent-compact-shards-v2-1'), ('runtime', {'python': 'foreign', 'sources': {}})]:
        changed = {**manifest, field: value}
        changed['study_id'] = digest({k: v for k, v in changed.items() if k not in ('study_id', 'receipt_key_sha256')})
        atomic_json(tmp_path/'study.json', changed)
        with pytest.raises(ValueError): shards.load_manifest(tmp_path)


def test_resealed_wrong_validation_level_is_rejected_on_resume_and_merge(tmp_path, monkeypatch):
    manifest = shards.prepare_study(sampled_design(), tmp_path)
    shards.run_shard(tmp_path, 0)
    store = shards.ShardStore(tmp_path, manifest, 0)
    try:
        for key, blob in store.connection.execute("SELECT id,body FROM records WHERE kind='baseline'"):
            record = json.loads(zlib.decompress(blob))
            if record['validation']['level'] == LIGHT:
                record['validation']['level'] = FULL
                from punishment_sim.persistent_checkpoint import canonical_json
                import hashlib
                body = canonical_json(record).encode(); checksum = hashlib.sha256(body).hexdigest()
                with store.connection:
                    store.connection.execute("UPDATE records SET body=?,sha256=?,receipt=? WHERE kind='baseline' AND id=?",
                        (zlib.compress(body), checksum, store._receipt('baseline', key, checksum), key))
                break
        else: pytest.fail('fixture requires a lightweight baseline')
    finally: store.close()
    monkeypatch.setattr(shards, 'PersistentSimulation', Mock(side_effect=AssertionError('corruption must not mine')))
    with pytest.raises(ValueError, match='validation policy/level/selection mismatch'): shards.run_shard(tmp_path, 0)
    with pytest.raises(ValueError, match='validation policy/level/selection mismatch'): shards.merge_shards(tmp_path, tmp_path/'merged.sqlite3')


def test_sampling_policy_remains_inside_manifest_checksum(tmp_path):
    manifest = shards.prepare_study(sampled_design(), tmp_path)
    manifest['validation']['policy']['salt'] = 'tampered'
    atomic_json(tmp_path/'study.json', manifest)
    with pytest.raises(ValueError, match='study manifest checksum'): shards.load_manifest(tmp_path)


def test_resealed_manifest_cannot_omit_deterministic_coverage(tmp_path):
    manifest = shards.prepare_study(sampled_design(), tmp_path)
    assert manifest['validation']['anchors']
    manifest['validation']['anchors'] = {}
    manifest['study_id'] = digest({k: v for k, v in manifest.items() if k not in ('study_id', 'receipt_key_sha256')})
    atomic_json(tmp_path/'study.json', manifest)
    with pytest.raises(ValueError, match='validation coverage differs from plan'): shards.load_manifest(tmp_path)


def test_native_simultaneous_and_cascading_reactions_force_replay():
    p = Population(.3, (('c1', .25), ('c2', .25)), .5, .02, 300, 84)
    rule = Rule('selfish'); C = ('c1', 'c2')
    raw = PersistentSimulation(p, 'selfish', True, C, rule, production=True).run()
    risks = validate_lightweight(raw, p, rule, 0, 'selfish', True, C)
    assert set(risks) == {'simultaneous_selfish_reactions', 'cascading_selfish_reactions'}
    context = validation_context({'mode': 'sampled', 'sample_per_million': 0})
    assert attestation(raw['identity'], context, risks)['level'] == FULL
    validate_run(raw, p, rule, 0, 'selfish', True, C)
