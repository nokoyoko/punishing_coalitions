"""Fixed LOCAL 14-task 30,000-block benchmark; identical mining inputs to prior evidence.

Runs 1–5 then 6–10, verifies all 700 native hashes against prior compact records,
and separately times validation candidates on the 14 full-SC repetition-1 cases.
Never enumerates or executes the research grid; never reads remote data.
"""
from collections import Counter
import contextlib
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
from statistics import median,mean
import sys
import tempfile
from time import perf_counter
import zlib

from analysis.benchmark_persistent_v2_compact import specification
from analysis import _persistent_v2_compact_validation_reference as reference
from punishment_sim import persistent_v2_checkpoint as validation
from punishment_sim.persistent_checkpoint import canonical_json,digest,atomic_json
from punishment_sim.persistent_v2 import Rule
from punishment_sim.persistent_v2_compact import runtime_identity
from punishment_sim.persistent_v2_shards import prepare_study,run_shard,merge_shards,export_study,ShardStore,task_rows,task_analysis,task_key

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'results/persistent_v2_51pct_local_benchmark'
EVIDENCE=ROOT/'docs/persistent_v2_51pct_benchmark.json'
PHASES=('mining_seconds','native_validation_seconds','extraction_seconds','compact_validation_seconds','aggregation_seconds','serialization_write_seconds')


def scientific(value):
    if isinstance(value,dict):return {k:scientific(v) for k,v in value.items() if k not in ('analysis_status','analysis_repetitions','planned_repetitions')}
    if isinstance(value,list):return [scientific(v) for v in value]
    return value


def storage_probe(path,repetitions):
    with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as con:
        samples={kind:list(con.execute('SELECT body,sha256,receipt FROM records WHERE kind=?',(kind,)))
                 for kind in ('baseline','repetition','task','preliminary_task')}
        rows=dict(con.execute('SELECT kind,COUNT(*) FROM records GROUP BY kind'))
        sizes={kind:{'count':len(values),'compressed_min':min(map(lambda v:len(v[0]),values)),
                     'compressed_mean':mean(len(v[0]) for v in values),'compressed_max':max(len(v[0]) for v in values)}
               for kind,values in samples.items() if values}
    with tempfile.TemporaryDirectory(prefix='v2-phase-storage-') as tmp:
        packing=Path(tmp)/'packing.sqlite3'
        with sqlite3.connect(packing) as con:
            con.execute('CREATE TABLE records(kind TEXT,id TEXT,body BLOB,sha256 TEXT,receipt TEXT,PRIMARY KEY(kind,id)) WITHOUT ROWID')
            for task in range(1000):
                for kind,copies in (('task',1),('preliminary_task',1),('repetition',repetitions),('baseline',2*repetitions if task%6==0 else 0)):
                    if not samples[kind]:continue
                    for rep in range(copies):
                        row=samples[kind][(task*max(copies,1)+rep)%len(samples[kind])]
                        seed=hashlib.sha256(f'{task}:{kind}:{rep}'.encode()).hexdigest()
                        key=seed if kind=='baseline' else seed[:24]+(f':{rep}' if kind=='repetition' else '')
                        con.execute('INSERT INTO records VALUES (?,?,?,?,?)',(kind,key,*row))
        packed=packing.stat().st_size
    return {'rows':rows,'record_sizes':sizes,'database_bytes':path.stat().st_size,'bytes_per_1000_tasks':packed,
            'method':'actual compressed records in identical SQLite schema; exact ID lengths; shared baselines amortized over six variants; retained preliminary tasks included; no mining'}


