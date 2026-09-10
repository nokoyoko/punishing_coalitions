"""Exact refined-design inventory from definitions; never runs mining or imports."""
import argparse
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from analysis.plan_oceanic_v4_rerun import analytical_spec
from punishment_sim.checkpoint_compatibility import check_spec_compatibility
from punishment_sim.coalition import MODEL_VERSION, Population, config_id
from punishment_sim.research_sweep import (
    generate_tasks, systematic_compositions, select_systematic_compositions)
from punishment_sim.theory import vanilla_selfish_mining_profitable


def hundredths(first,last):
    return [float(Decimal(i)/100) for i in range(first,last+1)]


def feasible(spec,alpha,total):
    residual=Decimal(1)-Decimal(str(alpha))-Decimal(str(total))
    return residual >= Decimal(str(spec['minimum_residual_power'])) and residual>0


def selected_cells(spec):
    grid=spec['composition'];systematic=grid['systematic'];cells=[];vectors={}
    for total in grid['candidate_power']:
        for members in systematic['member_counts']:
            all_vectors=systematic_compositions(total,members,systematic['power_step'],systematic['minimum_member_power'])
            chosen=select_systematic_compositions(all_vectors,systematic['sampling'])
            vectors[(total,members)]=chosen
            hhi=lambda xs:sum(Decimal(str(x))**2 for x in xs)
            least=min((hhi(x) for x in all_vectors),default=None)
            most=max((hhi(x) for x in all_vectors),default=None)
            levels=sorted({hhi(x) for x in chosen})
            cells.append({'candidate_total':total,'cardinality':members,
                'feasible_member_count':bool(all_vectors),'exhaustive_compositions':len(all_vectors),
                'selected_count':len(chosen),'selected_compositions':[list(x) for x in chosen],
                'selected_hhi':[float(hhi(x)) for x in chosen],
                'includes_least_concentrated':any(hhi(x)==least for x in chosen),
                'includes_most_concentrated':any(hhi(x)==most for x in chosen),
                'includes_one_percent_member':any(.01 in x for x in chosen),
                'distinct_selected_hhi_levels':len(levels),
                'distinct_available_hhi_levels':len({hhi(x) for x in all_vectors}),
                'interior_hhi_representatives':sum(least<hhi(x)<most for x in chosen) if chosen else 0})
    return cells,vectors


