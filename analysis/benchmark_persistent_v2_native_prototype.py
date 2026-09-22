"""Bounded exact H/S0/petty Python/native comparison, never a production sweep."""
import argparse
from collections import Counter
import gc
import hashlib
import json
import os
from pathlib import Path
from time import process_time, perf_counter

from . import persistent_v2_native_prototype as native
from .profile_persistent_v2_boundary import measured, validation_timers
from .profile_persistent_v2_kernel import population, deadline
from punishment_sim import persistent_v2_shards as shards
from punishment_sim.persistent_checkpoint import atomic_json, canonical_json, digest
from punishment_sim.persistent_v2 import PersistentSimulation, Rule, condition_identity
from punishment_sim.persistent_v2_validation import FULL


LAYOUT='persistent-condition-kernel-benchmark-v1'


def benchmark_manifest(source,directory,backend,count):
    directory.mkdir()
    runtime={'reference_python':source['runtime'],'benchmark_backend':backend}
    unsigned={'layout':LAYOUT,'design':source['design'],'runtime':runtime,'validation':source['validation'],
        'source_study_id':source['study_id'],'source_plan_sha256':source['plan_sha256'],
        'benchmark_unique_conditions':count}
    manifest={**unsigned,'study_id':digest(unsigned),'receipt_key_sha256':{}}
    (directory/'receipts').mkdir(mode=0o700)
    for shard in range(source['design']['shard_count']):
        key=os.urandom(32);path=directory/'receipts'/f'shard-{shard:02d}.key'
        path.write_bytes(key);path.chmod(0o600)
        manifest['receipt_key_sha256'][str(shard)]=hashlib.sha256(key).hexdigest()
    # Deliberately NOT study.json, and the layout is rejected by production.
    atomic_json(directory/'benchmark_manifest.json',manifest)
    return manifest


def condition(backend,store,case,repetition):
    p=population(case['task']['population']);rule=Rule(**case['rule'])
    strategy,flagged,C=case['strategy'],case['flagged'],tuple(case['coalition'])
    args=(p,strategy,flagged,C,rule)
    times={};result=raw=record=None
    was_enabled=gc.isenabled();gc.collect();gc.disable()
    cpu0,wall0=process_time(),perf_counter()
    try:
        identity=condition_identity(p,repetition,strategy,flagged,C,rule)
        key=digest(identity)
        if backend=='python':
            raw=measured(lambda:PersistentSimulation(*args,repetition=repetition,production=True).run(),times,'generation')
            with validation_timers(times):
                record=shards._validate_fresh(store,raw,p,rule,repetition,strategy,flagged,C)
        else:
            result=measured(lambda:native.run(*args,repetition=repetition),times,'kernel_and_boundary')
            raw=result.native
            risks=measured(lambda:shards.validate_lightweight(raw,p,rule,repetition,strategy,flagged,C),times,'lightweight')
            validation=measured(lambda:shards.attestation(identity,store.validation,risks),times,'selection')
            if validation['level']==FULL:
                measured(lambda:shards.validate_run(raw,p,rule,repetition,strategy,flagged,C),times,'replay')
            record={**result.compact_unattested,'producer':store.producer,'validation':validation}
            measured(lambda:shards.validate_compact(record,p,rule,repetition,strategy,flagged,C,store.producer,store.validation),times,'compact_validation')
        # The native emitter does not get to assert its own checksum correctness.
        # This independent diagnostic check is excluded from the timed workload.
        actual=measured(lambda:digest(raw),times,'diagnostic_native_hash')
        if actual!=record['native_result_sha256']:
            raise ValueError('native emission/hash mismatch')
        measured(lambda:store.put('prototype_condition',key,record),times,'persistence')
        native_timing=result.timings if result else None
        # Explicit collection charges Python's cyclic engine cleanup to its own
        # condition, instead of letting it contaminate the next native trial.
        c,w=process_time(),perf_counter()
        del raw,result;raw=result=None;gc.collect()
        times['cleanup']={'cpu_seconds':process_time()-c,'wall_seconds':perf_counter()-w}
        total={'cpu_seconds':process_time()-cpu0-times['diagnostic_native_hash']['cpu_seconds'],
               'wall_seconds':perf_counter()-wall0-times['diagnostic_native_hash']['wall_seconds']}
        return record,{'times':times,'total':total,'native_detail':native_timing}
    finally:
        if was_enabled:gc.enable()


