"""Reference-memory limits cannot silently become successful paired timings."""
from copy import deepcopy

import pytest

from analysis.benchmark_persistent_v2_native import ReferenceMemoryLimit, summarize
from analysis.persistent_v2_reference_witness import streamed_digest
from punishment_sim.persistent_checkpoint import digest


def test_streaming_reference_hash_preserves_expansion_and_rejects_bad_ancestry():
    raw = {'terminal': {'canonical_blocks': [
        {'id': 1, 'parent_id': None}, {'id': 2, 'parent_id': 1}, {'id': 3, 'parent_id': 1}],
        'frontier_blocks': []}, 'forward': {'__path__': [2, 0, True]},
        'reverse': {'__path__': [2, 0, False]}, 'empty': {'__path__': [1, 1, True]},
        'ordinary': {'tuple': (1, 2), 'unicode': 'λ🪙', 'float': -0.0}}
    expected = {**raw, 'forward': [1, 2], 'reverse': [2, 1], 'empty': []}
    assert streamed_digest(raw) == digest(expected)
    invalid = deepcopy(raw)
    invalid['forward']['__path__'][1] = 3
    with pytest.raises(ValueError, match='ancestor'):
        streamed_digest(invalid)


def test_incomplete_report_never_reports_a_successful_speedup():
    result = summarize({'status': 'FAILED', 'verification': [], 'records': []})
    assert 'speedup' not in result and result['paired_conditions'] == 0
    failure = ReferenceMemoryLimit({'terminal_path_entries': 250_000_001}, {'simulation': {'cpu_seconds': 7}})
    assert failure.shape['terminal_path_entries'] == 250_000_001
    assert failure.times['simulation']['cpu_seconds'] == 7
