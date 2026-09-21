"""Tiny local fixtures only; never load a production sweep or checkpoint."""
import copy
import csv
import json
from statistics import mean, stdev

import pytest

from punishment_sim import coalition as legacy
from punishment_sim import persistent_study as research
from punishment_sim.coalition import Population
from punishment_sim.persistent import MODEL_VERSION, PersistentSimulation, PunishmentSpec, mining_cache_key
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_sweep import (analysis_group_key, grouped_thresholds, prepare,
                                            run_sweep, scope, unpack_conditions)


def population():
    return Population(.2, (("c1", .1), ("c2", .1)), .5, .1, 12, 701)


def spec(k=2):
    return {"expected_model_version": MODEL_VERSION, "punishment_rule": "counter_fork", "counter_fork_k": k,
            "seed": 701, "accepted_blocks": 12, "repetitions": 2, "bootstrap_samples": 12,
            "tpr": [.5, 1], "fpr": [0, .1],
            "composition": {"target_hash": [.2], "candidate_power": [.2], "gamma": [.5],
                "natural_fork_rate": [0, .2], "systematic": {"power_step": .1,
                "minimum_member_power": .1, "member_counts": [2]}}}


def forbidden(*args, **kwargs):
    raise AssertionError("mining fallback must not occur")


@pytest.fixture
def sample(monkeypatch):
    monkeypatch.setattr(legacy, "ExplicitSimulation", forbidden)
    return research.study(population(), 20, PunishmentSpec(counter_fork_k=2),
                          tprs=(.5, 1), fprs=(0, .1), prior=.3, bootstrap_samples=20)


def test_twenty_repetitions_use_unchanged_paired_statistics_and_detector_mixtures(sample):
    assert len(sample["repetitions"]) == 20 and len(sample["conditional_runs"]) == 120
    rows = sample["repetitions"]
    h = [r["U_H"]["target"]["payoff"] for r in rows]
    sc = [r["U_SC"]["target"]["payoff"] for r in rows]
    differences = [x-y for x, y in zip(h, sc)]
    stats = sample["summary"][0]["deterrence"]
    assert stats == legacy.paired_stats(differences, h, sc)
    assert stats["n"] == 20 and stats["mean"] == mean(differences)
    assert stats["sample_sd"] == stdev(differences)
    assert stats["standard_error"] == pytest.approx(stdev(differences) / 20**.5)
    assert stats["ci95_high"] == pytest.approx(stats["mean"] + 2.093*stats["standard_error"])
    assert sample["summary"][0]["effectiveness_status"] == legacy.status(stats, True)
    for member in sample["members"]:
        j = member["member_id"]
        full = [r["U_SC"][j]["payoff"] for r in rows]
        s0 = [r["U_S0"][j]["payoff"] for r in rows]
        leave = [r["leaveouts"][j][j]["payoff"] for r in rows]
        assert member["baseline"] == legacy.paired_stats([a-b for a, b in zip(full, s0)], full, s0)
        assert member["deviation"] == legacy.paired_stats([a-b for a, b in zip(full, leave)], full, leave)
    for detector in sample["detector"]:
        tpr, fpr = detector["tpr"], detector["fpr"]
        for actor in rows[0]["U_H"]:
            selfish = mean((1-tpr)*r["U_S0"][actor]["payoff"] + tpr*r["U_SC"][actor]["payoff"] for r in rows)
            honest = mean((1-fpr)*r["U_H"][actor]["payoff"] + fpr*r["U_HF"][actor]["payoff"] for r in rows)
            assert detector["expected_selfish"][actor] == selfish
            assert detector["prior_weighted"][actor] == pytest.approx(.3*selfish + .7*honest)


def test_raw_runs_preserve_seeds_population_and_branch_boundaries(sample):
    for row in sample["conditional_runs"]:
        r = row["result"]
        assert r["population"]["seed"] == population().seed + row["repetition"]
        assert r["population"]["candidates"] == population().candidates
        assert r["model_version"] == MODEL_VERSION and r["counter_fork_k"] == 2
        assert "terminal_omitted_selfish_share_bound" not in r
    assert sample["repetitions"][0]["terminal"]["U_SC"]["boundary"]["method"] == "complete-frontier-conservative-v1"
    assert sample["tpr_thresholds"][0]["bootstrap_requested_samples"] == 20


