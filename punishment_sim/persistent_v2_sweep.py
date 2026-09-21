"""Explicit v2 local runner; no production grid and no implicit v1 migration."""
import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .persistent_checkpoint import atomic_json, digest
from .persistent_study import required_conditions
from .persistent_v2 import Rule, NETWORK_VERSION, configuration_id, model_version
from .persistent_v2_study import study
from .research_sweep import generate_tasks, _write_csv
from .persistent_sweep import grouped_thresholds as historical_grouped_thresholds


@dataclass(frozen=True)
class Task:
    population_task: object
    rule: Rule

    @property
    def task_id(self):
        return digest({"network_version": NETWORK_VERSION,
            "configuration_id": configuration_id(self.population_task.population, self.rule),
            "coalitions": self.population_task.coalitions})[:24]


def validate_spec(spec):
    spec = dict(spec)
    allowed = {"expected_model_version", "expected_network_version", "punishment_rule", "counter_fork_k",
        "accepted_blocks", "repetitions", "seed", "bootstrap_samples", "tpr", "fpr", "selfish_prior",
        "authorization_rule", "authorized_environment_triplets", "aggregate", "composition", "minimum_residual_power"}
    if set(spec)-allowed:
        raise ValueError("unsupported v2 configuration fields")
    rule = Rule(spec.get("punishment_rule"), spec.get("counter_fork_k"))
    if spec.get("expected_network_version") != NETWORK_VERSION or spec.get("expected_model_version") != model_version(rule):
        raise ValueError("explicit matching v2 network and model versions required")
    for key, value in (("accepted_blocks", 30000), ("repetitions", 10), ("seed", 41000), ("bootstrap_samples", 2000)):
        spec.setdefault(key, value)
    for key in ("accepted_blocks", "repetitions"):
        if type(spec[key]) is not int or spec[key] < 1:
            raise ValueError(key + " must be a positive integer")
    if type(spec["seed"]) is not int or type(spec["bootstrap_samples"]) is not int or spec["bootstrap_samples"] < 0:
        raise ValueError("invalid seed/bootstrap_samples")
    for key in ("tpr", "fpr"):
        if not spec.get(key) or any(not 0 <= x <= 1 for x in spec[key]):
            raise ValueError("nonempty detector probability grids required")
    if spec.get("selfish_prior") is not None and not 0 <= spec["selfish_prior"] <= 1:
        raise ValueError("selfish_prior must be a probability")
    return spec, rule


def prepare(spec):
    spec, rule = validate_spec(spec)
    tasks, _, _ = generate_tasks(spec)
    if not tasks:
        raise ValueError("no valid populations")
    return spec, [Task(t, rule) for t in tasks]


def scope(spec):
    spec, tasks = prepare(spec)
    cells = {}
    for task in tasks:
        n = len(required_conditions(task.population_task.coalitions))*spec["repetitions"]
        cell = cells.setdefault(str(task.population_task.population.natural_fork_rate),
            {"top_level_configurations": 0, "mining_simulations": 0, "accepted_block_work_units": 0})
        cell["top_level_configurations"] += 1
        cell["mining_simulations"] += n
        cell["accepted_block_work_units"] += n*spec["accepted_blocks"]
    return {"network_version": NETWORK_VERSION, "model_version": model_version(tasks[0].rule),
        **asdict(tasks[0].rule), "repetitions": spec["repetitions"], "accepted_block_target": spec["accepted_blocks"],
        "top_level_configurations": len(tasks), "per_lambda": cells,
        "mining_simulations": sum(c["mining_simulations"] for c in cells.values()),
        "accepted_block_work_units": sum(c["accepted_block_work_units"] for c in cells.values()),
        "historical_checkpoint_reuse": False, "shared_v2_baselines": True,
        "work_interpretation": "represented reference-height targets before validated cache reuse; not discoveries"}


def grouped_thresholds(rows):
    networks = {}
    for row in rows:
        networks.setdefault(row["network_version"], []).append(row)
    result = []
    for network, group in sorted(networks.items()):
        keys = ("analysis_status", "analysis_repetitions", "planned_repetitions")
        metadata = {k: group[0][k] for k in keys if k in group[0]}
        if any({k: row[k] for k in keys if k in row} != metadata for row in group):
            raise ValueError("cannot mix preliminary and final thresholds")
        result.extend({**row, "network_version": network, **metadata} for row in historical_grouped_thresholds(group))
    return result


