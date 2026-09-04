#!/usr/bin/env python3
"""Summarize the expanded oceanic-v3 aggregate sweep without rerunning mining."""
import argparse,csv,json,math
from collections import Counter,defaultdict
from pathlib import Path

from analysis.stage_b_racefix import obj,read_csv,truth,write_csv

def minimum(rows,predicate,maximum=None):
    powers=[float(r['active_hash_power']) for r in rows
            if (maximum is None or float(r['active_hash_power'])<=maximum+1e-12) and predicate(r)]
    return min(powers) if powers else None

def generate(root):
    root=Path(root); out=root/'analysis_tables'; figures=out/'figures'
    out.mkdir(exist_ok=True); figures.mkdir(exist_ok=True)
    analytic=read_csv(out/'eyal_sirer_profitability_domain.csv')
    admission={(float(r['target_hash_power']),float(r['gamma'])):truth(r['profitable_vanilla_selfish_mining']) for r in analytic}
    coalitions=read_csv(root/'coalition_credibility_refined.csv')
    by=defaultdict(list)
    for r in coalitions:
        by[(float(r['target_hash_power']),float(r['gamma']),float(r['natural_fork_rate']))].append(r)
    def effective(r): return r['effectiveness_status']=='SUPPORTED'
    def weak_baseline(r): return truth(r['weak_baseline_credible'])
    def weak_deviation(r): return truth(r['weak_deviation_proof'])
    def strict_baseline(r): return truth(r['strict_baseline_credible'])
    def strict_deviation(r): return truth(r['strict_deviation_proof'])
    predicates={
      'effectiveness':effective,
      'weak_baseline_credibility':weak_baseline,
      'weak_deviation_proof':weak_deviation,
      'weak_joint_feasibility':lambda r:effective(r) and weak_baseline(r) and weak_deviation(r),
      'strict_baseline_credibility':strict_baseline,
      'strict_deviation_proof':strict_deviation,
      'strict_joint_feasibility':lambda r:effective(r) and strict_baseline(r) and strict_deviation(r),
    }
    rows=[]
    for key,group in sorted(by.items()):
        admitted=admission[(key[0],key[1])]
        row={'target_hash_power':key[0],'gamma':key[1],'natural_fork_rate':key[2],
             'analytic_admission_status':'ANALYTICALLY_PROFITABLE' if admitted else 'NOT_ANALYTICALLY_PROFITABLE',
             'authorized_for_punishment_study':admitted,
             'evaluated_coalition_min':min(float(r['active_hash_power']) for r in group),
             'evaluated_coalition_max':max(float(r['active_hash_power']) for r in group)}
        for name,predicate in predicates.items():
            old=minimum(group,predicate,.40); expanded=minimum(group,predicate)
            row['minimum_'+name+'_through_040']=old
            row['minimum_'+name+'_through_060']=expanded
            row[name+'_new_above_040']=old is None and expanded is not None and expanded>.40
        row['weakly_feasible_through_060']=row['minimum_weak_joint_feasibility_through_060'] is not None
        row['strictly_feasible_through_060']=row['minimum_strict_joint_feasibility_through_060'] is not None
        row['infeasible_at_060']=not row['weakly_feasible_through_060']
        rows.append(row)
    write_csv(out/'expanded_aggregate_environment_summary.csv',rows)
    profitable=[r for r in rows if r['authorized_for_punishment_study']]
    write_csv(out/'analytic_authorized_environment_thresholds.csv',profitable)
    write_csv(out/'analytic_authorized_new_feasible_regimes.csv',[r for r in profitable if r['weak_joint_feasibility_new_above_040']])
    write_csv(out/'analytic_authorized_infeasible_at_060.csv',[r for r in profitable if r['infeasible_at_060']])
    try:
        import matplotlib.pyplot as plt
        targets=sorted({r['target_hash_power'] for r in rows}); gammas=sorted({r['gamma'] for r in rows})
        status_value={'NOT_ANALYTICALLY_PROFITABLE':0,'ANALYTICALLY_PROFITABLE':1}
        for rate in sorted({r['natural_fork_rate'] for r in rows}):
            subset={(r['target_hash_power'],r['gamma']):r for r in rows if r['natural_fork_rate']==rate}
            fig,axes=plt.subplots(1,3,figsize=(13,4),constrained_layout=True)
            panels=[('Analytic admission',lambda r:status_value[r['analytic_admission_status']]),
                    ('Minimum effective power',lambda r:r['minimum_effectiveness_through_060']),
                    ('Minimum weakly feasible power',lambda r:r['minimum_weak_joint_feasibility_through_060'])]
            for ax,(title,value) in zip(axes,panels):
                matrix=[[value(subset[(a,g)]) for g in gammas] for a in targets]
                numeric=[[math.nan if x is None else x for x in row] for row in matrix]
                image=ax.imshow(numeric,origin='lower',aspect='auto')
                ax.set_xticks(range(len(gammas)),gammas);ax.set_yticks(range(len(targets)),targets)
                ax.set_xlabel('gamma');ax.set_ylabel('target power');ax.set_title(title)
                fig.colorbar(image,ax=ax,shrink=.75)
            fig.suptitle(f'Expanded aggregate oceanic-v3, natural fork rate={rate}')
            fig.savefig(figures/f'expanded_aggregate_lambda_{str(rate).replace(".","p")}.png',dpi=180)
            plt.close(fig)
    except ImportError:
        pass
    summary={'configurations':len(coalitions),'environment_triplets':len(rows),
             'analytic_admission_counts':dict(Counter(r['analytic_admission_status'] for r in rows)),
             'authorized_environments':len(profitable),
             'authorized_weakly_feasible':sum(r['weakly_feasible_through_060'] for r in profitable),
             'authorized_strictly_feasible':sum(r['strictly_feasible_through_060'] for r in profitable),
             'new_authorized_weakly_feasible_above_040':sum(r['weak_joint_feasibility_new_above_040'] for r in profitable),
             'authorized_infeasible_at_060':sum(r['infeasible_at_060'] for r in profitable)}
    (out/'expanded_aggregate_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);args=parser.parse_args()
    print(json.dumps(generate(args.root),indent=2))
