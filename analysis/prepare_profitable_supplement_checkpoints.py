#!/usr/bin/env python3
"""Hard-link only behavior-identical corrected checkpoints into supplement."""
import json,os
from dataclasses import asdict
from pathlib import Path
from punishment_sim.coalition import MODEL_VERSION,config_id
from punishment_sim.research_sweep import generate_tasks

root=Path(__file__).resolve().parents[1]
spec=json.loads((root/'configs/research_sweep_stage_b_profitable_core_supplement.json').read_text())
assert spec['expected_model_version']==MODEL_VERSION
tasks,_,_=generate_tasks(spec); wanted={config_id(asdict(t.population)):t for t in tasks}
source=root/'results/research_sweep_stage_b_racefix/checkpoints'
dest=root/'results/research_sweep_stage_b_profitable_core_supplement/checkpoints';dest.mkdir(parents=True,exist_ok=True)
import csv
with (root/'results/research_sweep_stage_b_racefix/mining_configurations.csv').open(newline='') as f: old=list(csv.DictReader(f))
def same(row,t):
 p=t.population
 return (float(row['target_hash_power'])==p.target_hash_power and float(row['gamma'])==p.gamma and
  float(row['natural_fork_rate'])==p.natural_fork_rate and int(row['accepted_blocks'])==p.target_accepted_blocks and
  json.loads(row['candidate_distribution'])==dict(p.candidates) and row['model_version']==MODEL_VERSION)
linked=[];reuse=[]
for cid,t in sorted(wanted.items()):
 dst=dest/f'{cid}.json'
 if dst.exists():continue
 match=next((r for r in old if same(r,t)),None)
 if match:
  src=source/f"{match['configuration_id']}.json";os.link(src,dst);linked.append(cid);reuse.append({'destination_configuration_id':cid,'source_configuration_id':match['configuration_id']})
audit={'model_version':MODEL_VERSION,'source':str(source.relative_to(root)),'destination':str(dest.relative_to(root)),
 'requested_population_configurations':len(wanted),'reused_corrected_checkpoints_total':sum((dest/f'{x}.json').exists() for x in wanted),
 'newly_linked_this_run':len(linked),'remaining_new_checkpoints':len(wanted)-sum((dest/f'{x}.json').exists() for x in wanted),
 'pre_fix_reuse':False,'reuse_mapping':reuse}
(dest.parent/'checkpoint_reuse_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
print(json.dumps(audit,indent=2))
