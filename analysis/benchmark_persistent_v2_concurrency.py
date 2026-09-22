"""Controlled local-host throughput experiment; never SSHs or launches a research grid.

--describe enumerates only. --run is explicit and uses a fixed bounded workload.
Trials keep identical populations, conditions, seeds and work units, varying only
concurrent worker processes and the validation policy under comparison.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
from statistics import median
import tempfile
from time import perf_counter, process_time

from punishment_sim.persistent_checkpoint import atomic_json, canonical_json, digest
from punishment_sim.persistent_v2_shards import prepare_study, run_shard
from punishment_sim.persistent_v2_compact import runtime_identity
from punishment_sim.persistent_v2_validation import normalize_policy, FULL

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'configs/persistent_v2_concurrency_benchmark.json'
TIMERS = ('mining_seconds', 'lightweight_validation_seconds', 'sampled_replay_seconds',
          'full_replay_seconds', 'extraction_seconds', 'compact_validation_seconds',
          'aggregation_seconds', 'serialization_write_seconds')


def condition_group(identity):
    p = identity['population']
    if not identity['flagged']:
        rule, k, kind = 'shared_baseline', None, 'H' if identity['strategy'] == 'honest' else 'S0'
    else:
        rule, k = identity['rule']['punishment_rule'], identity['rule']['counter_fork_k']
        kind = 'HF' if identity['strategy'] == 'honest' else 'SC' if len(identity['active_coalition']) == len(p['candidates']) else 'SC_leaveout'
    return canonical_json([rule, k, len(p['candidates']), p['natural_fork_rate'], p['gamma'], p['target_hash_power'], kind])


def _worker(arguments):
    directory, shard, rep_end = arguments
    distribution, replay_distribution, reasons = Counter(), Counter(), Counter()
    native, selections = [], []
    def observe(event, value):
        if event != 'validated_condition':
            return
        record = value['compact']
        group = condition_group(record['identity'])
        distribution[group] += 1
        replay_distribution[group] += record['validation']['level'] == FULL
        reasons.update(record['validation']['replay_reasons'])
        native.append((record['condition_id'], record['native_result_sha256']))
        selections.append((record['condition_id'], record['validation']))
    start_cpu = process_time()
    metrics = run_shard(directory, shard, rep_end=rep_end, hook=observe)
    return {'metrics': metrics, 'cpu_seconds': process_time()-start_cpu,
            'distribution': dict(distribution), 'replayed_distribution': dict(replay_distribution),
            'replay_reasons': dict(reasons), 'native': native, 'selections': selections}


def describe(design, rep_end):
    if type(rep_end) is not int or not 1 <= rep_end <= design['repetitions']:
        raise ValueError('invalid benchmark repetition range')
    with tempfile.TemporaryDirectory(prefix='persistent-v2-benchmark-plan-') as temporary:
        manifest = prepare_study(design, temporary)
    count = manifest['scope']['after_reuse']*rep_end//design['repetitions']
    return {'scope': manifest['scope'], 'plan_sha256': manifest['plan_sha256'],
            'benchmark_repetitions': rep_end, 'unique_conditions_per_trial': count,
            'fixed_work_units': design['shard_count'], 'anchor_populations': len(set(manifest['validation']['anchors'].values())),
            'mining_launched': False}


def run_benchmark(design, destination, workers=(8, 16, 24, 28), modes=('full', 'sampled'), trials=1, rep_end=5):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('benchmark destination exists; no cached/resumed timing trials')
    if not workers or any(type(n) is not int or n < 1 for n in workers) or len(set(workers)) != len(workers):
        raise ValueError('distinct positive worker counts required')
    if not modes or any(mode not in ('full', 'sampled') for mode in modes) or len(set(modes)) != len(modes):
        raise ValueError('distinct supported validation modes required')
    if type(trials) is not int or trials < 1:
        raise ValueError('positive trial count required')
    inventory = describe(design, rep_end)
    if max(workers) > design['shard_count']:
        raise ValueError('fixed work units must be at least the maximum concurrency')
    destination.mkdir(parents=True)
    logical = os.cpu_count()
    affinity = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else logical
    evidence = {'status': 'INCOMPLETE', 'runtime': runtime_identity(), 'design': design,
                'benchmark_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'inventory': inventory, 'host': {'platform': platform.platform(), 'logical_cpus': logical,
                                              'affinity_cpus': affinity},
                'trials': [], 'production_sweep': False,
                'notes': ['Wall time includes worker startup, manifest checks, scheduling and checkpoint commits; planning excluded.',
                          'CPU seconds are summed worker process CPU time. Average busy cores is CPU/wall; no linear scaling assumed.',
                          'Identical fixed work units and native-result hashes are required across trials.',
                          'Forced stratum coverage may be denser in this bounded workload than in the research grid; actual replay fractions are reported.']}
    report = destination/'benchmark.json'
    atomic_json(report, evidence)
    expected_native, selections_by_mode = None, {}
    try:
        for repeat in range(trials):
            # Alternate direction and policy order to expose order/warm-cache effects.
            counts = list(workers) if repeat % 2 == 0 else list(reversed(workers))
            policy_modes = list(modes) if repeat % 2 == 0 else list(reversed(modes))
            for count in counts:
                for mode in policy_modes:
                    spec = json.loads(canonical_json(design))
                    spec['validation_policy'] = normalize_policy({**spec.get('validation_policy', {}), 'mode': mode})
                    directory = destination/f'trial-{repeat+1:02d}-{mode}-{count:02d}-workers'
                    plan_start = perf_counter()
                    manifest = prepare_study(spec, directory)
                    plan_seconds = perf_counter()-plan_start
                    assert manifest['plan_sha256'] == inventory['plan_sha256']
                    start = perf_counter()
                    with ProcessPoolExecutor(max_workers=count, mp_context=multiprocessing.get_context('spawn')) as pool:
                        results = list(pool.map(_worker, [(str(directory), shard, rep_end) for shard in range(spec['shard_count'])]))
                    wall = perf_counter()-start
                    metrics, distribution, replay_distribution, reasons = Counter(), Counter(), Counter(), Counter()
                    native, selections = [], []
                    for item in results:
                        metrics.update({k: item['metrics'].get(k, 0) for k in (*TIMERS, 'mining_simulations_executed', 'replayed_conditions', 'lightweight_only_conditions')})
                        distribution.update(item['distribution']); replay_distribution.update(item['replayed_distribution'])
                        reasons.update(item['replay_reasons']); native.extend(item['native']); selections.extend(item['selections'])
                    completed = metrics['mining_simulations_executed']
                    assert completed == inventory['unique_conditions_per_trial'] == len(native) == len({key for key, _ in native})
                    native_hash, selection_hash = digest(sorted(native)), digest(sorted(selections))
                    if expected_native is None:
                        expected_native = native_hash
                    assert native_hash == expected_native, 'scientific results changed across benchmark trials'
                    if mode in selections_by_mode:
                        assert selections_by_mode[mode] == selection_hash, 'validation selection changed with concurrency/order'
                    selections_by_mode[mode] = selection_hash
                    cpu = sum(item['cpu_seconds'] for item in results)
                    row = {'trial': repeat+1, 'workers': count, 'validation_mode': mode, 'study_id': manifest['study_id'],
                           'conditions_completed': completed, 'wall_seconds': wall, 'conditions_per_second': completed/wall,
                           'planning_seconds_excluded': plan_seconds, 'worker_cpu_seconds': cpu, 'average_busy_cores': cpu/wall,
                           'worker_capacity_utilization_percent': 100*cpu/(wall*count),
                           'logical_cpu_utilization_percent': 100*cpu/(wall*affinity) if affinity else None,
                           'timings_summed_worker_seconds': {k: metrics[k] for k in TIMERS},
                           'replayed_conditions': metrics['replayed_conditions'], 'lightweight_only_conditions': metrics['lightweight_only_conditions'],
                           'replay_fraction': metrics['replayed_conditions']/completed, 'replay_reasons': dict(reasons),
                           'native_results_sha256': native_hash, 'validation_selections_sha256': selection_hash,
                           'distribution_key': ['rule', 'k', 'cardinality', 'lambda', 'gamma', 'target_power', 'condition_type'],
                           'distribution': dict(distribution), 'replayed_distribution': dict(replay_distribution)}
                    evidence['trials'].append(row)
                    atomic_json(report, evidence)
                    print(json.dumps({k: row[k] for k in ('trial', 'workers', 'validation_mode', 'conditions_completed', 'wall_seconds', 'conditions_per_second', 'replay_fraction')}), flush=True)
        evidence['summary'] = [{'workers': count, 'validation_mode': mode,
            'median_conditions_per_second': median(t['conditions_per_second'] for t in evidence['trials'] if t['workers'] == count and t['validation_mode'] == mode)}
            for count in workers for mode in modes]
        evidence['status'] = 'COMPLETE'
        atomic_json(report, evidence)
        return evidence
    except BaseException as exc:
        evidence.update(status='FAILED', error_type=type(exc).__name__, error=str(exc))
        atomic_json(report, evidence)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--describe', action='store_true')
    action.add_argument('--run', action='store_true')
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--workers', nargs='+', type=int, default=[8, 16, 24, 28])
    parser.add_argument('--modes', nargs='+', choices=['full', 'sampled'], default=['full', 'sampled'])
    parser.add_argument('--trials', type=int, default=1)
    parser.add_argument('--rep-end', type=int, default=5)
    args = parser.parse_args()
    spec = json.loads(args.config.read_text())
    if args.describe:
        print(json.dumps(describe(spec, args.rep_end), indent=2))
    else:
        if args.output is None:
            parser.error('--run requires a fresh --output directory')
        run_benchmark(spec, args.output, args.workers, args.modes, args.trials, args.rep_end)


if __name__ == '__main__':
    main()
