"""Bounded post-fix CPU profile of the full condition boundary; local use only."""
import argparse
from collections import Counter
from contextlib import contextmanager
import cProfile
import json
from pathlib import Path
import pstats
import shutil
from time import process_time, perf_counter
from unittest.mock import patch

from .profile_persistent_v2_kernel import trajectory, ledger_shape, deadline, PhaseLimit, population
from punishment_sim import persistent_v2_shards as shards
from punishment_sim.persistent_v2 import PersistentSimulation, Rule
from punishment_sim.persistent_checkpoint import atomic_json, digest

STAGES = {'validate_lightweight':'lightweight', 'attestation':'selection', 'validate_run':'replay',
          'extract_validated':'extraction', 'validate_compact':'compact_validation'}


def measured(fn, times, key):
    cpu, wall = process_time(), perf_counter()
    try:
        return fn()
    finally:
        times[key] = {'cpu_seconds':process_time()-cpu, 'wall_seconds':perf_counter()-wall}


@contextmanager
def validation_timers(times):
    originals = {name:getattr(shards, name) for name in STAGES}
    def wrapper(name):
        return lambda *a, **k: measured(lambda:originals[name](*a, **k), times, STAGES[name])
    managers = [patch.object(shards, name, wrapper(name)) for name in STAGES]
    try:
        for manager in managers: manager.__enter__()
        yield
    finally:
        for manager in reversed(managers): manager.__exit__(None, None, None)


def profile_table(stats, blocks):
    total = sum(value[2] for value in stats.stats.values())
    return sorted([{'function':f'{Path(f).name}:{line}:{name}', 'calls':calls,
        'calls_per_accepted_block':calls/blocks, 'self_seconds':self_time,
        'inclusive_seconds':inclusive, 'self_percent':100*self_time/total}
        for (f,line,name),(_,calls,self_time,inclusive,_) in stats.stats.items()],
        key=lambda row:-row['self_seconds'])


