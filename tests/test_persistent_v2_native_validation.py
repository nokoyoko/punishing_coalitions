"""Accepted/rejected witness parity and representation-only replay checks."""
from copy import deepcopy
from dataclasses import asdict
import hashlib

import pytest

from punishment_sim import persistent_v2_native as native
from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import PersistentSimulation, Rule
from punishment_sim.persistent_v2_compact import extract_validated
from punishment_sim.persistent_v2_dag import expand_fixture, validate_run as replay_dag
from punishment_sim.persistent_v2_validation import validate_lightweight, validation_context, attestation
from punishment_sim.persistent_v2_checkpoint import validate_run as python_replay

RULES = [Rule('petty'), *(Rule('counter_fork', k) for k in (1, 2, 3)), Rule('ignore'), Rule('selfish')]


@pytest.fixture(scope='module', autouse=True)
def compiled():
    from punishment_sim.build_native import build
    build()
    native._module = None
    native.load_extension()


def outcome(check, raw, p, rule):
    try:
        return 'accepted', sorted(check(raw, p, rule, 0, 'selfish', True, ('c1', 'c2')))
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError):
        return 'rejected', None


def leaves(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, (*path, key))
    elif isinstance(value, (list, tuple)):
        for key, child in enumerate(value):
            yield from leaves(child, (*path, key))
    else:
        yield path


@pytest.mark.parametrize('rule', RULES)
def test_native_validator_matches_reference_for_corrupted_and_accepted_mutations(rule):
    p = Population(.31, (('c1', .18), ('c2', .16)), .5, 1, 40, 84)
    original = PersistentSimulation(p, 'selfish', True, ('c1', 'c2'), rule, production=True).run()
    assert outcome(validate_lightweight, original, p, rule) == outcome(native.validate_lightweight, original, p, rule)
    paths = sorted(leaves(original), key=lambda path: hashlib.sha256(repr(path).encode()).digest())[:160]
    outcomes = set()
    for path in paths:
        for replacement in (None, False, 'corruption'):
            raw = deepcopy(original)
            target = raw
            for part in path[:-1]:
                if isinstance(target[part], tuple):
                    target[part] = list(target[part])
                target = target[part]
            target[path[-1]] = replacement
            expected = outcome(validate_lightweight, raw, p, rule)
            actual = outcome(native.validate_lightweight, raw, p, rule)
            assert actual == expected, (asdict(rule), path, replacement, expected, actual)
            outcomes.add(expected[0])
    assert outcomes == {'accepted', 'rejected'}
    raw = deepcopy(original)
    raw['unused_diagnostic'] = {'unicode': 'λ🪙', 'huge_integer': 2**100}
    raw['member_activations']['extra_counter'] = 2**100
    assert outcome(validate_lightweight, raw, p, rule) == outcome(native.validate_lightweight, raw, p, rule) == ('accepted', sorted(validate_lightweight(raw, p, rule, 0, 'selfish', True, ('c1', 'c2'))))
    raw['unused_diagnostic']['nonfinite'] = float('nan')
    assert outcome(validate_lightweight, raw, p, rule) == outcome(native.validate_lightweight, raw, p, rule) == ('rejected', None)


def test_reference_json_and_diagnostic_equality_edge_cases():
    p = Population(.31, (('c1', .18), ('c2', .16)), .5, .02, 40, 84)
    rule = Rule('petty')
    original = PersistentSimulation(p, 'selfish', True, ('c1', 'c2'), rule, production=True).run()
    raw = deepcopy(original)
    nested = raw['unused'] = {}
    for _ in range(300):
        nested['child'] = {}; nested = nested['child']
    nested['text'] = '\ud800surrogate\udfff'
    raw['selfish_reactions'] = [{'discovery_event': 1, 'decisions': 'λ🪙'},
                              {'discovery_event': 1.0, 'decisions': []}]
    assert outcome(validate_lightweight, raw, p, rule) == outcome(native.validate_lightweight, raw, p, rule) == (
        'accepted', ['cascading_selfish_reactions', 'simultaneous_selfish_reactions'])
    raw = deepcopy(original)
    batch = raw['publication_batches'][0]
    for bid in batch['blocks']:
        block = next(b for b in raw['terminal']['canonical_blocks']+raw['terminal']['frontier_blocks'] if b['id'] == bid)
        block['publication_kind'] = 2**60
    batch['kind'] = 2**60+1
    assert outcome(validate_lightweight, raw, p, rule) == outcome(native.validate_lightweight, raw, p, rule) == ('rejected', None)


