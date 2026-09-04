#!/usr/bin/env python3
import json
from pathlib import Path
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from analysis.stage_b_racefix import DEFAULT_SOURCE,read_csv,truth,write_csv

plt.rcParams.update({'figure.figsize':(10,3.6),'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'petty-core-v1'})
OUT=DEFAULT_SOURCE/'analysis_figures'; TAB=DEFAULT_SOURCE/'analysis_tables'
def save(fig,name,rows,sources,metric):
 for ext in ('png','pdf','svg'):fig.savefig(OUT/f'{name}.{ext}',bbox_inches='tight')
 plt.close(fig);write_csv(OUT/f'{name}.csv',rows)
 (OUT/f'{name}.metadata.json').write_text(json.dumps({'corrected_model':'race-owner-precedence-v2','sources':sources,'metric':metric,'observations':len(rows),'plotted_observation_count':len(rows),'configuration_ids_traceable':True,'mining_executed':False,'stage_c_executed':False},indent=2)+'\n')
def maps(kind,name):
 rows=[r for r in read_csv(TAB/'joint_feasibility_map.csv') if r['map_type']==kind];fig,axs=plt.subplots(1,3,sharey=True)
 alphas=[.1,.15,.2,.25,.3,.35];gammas=[0,.25,.5,.75,1]
 symbols={'OUTSIDE_COMPOSITION_GRID':'OUT','NO_EFFECTIVE_COALITION':'NE','EFFECTIVE_BUT_NOT_CREDIBLE':'NC','CREDIBLE_BUT_NOT_DEVIATION_PROOF':'ND','NO_JOINTLY_FEASIBLE_COALITION':'NJ'}
 for ax,la in zip(axs,(0,.005,.02)):
  ax.set_title(f'λ={la:g}');ax.set_xticks(range(5),gammas);ax.set_yticks(range(6),alphas);ax.set_xlabel('γ');ax.imshow(np.zeros((6,5)),cmap='Greys',vmin=0,vmax=4,alpha=.08,origin='lower')
  for r in rows:
   if float(r['natural_fork_rate'])!=la:continue
   x=gammas.index(float(r['gamma']));y=alphas.index(float(r['target_hash_power']))
   text=f"{float(r['minimum_active_coalition_power']):.3g}" if r['status']=='FEASIBLE' else symbols.get(r['status'],'NJ')
   if truth(r['grid_boundary']):text+='†'
   if truth(r['terminal_review']):text+='*'
   ax.text(x,y,text,ha='center',va='center',fontsize=7)
 axs[0].set_ylabel('Selfish target hash α');fig.suptitle(('Strictly ' if kind=='strict' else '')+'jointly feasible minimum active hash\nOUT outside composition grid; NE no effective; NC baseline failure; ND deviation failure; † grid edge; * terminal review')
 save(fig,name,rows,['joint_feasibility_map.csv'],'minimum active coalition power / categorical feasibility')
def generate():
 maps('weak','joint_feasibility_map');maps('strict','strict_joint_feasibility_map')
 rows=read_csv(TAB/'joint_feasibility_map.csv');weak={(r['target_hash_power'],r['gamma'],r['natural_fork_rate']):r for r in rows if r['map_type']=='weak'};strict={(r['target_hash_power'],r['gamma'],r['natural_fork_rate']):r for r in rows if r['map_type']=='strict'}
 compact=[]
 for k,w in weak.items():
  s=strict[k];state='STRICT_EXISTS' if s['status']=='FEASIBLE' else 'WEAK_ONLY' if w['status']=='FEASIBLE' else 'NONE_OR_OUTSIDE';compact.append({**w,'viability_class':state})
 fig,axs=plt.subplots(1,3,sharey=True);colors={'STRICT_EXISTS':'#0072B2','WEAK_ONLY':'#E69F00','NONE_OR_OUTSIDE':'#999999'}
 for ax,la in zip(axs,(0,.005,.02)):
  rr=[r for r in compact if float(r['natural_fork_rate'])==la]
  for state in colors:
   q=[r for r in rr if r['viability_class']==state];ax.scatter([float(r['gamma']) for r in q],[float(r['target_hash_power']) for r in q],c=colors[state],label=state,s=45)
  ax.set(title=f'λ={la:g}',xlabel='γ',xticks=[0,.25,.5,.75,1],yticks=[.1,.15,.2,.25,.3,.35])
 axs[0].set_ylabel('α');axs[-1].legend(fontsize=7);fig.suptitle('Environment-level weak versus strict joint feasibility')
 save(fig,'weak_vs_strict_joint_feasibility',compact,['joint_feasibility_map.csv'],'environment viability class')
 observed=[r for r in rows if r['status']=='FEASIBLE'];fig,axs=plt.subplots(1,3,sharey=True)
 for ax,la in zip(axs,(0,.005,.02)):
  for kind,ls in (('weak','-'),('strict','--')):
   for ga in (0,.5,1):
    q=sorted([r for r in observed if r['map_type']==kind and float(r['natural_fork_rate'])==la and float(r['gamma'])==ga],key=lambda r:float(r['target_hash_power']))
    if q:ax.plot([float(r['target_hash_power']) for r in q],[float(r['minimum_active_coalition_power']) for r in q],ls,marker='o',label=f'{kind}, γ={ga:g}')
  ax.set(title=f'λ={la:g}',xlabel='Attacker hash α')
 axs[0].set_ylabel('Minimum active coalition hash');axs[-1].legend(fontsize=6);fig.suptitle('Minimum jointly feasible coalition size')
 save(fig,'minimum_joint_feasible_power_vs_attacker',observed,['joint_feasibility_map.csv'],'minimum active coalition power')
 tpr=[r for r in read_csv(TAB/'feasible_coalition_tpr_requirements.csv') if r['detector_condition']=='perfect_continuous'];fig,axs=plt.subplots(1,3,sharey=True)
 for ax,la in zip(axs,(0,.005,.02)):
  q=[r for r in tpr if float(r['natural_fork_rate'])==la and r['tpr_status']=='DETERRABLE']
  for ga in (0,.5,1):
   z=[r for r in q if float(r['gamma'])==ga];ax.scatter([float(r['target_hash_power']) for r in z],[float(r['continuous_tpr_min']) for r in z],label=f'γ={ga:g}',s=28)
  ax.set(title=f'λ={la:g}',xlabel='Attacker hash α',ylim=(0,1.05))
 axs[0].set_ylabel('Continuous minimum TPR');axs[-1].legend(fontsize=7);fig.suptitle('Detector requirement for minimum jointly feasible coalitions\nAlready-unprofitable cases retained categorically in companion CSV')
 save(fig,'joint_feasible_tpr_requirements',tpr,['feasible_coalition_tpr_requirements.csv'],'continuous minimum TPR')
 return ['joint_feasibility_map','strict_joint_feasibility_map','weak_vs_strict_joint_feasibility','minimum_joint_feasible_power_vs_attacker','joint_feasible_tpr_requirements']
if __name__=='__main__':print(json.dumps(generate(),indent=2))
