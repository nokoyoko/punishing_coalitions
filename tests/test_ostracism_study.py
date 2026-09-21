"""Only short conditional and checkpoint fixtures for the ignore model."""
import copy
import csv
import json
from statistics import mean

import pytest

from punishment_sim import coalition as legacy
from punishment_sim import persistent_study as research
from punishment_sim.coalition import Population
from punishment_sim.ostracism import MODEL_VERSION, OstracismSpec
from punishment_sim.persistent import PunishmentSpec, configuration_id, mining_cache_key
from punishment_sim.persistent_checkpoint import IGNORE_SCHEMA, digest
from punishment_sim.persistent_sweep import analysis_group_key, prepare, run_sweep, scope


def spec():
    return {"expected_model_version": MODEL_VERSION, "punishment_rule": "ignore", "seed": 701,
            "accepted_blocks": 12, "repetitions": 2, "bootstrap_samples": 12, "tpr": [.5, 1], "fpr": [0, .1],
            "composition": {"target_hash": [.2], "candidate_power": [.2], "gamma": [.5],
                "natural_fork_rate": [.2], "systematic": {"power_step": .1, "minimum_member_power": .1,
                "member_counts": [2]}}}


def population():
    return Population(.2, (("c1", .1), ("c2", .1)), .5, .2, 12, 701)


def forbidden(*args, **kwargs):
    raise AssertionError("mining fallback is forbidden")


@pytest.fixture
def sample(monkeypatch):
    monkeypatch.setattr(legacy, "ExplicitSimulation", forbidden)
    return research.study(population(), 20, OstracismSpec(), tprs=(.5, 1), fprs=(0, .1),
                          prior=.3, bootstrap_samples=20)


def test_twenty_independent_repetitions_preserve_paired_statistics_and_large_losses(sample):
    assert len(sample["repetitions"]) == 20 and len(sample["conditional_runs"]) == 120
    rows = sample["repetitions"]
    h = [r["U_H"]["target"]["payoff"] for r in rows]
    sc = [r["U_SC"]["target"]["payoff"] for r in rows]
    deterrence = legacy.paired_stats([a-b for a, b in zip(h, sc)], h, sc)
    assert sample["summary"][0]["deterrence"] == deterrence
    assert deterrence["n"] == 20
    assert deterrence["ci95_high"] == pytest.approx(deterrence["mean"] + 2.093*deterrence["standard_error"])
    for member in sample["members"]:
        j = member["member_id"]
        full = [r["U_SC"][j]["payoff"] for r in rows]
        s0 = [r["U_S0"][j]["payoff"] for r in rows]
        leave = [r["leaveouts"][j][j]["payoff"] for r in rows]
        baseline = legacy.paired_stats([a-b for a, b in zip(full, s0)], full, s0)
        deviation = legacy.paired_stats([a-b for a, b in zip(full, leave)], full, leave)
        assert member["baseline"] == baseline and member["baseline_status"] == legacy.status(baseline)
        assert member["deviation"] == deviation and member["deviation_status"] == legacy.status(deviation)
    assert any(m["baseline"]["mean"] < 0 for m in sample["members"])  # costs are not clipped away
    effective = sample["summary"][0]["effectiveness_status"] == "SUPPORTED"
    for kind, key in (("weak", "weak_jointly_feasible"), ("strict", "strictly_jointly_feasible")):
        expected = effective and all(m[name + "_refined"][kind + "_supported"]
                                    for m in sample["members"] for name in ("baseline", "deviation"))
        assert sample["summary"][0][key] == expected


def test_detector_false_positive_costs_and_prior_mixture_are_unchanged_formulas(sample):
    rows = sample["repetitions"]
    for detector in sample["detector"]:
        for actor in rows[0]["U_H"]:
            tpr, fpr = detector["tpr"], detector["fpr"]
            selfish = mean((1-tpr)*r["U_S0"][actor]["payoff"] + tpr*r["U_SC"][actor]["payoff"] for r in rows)
            honest = mean((1-fpr)*r["U_H"][actor]["payoff"] + fpr*r["U_HF"][actor]["payoff"] for r in rows)
            cost = mean(r["U_H"][actor]["payoff"] - r["U_HF"][actor]["payoff"] for r in rows)
            assert detector["expected_selfish"][actor] == selfish
            assert detector["expected_honest"][actor] == honest
            assert detector["false_positive_conditional_cost"][actor] == cost
            assert detector["false_positive_expected_cost"][actor] == fpr*cost
            assert detector["prior_weighted"][actor] == pytest.approx(.3*selfish + .7*honest)


