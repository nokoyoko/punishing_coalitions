"""Compact scientific equivalence, authenticated boundaries, crash-safe shards."""
import copy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from statistics import stdev
from unittest.mock import Mock
import zlib

import pytest

from punishment_sim import persistent_v2_shards as shards
from punishment_sim.coalition import paired_stats
from punishment_sim.persistent_checkpoint import canonical_json, digest
from punishment_sim.persistent_study import required_conditions
from punishment_sim.persistent_v2 import PersistentSimulation, Rule, NETWORK_VERSION
from punishment_sim.persistent_v2_compact import (compact_run, validate_compact, terminal_summary,
    runtime_identity, rerun_condition)
from punishment_sim.persistent_v2_outputs import task_outputs, paired_comparisons
from punishment_sim.persistent_v2_study import analyze

ROOT = Path(__file__).resolve().parents[1]


def design(repetitions=2, horizon=20, workers=1, variants=None):
    return {"expected_network_version": NETWORK_VERSION, "repetitions": repetitions,
        "accepted_blocks": horizon, "seed": 701, "bootstrap_samples": 20, "tpr": [.5, .9], "fpr": [0, .01],
        "shard_count": workers, "variants": [asdict(r) for r in (variants or shards.VARIANTS)],
        "composition": {"target_hash": [.2], "candidate_power": [.2], "gamma": [.5], "natural_fork_rate": [0, .02],
            "systematic": {"power_step": .1, "minimum_member_power": .1, "member_counts": [2]}}}


def logical_rows(directory):
    rows = {}
    for path in sorted(Path(directory).glob("shard-*.sqlite3")):
        with sqlite3.connect(path) as connection:
            for kind, key, blob in connection.execute("SELECT kind,id,body FROM records ORDER BY kind,id"):
                if kind != "complete":
                    rows[(kind, key)] = json.loads(zlib.decompress(blob))
    return rows


def test_intended_design_exactly_ten_and_historical_grid_untouched():
    current = json.loads((ROOT / "configs/persistent_v2_1pct_10rep.json").read_text())
    historical = json.loads((ROOT / "configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_1pct.json").read_text())
    assert current["repetitions"] == 10 and historical["repetitions"] == 20
    assert current["variants"] == [asdict(r) for r in shards.VARIANTS]
    assert current["shard_count"] == 28
    for key in ("accepted_blocks", "seed", "aggregate", "authorization_rule", "minimum_residual_power", "tpr", "fpr", "bootstrap_samples"):
        assert current[key] == historical[key]
    expected_composition = copy.deepcopy(historical["composition"])
    expected_composition["candidate_power"] = [i/100 for i in range(5,52)]
    expected_composition["systematic"]["member_counts"] = [2, 3, 4]
    assert current["composition"] == expected_composition
    assert historical["composition"]["candidate_power"][-1] == .60
    scope = json.loads((ROOT / "docs/persistent_v2_core_2to4_scope.json").read_text())
    assert scope["exact_enumeration"] and scope["populations"] == 126666
    assert scope["top_level_rule_configurations"] == 759996
    assert scope["per_variant_simulations"] == 8866620
    assert scope["after_reuse"] == 40533120
    assert scope["accepted_block_work_after_reuse"] == 1215993600000
    assert sum(scope["populations_by_shard"].values()) == 126666
    assert not scope["adaptive_followup"]


def test_ten_paired_values_use_student_t_df9_not_normal():
    left = [i/11 for i in range(10)]
    right = [i/13 for i in range(10)]
    values = [a-b for a,b in zip(left, right)]
    stats = paired_stats(values, left, right)
    assert stats["n"] == 10 and stats["sample_sd"] == stdev(values)
    assert stats["standard_error"] == stdev(values)/math.sqrt(10)
    assert stats["ci95_high"]-stats["mean"] == pytest.approx(2.262*stats["standard_error"])
    assert stats["ci95_high"]-stats["mean"] != pytest.approx(1.96*stats["standard_error"])


