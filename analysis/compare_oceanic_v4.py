"""Read-only input comparison; writes only to a separate comparison directory."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from analysis.plan_oceanic_v4_rerun import analytical_spec
from punishment_sim.research_sweep import generate_tasks
from punishment_sim.sharded_sweep import task_id
from punishment_sim.stage_b_validation import classify_margin, DEFAULT_EPSILON

METRICS=('effective','pipeline_winning','weak_joint','strict_joint')
PROVENANCE={'model_version','artifact_model_version','simulation_model_version','execution_provenance',
    'source_checkpoint_path','source_checkpoint_sha256','compatibility_rule'}


def read(path):
    with Path(path).open(newline='') as stream:return list(csv.DictReader(stream))


def write(path,rows):
    if not rows:raise ValueError(f'no rows for {path}')
    with Path(path).open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def key(r):return (r['configuration_id'],r['coalition'])


def environment(r):return tuple(float(r[x]) for x in ('target_hash_power','gamma','natural_fork_rate'))


def truth(value):
    if value not in ('True','False'):raise ValueError(f'invalid boolean {value!r}')
    return value=='True'


def indexed(rows,fields):
    out={tuple(r[f] for f in fields):r for r in rows}
    if len(out)!=len(rows):raise ValueError('duplicate input identities')
    return out


def classifications(coalitions,members):
    by_coal=defaultdict(list)
    for r in members:by_coal[key(r)].append(r)
    result={}
    for r in coalitions:
        ms=by_coal[key(r)];expected=set(json.loads(r['members']))
        if {m['member_id'] for m in ms}!=expected or len(ms)!=len(expected):raise ValueError('member coverage mismatch')
        if not expected:raise ValueError('comparison expects nonempty tested coalitions')
        baseline=[classify_margin(**{k:json.loads(m['baseline'])[v] for k,v in [('mean','mean'),('low','ci95_low'),('high','ci95_high')]}) for m in ms]
        deviation=[classify_margin(**{k:json.loads(m['deviation'])[v] for k,v in [('mean','mean'),('low','ci95_low'),('high','ci95_high')]}) for m in ms]
        eff=r['effectiveness_status']=='SUPPORTED'
        result[key(r)]={'effective':eff,'pipeline_winning':truth(r['winning']),
            'weak_joint':eff and all(x['weak_supported'] for x in baseline+deviation),
            'strict_joint':eff and all(x['strict_supported'] for x in baseline+deviation)}
    return result


def compare(old_dir,new_dir,output_dir,spec):
    old_dir,new_dir,out=map(lambda p:Path(p).resolve(),(old_dir,new_dir,output_dir))
    if old_dir==new_dir:raise ValueError('old/new sources must differ')
    if any(out==src or out in src.parents or src in out.parents for src in (old_dir,new_dir)):
        raise ValueError('comparison output must be separate and nonnested with inputs')
    tasks=generate_tasks(analytical_spec(spec))[0]
    expected_ids={task_id(t) for t in tasks}
    task_by_id={task_id(t):t for t in tasks}
    expected_pairs={(task_id(t),'|'.join(c)) for t in tasks for c in t.coalitions}
    expected_envs={ (t.population.target_hash_power,t.population.gamma,t.population.natural_fork_rate) for t in tasks}
    versions=('race-owner-oceanic-residual-v3','race-owner-oceanic-all-races-v4')
    data=[]
    for src,version in zip((old_dir,new_dir),versions):
        mining=read(src/'mining_configurations.csv');configs=indexed(mining,('configuration_id',))
        if {k[0] for k in configs}!=expected_ids or {r['model_version'] for r in mining}!={version}:raise ValueError('configuration scope/version mismatch')
        for row in mining:
            t=task_by_id[row['configuration_id']];p=t.population
            if environment(row)!=(p.target_hash_power,p.gamma,p.natural_fork_rate):raise ValueError('configuration environment mismatch')
            if json.loads(row['candidate_distribution'])!=dict(p.candidates):raise ValueError('composition mismatch')
            if int(row['repetitions'])!=spec['repetitions'] or int(row['accepted_blocks'])!=p.target_accepted_blocks:raise ValueError('stopping/repetition mismatch')
        coalitions=read(src/'coalition_results.csv');members=read(src/'member_credibility.csv')
        ci=indexed(coalitions,('configuration_id','coalition'));mi=indexed(members,('configuration_id','coalition','member_id'))
        if set(ci)!=expected_pairs or {environment(r) for r in coalitions}!=expected_envs:raise ValueError('coalition/environment coverage mismatch')
        data.append((ci,mi,classifications(coalitions,members)))
    if set(data[0][1])!=set(data[1][1]):raise ValueError('old/new member identities differ')
    # Numeric/scientific rows at lambda zero must agree exactly, excluding only provenance.
    zero_differences=[]
    for collection in (0,1):
        for identity,a in data[0][collection].items():
            if environment(a)[2]!=0:continue
            b=data[1][collection][identity]
            for field in (set(a)|set(b))-PROVENANCE:
                if a.get(field)!=b.get(field):zero_differences.append({'identity':list(identity),'field':field})
    rows=[]
    for env in sorted(expected_envs):
        row=dict(zip(('target_hash_power','gamma','natural_fork_rate'),env))
        for metric in METRICS:
            values=[]
            for label,(ci,mi,classes) in zip(('v3','v4'),data):
                candidates=[r for k,r in ci.items() if environment(r)==env and classes[k][metric]]
                minimum=min((float(r['active_hash_power']) for r in candidates),default=None)
                row[f'{label}_{metric}_exists']=bool(candidates)
                row[f'{label}_{metric}_min_power']=minimum
                row[f'{label}_{metric}_minimizers']=json.dumps(sorted([list(key(r)) for r in candidates if float(r['active_hash_power'])==minimum]))
                values.append((bool(candidates),minimum))
            row[f'{metric}_changed']=values[0]!=values[1]
        rows.append(row)
    summary=[]
    for rate in sorted({e[2] for e in expected_envs}):
        group=[r for r in rows if r['natural_fork_rate']==rate]
        for metric in METRICS:
            summary.append({'natural_fork_rate':rate,'metric':metric,'environments':len(group),
                'v3_feasible_environments':sum(r[f'v3_{metric}_exists'] for r in group),
                'v4_feasible_environments':sum(r[f'v4_{metric}_exists'] for r in group),
                'changed_classification_or_minimum':sum(r[f'{metric}_changed'] for r in group)})
    changes=[]
    for identity,a in data[0][0].items():
        b=data[1][0][identity]
        for metric in ('deterrence','punishment_reduction'):
            before=json.loads(a[metric])['mean'];after=json.loads(b[metric])['mean']
            changes.append({'configuration_id':identity[0],'coalition':identity[1],'member_id':'',
                'natural_fork_rate':environment(a)[2],'metric':metric,'v3_mean':before,'v4_mean':after,'delta':after-before})
    for identity,a in data[0][1].items():
        b=data[1][1][identity]
        for metric in ('baseline','deviation'):
            before=json.loads(a[metric])['mean'];after=json.loads(b[metric])['mean']
            changes.append({'configuration_id':identity[0],'coalition':identity[1],'member_id':identity[2],
                'natural_fork_rate':environment(a)[2],'metric':metric,'v3_mean':before,'v4_mean':after,'delta':after-before})
    equal_changes=[]
    pair_fields=('left_configuration_id','left_coalition','right_configuration_id','right_coalition','metric')
    old_equal=indexed(read(old_dir/'equal_hash_comparisons.csv'),pair_fields)
    new_equal=indexed(read(new_dir/'equal_hash_comparisons.csv'),pair_fields)
    if set(old_equal)!=set(new_equal):raise ValueError('equal-power comparison scope mismatch')
    for identity,a in old_equal.items():
        b=new_equal[identity]
        equal_changes.append({**dict(zip(pair_fields,identity)),
            'natural_fork_rate':float(a['natural_fork_rate']),
            'matched_active_hash_power':float(a['matched_active_hash_power']),
            'v3_difference':float(a['difference']),'v4_difference':float(b['difference']),
            'difference_delta':float(b['difference'])-float(a['difference']),
            'v3_status':a['status'],'v4_status':b['status'],'status_changed':a['status']!=b['status']})
        if float(a['natural_fork_rate'])==0 and any(a.get(f)!=b.get(f) for f in ('difference','ci95_low','ci95_high','status')):
            zero_differences.append({'identity':list(identity),'field':'equal_hash_comparison'})
    audit={'status':'PASS' if not zero_differences else 'ZERO_LAMBDA_MISMATCH',
        'environment_count':len(rows),'configuration_count':len(expected_ids),
        'zero_lambda_scientific_rows_equal':not zero_differences,'zero_lambda_differences':zero_differences,
        'credibility_epsilon':DEFAULT_EPSILON,
        'definitions':{'effective':'effectiveness_status=SUPPORTED','pipeline_winning':'existing winning field: effectiveness plus deviation credibility',
            'weak_joint':'effective plus existing epsilon-refined weak baseline and deviation credibility',
            'strict_joint':'effective plus existing epsilon-refined strict baseline and deviation credibility'},
        'inference':'descriptive cross-version deltas only; no paired cross-version confidence intervals',
        'positive_lambda_no_pipeline_winner_under_v4':not any(r['natural_fork_rate']>0 and r['v4_pipeline_winning_exists'] for r in rows)}
    out.mkdir(parents=True,exist_ok=True)
    write(out/'environment_feasibility_comparison.csv',rows);write(out/'lambda_feasibility_summary.csv',summary)
    write(out/'payoff_margin_changes.csv',changes)
    if equal_changes:write(out/'equal_power_composition_changes.csv',equal_changes)
    audit['equal_power_comparisons']=len(equal_changes)
    (out/'comparison_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    return audit


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--old-dir',required=True);p.add_argument('--new-dir',required=True)
    p.add_argument('--output-dir',required=True);p.add_argument('--config',required=True)
    a=p.parse_args();result=compare(a.old_dir,a.new_dir,a.output_dir,json.loads(Path(a.config).read_text()))
    print(json.dumps(result,indent=2))
    if result['status']!='PASS':raise SystemExit(1)
