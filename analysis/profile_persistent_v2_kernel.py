"""Bounded, real-plan kernel profiling; no production sweep or remote access."""
import argparse
import cProfile
from dataclasses import asdict
import json
from pathlib import Path
import platform
import pstats
import sqlite3
import signal
from contextlib import contextmanager
from time import perf_counter, process_time

from .benchmark_persistent_v2_quick import prepare_quick, population, ROOT
from punishment_sim.coalition import ExplicitSimulation
from punishment_sim.persistent_checkpoint import atomic_json, digest
from punishment_sim.persistent_v2 import PersistentSimulation, Rule, condition_identity
from punishment_sim.persistent_v2_shards import VARIANTS, ShardStore, _validate_fresh, load_manifest


def corpus(directory):
    manifest, _, inventory = prepare_quick(directory)
    rows = inventory['populations']
    # Include gamma=0 explicitly: it is rare in the analytically authorized core.
    candidates = []
    with sqlite3.connect(Path(directory)/'plan.sqlite3') as db:
        for pid, body, owner in db.execute('SELECT population_key,body,owner FROM tasks'):
            task = json.loads(body)
            if task['population']['gamma'] == 0:
                candidates.append((digest(['kernel-gamma-zero-v1', pid]),
                    {'population_id': pid, 'task': task, 'owner': owner, 'composition': 'gamma_zero_control'}))
    rows = rows + [min(candidates, key=lambda x: x[0])[1]]
    cases = {}
    def add(row, rule, strategy, flagged, C, label, profile=False):
        p = population(row['task']['population'])
        identity = condition_identity(p, 0, strategy, flagged, C, rule)
        key = digest(identity)
        previous = cases.get(key)
        cases[key] = {**row, 'identity': identity, 'condition_id': key,
            'rule': asdict(rule), 'strategy': strategy, 'flagged': flagged, 'coalition': list(C),
            'kind': label, 'profile': profile or bool(previous and previous['profile'])}
    for i, row in enumerate(rows):
        p = population(row['task']['population']); C = tuple(a for a, _ in p.candidates)
        add(row, VARIANTS[0], 'honest', False, (), 'H', i % 6 == 0)
        add(row, VARIANTS[0], 'selfish', False, (), 'S0', i % 6 == 0)
        for j, rule in enumerate(VARIANTS):
            add(row, rule, 'selfish', True, C, 'SC', i % 6 == j or i == 18)
            if i % 6 == j or i == 18:
                add(row, rule, 'honest', True, C, 'HF', True)
            if i in (0, 6, 12):
                for member in C:
                    add(row, rule, 'selfish', True, tuple(a for a in C if a != member),
                        'SC_leaveout', j == (i//6) and member == C[-1])
    return manifest, list(cases.values())


def timed(fn):
    wall, cpu = perf_counter(), process_time()
    value = fn()
    return value, {'wall_seconds': perf_counter()-wall, 'cpu_seconds': process_time()-cpu}


class PhaseLimit(BaseException):
    """Abort a diagnostic phase without attesting incomplete validation."""


@contextmanager
def deadline(seconds):
    def expired(*_):
        raise PhaseLimit(f"phase exceeded {seconds}s wall budget")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def trajectory(sim):
    # Same stopping/resource checks as TreeEngine.run; failures stay failures.
    while sim.public_height < sim.p.target_accepted_blocks:
        if sim.events >= sim.max_events:
            raise RuntimeError("INCOMPLETE_RESOURCE_LIMIT")
        sim.step()


def ledger_shape(sim):
    """Count terminal path expansion without materializing those paths."""
    distance = {None: 0}
    for bid, block in sim.blocks.items():
        distance[bid] = 0 if block.canonical else 1 + distance[block.parent_id]
    hidden = set(sim.blocks) - sim.public
    private_tips = hidden - {sim.blocks[b].parent_id for b in hidden}
    tips = (sim.public_tips - {sim.reference_tip}) | private_tips
    return {"blocks": len(sim.blocks), "terminal_branches": len(tips),
            "terminal_path_entries": sum(distance[b] for b in tips),
            "maximum_terminal_path": max((distance[b] for b in tips), default=0),
            "reorganizations": len(sim.reorganizations),
            "removed_block_entries": sum(len(r["removed"]) for r in sim.reorganizations)}


def function_table(stats, blocks):
    # Inclusive top-level timing is the measured profile envelope. cProfile on
    # CPython 3.13 can leave some time unattributed to individual self entries.
    total = sum(v[3] for k, v in stats.stats.items() if k[2] == 'trajectory')
    return sorted([{
        "function": f"{filename.replace(str(ROOT)+'/', '')}:{line}:{name}",
        "calls": calls, "calls_per_accepted_block": calls/blocks,
        "self_seconds": self_time, "inclusive_seconds": inclusive,
        "self_percent": 100*self_time/total,
        "inclusive_percent": 100*inclusive/total}
        for (filename, line, name), (_, calls, self_time, inclusive, _) in stats.stats.items()
    ], key=lambda row: -row["self_seconds"])


def run(directory, source_corpus=None, phase_seconds=20, max_path_entries=1_000_000,
        total_seconds=900, profile=True, compare=None, condition_ids=()):
    if phase_seconds <= 0 or total_seconds <= 0 or max_path_entries < 0:
        raise ValueError('positive time budgets and nonnegative path budget required')
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    if source_corpus:
        source = json.loads(Path(source_corpus).read_text())
        manifest, cases = source['manifest'], source['cases']
        # Read-only source plan; isolated profile stores use the same manifest/key.
        import shutil
        core = directory/'core_plan'; core.mkdir()
        source_core = Path(source_corpus).parent/'core_plan'
        if load_manifest(source_core) != manifest:
            raise ValueError('source corpus/manifest mismatch')
        for name in ('study.json', 'plan.sqlite3'):
            shutil.copy2(source_core/name, core/name)
        shutil.copytree(source_core/'receipts', core/'receipts')
    else:
        core = directory/'core_plan'
        manifest, cases = corpus(core)
    if condition_ids:
        selected = set(condition_ids)
        cases = [case for case in cases if case['condition_id'] in selected]
        if {case['condition_id'] for case in cases} != selected:
            raise ValueError('condition ID is outside the fixed core corpus')
    atomic_json(directory/'corpus.json', {'manifest': manifest, 'cases': cases})
    reference = json.loads(Path(compare).read_text()) if compare else {}
    expected = {r['condition_id']: r for r in reference.get('cases', []) if r['status'] == 'COMPLETE'}
    if reference.get('additional_original_outlier'):
        row = reference['additional_original_outlier']
        expected[row['condition_id']] = row
    report = {'status': 'INCOMPLETE', 'purpose': 'bounded local kernel profile',
        'python': platform.python_version(), 'platform': platform.platform(), 'runtime': manifest['runtime'],
        'cases': [], 'profiled_cases': 0, 'historical_comparisons': [],
        'phase_wall_limit_seconds': phase_seconds, 'total_work_wall_limit_seconds': total_seconds,
        'maximum_materialized_terminal_path_entries': max_path_entries,
        'production_sweep': False, 'ssh': False, 'xtra_access': False}
    stats = None
    profiled_blocks = profiled_events = 0
    stores = {}
    stop_at = perf_counter() + total_seconds
    def phase_budget(multiplier=1):
        return max(.001, min(phase_seconds*multiplier, stop_at-perf_counter()))
    try:
        for index, case in enumerate(cases):
            if perf_counter() >= stop_at:
                report['unexecuted_condition_ids'] = [c['condition_id'] for c in cases[index:]]
                break
            p = population(case['task']['population']); rule = Rule(**case['rule'])
            args = (p, case['strategy'], case['flagged'], tuple(case['coalition']), rule)
            row = {'condition_id': case['condition_id'], 'rule': asdict(rule), 'kind': case['kind'],
                'cardinality': len(p.candidates), 'lambda': p.natural_fork_rate, 'gamma': p.gamma,
                'attacker': p.target_hash_power, 'coalition_power': sum(h for _, h in p.candidates),
                'composition': case['composition'], 'status': 'INCOMPLETE'}
            report['cases'].append(row)
            sim = PersistentSimulation(*args, production=True)
            phase = 'trajectory'
            try:
                with deadline(phase_budget()):
                    _, row['trajectory'] = timed(lambda: trajectory(sim))
                row.update(events=sim.events, accepted_blocks=sim.public_height, ledger_shape=ledger_shape(sim))
                if profile and case['profile']:
                    phase = 'profiled_trajectory'
                    other = PersistentSimulation(*args, production=True)
                    profiler = cProfile.Profile()
                    with deadline(phase_budget(2)):
                        _, row['profiled_trajectory'] = timed(lambda: profiler.runcall(trajectory, other))
                    assert sim.blocks == other.blocks and sim.rng_snapshot() == other.rng_snapshot()
                    assert sim.reorganizations == other.reorganizations
                    current = pstats.Stats(profiler)
                    stats = current if stats is None else stats.add(current)
                    profiled_blocks += other.public_height; profiled_events += other.events
                    report['profiled_cases'] += 1
                    stats.dump_stats(str(directory/'trajectory.prof'))
                    report.update(profiled_accepted_blocks=profiled_blocks, profiled_events=profiled_events,
                        profile_total_seconds=stats.total_tt, functions=function_table(stats, profiled_blocks))
                    del other
                if row['ledger_shape']['terminal_path_entries'] > max_path_entries:
                    row.update(status='REPORT_CENSORED', reason='terminal expansion exceeds diagnostic budget')
                else:
                    phase = 'native_report'
                    with deadline(phase_budget()):
                        raw, row['native_report'] = timed(sim.report)
                    store = stores.get(case['owner'])
                    if store is None:
                        store = stores[case['owner']] = ShardStore(core, manifest, case['owner'])
                    before = dict(store.metrics)
                    phase = 'validation_and_extraction'
                    with deadline(phase_budget()):
                        compact, row['validation_and_extraction'] = timed(lambda: _validate_fresh(store, raw, p, rule, 0,
                            case['strategy'], case['flagged'], tuple(case['coalition'])))
                    _, row['persistence'] = timed(lambda: store.put('kernel_profile_condition', case['condition_id'], compact))
                    row.update(status='COMPLETE', validation=compact['validation'],
                        native_result_sha256=compact['native_result_sha256'],
                        phase_seconds={k: store.metrics[k]-before.get(k, 0) for k in store.metrics if k.endswith('_seconds')})
                    if row['condition_id'] in expected:
                        previous = expected[row['condition_id']]
                        for field in ('native_result_sha256', 'validation'):
                            if row[field] != previous[field]:
                                raise ValueError(f'exact reference mismatch: {field}')
                        row['exact_reference_match'] = True
                    del raw
                if rule.punishment_rule == 'petty' and case['kind'] in ('H', 'S0', 'SC'):
                    phase = 'historical_comparison'
                    with deadline(phase_budget()):
                        old, elapsed = timed(lambda: ExplicitSimulation(p, case['strategy'], case['flagged'], tuple(case['coalition'])).run())
                    total = row['trajectory']['cpu_seconds'] + row.get('native_report', {}).get('cpu_seconds', 0)
                    report['historical_comparisons'].append({'condition_id': case['condition_id'],
                        'kind': case['kind'], 'lambda': p.natural_fork_rate, 'historical': elapsed,
                        'persistent_v2_cpu_seconds': total, 'cpu_ratio_v2_over_v4': total/elapsed['cpu_seconds']})
                    del old
            except PhaseLimit as exc:
                row.update(status='PHASE_CENSORED', censored_phase=phase, reason=str(exc), events=sim.events,
                           accepted_blocks=sim.public_height)
            finally:
                del sim
                atomic_json(directory/'profile.json', report)
            print(f"profile {index+1}/{len(cases)} {rule} {case['kind']} m={len(p.candidates)} lambda={p.natural_fork_rate} {row['status']}", flush=True)
        report.update(status='COMPLETE_WITH_CENSORING' if report.get('unexecuted_condition_ids') or any(c['status'] != 'COMPLETE' for c in report['cases']) else 'COMPLETE')
        atomic_json(directory/'profile.json', report)
    except BaseException as exc:
        report.update(status='FAILED', error=repr(exc)); atomic_json(directory/'profile.json', report)
        raise
    finally:
        for store in stores.values(): store.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-corpus', type=Path)
    parser.add_argument('--phase-seconds', type=float, default=20)
    parser.add_argument('--max-path-entries', type=int, default=1_000_000)
    parser.add_argument('--total-seconds', type=float, default=900)
    parser.add_argument('--no-cprofile', action='store_true')
    parser.add_argument('--compare', type=Path, help='require matching native hashes and validation against a prior profile')
    parser.add_argument('--condition-id', action='append', default=[], help='restrict to a known member of the fixed corpus')
    args = parser.parse_args()
    run(args.output, args.source_corpus, args.phase_seconds, args.max_path_entries, args.total_seconds,
        not args.no_cprofile, args.compare, args.condition_id)


if __name__ == '__main__':
    main()