@pytest.mark.parametrize("rule", shards.VARIANTS)
@pytest.mark.parametrize("repetition", [0, 9])
def test_compact_terminal_and_exact_debug_regeneration(rule, repetition):
    from punishment_sim.coalition import Population
    p = Population(.2, (("c1", .1), ("c2", .1)), .5, .02, 80, 701)
    raw = PersistentSimulation(p, "selfish", True, ("c1", "c2"), rule, production=True, repetition=repetition).run()
    record = compact_run(raw, p, rule, repetition, "selfish", True, ("c1", "c2"), digest(runtime_identity()))
    validate_compact(record, p, rule, repetition, "selfish", True, ("c1", "c2"), digest(runtime_identity()))
    assert record["terminal"]["boundary"] == raw["terminal"]["boundary"]
    assert record["terminal"]["terminal_sha256"] == digest(raw["terminal"])
    assert "canonical_blocks" not in record["terminal"] and "frontier_blocks" not in record["terminal"]
    assert sum(a["accepted"] for a in record["actors"].values()) == record["accepted_blocks"]
    debug = rerun_condition(record, trace=True)
    assert debug["trace"] and debug["terminal"] == raw["terminal"]
    bad = copy.deepcopy(raw)
    bad["actors"]["target"]["accepted"] += 1
    with pytest.raises(ValueError):
        compact_run(bad, p, rule, repetition, "selfish", True, ("c1", "c2"), digest(runtime_identity()))


def test_ten_repetition_complete_scientific_equivalence_all_variants(tmp_path):
    spec = design(10)
    spec["composition"].pop("systematic")
    spec["composition"]["structures"] = ["two_equal", "two_unequal"]
    manifest = shards.prepare_study(spec, tmp_path)
    result = shards.run_shard(tmp_path, 0)
    assert result["mining_simulations_executed"] == manifest["scope"]["after_reuse"]
    store = shards.ShardStore(tmp_path, manifest, 0, readonly=True)
    compact, debug = [], []
    try:
        for task in shards.task_rows(tmp_path, manifest, 0):
            for rule in shards.VARIANTS:
                current = shards.task_analysis(store, task, rule, analyze_only=True)
                runs = {(rep,*condition): PersistentSimulation(task.population, *condition, rule, repetition=rep).run()
                    for rep in range(10) for condition in required_conditions(task.coalitions)}
                full = analyze(task.population, rule, 10, task.coalitions, spec["tpr"], spec["fpr"], runs, 20)
                expected = task_outputs(full, task, rule, spec)
                assert digest(current) == digest(expected)  # every scientific collection, including terminal summaries
                assert all(row["deterrence"]["n"] == 10 for row in current["summary"])
                compact.append(current)
                debug.append(expected)
        assert paired_comparisons(compact) == paired_comparisons(debug)
        assert paired_comparisons(compact, cross_rule=True) == paired_comparisons(debug, cross_rule=True)
        assert paired_comparisons(compact) and paired_comparisons(compact, cross_rule=True)
    finally:
        store.close()
    records = logical_rows(tmp_path)
    assert sum(k[0] == "baseline" for k in records) == 4*10*2
    for (kind, key), record in records.items():
        if kind == "repetition":
            assert len(record["baselines"]) == 2 and all(r["identity"]["flagged"] for r in record["conditions"])
        if kind == "task":
            assert "repetitions" not in record["outputs"]
    exported = shards.export_study(tmp_path, tmp_path / "exports", include_repetitions=True)
    assert exported["status"] == "COMPLETE" and exported["row_counts"]["repetitions"] > 0
    assert exported["row_counts"]["six_variant_comparisons"] and exported["row_counts"]["equal_power_comparisons"]


@pytest.mark.parametrize("phase", ["before_condition", "after_condition", "before_repetition_commit",
                                  "after_repetition_commit", "after_task_commit", "during_flush"])
def test_interrupted_work_resumes_without_duplicates_or_baseline_recomputation(tmp_path, monkeypatch, phase):
    spec = design(variants=(Rule("petty"), Rule("ignore")))
    uninterrupted, interrupted = tmp_path / "full", tmp_path / "interrupted"
    shards.prepare_study(spec, uninterrupted)
    shards.run_shard(uninterrupted, 0)
    shards.prepare_study(spec, interrupted)
    seen = 0
    def fail(event, value):
        nonlocal seen
        if event == phase:
            seen += 1
            if seen == 3:
                raise InterruptedError("injected interruption")
    with pytest.raises(InterruptedError):
        shards.run_shard(interrupted, 0, hook=fail)
    before = logical_rows(interrupted)
    original = shards.PersistentSimulation
    def observed(*args, **kwargs):
        sim = original(*args, **kwargs)
        assert ("baseline", digest(sim.identity)) not in before
        return sim
    monkeypatch.setattr(shards, "PersistentSimulation", observed)
    shards.run_shard(interrupted, 0)
    assert logical_rows(interrupted) == logical_rows(uninterrupted)
    monkeypatch.setattr(shards, "PersistentSimulation", Mock(side_effect=AssertionError("mining forbidden")))
    shards.run_shard(interrupted, 0, analyze_only=True)
    shards.run_shard(interrupted, 0)
    assert logical_rows(interrupted) == logical_rows(uninterrupted)


