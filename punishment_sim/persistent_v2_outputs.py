"""All persistent scientific outputs from paired vectors, never from block trees."""
import copy
import math
from collections import defaultdict
from itertools import combinations
from statistics import mean

from .coalition import paired_stats, status
from .persistent_v2_compact import terminal_summary
from .persistent_v2_sweep import grouped_thresholds
from .research_sweep import select_stage_c_candidates

METRICS = ("deterrence", "punishment_reduction", "baseline_credibility_margin",
           "deviation_credibility_margin", "credibility_slack")


def task_outputs(result, task, rule, spec):
    """Same reducer for full/debug and compact inputs; baseline payloads stay shared."""
    names = ("summary", "members", "detector", "repetitions", "tpr_thresholds")
    output = {name: copy.deepcopy(result[name]) for name in names}
    for name in names:
        for row in output[name]:
            row.update(family=task.family, structure=task.structure,
                candidate_population_power=task.candidate_total, base_seed=task.population.seed)
    for row in output["repetitions"]:
        C = row["coalition_members"]
        row.update(deterrence=row["U_H"]["target"]["payoff"]-row["U_SC"]["target"]["payoff"],
            punishment_reduction=row["U_S0"]["target"]["payoff"]-row["U_SC"]["target"]["payoff"],
            baseline_credibility_margin=min((row["U_SC"][j]["payoff"]-row["U_S0"][j]["payoff"] for j in C), default=0.),
            deviation_credibility_margin=min((row["U_SC"][j]["payoff"]-row["leaveouts"][j][j]["payoff"] for j in C), default=0.))
        row["credibility_slack"] = row["deviation_credibility_margin"]
        for name in ("terminal", "terminal_leaveouts"):
            row[name] = {key: value if value.get("schema") == "persistent-terminal-science-summary-v2-1"
                         else terminal_summary(value) for key, value in row[name].items()}
    for row in output["summary"]:
        row["member_hash_vector"] = [dict(task.population.candidates)[j] for j in row["members"]]
        row["credibility_slack"] = row["minimum_member_deviation_margin"]
    output["false_positive_costs"] = []
    seen = set()
    for row in output["detector"]:
        for actor, stat in sorted(row["false_positive_conditional_stats"].items()):
            key = (row["coalition"], actor, row["fpr"])
            if key in seen:
                continue
            seen.add(key)
            output["false_positive_costs"].append({"configuration_id": row["configuration_id"],
                "coalition": row["coalition"], "actor": actor, "fpr": row["fpr"],
                "conditional_loss": stat["mean"], "expected_cost": row["false_positive_expected_cost"][actor],
                "paired_statistics": stat, "status": status(stat, strict=True),
                "model_version": row["model_version"], "punishment_rule": row["punishment_rule"], "counter_fork_k": row["counter_fork_k"]})
    output["weakest_members"] = [{k: r[k] for k in ("configuration_id", "coalition", "weakest_member", "weakest_members",
        "minimum_member_deviation_margin", "model_version", "punishment_rule", "counter_fork_k")} for r in output["summary"]]
    output["minimal_winning_coalitions"] = [dict(r, minimality_scope="supplied coalitions within this population only")
        for r in output["summary"] if r["winning"] and not any(s["winning"] and set(s["members"]) < set(r["members"])
                                                              for s in output["summary"])]
    output["minimum_tested_thresholds"] = grouped_thresholds(output["summary"])
    index = {(r["configuration_id"], r["coalition"]): r for r in output["tpr_thresholds"]}
    output["stage_c_candidates"] = [dict(r, automatic_followup=False) for r in select_stage_c_candidates(
        output["summary"], index, {"tpr": spec["tpr"], "stage_c_max_candidates": 0})]
    output["boundary_diagnostics"] = []
    for summary in output["summary"]:
        rows = [r for r in output["repetitions"] if r["coalition"] == summary["coalition"]]
        terminals = [t for r in rows for t in [*r["terminal"].values(), *r["terminal_leaveouts"].values()]]
        output["boundary_diagnostics"].append({"configuration_id": summary["configuration_id"],
            "coalition": summary["coalition"], "conditions": len(terminals),
            "potentially_material_count": sum(t["boundary"]["potentially_material"] for t in terminals),
            "max_exposed_canonical_blocks": max(t["boundary"]["max_exposed_canonical_blocks"] for t in terminals),
            "max_public_frontier": max(t["frontier"]["public"]["count"] for t in terminals),
            "max_private_frontier": max(t["frontier"]["private"]["count"] for t in terminals),
            "bound_method": "unchanged conservative complete-frontier bounds; not sampling confidence intervals",
            "model_version": summary["model_version"], "counter_fork_k": summary["counter_fork_k"]})
    n = result["summary"][0]["repetition_count"]
    status_metadata = {"analysis_status": f"FINAL_{n}_REPETITIONS" if n == spec["repetitions"] else f"PRELIMINARY_{n}_REPETITIONS",
                       "analysis_repetitions": n, "planned_repetitions": spec["repetitions"]}
    for rows in output.values():
        for row in rows:
            row.update(status_metadata)
            for key in ("network_version", "model_version", "punishment_rule", "counter_fork_k"):
                row.setdefault(key, result[key])
    return output


