#!/usr/bin/env python3
"""Central-question analysis. Reads corrected CSVs; never invokes mining."""
from __future__ import annotations
import csv,json,math
from collections import defaultdict
from pathlib import Path
from analysis.stage_b_racefix import DEFAULT_SOURCE,MODEL_VERSION,obj,read_csv,truth,write_csv

DESIRED_A=[.10,.15,.20,.25,.30,.35]; DESIRED_G=[0,.25,.5,.75,1]; DESIRED_L=[0,.005,.02]

def generate(root=DEFAULT_SOURCE):
 root=Path(root); out=root/'analysis_tables'; out.mkdir(exist_ok=True)
 rows=[r for r in read_csv(root/'coalition_credibility_refined.csv') if r['family'] in ('composition','both')]
 if not rows or {r['model_version'] for r in rows}!={MODEL_VERSION}:raise RuntimeError('corrected composition inputs required')
 members=read_csv(root/'member_credibility_refined.csv'); mi=defaultdict(list)
 for m in members:mi[(m['configuration_id'],m['coalition'])].append(m)
 tpr={(r['configuration_id'],r['coalition']):r for r in read_csv(root/'continuous_tpr_thresholds.csv')}
 fp={(r['configuration_id'],r['coalition']):r for r in read_csv(root/'false_positive_vectors.csv') if r['actor']=='target' and float(r['fpr'])==.1}
 detector={(r['configuration_id'],r['coalition'],float(r['tpr'])):r for r in read_csv(root/'detector_evaluations.csv') if float(r['fpr'])==0}
 def flags(r):
  return {'effective':r['effectiveness_status']=='SUPPORTED','baseline_credible':truth(r['weak_baseline_credible']),
   'strict_baseline_credible':truth(r['strict_baseline_credible']),'deviation_proof':truth(r['weak_deviation_proof']),
   'strictly_deviation_proof':truth(r['strict_deviation_proof']),
   'jointly_feasible':r['effectiveness_status']=='SUPPORTED' and truth(r['weak_baseline_credible']) and truth(r['weak_deviation_proof']),
   'strictly_jointly_feasible':r['effectiveness_status']=='SUPPORTED' and truth(r['strict_baseline_credible']) and truth(r['strict_deviation_proof'])}
 enriched=[]
 for r in rows:enriched.append({**r,**flags(r)})
 envkeys=('target_hash_power','gamma','natural_fork_rate','structure','candidate_population_power'); by=defaultdict(list)
 for r in enriched:by[tuple(r[k] for k in envkeys)].append(r)
 feas=[]
 for k,g in sorted(by.items(),key=lambda x:tuple(float(v) if i in (0,1,2,4) else v for i,v in enumerate(x[0]))):
  z={envkeys[i]:v for i,v in enumerate(k)};z['enumerated_coalitions']=len(g)
  for field in ('effective','baseline_credible','deviation_proof','strictly_deviation_proof','jointly_feasible','strictly_jointly_feasible'):
   z['number_'+field]=sum(x[field] for x in g);z['any_'+field]=any(x[field] for x in g)
  z['configuration_id']=g[0]['configuration_id'];feas.append(z)
 write_csv(out/'coalition_feasibility_by_environment.csv',feas)

 central=defaultdict(list)
 for r in enriched:central[(r['target_hash_power'],r['gamma'],r['natural_fork_rate'])].append(r)
 criteria=[('EFFECTIVE','effective'),('EFFECTIVE_BASELINE_CREDIBLE',None),('JOINTLY_FEASIBLE','jointly_feasible'),('STRICTLY_JOINTLY_FEASIBLE','strictly_jointly_feasible')]
 mins=[]
 for env,g in sorted(central.items(),key=lambda x:tuple(map(float,x[0]))):
  powers=sorted({float(x['active_hash_power']) for x in g})
  for label,field in criteria:
   q=[r for r in g if (r['effective'] and r['baseline_credible'])] if field is None else [r for r in g if r[field]]
   if not q:
    mins.append({'criterion':label,'qualifying_coalition_exists':False,'no_coalition_status':'NO_QUALIFYING_COALITION','target_hash_power':env[0],'gamma':env[1],'natural_fork_rate':env[2],'configuration_id':''});continue
   hp=min(float(r['active_hash_power']) for r in q)
   boundary='AT_LOWER_GRID_EDGE' if hp==powers[0] else 'AT_UPPER_GRID_EDGE' if hp==powers[-1] else 'OBSERVED_INTERIOR'
   for r in q:
    if not math.isclose(float(r['active_hash_power']),hp,abs_tol=1e-12):continue
    ms=mi[(r['configuration_id'],r['coalition'])]; dist=obj(r['candidate_distribution']); active=set(obj(r['members']))
    tr=tpr[(r['configuration_id'],r['coalition'])]; d=obj(r['deterrence'])
    mins.append({'criterion':label,'qualifying_coalition_exists':True,'no_coalition_status':'','configuration_id':r['configuration_id'],
     'target_hash_power':r['target_hash_power'],'gamma':r['gamma'],'natural_fork_rate':r['natural_fork_rate'],
     'candidate_population_power':r['candidate_population_power'],'active_coalition_power':r['active_hash_power'],'structure':r['structure'],
     'coalition':r['coalition'],'coalition_cardinality':r['cardinality'],'active_members':r['members'],'active_member_hash_vector':r['member_hash_vector'],
     'inactive_candidate_hash_vector':[dist[x] for x in dist if x not in active],'residual_honest_power':r['residual_honest_power'],
     'deterrence_estimate':d['mean'],'deterrence_ci_low':d['ci95_low'],'deterrence_ci_high':d['ci95_high'],'effectiveness_status':r['effectiveness_status'],
     'baseline_member_statuses':{m['member_id']:m['baseline_classification'] for m in ms},'deviation_member_margins':{m['member_id']:obj(m['deviation']) for m in ms},
     'weakest_member':r['weakest_member'],'weakest_member_hash_power':min(obj(r['member_hash_vector'])),'credibility_slack':r['credibility_slack'],
     'weak_deviation_proof':r['weak_deviation_proof'],'strict_deviation_proof':r['strict_deviation_proof'],'tpr_status':tr['status'],
     'continuous_tpr_min':tr['tpr_min'] if tr['status']=='DETERRABLE' else '','tpr_ci_low':tr['bootstrap_ci_low'],'tpr_ci_high':tr['bootstrap_ci_high'],
     'false_positive_target_loss_fpr_0_1':fp[(r['configuration_id'],r['coalition'])]['conditional_loss'],
     'terminal_review':truth(r['boundary_could_change_point_deterrence']) or truth(r['boundary_could_affect_supported_deterrence']),
     'threshold_grid_boundary':boundary})
 write_csv(out/'minimum_feasible_coalitions.csv',mins)
 compositions=[r for r in mins if r['criterion']=='JOINTLY_FEASIBLE' and truth(r['qualifying_coalition_exists'])]
 write_csv(out/'feasible_coalition_compositions.csv',compositions)

 # One row per central cell, including coverage-aware categorical state.
 maps=[]
 for a in DESIRED_A:
  for ga in DESIRED_G:
   for la in DESIRED_L:
    g=central.get((str(a),str(ga),str(la))) or central.get((f'{a:g}',f'{ga:g}',f'{la:g}')) or []
    for strict,field in ((False,'jointly_feasible'),(True,'strictly_jointly_feasible')):
     if not g:status='OUTSIDE_COMPOSITION_GRID';q=[]
     else:
      q=[r for r in g if r[field]]
      if q:status='FEASIBLE'
      elif not any(r['effective'] for r in g):status='NO_EFFECTIVE_COALITION'
      elif not any(r['effective'] and r['baseline_credible'] for r in g):status='EFFECTIVE_BUT_NOT_CREDIBLE'
      elif not any(r['effective'] and r['baseline_credible'] and r['deviation_proof'] for r in g):status='CREDIBLE_BUT_NOT_DEVIATION_PROOF'
      else:status='NO_JOINTLY_FEASIBLE_COALITION'
     hp=min((float(r['active_hash_power']) for r in q),default=None);qq=[r for r in q if hp is not None and math.isclose(float(r['active_hash_power']),hp)]
     maps.append({'map_type':'strict' if strict else 'weak','target_hash_power':a,'gamma':ga,'natural_fork_rate':la,'status':status,
      'minimum_active_coalition_power':hp,'configuration_ids':[r['configuration_id'] for r in qq],
      'coalitions':[r['coalition'] for r in qq],'grid_boundary':bool(q) and hp in (min(float(r['active_hash_power']) for r in g),max(float(r['active_hash_power']) for r in g)),
      'terminal_review':any(truth(r['boundary_could_change_point_deterrence']) or truth(r['boundary_could_affect_supported_deterrence']) for r in qq)})
 write_csv(out/'joint_feasibility_map.csv',maps)

 # Equal-active-hash comparisons where composition flips joint feasibility.
 ch=[]; match=defaultdict(list)
 for r in enriched:match[(r['target_hash_power'],r['gamma'],r['natural_fork_rate'],r['active_hash_power'])].append(r)
 for k,g in match.items():
  for i,a in enumerate(g):
   for b in g[i+1:]:
    if (a['cardinality'],a['member_hash_vector'])==(b['cardinality'],b['member_hash_vector']) or a['jointly_feasible']==b['jointly_feasible']:continue
    ch.append({'target_hash_power':k[0],'gamma':k[1],'natural_fork_rate':k[2],'total_active_hash':k[3],
     'configuration_id_a':a['configuration_id'],'coalition_a':a['coalition'],'composition_a':a['member_hash_vector'],'jointly_feasible_a':a['jointly_feasible'],
     'effectiveness_a':a['effectiveness_status'],'baseline_credible_a':a['baseline_credible'],'deviation_proof_a':a['deviation_proof'],'slack_a':a['credibility_slack'],'weakest_power_a':min(obj(a['member_hash_vector'])),
     'configuration_id_b':b['configuration_id'],'coalition_b':b['coalition'],'composition_b':b['member_hash_vector'],'jointly_feasible_b':b['jointly_feasible'],
     'effectiveness_b':b['effectiveness_status'],'baseline_credible_b':b['baseline_credible'],'deviation_proof_b':b['deviation_proof'],'slack_b':b['credibility_slack'],'weakest_power_b':min(obj(b['member_hash_vector'])),
     'feasibility_difference_reason':'effectiveness/baseline/deviation conjunction differs'})
 write_csv(out/'composition_changes_feasibility.csv',ch)

 # Perfect and detector-adjusted feasibility, algebraic detector outputs only.
 tprout=[]
 for r in compositions:
  key=(r['configuration_id'],r['coalition']); tr=tpr[key]
  tprout.append({**r,'detector_condition':'perfect_continuous','detector_adjusted_effective':tr['status']!='NOT_DETERRENT_AT_TPR_1'})
  for level in (.5,.7,.9,1):
   dr=detector[(key[0],key[1],level)]
   tprout.append({**r,'detector_condition':f'TPR_{level:g}','configured_tpr':level,'detector_adjusted_effective':dr['expected_effectiveness_status']=='SUPPORTED'})
 write_csv(out/'feasible_coalition_tpr_requirements.csv',tprout)

 # Lambda changes and coverage.
 lc=[]
 for a in DESIRED_A:
  for ga in DESIRED_G:
   z=[r for r in maps if r['map_type']=='weak' and float(r['target_hash_power'])==a and float(r['gamma'])==ga]
   if len(z)==3 and len({(r['status'],r['minimum_active_coalition_power']) for r in z})>1:lc.extend(z)
 write_csv(out/'lambda_feasibility_changes.csv',lc)
 mining=read_csv(root/'mining_configurations.csv'); coverage=[]
 for a in DESIRED_A:
  for ga in DESIRED_G:
   for la in DESIRED_L:
    agg=any(float(r['target_hash_power'])==a and float(r['gamma'])==ga and float(r['natural_fork_rate'])==la and r['family'] in ('aggregate','both') for r in mining)
    comp=any(float(r['target_hash_power'])==a and float(r['gamma'])==ga and float(r['natural_fork_rate'])==la and r['family'] in ('composition','both') for r in mining)
    coverage.append({'target_hash_power':a,'gamma':ga,'natural_fork_rate':la,'aggregate_effectiveness_exists':agg,'composition_credibility_exists':comp,'exact_coalition_enumeration_exists':comp,'joint_feasibility_answerable':comp})
 write_csv(out/'coalition_research_coverage.csv',coverage)
 missing=[r for r in coverage if not r['joint_feasibility_answerable']]
 # 36 requested populations/cell; singleton configurations overlap aggregate.
 plan={'model_version':MODEL_VERSION,'planning_only':True,'simulation_executed':False,'missing_environments':len(missing),
  'missing_environment_rows':missing,'requested_population_configurations':len(missing)*36,
  'estimated_new_population_configurations':len(missing)*30,'estimated_unique_new_mining_simulations':len(missing)*30*260,
  'estimated_blocks':len(missing)*30*260*30000,'estimated_runtime_seconds':len(missing)*30*260*30000/(13543200000/7190.781591667037),
  'estimated_storage_gib':2.7*(len(missing)*30*260*30000)/13543200000,'note':'conservative planning estimate; dry run only'}
 (root/'central_coverage_supplement_dry_run.json').write_text(json.dumps(plan,indent=2)+'\n')
 config={'stage':'central-coverage-supplement-planning-only','do_not_execute':True,'base_config':'configs/research_sweep_stage_b.json','model_version':MODEL_VERSION,
  'explicit_missing_environments':[{k:r[k] for k in ('target_hash_power','gamma','natural_fork_rate')} for r in missing],
  'candidate_power':[.05,.10,.15,.20,.25,.30],'structures':['singleton','two_equal','two_unequal','three_equal','three_moderate','three_concentrated'],'repetitions':30,'accepted_blocks':30000}
 (Path('configs')/'research_sweep_stage_b_core_coverage_supplement.json').write_text(json.dumps(config,indent=2)+'\n')

 # Narrow confirmation set: only minimum weak/strict identities and boundary cases.
 cand={}
 for r in mins:
  if r.get('qualifying_coalition_exists') is not True:continue
  if r['criterion'] not in ('JOINTLY_FEASIBLE','STRICTLY_JOINTLY_FEASIBLE'):continue
  reasons=[]
  if r['threshold_grid_boundary']!='OBSERVED_INTERIOR':reasons.append('minimum coalition grid boundary')
  if r['criterion']=='JOINTLY_FEASIBLE' and not truth(r['strict_deviation_proof']):reasons.append('weak versus strict headline feasibility')
  if r['tpr_status']=='DETERRABLE' and r['tpr_ci_low'] and r['tpr_ci_high']:reasons.append('headline TPR feasibility boundary')
  if truth(r['terminal_review']):reasons.append('terminal-sensitive minimum coalition')
  if reasons:cand[(r['configuration_id'],r['coalition'])]={**r,'headline_conclusion_at_risk':'minimum/existence/strictness/TPR of jointly feasible coalition','confirmation_reasons':reasons}
 write_csv(out/'central_question_stage_c_candidates.csv',cand.values())
 return {'coalitions':len(enriched),'environment_rows':len(feas),'central_cells_answered':len(central),'joint_map_rows':len(maps),'composition_flips':len(ch),'coverage_missing':len(missing),'stage_c_candidates':len(cand),'supplement':plan}

if __name__=='__main__':print(json.dumps(generate(),indent=2))