@pytest.mark.parametrize('rule', RULES)
@pytest.mark.parametrize('strategy,flagged', [('honest', False), ('selfish', False), ('honest', True), ('selfish', True)])
def test_checked_native_dag_is_exact_and_independently_replayed(rule, strategy, flagged):
    p = Population(.31, (('c1', .18), ('c2', .16)), .5, .02, 120, 84)
    coalition = ('c1', 'c2') if flagged else ()
    reference = PersistentSimulation(p, strategy, flagged, coalition, rule, production=True).run()
    result = native.run(p, strategy, flagged, coalition, rule, _checked=True, _selector=lambda risks: True)
    assert expand_fixture(result.native) == reference
    assert result.compact_unattested['native_result_sha256'] == digest(reference)
    from analysis.persistent_v2_reference_witness import streamed_digest
    assert streamed_digest(result.native) == digest(reference)
    replay_dag(result.native, p, rule, 0, strategy, flagged, coalition)
    context = validation_context()
    record, times = native.execute(p, strategy, flagged, coalition, rule, producer='fixture', context=context)
    expected = extract_validated(reference, 'fixture', attestation(reference['identity'], context,
        validate_lightweight(reference, p, rule, 0, strategy, flagged, coalition)))
    assert record == expected
    assert times['replay_cpu_seconds'] >= 0


@pytest.mark.parametrize('rule', RULES)
def test_unselected_native_witness_is_not_materialized(rule):
    p = Population(.2, (('c1', .1), ('c2', .1)), .5, .02, 40, 84)
    result = native.run(p, 'honest', False, (), rule, _checked=True, _selector=lambda risks: False)
    assert result.native is None
    assert result.timings['raw_json_bytes'] == 0
    assert result.compact_unattested['native_result_sha256']


@pytest.mark.parametrize('field', ['terminal', 'reorganizations', 'rng', 'selfish_reactions'])
def test_independent_dag_replay_still_rejects_corruption(field):
    p = Population(.31, (('c1', .18), ('c2', .16)), .5, .02, 120, 84)
    rule = Rule('selfish')
    raw = native.run(p, 'selfish', True, ('c1', 'c2'), rule, _checked=True, _selector=lambda risks: True).native
    if field == 'terminal':
        raw[field]['alternative_branches'][0]['path']['__path__'][1] += 1
    elif field == 'reorganizations':
        raw[field][0]['removed']['__path__'][0] += 1
    elif field == 'rng':
        raw[field]['ties']['draw_count'] += 1
    else:
        raw[field].pop()
    with pytest.raises(ValueError):
        replay_dag(raw, p, rule, 0, 'selfish', True, ('c1', 'c2'))


@pytest.mark.parametrize('rule', RULES)
def test_native_replay_matches_python_on_accepted_and_corrupted_ledgers(rule):
    p = Population(.31, (('c1', .18), ('c2', .16)), .5, 1, 40, 84)
    original = PersistentSimulation(p, 'selfish', True, ('c1', 'c2'), rule, production=True).run()
    def accepts(fn, raw):
        try:
            fn(raw, p, rule, 0, 'selfish', True, ('c1', 'c2'))
            return True
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError):
            return False
    assert accepts(python_replay, original) and accepts(native.validate_replay, original)
    paths = sorted(leaves(original), key=lambda path: hashlib.sha256(repr(path).encode()).digest())[:160]
    for path in paths:
        for replacement in (None, False, 'corruption'):
            raw = deepcopy(original)
            target = raw
            for part in path[:-1]:
                if isinstance(target[part], tuple):
                    target[part] = list(target[part])
                target = target[part]
            target[path[-1]] = replacement
            assert accepts(native.validate_replay, raw) == accepts(python_replay, raw), (rule, path, replacement)


def test_selected_production_replay_stays_native_without_python_witness(monkeypatch):
    from unittest.mock import Mock
    from punishment_sim import persistent_v2_dag, persistent_v2_checkpoint
    monkeypatch.setattr(persistent_v2_dag, 'validate_run', Mock(side_effect=AssertionError('Python replay invoked')))
    monkeypatch.setattr(persistent_v2_checkpoint, 'validate_run', Mock(side_effect=AssertionError('Python replay invoked')))
    p = Population(.31, (('c1', .18), ('c2', .16)), .5, 1, 80, 84)
    record, timing = native.execute(p, 'selfish', True, ('c1', 'c2'), Rule('selfish'),
                                   producer='fixture', context=validation_context())
    assert record['validation']['replay_reasons'] == ['full_policy']
    assert timing['replay_implementation'] == 'native-independent-ledger-replay-v1'
    assert timing['replay_cpu_seconds'] >= 0 and timing['raw_json_bytes'] == 0
