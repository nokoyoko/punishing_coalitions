"""Reuse measured .51 timing/packing evidence for independently enumerated scopes.

No mining, benchmarking, remote access, or production preparation occurs here.
"""
import json
from pathlib import Path
from punishment_sim.persistent_checkpoint import atomic_json, digest
from .plan_persistent_v2 import LABELS
from .project_persistent_v2_51pct import project

ROOT = Path(__file__).resolve().parents[1]


def project_cardinalities(scope):
    result = project(scope)
    benchmark = json.loads((ROOT/'docs/persistent_v2_51pct_benchmark.json').read_text())
    studies = {s['members']: s for s in benchmark['studies']}
    def weighted(values):
        return sum(count*6*(values[2]+(int(m)-2)*(values[6]-values[2])/4)
                   for m, count in scope['by_cardinality'].items())
    for phase in ('Phase I', 'Phase II'):
        storage = result['storage'][phase]
        rows = {m: s['phases'][phase]['exports']['row_counts'] for m, s in studies.items()}
        excluded = {'repetitions', 'equal_power_comparisons', 'six_variant_comparisons'}
        regular_rows = weighted({m: sum(v for k, v in counts.items() if k not in excluded)/studies[m]['scope']['top_level_rule_configurations']
                                 for m, counts in rows.items()})+sum(result['comparison_rows'].values())
        detailed_rows = weighted({m: counts['repetitions']/studies[m]['scope']['top_level_rule_configurations'] for m, counts in rows.items()})
        # Scope/role columns, additional pooled thresholds, exact native control plan.
        extra_regular = regular_rows*200 + scope['authorized_environments']*6*4*32768
        extra_detailed = detailed_rows*200
        extra_primary = scope['native_plan_bytes']+100*1024
        storage.update(scope_metadata_bytes_per_row_allowance=200,
                       scoped_threshold_row_allowance_bytes=32768,
                       additional_scoped_regular_exports_bytes=extra_regular,
                       additional_scoped_repetition_exports_bytes=extra_detailed,
                       native_plan_and_collection_control_bytes=extra_primary)
        storage['primary_dataset_bytes'] += extra_primary
        storage['regular_exports_bytes'] += extra_regular
        storage['detailed_repetition_exports_bytes'] += extra_detailed
        primary, regular, detail = (storage[k] for k in ('primary_dataset_bytes', 'regular_exports_bytes', 'detailed_repetition_exports_bytes'))
        storage.update(dataset_with_regular_exports_bytes=primary+regular, dataset_with_all_exports_bytes=primary+regular+detail,
                       planning_allowance_regular_bytes=2*(primary+regular), planning_allowance_all_exports_bytes=2*(primary+regular+detail))
    first, final = result['storage']['Phase I'], result['storage']['Phase II']
    final.update(incremental_primary_bytes_over_phase_I=final['primary_dataset_bytes']-first['primary_dataset_bytes'],
                 planning_allowance_regular_retaining_phase_I_exports_bytes=2*(final['dataset_with_regular_exports_bytes']+first['regular_exports_bytes']),
                 planning_allowance_all_retaining_phase_I_exports_bytes=2*(final['dataset_with_all_exports_bytes']+first['regular_exports_bytes']+first['detailed_repetition_exports_bytes']))
    result.pop('storage_change_vs_previous_060')
    result['runtime_ranges_ideal_28_worker_days'] = result.pop('runtime_ranges_ideal_28_core_days')
    result['timing_evidence'] = {'path': 'docs/persistent_v2_51pct_benchmark.json', 'sha256': digest(benchmark),
                               'new_benchmark_executed': False, 'native_mining_validation_and_reducers_unchanged': True,
                               'validation_contract': 'historical full replay; new lightweight checks and sampled policy are not timed'}
    result['projection_use'] = 'historical timing/storage illustration only; not a current production throughput or storage forecast'
    result['runtime_note'] = 'The user-reported Kinakuta rate contradicts ideal 28-worker scaling; measure concurrency before forecasting. ' + result['runtime_note']
    result['kinakuta_planning'] = {'logical_cpus': 32, 'physical_cores': 16, 'workers': 28,
                                  'hardware_source': 'user supplied; not remotely verified',
                                  'note': '28 workers use SMT/hyperthreads. Ideal 28-worker times are not guaranteed wall-clock times.',
                                  'illustrative_16_core_capacity_days': {phase: [days*28/16 for days in values]
                                      for phase, values in result['runtime_ranges_ideal_28_worker_days'].items()}}
    result['storage_note'] += '; native plan and 100 KiB collection control included; scoped CSV columns allowed 200 B/row; pooled threshold rows allowed 32 KiB each; temporary per-source strict merge catalog fits the 2x allowance; cross-scope combined exports require their own allowance; historical compact schema: new validation attestation/diagnostic storage is not measured'
    return result


def main():
    for label in LABELS:
        scope = json.loads((ROOT/f'docs/persistent_v2_{label}_scope.json').read_text())
        result = project_cardinalities(scope)
        atomic_json(ROOT/f'docs/persistent_v2_{label}_projection.json', result)
        print(json.dumps({label: {'runtime_days': result['runtime_ranges_ideal_28_worker_days'], 'storage': result['storage']}}, indent=2))


if __name__ == '__main__':
    main()
