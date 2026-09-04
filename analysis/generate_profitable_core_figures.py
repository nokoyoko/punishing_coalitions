#!/usr/bin/env python3
import json,os
from pathlib import Path
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from analysis.stage_b_racefix import DEFAULT_SOURCE,read_csv,write_csv
ROOT=Path(os.environ.get('PROFITABLE_CORE_ROOT',DEFAULT_SOURCE));T=ROOT/'analysis_tables';F=ROOT/'analysis_figures';F.mkdir(exist_ok=True);plt.rcParams.update({'font.size':9,'svg.hashsalt':'profitable-core-v1'})
def save(fig,name,rows,metric):
 for x in ('png','pdf','svg'):fig.savefig(F/f'{name}.{x}',bbox_inches='tight')
 plt.close(fig);write_csv(F/f'{name}.csv',rows);(F/f'{name}.metadata.json').write_text(json.dumps({'model_version':'race-owner-precedence-v2','profitable_domain_only':True,'metric':metric,'plotted_observation_count':len(rows),'mining_executed_by_figure':False,'stage_c_executed':False},indent=2)+'\n')
def mapfig(name,strict=False):
 rows=read_csv(T/'core_environment_classification.csv');mins=read_csv(T/'minimum_profitable_environment_coalitions.csv');mi={(r['target_hash_power'],r['gamma'],r['natural_fork_rate']):r for r in mins if r.get('qualifying_coalition_exists')=='True' and (not strict or r.get('strictly_jointly_feasible')=='True')}
 fig,axs=plt.subplots(1,3,figsize=(10,3.8),sharey=True);A=[.1,.15,.2,.25,.3,.35];G=[0,.25,.5,.75,1];lab={'SELFISH_NOT_PROFITABLE':'NP','SELFISH_PROFITABILITY_INCONCLUSIVE':'INC','SELFISH_PROFITABLE_NO_FEASIBLE_COALITION':'PNF','SELFISH_PROFITABLE_COMPOSITION_DATA_MISSING':'MISS'}
 for ax,L in zip(axs,(0,.005,.02)):
  ax.imshow(np.zeros((6,5)),cmap='Greys',alpha=.06,origin='lower');ax.set(xticks=range(5),xticklabels=G,yticks=range(6),yticklabels=A,title=f'λ={L:g}',xlabel='γ')
  for r in rows:
   if float(r['natural_fork_rate'])!=L:continue
   k=(r['target_hash_power'],r['gamma'],r['natural_fork_rate']);m=mi.get(k);text=f"{float(m['minimum_active_coalition_power']):.3g}" if m else lab.get(r['core_classification'],'PNF');ax.text(G.index(float(r['gamma'])),A.index(float(r['target_hash_power'])),text,ha='center',va='center',fontsize=7)
 axs[0].set_ylabel('Attacker hash α');fig.suptitle(('Strict ' if strict else '')+'profitable-selfish coalition feasibility\nNP not profitable; INC baseline inconclusive; PNF profitable, no feasible coalition')
 save(fig,name,rows,'profitable-domain minimum active coalition power')
def generate():
 mapfig('profitable_selfish_joint_feasibility_map');mapfig('profitable_selfish_strict_feasibility_map',True)
 mins=read_csv(T/'minimum_profitable_environment_coalitions.csv');valid=[r for r in mins if r.get('qualifying_coalition_exists')=='True']
 for strict,name in ((False,'profitable_minimum_coalition_power_weak'),(True,'profitable_minimum_coalition_power_strict')):
  q=[r for r in valid if not strict or r['strictly_jointly_feasible']=='True'];fig,ax=plt.subplots(figsize=(6.4,4))
  if q:
   for ga in sorted({float(r['gamma']) for r in q}):
    z=[r for r in q if float(r['gamma'])==ga];ax.scatter([float(r['target_hash_power']) for r in z],[float(r['minimum_active_coalition_power']) for r in z],label=f'γ={ga:g}')
  else:ax.text(.5,.5,'No qualifying coalition in profitable domain',ha='center',va='center',transform=ax.transAxes)
  ax.set(xlabel='Attacker hash α',ylabel='Minimum active coalition hash',title=('Strict' if strict else 'Weak')+' feasible coalition size');save(fig,name,q,'minimum active hash; profitable only')
 tpr=read_csv(T/'profitable_environment_tpr_requirements.csv');fig,ax=plt.subplots(figsize=(6.4,4))
 if tpr:ax.scatter([float(r['target_hash_power']) for r in tpr],[float(r['continuous_tpr_min']) for r in tpr])
 else:ax.text(.5,.5,'No minimum viable coalition; TPR requirement undefined',ha='center',va='center',transform=ax.transAxes)
 ax.set(xlabel='Attacker hash α',ylabel='Continuous minimum TPR',title='Detector quality in profitable environments');save(fig,'profitable_environment_tpr_requirements',tpr,'continuous TPR; profitable feasible only')
 return 5
if __name__=='__main__':print(generate())
