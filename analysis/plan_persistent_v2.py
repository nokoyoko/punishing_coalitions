"""Exact core/optional-extension enumeration and identity audit; never mines."""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import canonical_json, digest
from punishment_sim.persistent_v2 import Rule
from punishment_sim.persistent_v2_shards import prepare_study, task_key
from punishment_sim.research_sweep import SweepTask

ROOT = Path(__file__).resolve().parents[1]
LABELS = ('core_2to4', 'extension_5', 'extension_6')
KEYS = ('populations', 'top_level_rule_configurations', 'before_reuse',
        'shared_baseline_simulations', 'after_reuse', 'accepted_block_work_after_reuse')


def enumerate_scope(design):
    cells, structures, environments = set(), set(), set()
    hashes = {}
    with tempfile.TemporaryDirectory(prefix='persistent-v2-plan-') as temporary:
        manifest = prepare_study(design, temporary)
        with sqlite3.connect(Path(temporary)/'plan.sqlite3') as plan:
            for pid, body in plan.execute('SELECT population_key,body FROM tasks ORDER BY population_key'):
                raw = json.loads(body)
                raw['population']['candidates'] = tuple(tuple(x) for x in raw['population']['candidates'])
                raw['population'] = Population(**raw['population'])
                raw['coalitions'] = tuple(tuple(c) for c in raw['coalitions'])
                task = SweepTask(**raw)
                p, m = task.population, len(task.population.candidates)
                cells.add((round(task.candidate_total, 2), m))
                structures.add((round(task.candidate_total, 2), tuple(h for _, h in p.candidates)))
                environments.add((p.target_hash_power, p.gamma, p.natural_fork_rate))
                identities = [task_key(task, Rule(**r)) for r in design['variants']]
                hashes.setdefault(str(m), hashlib.sha256()).update(canonical_json([pid, asdict(task), identities]).encode()+b'\n')
        plan_bytes = (Path(temporary)/'plan.sqlite3').stat().st_size
    scope = manifest['scope']
    scope.update(exact_enumeration=True, native_task_plan_sha256=manifest['plan_sha256'],
        native_plan_bytes=plan_bytes, configuration_sha256=digest(design),
        coalition_totals=design['composition']['candidate_power'],
        feasible_total_cardinality_cells=len(cells), sampled_structures_per_environment=len(structures),
        authorized_environments=len(environments),
        sampled_structures_per_total=dict(sorted(Counter(str(total) for total, shares in structures).items())),
        feasible_cells_by_cardinality=dict(sorted(Counter(str(m) for total, m in cells).items())),
        identity_sha256_by_cardinality={m: h.hexdigest() for m, h in sorted(hashes.items())},
        execution_phases={name: {'repetitions': bounds, 'unique_simulations': scope['after_reuse']//2,
            'before_reuse': scope['before_reuse']//2, 'shared_baselines': scope['shared_baseline_simulations']//2,
            'nominal_block_work': scope['accepted_block_work_after_reuse']//2}
            for name, bounds in (('Phase I', [1, 5]), ('Phase II', [6, 10]))},
        final_repetitions=10, adaptive_followup=False, historical_checkpoint_reuse=False)
    return scope


def main():
    designs = {label: json.loads((ROOT/f'configs/persistent_v2_{label}_1pct_10rep.json').read_text()) for label in LABELS}
    full = json.loads(canonical_json(designs['core_2to4']))
    full['composition']['systematic']['member_counts'] = [2, 3, 4, 5, 6]
    reference = json.loads((ROOT/'docs/persistent_v2_51pct_scope.json').read_text())
    full_scope = enumerate_scope(full)
    assert full_scope['native_task_plan_sha256'] == reference['native_task_plan_sha256']
    scopes = {}
    for label, design in designs.items():
        scope = enumerate_scope(design)
        for m, fingerprint in scope['identity_sha256_by_cardinality'].items():
            assert fingerprint == full_scope['identity_sha256_by_cardinality'][m]
        scope.update(configuration=f'configs/persistent_v2_{label}_1pct_10rep.json',
            dataset_role='core' if label == 'core_2to4' else label,
            cardinalities=design['composition']['systematic']['member_counts'],
            previous_2to6={k: reference[k] for k in KEYS},
            reductions_vs_2to6={k: {'absolute': reference[k]-scope[k], 'percent': 100*(reference[k]-scope[k])/reference[k]} for k in KEYS},
            identity_audit={'all_population_bodies_and_rule_task_ids_match_2to6': True,
                            'full_plan_matches_prior_51pct_plan': True,
                            'reference_identity_sha256_by_cardinality': full_scope['identity_sha256_by_cardinality']})
        (ROOT/f'docs/persistent_v2_{label}_scope.json').write_text(json.dumps(scope, indent=2)+'\n')
        scopes[label] = scope
        print(json.dumps({label: {k: scope[k] for k in (*KEYS, 'feasible_total_cardinality_cells', 'sampled_structures_per_environment', 'execution_phases')}}), flush=True)
    for key in KEYS:
        assert sum(s[key] for s in scopes.values()) == full_scope[key]


if __name__ == '__main__':
    main()
