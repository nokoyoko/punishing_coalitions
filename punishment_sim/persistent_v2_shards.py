"""Independent compact SQLite workers, population ownership and strict merge.

Preparing a plan never mines. Each worker owns all variants of its populations.
Only run_shard explicitly mines; analysis, merge and inspection never fall back.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
from time import perf_counter
import zlib

from .coalition import Population
from .persistent_checkpoint import atomic_json, canonical_json, digest
from .persistent_study import required_conditions, IncompleteStudyError
from .persistent_v2 import Rule, PersistentSimulation, NETWORK_VERSION, model_version, condition_identity
from .persistent_v2_compact import (runtime_identity, extract_validated, validate_compact, analysis_record)
from .persistent_v2_checkpoint import require, same, validate_run
from .persistent_v2_validation import (normalize_policy, validation_context, add_anchor,
    validate_lightweight, attestation, prepare_context, FULL)
from .persistent_v2_study import _analyze_validated
from .persistent_v2_sweep import Task, validate_spec
from .persistent_v2_production import plan_tasks, iter_tasks

LAYOUT = "persistent-compact-shards-v2-2"
VARIANTS = (Rule("petty"), Rule("counter_fork", 1), Rule("counter_fork", 2), Rule("counter_fork", 3), Rule("ignore"), Rule("selfish"))


def normalize_design(design):
    design = dict(design)
    policy = normalize_policy(design.pop("validation_policy", None))
    variants = [Rule(**r) for r in design.pop("variants")]
    shards = design.pop("shard_count", 28)
    require(type(shards) is int and shards > 0 and variants and len(set(variants)) == len(variants), "variants/shards")
    first = variants[0]
    spec, _ = validate_spec({**design, **asdict(first), "expected_model_version": model_version(first)})
    for k in ("punishment_rule", "counter_fork_k", "expected_model_version"):
        spec.pop(k)
    return {**spec, "variants": [asdict(r) for r in variants], "shard_count": shards, "validation_policy": policy}


def single_variant_design(spec):
    spec, rule = validate_spec(spec)
    return {k: v for k, v in spec.items() if k not in ("punishment_rule", "counter_fork_k", "expected_model_version")} | {
        "variants": [asdict(rule)], "shard_count": 1}


def population_owner(population_key, count):
    return int(population_key[:16], 16) % count


def task_key(ptask, rule):
    return Task(ptask, rule).task_id


def _plan_digest(connection, *, anchors=None, policy=None):
    h = hashlib.sha256()
    for pid, body, owner, group in connection.execute("SELECT population_key,body,owner,analysis_group FROM tasks ORDER BY ordinal"):
        body = json.loads(body)
        h.update(canonical_json([pid, body, owner, group]).encode()+b"\n")
        if anchors is not None:
            add_anchor(anchors, Population(**body['population']), policy)
    return h.hexdigest()


def prepare_study(design, directory):
    """Enumerate exact native tasks; create immutable plan/control files, no mining."""
    design = normalize_design(design)
    directory = Path(directory)
    if (directory / "study.json").exists():
        manifest = load_manifest(directory)
        same(manifest["design"], design, "different study design")
        return manifest
    require(not directory.exists() or not any(directory.iterdir()), "nonempty study without manifest")
    directory.mkdir(parents=True, exist_ok=True)
    runtime = runtime_identity()
    rules = [Rule(**r) for r in design["variants"]]
    spec = {k: v for k, v in design.items() if k not in ("variants", "shard_count", "validation_policy")}
    spec.update(**asdict(rules[0]), expected_model_version=model_version(rules[0]))
    with sqlite3.connect(directory / "plan.sqlite3") as connection:
        plan_tasks(connection, spec)
        connection.execute("ALTER TABLE tasks ADD COLUMN owner INTEGER")
        connection.execute("ALTER TABLE tasks ADD COLUMN analysis_group TEXT")
        per_lambda, cardinalities, shard_counts = {}, Counter(), Counter()
        populations = per_variant = baseline = 0
        anchors = {}
        for task in iter_tasks(connection, rules[0]):
            ptask = task.population_task
            p, pid = ptask.population, digest(asdict(ptask.population))
            add_anchor(anchors, p, design["validation_policy"])
            owner = population_owner(pid, design["shard_count"])
            group = canonical_json([p.target_hash_power, p.gamma, p.natural_fork_rate, ptask.candidate_total,
                                    p.target_accepted_blocks, p.seed])
            connection.execute("UPDATE tasks SET owner=?,analysis_group=? WHERE population_key=?", (owner, group, pid))
            count = len(required_conditions(ptask.coalitions))*design["repetitions"]
            populations += 1
            per_variant += count
            baseline += 2*design["repetitions"]
            cardinalities[len(p.candidates)] += 1
            shard_counts[owner] += 1
            cell = per_lambda.setdefault(str(p.natural_fork_rate), {"populations": 0, "per_variant_simulations": 0, "shared_baselines": 0})
            cell["populations"] += 1
            cell["per_variant_simulations"] += count
            cell["shared_baselines"] += 2*design["repetitions"]
        connection.execute("CREATE INDEX task_owners ON tasks(owner,ordinal)")
        connection.execute("CREATE INDEX analysis_groups ON tasks(analysis_group,ordinal)")
        connection.commit()
        plan_hash = _plan_digest(connection)
    independent = per_variant*len(rules)
    unique = independent-(len(rules)-1)*baseline
    for cell in per_lambda.values():
        cell.update(before_reuse=cell["per_variant_simulations"]*len(rules),
            after_reuse=cell["per_variant_simulations"]*len(rules)-(len(rules)-1)*cell["shared_baselines"])
        cell["accepted_block_work"] = cell["after_reuse"]*design["accepted_blocks"]
    scope = {"populations": populations, "top_level_rule_configurations": populations*len(rules),
        "repetitions": design["repetitions"], "per_variant_simulations": per_variant,
        "per_variant_policy_only_simulations": per_variant-baseline, "shared_baseline_simulations": baseline,
        "before_reuse": independent, "after_reuse": unique, "saved_by_baseline_reuse": independent-unique,
        "accepted_block_work_before_reuse": independent*design["accepted_blocks"],
        "accepted_block_work_after_reuse": unique*design["accepted_blocks"],
        "by_lambda": per_lambda, "by_cardinality": dict(cardinalities), "populations_by_shard": dict(shard_counts)}
    unsigned = {"layout": LAYOUT, "design": design, "runtime": runtime, "plan_sha256": plan_hash, "scope": scope,
                "validation": validation_context(design["validation_policy"], anchors)}
    # Hash the durable JSON representation: integer keys become strings, whose
    # canonical sort order can differ (e.g. shard 2 versus shard 10).
    unsigned = json.loads(canonical_json(unsigned))
    manifest = {**unsigned, "study_id": digest(unsigned)}
    keys = directory / "receipts"
    keys.mkdir(mode=0o700)
    manifest["receipt_key_sha256"] = {}
    for shard in range(design["shard_count"]):
        key = os.urandom(32)
        path = keys / f"shard-{shard:02d}.key"
        with path.open("xb") as stream:
            stream.write(key)
        path.chmod(0o600)
        manifest["receipt_key_sha256"][str(shard)] = hashlib.sha256(key).hexdigest()
    atomic_json(directory / "study.json", manifest)
    return manifest


def load_manifest(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "study.json").read_text())
    require(manifest["layout"] == LAYOUT, "compact study layout")
    unsigned = {k: v for k, v in manifest.items() if k not in ("study_id", "receipt_key_sha256")}
    require(manifest["study_id"] == digest(unsigned), "study manifest checksum")
    same(manifest["runtime"], runtime_identity(), "worker/analysis source or Python version changed")
    same(manifest["validation"]["policy"], normalize_policy(manifest["design"]["validation_policy"]), "manifest validation policy")
    with sqlite3.connect(f"file:{directory / 'plan.sqlite3'}?mode=ro", uri=True) as connection:
        require(connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "plan integrity")
        anchors = {}
        policy = manifest["validation"]["policy"]
        require(_plan_digest(connection, anchors=anchors, policy=policy) == manifest["plan_sha256"], "plan content mismatch")
        same(manifest["validation"], validation_context(policy, anchors), "validation coverage differs from plan")
    return manifest


@contextmanager
def shard_lock(directory, shard, shared=False):
    path = Path(directory) / f"shard-{shard:02d}.lock"
    with path.open("a+b") as lock:
        try:
            fcntl.flock(lock, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("shard already has an active writer/reader") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def task_rows(directory, manifest, shard):
    with sqlite3.connect(f"file:{Path(directory) / 'plan.sqlite3'}?mode=ro", uri=True) as connection:
        from .research_sweep import SweepTask
        for pid, body in connection.execute("SELECT population_key,body FROM tasks WHERE owner=? ORDER BY ordinal", (shard,)):
            raw = json.loads(body)
            raw["population"]["candidates"] = tuple(tuple(x) for x in raw["population"]["candidates"])
            raw["population"] = Population(**raw["population"])
            raw["coalitions"] = tuple(tuple(c) for c in raw["coalitions"])
            require(population_owner(pid, manifest["design"]["shard_count"]) == shard, "foreign task owner")
            yield SweepTask(**raw)


class ShardStore:
    """One writer, FULL synchronous transactions; no raw trajectory serialization."""
    def __init__(self, directory, manifest, shard, readonly=False):
        self.directory, self.manifest, self.shard = Path(directory), manifest, shard
        require(type(shard) is int and 0 <= shard < manifest["design"]["shard_count"], "invalid shard")
        key = (self.directory / "receipts" / f"shard-{shard:02d}.key").read_bytes()
        require(hashlib.sha256(key).hexdigest() == manifest["receipt_key_sha256"][str(shard)], "receipt key provenance")
        self.key = key
        self.producer = digest(manifest["runtime"])
        self.validation = prepare_context(manifest["validation"])
        self.path = self.directory / f"shard-{shard:02d}.sqlite3"
        self.connection = sqlite3.connect(f"file:{self.path}?mode=ro" if readonly else self.path, uri=readonly, timeout=0)
        if not readonly:
            self.connection.execute("PRAGMA journal_mode=DELETE")
            self.connection.execute("PRAGMA synchronous=FULL")
            self.connection.execute("CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, body BLOB NOT NULL, sha256 TEXT NOT NULL, receipt TEXT NOT NULL, PRIMARY KEY(kind,id)) WITHOUT ROWID")
            self.connection.commit()
        require(self.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "shard integrity")
        self.metrics = Counter()
        if self.connection.execute("SELECT COUNT(*) FROM records WHERE kind='validation_failure'").fetchone()[0]:
            self.connection.close()
            require(False, "prior validation failure; explicit investigation and a fresh study are required")

    def close(self):
        self.connection.close()

    def _receipt(self, kind, key, checksum):
        message = canonical_json([self.manifest["study_id"], self.shard, kind, key, checksum]).encode()
        return hmac.new(self.key, message, hashlib.sha256).hexdigest()

    def get(self, kind, key):
        start = perf_counter()
        row = self.connection.execute("SELECT body,sha256,receipt FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        if row is None:
            return None
        blob, checksum, receipt = row
        require(hmac.compare_digest(receipt, self._receipt(kind, key, checksum)), "native-validation receipt mismatch")
        try:
            body = zlib.decompress(blob)
            require(hashlib.sha256(body).hexdigest() == checksum, "compact content checksum")
            value = json.loads(body)
        except (zlib.error, ValueError) as exc:
            raise ValueError("invalid compact payload") from exc
        self.metrics["compact_read_seconds"] += perf_counter()-start
        return value

    def put(self, kind, key, value, hook=lambda *args: None):
        start = perf_counter()
        body = canonical_json(value).encode()
        checksum = hashlib.sha256(body).hexdigest()
        previous = self.get(kind, key)
        if previous is not None:
            same(previous, value, "refusing different immutable compact result")
            return
        blob = zlib.compress(body, 6)
        receipt = self._receipt(kind, key, checksum)
        with self.connection:
            self.connection.execute("INSERT INTO records VALUES (?,?,?,?,?)", (kind, key, blob, checksum, receipt))
            hook("during_flush", {"kind": kind, "id": key})
        self.metrics["serialization_write_seconds"] += perf_counter()-start
        self.metrics[kind+"_bytes"] += len(blob)


def _validate_fresh(store, raw, p, rule, rep, strategy, flagged, coalition):
    identity, producer = condition_identity(p, rep, strategy, flagged, coalition, rule), store.producer
    try:
        start = perf_counter()
        risks = validate_lightweight(raw, p, rule, rep, strategy, flagged, coalition)
        store.metrics["lightweight_validation_seconds"] += perf_counter()-start
        validation = attestation(identity, store.validation, risks)
        if validation["level"] == FULL:
            start = perf_counter()
            # Fatal on failure. No catch/retry or downgrade to lightweight.
            validate_run(raw, p, rule, rep, strategy, flagged, coalition)
            elapsed = perf_counter()-start
            store.metrics["native_validation_seconds"] += elapsed
            store.metrics["full_replay_seconds" if store.validation.mode == "full" else "sampled_replay_seconds"] += elapsed
            store.metrics["replayed_conditions"] += 1
        else:
            store.metrics["lightweight_only_conditions"] += 1
        for reason in validation["replay_reasons"]:
            store.metrics["replay_reason:"+reason] += 1
        start = perf_counter()
        result = extract_validated(raw, producer, validation)
        store.metrics["extraction_seconds"] += perf_counter()-start
        start = perf_counter()
        validate_compact(result, p, rule, rep, strategy, flagged, coalition, producer, store.validation)
        store.metrics["compact_validation_seconds"] += perf_counter()-start
        return result
    except Exception as exc:
        # A validation failure is not a cache miss. Persist a signed stop marker
        # before diagnostics, so a restart cannot silently remine until success.
        key = digest(condition_identity(p, rep, strategy, flagged, coalition, rule))
        store.put('validation_failure', key, {'condition_id': key,
            'validation_policy_sha256': store.validation.policy_sha256,
            'error_type': type(exc).__name__, 'error': str(exc)})
        try:
            atomic_json(store.directory/'validation_failures'/(key+'.json'),
                        {'error': str(exc), 'raw': raw})
        except (ValueError, TypeError):
            pass  # Non-finite/malformed raw data cannot be serialized; marker persists.
        raise


def _condition(store, p, rule, rep, condition, analyze_only, hook, baseline_cache):
    strategy, flagged, coalition = condition
    identity = condition_identity(p, rep, strategy, flagged, coalition, rule)
    key = digest(identity)
    producer = store.producer
    if not identity["flagged"] and key in baseline_cache:
        return baseline_cache[key]
    result = store.get("baseline", key) if not identity["flagged"] else None
    if result is None:
        require(not analyze_only, "analysis-only missing compact condition")
        hook("before_condition", identity)
        start = perf_counter()
        raw = PersistentSimulation(p, strategy, flagged, coalition, rule, repetition=rep, production=True).run()
        store.metrics["mining_seconds"] += perf_counter()-start
        if raw["status"] != "COMPLETE":
            raise IncompleteStudyError(condition, raw)
        result = _validate_fresh(store, raw, p, rule, rep, strategy, flagged, coalition)
        store.metrics["mining_simulations_executed"] += 1
        start = perf_counter()
        hook("validated_condition", {"raw": raw, "compact": result})
        store.metrics["diagnostic_measurement_seconds"] += perf_counter()-start
        del raw
        if not identity["flagged"]:
            store.put("baseline", key, result, hook)
    else:
        start = perf_counter()
        validate_compact(result, p, rule, rep, strategy, flagged, coalition, producer, store.validation)
        store.metrics["compact_validation_seconds"] += perf_counter()-start
    if not identity["flagged"]:
        baseline_cache[key] = result
    hook("after_condition", identity)
    return result


def load_repetition(store, ptask, rule, rep, payload, baseline_cache):
    p, tid = ptask.population, task_key(ptask, rule)
    require(payload["task_id"] == tid and payload["repetition"] == rep, "repetition identity")
    expected = required_conditions(ptask.coalitions)
    records = list(payload["conditions"])
    baseline_ids = set()
    for ref in payload["baselines"]:
        key = ref["condition_id"]
        require(key not in baseline_ids, "duplicate baseline reference")
        baseline_ids.add(key)
        if key not in baseline_cache:
            record = store.get("baseline", key)
            require(record is not None, "missing shared baseline")
            identity = record["identity"]
            validate_compact(record, p, rule, rep, identity["strategy"], False, (), store.producer, store.validation)
            require(not identity["flagged"], "flagged shared baseline")
            baseline_cache[key] = record
        record = baseline_cache[key]
        require(digest(record) == ref["sha256"], "baseline reference checksum")
        records.append(record)
    found = {}
    start = perf_counter()
    for record in records:
        identity = record["identity"]
        c = (identity["strategy"], identity["flagged"], tuple(identity["active_coalition"]))
        require(c not in found, "duplicate repetition condition")
        if c[1]:
            validate_compact(record, p, rule, rep, *c, store.producer, store.validation)
        else:
            same(record["identity"], condition_identity(p, rep, *c, rule), "cached baseline identity")
        found[c] = record
    require(set(found) == set(expected), "repetition condition coverage")
    require(len(payload["baselines"]) == 2 and all(r["identity"]["flagged"] for r in payload["conditions"]), "baseline duplication")
    store.metrics["compact_validation_seconds"] += perf_counter()-start
    return found


def repetition_range(total, rep_start=1, rep_end=None):
    """Public inclusive, one-based range; identities always retain native indices."""
    end = total if rep_end is None else rep_end
    require(type(rep_start) is int and type(end) is int and 1 <= rep_start <= end <= total,
            "invalid one-based repetition range")
    return rep_start-1, end


def task_analysis(store, ptask, rule, *, analyze_only=False, hook=lambda *args: None, baseline_cache=None,
                  rep_start=1, rep_end=None, preliminary=False):
    baseline_cache = {} if baseline_cache is None else baseline_cache
    spec = store.manifest["design"]
    total = spec["repetitions"]
    start_rep, end_rep = repetition_range(total, rep_start, rep_end)
    if preliminary:
        require(analyze_only and total == 10, "preliminary analysis requires the ten-repetition design")
        start_rep, end_rep = 0, 5
    tid, p = task_key(ptask, rule), ptask.population
    runs, repetition_refs = {}, []
    for rep in range(end_rep):
        rid = f"{tid}:{rep}"
        payload = store.get("repetition", rid)
        if payload is None:
            require(not analyze_only, "analysis-only missing repetition")
            require(rep >= start_rep, "earlier repetition phase incomplete")
            baselines = [_condition(store, p, rule, rep, (strategy, False, ()), False, hook, baseline_cache)
                         for strategy in ("honest", "selfish")]
            conditions = [_condition(store, p, rule, rep, c, False, hook, baseline_cache)
                          for c in required_conditions(ptask.coalitions) if c[1]]
            payload = {"task_id": tid, "repetition": rep,
                "baselines": [{"condition_id": r["condition_id"], "sha256": digest(r)} for r in baselines],
                "conditions": conditions}
            hook("before_repetition_commit", payload)
            store.put("repetition", rid, payload, hook)
            hook("after_repetition_commit", payload)
        conditions = load_repetition(store, ptask, rule, rep, payload, baseline_cache)
        runs.update({(rep, *c): analysis_record(r) for c, r in conditions.items()})
        repetition_refs.append({"id": rid, "sha256": digest(payload)})
    # Generic ranges can stop before either reporting boundary. Only the fixed
    # first-five snapshot and complete final design receive derived task records.
    n = total if end_rep == total else 5 if total == 10 and end_rep >= 5 else None
    if n is None:
        require(not analyze_only, "no supported analysis boundary")
        return None
    runs = {key: value for key, value in runs.items() if key[0] < n}
    start = perf_counter()
    result = _analyze_validated(p, rule, n, ptask.coalitions, spec["tpr"], spec["fpr"],
                               runs, spec["bootstrap_samples"], spec.get("selfish_prior"))
    from .persistent_v2_outputs import task_outputs
    result = task_outputs(result, ptask, rule, spec)
    store.metrics["aggregation_seconds"] += perf_counter()-start
    kind = "task" if n == total else "preliminary_task"
    durable = {"task_id": tid, "population_key": digest(asdict(p)), "rule": asdict(rule),
        "repetitions": repetition_refs[:n], "outputs": {k: v for k, v in result.items() if k != "repetitions"}}
    if analyze_only:
        existing = store.get(kind, tid)
        # A stable first-five view may be requested after a one-shot final run.
        # Authenticated repetition records suffice; an optional saved view must agree.
        if kind == "task" or existing is not None:
            same(existing, durable, "task analysis/receipt mismatch")
    else:
        store.put(kind, tid, durable, hook)
    hook("after_task_commit", durable)
    return result


def run_shard(directory, shard, *, analyze_only=False, hook=lambda *args: None,
              rep_start=1, rep_end=None, preliminary=False):
    manifest = load_manifest(directory)
    total = manifest["design"]["repetitions"]
    first, end = repetition_range(total, rep_start, rep_end)
    require(not preliminary or analyze_only, "preliminary flag is analysis-only")
    if preliminary:
        require(total == 10, "preliminary analysis requires ten repetitions")
        first, end = 0, 5
    rules = [Rule(**r) for r in manifest["design"]["variants"]]
    with shard_lock(directory, shard, shared=analyze_only):
        store = ShardStore(directory, manifest, shard, readonly=analyze_only)
        try:
            tasks = populations = 0
            for ptask in task_rows(directory, manifest, shard):
                baselines = {}
                populations += 1
                for rule in rules:
                    task_analysis(store, ptask, rule, analyze_only=analyze_only, hook=hook, baseline_cache=baselines,
                                  rep_start=first+1, rep_end=end, preliminary=preliminary)
                    tasks += 1
            complete = {"tasks": tasks, "baselines": populations*2*end, "repetitions": tasks*end,
                        "study_id": manifest["study_id"], "shard": shard}
            if end == total:
                for kind, count in (("baseline", populations*2*total), ("repetition", tasks*total), ("task", tasks)):
                    require(store.connection.execute("SELECT COUNT(*) FROM records WHERE kind=?", (kind,)).fetchone()[0] == count,
                            "unexpected shard rows")
                if not analyze_only:
                    store.put("complete", str(shard), complete, hook)
                else:
                    same(store.get("complete", str(shard)), complete, "incomplete shard")
            elif end == 5 and total == 10:
                if not analyze_only:
                    store.put("preliminary_complete", str(shard), complete, hook)
            return {**complete, **dict(store.metrics), "database_bytes": store.path.stat().st_size,
                    "analysis_status": f"FINAL_{total}_REPETITIONS" if end == total else
                        "PRELIMINARY_5_REPETITIONS" if total == 10 and end >= 5 else "PARTIAL_EXECUTION",
                    "requested_repetitions": [first+1, end], "final_repetitions": total}
        finally:
            store.close()


def merge_shards(directory, destination, *, preliminary=False):
    """Authenticated coverage + scientific reconstruction, no mining and no copies of baselines."""
    from contextlib import ExitStack
    manifest = load_manifest(directory)
    require(not preliminary or manifest["design"]["repetitions"] == 10, "preliminary merge requires ten repetitions")
    destination = Path(destination)
    require(not destination.exists(), "merge destination exists")
    temporary = destination.with_suffix(destination.suffix+".tmp")
    require(not temporary.exists(), "merge temporary exists")
    with ExitStack() as stack:
        for shard in range(manifest["design"]["shard_count"]):
            stack.enter_context(shard_lock(directory, shard, shared=True))
        connection = sqlite3.connect(temporary)
        try:
            connection.execute("CREATE TABLE tasks(task_id TEXT PRIMARY KEY,shard INTEGER,body BLOB,sha256 TEXT)")
            connection.execute("CREATE TABLE manifest(body TEXT)")
            total = 0
            for shard in range(manifest["design"]["shard_count"]):
                store = ShardStore(directory, manifest, shard, readonly=True)
                try:
                    if not preliminary:
                        require(store.get("complete", str(shard)) is not None, "incomplete shard")
                    count = 0
                    for ptask in task_rows(directory, manifest, shard):
                        baselines = {}
                        for variant in manifest["design"]["variants"]:
                            rule = Rule(**variant)
                            output = task_analysis(store, ptask, rule, analyze_only=True, baseline_cache=baselines, preliminary=preliminary)
                            tid = task_key(ptask, rule)
                            if preliminary:
                                raw = {"task_id": tid, "analysis_status": "PRELIMINARY_5_REPETITIONS",
                                       "outputs": {k: v for k, v in output.items() if k != "repetitions"}}
                            else:
                                raw = store.get("task", tid)
                                if store.get("preliminary_task", tid) is not None:
                                    task_analysis(store, ptask, rule, analyze_only=True, baseline_cache=baselines, preliminary=True)
                            body = canonical_json(raw).encode()
                            connection.execute("INSERT INTO tasks VALUES (?,?,?,?)", (tid, shard, zlib.compress(body), hashlib.sha256(body).hexdigest()))
                            count += 1
                    reps = manifest["design"]["repetitions"]
                    expected = {"task": count, "repetition": count*reps,
                        "baseline": count//len(manifest["design"]["variants"])*2*reps, "complete": 1}
                    counts = dict(store.connection.execute("SELECT kind,COUNT(*) FROM records GROUP BY kind"))
                    require(set(counts) <= {"task", "repetition", "baseline", "complete", "preliminary_task", "preliminary_complete"},
                            "merge extra/missing shard rows")
                    if not preliminary:
                        same({k: v for k, v in counts.items() if not k.startswith("preliminary_")},
                             {k: v for k, v in expected.items() if v}, "merge extra/missing shard rows")
                    expected_ids = {task_key(t, Rule(**v)) for t in task_rows(directory, manifest, shard)
                                    for v in manifest["design"]["variants"]}
                    require({row[0] for row in store.connection.execute("SELECT id FROM records WHERE kind='preliminary_task'")} <= expected_ids,
                            "foreign preliminary task")
                    if counts.get("preliminary_complete", 0):
                        require(counts["preliminary_complete"] == 1, "foreign preliminary marker")
                        same(store.get("preliminary_complete", str(shard)), {"tasks": count,
                            "baselines": count//len(manifest["design"]["variants"])*10,
                            "repetitions": count*5, "study_id": manifest["study_id"], "shard": shard}, "preliminary marker")
                    total += count
                finally:
                    store.close()
            require(total == manifest["scope"]["top_level_rule_configurations"], "merge task coverage")
            connection.execute("INSERT INTO manifest VALUES (?)", (canonical_json({"study": manifest,
                "source_directory": str(Path(directory).resolve()), "tasks": total,
                "status": "PRELIMINARY_5_REPETITIONS" if preliminary else "FINAL_10_REPETITIONS" if manifest["design"]["repetitions"] == 10 else "FINAL",
                "analysis_repetitions": 5 if preliminary else manifest["design"]["repetitions"]}),))
            connection.commit()
            require(connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "merged catalog integrity")
        except BaseException:
            connection.close()
            temporary.unlink(missing_ok=True)
            raise
        else:
            connection.close()
    temporary.replace(destination)
    return {"tasks": total, "catalog_bytes": destination.stat().st_size, "baseline_payloads_duplicated": 0,
            "analysis_status": "PRELIMINARY_5_REPETITIONS" if preliminary else "FINAL"}


def export_study(directory, destination, *, include_repetitions=False, preliminary=False):
    """Stream scientific CSVs by environment/total group; never launch mining.

