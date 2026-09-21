"""Conditional persistent-engine runs and reuse of the unchanged paired analysis.

The legacy study function is used only as an in-memory statistical reducer with
a complete, fail-closed cache. Legacy mining/checkpoints are never called/read.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import copy
import hashlib

from . import coalition as legacy
from .persistent import (MODEL_VERSION, PersistentSimulation, PunishmentSpec,
                         OstracismSpec, SelfishCounterSpec, model_version, configuration_id, mining_cache_key)
from .research_sweep import tpr_threshold
from .stage_b_validation import classify_margin
from .persistent_checkpoint import validate_run


class IncompleteStudyError(RuntimeError):
    def __init__(self, condition, result):
        self.condition, self.result = condition, result
        super().__init__(f"conditional simulation {condition}: {result['status']}")


class AnalysisCache(dict):
    def __contains__(self, key):
        if not super().__contains__(key):
            raise RuntimeError("analysis cannot fall back to historical mining")
        return True


def required_conditions(coalitions):
    conditions = {("honest", False, ()), ("selfish", False, ())}
    for coalition in coalitions:
        C = tuple(coalition)
        conditions.update((("honest", bool(C), C), ("selfish", bool(C), C)))
        conditions.update(("selfish", bool(rest), rest)
                          for j in C for rest in [tuple(i for i in C if i != j)])
    return sorted(conditions)


def analyze(population, rule, repetitions, coalitions, tprs, fprs, runs,
            bootstrap_samples=2000, prior=None):
    """Recompute statistical outputs from complete conditional runs; never mine."""
    expected = {(rep, strategy, flagged, C) for rep in range(repetitions)
                for strategy, flagged, C in required_conditions(coalitions)}
    if set(runs) != expected:
        raise ValueError("conditional coverage mismatch")
    bridge = AnalysisCache()
    for (rep, strategy, flagged, C), result in runs.items():
        if result["status"] != "COMPLETE":
            raise IncompleteStudyError((rep, strategy, flagged, C), result)
        if result["model_version"] != model_version(rule) or any(result[k] != v for k, v in asdict(rule).items()):
            raise ValueError("conditional model/rule mismatch")
        validate_run(result, population, rule, rep, strategy, flagged, C)
        # The old reducer copies these three terminal scalars into its rows.
        # Replace the entire terminal section below; no old omission bound is
        # assigned to a persistent-fork result or used in an inference.
        adapted = {**result, "terminal_private_lead": len(result["terminal"]["target_private_chain"]),
                   "terminal_uncredited_private_blocks": len(result["terminal"]["private_frontier"]),
                   "terminal_omitted_selfish_share_bound": None}
        bridge[legacy.mining_cache_key(population, rep, strategy, flagged, C)] = adapted
    output = legacy.study(population, repetitions, tprs, fprs, prior,
                          selected_coalitions=coalitions, simulation_cache=bridge)
    cid = configuration_id(population, rule)
    metadata = {"configuration_id": cid, "model_version": model_version(rule), **asdict(rule)}
    for collection in ("summary", "members", "detector", "repetitions"):
        for row in output[collection]:
            row.update(metadata)
    by_coalition = {tuple(C): [] for C in coalitions}
    for row in output["repetitions"]:
        rep, C = row["repetition"], tuple(row["coalition_members"])
        choices = {"U_H": ("honest", False, ()), "U_S0": ("selfish", False, ()),
                   "U_HF": ("honest", bool(C), C), "U_SC": ("selfish", bool(C), C)}
        row["terminal"] = {name: runs[(rep, *condition)]["terminal"] for name, condition in choices.items()}
        row["terminal_leaveouts"] = {j: runs[(rep, "selfish", bool(rest), rest)]["terminal"]
                                      for j in C for rest in [tuple(i for i in C if i != j)]}
        by_coalition[C].append(row)
    tpr_rows = []
    for C, rows in by_coalition.items():
        label = "|".join(C)
        seed = int(hashlib.sha256(f"{cid}:{label}".encode()).hexdigest()[:16], 16)
        tpr_rows.append({**metadata, "coalition": label,
                         **tpr_threshold(rows, bootstrap_samples, seed)})
    for summary in output["summary"]:
        members = [m for m in output["members"] if m["coalition"] == summary["coalition"]]
        for member in members:
            for kind in ("baseline", "deviation"):
                stat = member[kind]
                member[kind + "_refined"] = classify_margin(stat["mean"], stat["ci95_low"], stat["ci95_high"])
        effective = summary["effectiveness_status"] == "SUPPORTED"
        summary["weak_jointly_feasible"] = effective and all(
            m[k + "_refined"]["weak_supported"] for m in members for k in ("baseline", "deviation"))
        summary["strictly_jointly_feasible"] = effective and all(
            m[k + "_refined"]["strict_supported"] for m in members for k in ("baseline", "deviation"))
        rows = by_coalition[tuple(summary["members"])]
        summary["boundary_potentially_material"] = any(
            t["boundary"]["potentially_material"] for row in rows
            for t in [*row["terminal"].values(), *row["terminal_leaveouts"].values()])
    output.update(metadata)
    output["tpr_thresholds"] = tpr_rows
    output["meta"].update(mining_simulations=len(expected), mining_simulations_executed=0,
                          cache_hits=len(expected), cache_misses=0)
    return output


def study(population, repetitions, rule, tprs=(.9,), fprs=(.01,),
          selected_coalitions=None, prior=None, bootstrap_samples=2000,
          max_events=None, simulation_cache=None):
    if not isinstance(rule, (PunishmentSpec, OstracismSpec, SelfishCounterSpec)):
        raise ValueError("rule must be a PunishmentSpec, OstracismSpec or SelfishCounterSpec")
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("repetitions must be positive")
    if type(bootstrap_samples) is not int or bootstrap_samples < 0:
        raise ValueError("bootstrap_samples must be nonnegative")
    if not tprs or not fprs or any(not 0 <= x <= 1 for x in (*tprs, *fprs)):
        raise ValueError("nonempty detector probability grids required")
    if prior is not None and not 0 <= prior <= 1:
        raise ValueError("selfish_prior must be a probability")
    ids = tuple(i for i, _ in population.candidates)
    coalitions = sorted({tuple(sorted(C)) for C in (selected_coalitions if selected_coalitions is not None else [ids])})
    if not coalitions or any(len(C) != len(set(C)) or not set(C) <= set(ids) for C in coalitions):
        raise ValueError("invalid coalitions")
    cache = {} if simulation_cache is None else simulation_cache
    runs, misses = {}, 0
    for rep in range(repetitions):
        for strategy, flagged, C in required_conditions(coalitions):
            key = mining_cache_key(population, rep, strategy, flagged, C, rule)
            if key not in cache:
                sim = PersistentSimulation(replace(population, seed=population.seed+rep),
                                           strategy, flagged, C, rule, max_events)
                result = sim.run()
                if result["status"] != "COMPLETE":
                    raise IncompleteStudyError((rep, strategy, flagged, C), result)
                cache[key] = result
                misses += 1
            runs[(rep, strategy, flagged, C)] = cache[key]
    result = analyze(population, rule, repetitions, coalitions, tprs, fprs, runs, bootstrap_samples, prior)
    result["meta"].update(mining_simulations_executed=misses, cache_misses=misses,
                          cache_hits=len(runs)-misses)
    # Preserve the raw per-condition provenance/frontier as well as paired rows.
    result["conditional_runs"] = [{"repetition": rep, "strategy": s, "flagged": f,
                                   "active_coalition": list(C), "result": copy.deepcopy(r)}
                                  for (rep, s, f, C), r in sorted(runs.items())]
    return result
