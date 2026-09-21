"""Small paired-analysis, identity and fail-closed checkpoint fixtures."""
import csv
import json
from statistics import mean, stdev

import pytest

from punishment_sim import coalition as legacy
from punishment_sim import persistent_study as research
from punishment_sim.coalition import Population
from punishment_sim.ostracism import OstracismSpec
from punishment_sim.persistent import PersistentSimulation, PunishmentSpec, configuration_id, mining_cache_key, model_version
from punishment_sim.persistent_checkpoint import SELFISH_SCHEMA, digest
from punishment_sim.persistent_sweep import analysis_group_key, grouped_thresholds, prepare, run_sweep, scope
from punishment_sim.selfish_counter import MODEL_VERSION, SelfishCounterSpec


def spec():
    return {"expected_model_version": MODEL_VERSION, "punishment_rule": "selfish", "seed": 701,
            "accepted_blocks": 12, "repetitions": 2, "bootstrap_samples": 12, "tpr": [.5, 1], "fpr": [0, .1],
            "composition": {"target_hash": [.2], "candidate_power": [.2], "gamma": [.5],
                "natural_fork_rate": [.2], "systematic": {"power_step": .1, "minimum_member_power": .1,
                "member_counts": [2]}}}


def population():
    return Population(.2, (("c1", .1), ("c2", .1)), .5, .2, 12, 701)


def forbidden(*args, **kwargs):
    raise AssertionError("mining fallback is forbidden")


@pytest.fixture(scope="module")
def sample():
    return research.study(population(), 20, SelfishCounterSpec(), tprs=(.5, 1), fprs=(0, .1),
                          prior=.3, bootstrap_samples=20)


def test_twenty_repetitions_keep_d_b_q_sample_uncertainty_and_classifications(sample):
    rows = sample["repetitions"]
    assert len(rows) == 20 and len(sample["conditional_runs"]) == 120
    h = [r["U_H"]["target"]["payoff"] for r in rows]
    sc = [r["U_SC"]["target"]["payoff"] for r in rows]
    deterrence = legacy.paired_stats([a-b for a, b in zip(h, sc)], h, sc)
    assert sample["summary"][0]["deterrence"] == deterrence
    assert deterrence["n"] == 20 and deterrence["mean"] == mean(a-b for a, b in zip(h, sc))
    assert deterrence["standard_error"] == pytest.approx(stdev(a-b for a, b in zip(h, sc)) / 20**.5)
    assert deterrence["ci95_high"] == pytest.approx(deterrence["mean"] + 2.093*deterrence["standard_error"])
    for member in sample["members"]:
        actor = member["member_id"]
        full = [r["U_SC"][actor]["payoff"] for r in rows]
        s0 = [r["U_S0"][actor]["payoff"] for r in rows]
        leave = [r["leaveouts"][actor][actor]["payoff"] for r in rows]
        for name, other in (("baseline", s0), ("deviation", leave)):
            expected = legacy.paired_stats([a-b for a, b in zip(full, other)], full, other)
            assert member[name] == expected and member[name + "_status"] == legacy.status(expected)
    effective = sample["summary"][0]["effectiveness_status"] == "SUPPORTED"
    for kind, key in (("weak", "weak_jointly_feasible"), ("strict", "strictly_jointly_feasible")):
        expected = effective and all(m[name + "_refined"][kind + "_supported"]
                                    for m in sample["members"] for name in ("baseline", "deviation"))
        assert sample["summary"][0][key] == expected


def test_detector_is_downstream_algebra_including_false_positive_and_prior_costs(sample):
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


def test_conditional_seeds_private_states_population_and_leaveout_are_independent(sample):
    rows = sample["conditional_runs"]
    for row in rows:
        result = row["result"]
        expected = ({"target"} if row["strategy"] == "selfish" else set())
        if row["flagged"]:
            expected.update(row["active_coalition"])
        states = result["terminal"]["selfish_states"]
        assert set(states) == expected
        assert result["population"]["seed"] == population().seed + row["repetition"]
        assert result["population"]["candidates"] == population().candidates
        assert result["actors"]["c1"]["hash_power"] == result["actors"]["c2"]["hash_power"] == .1
        assert result["member_activations"] == ({a: 1 for a in row["active_coalition"]} if row["flagged"] else {})
    full = next(r["result"] for r in rows if r["strategy"] == "selfish" and r["active_coalition"] == ["c1", "c2"])
    leave = next(r["result"] for r in rows if r["strategy"] == "selfish" and r["active_coalition"] == ["c2"])
    assert full["terminal"] is not leave["terminal"]
    assert full["terminal"]["selfish_states"]["c2"] is not leave["terminal"]["selfish_states"]["c2"]
    assert full["publication_batches"] != leave["publication_batches"]


