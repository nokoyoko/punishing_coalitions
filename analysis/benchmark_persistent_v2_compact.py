"""Fixed LOCAL 14-task benchmark: 30,000 blocks, ten reps, no production grid.

Twelve two-member tasks cover all six variants at lambda 0/.02. Two six-member
tasks (ignore/selfish, lambda .02) check the larger sufficient-record payloads.
Only compact records are written. Old full-ledger sizes are measured in memory.
"""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import resource
import sqlite3
import sys
import tempfile
from time import perf_counter
import zlib

from punishment_sim.persistent_checkpoint import canonical_json, digest, atomic_json
from punishment_sim.persistent_v2 import Rule, NETWORK_VERSION
from punishment_sim.persistent_v2_checkpoint import encode_checkpoint
from punishment_sim.persistent_v2_shards import (VARIANTS, prepare_study, ShardStore, task_rows,
    task_analysis, task_key, shard_lock, run_shard, merge_shards, export_study)

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "results/persistent_v2_compact_local_benchmark"
EVIDENCE = ROOT / "docs/persistent_v2_compact_benchmark.json"


def rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform == "darwin" else 1024)


def specification(members):
    variants = VARIANTS if members == 2 else (Rule("ignore"), Rule("selfish"))
    return {"expected_network_version": NETWORK_VERSION, "repetitions": 10, "accepted_blocks": 30000,
        "seed": 701, "bootstrap_samples": 2000, "tpr": [.5,.7,.9,1.], "fpr": [0,.001,.01,.05,.1],
        "shard_count": 1, "variants": [asdict(r) for r in variants],
        "composition": {"target_hash": [.2], "candidate_power": [.2], "gamma": [.5],
            "natural_fork_rate": [0,.02] if members == 2 else [.02],
            "systematic": {"power_step": .01, "minimum_member_power": .01, "member_counts": [members],
                "sampling": {"mode": "hhi_quantiles", "max_per_cell": 1}}}}


def storage_probe(source, tasks=1000):
    """Physical SQLite packing, not scientific runs: repeated observed blobs only."""
    with sqlite3.connect(source) as connection:
        samples = {kind: list(connection.execute("SELECT body,sha256,receipt FROM records WHERE kind=?", (kind,)))
                   for kind in ("baseline", "repetition", "task")}
    with tempfile.TemporaryDirectory(prefix="compact-storage-probe-") as temporary:
        path = Path(temporary) / "packing.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE records(kind TEXT,id TEXT,body BLOB,sha256 TEXT,receipt TEXT,PRIMARY KEY(kind,id)) WITHOUT ROWID")
            for task in range(tasks):
                for kind, copies in (("task", 1), ("repetition", 10), ("baseline", 20 if task % 6 == 0 else 0)):
                    for i in range(copies):
                        blob, sha, receipt = samples[kind][(task*copies+i) % len(samples[kind])]
                        key = hashlib.sha256(f"{task}:{kind}:{i}".encode()).hexdigest()[:24]+f":{i}"
                        connection.execute("INSERT INTO records VALUES (?,?,?,?,?)", (kind,key,blob,sha,receipt))
        return {"tasks": tasks, "bytes": path.stat().st_size, "method": "isolated synthetic packing of measured blobs, same SQLite table/index; 20 baseline rows per six tasks; no mining"}


