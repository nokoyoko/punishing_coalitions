#!/usr/bin/env python3
import argparse,json
from collections import Counter
from pathlib import Path

from analysis.stage_b_racefix import write_csv
from punishment_sim.research_sweep import systematic_compositions,select_systematic_compositions

def hhi(composition):return sum(x*x for x in composition)

def generate(config_path,output_dir):
    spec=json.loads(Path(config_path).read_text());comp=spec['composition'];systematic=comp['systematic']
    sampling=systematic.get('sampling');detail=[];summary=[]
    for total in comp['candidate_power']:
        for cardinality in systematic['member_counts']:
            exhaustive=systematic_compositions(float(total),int(cardinality),float(systematic['power_step']),float(systematic['minimum_member_power']))
            selected=select_systematic_compositions(exhaustive,sampling)
            least=min(exhaustive,key=lambda x:(hhi(x),x)) if exhaustive else None
            most=max(exhaustive,key=lambda x:(hhi(x),x)) if exhaustive else None
            for rank,x in enumerate(selected,1):
                detail.append({'coalition_total':total,'cardinality':cardinality,'exhaustive_count':len(exhaustive),
                    'selected_count':len(selected),'selection_rank':rank,'composition':list(x),'hhi':hhi(x),
                    'minimum_member_power':min(x),'maximum_member_power':max(x),
                    'is_least_concentrated':x==least,'is_most_concentrated':x==most,
                    'contains_one_percent_member':any(abs(v-.01)<1e-12 for v in x),
                    'is_hhi_spaced_interior':x not in (least,most)})
            distinct_categories=len(set(x for x in (least,most) if x is not None))
            summary.append({'coalition_total':total,'cardinality':cardinality,'exhaustive_count':len(exhaustive),
                'selected_count':len(selected),'selected_compositions':[list(x) for x in selected],
                'selected_hhi':[hhi(x) for x in selected],
                'includes_least_concentrated':least in selected if least else False,
                'includes_most_concentrated':most in selected if most else False,
                'includes_one_percent_member':any(any(abs(v-.01)<1e-12 for v in x) for x in selected),
                'interior_representatives':sum(x not in (least,most) for x in selected),
                'collapsed_structural_categories':len(exhaustive)<3 or distinct_categories<2,
                'obvious_extreme_member_structure_missing':bool(exhaustive) and
                    (least not in selected or most not in selected or
                     (any(any(abs(v-.01)<1e-12 for v in x) for x in exhaustive) and
                      not any(any(abs(v-.01)<1e-12 for v in x) for x in selected)))})
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/'sampled_composition_cells.csv',summary);write_csv(out/'sampled_composition_representatives.csv',detail)
    by_k=Counter();by_total=Counter()
    for r in summary:by_k[str(r['cardinality'])]+=r['selected_count'];by_total[str(r['coalition_total'])]+=r['selected_count']
    report={'cells':len(summary),'selected_structures_per_authorized_environment':sum(r['selected_count'] for r in summary),
        'by_cardinality':dict(by_k),'by_coalition_total':dict(by_total),
        'cells_with_collapsed_categories':sum(r['collapsed_structural_categories'] for r in summary),
        'cells_missing_obvious_extreme_member_structure':sum(r['obvious_extreme_member_structure_missing'] for r in summary)}
    (out/'sampled_composition_audit.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args()
    print(json.dumps(generate(a.config,a.output_dir),indent=2))
