"""Storage/workload projections from completed local measurements, never mining."""
import json
from math import comb
from pathlib import Path
from statistics import mean

from punishment_sim.research_sweep import systematic_compositions, select_systematic_compositions
from punishment_sim.persistent_checkpoint import atomic_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    evidence = json.loads((ROOT / "docs/persistent_v2_compact_benchmark.json").read_text())
    if evidence["status"] != "COMPLETE":
        raise ValueError("fixed benchmark is incomplete")
    scope = json.loads((ROOT / "docs/persistent_v2_10rep_scope.json").read_text())
    # Frozen .60 comparison geometry; the current persistent design now ends at .51.
    design = json.loads((ROOT / "configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_1pct.json").read_text())
    studies = {s["members"]: s for s in evidence["studies"]}
    weighted = lambda per_task: sum(count*6*(per_task[2]+(int(m)-2)*(per_task[6]-per_task[2])/4)
                                    for m,count in scope["by_cardinality"].items())
    bytes_per_task = {m: s["storage_probe_per_1000_tasks"]["bytes"]/1000 for m,s in studies.items()}
    database_projection = weighted(bytes_per_task)
    catalog_per_task = {m: s["merge"]["catalog_bytes"]/s["scope"]["top_level_rule_configurations"] for m,s in studies.items()}
    catalog_projection = weighted(catalog_per_task)
    excluded = {"repetitions.csv", "equal_power_comparisons.csv", "six_variant_comparisons.csv"}
    regular_export_per_task = {m: sum(v for k,v in s["export_bytes"].items() if k not in excluded)/s["scope"]["top_level_rule_configurations"]
                               for m,s in studies.items()}
    repetition_export_per_task = {m: s["export_bytes"]["repetitions.csv"]/s["scope"]["top_level_rule_configurations"] for m,s in studies.items()}
    # Count composition pairs exactly from the same selected canonical compositions.
    comp = design["composition"]
    settings = comp["systematic"]
    per_total = {}
    for total in comp["candidate_power"]:
        compositions = {tuple(shares) for m in settings["member_counts"]
            for shares in select_systematic_compositions(systematic_compositions(total,m,settings["power_step"],settings["minimum_member_power"]),settings["sampling"])}
        per_total[str(total)] = len(compositions)
    environments = scope["populations"]//sum(per_total.values())
    assert environments*sum(per_total.values()) == scope["populations"]
    composition_pairs = sum(comb(count,2) for count in per_total.values())*environments*6
    comparison_rows = {"equal_power": composition_pairs*5, "cross_rule": scope["populations"]*comb(6,2)*5}
    measured_lines = []
    for members in (2,6):
        path = ROOT / f"results/persistent_v2_compact_local_benchmark/members-{members}/exports/six_variant_comparisons.csv"
        with path.open("rb") as stream:
            next(stream)
            measured_lines.extend(len(line) for line in stream)
    row_allowance = max(measured_lines)+256
    comparison_bytes = sum(comparison_rows.values())*row_allowance
    primary = database_projection+catalog_projection
    regular_exports = weighted(regular_export_per_task)+comparison_bytes
    repetitions_export = weighted(repetition_export_per_task)
    # Include every measured phase used by normal execution, excluding old-format
    # encoding performed solely to measure the comparison storage footprint.
    phases = ("mining_seconds", "native_validation_seconds", "extraction_seconds",
              "compact_validation_seconds", "aggregation_seconds", "serialization_write_seconds")
    total_seconds = {}
    # Scale the measured mixed per-unique-condition throughput by the exact
    # reused scope. This is explicitly an illustration, not a fitted model for
    # the full grid's different baseline/active/cardinality mix.
    base_ids = {r["condition_id"] for r in evidence["conditions"] if r["members"]==2 and not r["flagged"]}
    observed_unique = studies[2]["scope"]["after_reuse"]
    assert observed_unique == 520 and len(base_ids) == 40
    for phase in phases:
        total_seconds[phase] = studies[2]["metrics"].get(phase,0)/observed_unique*scope["after_reuse"]
    work_seconds = sum(total_seconds.values())
    six_per_condition = sum(studies[6]["metrics"].get(p,0) for p in phases)/studies[6]["scope"]["after_reuse"]
    two_per_condition = sum(studies[2]["metrics"].get(p,0) for p in phases)/observed_unique
    rows = evidence["conditions"]
    size_stats = {}
    for label, filtered in (("baseline",[r for r in rows if not r["flagged"]]),("policy_condition",[r for r in rows if r["flagged"]])):
        size_stats[label] = {field: {"min":min(r[field] for r in filtered), "mean":mean(r[field] for r in filtered), "max":max(r[field] for r in filtered)}
                            for field in ("compact_json_bytes","compact_compressed_bytes","old_full_checkpoint_bytes")}
    projection = {"basis": "exact scope; measured two/six-member records with linear cardinality interpolation; not measured full-grid resource requirements",
        "scope": scope, "size_measurements": size_stats, "sqlite_bytes_per_1000_tasks": {m:s["storage_probe_per_1000_tasks"]["bytes"] for m,s in studies.items()},
        "projected_shard_databases_bytes": database_projection, "projected_merged_catalog_bytes": catalog_projection,
        "projected_primary_dataset_bytes": primary, "projected_regular_plain_csv_bytes": regular_exports,
        "projected_optional_repetition_csv_bytes": repetitions_export,
        "projected_with_regular_exports_bytes": primary+regular_exports,
        "projected_with_all_plain_exports_bytes": primary+regular_exports+repetitions_export,
        "planning_space_with_regular_exports_bytes": 2*(primary+regular_exports),
        "planning_space_with_all_plain_exports_bytes": 2*(primary+regular_exports+repetitions_export),
        "planning_space_note": "2x planning allowance for workload variation, transient output space and headroom; not a proven upper bound or a claim of available capacity; backups require their own budget",
        "exact_comparison_row_counts": comparison_rows, "comparison_csv_row_allowance_bytes": row_allowance,
        "selected_compositions_per_total": per_total, "authorized_environments": environments,
        "projected_cpu_seconds_by_phase_from_two_member_mean": total_seconds,
        "measured_seconds_per_unique_condition_two_member": two_per_condition,
        "measured_seconds_per_unique_condition_six_member_ignore_selfish": six_per_condition,
        "projected_cpu_years": work_seconds/(365.25*86400),
        "ideal_28_core_days": work_seconds/(28*86400),
        "ideal_28_core_days_at_six_member_ignore_selfish_rate": six_per_condition*scope["after_reuse"]/(28*86400),
        "runtime_note": "mixed per-unique-condition throughput illustrations on the local CPU, perfect 28-way scaling; the full grid's baseline/active/cardinality mix differs; high-power/skewed cells, other hardware, stragglers, shared I/O, merge and exports can increase time",
        "measured_merge_seconds": {m:s["merge_wall_seconds"] for m,s in studies.items()},
        "measured_export_seconds": {m:s["export_wall_seconds"] for m,s in studies.items()},
        "capacity_verified": False, "production_ready_unconditionally": False}
    atomic_json(ROOT / "docs/persistent_v2_compact_projection.json", projection)
    print(json.dumps({k:v for k,v in projection.items() if k not in ("scope","selected_compositions_per_total","size_measurements")},indent=2))


if __name__ == "__main__":
    main()