def test_discovery_crn_is_shared_within_repetition_but_state_evolves_independently():
    p, rule = population(), SelfishCounterSpec()
    full = PersistentSimulation(p, "selfish", True, ("c1", "c2"), rule, trace_mode=True)
    leave = PersistentSimulation(p, "selfish", True, ("c2",), rule, trace_mode=True)
    for _ in range(20):
        full.step()
        leave.step()
    assert [b.owner_id for b in full.blocks.values()] == [b.owner_id for b in leave.blocks.values()]
    assert full.trace != leave.trace and "c1" not in leave.policy.states


def test_three_rules_separate_identities_rng_tasks_and_grouping_keep_counter_depth():
    rules = [PunishmentSpec(counter_fork_k=1), PunishmentSpec(counter_fork_k=3), OstracismSpec(), SelfishCounterSpec()]
    p = population()
    assert len({configuration_id(p, r) for r in rules}) == 4
    assert len({mining_cache_key(p, 0, "selfish", True, ("c1",), r) for r in rules}) == 4
    # k shares the counter-fork namespace intentionally; models never share it.
    models = [rules[0], *rules[2:]]
    assert len({repr(PersistentSimulation(p, "selfish", False, (), r).rng.getstate()) for r in models}) == 3
    tasks, rows = [], []
    for rule in rules:
        config = {**spec(), "expected_model_version": model_version(rule), "punishment_rule": rule.punishment_rule,
                  "counter_fork_k": rule.counter_fork_k}
        tasks.append(prepare(config)[1][0].task_id)
        rows.append({"model_version": model_version(rule), "punishment_rule": rule.punishment_rule,
            "counter_fork_k": rule.counter_fork_k, "target_hash_power": .2, "gamma": .5,
            "natural_fork_rate": .2, "accepted_block_target": 12, "repetition_count": 20, "structure": "two_equal",
            "members": ["c1", "c2"], "effectiveness_status": "INCONCLUSIVE", "winning": False,
            "weak_jointly_feasible": False, "strictly_jointly_feasible": False})
    assert len(set(tasks)) == len({analysis_group_key(r) for r in rows}) == 4
    thresholds = grouped_thresholds(rows)
    assert len(thresholds) == 16
    assert {(r["punishment_rule"], r["counter_fork_k"]) for r in thresholds} == {
        ("counter_fork", 1), ("counter_fork", 3), ("ignore", None), ("selfish", None)}


def test_scope_defaults_remain_twenty_and_30000_without_running_default_design():
    config = spec()
    del config["repetitions"]
    del config["accepted_blocks"]
    plan = scope(config)
    assert plan["repetitions"] == 20 and plan["accepted_block_target"] == 30000
    assert plan["mining_simulations"] == 120 and plan["accepted_block_work_units"] == 3600000
    assert not plan["historical_checkpoint_reuse"]


@pytest.mark.parametrize("field,value", [("expected_model_version", "persistent-ignore-v1"),
    ("expected_model_version", legacy.MODEL_VERSION), ("counter_fork_k", 1), ("counter_fork_k", 0),
    ("punishment_rule", ["selfish", "ignore"]), ("punishment_rules", ["selfish", "ignore"]),
    ("gamma_C", .5), ("gamma_c1", .5)])
def test_combinations_coalition_gamma_and_mismatched_models_are_rejected(field, value):
    config = spec()
    config[field] = value
    with pytest.raises(ValueError):
        prepare(config)


