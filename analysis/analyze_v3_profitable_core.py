#!/usr/bin/env python3
import csv,json,math,shutil
from collections import defaultdict
from pathlib import Path
from analysis.stage_b_racefix import obj,read_csv,truth,write_csv
A=Path('results/research_sweep_stage_b_oceanic_v3');R=Path('results/research_sweep_stage_b_oceanic_v3_profitable_core');O=R/'analysis_tables';O.mkdir(exist_ok=True)
domain=read_csv(A/'analysis_tables/selfish_profitability_domain.csv');write_csv(O/'selfish_profitability_domain.csv',domain);ds={(float(r['target_hash_power']),float(r['gamma']),float(r['natural_fork_rate'])):r for r in domain}
coals=read_csv(R/'coalition_credibility_refined.csv');members=defaultdict(list)
for r in read_csv(R/'member_credibility_refined.csv'):members[(r['configuration_id'],r['coalition'])].append(r)
tpr={(r['configuration_id'],r['coalition']):r for r in read_csv(R/'continuous_tpr_thresholds.csv')};fp={(r['configuration_id'],r['coalition']):r for r in read_csv(R/'false_positive_vectors.csv') if r['actor']=='target' and float(r['fpr'])==.1}
by=defaultdict(list)
for r in coals:by[(float(r['target_hash_power']),float(r['gamma']),float(r['natural_fork_rate']))].append(r)
def fl(r):return (r['effectiveness_status']=='SUPPORTED',truth(r['weak_baseline_credible']),truth(r['weak_deviation_proof']),truth(r['strict_baseline_credible']),truth(r['strict_deviation_proof']))
classes=[];mins=[]
for k,d in sorted(ds.items()):
 status=d['statistically_supported_profitability_status'];g=by.get(k,[])
 if status!='SELFISH_PROFITABLE':c=status
 else:
  q=[r for r in g if all(fl(r)[:3])];c='SELFISH_PROFITABLE_FEASIBLE' if q else 'SELFISH_PROFITABLE_NO_FEASIBLE_COALITION' if g else 'SELFISH_PROFITABLE_COMPOSITION_DATA_MISSING'
 classes.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'core_classification':c,'configuration_ids':[r['configuration_id'] for r in g]})
 if status!='SELFISH_PROFITABLE':continue
 q=[r for r in g if all(fl(r)[:3])]
 if not q:mins.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'qualifying_coalition_exists':False,'status':'NO_FEASIBLE_COALITION_WITHIN_TESTED_GRID'});continue
 hp=min(float(r['active_hash_power']) for r in q)
 for r in q:
  if not math.isclose(float(r['active_hash_power']),hp):continue
  ms=members[(r['configuration_id'],r['coalition'])];t=tpr[(r['configuration_id'],r['coalition'])];dstat=obj(r['deterrence'])
  mins.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'qualifying_coalition_exists':True,'status':'PROFITABLE_AND_WEAKLY_FEASIBLE','configuration_id':r['configuration_id'],'coalition':r['coalition'],'minimum_active_coalition_power':hp,'candidate_population_power':r['candidate_population_power'],'structure':r['structure'],'cardinality':r['cardinality'],'member_hash_vector':r['member_hash_vector'],'weakest_member':r['weakest_member'],'weakest_member_hash_power':min(obj(r['member_hash_vector'])),'credibility_slack':r['credibility_slack'],'baseline_margins':{m['member_id']:obj(m['baseline']) for m in ms},'deviation_margins':{m['member_id']:obj(m['deviation']) for m in ms},'strictly_jointly_feasible':fl(r)[0] and fl(r)[3] and fl(r)[4],'deterrence_estimate':dstat['mean'],'deterrence_ci_low':dstat['ci95_low'],'deterrence_ci_high':dstat['ci95_high'],'tpr_status':t['status'],'continuous_tpr_min':t['tpr_min'] if t['status']=='DETERRABLE' else '','tpr_ci_low':t['bootstrap_ci_low'],'tpr_ci_high':t['bootstrap_ci_high'],'false_positive_target_loss':fp[(r['configuration_id'],r['coalition'])]['conditional_loss'],'terminal_boundary_flag':truth(r['boundary_could_change_point_deterrence']) or truth(r['boundary_could_affect_supported_deterrence']),'model_version':r['model_version']})
write_csv(O/'core_environment_classification.csv',classes);write_csv(O/'minimum_profitable_environment_coalitions.csv',mins);write_csv(O/'feasible_coalition_compositions.csv',[r for r in mins if truth(r.get('qualifying_coalition_exists'))])
flips=[]
for k,g in by.items():
 matched=defaultdict(list)
 for r in g:matched[float(r['active_hash_power'])].append(r)
 for hp,rr in matched.items():
  for i,a in enumerate(rr):
   for b in rr[i+1:]:
    ja=all(fl(a)[:3]);jb=all(fl(b)[:3]);sa=fl(a)[0] and fl(a)[3] and fl(a)[4];sb=fl(b)[0] and fl(b)[3] and fl(b)[4]
    if ja!=jb or sa!=sb:flips.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'active_hash_power':hp,'configuration_id_a':a['configuration_id'],'composition_a':a['member_hash_vector'],'joint_a':ja,'strict_a':sa,'configuration_id_b':b['configuration_id'],'composition_b':b['member_hash_vector'],'joint_b':jb,'strict_b':sb})
write_csv(O/'profitable_composition_changes_feasibility.csv',flips)
tpro=[r for r in mins if truth(r.get('qualifying_coalition_exists')) and r['tpr_status']=='DETERRABLE'];write_csv(O/'profitable_environment_tpr_requirements.csv',tpro)
rob=[]
for a in sorted({k[0] for k in by}):
 for ga in sorted({k[1] for k in by}):
  z=[r for r in mins if float(r['target_hash_power'])==a and float(r['gamma'])==ga]
  if len({(r.get('qualifying_coalition_exists'),r.get('minimum_active_coalition_power'),r.get('strictly_jointly_feasible'),r.get('coalition'),r.get('continuous_tpr_min')) for r in z})>1:rob.extend(z)
write_csv(O/'profitable_lambda_robustness.csv',rob)
cand=[]
for r in mins:
 reasons=[]
 if not truth(r.get('qualifying_coalition_exists')):reasons=['existence/nonexistence of feasible coalition']
 else:
  if not truth(r['strictly_jointly_feasible']):reasons.append('weak-versus-strict feasibility')
  if truth(r['terminal_boundary_flag']):reasons.append('headline terminal overlap')
  if r['tpr_status']=='DETERRABLE':reasons.append('important TPR boundary')
 if reasons:cand.append({**r,'headline_conclusion_at_risk':'profitable-domain coalition feasibility/minimum','confirmation_reasons':reasons})
write_csv(O/'profitable_core_stage_c_candidates.csv',cand)
print(json.dumps({'profitable_environments':sum(r['statistically_supported_profitability_status']=='SELFISH_PROFITABLE' for r in domain),'feasible_environments':len({(r['target_hash_power'],r['gamma'],r['natural_fork_rate']) for r in mins if truth(r.get('qualifying_coalition_exists'))}),'strict_environments':len({(r['target_hash_power'],r['gamma'],r['natural_fork_rate']) for r in mins if truth(r.get('strictly_jointly_feasible'))}),'no_feasible':sum(not truth(r.get('qualifying_coalition_exists')) for r in mins),'minimum_rows':sum(truth(r.get('qualifying_coalition_exists')) for r in mins),'composition_flips':len(flips),'tpr_rows':len(tpro),'lambda_rows':len(rob),'stage_c_candidates':len(cand)},indent=2))
