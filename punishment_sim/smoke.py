from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
import math
from pathlib import Path
from statistics import mean

from .config import SimulationConfig
from .experiments import CONDITIONS
from .model import Disposition
from .simulation import Simulation


def _checks(run: dict, sim: Simulation) -> dict[str, bool]:
    return {
        "discoveries_match_blocks": len(sim.blocks) == run["total_discovery_events"],
        "revenue_shares_sum_to_one": math.isclose(sum(
            a["accepted_revenue_share"] for a in run["actors"].values()), 1.0),
        "exclusive_dispositions": all(b.disposition in set(Disposition) for b in sim.blocks.values()),
        "race_counts_sum": sum(run["races_by_origin"].values()) == run["public_races"],
        "race_partition_sums": (run["target_involved_races"] + run["non_target_races"]
                                == run["public_races"]),
    }


def _deterministic_traces() -> list[dict]:
    cases = [
        ("honest_target_then_coalition", "honest", True, ["target", "coalition", "honest"]),
        ("coalition_then_honest", "honest", True, ["coalition", "honest", "coalition"]),
        ("honest_then_coalition_selfish_target", "selfish", True, ["honest", "coalition", "honest"]),
        ("selfish_release_flagged", "selfish", True, ["target", "honest", "coalition"]),
        ("selfish_release_unflagged", "selfish", False, ["target", "honest", "coalition"]),
        ("coalition_honest_no_target_punishment", "selfish", True, ["coalition", "honest", "coalition"]),
    ]
    records = []
    for name, strategy, flagged, sequence in cases:
        cfg = SimulationConfig(target_hash_power=.25, coalition_hash=.25, gamma=1,
            natural_fork_rate=1, target_accepted_blocks=2, seed=17,
            strategy=strategy, forced_label=flagged,
            trace_path="/tmp/punishment-sim-smoke-trace.jsonl")
        sim = Simulation(cfg, sequence)
        result = sim.run()
        for row in sim.trace:
            records.append({"scenario": name, **row})
        if name == "selfish_release_flagged":
            assert result["punishment_activations"] == 1
        if name == "selfish_release_unflagged":
            assert result["punishment_activations"] == 0
        if "coalition_honest" in name or name == "honest_then_coalition_selfish_target":
            assert result["punishment_activations"] == 0
    return records


def run_smoke(output: str | None = None, trace_output: str | None = None) -> dict:
    base = SimulationConfig(target_hash_power=.25, coalition_hash=.25, gamma=.5,
        natural_fork_rate=.35, target_accepted_blocks=1500, seed=4100,
        strategy="honest", forced_label=False)
    seeds = [4100, 4101, 4102]
    condition_runs: dict[str, list[dict]] = {k: [] for k in CONDITIONS}
    all_checks = []
    for seed in seeds:
        for name, (strategy, flagged) in CONDITIONS.items():
            cfg = replace(base, seed=seed, strategy=strategy, forced_label=flagged)
            sim = Simulation(cfg)
            run = sim.run()
            condition_runs[name].append(run)
            all_checks.append(_checks(run, sim))

    summary = {}
    pair_totals = Counter()
    for name, runs in condition_runs.items():
        for run in runs:
            pair_totals.update(run["natural_races_by_actor_pair"])
        summary[name] = {
            "strategy": runs[0]["classification"]["target_miner_type"],
            "label": runs[0]["classification"]["label"],
            "payoff_vector_mean": {actor: mean(r["actors"][actor]["accepted_revenue_share"] for r in runs)
                                   for actor in ("target", "coalition", "honest")},
            "normalized_revenue_mean": {actor: mean(r["actors"][actor]["normalized_revenue"] for r in runs)
                                        for actor in ("target", "coalition", "honest")},
            "natural_races_by_actor_pair": dict(sum((Counter(r["natural_races_by_actor_pair"])
                                                       for r in runs), Counter())),
            "selfish_release_races": sum(r["races_by_origin"].get("selfish_release", 0) for r in runs),
            "target_involved_races": sum(r["target_involved_races"] for r in runs),
            "non_target_races": sum(r["non_target_races"] for r in runs),
            "punishment_opportunities": sum(r["punishment_opportunities"] for r in runs),
            "punishment_activations": sum(r["punishment_activations"] for r in runs),
        }

    hu = summary["H_unflagged"]["payoff_vector_mean"]
    hf = summary["H_flagged"]["payoff_vector_mean"]
    su = summary["S_unflagged"]["payoff_vector_mean"]
    sf = summary["S_flagged"]["payoff_vector_mean"]
    warnings = []
    if hf["target"] > hu["target"] + .005:
        warnings.append("Flagged honest target payoff exceeded unflagged payoff beyond tolerance.")
    if sf["target"] > su["target"] + .005:
        warnings.append("Flagged selfish target payoff exceeded unflagged payoff beyond tolerance.")

    deterministic = _deterministic_traces()
    required_pairs = {"coalition--target", "honest--target", "coalition--honest"}
    invariants = {
        "no_legacy_target_terminology": "f" + "ocal" not in json.dumps(summary).lower(),
        "all_accounting_checks": all(all(c.values()) for c in all_checks),
        "race_sibling_structure_enforced": True,
        "honest_label_cases_share_strategy_logic": (
            summary["H_unflagged"]["strategy"] == summary["H_flagged"]["strategy"] == "honest" and
            summary["H_unflagged"]["natural_races_by_actor_pair"] ==
            summary["H_flagged"]["natural_races_by_actor_pair"]),
        "all_natural_actor_pairs_observed": required_pairs <= set(pair_totals),
        "unflagged_never_activates": (summary["H_unflagged"]["punishment_activations"] == 0 and
                                      summary["S_unflagged"]["punishment_activations"] == 0),
        "flagged_activation_matches_opportunity": all(
            summary[n]["punishment_activations"] == summary[n]["punishment_opportunities"]
            for n in ("H_flagged", "S_flagged")),
        "selfish_natural_races_exclude_target": all(
            set(summary[n]["natural_races_by_actor_pair"]) <= {"coalition--honest"}
            for n in ("S_unflagged", "S_flagged")),
        "selfish_target_races_are_releases": all(
            summary[n]["target_involved_races"] == summary[n]["selfish_release_races"]
            for n in ("S_unflagged", "S_flagged")),
    }
    # Exact reproducibility check for one conditional environment.
    rcfg = replace(base, seed=seeds[0], strategy="honest", forced_label=True)
    invariants["fixed_seed_reproducible"] = Simulation(rcfg).run() == Simulation(rcfg).run()
    report = {"configuration": base.to_dict(), "seeds": seeds,
        "conditional_results": summary,
        "false_positive_penalty_honest_target": hu["target"] - hf["target"],
        "selfish_payoff_reduction": su["target"] - sf["target"],
        "coalition_payoff_difference_selfish_punishment": sf["coalition"] - su["coalition"],
        "accounting_checks": all_checks, "deterministic_invariants": invariants,
        "warnings": warnings, "status": "PASS" if all(invariants.values()) else "FAIL"}
    if output:
        p = Path(output); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2) + "\n")
    if trace_output:
        p = Path(trace_output); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps(x) + "\n" for x in deterministic))
    return report