def test_analysis_fails_closed_on_missing_or_invalid_conditions(sample, monkeypatch):
    runs = unpack_conditions(sample["conditional_runs"])
    args = (population(), PunishmentSpec(counter_fork_k=2), 20, [("c1", "c2")], [.5], [0])
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    monkeypatch.setattr(legacy, "ExplicitSimulation", forbidden)
    result = research.analyze(*args, runs, bootstrap_samples=5)
    assert result["meta"]["mining_simulations_executed"] == 0
    runs.pop(next(iter(runs)))
    with pytest.raises(ValueError, match="coverage"):
        research.analyze(*args, runs)
    with pytest.raises(RuntimeError, match="cannot fall back"):
        "missing" in research.AnalysisCache()


def test_condition_cache_is_versioned_and_reusable_without_new_simulation(monkeypatch):
    cache, p, rule = {}, population(), PunishmentSpec()
    a = research.study(p, 2, rule, simulation_cache=cache, bootstrap_samples=0)
    assert a["meta"]["mining_simulations_executed"] == 12
    assert all(key[0] == MODEL_VERSION and key[1:3] == ("counter_fork", 1) for key in cache)
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    b = research.study(p, 2, rule, simulation_cache=cache, bootstrap_samples=0)
    assert b["meta"]["cache_hits"] == 12 and b["meta"]["mining_simulations_executed"] == 0
    assert a["repetitions"] == b["repetitions"]
    key = mining_cache_key(p, 0, "honest", False, (), rule)
    cache[key]["population"]["seed"] += 1
    with pytest.raises(ValueError, match="population/seed"):
        research.study(p, 2, rule, simulation_cache=cache)


@pytest.mark.parametrize("field,value", [("expected_model_version", legacy.MODEL_VERSION),
    ("punishment_rule", "ostracism"), ("punishment_rule", ["counter_fork", "ostracism"]),
    ("punishment_rules", ["counter_fork", "ostracism"]),
    ("counter_fork_k", 0), ("counter_fork_k", [1, 2, 3]), ("repetitions", 0),
    ("accepted_blocks", 3.2), ("authorized_environment_file", "unused-historical.csv")])
def test_runner_rejects_invalid_or_historical_designs(field, value):
    config = spec()
    config[field] = value
    with pytest.raises(ValueError):
        prepare(config)


def test_scope_defaults_and_rule_aware_task_group_identity():
    config = spec()
    plan = scope(config)
    assert plan["mining_simulations"] == 24 and plan["accepted_block_work_units"] == 288
    assert {x["mining_simulations"] for x in plan["per_lambda"].values()} == {12}
    assert not plan["historical_checkpoint_reuse"]
    del config["repetitions"]
    del config["accepted_blocks"]
    assert scope(config)["repetitions"] == 20 and scope(config)["accepted_block_target"] == 30000
    assert scope(config)["mining_simulations"] == 240
    one = prepare(spec(1))[1][0]
    two = prepare(spec(2))[1][0]
    assert one.task_id != two.task_id and one.configuration_id != two.configuration_id
    row = {"model_version": MODEL_VERSION, "punishment_rule": "counter_fork", "counter_fork_k": 1,
           "target_hash_power": .2, "gamma": .5, "natural_fork_rate": 0, "accepted_block_target": 12,
           "repetition_count": 2, "structure": "two_equal", "configuration_id": "a",
           "coalition": "c1|c2", "members": ["c1", "c2"], "active_hash_power": .2,
           "effectiveness_status": "SUPPORTED", "winning": True, "weak_jointly_feasible": True,
           "strictly_jointly_feasible": False}
    other = {**row, "counter_fork_k": 2, "active_hash_power": .3}
    assert analysis_group_key(row) != analysis_group_key(other)
    thresholds = grouped_thresholds([row, other])
    assert len(thresholds) == 8
    assert [r["hash_power"] for r in thresholds if r["threshold_kind"] == "effective"] == [.2, .3]


