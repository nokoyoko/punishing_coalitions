"""Disk-backed task planning and scientific exports, with one raw run in memory.

No simulation is launched on import. Model, population and condition provenance
are validated by the same native v2 condition store used in diagnostic mode.
"""
from dataclasses import asdict
import csv
import itertools
import json
from pathlib import Path
import sqlite3

from .coalition import Population, subsets
from .persistent_checkpoint import atomic_json, canonical_json, digest
from .persistent_study import required_conditions
from .persistent_sweep import analysis_group_key
from .persistent_v2 import NETWORK_VERSION, model_version
from .persistent_v2_study import study
from .persistent_v2_sweep import Task, validate_spec, grouped_thresholds
from .research_sweep import (SweepTask, candidate_structure, systematic_compositions,
                             select_systematic_compositions, _flat)


def task_requests(spec):
    """Same ordered requests/admission/sampling as research_sweep.generate_tasks."""
    seed, blocks = spec["seed"], spec["accepted_blocks"]
    floor = float(spec.get("minimum_residual_power", 0))
    authorized = {tuple(map(float, x)) for x in spec.get("authorized_environment_triplets", [])}
    authorization = spec.get("authorization_rule")
    if authorization is not None:
        if authorization != "analytic_vanilla_eyal_sirer" or "authorized_environment_triplets" in spec:
            raise ValueError("invalid or conflicting analytical authorization")

    def allowed(alpha, total, gamma, rate):
        if authorization:
            from .theory import vanilla_selfish_mining_profitable
            admitted = vanilla_selfish_mining_profitable(alpha, gamma)
        else:
            admitted = not authorized or (float(alpha), float(gamma), float(rate)) in authorized
        return admitted and 1-alpha-total >= floor-1e-12 and alpha+total < 1

    agg = spec.get("aggregate", {})
    for alpha, total, gamma, rate in itertools.product(*(agg.get(k, []) for k in
            ("target_hash", "coalition_power", "gamma", "natural_fork_rate"))):
        if allowed(alpha, total, gamma, rate):
            yield SweepTask(Population(alpha, candidate_structure("singleton", total), gamma, rate, blocks, seed),
                            "aggregate", "singleton", total, (("c1",),))
    comp = spec.get("composition", {})
    systematic = comp.get("systematic")
    selected = {}
    dimensions = [comp.get(k, []) for k in ("target_hash", "candidate_power", "gamma", "natural_fork_rate")]
    dimensions.append(systematic.get("member_counts", []) if systematic else comp.get("structures", []))
    for alpha, total, gamma, rate, kind in itertools.product(*dimensions):
        if not allowed(alpha, total, gamma, rate):
            continue
        if systematic:
            step = float(systematic.get("power_step", .01))
            minimum = float(systematic.get("minimum_member_power", step))
            cell = (total, int(kind))
            if cell not in selected:
                selected[cell] = select_systematic_compositions(
                    systematic_compositions(total, int(kind), step, minimum), systematic.get("sampling"))
            for shares in selected[cell]:
                candidates = tuple((f"c{i+1}", share) for i, share in enumerate(shares))
                structure = "systematic_" + "_".join(str(int(round(x/step))) for x in shares)
                ids = tuple(a for a, _ in candidates)
                yield SweepTask(Population(alpha, candidates, gamma, rate, blocks, seed),
                                "composition", structure, total, (ids,))
        else:
            candidates = candidate_structure(kind, total)
            ids = tuple(a for a, _ in candidates)
            yield SweepTask(Population(alpha, candidates, gamma, rate, blocks, seed),
                            "composition", kind, total, tuple(C for C in subsets(ids) if C))