def test_conditional_seeds_actor_population_misses_false_positives_and_leaveouts(sample):
    for row in sample["conditional_runs"]:
        result = row["result"]
        state = result["terminal"]["retaliation"]
        assert result["population"]["seed"] == population().seed + row["repetition"]
        assert result["population"]["candidates"] == population().candidates
        assert result["model_version"] == MODEL_VERSION and result["punishment_rule"] == "ignore"
        assert set(result["actors"]) == {"target", "c1", "c2", "honest_residual"}
        if not row["flagged"]:
            assert not state["armed"] and state["rejected_roots"] == []
        else:
            assert state["activation_publication_sequence"] == 0 and state["armed"]
        if row["active_coalition"] == ["c2"]:
            assert result["actors"]["c1"]["hash_power"] == .1
        assert "terminal_omitted_selfish_share_bound" not in result
    honest_flagged = [r["result"] for r in sample["conditional_runs"] if r["flagged"] and r["strategy"] == "honest"]
    assert any(r["terminal"]["retaliation"]["rejected_roots"] for r in honest_flagged)
    assert sample["tpr_thresholds"][0]["bootstrap_requested_samples"] == 20


def test_rule_model_cache_task_and_group_identity_are_separate():
    p = population()
    assert configuration_id(p, OstracismSpec()) != configuration_id(p, PunishmentSpec())
    assert mining_cache_key(p, 0, "selfish", True, ("c1",), OstracismSpec()) != mining_cache_key(
        p, 0, "selfish", True, ("c1",), PunishmentSpec())
    config = spec()
    ignore_task = prepare(config)[1][0]
    counter = {**config, "expected_model_version": "persistent-counter-fork-v1",
               "punishment_rule": "counter_fork", "counter_fork_k": 1}
    assert ignore_task.task_id != prepare(counter)[1][0].task_id
    row = {"model_version": MODEL_VERSION, "punishment_rule": "ignore", "counter_fork_k": None,
           "target_hash_power": .2, "gamma": .5, "natural_fork_rate": .2, "accepted_block_target": 12,
           "repetition_count": 2, "structure": "two_equal"}
    other = {**row, "model_version": "persistent-counter-fork-v1", "punishment_rule": "counter_fork", "counter_fork_k": 1}
    assert analysis_group_key(row) != analysis_group_key(other)


def test_ignore_scope_defaults_remain_twenty_and_30000_without_a_production_grid():
    config = spec()
    del config["repetitions"]
    del config["accepted_blocks"]
    plan = scope(config)
    assert plan["repetitions"] == 20 and plan["accepted_block_target"] == 30000
    assert plan["mining_simulations"] == 120 and plan["accepted_block_work_units"] == 3600000
    assert plan["model_version"] == MODEL_VERSION and plan["counter_fork_k"] is None
    assert not plan["historical_checkpoint_reuse"]


@pytest.mark.parametrize("field,value", [("expected_model_version", "persistent-counter-fork-v1"),
    ("expected_model_version", legacy.MODEL_VERSION), ("counter_fork_k", 1), ("counter_fork_k", 0),
    ("punishment_rule", ["ignore", "counter_fork"]), ("punishment_rules", ["ignore", "selfish"]),
    ("punishment_rule", "selfish")])
def test_unsupported_design_cannot_run(field, value):
    config = spec()
    config[field] = value
    with pytest.raises(ValueError):
        prepare(config)


