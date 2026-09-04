#!/usr/bin/env python3
"""Classify selfish profitability from paired corrected aggregate repetitions."""
import csv,json,math,statistics
from collections import defaultdict,Counter
from pathlib import Path
from analysis.stage_b_racefix import DEFAULT_SOURCE,MODEL_VERSION,read_csv,write_csv

def generate(root=DEFAULT_SOURCE):
 root=Path(root);out=root/'analysis_tables';configs={r['configuration_id']:r for r in read_csv(root/'mining_configurations.csv')}
 reps=defaultdict(list)
 for r in read_csv(root/'repetition_metrics.csv'):
  c=configs[r['configuration_id']]
  if c['structure']=='singleton' and c['family'] in ('aggregate','both'):
   reps[r['configuration_id']].append(float(r['punishment_reduction'])-float(r['deterrence'])) # (S0-SC)-(H-SC)=S0-H
 per=[]
 for cid,v in reps.items():
  c=configs[cid];mu=statistics.mean(v);se=statistics.stdev(v)/math.sqrt(len(v));lo=mu-2.045*se;hi=mu+2.045*se
  st='SELFISH_PROFITABLE' if lo>0 else 'SELFISH_NOT_PROFITABLE' if hi<0 else 'SELFISH_PROFITABILITY_INCONCLUSIVE'
  per.append({**c,'profitability_difference':mu,'ci95_low':lo,'ci95_high':hi,'representation_status':st,'n':len(v)})
 env=defaultdict(list)
 for r in per:env[(r['target_hash_power'],r['gamma'],r['natural_fork_rate'])].append(r)
 mining=read_csv(root/'mining_configurations.csv'); coal=read_csv(root/'coalition_results.csv'); pay={(r['configuration_id'],r['coalition']):(float(r['target_honest']),float(r['target_unpunished_selfish'])) for r in coal};domain=[]
 for k,g in sorted(env.items(),key=lambda z:tuple(map(float,z[0]))):
  statuses={r['representation_status'] for r in g}
  if statuses=={'SELFISH_PROFITABLE'}:supported='SELFISH_PROFITABLE'
  elif statuses=={'SELFISH_NOT_PROFITABLE'}:supported='SELFISH_NOT_PROFITABLE'
  else:supported='SELFISH_PROFITABILITY_INCONCLUSIVE'
  point='SELFISH_PROFITABLE' if all(float(r['profitability_difference'])>0 for r in g) else 'SELFISH_NOT_PROFITABLE' if all(float(r['profitability_difference'])<=0 for r in g) else 'SELFISH_PROFITABILITY_INCONCLUSIVE'
  comp=any(float(r['target_hash_power'])==float(k[0]) and float(r['gamma'])==float(k[1]) and float(r['natural_fork_rate'])==float(k[2]) and r['family'] in ('composition','both') for r in mining)
  domain.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],
   'U_H_range':[min(pay[(r['configuration_id'],'c1')][0] for r in g),max(pay[(r['configuration_id'],'c1')][0] for r in g)],
   'U_S0_range':[min(pay[(r['configuration_id'],'c1')][1] for r in g),max(pay[(r['configuration_id'],'c1')][1] for r in g)],
   'U_S0_minus_U_H_mean_range':[min(r['profitability_difference'] for r in g),max(r['profitability_difference'] for r in g)],
   'profitability_ci_low_min':min(r['ci95_low'] for r in g),'profitability_ci_high_max':max(r['ci95_high'] for r in g),
   'point_estimate_profitability_status':point,'statistically_supported_profitability_status':supported,
   'aggregate_configuration_ids':[r['configuration_id'] for r in g],'aggregate_candidate_powers':[r['candidate_total'] for r in g],
   'representation_statuses':{r['candidate_total']:r['representation_status'] for r in g},'composition_data_currently_exist':comp,
   'supplemental_composition_mining_required':supported=='SELFISH_PROFITABLE' and not comp,'model_version':MODEL_VERSION})
 write_csv(out/'selfish_profitability_domain.csv',domain)
 profitable=[r for r in domain if r['statistically_supported_profitability_status']=='SELFISH_PROFITABLE']
 coverage=[]
 for r in profitable:
  coverage.append({**r,'candidate_structures_currently_covered':['singleton','two_equal','two_unequal','three_equal','three_moderate','three_concentrated'] if r['composition_data_currently_exist'] else [],
   'candidate_population_powers_currently_covered':[.05,.10,.15,.20,.25,.30] if r['composition_data_currently_exist'] else [],
   'exact_coalition_enumeration_available':r['composition_data_currently_exist'],'supplemental_run_required':not r['composition_data_currently_exist']})
 write_csv(out/'profitable_environment_coverage.csv',coverage)
 counts=Counter(r['statistically_supported_profitability_status'] for r in domain)
 missing=[r for r in profitable if not r['composition_data_currently_exist']]
 config={'stage':'profitable-core-supplement','expected_model_version':MODEL_VERSION,'seed':51000,'repetitions':30,'accepted_blocks':30000,'bootstrap_samples':2000,'execution_workers':8,'stage_c_max_candidates':0,'tpr':[.5,.7,.9,1.0],'fpr':[0,.001,.01,.05,.10],'robustness_bins':[.0001,.0005],
  'aggregate':{'target_hash':[],'coalition_power':[],'gamma':[],'natural_fork_rate':[]},
  'composition':{'target_hash':sorted({float(r['target_hash_power']) for r in missing}),'candidate_power':[.05,.10,.15,.20,.25,.30],
   'gamma':sorted({float(r['gamma']) for r in missing}),'natural_fork_rate':sorted({float(r['natural_fork_rate']) for r in missing}),
   'structures':['singleton','two_equal','two_unequal','three_equal','three_moderate','three_concentrated']},
  'authorized_environment_triplets':[[float(r['target_hash_power']),float(r['gamma']),float(r['natural_fork_rate'])] for r in missing]}
 Path('configs/research_sweep_stage_b_profitable_core_supplement.json').write_text(json.dumps(config,indent=2)+'\n')
 return {'counts':dict(counts),'profitable_covered':sum(r['composition_data_currently_exist'] for r in profitable),'profitable_missing':len(missing),'mixed_representation_environments':sum(r['statistically_supported_profitability_status']=='SELFISH_PROFITABILITY_INCONCLUSIVE' for r in domain)}
if __name__=='__main__':print(json.dumps(generate(),indent=2))