def test_checkpoint_csv_resume_and_analysis_only_with_no_mining(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy, "ExplicitSimulation", forbidden)
    first = run_sweep(spec(), tmp_path)
    assert first["metadata"]["mining_simulations_executed"] == 12
    checkpoint = json.loads(next((tmp_path / "checkpoints").glob("*.json")).read_text())
    assert checkpoint["schema"] == SELFISH_SCHEMA
    assert checkpoint["manifest"]["rng_namespace"] == MODEL_VERSION
    for file in tmp_path.glob("*.csv"):
        with file.open() as f:
            rows = list(csv.DictReader(f))
        assert rows and all(r["model_version"] == MODEL_VERSION and r["punishment_rule"] == "selfish"
                            and r["counter_fork_k"] == "" for r in rows)
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    resumed = run_sweep(spec(), tmp_path, analyze_only=True)
    assert resumed["metadata"]["mining_simulations_executed"] == 0
    assert before == {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}
    for name in ("summary", "members", "detector", "repetitions", "thresholds", "tpr_thresholds"):
        assert first[name] == resumed[name]


def test_cache_cannot_reuse_either_earlier_rule_or_mislabeled_payload(monkeypatch):
    cache = {}
    for rule in (PunishmentSpec(), OstracismSpec(), SelfishCounterSpec()):
        result = research.study(population(), 2, rule, simulation_cache=cache, bootstrap_samples=0)
        assert result["meta"]["mining_simulations_executed"] == 12
    assert len(cache) == 36
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    reused = research.study(population(), 2, SelfishCounterSpec(), simulation_cache=cache, bootstrap_samples=0)
    assert reused["meta"]["mining_simulations_executed"] == 0 and reused["repetitions"] == result["repetitions"]
    key = mining_cache_key(population(), 0, "honest", False, (), SelfishCounterSpec())
    cache[key]["model_version"] = "persistent-ignore-v1"
    with pytest.raises(ValueError, match="model/rule mismatch"):
        research.study(population(), 2, SelfishCounterSpec(), simulation_cache=cache, bootstrap_samples=0)


@pytest.mark.parametrize("mutation", ["schema", "model", "rule", "activation", "actors", "reaction_order",
    "propagation", "round", "decisions", "observed", "private", "exposure", "lead", "bounds", "queue", "coverage", "seed"])
def test_recomputed_checksum_does_not_allow_corrupt_provenance_or_state(tmp_path, monkeypatch, mutation):
    run_sweep(spec(), tmp_path)
    path = next((tmp_path / "checkpoints").glob("*.json"))
    payload = json.loads(path.read_text())
    row = next(r for r in payload["conditional_runs"] if r["flagged"] and r["strategy"] == "selfish"
               and r["active_coalition"] == ["c1", "c2"] and r["result"]["episodes"])
    result = row["result"]
    terminal = result["terminal"]
    if mutation == "schema":
        payload["schema"] = "persistent-ignore-conditional-checkpoint-v1"
    elif mutation == "model":
        result["model_version"] = "persistent-ignore-v1"
    elif mutation == "rule":
        result["punishment_rule"] = "ignore"
    elif mutation == "activation":
        terminal["retaliation"]["activation_event"] = 1
    elif mutation == "actors":
        terminal["selfish_states"].pop("c1")
    elif mutation == "reaction_order":
        result["reaction_order"] = "pooled-sequential"
    elif mutation == "propagation":
        result["propagation_convention"] = "private-delay"
    elif mutation == "round":
        result["episodes"].pop(0)
    elif mutation == "decisions":
        result["episodes"][0]["decisions"][0]["blocks"] = []
    elif mutation == "observed":
        result["episodes"][0]["observed_publications"] = []
    elif mutation == "private":
        terminal["selfish_states"]["c1"]["private_chain"].append(terminal["reference_tip"])
    elif mutation == "exposure":
        terminal["selfish_states"]["c1"]["exposure_is_leading"] = "unverified"
    elif mutation == "lead":
        terminal["boundary"]["private_leads"]["c1"] += 1
    elif mutation == "bounds":
        terminal["boundary"]["actor_payoff_bounds"] = {"target": [.4, .6]}
    elif mutation == "queue":
        terminal["reaction_queue"] = [1]
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


def test_resource_failure_never_becomes_a_completed_checkpoint(tmp_path):
    with pytest.raises(research.IncompleteStudyError, match="INCOMPLETE_RESOURCE_LIMIT"):
        run_sweep(spec(), tmp_path, max_events=1)
    assert not (tmp_path / "checkpoints").exists()
    result = json.loads(next((tmp_path / "failures").glob("*.json")).read_text())["result"]
    assert result["model_version"] == MODEL_VERSION and result["status"] == "INCOMPLETE_RESOURCE_LIMIT"