def run(source_corpus,destination,*,repetitions=3,total_seconds=900):
    if type(repetitions) is not int or not 1<=repetitions<=3:
        raise ValueError('bounded prototype benchmark supports 1..3 repetitions')
    source_corpus=Path(source_corpus);destination=Path(destination)
    source=json.loads(source_corpus.read_text());manifest=shards.load_manifest(source_corpus.parent/'core_plan')
    if manifest!=source['manifest']:raise ValueError('source/manifest mismatch')
    cases=[c for c in source['cases'] if c['kind'] in ('H','S0') or c['rule']['punishment_rule']=='petty']
    if len(cases)!=70:raise ValueError('expected fixed 70-condition H/S0/petty corpus')
    destination.mkdir(parents=True,exist_ok=False)
    producer=native.backend_identity()
    count=len(cases)*repetitions
    manifests={backend:benchmark_manifest(manifest,destination/backend,{'id':'python-reference'} if backend=='python' else producer,count)
               for backend in ('python','native')}
    stores={};report={'status':'INCOMPLETE','prototype':producer,'reference_runtime':manifest['runtime'],
        'conditions_per_backend':count,'repetitions':list(range(repetitions)), 'horizon':30000,
        'source_plan_sha256':manifest['plan_sha256'],'validation_context_sha256':digest(manifest['validation']),
        'records':[],'production_sweep':False,'ssh':False,'xtra_access':False,'remote_job':False}
    stop=perf_counter()+total_seconds
    try:
        for repetition in range(repetitions):
            for case in cases:
                if perf_counter()>=stop:raise TimeoutError('bounded prototype benchmark budget exhausted')
                i=len(report['records']);records,timings={},{}
                # Reverse paired order on alternating conditions; both execute
                # every native identity exactly once and use fresh stores.
                order=('python','native') if i%2==0 else ('native','python')
                for backend in order:
                    pair=(backend,case['owner'])
                    if pair not in stores:stores[pair]=shards.ShardStore(destination/backend,manifests[backend],case['owner'])
                    with deadline(max(.001,min(60,stop-perf_counter()))):
                        records[backend],timings[backend]=condition(backend,stores[pair],case,repetition)
                left={k:v for k,v in records['python'].items() if k!='producer'}
                right={k:v for k,v in records['native'].items() if k!='producer'}
                if left!=right:raise ValueError('exact Python/native scientific compact or attestation mismatch')
                row={'condition_id':left['condition_id'],'kind':case['kind'],'cardinality':len(case['task']['population']['candidates']),
                    'lambda':case['task']['population']['natural_fork_rate'],'gamma':case['task']['population']['gamma'],
                    'repetition':repetition,'owner':case['owner'],'native_result_sha256':left['native_result_sha256'],
                    'validation':left['validation'],'exact_match':True,**timings}
                report['records'].append(row)
                atomic_json(destination/'benchmark.json',report)
                print(f"native prototype {i+1}/{count} {case['kind']} m={row['cardinality']} lambda={row['lambda']} exact",flush=True)
        if native.backend_identity()!=producer:raise ValueError('prototype source/binary changed during benchmark')
        report['status']='COMPLETE'
        report['totals']={backend:{'cpu_seconds':sum(r[backend]['total']['cpu_seconds'] for r in report['records']),
            'wall_seconds':sum(r[backend]['total']['wall_seconds'] for r in report['records'])} for backend in ('python','native')}
        report['speedup']=report['totals']['python']['cpu_seconds']/report['totals']['native']['cpu_seconds']
    except BaseException as exc:
        report.update(status='FAILED',error=repr(exc));raise
    finally:
        for store in stores.values():store.close()
        atomic_json(destination/'benchmark.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',required=True)
    parser.add_argument('--source-corpus',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--total-seconds',type=float,default=900)
    args=parser.parse_args()
    run(args.source_corpus,args.output,repetitions=args.repetitions,total_seconds=args.total_seconds)
