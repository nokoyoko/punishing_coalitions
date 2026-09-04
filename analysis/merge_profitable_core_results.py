#!/usr/bin/env python3
import csv,json,math
from collections import defaultdict
from pathlib import Path
from analysis.stage_b_racefix import DEFAULT_SOURCE,obj,read_csv,truth,write_csv

SUP=Path('results/research_sweep_stage_b_profitable_core_supplement');OUT=DEFAULT_SOURCE/'analysis_tables'
def write_schema(path,rows,fields):
 rows=list(rows)
 if rows:write_csv(path,rows);return
 with Path(path).open('w',newline='') as f:csv.DictWriter(f,fieldnames=fields).writeheader()
def sig(r):return (float(r['target_hash_power']),json.dumps(obj(r['candidate_distribution']),sort_keys=True),float(r['gamma']),float(r['natural_fork_rate']),r['coalition'])
def generate():
 original=[r for r in read_csv(DEFAULT_SOURCE/'coalition_credibility_refined.csv') if r['family'] in ('composition','both')]
 supplement=read_csv(SUP/'coalition_credibility_refined.csv'); oi={sig(r):r for r in original}; merged=[]
 for r in original:merged.append({**r,'source_provenance':'original_corrected_stage_b'})
 for r in supplement:
  if sig(r) in oi:continue
  merged.append({**r,'source_provenance':'profitable_core_supplement'})
 assert all(r['model_version']=='race-owner-precedence-v2' for r in merged)
 write_csv(OUT/'core_profitable_composition_results.csv',merged)
 domain=read_csv(OUT/'selfish_profitability_domain.csv'); ds={(float(r['target_hash_power']),float(r['gamma']),float(r['natural_fork_rate'])):r for r in domain}
 mi=defaultdict(list)
 for path in (DEFAULT_SOURCE/'member_credibility_refined.csv',SUP/'member_credibility_refined.csv'):
  for r in read_csv(path):mi[(r['configuration_id'],r['coalition'])].append(r)
 tp={}
 for path in (DEFAULT_SOURCE/'continuous_tpr_thresholds.csv',SUP/'continuous_tpr_thresholds.csv'):
  for r in read_csv(path):tp[(r['configuration_id'],r['coalition'])]=r
 fp={}
 for path in (DEFAULT_SOURCE/'false_positive_vectors.csv',SUP/'false_positive_vectors.csv'):
  for r in read_csv(path):
   if r['actor']=='target' and float(r['fpr'])==.1:fp[(r['configuration_id'],r['coalition'])]=r
 by=defaultdict(list)
 for r in merged:
  k=(float(r['target_hash_power']),float(r['gamma']),float(r['natural_fork_rate']));
  if ds[k]['statistically_supported_profitability_status']=='SELFISH_PROFITABLE':by[k].append(r)
 def flags(r):return (r['effectiveness_status']=='SUPPORTED',truth(r['weak_baseline_credible']),truth(r['weak_deviation_proof']),truth(r['strict_baseline_credible']),truth(r['strict_deviation_proof']))
 envclass=[];mins=[]
 for k,d in sorted(ds.items()):
  status=d['statistically_supported_profitability_status'];g=by.get(k,[])
  if status!='SELFISH_PROFITABLE':cls=status
  elif not g:cls='SELFISH_PROFITABLE_COMPOSITION_DATA_MISSING'
  else:
   q=[r for r in g if all(flags(r)[:3])];cls='SELFISH_PROFITABLE_FEASIBLE' if q else 'SELFISH_PROFITABLE_NO_FEASIBLE_COALITION'
  envclass.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'core_classification':cls,'configuration_ids':[r['configuration_id'] for r in g]})
  if status!='SELFISH_PROFITABLE':continue
  q=[r for r in g if all(flags(r)[:3])]
  if not q:mins.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'qualifying_coalition_exists':False,'status':'NO_FEASIBLE_COALITION_WITHIN_TESTED_GRID'});continue
  hp=min(float(r['active_hash_power']) for r in q)
  for r in q:
   if not math.isclose(float(r['active_hash_power']),hp):continue
   ms=mi[(r['configuration_id'],r['coalition'])];tr=tp[(r['configuration_id'],r['coalition'])];det=obj(r['deterrence'])
   mins.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'qualifying_coalition_exists':True,'status':'PROFITABLE_AND_WEAKLY_FEASIBLE',
    'configuration_id':r['configuration_id'],'coalition':r['coalition'],'minimum_active_coalition_power':hp,'candidate_population_power':r['candidate_population_power'],'structure':r['structure'],'cardinality':r['cardinality'],'member_hash_vector':r['member_hash_vector'],
    'weakest_member':r['weakest_member'],'weakest_member_hash_power':min(obj(r['member_hash_vector'])),'credibility_slack':r['credibility_slack'],
    'baseline_margins':{m['member_id']:obj(m['baseline']) for m in ms},'deviation_margins':{m['member_id']:obj(m['deviation']) for m in ms},
    'strictly_jointly_feasible':flags(r)[0] and flags(r)[3] and flags(r)[4],'deterrence_estimate':det['mean'],'deterrence_ci_low':det['ci95_low'],'deterrence_ci_high':det['ci95_high'],
    'tpr_status':tr['status'],'continuous_tpr_min':tr['tpr_min'] if tr['status']=='DETERRABLE' else '','tpr_ci_low':tr['bootstrap_ci_low'],'tpr_ci_high':tr['bootstrap_ci_high'],
    'false_positive_target_loss':fp[(r['configuration_id'],r['coalition'])]['conditional_loss'],'terminal_boundary_flag':truth(r['boundary_could_change_point_deterrence']) or truth(r['boundary_could_affect_supported_deterrence']),'source_provenance':r['source_provenance']})
 write_csv(OUT/'core_environment_classification.csv',envclass);write_csv(OUT/'minimum_profitable_environment_coalitions.csv',mins)
 # Composition flips, conditional on profitable domain.
 flips=[]
 for k,g in by.items():
  matched=defaultdict(list)
  for r in g:matched[float(r['active_hash_power'])].append(r)
  for hp,rr in matched.items():
   for i,a in enumerate(rr):
    for b in rr[i+1:]:
     fa=all(flags(a)[:3]);fb=all(flags(b)[:3]);sa=flags(a)[0] and flags(a)[3] and flags(a)[4];sb=flags(b)[0] and flags(b)[3] and flags(b)[4]
     if fa==fb and sa==sb:continue
     flips.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'active_hash_power':hp,'configuration_id_a':a['configuration_id'],'composition_a':a['member_hash_vector'],'joint_a':fa,'strict_a':sa,'configuration_id_b':b['configuration_id'],'composition_b':b['member_hash_vector'],'joint_b':fb,'strict_b':sb})
 write_schema(OUT/'profitable_composition_changes_feasibility.csv',flips,['target_hash_power','gamma','natural_fork_rate','active_hash_power','configuration_id_a','composition_a','joint_a','strict_a','configuration_id_b','composition_b','joint_b','strict_b'])
 tpro=[r for r in mins if truth(r.get('qualifying_coalition_exists')) and r['tpr_status']=='DETERRABLE'];write_schema(OUT/'profitable_environment_tpr_requirements.csv',tpro,['target_hash_power','gamma','natural_fork_rate','configuration_id','coalition','minimum_active_coalition_power','continuous_tpr_min','tpr_ci_low','tpr_ci_high'])
 # Lambda robustness rows only where a property changes across lambda.
 robust=[]
 for a in sorted({k[0] for k in by}):
  for ga in sorted({k[1] for k in by}):
   z=[r for r in mins if float(r['target_hash_power'])==a and float(r['gamma'])==ga];signature={(r['natural_fork_rate'],r.get('minimum_active_coalition_power'),r.get('strictly_jointly_feasible'),r.get('coalition'),r.get('continuous_tpr_min')) for r in z}
   if len({x[1:] for x in signature})>1:robust.extend(z)
 write_schema(OUT/'profitable_lambda_robustness.csv',robust,['target_hash_power','gamma','natural_fork_rate','qualifying_coalition_exists','status','minimum_active_coalition_power','strictly_jointly_feasible','coalition','continuous_tpr_min'])
 cand=[]
 for r in mins:
  if not truth(r.get('qualifying_coalition_exists')):cand.append({**r,'headline_conclusion_at_risk':'existence of a feasible coalition in profitable environment'});continue
  reasons=[]
  if not truth(r['strictly_jointly_feasible']):reasons.append('weak versus strict feasibility')
  if truth(r['terminal_boundary_flag']):reasons.append('terminal-sensitive minimum')
  if r['tpr_status']=='DETERRABLE':reasons.append('meaningful detector threshold')
  if reasons:cand.append({**r,'headline_conclusion_at_risk':'minimum power/composition/strictness/TPR','confirmation_reasons':reasons})
 write_csv(OUT/'profitable_core_stage_c_candidates.csv',cand)
 return {'merged_rows':len(merged),'profitable_environments':len(by),'feasible_environments':len({(r['target_hash_power'],r['gamma'],r['natural_fork_rate']) for r in mins if truth(r.get('qualifying_coalition_exists'))}),'strict_environments':len({(r['target_hash_power'],r['gamma'],r['natural_fork_rate']) for r in mins if truth(r.get('strictly_jointly_feasible'))}),'composition_flips':len(flips),'stage_c_candidates':len(cand)}
if __name__=='__main__':print(json.dumps(generate(),indent=2))
