"""Structural scope only: never reads checkpoints or invokes mining."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from punishment_sim.coalition import config_id
from punishment_sim.research_sweep import generate_tasks
from punishment_sim.theory import vanilla_selfish_mining_profitable


def analytical_spec(spec):
    """Resolve authorization from grids/formula only, without result files."""
    grid=spec['composition']
    resolved={k:v for k,v in spec.items() if k not in {'authorized_environment_file','authorization_rule'}}
    resolved['authorized_environment_triplets']=[(a,g,r) for a in grid['target_hash']
        for g in grid['gamma'] for r in grid['natural_fork_rate']
        if vanilla_selfish_mining_profitable(a,g)]
    return resolved


def plan(old_spec, new_spec):
    mutable={'stage','expected_model_version'}
    if {k:v for k,v in old_spec.items() if k not in mutable} != {k:v for k,v in new_spec.items() if k not in mutable}:
        raise ValueError('scientific or execution specification changed beyond stage/model metadata')
    if old_spec.get('expected_model_version')!='race-owner-oceanic-residual-v3' or new_spec.get('expected_model_version')!='race-owner-oceanic-all-races-v4':
        raise ValueError('expected explicit v3 to v4 correction specifications')
    tasks,_,_=generate_tasks(analytical_spec(new_spec))
    old_tasks,_,_=generate_tasks(analytical_spec(old_spec))
    records=lambda ts: sorted((config_id(asdict(t.population)),asdict(t)) for t in ts)
    if records(tasks)!=records(old_tasks): raise ValueError('task identities or compositions changed')
    counts=Counter(); simulations=Counter(); cardinalities=Counter(); environments=set()
    for task in tasks:
        p=task.population
        if not vanilla_selfish_mining_profitable(p.target_hash_power,p.gamma):
            raise ValueError('task outside analytical Eyal-Sirer admission')
        rate=p.natural_fork_rate; counts[rate]+=1
        cardinalities[(rate,len(p.candidates))]+=1
        environments.add((p.target_hash_power,p.gamma,rate))
        conditions={('honest',False,()),('selfish',False,())}
        for coalition in task.coalitions:
            conditions.update([('honest',bool(coalition),coalition),('selfish',bool(coalition),coalition)])
            conditions.update(('selfish',bool(remaining),remaining)
                for member in coalition for remaining in [tuple(x for x in coalition if x!=member)])
        simulations[rate]+=len(conditions)*int(new_spec['repetitions'])
    grid=new_spec['composition']
    authorized={(float(a),float(g),float(r)) for a in grid['target_hash'] for g in grid['gamma']
                for r in grid['natural_fork_rate'] if vanilla_selfish_mining_profitable(a,g)}
    if environments!=authorized: raise ValueError('authorization does not match complete analytical domain')
    groups=[]
    for rate in sorted(counts):
        groups.append({'natural_fork_rate':rate,'top_level_configurations':counts[rate],
            'mining_simulations':simulations[rate],
            'accepted_block_work_units':simulations[rate]*new_spec['accepted_blocks'],
            'by_cardinality':{str(k):cardinalities[(rate,k)] for k in grid['systematic']['member_counts']}})
    return {'scope_basis':'local definitions only; no production checkpoint validation or execution',
        'task_population_and_design_sha256':hashlib.sha256(json.dumps(records(tasks),sort_keys=True).encode()).hexdigest(),
        'authorized_environment_count':len(environments),'top_level_configurations':len(tasks),
        'repetitions':new_spec['repetitions'],'accepted_blocks':new_spec['accepted_blocks'],
        'by_lambda':groups,'zero_lambda_configurations':counts[0],
        'positive_lambda_configurations':sum(v for k,v in counts.items() if k>0),
        'represented_mining_simulations':sum(simulations.values()),
        'future_positive_lambda_mining_simulations':sum(v for k,v in simulations.items() if k>0),
        'zero_lambda_mining_simulations_eligible_for_reuse':simulations[0],
        'conditions_per_full_k_member_population':'H, S0, HF(C), SC(C), S(C minus j) for each of k members; (4+k)*repetitions',
        'work_note':'accepted-block target times simulations; not elapsed time or exact discovery count'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-config',required=True);parser.add_argument('--new-config',required=True)
    parser.add_argument('--output')
    args=parser.parse_args()
    report=plan(json.loads(Path(args.old_config).read_text()),json.loads(Path(args.new_config).read_text()))
    text=json.dumps(report,indent=2)+'\n'
    if args.output: Path(args.output).write_text(text)
    print(text,end='')


if __name__=='__main__': main()
