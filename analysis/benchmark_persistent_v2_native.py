"""Bounded sequential native/Python comparison of actual sampled core conditions.

All required conditions for 19 deterministic core populations: 608 planned per
backend. Memory-limited Python references remain explicitly identified and are
checked using independent Python DAG replay and a streaming legacy-hash oracle.
No concurrency study, remote access, production dispatch or duration projection.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import gc
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import process_time, perf_counter

from .benchmark_persistent_v2_native_prototype import benchmark_manifest
from .profile_persistent_v2_boundary import measured, validation_timers
from .profile_persistent_v2_kernel import corpus, population, trajectory, ledger_shape
from punishment_sim import persistent_v2_native as native
from punishment_sim import persistent_v2_shards as shards
from punishment_sim.persistent_checkpoint import atomic_json, digest
from punishment_sim.persistent_study import required_conditions
from punishment_sim.persistent_v2 import PersistentSimulation, Rule, condition_identity
from punishment_sim.persistent_v2_validation import attestation, FULL, prepare_context

ROOT = Path(__file__).resolve().parents[1]
PATH_LIMIT = 250_000_000


class ReferenceMemoryLimit(RuntimeError):
    def __init__(self, shape, times):
        super().__init__('Python reference expanded-path safety bound exceeded; no successful timing')
        self.shape, self.times = shape, times


def inventory(source_cases):
    populations = {case['population_id']: case for case in source_cases}
    result = []
    for row in populations.values():
        p = population(row['task']['population'])
        for rule_index, rule in enumerate(shards.VARIANTS):
            for strategy, flagged, coalition in required_conditions(row['task']['coalitions']):
                if not flagged and rule_index:
                    continue
                identity = condition_identity(p, 0, strategy, flagged, coalition, rule)
                kind = ('H' if strategy == 'honest' else 'S0') if not flagged else (
                    'HF' if strategy == 'honest' else 'SC' if len(coalition) == len(p.candidates) else 'SC_leaveout')
                result.append({**row, 'rule': asdict(rule), 'strategy': strategy, 'flagged': flagged,
                    'coalition': list(coalition), 'kind': kind, 'condition_id': digest(identity), 'identity': identity})
    if len(result) != 608 or len({c['condition_id'] for c in result}) != 608:
        raise ValueError('expected 608 distinct actual core conditions')
    return result


def source_goldens():
    evidence = json.loads((ROOT/'docs/persistent_v2_condition_profile.json').read_text())
    # Recorded results are admissible only while every mining/serializer source
    # is byte-identical. Control-plane/validation/backend changes are separate.
    for name in ('coalition', 'persistent', 'persistent_checkpoint', 'persistent_v2',
                 'persistent_v2_policies', 'persistent_v2_index', 'persistent_v2_terminal',
                 'ostracism', 'selfish_counter', 'selfish_strategy'):
        current = hashlib.sha256((ROOT/'punishment_sim'/(name+'.py')).read_bytes()).hexdigest()
        if current != evidence['runtime']['sources'][name]:
            raise ValueError('frozen scientific reference source changed: '+name)
    return {row['condition_id']: row for row in evidence['cases'] if row['status'] == 'COMPLETE'}


def verify_large_reference(manifest, case):
    """Independent Python replay/hash oracle without expanded path storage."""
    from .persistent_v2_reference_witness import streamed_digest, shape
    from punishment_sim.persistent_v2_dag import validate_run as python_replay
    from punishment_sim.persistent_v2_compact import validate_compact
    p = population(case['task']['population'])
    rule = Rule(**case['rule'])
    context = prepare_context(manifest['validation'])
    validation = None
    def select(risks):
        nonlocal validation
        validation = attestation(case['identity'], context, risks)
        # Capture is diagnostic. Actual production selection is recorded above.
        return True
    result = native.run(p, case['strategy'], case['flagged'], tuple(case['coalition']), rule,
                        _checked=True, _selector=select)
    times = {}
    args = (result.native, p, rule, 0, case['strategy'], case['flagged'], tuple(case['coalition']))
    measured(lambda: python_replay(*args), times, 'independent_python_dag_replay')
    expected = measured(lambda: streamed_digest(result.native), times, 'independent_python_legacy_hash')
    if expected != result.compact_unattested['native_result_sha256']:
        raise ValueError('independent streamed legacy hash mismatch: '+case['condition_id'])
    record = {**result.compact_unattested, 'producer': 'bounded-equivalence-fixture', 'validation': validation}
    validate_compact(record, p, rule, 0, case['strategy'], case['flagged'], tuple(case['coalition']),
                     record['producer'], context)
    return {'condition_id': case['condition_id'], 'native_result_sha256': expected, 'validation': validation,
            'exact_reference_match': True, 'reference': 'independent Python DAG replay and streamed legacy hash',
            'shape': shape(result.native), 'diagnostic_times': times, 'native_metrics': result.timings}


def verify(manifest, source_cases, report, destination):
    golden = source_goldens()
    report['verification'] = []
    for index, case in enumerate(source_cases):
        if case['condition_id'] not in golden:
            print('verify memory-bounded Python oracle '+case['condition_id'], flush=True)
            report['verification'].append(verify_large_reference(manifest, case))
            atomic_json(destination/'benchmark.json', report)
            gc.collect()
            continue
        p = population(case['task']['population'])
        rule = Rule(**case['rule'])
        record, detail = native.execute(p, case['strategy'], case['flagged'], tuple(case['coalition']), rule,
            producer='bounded-equivalence-fixture', context=manifest['validation'])
        expected = golden[case['condition_id']]
        if record['native_result_sha256'] != expected['native_result_sha256'] or record['validation'] != expected['validation']:
            raise ValueError('real-core frozen reference mismatch: '+case['condition_id'])
        report['verification'].append({'condition_id': case['condition_id'],
            'native_result_sha256': record['native_result_sha256'], 'validation': record['validation'],
            'native_metrics': detail, 'exact_reference_match': True})
        atomic_json(destination/'benchmark.json', report)
        print(f"verify {len(report['verification'])}/230 {case['kind']} {rule} exact", flush=True)
        gc.collect()
    if len(report['verification']) != 230:
        raise ValueError('incomplete 230-condition real-core equivalence pass')


def one(backend, store, case, *, path_limit=PATH_LIMIT):
    p = population(case['task']['population'])
    rule = Rule(**case['rule'])
    strategy, flagged, coalition = case['strategy'], case['flagged'], tuple(case['coalition'])
    times, detail, shape = {}, None, None
    sim = raw = None
    was_enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    cpu, wall = process_time(), perf_counter()
    try:
        if backend == 'python':
            sim = measured(lambda: PersistentSimulation(p, strategy, flagged, coalition, rule, production=True), times, 'initialization')
            measured(lambda: trajectory(sim), times, 'simulation')
            shape = measured(lambda: ledger_shape(sim), times, 'diagnostic_shape')
            if shape['terminal_path_entries'] > path_limit:
                raise ReferenceMemoryLimit(shape, times)
            raw = measured(sim.report, times, 'terminal')
            with validation_timers(times):
                record = shards._validate_fresh(store, raw, p, rule, 0, strategy, flagged, coalition)
        else:
            record, detail = measured(lambda: native.execute(p, strategy, flagged, coalition, rule,
                producer=store.producer, context=store.validation), times, 'native_pipeline')
        measured(lambda: store.put('backend_benchmark_condition', case['condition_id'], record), times, 'persistence')
        c, w = process_time(), perf_counter()
        del raw, sim
        raw = sim = None
        gc.collect()
        times['cleanup'] = {'cpu_seconds': process_time()-c, 'wall_seconds': perf_counter()-w}
        diagnostic = times.get('diagnostic_shape', {'cpu_seconds': 0, 'wall_seconds': 0})
        total = {'cpu_seconds': process_time()-cpu-diagnostic['cpu_seconds'],
                 'wall_seconds': perf_counter()-wall-diagnostic['wall_seconds']}
        return record, {'stages': times, 'native_metrics': detail, 'shape': shape, 'total': total}
    finally:
        if was_enabled:
            gc.enable()


def run(destination, *, verify_only=False):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    manifest, source_cases = corpus(destination/'core_plan')
    cases = inventory(source_cases)
    atomic_json(destination/'corpus.json', {'manifest': manifest, 'cases': cases, 'verification_cases': source_cases})
    producer = native.backend_identity()
    report = {'status': 'VERIFYING', 'planned_conditions_per_backend': len(cases), 'horizon': 30000,
        'analysis_sources': {name: hashlib.sha256((ROOT/'analysis'/name).read_bytes()).hexdigest()
            for name in ('benchmark_persistent_v2_native.py', 'persistent_v2_reference_witness.py',
                         'profile_persistent_v2_kernel.py', 'profile_persistent_v2_boundary.py',
                         'benchmark_persistent_v2_native_prototype.py')},
        'platform': platform.platform(), 'python_version': platform.python_version(),
        'repetitions': [0], 'native_runtime': producer, 'python_runtime': manifest['runtime'],
        'source_plan_sha256': manifest['plan_sha256'], 'validation_context_sha256': digest(manifest['validation']),
        'condition_inventory_sha256': digest([case['condition_id'] for case in cases]),
        'condition_inventory': [{'condition_id': c['condition_id'], 'kind': c['kind'], 'rule': c['rule'],
            'owner': c['owner'], 'population_id': c['population_id']} for c in cases],
        'records': [], 'unpaired_native': [], 'production_sweep': False, 'ssh': False, 'xtra_access': False, 'remote_job': False}
    stores = {}
    try:
        verify(manifest, source_cases, report, destination)
        verified = {r['condition_id']: r for r in report['verification']}
        report['status'] = 'VERIFIED'
        if verify_only:
            return report
        manifests = {backend: benchmark_manifest(manifest, destination/backend,
            {'id': 'python-reference'} if backend == 'python' else producer, len(cases)) for backend in ('python', 'native')}
        report['status'] = 'BENCHMARKING'
        for index, case in enumerate(cases):
            records, times = {}, {}
            reference_limit = None
            known = verified.get(case['condition_id'], {})
            if known.get('shape', {}).get('terminal_path_entries', 0) > PATH_LIMIT:
                reference_limit = {'shape': known['shape'], 'reason': 'expanded Python reference exceeds memory bound'}
            print(f"start {index+1}/{len(cases)} {case['condition_id']}", flush=True)
            for backend in (('python', 'native') if index % 2 == 0 else ('native', 'python')):
                if backend == 'python' and reference_limit is not None:
                    continue
                key = (backend, case['owner'])
                if key not in stores:
                    stores[key] = shards.ShardStore(destination/backend, manifests[backend], case['owner'])
                try:
                    records[backend], times[backend] = one(backend, stores[key], case)
                except ReferenceMemoryLimit as exc:
                    reference_limit = {'shape': exc.shape, 'partial_times': exc.times, 'reason': str(exc)}
            if reference_limit is not None:
                if 'shape' not in known:
                    gc.collect()
                    known = verify_large_reference(manifest, case)
                    report['verification'].append(known)
                if (records['native']['native_result_sha256'] != known['native_result_sha256']
                        or records['native']['validation'] != known['validation']):
                    raise ValueError('memory-bounded reference mismatch')
                report['unpaired_native'].append({'condition_id': case['condition_id'], 'kind': case['kind'],
                    'rule': case['rule'], 'native': times['native'], 'reference_limit': reference_limit,
                    'native_result_sha256': known['native_result_sha256'], 'validation': records['native']['validation'],
                    'exact_reference_match': True})
                atomic_json(destination/'benchmark.json', report)
                print('native complete; Python legacy end-to-end timing unavailable under memory bound', flush=True)
                continue
            left, right = ({k:v for k,v in records[b].items() if k != 'producer'} for b in ('python', 'native'))
            if left != right:
                raise ValueError('exact native-result/compact/attestation mismatch: '+case['condition_id'])
            p = population(case['task']['population'])
            rule = case['rule']['punishment_rule']
            category = 'shared_baseline' if case['kind'] in ('H', 'S0') else rule + (
                '_k'+str(case['rule']['counter_fork_k']) if rule == 'counter_fork' else '')
            report['records'].append({'condition_id': case['condition_id'], 'kind': case['kind'],
                'rule': category, 'cardinality': len(p.candidates), 'lambda': p.natural_fork_rate,
                'gamma': p.gamma, 'composition': case['composition'], 'owner': case['owner'],
                'native_result_sha256': left['native_result_sha256'], 'validation': left['validation'],
                'exact_match': True, **times})
            atomic_json(destination/'benchmark.json', report)
            py = times['python']['total']['cpu_seconds']
            cpp = times['native']['total']['cpu_seconds']
            print(f'paired {index+1}/{len(cases)} {category} {case["kind"]}: Python {py:.3f}s native {cpp:.3f}s {py/cpp:.2f}x exact', flush=True)
        if native.backend_identity() != producer:
            raise ValueError('native source/binary changed during benchmark')
        report['status'] = 'COMPLETE_WITH_REFERENCE_LIMITS' if report['unpaired_native'] else 'COMPLETE'
        report['totals'] = {backend: {clock: sum(row[backend]['total'][clock] for row in report['records'])
            for clock in ('cpu_seconds', 'wall_seconds')} for backend in ('python', 'native')}
        report['speedup'] = report['totals']['python']['cpu_seconds']/report['totals']['native']['cpu_seconds']
        all_rows = report['records']+report['unpaired_native']
        report['completed_conditions'] = {'python': len(report['records']), 'native': len(all_rows)}
        report['speedup_scope'] = 'completed paired conditions only; memory-limited Python references excluded explicitly'
        report['replay_count'] = sum('replay_cpu_seconds' in r['native']['native_metrics'] for r in all_rows)
        report['replay_fraction'] = report['replay_count']/len(all_rows)
        report['native_total_cpu_seconds_including_unpaired'] = sum(r['native']['total']['cpu_seconds'] for r in all_rows)
    except BaseException as exc:
        report.update(status='FAILED', error=repr(exc))
        raise
    finally:
        for store in stores.values():
            store.close()
        atomic_json(destination/'benchmark.json', report)
    return report


def summarize(report):
    """Read-only summary; incomplete runs never acquire a speedup attestation."""
    result = {'status': report['status'], 'verified_conditions': len(report.get('verification', [])),
              'paired_conditions': len(report['records'])}
    if report['status'] not in ('COMPLETE', 'COMPLETE_WITH_REFERENCE_LIMITS'):
        return result
    rows = report['records']
    def aggregate(items):
        seconds = {b: sum(r[b]['total']['cpu_seconds'] for r in items) for b in ('python', 'native')}
        return {'conditions': len(items), **seconds, 'speedup': seconds['python']/seconds['native']}
    result.update(aggregate(rows))
    result['cpu_seconds_per_condition'] = {b: result[b]/len(rows) for b in ('python', 'native')}
    result['replay_count'] = report['replay_count']
    result['replay_fraction'] = report['replay_fraction']
    result['completed_conditions'] = report['completed_conditions']
    result['speedup_scope'] = report['speedup_scope']
    result['native_total_cpu_seconds_including_unpaired'] = report['native_total_cpu_seconds_including_unpaired']
    result['reference_limited_condition_ids'] = [r['condition_id'] for r in report['unpaired_native']]
    result['by'] = {axis: {str(value): aggregate([r for r in rows if r[axis] == value])
        for value in sorted({r[axis] for r in rows})} for axis in ('rule', 'cardinality', 'lambda', 'kind')}
    result['python_stages'] = {key: sum(r['python']['stages'].get(key, {}).get('cpu_seconds', 0) for r in rows)
        for key in ('initialization', 'simulation', 'terminal', 'lightweight', 'selection', 'replay',
                    'extraction', 'compact_validation', 'persistence', 'cleanup')}
    result['native_stages'] = {key: sum(r['native']['native_metrics'].get(key, 0) for r in rows)
        for key in ('prepare_cpu_seconds', 'native_simulation_cpu_seconds', 'native_emission_cpu_seconds',
                    'native_lightweight_cpu_seconds', 'boundary_decode_cpu_seconds', 'replay_cpu_seconds',
                    'compact_validation_cpu_seconds')}
    for key in ('persistence', 'cleanup'):
        result['native_stages'][key+'_cpu_seconds'] = sum(r['native']['stages'][key]['cpu_seconds'] for r in rows)
    result['replay_reasons'] = dict(Counter(reason for r in rows for reason in r['validation']['replay_reasons']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--result', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--wall-seconds', type=int, default=1800)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.result:
        print(json.dumps(summarize(json.loads(args.result.read_text())), indent=2))
        return
    if args.output is None:
        parser.error('--run requires --output')
    if not 1 <= args.wall_seconds <= 3600:
        parser.error('wall limit must be 1..3600 seconds')
    if args.worker:
        run(args.output, verify_only=args.verify_only)
    else:
        # An independent parent enforces the bound even while C++ holds the GIL.
        try:
            subprocess.run([sys.executable, '-m', 'analysis.benchmark_persistent_v2_native',
                *sys.argv[1:], '--worker'], check=True, timeout=args.wall_seconds)
        except subprocess.TimeoutExpired:
            path = args.output/'benchmark.json'
            if path.exists():
                report = json.loads(path.read_text())
                if report['status'] not in ('COMPLETE', 'COMPLETE_WITH_REFERENCE_LIMITS'):
                    report.update(status='TIMED_OUT', error='external wall-clock limit reached')
                    atomic_json(path, report)
            raise


if __name__ == '__main__':
    main()