def test_ignore_checkpoint_and_csv_resume_analysis_only_without_mining(tmp_path, monkeypatch):
    first = run_sweep(spec(), tmp_path)
    assert first["metadata"]["mining_simulations_executed"] == 12
    checkpoint = json.loads(next((tmp_path / "checkpoints").glob("*.json")).read_text())
    assert checkpoint["schema"] == IGNORE_SCHEMA
    assert checkpoint["manifest"]["rng_namespace"] == MODEL_VERSION
    for file in tmp_path.glob("*.csv"):
        with file.open() as f:
            rows = list(csv.DictReader(f))
        assert rows and all(r["model_version"] == MODEL_VERSION and r["punishment_rule"] == "ignore"
                            and r["counter_fork_k"] == "" for r in rows)
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    monkeypatch.setattr(legacy, "ExplicitSimulation", forbidden)
    resumed = run_sweep(spec(), tmp_path, analyze_only=True)
    assert resumed["metadata"]["mining_simulations_executed"] == 0
    for name in ("summary", "members", "detector", "repetitions", "thresholds", "tpr_thresholds"):
        assert first[name] == resumed[name]


def test_cache_reuse_and_counter_fork_payload_rejection(monkeypatch):
    cache = {}
    a = research.study(population(), 2, OstracismSpec(), simulation_cache=cache, bootstrap_samples=0)
    assert a["meta"]["mining_simulations_executed"] == 12
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    b = research.study(population(), 2, OstracismSpec(), simulation_cache=cache, bootstrap_samples=0)
    assert b["meta"]["mining_simulations_executed"] == 0 and a["repetitions"] == b["repetitions"]
    first_key = next(iter(cache))
    cache[first_key]["model_version"] = "persistent-counter-fork-v1"
    with pytest.raises(ValueError, match="model/rule mismatch"):
        research.study(population(), 2, OstracismSpec(), simulation_cache=cache, bootstrap_samples=0)


@pytest.mark.parametrize("mutation", ["counter_schema", "model", "rule", "activation", "roots", "minimal_roots",
    "eligible", "conflict", "deficit", "exposure", "bounds", "capitulation", "coverage", "seed"])
def test_corrupt_provenance_or_policy_state_is_rejected_without_mining(tmp_path, monkeypatch, mutation):
    run_sweep(spec(), tmp_path)
    path = next((tmp_path / "checkpoints").glob("*.json"))
    payload = json.loads(path.read_text())
    row = next(r for r in payload["conditional_runs"] if r["flagged"] and r["result"]["terminal"]["retaliation"]["rejected_roots"])
    result, state = row["result"], row["result"]["terminal"]["retaliation"]
    if mutation == "counter_schema":
        payload["schema"] = "persistent-conditional-checkpoint-v1"
    elif mutation == "model":
        result["model_version"] = "persistent-counter-fork-v1"
    elif mutation == "rule":
        result["punishment_rule"] = "counter_fork"
    elif mutation == "activation":
        state["activation_publication_sequence"] = 1
    elif mutation == "roots":
        state["rejected_roots"].pop()
    elif mutation == "minimal_roots":
        state["minimal_rejected_roots"] = []
    elif mutation == "eligible":
        state["eligible_public_frontier"] = []
    elif mutation == "conflict":
        state["conflict_active"] = not state["conflict_active"]
    elif mutation == "deficit":
        result["terminal"]["boundary"]["best_eligible_height"] += 1
    elif mutation == "exposure":
        result["terminal"]["ostracism_eligible_frontier"][0]["canonical_blocks_exposed"] += 1
    elif mutation == "bounds":
        result["terminal"]["boundary"]["actor_payoff_bounds"] = {"target": [.4, .6]}
    elif mutation == "capitulation":
        result["episodes"].append({"outcome": "CAPITULATED"})
    elif mutation == "coverage":
        payload["conditional_runs"].pop()
    elif mutation == "seed":
        result["population"]["seed"] += 1
    payload.pop("content_sha256")
    payload["content_sha256"] = digest(payload)
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    with pytest.raises(ValueError):
        run_sweep(spec(), tmp_path)


def test_incomplete_ignore_run_produces_only_failure_not_completed_task(tmp_path):
    with pytest.raises(research.IncompleteStudyError, match="INCOMPLETE_RESOURCE_LIMIT"):
        run_sweep(spec(), tmp_path, max_events=1)
    assert not (tmp_path / "checkpoints").exists()
    result = json.loads(next((tmp_path / "failures").glob("*.json")).read_text())["result"]
    assert result["model_version"] == MODEL_VERSION and result["status"] == "INCOMPLETE_RESOURCE_LIMIT"