def test_local_runner_checkpoint_resume_analysis_only_and_csv_identity(tmp_path, monkeypatch):
    config = spec()
    a = run_sweep(config, tmp_path)
    assert a["metadata"]["mining_simulations_executed"] == 24
    for path in tmp_path.glob("*.csv"):
        with path.open() as f:
            rows = list(csv.DictReader(f))
        assert rows
        assert all(r["model_version"] == MODEL_VERSION and r["punishment_rule"] == "counter_fork"
                   and r["counter_fork_k"] == "2" for r in rows)
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    monkeypatch.setattr(legacy, "ExplicitSimulation", forbidden)
    b = run_sweep(config, tmp_path, analyze_only=True)
    c = run_sweep(config, tmp_path)
    assert b["metadata"]["resumed_tasks"] == 2
    assert b["metadata"]["mining_simulations_executed"] == c["metadata"]["mining_simulations_executed"] == 0
    for name in ("summary", "members", "detector", "repetitions", "thresholds", "tpr_thresholds"):
        assert a[name] == b[name] == c[name]
    with pytest.raises(ValueError, match="different persistent design"):
        run_sweep(spec(3), tmp_path)


def test_missing_analysis_only_checkpoint_never_mines_or_creates_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    with pytest.raises(ValueError, match="mining fallback is disabled"):
        run_sweep(spec(), tmp_path, analyze_only=True)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("mutation", ["schema", "model", "depth", "repetitions", "checksum", "coverage", "duplicate", "seed", "payoff", "frontier"])
def test_corrupt_or_mismatched_checkpoint_rejected_without_mining(tmp_path, monkeypatch, mutation):
    config = spec()
    run_sweep(config, tmp_path)
    checkpoint = next((tmp_path / "checkpoints").glob("*.json"))
    payload = json.loads(checkpoint.read_text())
    if mutation == "schema":
        payload["schema"] = "historical-v4"
    elif mutation in ("model", "depth", "repetitions"):
        field, value = {"model": ("model_version", legacy.MODEL_VERSION), "depth": ("counter_fork_k", 3),
                        "repetitions": ("repetitions", 30)}[mutation]
        payload["manifest"][field] = value
    elif mutation == "coverage":
        payload["conditional_runs"].pop()
    elif mutation == "duplicate":
        payload["conditional_runs"].append(copy.deepcopy(payload["conditional_runs"][0]))
    elif mutation == "seed":
        payload["conditional_runs"][0]["result"]["population"]["seed"] += 1
    elif mutation == "payoff":
        payload["conditional_runs"][0]["result"]["actors"]["target"]["payoff"] += .01
    elif mutation == "frontier":
        payload["conditional_runs"][0]["result"]["terminal"]["public_frontier"] = []
    if mutation != "checksum":
        payload.pop("content_sha256")
        payload["content_sha256"] = digest(payload)
    else:
        payload["content_sha256"] = "corrupt"
    checkpoint.write_text(json.dumps(payload))
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    with pytest.raises(ValueError):
        run_sweep(config, tmp_path)


def test_historical_output_directory_is_never_overwritten(tmp_path):
    historical = tmp_path / "old-results.json"
    historical.write_text("historical fixture")
    with pytest.raises(ValueError, match="nonempty output directory"):
        run_sweep(spec(), tmp_path)
    assert historical.read_text() == "historical fixture" and len(list(tmp_path.iterdir())) == 1


def test_incomplete_resource_run_has_failure_artifact_but_no_complete_checkpoint(tmp_path):
    with pytest.raises(research.IncompleteStudyError, match="INCOMPLETE_RESOURCE_LIMIT"):
        run_sweep(spec(), tmp_path, max_events=1)
    assert not (tmp_path / "checkpoints").exists()
    failure = json.loads(next((tmp_path / "failures").glob("*.json")).read_text())
    assert failure["result"]["status"] == "INCOMPLETE_RESOURCE_LIMIT"
    assert not (tmp_path / "persistent_results.json").exists()


def test_unsupported_run_is_reported_and_never_used_as_completed_study(monkeypatch):
    from punishment_sim.persistent import UnsupportedStateError
    def unsupported(self):
        raise UnsupportedStateError("scripted ambiguous target frontier")
    monkeypatch.setattr(PersistentSimulation, "step", unsupported)
    result = PersistentSimulation(population(), "selfish", True, ("c1",), PunishmentSpec()).run()
    assert result["status"] == "UNSUPPORTED_STATE" and "ambiguous" in result["error"]
    with pytest.raises(research.IncompleteStudyError, match="UNSUPPORTED_STATE"):
        research.study(population(), 2, PunishmentSpec())
