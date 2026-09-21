"""Exact .51 scope with measured 5+5 runtime/storage, no mining."""
import json
from math import comb
from pathlib import Path
from statistics import mean
from punishment_sim.persistent_checkpoint import atomic_json

ROOT=Path(__file__).resolve().parents[1]
PHASES=('mining_seconds','native_validation_seconds','extraction_seconds','compact_validation_seconds','aggregation_seconds','serialization_write_seconds')


def project(scope):
    b=json.loads((ROOT/'docs/persistent_v2_51pct_benchmark.json').read_text())
    if b['status']!='COMPLETE':raise ValueError('benchmark incomplete')
    old=json.loads((ROOT/'docs/persistent_v2_compact_projection.json').read_text())
    previous=json.loads((ROOT/'docs/persistent_v2_compact_benchmark.json').read_text())
    studies={s['members']:s for s in b['studies']}
    tasks=scope['top_level_rule_configurations'];N=scope['after_reuse']
    def weighted(values):
        return sum(count*6*(values[2]+(int(m)-2)*(values[6]-values[2])/4) for m,count in scope['by_cardinality'].items())
    comparison_rows={'equal_power':sum(comb(v,2) for v in scope['sampled_structures_per_total'].values())*scope['authorized_environments']*6*5,
                     'cross_rule':scope['populations']*comb(6,2)*5}
    storage={};runtime={};before_after={}
    for phase in ('Phase I','Phase II'):
        n=5 if phase=='Phase I' else 10
        per_task={m:s['phases'][phase]['storage']['bytes_per_1000_tasks']/1000 for m,s in studies.items()}
        db=weighted(per_task)
        catalogs=weighted({m:s['phases'][phase]['merge']['catalog_bytes']/s['scope']['top_level_rule_configurations'] for m,s in studies.items()})
        if phase=='Phase II':catalogs+=storage['Phase I']['catalogs_bytes'] # retain both snapshots
        row_allowance=max(s['phases'][phase]['max_comparison_csv_row_bytes'] for s in studies.values())+256
        excluded={'repetitions.csv','equal_power_comparisons.csv','six_variant_comparisons.csv'}
        regular=weighted({m:sum(v for k,v in s['phases'][phase]['export_bytes'].items() if k not in excluded)/s['scope']['top_level_rule_configurations'] for m,s in studies.items()})+sum(comparison_rows.values())*row_allowance
        detailed=weighted({m:s['phases'][phase]['export_bytes']['repetitions.csv']/s['scope']['top_level_rule_configurations'] for m,s in studies.items()})
        primary=db+catalogs
        storage[phase]={'completed_repetitions':n,'shard_databases_bytes':db,'catalogs_bytes':catalogs,'primary_dataset_bytes':primary,
                        'regular_exports_bytes':regular,'detailed_repetition_exports_bytes':detailed,
                        'dataset_with_regular_exports_bytes':primary+regular,'dataset_with_all_exports_bytes':primary+regular+detailed,
                        'planning_allowance_regular_bytes':2*(primary+regular),'planning_allowance_all_exports_bytes':2*(primary+regular+detailed),
                        'comparison_row_allowance_bytes':row_allowance}
        runtime[phase]={}
        for m,s in studies.items():
            metric=s['phases'][phase]['metrics'];units=metric['mining_simulations_executed']
            phase_seconds={p:metric.get(p,0)/units*(N//2) for p in PHASES}
            seconds=sum(phase_seconds.values())
            runtime[phase][str(m)]={'measured_unique_conditions':units,'measured_seconds_per_condition':sum(metric.get(p,0) for p in PHASES)/units,
                                  'unique_simulations':N//2,'nominal_block_work':N//2*30000,'projected_single_worker_seconds':seconds,
                                  'single_worker_days':seconds/86400,'ideal_28_core_days':seconds/(28*86400),'seconds_by_phase':phase_seconds}
    runtime['Full']={}
    for m,s in studies.items():
        full=sum(runtime[phase][str(m)]['projected_single_worker_seconds'] for phase in ('Phase I','Phase II'))
        runtime['Full'][str(m)]={'unique_simulations':N,'nominal_block_work':N*30000,'single_worker_seconds':full,
                                'single_worker_days':full/86400,'ideal_28_core_days':full/(28*86400)}
        observed={p:sum(s['phases'][phase]['metrics'].get(p,0) for phase in ('Phase I','Phase II')) for p in PHASES}
        total=sum(observed.values());count=s['scope']['after_reuse']
        prior=next(t for t in previous['studies'] if t['members']==m);oldtotal=sum(prior['metrics'].get(p,0) for p in PHASES)
        before_after[str(m)]={'before_validation_seconds_per_condition':prior['metrics']['native_validation_seconds']/count,
                             'after_validation_seconds_per_condition':observed['native_validation_seconds']/count,
                             'before_total_phase_seconds_per_condition':oldtotal/count,'after_total_phase_seconds_per_condition':total/count,
                             'before_validation_fraction':prior['metrics']['native_validation_seconds']/oldtotal,
                             'after_validation_fraction':observed['native_validation_seconds']/total,
                             'after_mining_fraction':observed['mining_seconds']/total,'after_extraction_fraction':observed['extraction_seconds']/total}
    component_summary={}
    for variant in ('unoptimized','comparison','reactions','debug','metadata','all'):
        ref=sum(c['timings']['reference']['median_seconds'] for c in b['validation_components'])
        current=sum(c['timings'][variant]['median_seconds'] for c in b['validation_components'])
        component_summary[variant]={'reference_sum_median_seconds':ref,'candidate_sum_median_seconds':current,'relative_change_percent':100*(current/ref-1),
                                    'relative_change_vs_unoptimized_current_percent':100*(current/sum(c['timings']['unoptimized']['median_seconds'] for c in b['validation_components'])-1)}
    final=storage['Phase II'];first=storage['Phase I']
    final['incremental_primary_bytes_over_phase_I']=final['primary_dataset_bytes']-first['primary_dataset_bytes']
    final['planning_allowance_regular_retaining_phase_I_exports_bytes']=2*(final['dataset_with_regular_exports_bytes']+first['regular_exports_bytes'])
    final['planning_allowance_all_retaining_phase_I_exports_bytes']=2*(final['dataset_with_all_exports_bytes']+first['regular_exports_bytes']+first['detailed_repetition_exports_bytes'])
    comparison={key:{'old_bytes':old[oldkey],'new_bytes':final[key],
                     'percent_change':100*(final[key]/old[oldkey]-1)}
        for key,oldkey in [('primary_dataset_bytes','projected_primary_dataset_bytes'),
                          ('planning_allowance_regular_bytes','planning_space_with_regular_exports_bytes'),
                          ('planning_allowance_all_exports_bytes','planning_space_with_all_plain_exports_bytes')]}
    output={'scope':scope,'runtime_ranges_ideal_28_core_days':{phase:[min(v['ideal_28_core_days'] for v in values.values()),max(v['ideal_28_core_days'] for v in values.values())] for phase,values in runtime.items()},'runtime':runtime,'storage':storage,'before_after':before_after,'paired_validation_components':component_summary,
            'comparison_rows':comparison_rows,'storage_change_vs_previous_060':comparison,
            'runtime_note':'measured mixed two-member all-rule and six-member ignore/selfish rates; perfect scaling; not confidence bounds; excludes final merge/export, setup and untimed bookkeeping; high-power/skewed cells and target hardware remain unmeasured',
            'storage_note':'actual 1000-task packing; cardinality interpolation; final primary retains preliminary records and both catalogs; export allowances normally refer to the selected current snapshot; 2x headroom is a planning allowance, not an upper bound; backups additional',
            'capacity_verified':False,'production_launched':False}
    return output


def main():
    output = project(json.loads((ROOT/'docs/persistent_v2_51pct_scope.json').read_text()))
    atomic_json(ROOT/'docs/persistent_v2_51pct_projection.json',output)
    print(json.dumps({k:v for k,v in output.items() if k not in ('scope','storage_note','runtime_note')},indent=2))


if __name__=='__main__':main()
