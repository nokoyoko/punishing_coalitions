"""Explicit, fail-closed reuse of v3 zero-lambda population batches.

This module never mines. Source files remain untouched. The destination's v4
version describes its compatibility envelope, while simulation_model_version
continues to identify the v3 execution. Historical unversioned checkpoints are
intentionally unsupported: their format/provenance needs a separate audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .coalition import MODEL_VERSION

SOURCE_MODEL_VERSION = "race-owner-oceanic-residual-v3"
DESTINATION_MODEL_VERSION = "race-owner-oceanic-all-races-v4"
PROVENANCE_SCHEMA = "explicit-zero-lambda-compatibility-v1"
COMPATIBILITY_RULE = "explicit-v3-to-v4-natural-fork-rate-exactly-zero-v1"
VALIDATION_EVIDENCE = "docs/oceanic_all_races_v4.md;tests/fixtures/oceanic_v3_zero_lambda.json"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def value_sha256(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def versioned_specification_hash(spec, model_version):
    return hashlib.sha256((model_version + "\n" + canonical(spec)).encode()).hexdigest()


def checkpoint_provenance(saved):
    """Scalar output columns; caller must validate checkpoints before trusting them."""
    provenance = saved.get("compatibility_provenance", {})
    simulation_version = saved.get("simulation_model_version", saved.get("model_version", "unverified_legacy"))
    return {
        "artifact_model_version": saved.get("model_version", "unverified_legacy"),
        "simulation_model_version": simulation_version,
        "execution_provenance": ("reused_from_behaviorally_equivalent_v3_zero_lambda" if provenance
                                 else "executed_under_v4" if simulation_version == DESTINATION_MODEL_VERSION
                                 else "executed_under_source_model"),
        "source_checkpoint_path": provenance.get("source_checkpoint_path", ""),
        "source_checkpoint_sha256": provenance.get("source_checkpoint_sha256", ""),
        "compatibility_rule": provenance.get("compatibility_rule", ""),
    }


def _scientific_spec(spec):
    # Only run labels, expected envelope version and scheduling may differ. In
    # particular detector, authorization, bootstrap and Stage C fields must match.
    return {k: v for k, v in spec.items() if k not in {"stage", "expected_model_version", "execution_workers"}}


def check_spec_compatibility(source_spec, destination_spec):
    if MODEL_VERSION != DESTINATION_MODEL_VERSION:
        raise ValueError("compatibility rule is only valid for the audited v4 runtime")
    if source_spec.get("expected_model_version") != SOURCE_MODEL_VERSION:
        raise ValueError("source configuration must explicitly declare v3")
    if destination_spec.get("expected_model_version") != DESTINATION_MODEL_VERSION:
        raise ValueError("destination configuration must explicitly declare v4")
    if canonical(_scientific_spec(source_spec)) != canonical(_scientific_spec(destination_spec)):
        raise ValueError("source and destination scientific configurations differ")


def validate_compatibility(saved, record, config_hash, repetitions):
    """Validate a derived envelope and recheck its immutable original source."""
    from .sharded_sweep import _validate_checkpoint_payload

    try:
        provenance = saved["compatibility_provenance"]
        if provenance.get("provenance_schema") != PROVENANCE_SCHEMA:
            return False, "compatibility_schema"
        if provenance.get("compatibility_rule") != COMPATIBILITY_RULE:
            return False, "compatibility_rule"
        if provenance.get("engine") != "ExplicitSimulation":
            return False, "compatibility_engine"
        if saved.get("simulation_model_version") != SOURCE_MODEL_VERSION:
            return False, "simulation_model_version"
        if (provenance.get("source_model_version") != SOURCE_MODEL_VERSION or
                provenance.get("destination_model_version") != DESTINATION_MODEL_VERSION):
            return False, "compatibility_versions"
        if record["population"]["natural_fork_rate"] != 0:
            return False, "compatibility_requires_zero_lambda"
        source_spec = provenance["source_configuration"]
        destination_spec = provenance["destination_configuration"]
        check_spec_compatibility(source_spec, destination_spec)
        if versioned_specification_hash(destination_spec, MODEL_VERSION) != config_hash:
            return False, "compatibility_destination_configuration_hash"
        source_hash = versioned_specification_hash(source_spec, SOURCE_MODEL_VERSION)
        if provenance.get("source_configuration_hash") != source_hash:
            return False, "compatibility_source_configuration_hash"
        if int(source_spec["repetitions"]) != repetitions:
            return False, "compatibility_repetitions"
        source_path = Path(provenance["source_checkpoint_path"])
        if not source_path.is_absolute():
            return False, "compatibility_source_path"
        raw = source_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != provenance["source_checkpoint_sha256"]:
            return False, "compatibility_source_checksum"
        source = json.loads(raw)
        if source.get("compatibility_provenance") or source.get("simulation_model_version", SOURCE_MODEL_VERSION) != SOURCE_MODEL_VERSION:
            return False, "compatibility_source_not_native_v3"
        source_record = {**record, "num_shards": provenance["source_num_shards"],
                         "shard_index": provenance["source_shard_index"]}
        valid, reason = _validate_checkpoint_payload(source, source_record, source_hash, repetitions, SOURCE_MODEL_VERSION)
        if not valid:
            return False, "compatibility_source_" + reason
        if (canonical(saved["result"]) != canonical(source["result"]) or
                canonical(saved["cache_audit"]) != canonical(source["cache_audit"])):
            return False, "compatibility_source_payload_changed"
        if value_sha256(saved["result"]) != provenance["source_result_sha256"]:
            return False, "compatibility_result_checksum"
        if provenance.get("validation_evidence") != VALIDATION_EVIDENCE:
            return False, "compatibility_validation_evidence"
        valid, reason = _validate_detector_inputs(source["result"], source_spec, record)
        if not valid:
            return False, reason
        return True, "valid"
    except Exception as exc:
        return False, f"compatibility_corrupt:{type(exc).__name__}"


def _validate_detector_inputs(result, spec, record):
    expected = {(tuple(c), tpr, fpr) for c in record["coalitions"] for tpr in spec["tpr"] for fpr in spec["fpr"]}
    rows = result["detector"]
    actual = [(tuple(row["members"]), row["tpr"], row["fpr"]) for row in rows]
    if len(actual) != len(expected) or set(actual) != expected:
        return False, "detector_coverage"
    if any(("prior_weighted" in row) != (spec.get("selfish_prior") is not None) for row in rows):
        return False, "detector_prior"
    return True, "valid"


def _source_manifest(source_dir, source_spec):
    from .research_sweep import generate_tasks
    from .sharded_sweep import _task_record

    source_dir = Path(source_dir)
    audit_path = source_dir / "manifest_audit.json"
    audit = json.loads(audit_path.read_text())
    if audit.get("schema") != "sharded-sweep-manifest-v1" or audit.get("model_version") != SOURCE_MODEL_VERSION:
        raise ValueError("source manifest has unsupported schema or model version")
    if audit.get("configuration_hash") != versioned_specification_hash(source_spec, SOURCE_MODEL_VERSION):
        raise ValueError("source manifest configuration hash mismatch")
    shards = audit["num_shards"]
    if type(shards) is not int or shards < 1:
        raise ValueError("source manifest shard count invalid")
    tasks, requested, valid = generate_tasks(source_spec)
    records = sorted((_task_record(task, shards) for task in tasks), key=lambda r: r["task_id"])
    manifest_path = source_dir / "task_manifest.jsonl"
    manifest_raw = manifest_path.read_bytes()
    observed = sorted((json.loads(line) for line in manifest_raw.splitlines() if line.strip()), key=lambda r: r["task_id"])
    if canonical(observed) != canonical(records):
        raise ValueError("source manifest task coverage/scientific inputs mismatch")
    expected_counts = {"requested_population_configurations": requested, "valid_population_requests": valid,
                       "unique_population_configurations": len(records),
                       "tasks_by_shard": {str(i): sum(r["shard_index"] == i for r in records) for i in range(shards)}}
    if any(audit.get(k) != v for k, v in expected_counts.items()):
        raise ValueError("source manifest audit coverage mismatch")
    return records, {"source_manifest_path": str(manifest_path.resolve()),
                     "source_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                     "source_manifest_audit_path": str(audit_path.resolve()),
                     "source_manifest_audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest()}


def import_zero_lambda(source_spec, destination_spec, source_dir, destination_dir, num_shards):
    """Import all and only matching zero-lambda tasks; never execute simulations."""
    from .research_sweep import generate_tasks
    from .sharded_sweep import (_atomic_json, _task_record, _validate_checkpoint_payload,
                                build_manifest, validate_checkpoint)

    check_spec_compatibility(source_spec, destination_spec)
    source_dir = Path(source_dir).resolve()
    destination_dir = Path(destination_dir).resolve()
    if source_dir == destination_dir or source_dir in destination_dir.parents or destination_dir in source_dir.parents:
        raise ValueError("source and destination must be separate, nonnested directories")
    if type(num_shards) is not int or num_shards < 1:
        raise ValueError("destination shard count must be a positive integer")
    sources, manifest_provenance = _source_manifest(source_dir, source_spec)
    tasks = generate_tasks(destination_spec)[0]
    destinations = sorted((_task_record(task, num_shards) for task in tasks), key=lambda r: r["task_id"])
    scientific_record = lambda r: {k: v for k, v in r.items() if k not in {"num_shards", "shard_index"}}
    if canonical([scientific_record(r) for r in sources]) != canonical([scientific_record(r) for r in destinations]):
        raise ValueError("source and destination task manifests differ")
    source_by_id = {r["task_id"]: r for r in sources}
    selected = [r for r in destinations if r["population"]["natural_fork_rate"] == 0]
    if not selected:
        raise ValueError("no zero-lambda tasks to import")
    reps = int(destination_spec["repetitions"])
    destination_hash = versioned_specification_hash(destination_spec, MODEL_VERSION)
    source_hash = versioned_specification_hash(source_spec, SOURCE_MODEL_VERSION)
    # Validate all source batches and existing destinations before writing any.
    verified = []
    for record in selected:
        source_path = source_dir / "checkpoints" / (record["task_id"] + ".json")
        raw = source_path.read_bytes()
        source = json.loads(raw)
        valid, reason = _validate_checkpoint_payload(source, source_by_id[record["task_id"]], source_hash, reps, SOURCE_MODEL_VERSION)
        if not valid:
            raise ValueError(f"source checkpoint {source_path}: {reason}")
        if source.get("compatibility_provenance") or source.get("simulation_model_version", SOURCE_MODEL_VERSION) != SOURCE_MODEL_VERSION:
            raise ValueError("only native v3 source checkpoints are supported")
        valid, reason = _validate_detector_inputs(source["result"], source_spec, record)
        if not valid:
            raise ValueError(f"source checkpoint {source_path}: {reason}")
        destination_path = destination_dir / "checkpoints" / (record["task_id"] + ".json")
        if destination_path.exists():
            valid, reason = validate_checkpoint(destination_path, record, destination_hash, reps)
            if not valid:
                raise ValueError(f"existing destination checkpoint {destination_path}: {reason}")
        verified.append((record, source_path, hashlib.sha256(raw).hexdigest(), destination_path))
    build_manifest(destination_spec, destination_dir, num_shards)
    created = reused = represented = 0
    for record, source_path, checksum, destination_path in verified:
        raw = source_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError(f"source changed during import: {source_path}")
        source = json.loads(raw)
        represented += source["cache_audit"]["misses"]
        if destination_path.exists():
            valid, reason = validate_checkpoint(destination_path, record, destination_hash, reps)
            if not valid:
                raise ValueError(f"destination changed during import: {reason}")
            reused += 1
            continue
        provenance = {
            "provenance_schema": PROVENANCE_SCHEMA, "compatibility_rule": COMPATIBILITY_RULE,
            "engine": "ExplicitSimulation", "source_model_version": SOURCE_MODEL_VERSION,
            "destination_model_version": MODEL_VERSION, "source_checkpoint_path": str(source_path),
            "source_checkpoint_sha256": checksum, "source_result_sha256": value_sha256(source["result"]),
            "source_configuration": source_spec, "destination_configuration": destination_spec,
            "source_configuration_hash": source_hash, "source_num_shards": source["num_shards"],
            "source_shard_index": source["shard_index"], "validation_evidence": VALIDATION_EVIDENCE,
        }
        derived = {**source, "model_version": MODEL_VERSION, "simulation_model_version": SOURCE_MODEL_VERSION,
                   "configuration_hash": destination_hash, "num_shards": record["num_shards"],
                   "shard_index": record["shard_index"], "compatibility_provenance": provenance}
        valid, reason = validate_compatibility(derived, record, destination_hash, reps)
        if not valid:
            raise ValueError(f"derived checkpoint validation failed: {reason}")
        _atomic_json(destination_path, derived)
        created += 1
    audit = {"schema": "zero-lambda-import-audit-v1", "status": "COMPLETE", "compatibility_rule": COMPATIBILITY_RULE,
             "source_model_version": SOURCE_MODEL_VERSION, "artifact_model_version": MODEL_VERSION,
             "source_directory": str(source_dir), "destination_directory": str(destination_dir),
             "source_configuration_hash": source_hash, "destination_configuration_hash": destination_hash,
             "full_manifest_tasks": len(destinations), "zero_lambda_tasks": len(selected),
             "created_compatibility_checkpoints": created, "already_valid_destination_checkpoints": reused,
             "mining_simulations_represented_by_selected_source_tasks": represented,
             "mining_simulations_executed_by_import": 0, **manifest_provenance}
    _atomic_json(destination_dir / "zero_lambda_import_audit.json", audit)
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-config", required=True)
    parser.add_argument("--destination-config", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--destination-dir", required=True)
    parser.add_argument("--num-shards", required=True, type=int)
    args = parser.parse_args(argv)
    audit = import_zero_lambda(json.loads(Path(args.source_config).read_text()),
                               json.loads(Path(args.destination_config).read_text()),
                               args.source_dir, args.destination_dir, args.num_shards)
    print(json.dumps(audit, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
