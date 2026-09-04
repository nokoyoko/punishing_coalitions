#!/usr/bin/env python3
"""Generate the authoritative analytic admission domain for Stage B."""
import argparse,csv,json
from decimal import Decimal
from pathlib import Path

from analysis.stage_b_racefix import write_csv
from punishment_sim.theory import eyal_sirer_profitability_threshold,vanilla_selfish_mining_profitable

def generate(config_path,output_dir):
    spec=json.loads(Path(config_path).read_text()); aggregate=spec['aggregate']
    targets=sorted({float(x) for x in aggregate['target_hash']})
    gammas=sorted({float(x) for x in aggregate['gamma']})
    rates=sorted({float(x) for x in aggregate['natural_fork_rate']})
    domain=[]
    for alpha in targets:
        for gamma in gammas:
            threshold=eyal_sirer_profitability_threshold(gamma)
            profitable=vanilla_selfish_mining_profitable(alpha,gamma)
            domain.append({'target_hash_power':alpha,'gamma':gamma,'eyal_sirer_threshold':threshold,
                'margin_above_threshold':float(Decimal(str(alpha))-Decimal(str(threshold))),
                'profitable_vanilla_selfish_mining':profitable,
                'admission_basis':'strict alpha > (1-gamma)/(3-2gamma); alpha < 1/2'})
    authorized=[]
    for row in domain:
        if not row['profitable_vanilla_selfish_mining']:continue
        for rate in rates:
            authorized.append({'target_hash_power':row['target_hash_power'],'gamma':row['gamma'],
                'natural_fork_rate':rate,'eyal_sirer_threshold':row['eyal_sirer_threshold'],
                'margin_above_threshold':row['margin_above_threshold'],
                'profitable_vanilla_selfish_mining':True,'authorized_for_punishment_study':True,
                'admission_stage':'analytic_vanilla_eyal_sirer',
                'natural_fork_role':'simulation robustness only; not part of profitability admission'})
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/'eyal_sirer_profitability_domain.csv',domain)
    write_csv(out/'authorized_punishment_environments.csv',authorized)
    return {'target_gamma_pairs':len(domain),'profitable_target_gamma_pairs':sum(r['profitable_vanilla_selfish_mining'] for r in domain),
            'natural_fork_rates':rates,'authorized_punishment_environments':len(authorized)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args()
    print(json.dumps(generate(a.config,a.output_dir),indent=2))
