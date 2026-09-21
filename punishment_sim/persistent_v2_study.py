"""V2 conditional studies with shared, strictly validated baseline storage.

The historical paired statistical reducer is unchanged. It receives a complete
in-memory analysis cache and cannot fall back to historical mining.
"""
from dataclasses import asdict
import copy
import hashlib

from . import coalition as legacy
from .persistent_study import AnalysisCache, IncompleteStudyError, required_conditions
from .research_sweep import tpr_threshold
from .stage_b_validation import classify_margin
from .persistent_checkpoint import digest
from .persistent_v2 import (Rule, PersistentSimulation, model_version, configuration_id,
                            mining_cache_key, NETWORK_VERSION)
from .persistent_v2_checkpoint import validate_run, ConditionStore


def analyze(population, rule, repetitions, coalitions, tprs, fprs, runs,
            bootstrap_samples=2000, prior=None):
    """Recompute statistical outputs from complete conditional runs; never mine."""
    for (rep, strategy, flagged, C), result in runs.items():
        validate_run(result, population, rule, rep, strategy, flagged, C)
    return _analyze_validated(population, rule, repetitions, coalitions, tprs, fprs, runs,
                              bootstrap_samples, prior)


def _compact_result(result):
    """Keep statistics in memory; full terminal science remains in its checkpoint."""
    terminal = result["terminal"]
    checksum = digest(result)
    summary = {k: terminal[k] for k in ("reference_tip", "reference_height", "pending_publication_window", "boundary")}
    summary.update(condition_id=result["condition_id"], content_sha256=checksum,
        terminal_location="validated-condition-checkpoint", public_frontier_count=len(terminal["public_frontier"]),
        private_frontier_count=len(terminal["private_frontier"]),
        alternative_branch_count=len(terminal["alternative_branches"]))
    return {**{k: result[k] for k in ("status", "condition_id", "accepted_blocks", "actors", "member_opportunities", "member_activations", "natural_pairs")},
        "terminal": summary, "_raw_result_digest": checksum,
        "terminal_private_lead": len(terminal["target_private_chain"]),
        "terminal_uncredited_private_blocks": len(terminal["private_frontier"]),
        "terminal_omitted_selfish_share_bound": None}


def _analyze_validated(population, rule, repetitions, coalitions, tprs, fprs, runs,
                       bootstrap_samples=2000, prior=None):
    """Private reducer boundary: called only with validated, process-local data."""
    expected = {(rep, strategy, flagged, C) for rep in range(repetitions)
                for strategy, flagged, C in required_conditions(coalitions)}
    if set(runs) != expected:
        raise ValueError("conditional coverage mismatch")
    bridge = AnalysisCache()
    for (rep, strategy, flagged, C), result in runs.items():
        if result["status"] != "COMPLETE":
            raise IncompleteStudyError((rep, strategy, flagged, C), result)
        # The old reducer copies these three terminal scalars into its rows.
        # Replace the entire terminal section below; no old omission bound is
        # assigned to a persistent-fork result or used in an inference.
        adapted = result if "_raw_result_digest" in result else {**result, "terminal_private_lead": len(result["terminal"]["target_private_chain"]),
                   "terminal_uncredited_private_blocks": len(result["terminal"]["private_frontier"]),
                   "terminal_omitted_selfish_share_bound": None}
        bridge[legacy.mining_cache_key(population, rep, strategy, flagged, C)] = adapted
    output = legacy.study(population, repetitions, tprs, fprs, prior,
                          selected_coalitions=coalitions, simulation_cache=bridge)
    cid = configuration_id(population, rule)
    metadata = {"configuration_id": cid, "model_version": model_version(rule), "network_version": NETWORK_VERSION, **asdict(rule)}
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
    output["baseline_references"] = [{"repetition": rep, "strategy": strategy,
        "condition_id": runs[(rep, strategy, False, ())]["condition_id"],
        "content_sha256": (runs[(rep, strategy, False, ())]["_raw_result_digest"]
                           if "_raw_result_digest" in runs[(rep, strategy, False, ())] else digest(runs[(rep, strategy, False, ())]))}
        for rep in range(repetitions) for strategy in ("honest", "selfish")]
    output["meta"].update(mining_simulations=len(expected), mining_simulations_executed=0,
                          cache_hits=len(expected), cache_misses=0)
    return output


def study(population, repetitions, rule, tprs=(.9,), fprs=(.01,), selected_coalitions=None,
          prior=None, bootstrap_samples=2000, max_events=None, simulation_cache=None,
          checkpoint_dir=None, analyze_only=False, production=False):
    model_version(rule)
    if type(production) is not bool:
        raise ValueError("production must be boolean")
    if production and (checkpoint_dir is None or simulation_cache is not None):
        raise ValueError("production study requires a disk condition store and no full-result memory cache")
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
    store = ConditionStore(checkpoint_dir) if checkpoint_dir is not None else None
    runs, missing = {}, []
    # Validate every existing result before considering any new mining. A corrupt
    # entry is an error, not a cache miss; analysis-only has no mining fallback.
    for rep in range(repetitions):
        for strategy, flagged, C in required_conditions(coalitions):
            condition = (rep, strategy, flagged, C)
            key = mining_cache_key(population, rep, strategy, flagged, C, rule)
            present = key in cache
            result = cache[key] if present else None
            if present:
                validate_run(result, population, rule, rep, strategy, flagged, C)
            if not present and store is not None:
                result = store.load(population, rule, rep, strategy, flagged, C)
            if result is None:
                missing.append((condition, key))
            else:
                runs[condition] = _compact_result(result) if production else result
    if analyze_only and missing:
        raise ValueError("analysis-only requires complete validated v2 conditions; mining fallback disabled")
    for (rep, strategy, flagged, C), key in missing:
        result = PersistentSimulation(population, strategy, flagged, C, rule, max_events,
                                      repetition=rep, production=production).run()
        if result["status"] != "COMPLETE":
            raise IncompleteStudyError((rep, strategy, flagged, C), result)
        if store is not None:
            store.save(result, population, rule, rep, strategy, flagged, C)
        else:
            validate_run(result, population, rule, rep, strategy, flagged, C)
        if not production:
            cache[key] = result
        runs[(rep, strategy, flagged, C)] = _compact_result(result) if production else result
    output = _analyze_validated(population, rule, repetitions, coalitions, tprs, fprs, runs, bootstrap_samples, prior)
    output["meta"].update(mining_simulations_executed=len(missing), cache_misses=len(missing),
                          cache_hits=len(runs)-len(missing))
    if production:
        output["conditional_references"] = [{"repetition": rep, "strategy": s, "flagged": f,
            "active_coalition": list(C), "condition_id": r["condition_id"], "content_sha256": r["_raw_result_digest"]}
            for (rep, s, f, C), r in sorted(runs.items())]
        output["recording_mode"] = "production-v2"
    else:
        output["conditional_runs"] = [{"repetition": rep, "strategy": s, "flagged": f,
            "active_coalition": list(C), "result": copy.deepcopy(r)} for (rep, s, f, C), r in sorted(runs.items())]
    return output
