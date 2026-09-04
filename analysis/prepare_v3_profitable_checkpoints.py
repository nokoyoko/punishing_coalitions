#!/usr/bin/env python3
import csv,json,os
from dataclasses import asdict
from pathlib import Path
from punishment_sim.coalition import MODEL_VERSION,config_id
from punishment_sim.research_sweep import generate_tasks
root=Path(__file__).resolve().parents[1];srcroot=root/'results/research_sweep_stage_b_oceanic_v3';dstroot=root/'results/research_sweep_stage_b_oceanic_v3_profitable_core';dst=(dstroot/'checkpoints');dst.mkdir(parents=True,exist_ok=True)
spec=json.loads((root/'configs/research_sweep_stage_b_oceanic_v3_profitable_core.json').read_text());tasks,_,_=generate_tasks(spec)
with (srcroot/'mining_configurations.csv').open(newline='') as f:old=list(csv.DictReader(f))
def same(r,t):
 p=t.population;return r['model_version']==MODEL_VERSION and float(r['target_hash_power'])==p.target_hash_power and float(r['gamma'])==p.gamma and float(r['natural_fork_rate'])==p.natural_fork_rate and int(r['accepted_blocks'])==p.target_accepted_blocks and json.loads(r['candidate_distribution'])==dict(p.candidates)
mapping=[]
for t in tasks:
 cid=config_id(asdict(t.population));match=next((r for r in old if same(r,t)),None)
 if match and not (dst/f'{cid}.json').exists():os.link(srcroot/'checkpoints'/f"{match['configuration_id']}.json",dst/f'{cid}.json');mapping.append({'destination':cid,'source':match['configuration_id']})
audit={'model_version':MODEL_VERSION,'pre_v3_reuse':False,'v3_aggregate_checkpoints_reused':sum(1 for t in tasks if (dst/f'{config_id(asdict(t.population))}.json').exists()),'newly_linked':len(mapping),'total_populations':len(tasks),'mapping':mapping};(dstroot/'checkpoint_reuse_audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps({k:v for k,v in audit.items() if k!='mapping'},indent=2))
