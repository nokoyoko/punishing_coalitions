"""Isolated local runner/analysis entry point for the persistent model.

No production grid is supplied. Nothing runs on import. The historical CLI,
sharder, task IDs, schemas, outputs and checkpoint importers are not modified.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .persistent import (MODEL_VERSION, PunishmentSpec, OstracismSpec, SelfishCounterSpec,
                         model_version, configuration_id, identity)
from .persistent_checkpoint import atomic_json, digest, read_checkpoint, write_checkpoint
from .persistent_study import IncompleteStudyError, analyze, required_conditions, study
from .research_sweep import generate_tasks as population_tasks, _write_csv


@dataclass(frozen=True)
class PersistentTask:
    population_task: object
    rule: PunishmentSpec | OstracismSpec | SelfishCounterSpec

    @property
    def configuration_id(self):
        return configuration_id(self.population_task.population, self.rule)

    @property
    def task_id(self):
        return digest({**identity(self.population_task.population, self.rule),
                       "coalitions": self.population_task.coalitions})[:24]


def prepare(spec):
    spec = dict(spec)
    supported = {"expected_model_version", "punishment_rule", "counter_fork_k", "accepted_blocks",
                 "repetitions", "seed", "bootstrap_samples", "tpr", "fpr", "selfish_prior",
                 "authorization_rule", "authorized_environment_file", "authorized_environment_triplets",
                 "aggregate", "composition", "minimum_residual_power"}
    if set(spec) - supported:
        raise ValueError("unsupported persistent configuration fields: " + ", ".join(sorted(set(spec) - supported)))
    rule = (SelfishCounterSpec(counter_fork_k=spec.get("counter_fork_k")) if spec.get("punishment_rule") == "selfish"
            else OstracismSpec(counter_fork_k=spec.get("counter_fork_k")) if spec.get("punishment_rule") == "ignore"
            else PunishmentSpec(spec.get("punishment_rule"), spec.get("counter_fork_k")))
    if spec.get("expected_model_version") != model_version(rule):
        raise ValueError("explicit persistent expected_model_version required; petty configs are ineligible")
    spec.setdefault("accepted_blocks", 30000)
    spec.setdefault("repetitions", 20)
    spec.setdefault("seed", 41000)
    spec.setdefault("bootstrap_samples", 2000)
    for field in ("accepted_blocks", "repetitions"):
        if type(spec[field]) is not int or spec[field] < 1:
            raise ValueError(field + " must be a positive integer")
    if type(spec["seed"]) is not int:
        raise ValueError("seed must be an integer")
    if type(spec["bootstrap_samples"]) is not int or spec["bootstrap_samples"] < 0:
        raise ValueError("bootstrap_samples must be nonnegative")
    for field in ("tpr", "fpr"):
        if not spec.get(field) or any(not 0 <= x <= 1 for x in spec[field]):
            raise ValueError("nonempty " + field + " probability grid required")
    prior = spec.get("selfish_prior")
    if prior is not None and not 0 <= prior <= 1:
        raise ValueError("selfish_prior must be a probability")
    # Admission lists belong to the historical run/engine. Authorization via
    # the existing analytic formula remains possible for an explicitly supplied
    # future design, without importing any historical mining result.
    if spec.get("authorized_environment_file"):
        raise ValueError("stored historical environment admission lists are unsupported")
    tasks, _, _ = population_tasks(spec)
    if not tasks:
        raise ValueError("configuration generates no valid populations")
    return spec, [PersistentTask(task, rule) for task in tasks]


def scope(spec):
    spec, tasks = prepare(spec)
    per_lambda = {}
    for task in tasks:
        ptask = task.population_task
        count = len(required_conditions(ptask.coalitions)) * spec["repetitions"]
        rate = str(ptask.population.natural_fork_rate)
        cell = per_lambda.setdefault(rate, {"top_level_configurations": 0, "mining_simulations": 0,
                                           "accepted_block_work_units": 0})
        cell["top_level_configurations"] += 1
        cell["mining_simulations"] += count
        cell["accepted_block_work_units"] += count * spec["accepted_blocks"]
    return {"model_version": model_version(tasks[0].rule), **asdict(tasks[0].rule),
            "repetitions": spec["repetitions"], "accepted_block_target": spec["accepted_blocks"],
            "top_level_configurations": len(tasks),
            "mining_simulations": sum(x["mining_simulations"] for x in per_lambda.values()),
            "accepted_block_work_units": sum(x["accepted_block_work_units"] for x in per_lambda.values()),
            "work_interpretation": "nominal reference-height targets, not discovery counts; atomic releases may overshoot",
            "per_lambda": per_lambda, "historical_checkpoint_reuse": False}


def manifest(spec, task):
    return {"model_version": model_version(task.rule), **asdict(task.rule), "specification_sha256": digest(spec),
            "task_id": task.task_id, "configuration_id": task.configuration_id,
            "population": asdict(task.population_task.population),
            "coalitions": task.population_task.coalitions, "repetitions": spec["repetitions"],
            "seed_schedule": "population.seed + repetition (zero based)",
            "rng_namespace": model_version(task.rule)}


def unpack_conditions(rows):
    runs = {}
    for row in rows:
        if type(row["repetition"]) is not int or type(row["flagged"]) is not bool:
            raise ValueError("invalid conditional repetition/flag")
        key = (row["repetition"], row["strategy"], row["flagged"], tuple(row["active_coalition"]))
        if key in runs:
            raise ValueError("duplicate conditional checkpoint row")
        runs[key] = row["result"]
    return runs


def analysis_group_key(row):
    """Never pool punishment parameters or different observation designs."""
    return (row["model_version"], row["punishment_rule"], row["counter_fork_k"],
            row["target_hash_power"], row["gamma"], row["natural_fork_rate"],
            row["accepted_block_target"], row["repetition_count"], row["structure"])


def grouped_thresholds(rows):
    groups = {}
    for row in rows:
        groups.setdefault(analysis_group_key(row), []).append(row)
    output = []
    for key, group in sorted(groups.items()):
        common = dict(zip(("model_version", "punishment_rule", "counter_fork_k", "target_hash_power",
                           "gamma", "natural_fork_rate", "accepted_block_target", "repetition_count", "structure"), key))
        for name, predicate in (
            ("effective", lambda r: r["effectiveness_status"] == "SUPPORTED"),
            ("winning", lambda r: r["winning"]),
            ("weak_jointly_feasible", lambda r: r["weak_jointly_feasible"]),
            ("strictly_jointly_feasible", lambda r: r["strictly_jointly_feasible"]),
        ):
            candidates = [r for r in group if r["members"] and predicate(r)]
            minimum = min((r["active_hash_power"] for r in candidates), default=None)
            matches = [{"configuration_id": r["configuration_id"], "coalition": r["coalition"]}
                       for r in candidates if r["active_hash_power"] == minimum]
            output.append({**common, "threshold_kind": name, "hash_power": minimum,
                           "matches": matches, "interpretation": "minimum supported among supplied grid points"})
    return output


def run_sweep(spec, output_dir, *, analyze_only=False, max_events=None):
    """Mine explicitly requested tasks, or reanalyze verified native raw runs.

    Invalid existing checkpoints are errors, never silent cache misses. All
    existing inputs are validated before any new simulation is considered.
    """
    spec, tasks = prepare(spec)
    output_dir = Path(output_dir)
    run_manifest = {"model_version": model_version(tasks[0].rule), "specification": spec, "specification_sha256": digest(spec)}
    manifest_path = output_dir / "persistent_manifest.json"
    if manifest_path.exists():
        if digest(json.loads(manifest_path.read_text())) != digest(run_manifest):
            raise ValueError("output directory belongs to a different persistent design")
    elif output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("refusing nonempty output directory without a persistent manifest")
    prepared, missing = {}, []
    for task in tasks:
        path = output_dir / "checkpoints" / (task.task_id + ".json")
        ptask = task.population_task
        if path.exists():
            raw = read_checkpoint(path, manifest(spec, task))
            prepared[task.task_id] = analyze(ptask.population, task.rule, spec["repetitions"],
                ptask.coalitions, spec["tpr"], spec["fpr"], unpack_conditions(raw),
                spec["bootstrap_samples"], spec.get("selfish_prior"))
        else:
            missing.append(task)
    if analyze_only and missing:
        raise ValueError("analysis-only requires every native checkpoint; mining fallback is disabled")
    atomic_json(manifest_path, run_manifest)
    executed = 0
    for task in missing:
        ptask = task.population_task
        try:
            result = study(ptask.population, spec["repetitions"], task.rule, spec["tpr"], spec["fpr"],
                selected_coalitions=ptask.coalitions, prior=spec.get("selfish_prior"),
                bootstrap_samples=spec["bootstrap_samples"], max_events=max_events)
        except IncompleteStudyError as exc:
            atomic_json(output_dir / "failures" / (task.task_id + ".json"),
                        {"manifest": manifest(spec, task), "condition": exc.condition, "result": exc.result})
            raise
        write_checkpoint(output_dir / "checkpoints" / (task.task_id + ".json"),
                         manifest(spec, task), result.pop("conditional_runs"))
        executed += result["meta"]["mining_simulations_executed"]
        prepared[task.task_id] = result
    collections = {k: [] for k in ("summary", "members", "detector", "repetitions", "tpr_thresholds")}
    for task in tasks:
        result = prepared[task.task_id]
        ptask = task.population_task
        for name in collections:
            for row in result[name]:
                row.update(task_id=task.task_id, family=ptask.family, structure=ptask.structure)
                collections[name].append(row)
    filenames = {"summary": "coalition_results", "members": "member_credibility",
                 "detector": "detector_evaluations", "repetitions": "repetition_metrics",
                 "tpr_thresholds": "continuous_tpr_thresholds"}
    for name, filename in filenames.items():
        _write_csv(output_dir / (filename + ".csv"), collections[name])
    collections["thresholds"] = grouped_thresholds(collections["summary"])
    _write_csv(output_dir / "minimum_thresholds.csv", collections["thresholds"])
    result = {"metadata": {**scope(spec), "specification_sha256": digest(spec),
                          "mining_simulations_executed": executed,
                          "resumed_tasks": len(tasks) - len(missing)}, **collections}
    atomic_json(output_dir / "persistent_results.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--analyze-only", action="store_true")
    args = parser.parse_args()
    spec = json.loads(args.config.read_text())
    if args.dry_run:
        print(json.dumps(scope(spec), indent=2))
    else:
        if args.output is None:
            parser.error("--output is required unless --dry-run is selected")
        result = run_sweep(spec, args.output, analyze_only=args.analyze_only)
        print(json.dumps(result["metadata"], indent=2))


if __name__ == "__main__":
    main()