def plan_tasks(connection, spec):
    connection.execute("CREATE TABLE IF NOT EXISTS tasks (ordinal INTEGER PRIMARY KEY, population_key TEXT UNIQUE, body TEXT)")
    connection.execute("DELETE FROM tasks")
    for task in task_requests(spec):
        key = digest(asdict(task.population))
        old = connection.execute("SELECT body FROM tasks WHERE population_key=?", (key,)).fetchone()
        if old:
            previous = json.loads(old[0])
            coalitions = {tuple(c) for c in previous["coalitions"]} | set(task.coalitions)
            previous["coalitions"] = sorted(coalitions, key=lambda c: (len(c), c))
            if previous["family"] != task.family:
                previous["family"] = "both"
            connection.execute("UPDATE tasks SET body=? WHERE population_key=?", (canonical_json(previous), key))
        else:
            # Preserve insertion/key order for the historical CSV field layout.
            connection.execute("INSERT INTO tasks (population_key,body) VALUES (?,?)", (key, json.dumps(asdict(task))))
    connection.commit()
    if connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
        raise ValueError("no valid populations")


def iter_tasks(connection, rule):
    for body, in connection.execute("SELECT body FROM tasks ORDER BY ordinal"):
        raw = json.loads(body)
        raw["population"]["candidates"] = tuple(tuple(x) for x in raw["population"]["candidates"])
        raw["population"] = Population(**raw["population"])
        raw["coalitions"] = tuple(tuple(c) for c in raw["coalitions"])
        yield Task(SweepTask(**raw), rule)


def export_csv(connection, collection, path):
    fields = []
    for body, in connection.execute("SELECT body FROM outputs WHERE collection=? ORDER BY ordinal", (collection,)):
        for key in json.loads(body):
            if key not in fields:
                fields.append(key)
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="") as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for body, in connection.execute("SELECT body FROM outputs WHERE collection=? ORDER BY ordinal", (collection,)):
                writer.writerow(_flat(json.loads(body)))
    temporary.replace(path)


