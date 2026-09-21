"""Exact local .51 enumeration and 5+5 planning; no mining or historical reuse."""
import json
from pathlib import Path
import tempfile
from collections import Counter

from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2_shards import prepare_study, task_rows

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "configs/persistent_v2_1pct_10rep.json"
    design = json.loads(path.read_text())
    cells, structures, environments = set(), set(), set()
    with tempfile.TemporaryDirectory(prefix="persistent-v2-plan-") as temporary:
        manifest = prepare_study(design, temporary)
        for shard in range(design["shard_count"]):
            for task in task_rows(temporary, manifest, shard):
                p = task.population
                cells.add((round(task.candidate_total, 2), len(p.candidates)))
                structures.add((round(task.candidate_total, 2), tuple(h for _, h in p.candidates)))
                environments.add((p.target_hash_power, p.gamma, p.natural_fork_rate))
    scope = manifest["scope"]
    previous = json.loads((ROOT / "docs/persistent_v2_10rep_scope.json").read_text())
    keys = ("populations", "top_level_rule_configurations", "before_reuse", "shared_baseline_simulations", "after_reuse", "accepted_block_work_after_reuse")
    scope.update(configuration=str(path.relative_to(ROOT)), configuration_sha256=digest(design),
        exact_enumeration=True, native_task_plan_sha256=manifest["plan_sha256"],
        coalition_totals=design["composition"]["candidate_power"], feasible_total_cardinality_cells=len(cells),
        sampled_structures_per_environment=len(structures), authorized_environments=len(environments),
        sampled_structures_per_total=dict(sorted(Counter(str(total) for total, shares in structures).items())),
        feasible_cells_by_cardinality=dict(sorted(Counter(str(m) for total,m in cells).items())),
        previous_060={k:previous[k] for k in keys},
        reductions={k:{"absolute":previous[k]-scope[k],"percent":100*(previous[k]-scope[k])/previous[k]} for k in keys},
        execution_phases={name:{"repetitions":bounds,"unique_simulations":scope["after_reuse"]//2,
            "shared_baselines":scope["shared_baseline_simulations"]//2,
            "nominal_block_work":scope["accepted_block_work_after_reuse"]//2}
            for name,bounds in (("Phase I",[1,5]),("Phase II",[6,10]))},
        final_repetitions=10, adaptive_followup=False, historical_checkpoint_reuse=False)
    out = ROOT / "docs/persistent_v2_51pct_scope.json"
    out.write_text(json.dumps(scope, indent=2)+"\n")
    print(json.dumps({k:v for k,v in scope.items() if k not in ("populations_by_shard","sampled_structures_per_total","coalition_totals")},indent=2))


if __name__ == "__main__":
    main()