def refined_plan(spec,coarse_spec):
    grid=spec['composition']
    if grid['target_hash']!=hundredths(10,35) or grid['candidate_power']!=hundredths(5,60):
        raise ValueError('expected exact required one-percent power ranges')
    if spec.get('authorization_rule')!='analytic_vanilla_eyal_sirer':raise ValueError('refined design must authorize analytically')
    if spec['expected_model_version']!=MODEL_VERSION:raise ValueError('unexpected model version')
    repetitions=spec['repetitions'];source_repetitions=coarse_spec['repetitions']
    if type(repetitions) is not int or not 0<repetitions<=source_repetitions:
        raise ValueError('source does not contain the requested repetition prefix')
    # Audit the existing importer without reading any checkpoint or manifest.
    # Population overlap alone does not authorize reuse of a different design.
    try:
        check_spec_compatibility(coarse_spec,spec)
        importer_supported=True;importer_rejection=None
    except ValueError as exc:
        importer_supported=False;importer_rejection=str(exc)
    cells,vectors=selected_cells(spec)
    pairs=[(a,g) for a in grid['target_hash'] for g in grid['gamma'] if vanilla_selfish_mining_profitable(a,g)]
    # Coarse IDs are generated from the same unmodified scientific definitions,
    # using formula admission instead of reading historical result files.
    coarse_tasks=generate_tasks(analytical_spec(coarse_spec))[0]
    coarse_zero={config_id(asdict(t.population)):t for t in coarse_tasks if t.population.natural_fork_rate==0}
    reusable_ids=set();reused_simulations=0;source_overlap_simulations=0
    for cid,t in coarse_zero.items():
        p=t.population;total=t.candidate_total;k=len(p.candidates)
        if (p.target_hash_power,p.gamma) not in pairs or total not in grid['candidate_power']:continue
        if tuple(h for i,h in p.candidates) not in vectors[(total,k)]:continue
        replacement=Population(p.target_hash_power,p.candidates,p.gamma,0,spec['accepted_blocks'],spec['seed'])
        if config_id(asdict(replacement))!=cid:raise ValueError('overlap population identity changed')
        if spec['tpr']!=coarse_spec['tpr'] or spec['fpr']!=coarse_spec['fpr']:
            raise ValueError('overlap computation settings changed')
        # study seeds each independent repetition with population.seed + rep.
        # This is a potential prefix saving, never an import or truncation.
        reusable_ids.add(cid);reused_simulations+=(4+k)*repetitions
        source_overlap_simulations+=(4+k)*source_repetitions
    environments=[];counts=Counter();simulations=Counter();by_k=Counter()
    for alpha,gamma in pairs:
        totals=[c for c in grid['candidate_power'] if feasible(spec,alpha,c)]
        for rate in grid['natural_fork_rate']:
            n=sum(len(vectors[(c,k)]) for c in totals for k in grid['systematic']['member_counts'])
            sims=sum(len(vectors[(c,k)])*(4+k)*spec['repetitions'] for c in totals for k in grid['systematic']['member_counts'])
            environments.append({'target_hash_power':alpha,'gamma':gamma,'natural_fork_rate':rate,
                'valid_candidate_total_count':len(totals),'valid_candidate_totals':totals,
                'sampled_configurations':n,'mining_simulations':sims})
            counts[rate]+=n;simulations[rate]+=sims
            for k in grid['systematic']['member_counts']:by_k[k]+=sum(len(vectors[(c,k)]) for c in totals)
    total=sum(counts.values());sims=sum(simulations.values())
    supported_reuse_count=len(reusable_ids) if importer_supported else 0
    supported_reuse_simulations=reused_simulations if importer_supported else 0
    return {'scope_basis':'definition-only exact counts; no simulations or production checkpoint validation',
        'repetitions':repetitions,'accepted_blocks_per_simulation':spec['accepted_blocks'],
        'model_version':MODEL_VERSION,'target_grid':grid['target_hash'],'candidate_total_grid':grid['candidate_power'],
        'target_value_count':len(grid['target_hash']),'candidate_total_value_count':len(grid['candidate_power']),
        'authorized_target_gamma_pairs':[{'target_hash_power':a,'gamma':g} for a,g in pairs],
        'authorized_pair_count':len(pairs),'authorized_environment_count':len(environments),
        'composition_cells':len(cells),'feasible_composition_cells':sum(c['feasible_member_count'] for c in cells),
        'sampled_structures_across_total_cardinality_cells':sum(c['selected_count'] for c in cells),
        'top_level_configurations':total,'mining_simulations':sims,'accepted_block_work_units':sims*spec['accepted_blocks'],
        'by_lambda':[{'natural_fork_rate':r,'configurations':counts[r],'mining_simulations':simulations[r],
            'accepted_block_work_units':simulations[r]*spec['accepted_blocks']} for r in grid['natural_fork_rate']],
        'configurations_by_cardinality':dict(by_k),
        'current_importer_reuse':{'supported':importer_supported,'rejection':importer_rejection,
            'repetition_counts_match':repetitions==source_repetitions,
            'prefix_import_implemented':False,
            'configurations':supported_reuse_count,'mining_simulations':supported_reuse_simulations,
            'accepted_block_work_units':supported_reuse_simulations*spec['accepted_blocks']},
        'theoretical_reuse':{'source':'coarse explicit v3 lambda=0; requires a separately implemented and validated overlap/prefix importer',
            'source_repetitions':source_repetitions,'destination_repetitions':repetitions,
            'selected_repetition_indices':list(range(repetitions)),
            'selected_repetition_seeds':[spec['seed']+rep for rep in range(repetitions)],
            'source_mining_simulations':source_overlap_simulations,
            'source_accepted_block_work_units':source_overlap_simulations*spec['accepted_blocks'],
            'configurations':len(reusable_ids),'mining_simulations':reused_simulations,
            'accepted_block_work_units':reused_simulations*spec['accepted_blocks'],
            'task_ids_sha256':hashlib.sha256('\n'.join(sorted(reusable_ids)).encode()).hexdigest()},
        'fresh_v4':{'basis':'current importer; no unsupported prefix reuse deducted',
            'configurations':total-supported_reuse_count,'mining_simulations':sims-supported_reuse_simulations,
            'accepted_block_work_units':(sims-supported_reuse_simulations)*spec['accepted_blocks'],
            'zero_lambda_configurations':counts[0]-supported_reuse_count,
            'zero_lambda_mining_simulations':simulations[0]-supported_reuse_simulations,
            'zero_lambda_accepted_block_work_units':(simulations[0]-supported_reuse_simulations)*spec['accepted_blocks'],
            'positive_lambda_configurations':sum(n for r,n in counts.items() if r>0),
            'positive_lambda_mining_simulations':sum(n for r,n in simulations.items() if r>0),
            'positive_lambda_accepted_block_work_units':sum(n for r,n in simulations.items() if r>0)*spec['accepted_blocks']},
        'fresh_v4_if_validated_prefix_reuse':{'basis':'conditional only; overlap/prefix import is not implemented',
            'configurations':total-len(reusable_ids),'mining_simulations':sims-reused_simulations,
            'accepted_block_work_units':(sims-reused_simulations)*spec['accepted_blocks'],
            'new_zero_lambda_configurations':counts[0]-len(reusable_ids),
            'new_zero_lambda_mining_simulations':simulations[0]-reused_simulations,
            'new_zero_lambda_accepted_block_work_units':(simulations[0]-reused_simulations)*spec['accepted_blocks'],
            'positive_lambda_configurations':sum(n for r,n in counts.items() if r>0),
            'positive_lambda_mining_simulations':sum(n for r,n in simulations.items() if r>0),
            'positive_lambda_accepted_block_work_units':sum(n for r,n in simulations.items() if r>0)*spec['accepted_blocks']},
        'environments':environments,'composition_coverage':cells}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--coarse-config',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    report=refined_plan(json.loads(Path(args.config).read_text()),json.loads(Path(args.coarse_config).read_text()))
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('environments','composition_coverage')},indent=2))


if __name__=='__main__':main()