def main():
    if OUTPUT.exists():raise ValueError('preserve benchmark evidence; output already exists')
    before=json.loads((ROOT/'docs/persistent_v2_compact_benchmark.json').read_text())
    expected_tasks={t['task_id']:t['scientific_outputs_sha256'] for t in before['tasks']}
    expected_conditions={}
    for m in (2,6):
        path=ROOT/f'results/persistent_v2_compact_local_benchmark/members-{m}/shard-00.sqlite3'
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as con:
            for kind,blob in con.execute("SELECT kind,body FROM records WHERE kind IN ('baseline','repetition')"):
                value=json.loads(zlib.decompress(blob))
                for record in ([value] if kind=='baseline' else value['conditions']):
                    expected_conditions[record['condition_id']]=record['native_result_sha256']
    evidence={'status':'INCOMPLETE','runtime':runtime_identity(),'purpose':'fixed local identical-input benchmark, no scientific inference',
              'repetitions':10,'horizon':30000,'studies':[],'validation_components':[],'verified_conditions':[],
              'production_sweep':False,'ssh':False,'xtra_access':False,'remote_job':False}
    for members in (2,6):
        directory=OUTPUT/f'members-{members}'
        manifest=prepare_study(specification(members),directory)
        study={'members':members,'scope':manifest['scope'],'phases':{},'scientific_outputs_match_prior':True}
        def observe(event,value):
            if event!='validated_condition':return
            raw,record=value['raw'],value['compact'];identity=raw['identity']
            assert record['native_result_sha256']==expected_conditions[record['condition_id']]
            evidence['verified_conditions'].append(record['condition_id'])
            if identity['repetition']==0 and identity['strategy']=='selfish' and identity['flagged'] and len(identity['active_coalition'])==members:
                p=next(t.population for t in task_rows(directory,manifest,0) if digest(t.population.__dict__)==digest(identity['population']))
                rule=Rule(**identity['rule']);args=(raw,p,rule,0,'selfish',True,tuple(identity['active_coalition']))
                measurements={}
                variants=[('reference',None),('unoptimized',frozenset()),('comparison',{'comparison'}),
                          ('reactions',{'reactions'}),('debug',{'debug'}),('metadata',{'metadata'}),
                          ('all',{'comparison','reactions','debug','metadata'})]
                # Interleave candidates to limit simple warm-up/order bias.
                samples={name:[] for name,_ in variants}
                for repeat in range(3):
                    for name,options in (variants if repeat%2==0 else reversed(variants)):
                        start=perf_counter()
                        if options is None:reference.validate_run(*args)
                        else:validation._validate_run(*args,optimizations=options)
                        samples[name].append(perf_counter()-start)
                measurements={name:{'median_seconds':median(values),'samples':values} for name,values in samples.items()}
                evidence['validation_components'].append({'members':members,'identity':identity,'timings':measurements})
                atomic_json(EVIDENCE,evidence)
        for phase,first,last in (('Phase I',1,5),('Phase II',6,10)):
            start=perf_counter();metrics=run_shard(directory,0,rep_start=first,rep_end=last,hook=observe);wall=perf_counter()-start
            preliminary=last==5
            storage=storage_probe(directory/'shard-00.sqlite3',last)
            start=perf_counter();merged=merge_shards(directory,directory/f'merged-{last}.sqlite3',preliminary=preliminary);merge_time=perf_counter()-start
            start=perf_counter();export=export_study(directory,directory/f'exports-{last}',preliminary=preliminary,include_repetitions=True);export_time=perf_counter()-start
            export_bytes={p.name:p.stat().st_size for p in (directory/f'exports-{last}').glob('*.csv')}
            lines=[]
            for p in (directory/f'exports-{last}').glob('*comparisons.csv'):
                with p.open('rb') as stream:
                    next(stream,None);lines.extend(len(line) for line in stream)
            study['phases'][phase]={'metrics':metrics,'wall_seconds_including_diagnostics':wall,'storage':storage,
                'merge':merged,'merge_seconds':merge_time,'exports':export,'export_seconds':export_time,'export_bytes':export_bytes,
                'max_comparison_csv_row_bytes':max(lines,default=0)}
            evidence['studies']=[*evidence['studies'][:(0 if members==2 else 1)],study]
            atomic_json(EVIDENCE,evidence)
            print(f'm={members} {phase}: '+', '.join(f'{p}={metrics.get(p,0):.3f}' for p in PHASES),flush=True)
        store=ShardStore(directory,manifest,0,readonly=True)
        try:
            for task in task_rows(directory,manifest,0):
                for v in manifest['design']['variants']:
                    rule=Rule(**v);result=task_analysis(store,task,rule,analyze_only=True)
                    assert digest(scientific(result))==expected_tasks[task_key(task,rule)]
        finally:store.close()
        study['resume']=run_shard(directory,0,analyze_only=True)
        assert study['resume'].get('mining_simulations_executed',0)==0
    assert len(evidence['verified_conditions'])==len(set(evidence['verified_conditions']))==700
    assert len(evidence['validation_components'])==14
    evidence.update(status='COMPLETE',peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))
    atomic_json(EVIDENCE,evidence)
    print(EVIDENCE,flush=True)


if __name__=='__main__':main()