def main():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    evidence = {"purpose": "fixed local performance/storage diagnostics, no scientific inference",
        "python": sys.version, "platform": platform.platform(), "repetitions": 10, "horizon": 30000,
        "planned_tasks": 14, "planned_unique_simulations": 700, "tasks": [], "conditions": [], "studies": [],
        "production_sweep": False, "ssh": False, "xtra_access": False, "remote_job": False}
    for members in (2, 6):
        directory = DIRECTORY / f"members-{members}"
        manifest = prepare_study(specification(members), directory)
        require_empty = not (directory / "shard-00.sqlite3").exists()
        if not require_empty:
            raise ValueError("benchmark output already exists; preserve evidence and choose a separate explicitly fixed rerun")
        with shard_lock(directory, 0):
            store = ShardStore(directory, manifest, 0)
            old_bytes = Counter()
            def observe(event, value):
                if event != "validated_condition":
                    return
                raw, compact = value["raw"], value["compact"]
                before_rss = rss()
                start = perf_counter()
                legacy_bytes = len(encode_checkpoint(raw))
                legacy_encode = perf_counter()-start
                identity = compact["identity"]
                old_bytes[compact["condition_id"]] = legacy_bytes
                evidence["conditions"].append({"members": members, "lambda": identity["population"]["natural_fork_rate"],
                    "rule": identity["rule"], "strategy": identity["strategy"], "flagged": identity["flagged"],
                    "active_coalition": identity["active_coalition"], "repetition": identity["repetition"],
                    "condition_id": compact["condition_id"], "events": compact["events"], "reference_blocks": compact["accepted_blocks"],
                    "compact_json_bytes": len(canonical_json(compact).encode()),
                    "compact_compressed_bytes": len(zlib.compress(canonical_json(compact).encode(),6)),
                    "old_full_checkpoint_bytes": legacy_bytes, "old_checkpoint_encoding_seconds": legacy_encode,
                    "peak_rss_before_diagnostic_encoding": before_rss})
            try:
                task_count = 0
                for task in task_rows(directory, manifest, 0):
                    baseline_cache = {}
                    for variant in manifest["design"]["variants"]:
                        rule, before = Rule(**variant), Counter(store.metrics)
                        start = perf_counter()
                        output = task_analysis(store, task, rule, hook=observe, baseline_cache=baseline_cache)
                        wall = perf_counter()-start
                        delta = Counter(store.metrics)
                        delta.subtract(before)
                        tid = task_key(task, rule)
                        rep_bytes = store.connection.execute("SELECT SUM(length(body)) FROM records WHERE kind='repetition' AND id LIKE ?", (tid+":%",)).fetchone()[0]
                        task_bytes = store.connection.execute("SELECT length(body) FROM records WHERE kind='task' AND id=?", (tid,)).fetchone()[0]
                        baseline_bytes = sum(len(zlib.compress(canonical_json(r).encode(),6)) for r in baseline_cache.values())
                        old_task_bytes = sum(old_bytes[r["condition_id"]] for r in baseline_cache.values())
                        for rep in range(10):
                            payload = store.get("repetition", f"{tid}:{rep}")
                            old_task_bytes += sum(old_bytes[r["condition_id"]] for r in payload["conditions"])
                        row = {"members": members, "population": asdict(task.population), "rule": asdict(rule), "task_id": tid,
                            "wall_seconds_including_measurement": wall, "metrics": dict(delta), "peak_rss_bytes": rss(),
                            "repetition_checkpoint_bytes_total": rep_bytes, "derived_task_record_bytes": task_bytes,
                            "task_checkpoint_bytes_excluding_shared_baselines": rep_bytes+task_bytes,
                            "referenced_shared_baseline_bytes": baseline_bytes, "old_full_condition_checkpoints_bytes": old_task_bytes,
                            "scientific_outputs_sha256": digest(output), "database_bytes_so_far": store.path.stat().st_size}
                        evidence["tasks"].append(row)
                        atomic_json(EVIDENCE, {**evidence, "status": "INCOMPLETE"})
                        print(f"m={members} lambda={task.population.natural_fork_rate} {variant}: mining={delta['mining_seconds']:.2f}s native-validation={delta['native_validation_seconds']:.2f}s task={rep_bytes+task_bytes:,} bytes", flush=True)
                        del output
                        task_count += 1
                complete = {"tasks": task_count, "baselines": manifest["scope"]["shared_baseline_simulations"],
                    "repetitions": task_count*10, "study_id": manifest["study_id"], "shard": 0}
                store.put("complete", "0", complete)
                study_metrics = dict(store.metrics)
                counts = dict(store.connection.execute("SELECT kind,COUNT(*) FROM records GROUP BY kind"))
            finally:
                store.close()
        start = perf_counter()
        resumed = run_shard(directory, 0, analyze_only=True)
        resume_wall = perf_counter()-start
        start = perf_counter()
        merge = merge_shards(directory, directory / "merged.sqlite3")
        merge_wall = perf_counter()-start
        start = perf_counter()
        exported = export_study(directory, directory / "exports", include_repetitions=True)
        export_wall = perf_counter()-start
        exported_bytes = {p.name: p.stat().st_size for p in (directory / "exports").glob("*.csv")}
        probe = storage_probe(directory / "shard-00.sqlite3")
        evidence["studies"].append({"members": members, "scope": manifest["scope"], "runtime": manifest["runtime"],
            "metrics": study_metrics, "resume_metrics": resumed, "resume_wall_seconds": resume_wall,
            "merge": merge, "merge_wall_seconds": merge_wall, "export_wall_seconds": export_wall,
            "export_rows": exported["row_counts"], "export_bytes": exported_bytes,
            "rows": counts, "storage_probe_per_1000_tasks": probe,
            "database_bytes": (directory / "shard-00.sqlite3").stat().st_size,
            "full_ledger_bytes_if_every_unique_condition_persisted": sum(old_bytes.values())})
    assert len(evidence["tasks"]) == 14 and len(evidence["conditions"]) == 700
    evidence.update(status="COMPLETE", peak_rss_bytes=rss(),
        memory_note="single fresh benchmark process, high-water RSS includes native validation and in-memory old-format encoding diagnostics; no raw tree checkpoints written")
    atomic_json(EVIDENCE, evidence)
    print(EVIDENCE, flush=True)


if __name__ == "__main__":
    main()