def run_sweep(spec, output_dir, *, checkpoint_dir=None, analyze_only=False, max_events=None, production=False,
              rep_start=1, rep_end=None, preliminary=False):
    if production:
        from .persistent_v2_production import run_production
        return run_production(spec, output_dir, checkpoint_dir=checkpoint_dir,
                              analyze_only=analyze_only, max_events=max_events, rep_start=rep_start, rep_end=rep_end, preliminary=preliminary)
    if rep_start != 1 or rep_end is not None or preliminary:
        raise ValueError("repetition phases require compact production mode")
    spec, tasks = prepare(spec)
    output_dir = Path(output_dir)
    store = Path(checkpoint_dir) if checkpoint_dir is not None else output_dir / "v2_conditions"
    manifest = {"network_version": NETWORK_VERSION, "specification": spec, "specification_sha256": digest(spec),
                "condition_store": str(store.resolve())}
    path = output_dir / "persistent_v2_manifest.json"
    if path.exists():
        if digest(json.loads(path.read_text())) != digest(manifest):
            raise ValueError("output directory belongs to a different v2 design")
    elif output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("nonempty output directory without v2 manifest")
    # Read/validate every available task first. Missing results are allowed only
    # in explicit run mode; a corrupt result never silently triggers new work.
    prepared = {}
    for task in tasks:
        ptask = task.population_task
        try:
            prepared[task.task_id] = study(ptask.population, spec["repetitions"], task.rule,
                spec["tpr"], spec["fpr"], ptask.coalitions, spec.get("selfish_prior"), spec["bootstrap_samples"],
                checkpoint_dir=store, analyze_only=True)
        except ValueError as exc:
            if str(exc) != "analysis-only requires complete validated v2 conditions; mining fallback disabled" or analyze_only:
                raise
    atomic_json(path, manifest)
    collections = {k: [] for k in ("summary", "members", "detector", "repetitions", "tpr_thresholds")}
    references, executed = [], 0
    for task in tasks:
        ptask = task.population_task
        result = prepared.get(task.task_id)
        if result is None:
            result = study(ptask.population, spec["repetitions"], task.rule, spec["tpr"], spec["fpr"],
                ptask.coalitions, spec.get("selfish_prior"), spec["bootstrap_samples"], max_events,
                checkpoint_dir=store)
        executed += result["meta"]["mining_simulations_executed"]
        references.extend({**r, "task_id": task.task_id} for r in result["baseline_references"])
        for name in collections:
            collections[name].extend({**row, "task_id": task.task_id, "family": ptask.family, "structure": ptask.structure}
                                     for row in result[name])
    filenames = {"summary": "coalition_results", "members": "member_credibility", "detector": "detector_evaluations",
                 "repetitions": "repetition_metrics", "tpr_thresholds": "continuous_tpr_thresholds"}
    for name, filename in filenames.items():
        _write_csv(output_dir / (filename+".csv"), collections[name])
    collections["thresholds"] = grouped_thresholds(collections["summary"])
    _write_csv(output_dir / "minimum_thresholds.csv", collections["thresholds"])
    result = {"metadata": {**scope(spec), "specification_sha256": digest(spec), "mining_simulations_executed": executed},
              "baseline_references": references, **collections}
    atomic_json(output_dir / "persistent_v2_results.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--rep-start", type=int, default=1)
    parser.add_argument("--rep-end", type=int)
    parser.add_argument("--preliminary", action="store_true")
    parser.add_argument("--diagnostic", action="store_true", help="retain full raw results in study/runner memory")
    args = parser.parse_args()
    spec = json.loads(args.config.read_text())
    if args.dry_run:
        print(json.dumps(scope(spec), indent=2))
    else:
        if args.output is None:
            parser.error("--output required")
        result = run_sweep(spec, args.output, checkpoint_dir=args.checkpoint_dir,
                           analyze_only=args.analyze_only, production=not args.diagnostic,
                           rep_start=args.rep_start, rep_end=args.rep_end, preliminary=args.preliminary)
        print(json.dumps(result["metadata"], indent=2))


if __name__ == "__main__":
    main()