def test_mid_condition_failure_preserves_committed_baselines(tmp_path, monkeypatch):
    shards.prepare_study(design(variants=(Rule("petty"),)), tmp_path)
    original_step = PersistentSimulation.step
    def fail_midway(self, *args, **kwargs):
        if self.enabled and self.events == 5:
            raise InterruptedError("mid-discovery")
        return original_step(self, *args, **kwargs)
    monkeypatch.setattr(PersistentSimulation, "step", fail_midway)
    with pytest.raises(InterruptedError):
        shards.run_shard(tmp_path, 0)
    assert sum(kind == "baseline" for kind, key in logical_rows(tmp_path)) == 2
    assert not any(kind == "repetition" for kind, key in logical_rows(tmp_path))
    monkeypatch.setattr(PersistentSimulation, "step", original_step)
    shards.run_shard(tmp_path, 0)


def test_hard_process_exit_during_database_flush_rolls_back(tmp_path):
    shards.prepare_study(design(variants=(Rule("petty"),)), tmp_path)
    script = """import os, sys
from punishment_sim.persistent_v2_shards import run_shard
def hook(event, value):
    if event == 'during_flush' and value['kind'] == 'repetition':
        os._exit(91)
run_shard(sys.argv[1], 0, hook=hook)
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], cwd=ROOT)
    assert result.returncode == 91
    assert not any(kind == "repetition" for kind,key in logical_rows(tmp_path))
    metrics = shards.run_shard(tmp_path, 0)
    assert metrics["tasks"] == 2


def test_28_isolated_workers_ownership_and_strict_merge(tmp_path, monkeypatch):
    manifest = shards.prepare_study(design(workers=28), tmp_path)
    with ThreadPoolExecutor(max_workers=28) as pool:
        results = list(pool.map(lambda i: shards.run_shard(tmp_path, i), range(28)))
    assert sum(r.get("mining_simulations_executed", 0) for r in results) == manifest["scope"]["after_reuse"]
    assert len(list(tmp_path.glob("shard-*.sqlite3"))) == 28
    monkeypatch.setattr(shards, "PersistentSimulation", Mock(side_effect=AssertionError("merge cannot mine")))
    merged = shards.merge_shards(tmp_path, tmp_path / "merged.sqlite3")
    assert merged["tasks"] == 12 and merged["baseline_payloads_duplicated"] == 0
    with shards.shard_lock(tmp_path, 0):
        with pytest.raises(ValueError, match="active writer"):
            shards.run_shard(tmp_path, 0)


def test_merge_rejects_missing_foreign_and_resealed_corrupt_data(tmp_path):
    manifest = shards.prepare_study(design(workers=2), tmp_path)
    shards.run_shard(tmp_path, 0)
    with pytest.raises((ValueError, sqlite3.OperationalError)):
        shards.merge_shards(tmp_path, tmp_path / "incomplete.sqlite3")
    assert not (tmp_path / "incomplete.sqlite3").exists()
    shards.run_shard(tmp_path, 1)
    owner = next(int(k) for k,v in manifest["scope"]["populations_by_shard"].items() if v)
    with sqlite3.connect(tmp_path / f"shard-{owner:02d}.sqlite3") as connection:
        key, blob = connection.execute("SELECT id,body FROM records WHERE kind='baseline' LIMIT 1").fetchone()
        record = json.loads(zlib.decompress(blob))
        record["actors"]["target"]["accepted"] += 1
        body = canonical_json(record).encode()
        connection.execute("UPDATE records SET body=?,sha256=? WHERE kind='baseline' AND id=?",
            (zlib.compress(body), hashlib.sha256(body).hexdigest(), key))
    with pytest.raises(ValueError, match="receipt mismatch"):
        shards.merge_shards(tmp_path, tmp_path / "corrupt.sqlite3")
    assert not (tmp_path / "corrupt.sqlite3").exists()


def test_normal_production_entry_uses_compact_store_and_ten_default(tmp_path):
    from punishment_sim.persistent_v2_sweep import run_sweep
    spec = design(variants=(Rule("petty"),))
    spec.pop("repetitions")
    spec.pop("variants")
    spec.pop("shard_count")
    spec.update(punishment_rule="petty", counter_fork_k=None, expected_model_version="persistent-petty-v2")
    result = run_sweep(spec, tmp_path, production=True)
    assert result["layout"] == shards.LAYOUT and result["metadata"]["repetitions"] == 10
    assert not list(tmp_path.rglob("*.json.gz"))
    assert not list(tmp_path.glob("v2_conditions*"))


def test_native_validation_once_per_new_run_and_no_native_replay_on_resume(tmp_path, monkeypatch):
    manifest = shards.prepare_study(design(), tmp_path)
    validate = Mock(wraps=shards.validate_run)
    monkeypatch.setattr(shards, "validate_run", validate)
    shards.run_shard(tmp_path, 0)
    assert validate.call_count == manifest["scope"]["after_reuse"]
    validate.reset_mock()
    shards.run_shard(tmp_path, 0, analyze_only=True)
    assert validate.call_count == 0


def test_merge_reconstructs_analysis_even_if_a_wrong_derived_row_has_a_valid_receipt(tmp_path):
    manifest = shards.prepare_study(design(variants=(Rule("petty"),)), tmp_path)
    shards.run_shard(tmp_path, 0)
    store = shards.ShardStore(tmp_path, manifest, 0)
    try:
        key, = store.connection.execute("SELECT id FROM records WHERE kind='task' LIMIT 1").fetchone()
        value = store.get("task", key)
        value["outputs"]["summary"][0]["deterrence"]["mean"] += .1
        body = canonical_json(value).encode()
        checksum = hashlib.sha256(body).hexdigest()
        with store.connection:
            store.connection.execute("UPDATE records SET body=?,sha256=?,receipt=? WHERE kind='task' AND id=?",
                (zlib.compress(body), checksum, store._receipt("task", key, checksum), key))
    finally:
        store.close()
    with pytest.raises(ValueError, match="task analysis"):
        shards.merge_shards(tmp_path, tmp_path / "merged.sqlite3")


def test_foreign_rows_and_missing_baselines_fail_merge(tmp_path):
    manifest = shards.prepare_study(design(variants=(Rule("petty"),)), tmp_path)
    shards.run_shard(tmp_path, 0)
    store = shards.ShardStore(tmp_path, manifest, 0)
    try:
        store.put("unexpected", "foreign", {"not_in_plan": True})
        with pytest.raises(ValueError, match="extra/missing"):
            shards.merge_shards(tmp_path, tmp_path / "extra.sqlite3")
        with store.connection:
            store.connection.execute("DELETE FROM records WHERE kind='unexpected'")
            store.connection.execute("DELETE FROM records WHERE kind='baseline'")
        with pytest.raises(ValueError, match="missing shared baseline"):
            shards.merge_shards(tmp_path, tmp_path / "missing.sqlite3")
    finally:
        store.close()


def test_shard_assignment_does_not_change_scientific_records(tmp_path):
    for count in (1, 4):
        directory = tmp_path / str(count)
        shards.prepare_study(design(workers=count), directory)
        for shard in reversed(range(count)):
            shards.run_shard(directory, shard)
    assert logical_rows(tmp_path / "1") == logical_rows(tmp_path / "4")


def test_fixed_ten_repetition_benchmark_evidence_and_native_source_identity():
    evidence = json.loads((ROOT / "docs/persistent_v2_compact_benchmark.json").read_text())
    assert evidence["status"] == "COMPLETE" and evidence["repetitions"] == 10 and evidence["horizon"] == 30000
    assert len(evidence["tasks"]) == 14 and len(evidence["conditions"]) == 700
    assert all(r["reference_blocks"] >= 30000 for r in evidence["conditions"])
    assert {r["repetition"] for r in evidence["conditions"]} == set(range(10))
    assert all(s["runtime"]["sources"]["persistent_v2"] == runtime_identity()["sources"]["persistent_v2"] and s["resume_metrics"].get("mining_simulations_executed",0) == 0
               for s in evidence["studies"])
    assert not any(evidence[k] for k in ("production_sweep", "remote_job", "ssh", "xtra_access"))