def run(source_corpus, destination, *, total_seconds=900, phase_seconds=35, profiles=True):
    source_corpus, destination = Path(source_corpus), Path(destination)
    manifest = shards.load_manifest(source_corpus.parent/'core_plan')
    source = json.loads(source_corpus.read_text())
    if source['manifest'] != manifest: raise ValueError('corpus/manifest mismatch')
    destination.mkdir(parents=True, exist_ok=False)
    core = destination/'core_plan'; core.mkdir()
    for name in ('study.json','plan.sqlite3'):
        shutil.copy2(source_corpus.parent/'core_plan'/name, core/name)
    shutil.copytree(source_corpus.parent/'core_plan'/'receipts', core/'receipts')
    atomic_json(destination/'corpus.json', source)
    report = {'status':'INCOMPLETE','runtime':manifest['runtime'],'core_plan_sha256':manifest['plan_sha256'],
        'validation_context_sha256':digest(manifest['validation']), 'cases':[], 'profiles':{},
        'total_work_limit_seconds':total_seconds, 'trajectory_limit_seconds':phase_seconds,
        'production_sweep':False,'ssh':False,'xtra_access':False,'remote_job':False}
    stores, stats, profiled_blocks = {}, {}, Counter()
    stop = perf_counter()+total_seconds
    def budget(seconds): return max(.001,min(seconds,stop-perf_counter()))
    def profiled(key, fn, blocks):
        profiler = cProfile.Profile()
        value = profiler.runcall(fn)
        current = pstats.Stats(profiler)
        stats[key] = stats[key].add(current) if key in stats else current
        profiled_blocks[key] += blocks() if callable(blocks) else blocks
        stats[key].dump_stats(str(destination/(key+'.prof')))
        report['profiles'][key] = {'accepted_blocks':profiled_blocks[key],
            'functions':profile_table(stats[key],profiled_blocks[key])}
        return value
    try:
        for i,case in enumerate(source['cases']):
            if perf_counter() >= stop:
                report['unexecuted']=[c['condition_id'] for c in source['cases'][i:]]; break
            p=population(case['task']['population']); rule=Rule(**case['rule'])
            args=(p,case['strategy'],case['flagged'],tuple(case['coalition']),rule)
            if case['owner'] not in stores: stores[case['owner']]=shards.ShardStore(core,manifest,case['owner'])
            store=stores[case['owner']]
            row={k:case[k] for k in ('condition_id','rule','kind','composition')}
            row.update(cardinality=len(p.candidates), gamma=p.gamma, **{'lambda':p.natural_fork_rate},
                status='INCOMPLETE', times={})
            report['cases'].append(row); times=row['times']
            sim=raw=compact=None; phase='initialization'
            cpu0,wall0=process_time(),perf_counter()
            try:
                sim=measured(lambda:PersistentSimulation(*args,production=True),times,'initialization')
                phase='trajectory'
                with deadline(budget(phase_seconds)):
                    measured(lambda:trajectory(sim),times,phase)
                # Diagnostic-only O(blocks) count protects against materializing an
                # unbounded endpoint. Its measured cost is subtracted from total.
                row['shape']=measured(lambda:ledger_shape(sim),times,'diagnostic_shape')
                if row['shape']['terminal_path_entries']>50_000_000:
                    raise PhaseLimit('more than 50M terminal path entries')
                phase='terminal'
                with deadline(budget(90)):
                    raw=measured(sim.report,times,phase)
                phase='validation'
                with deadline(budget(90)), validation_timers(times):
                    compact=shards._validate_fresh(store,raw,p,rule,0,*args[1:4])
                phase='persistence'
                measured(lambda:store.put('boundary_profile_condition',case['condition_id'],compact),times,phase)
                row.update(native_result_sha256=compact['native_result_sha256'],validation=compact['validation'],
                    events=raw['events'],accepted_blocks=raw['accepted_blocks'])
                phase='cleanup'; cpu,wall=process_time(),perf_counter()
                del raw,sim; raw=sim=None
                times['cleanup']={'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall}
                row['total_condition']={'cpu_seconds':process_time()-cpu0-times['diagnostic_shape']['cpu_seconds'],
                    'wall_seconds':perf_counter()-wall0-times['diagnostic_shape']['wall_seconds']}
                row['status']='COMPLETE'
                # Separate instrumented repeat, excluded from all production CPU
                # timings; no replay is falsely attested and no profile is resumed.
                if profiles and case['profile']:
                    phase='instrumented_repeat'
                    other=PersistentSimulation(*args,production=True)
                    with deadline(budget(90)):
                        profiled('trajectory',lambda:trajectory(other),lambda:other.public_height)
                        other_raw=profiled('terminal',other.report,other.public_height)
                        assert digest(other_raw)==row['native_result_sha256']
                        def prof_wrapper(name,original):
                            return lambda *a,**k:profiled(STAGES[name],lambda:original(*a,**k),other.public_height)
                        managers=[patch.object(shards,name,prof_wrapper(name,getattr(shards,name))) for name in STAGES]
                        try:
                            for manager in managers: manager.__enter__()
                            other_compact=shards._validate_fresh(store,other_raw,p,rule,0,*args[1:4])
                        finally:
                            for manager in reversed(managers): manager.__exit__(None,None,None)
                        assert other_compact==compact
                    del other_raw,other,other_compact
            except PhaseLimit as exc:
                if row['status']=='COMPLETE': row['profile_censored']=str(exc)
                else: row.update(status='CENSORED',phase=phase,reason=str(exc))
            finally:
                del sim,raw,compact
                atomic_json(destination/'profile.json',report)
            print(f"boundary {i+1}/{len(source['cases'])} {row['kind']} {rule} {row['status']}",flush=True)
        report['status']='COMPLETE_WITH_CENSORING' if report.get('unexecuted') or any(c['status']!='COMPLETE' for c in report['cases']) else 'COMPLETE'
    except BaseException as exc:
        report.update(status='FAILED',error=repr(exc));raise
    finally:
        for store in stores.values(): store.close()
        atomic_json(destination/'profile.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-corpus',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--total-seconds',type=float,default=900)
    parser.add_argument('--phase-seconds',type=float,default=35)
    parser.add_argument('--no-profiles',action='store_true')
    args=parser.parse_args()
    run(args.source_corpus,args.output,total_seconds=args.total_seconds,phase_seconds=args.phase_seconds,profiles=not args.no_profiles)
