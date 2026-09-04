#!/usr/bin/env python3
import argparse,csv,json,math,statistics
from collections import defaultdict,Counter
from pathlib import Path
from analysis.stage_b_racefix import read_csv,write_csv
parser=argparse.ArgumentParser()
parser.add_argument('--root',default='results/research_sweep_stage_b_oceanic_v3')
args=parser.parse_args()
ROOT=Path(args.root);OUT=ROOT/'analysis_tables';OUT.mkdir(exist_ok=True)
configs={r['configuration_id']:r for r in read_csv(ROOT/'mining_configurations.csv')};coal={(r['configuration_id'],r['coalition']):r for r in read_csv(ROOT/'coalition_results.csv')};reps=defaultdict(list)
for r in read_csv(ROOT/'repetition_metrics.csv'):reps[r['configuration_id']].append(float(r['punishment_reduction'])-float(r['deterrence']))
env=defaultdict(list)
sensitivity=[]
for cid,v in reps.items():
 c=configs[cid];mu=statistics.mean(v);se=statistics.stdev(v)/math.sqrt(len(v));lo=mu-2.045*se;hi=mu+2.045*se;st='SELFISH_PROFITABLE' if lo>0 else 'SELFISH_NOT_PROFITABLE' if hi<0 else 'SELFISH_PROFITABILITY_INCONCLUSIVE';x=coal[(cid,'c1')]
 item={'configuration_id':cid,'target_hash_power':c['target_hash_power'],'gamma':c['gamma'],'natural_fork_rate':c['natural_fork_rate'],'candidate_power':c['candidate_total'],'residual_honest_power':c['residual_honest_power'],'U_H':x['target_honest'],'U_S0':x['target_unpunished_selfish'],'difference':mu,'ci95_low':lo,'ci95_high':hi,'representation_sensitivity_status':st,'role':'sensitivity_only_not_stage_b_admission'}
 sensitivity.append(item);env[(c['target_hash_power'],c['gamma'],c['natural_fork_rate'])].append(item)
rows=[]
for k,g in sorted(env.items(),key=lambda z:tuple(map(float,z[0]))):
 s={x['representation_sensitivity_status'] for x in g};status=next(iter(s)) if len(s)==1 else 'SELFISH_PROFITABILITY_INCONCLUSIVE'
 rows.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'statistically_supported_profitability_status':status,'representation_statuses':{x['candidate_power']:x['representation_sensitivity_status'] for x in g},'configuration_ids':[x['configuration_id'] for x in g],'U_H_range':[min(float(x['U_H']) for x in g),max(float(x['U_H']) for x in g)],'U_S0_range':[min(float(x['U_S0']) for x in g),max(float(x['U_S0']) for x in g)],'difference_range':[min(x['difference'] for x in g),max(x['difference'] for x in g)],'ci_low_min':min(x['ci95_low'] for x in g),'ci_high_max':max(x['ci95_high'] for x in g),'model_version':'race-owner-oceanic-residual-v3','role':'historical_representation_sensitivity_not_stage_b_admission'})
write_csv(OUT/'representation_sensitivity_selfish_profitability.csv',rows)
write_csv(OUT/'honest_population_representation_sensitivity.csv',sorted(sensitivity,key=lambda r:(float(r['target_hash_power']),float(r['gamma']),float(r['natural_fork_rate']),float(r['candidate_power']))))
print(json.dumps({'sensitivity_only':True,'historical_representation_status_counts':dict(Counter(r['statistically_supported_profitability_status'] for r in rows))},indent=2))
