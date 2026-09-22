"""Bounded, matched local petty-v4 / v2 old serializer / v2 current comparison."""
import argparse
import gc
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from .profile_persistent_v2_kernel import deadline, population, timed
from punishment_sim import persistent_v2
from punishment_sim.coalition import ExplicitSimulation
from punishment_sim.persistent import PersistentSimulation as TreeEngine
from punishment_sim.persistent_checkpoint import atomic_json, digest
from punishment_sim.persistent_v2_shards import load_manifest


def run(source_corpus, output):
    source_corpus, output = Path(source_corpus), Path(output)
    if output.exists():
        raise ValueError('comparison output already exists')
    source = json.loads(source_corpus.read_text())
    if source['manifest'] != load_manifest(source_corpus.parent / 'core_plan'):
        raise ValueError('source manifest mismatch')
    cases = [c for c in source['cases'] if c['rule']['punishment_rule'] == 'petty'
             and c['kind'] in ('H', 'S0', 'SC')]
    if len(cases) != 57:
        raise ValueError('expected fixed 57-condition matched corpus')
    report = {'status': 'INCOMPLETE', 'runtime': source['manifest']['runtime'],
              'source_plan_sha256': source['manifest']['plan_sha256'],
              'horizon': 30000, 'records': [], 'production_sweep': False,
              'ssh': False, 'xtra_access': False, 'remote_job': False,
              'clock': 'process CPU: construction, trajectory, native report; excludes cleanup/validation/persistence'}
    backends = ('petty_v4', 'persistent_v2_before', 'persistent_v2_after')
    stop = perf_counter() + 180
    try:
        for i, case in enumerate(cases):
            p = population(case['task']['population'])
            args = (p, case['strategy'], case['flagged'], tuple(case['coalition']))
            row = {k: case[k] for k in ('condition_id', 'kind')}
            row.update(cardinality=len(p.candidates), **{'lambda': p.natural_fork_rate})
            hashes = {}
            for backend in backends[i % 3:] + backends[:i % 3]:
                gc.collect()
                enabled = gc.isenabled()
                gc.disable()
                try:
                    with deadline(max(.001, min(20, stop - perf_counter()))):
                        if backend == 'petty_v4':
                            raw, row[backend] = timed(lambda: ExplicitSimulation(*args).run())
                        else:
                            serializer = (TreeEngine.terminal_state if backend.endswith('before')
                                          else persistent_v2.base_terminal_state)
                            with patch.object(persistent_v2, 'base_terminal_state', serializer):
                                raw, row[backend] = timed(lambda: persistent_v2.PersistentSimulation(
                                    *args, persistent_v2.Rule('petty'), production=True).run())
                            hashes[backend] = digest(raw)
                        del raw
                finally:
                    gc.collect()
                    if enabled:
                        gc.enable()
            if len(set(hashes.values())) != 1:
                raise ValueError('before/after serializer changed native output')
            row.update(native_result_sha256=next(iter(hashes.values())), exact_serializer_match=True)
            report['records'].append(row)
            atomic_json(output, report)
            print(f'matched petty {i + 1}/{len(cases)} exact serializer', flush=True)
        report['status'] = 'COMPLETE'
    except BaseException as exc:
        report.update(status='FAILED', error=repr(exc))
        raise
    finally:
        atomic_json(output, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source_corpus, args.output)