def paired_comparisons(outputs, cross_rule=False):
    """Matched composition or rule comparisons, within one bounded environment group.

Input may contain different compositions/variants; only scientifically matched
rows are paired. Callers stream one environment/total group, not the full grid.
"""
    summaries = [r for out in outputs for r in out["summary"]]
    vectors = defaultdict(list)
    for out in outputs:
        for row in out["repetitions"]:
            vectors[(row["configuration_id"], row["coalition"])].append(row)
    results = []
    for left, right in combinations(sorted(summaries, key=lambda r: (r["configuration_id"], r["coalition"])), 2):
        matching = ("target_hash_power", "gamma", "natural_fork_rate", "accepted_block_target", "repetition_count", "base_seed",
                    "candidate_population_power", "analysis_status", "analysis_repetitions", "planned_repetitions")
        if any(left[k] != right[k] for k in matching) or not math.isclose(left["active_hash_power"], right["active_hash_power"], abs_tol=1e-12, rel_tol=0):
            continue
        same_rule = all(left[k] == right[k] for k in ("model_version", "counter_fork_k"))
        same_population = left["candidate_distribution"] == right["candidate_distribution"] and left["members"] == right["members"]
        if (cross_rule and (same_rule or not same_population)) or (not cross_rule and (not same_rule or same_population)):
            continue
        a = sorted(vectors[(left["configuration_id"], left["coalition"])], key=lambda r: r["repetition"])
        b = sorted(vectors[(right["configuration_id"], right["coalition"])], key=lambda r: r["repetition"])
        if [r["repetition"] for r in a] != [r["repetition"] for r in b]:
            raise ValueError("unmatched repetition vectors")
        for metric in METRICS:
            av, bv = [r[metric] for r in a], [r[metric] for r in b]
            stat = paired_stats([x-y for x, y in zip(av, bv)], av, bv)
            results.append({"left_configuration_id": left["configuration_id"], "right_configuration_id": right["configuration_id"],
                "left_coalition": left["coalition"], "right_coalition": right["coalition"], "metric": metric,
                "left_model_version": left["model_version"], "right_model_version": right["model_version"],
                "left_k": left["counter_fork_k"], "right_k": right["counter_fork_k"],
                "comparison": "punishment_rule" if cross_rule else "equal_power_composition", "paired_statistics": stat,
                "status": status(stat, strict=True), "pairing": "matched base seed and repetition, common v2 streams",
                **{k:left[k] for k in ("analysis_status", "analysis_repetitions", "planned_repetitions")}})
    return results