Shared baseline copies appear only in an explicitly requested repetition export,
not in the durable checkpoint store. Cross-rule/composition vectors are reconstructed.
"""
    import csv
    from contextlib import ExitStack
    from itertools import groupby
    from .research_sweep import SweepTask, _flat
    from .persistent_v2_outputs import paired_comparisons
    from .persistent_v2_sweep import grouped_thresholds
    manifest = load_manifest(directory)
    require(not preliminary or manifest["design"]["repetitions"] == 10, "preliminary export requires ten repetitions")
    destination = Path(destination)
    require(not destination.exists(), "export destination exists")
    destination.mkdir(parents=True)
    atomic_json(destination / "status.json", {"status": "INCOMPLETE", "study_id": manifest["study_id"]})
    counts, writers, handles = Counter(), {}, {}

    def emit(name, rows):
        for row in rows:
            if name not in writers:
                handle = (destination / (name+".csv")).open("w", newline="")
                handles[name] = handle
                writers[name] = csv.DictWriter(handle, fieldnames=list(row))
                writers[name].writeheader()
            writers[name].writerow(_flat(row))
            counts[name] += 1

    with ExitStack() as stack:
        for shard in range(manifest["design"]["shard_count"]):
            stack.enter_context(shard_lock(directory, shard, shared=True))
        stores = {shard: ShardStore(directory, manifest, shard, readonly=True)
                  for shard in range(manifest["design"]["shard_count"])}
        temporary = destination / "threshold_groups.sqlite3"
        try:
            for shard, store in stores.items():
                if not preliminary:
                    require(store.get("complete", str(shard)) is not None, "incomplete export shard")
            with sqlite3.connect(temporary) as reduction, sqlite3.connect(
                    f"file:{Path(directory) / 'plan.sqlite3'}?mode=ro", uri=True) as plan:
                reduction.execute("CREATE TABLE summaries(group_key TEXT,body TEXT)")
                reduction.execute("CREATE INDEX groups ON summaries(group_key)")
                cursor = plan.execute("SELECT analysis_group,owner,body FROM tasks ORDER BY analysis_group,ordinal")
                for _, group in groupby(cursor, key=lambda row: row[0]):
                    results = []
                    for _, owner, body in group:
                        raw = json.loads(body)
                        raw["population"]["candidates"] = tuple(tuple(x) for x in raw["population"]["candidates"])
                        raw["population"] = Population(**raw["population"])
                        raw["coalitions"] = tuple(tuple(c) for c in raw["coalitions"])
                        task, baselines = SweepTask(**raw), {}
                        for variant in manifest["design"]["variants"]:
                            result = task_analysis(stores[owner], task, Rule(**variant), analyze_only=True, baseline_cache=baselines, preliminary=preliminary)
                            results.append(result)
                            for name, rows in result.items():
                                if name == "minimum_tested_thresholds" or (name == "repetitions" and not include_repetitions):
                                    continue
                                emit(name, rows)
                            from .persistent_sweep import analysis_group_key
                            for row in result["summary"]:
                                reduction.execute("INSERT INTO summaries VALUES (?,?)", (canonical_json(analysis_group_key(row)), canonical_json(row)))
                    emit("equal_power_comparisons", paired_comparisons(results))
                    emit("six_variant_comparisons", paired_comparisons(results, cross_rule=True))
                    reduction.commit()
                for group, in reduction.execute("SELECT DISTINCT group_key FROM summaries ORDER BY group_key"):
                    emit("minimum_tested_thresholds", grouped_thresholds([json.loads(row[0]) for row in reduction.execute(
                        "SELECT body FROM summaries WHERE group_key=? ORDER BY rowid", (group,))]))
            temporary.unlink()
        finally:
            for store in stores.values():
                store.close()
            for handle in handles.values():
                handle.close()
    for name in ("summary", "members", "detector", "tpr_thresholds", "false_positive_costs", "weakest_members",
                 "minimal_winning_coalitions", "minimum_tested_thresholds", "stage_c_candidates", "boundary_diagnostics",
                 "equal_power_comparisons", "six_variant_comparisons"):
        if name not in writers:
            (destination / (name+".csv")).write_text("")
            counts[name] = 0
    result = {"status": "PRELIMINARY_5_REPETITIONS" if preliminary else "COMPLETE",
              "analysis_status": "PRELIMINARY_5_REPETITIONS" if preliminary else "FINAL",
              "analysis_repetitions": 5 if preliminary else manifest["design"]["repetitions"],
              "final_repetitions": manifest["design"]["repetitions"], "study_id": manifest["study_id"], "row_counts": dict(counts),
              "repetitions_exported": include_repetitions, "automatic_followup": False}
    atomic_json(destination / "status.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("config", type=Path)
    plan.add_argument("directory", type=Path)
    run = sub.add_parser("run")
    run.add_argument("directory", type=Path)
    run.add_argument("--shard", type=int, required=True)
    run.add_argument("--analyze-only", action="store_true")
    run.add_argument("--rep-start", type=int, default=1, help="first repetition, one-based inclusive")
    run.add_argument("--rep-end", type=int, help="last repetition, one-based inclusive")
    run.add_argument("--preliminary", action="store_true", help="analyze exactly repetitions 1–5")
    merge = sub.add_parser("merge")
    merge.add_argument("directory", type=Path)
    merge.add_argument("destination", type=Path)
    merge.add_argument("--preliminary", action="store_true")
    export = sub.add_parser("export")
    export.add_argument("directory", type=Path)
    export.add_argument("destination", type=Path)
    export.add_argument("--include-repetitions", action="store_true")
    export.add_argument("--preliminary", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        result = prepare_study(json.loads(args.config.read_text()), args.directory)["scope"]
    elif args.command == "run":
        result = run_shard(args.directory, args.shard, analyze_only=args.analyze_only,
                           rep_start=args.rep_start, rep_end=args.rep_end, preliminary=args.preliminary)
    elif args.command == "merge":
        result = merge_shards(args.directory, args.destination, preliminary=args.preliminary)
    else:
        result = export_study(args.directory, args.destination, include_repetitions=args.include_repetitions, preliminary=args.preliminary)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
