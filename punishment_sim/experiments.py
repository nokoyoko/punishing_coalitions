from __future__ import annotations

from dataclasses import replace
import itertools
import math
from statistics import mean, stdev

from .config import SimulationConfig
from .simulation import Simulation


CONDITIONS = {
    "H_unflagged": ("honest", False),
    "H_flagged": ("honest", True),
    "S_unflagged": ("selfish", False),
    "S_flagged": ("selfish", True),
}


def _payoff_vector(run: dict) -> dict[str, float]:
    return {actor: values["accepted_revenue_share"]
            for actor, values in run["actors"].items()}


def combine_conditional(payoffs: dict[str, dict[str, float]],
                        tpr: float, fpr: float) -> dict:
    """Algebraically mix four conditional payoff vectors; no mining occurs."""
    actors = payoffs["H_unflagged"].keys()
    honest = {a: (1-fpr)*payoffs["H_unflagged"][a] + fpr*payoffs["H_flagged"][a]
              for a in actors}
    selfish = {a: (1-tpr)*payoffs["S_unflagged"][a] + tpr*payoffs["S_flagged"][a]
               for a in actors}
    target_h = honest["target"]
    target_s = selfish["target"]
    return {"tpr": tpr, "fpr": fpr, "expected_honest_payoffs": honest,
            "expected_selfish_payoffs": selfish,
            "expected_honest_target_payoff": target_h,
            "expected_selfish_target_payoff": target_s,
            "expected_selfish_advantage": target_s-target_h,
            "expected_deterrence_value": target_h-target_s}


def compare(config: SimulationConfig) -> dict:
    runs = {}
    for name, (strategy, flagged) in CONDITIONS.items():
        runs[name] = Simulation(replace(config, strategy=strategy,
                                        punishment_enabled=True,
                                        forced_label=flagged)).run()
    payoffs = {name: _payoff_vector(run) for name, run in runs.items()}
    mixed = combine_conditional(payoffs, config.tpr, config.fpr)
    return {"parameters": config.to_dict(), "conditional_payoffs": payoffs,
            "conditional_effects": {
                "honest_target_flagging_cost": payoffs["H_unflagged"]["target"] - payoffs["H_flagged"]["target"],
                "selfish_target_flagging_effect": payoffs["S_unflagged"]["target"] - payoffs["S_flagged"]["target"],
                "honest_coalition_flagging_cost": payoffs["H_unflagged"]["coalition"] - payoffs["H_flagged"]["coalition"],
                "selfish_coalition_flagging_effect": payoffs["S_unflagged"]["coalition"] - payoffs["S_flagged"]["coalition"]},
            "expected_payoffs": mixed, "conditional_runs": runs}


def sweep(spec: dict) -> list[dict]:
    base = spec.get("base", {})
    grid = spec["grid"]
    defaults = SimulationConfig()
    mining_names = ["target_hash_power", "coalition_hash", "gamma", "natural_fork_rate"]
    tprs = grid.get("tpr", [base.get("tpr", defaults.tpr)])
    fprs = grid.get("fpr", [base.get("fpr", defaults.fpr)])
    rows = []
    for values in itertools.product(
            *(grid.get(n, [base.get(n, getattr(defaults, n))]) for n in mining_names)):
        params = base | dict(zip(mining_names, values))
        if params["target_hash_power"] + params["coalition_hash"] >= 1:
            continue
        for repetition in range(spec.get("repetitions", 1)):
            cfg = SimulationConfig(**(params | {"seed": int(base.get("seed", 1)) + repetition}))
            result = compare(cfg)  # exactly four mining simulations here
            p = result["conditional_payoffs"]
            for tpr, fpr in itertools.product(tprs, fprs):
                mixed = combine_conditional(p, tpr, fpr)
                rows.append({**{n: getattr(cfg, n) for n in mining_names},
                    "tpr": tpr, "fpr": fpr, "seed": cfg.seed, "repetition": repetition,
                    "H_unflagged_target": p["H_unflagged"]["target"],
                    "H_flagged_target": p["H_flagged"]["target"],
                    "S_unflagged_target": p["S_unflagged"]["target"],
                    "S_flagged_target": p["S_flagged"]["target"],
                    "expected_honest_target_payoff": mixed["expected_honest_target_payoff"],
                    "expected_selfish_target_payoff": mixed["expected_selfish_target_payoff"],
                    "expected_selfish_advantage": mixed["expected_selfish_advantage"],
                    "expected_deterrence_value": mixed["expected_deterrence_value"]})
    return rows


def aggregate(rows: list[dict], metric: str = "expected_selfish_target_payoff") -> list[dict]:
    keys = ("target_hash_power", "coalition_hash", "gamma", "natural_fork_rate", "tpr", "fpr")
    groups: dict[tuple, list[float]] = {}
    for row in rows:
        groups.setdefault(tuple(row[k] for k in keys), []).append(row[metric])
    out = []
    for values, samples in groups.items():
        se = stdev(samples) / math.sqrt(len(samples)) if len(samples) > 1 else None
        out.append(dict(zip(keys, values)) | {"metric": metric, "n": len(samples),
                   "mean": mean(samples), "standard_error": se,
                   "ci95_low": mean(samples)-1.96*se if se is not None else None,
                   "ci95_high": mean(samples)+1.96*se if se is not None else None})
    return out
