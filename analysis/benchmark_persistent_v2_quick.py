"""Quick sampled-production throughput comparison: 16 workers, then 28.

--describe only plans; --run explicitly mines 1,152 conditions twice.
The full core plan supplies native identities AND the original validation anchors.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib
import json
import multiprocessing
from pathlib import Path
import shutil
import sqlite3
import tempfile
from time import perf_counter, process_time

from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import atomic_json, digest
from punishment_sim.persistent_study import required_conditions
from punishment_sim.persistent_v2 import Rule, condition_identity
from punishment_sim.persistent_v2_compact import runtime_identity
from punishment_sim.persistent_v2_shards import prepare_study, load_manifest, ShardStore, VARIANTS, _condition
from punishment_sim.persistent_v2_validation import FULL, prepare_context, replay_reasons
from .benchmark_persistent_v2_concurrency import TIMERS, condition_group

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT/'configs/persistent_v2_core_2to4_1pct_10rep.json'
SELECTION_SALT = 'persistent-v2-quick-concurrency-v1'
WORKERS = (16, 28)


def population(raw):
    return Population(**{**raw, 'candidates': tuple(tuple(c) for c in raw['candidates'])})


def select_jobs(directory, manifest):
    """One near-balanced and one skewed native population per (m, lambda)."""
    design = manifest['design']
    if (design['accepted_blocks'] != 30000 or design['repetitions'] != 10
            or design['validation_policy']['mode'] != 'sampled'
            or design['variants'] != [asdict(r) for r in VARIANTS]):
        raise ValueError('quick benchmark requires the native sampled core design')
    selected = {}
    with sqlite3.connect(f"file:{Path(directory)/'plan.sqlite3'}?mode=ro", uri=True) as db:
        for pid, body, owner in db.execute('SELECT population_key,body,owner FROM tasks'):
            task = json.loads(body)
            p = population(task['population'])
            powers = [h for _, h in p.candidates]
            ratio = max(powers)/min(powers)
            kind = 'balanced' if ratio <= 1.5+1e-12 else 'skewed' if ratio >= 4 else None
            if kind is None:
                continue
            key = (len(powers), p.natural_fork_rate, kind)
            rank = (digest([SELECTION_SALT, pid]), pid)
            if key not in selected or rank < selected[key][0]:
                selected[key] = (rank, {'population_id': pid, 'task': task, 'owner': owner,
                                       'composition': kind})
    expected = {(m, rate, kind) for m in (2, 3, 4) for rate in (0, .005, .02)
                for kind in ('balanced', 'skewed')}
    if set(selected) != expected:
        raise ValueError('core plan does not have the required quick coverage')
    jobs, ids, distribution, reasons = [], [], Counter(), Counter()
    context = prepare_context(manifest['validation'])
    rows = [selected[key][1] for key in sorted(selected)]
    for row in rows:
        p = population(row['task']['population'])
        conditions = required_conditions(row['task']['coalitions'])
        for rep in (0, 1):
            for rule_index, rule in enumerate(VARIANTS):
                # H/S0 are simulated once, alongside petty, exactly as in production.
                chosen = [c for c in conditions if c[1] or rule_index == 0]
                job = {**row, 'rule': asdict(rule), 'repetition': rep, 'conditions': chosen}
                jobs.append(job)
                for strategy, flagged, coalition in chosen:
                    identity = condition_identity(p, rep, strategy, flagged, coalition, rule)
                    ids.append(digest(identity))
                    distribution[condition_group(identity)] += 1
                    reasons.update(replay_reasons(identity, context))
    if len(ids) != len(set(ids)) or len(ids) != 1152:
        raise ValueError('unexpected quick condition inventory')
    # The same interleaved queue at both concurrencies; enough work units to avoid
    # limiting a 28-process pool to just the 18 selected populations.
    jobs.sort(key=lambda j: digest([SELECTION_SALT, j['population_id'], j['rule'], j['repetition']]))
    inventory = {'populations': rows, 'unique_conditions_per_trial': len(ids),
        'repetitions': [1, 2], 'fixed_work_units': len(jobs),
        'condition_ids_sha256': digest(sorted(ids)), 'distribution': dict(distribution),
        'core_plan_sha256': manifest['plan_sha256'], 'core_study_id': manifest['study_id'],
        'validation_context_sha256': digest(manifest['validation']),
        'core_anchor_populations': len(context.anchor_ids),
        'selected_anchor_populations': sum(r['population_id'] in context.anchor_ids for r in rows),
        'known_replay_reasons_before_mining': dict(reasons)}
    return jobs, inventory


def prepare_quick(directory):
    prepare_study(json.loads(CORE.read_text()), directory)
    manifest = load_manifest(directory)
    jobs, inventory = select_jobs(directory, manifest)
    return manifest, jobs, inventory


def _quick_worker(arguments):
    core, trial, index, manifest, job = arguments
    start_cpu = process_time()
    if runtime_identity() != manifest['runtime']:
        raise ValueError('quick worker source/runtime changed')
    directory = Path(trial)/f'unit-{index:03d}'
    directory.mkdir()
    (directory/'receipts').mkdir(mode=0o700)
    key = f"shard-{job['owner']:02d}.key"
    shutil.copyfile(Path(core)/'receipts'/key, directory/'receipts'/key)
    (directory/'receipts'/key).chmod(0o600)
    # Native identity, validation context, provenance and HMAC checks are intact.
    # Each benchmark unit has a separate store; it is not a production shard.
    store = ShardStore(directory, manifest, job['owner'])
    records = []
    try:
        p, rule = population(job['task']['population']), Rule(**job['rule'])
        for strategy, flagged, coalition in job['conditions']:
            record = _condition(store, p, rule, job['repetition'],
                (strategy, flagged, tuple(coalition)), False, lambda *args: None, {})
            if flagged:
                store.put('benchmark_condition', record['condition_id'], record)
            records.append((record['condition_id'], record['native_result_sha256'], record['validation']))
        return {'metrics': dict(store.metrics), 'cpu_seconds': process_time()-start_cpu, 'records': records}
    finally:
        store.close()


def summarize_trial(workers, wall, results, inventory):
    metrics, records = Counter(), []
    for result in results:
        metrics.update(result['metrics'])
        records.extend(result['records'])
    ids = [r[0] for r in records]
    if (len(ids) != len(set(ids)) or len(ids) != inventory['unique_conditions_per_trial']
            or digest(sorted(ids)) != inventory['condition_ids_sha256']
            or metrics['mining_simulations_executed'] != len(ids)):
        raise ValueError('quick trial changed or duplicated conditions')
    replayed = sum(r[2]['level'] == FULL for r in records)
    return {'workers': workers, 'unique_conditions': len(ids), 'wall_seconds': wall,
        'conditions_per_second': len(ids)/wall,
        'total_mining_seconds': metrics['mining_seconds'],
        'lightweight_validation_seconds': metrics['lightweight_validation_seconds'],
        'native_replay_seconds': metrics['sampled_replay_seconds'],
        'replay_count': replayed, 'replay_fraction': replayed/len(ids),
        'average_busy_cores': sum(r['cpu_seconds'] for r in results)/wall,
        'timings_summed_worker_seconds': {k: metrics[k] for k in TIMERS},
        'native_results_sha256': digest(sorted((r[0], r[1]) for r in records)),
        'validation_selections_sha256': digest(sorted((r[0], r[2]) for r in records))}


def print_trial(row):
    print(json.dumps({k: round(v, 4) if isinstance(v, float) else v
        for k, v in row.items() if k not in ('timings_summed_worker_seconds',
            'native_results_sha256', 'validation_selections_sha256')}), flush=True)


def print_result(report):
    if report['status'] != 'COMPLETE':
        raise ValueError('quick benchmark is not complete')
    rates = {r['workers']: r['conditions_per_second'] for r in report['trials']}
    if set(rates) != {16, 28} or len(report['trials']) != 2:
        raise ValueError('quick benchmark must contain exactly two trials')
    for workers in WORKERS:
        print(f'{workers} workers: {rates[workers]:.4f} conditions/sec', flush=True)
    ratio = rates[28]/rates[16]
    print(f'relative throughput: 28/16 = {ratio:.4f}x ({(ratio-1)*100:+.2f}%)', flush=True)
    if abs(ratio-1) <= .05:
        print('Within 5%: an optional reversed-order run can resolve the small difference.', flush=True)


def run_quick(destination, reverse=False):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    start = perf_counter()
    core = destination/'core_plan'
    manifest, jobs, inventory = prepare_quick(core)
    report = {'status': 'INCOMPLETE', 'validation_mode': 'sampled', 'inventory': inventory,
        'runtime': manifest['runtime'], 'validation': manifest['validation'],
        'benchmark_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'preparation_seconds_excluded': perf_counter()-start, 'trials': [], 'production_sweep': False}
    path = destination/'benchmark.json'
    atomic_json(path, report)
    try:
        for workers in reversed(WORKERS) if reverse else WORKERS:
            trial = destination/f'{workers}-workers'
            trial.mkdir()
            start = perf_counter()
            pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn'))
            try:
                results = list(pool.map(_quick_worker,
                    [(str(core), str(trial), i, manifest, job) for i, job in enumerate(jobs)]))
            finally:
                pool.shutdown(wait=True, cancel_futures=True)
            row = summarize_trial(workers, perf_counter()-start, results, inventory)
            if report['trials']:
                for key in ('native_results_sha256', 'validation_selections_sha256'):
                    if row[key] != report['trials'][0][key]:
                        raise ValueError(f'quick comparison changed {key}')
            report['trials'].append(row)
            atomic_json(path, report)
            print_trial(row)
        report['status'] = 'COMPLETE'
        atomic_json(path, report)
        print_result(report)
        return report
    except BaseException as exc:
        report.update(status='FAILED', error=str(exc))
        atomic_json(path, report)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--describe', action='store_true')
    action.add_argument('--run', action='store_true')
    action.add_argument('--result', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--reverse', action='store_true', help='Optional later comparison: 28, then 16; still only two trials')
    args = parser.parse_args()
    if args.result:
        report = json.loads(args.result.read_text())
        for row in report['trials']:
            print_trial(row)
        print_result(report)
    elif args.describe:
        with tempfile.TemporaryDirectory(prefix='persistent-v2-quick-plan-') as directory:
            _, _, inventory = prepare_quick(directory)
        print(json.dumps(inventory, indent=2))
    elif args.output is None:
        parser.error('--run requires a fresh --output directory')
    else:
        run_quick(args.output, args.reverse)


if __name__ == '__main__':
    main()