def run_full_ledger_production(spec, output_dir, *, checkpoint_dir=None, analyze_only=False, max_events=None):
    spec, rule = validate_spec(spec)
    output = Path(output_dir)
    store = Path(checkpoint_dir) if checkpoint_dir is not None else output / "v2_conditions"
    manifest = {"network_version": NETWORK_VERSION, "specification": spec, "specification_sha256": digest(spec),
        "condition_store": str(store.resolve()), "layout": "persistent-production-dataset-v2"}
    path = output / "persistent_v2_manifest.json"
    if path.exists():
        if digest(json.loads(path.read_text())) != digest(manifest):
            raise ValueError("output directory belongs to a different design or recording layout")
    elif output.exists() and any(output.iterdir()):
        raise ValueError("nonempty output directory without v2 manifest")
    atomic_json(path, manifest)
    status_path = output / "persistent_v2_status.json"
    atomic_json(status_path, {"status": "INCOMPLETE", "completed_tasks": 0})
    completed = executed = represented = 0
    per_lambda = {}
    names = {"summary": "coalition_results", "members": "member_credibility", "detector": "detector_evaluations",
             "repetitions": "repetition_metrics", "tpr_thresholds": "continuous_tpr_thresholds",
             "baseline_references": "baseline_references", "conditional_references": "conditional_references"}
    with sqlite3.connect(output / "persistent_v2_analysis.sqlite3") as connection:
        plan_tasks(connection, spec)
        connection.execute("CREATE TABLE IF NOT EXISTS outputs (ordinal INTEGER PRIMARY KEY, collection TEXT, group_key TEXT, body TEXT)")
        connection.execute("CREATE INDEX IF NOT EXISTS outputs_collection ON outputs (collection,group_key,ordinal)")
        connection.execute("DELETE FROM outputs")
        connection.commit()
        for task in iter_tasks(connection, rule):
            ptask = task.population_task
            result = study(ptask.population, spec["repetitions"], rule, spec["tpr"], spec["fpr"],
                ptask.coalitions, spec.get("selfish_prior"), spec["bootstrap_samples"], max_events,
                checkpoint_dir=store, analyze_only=analyze_only, production=True)
            n = result["meta"]["mining_simulations"]
            represented += n
            executed += result["meta"]["mining_simulations_executed"]
            cell = per_lambda.setdefault(str(ptask.population.natural_fork_rate),
                {"top_level_configurations": 0, "mining_simulations": 0, "accepted_block_work_units": 0})
            cell["top_level_configurations"] += 1
            cell["mining_simulations"] += n
            cell["accepted_block_work_units"] += n*spec["accepted_blocks"]
            for name in names:
                for row in result[name]:
                    row = {**row, "task_id": task.task_id, "family": ptask.family, "structure": ptask.structure}
                    group = canonical_json([NETWORK_VERSION, *analysis_group_key(row)]) if name == "summary" else None
                    connection.execute("INSERT INTO outputs (collection,group_key,body) VALUES (?,?,?)",
                                       (name, group, json.dumps(row)))
            connection.commit()
            completed += 1
            atomic_json(status_path, {"status": "INCOMPLETE", "completed_tasks": completed})
            del result
        # Threshold reduction is bounded to one scientific grouping, not the grid.
        for group, in connection.execute("SELECT DISTINCT group_key FROM outputs WHERE collection='summary' ORDER BY group_key"):
            rows = [json.loads(body) for body, in connection.execute(
                "SELECT body FROM outputs WHERE collection='summary' AND group_key=? ORDER BY ordinal", (group,))]
            for row in grouped_thresholds(rows):
                connection.execute("INSERT INTO outputs (collection,body) VALUES (?,?)", ("thresholds", json.dumps(row)))
        connection.commit()
        names["thresholds"] = "minimum_thresholds"
        counts = {}
        for name, filename in names.items():
            export_csv(connection, name, output / (filename+".csv"))
            counts[name] = connection.execute("SELECT COUNT(*) FROM outputs WHERE collection=?", (name,)).fetchone()[0]
    metadata = {"network_version": NETWORK_VERSION, "model_version": model_version(rule), **asdict(rule),
        "repetitions": spec["repetitions"], "accepted_block_target": spec["accepted_blocks"],
        "top_level_configurations": completed, "per_lambda": per_lambda, "mining_simulations": represented,
        "mining_simulations_executed": executed, "accepted_block_work_units": represented*spec["accepted_blocks"],
        "specification_sha256": digest(spec), "historical_checkpoint_reuse": False, "shared_v2_baselines": True}
    result = {"metadata": metadata, "layout": manifest["layout"], "row_counts": counts,
        "scientific_database": "persistent_v2_analysis.sqlite3", "csv_files": {k: v+".csv" for k, v in names.items()},
        "terminal_provenance": "Full terminal ledgers are retained in referenced, validated native condition checkpoints."}
    atomic_json(output / "persistent_v2_results.json", result)
    atomic_json(status_path, {"status": "COMPLETE", "completed_tasks": completed})
    return result


def run_production(spec, output_dir, *, checkpoint_dir=None, analyze_only=False, max_events=None,
                   rep_start=1, rep_end=None, preliminary=False):
    """Normal production entry: compact repetition checkpoints, never full ledgers.

For shared baselines across six variants use persistent_v2_shards with the common
multi-rule design. The old full-ledger runner is explicit diagnostic compatibility.
"""
    from .persistent_v2_shards import (single_variant_design, prepare_study, run_shard, load_manifest)
    if checkpoint_dir is not None or max_events is not None:
        raise ValueError("compact production uses its isolated shard store; external ledger stores/resource overrides require explicit diagnostic mode")
    output = Path(output_dir)
    if analyze_only:
        manifest = load_manifest(output)
        from .persistent_v2_checkpoint import same
        from .persistent_v2_shards import normalize_design
        same(manifest["design"], normalize_design(single_variant_design(spec)), "different analysis design")
    else:
        manifest = prepare_study(single_variant_design(spec), output)
    metrics = run_shard(output, 0, analyze_only=analyze_only, rep_start=rep_start, rep_end=rep_end, preliminary=preliminary)
    return {"layout": manifest["layout"], "metadata": {**manifest["scope"],
        "mining_simulations": manifest["scope"]["after_reuse"],
        "mining_simulations_executed": metrics.get("mining_simulations_executed", 0),
        "analysis_status": metrics["analysis_status"], "requested_repetitions": metrics["requested_repetitions"]},
        "metrics": metrics, "scientific_database": "shard-00.sqlite3"}
