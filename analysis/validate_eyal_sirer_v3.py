#!/usr/bin/env python3
import csv,json,math
from pathlib import Path
from punishment_sim.coalition import MODEL_VERSION,ExplicitSimulation,Population,paired_stats

POINTS={0:[.30,.33,.35],.25:[.25,.30,.35],.5:[.20,.25,.30],.75:[.15,.20,.25],1:[.05,.10,.20]}
OUT=Path('results/residual_oceanic_validation');OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for gamma,alphas in POINTS.items():
 threshold=(1-gamma)/(3-2*gamma)
 for alpha in alphas:
  diffs=[];hs=[];ss=[]
  for rep in range(40):
   p=Population(alpha,(("benchmark_explicit",.001),),gamma,0,100000,880000+rep)
   h=ExplicitSimulation(p,'honest',False,()).run()['actors']['target']['payoff']
   s=ExplicitSimulation(p,'selfish',False,()).run()['actors']['target']['payoff']
   hs.append(h);ss.append(s);diffs.append(s-h)
  st=paired_stats(diffs,ss,hs);classification='PROFITABLE' if st['ci95_low']>0 else 'UNPROFITABLE' if st['ci95_high']<0 else 'INCONCLUSIVE'
  expected='PROFITABLE' if alpha>threshold+1e-12 else 'UNPROFITABLE' if alpha<threshold-1e-12 else 'BOUNDARY'
  match=classification==expected or expected=='BOUNDARY' and classification=='INCONCLUSIVE'
  rows.append({'model_version':MODEL_VERSION,'alpha':alpha,'gamma':gamma,'lambda':0,'theoretical_threshold':threshold,'theoretical_side':expected,
   'simulated_U_H':sum(hs)/len(hs),'simulated_U_S_empty':sum(ss)/len(ss),'difference':st['mean'],'ci95_low':st['ci95_low'],'ci95_high':st['ci95_high'],
   'repetitions':40,'accepted_blocks':100000,'simulated_classification':classification,'expected_classification':expected,'match':match})
with (OUT/'eyal_sirer_threshold_validation.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
print(json.dumps({'rows':len(rows),'matches':sum(r['match'] for r in rows),'mismatches':[r for r in rows if not r['match']]},indent=2))
