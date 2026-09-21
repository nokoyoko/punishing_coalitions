"""Short v2 studies, shared baseline provenance and strict native validation."""
import copy
import csv
import json
from statistics import stdev

import pytest

from punishment_sim import coalition as legacy
from punishment_sim import persistent_v2_study as research
from punishment_sim.coalition import Population
from punishment_sim.persistent import PersistentSimulation as HistoricalSimulation, PunishmentSpec
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import (Rule, PersistentSimulation, NETWORK_VERSION, BASELINE_VERSION,
                                         model_version, mining_cache_key)
from punishment_sim.persistent_v2_checkpoint import (ConditionStore, PublicReplay, BASELINE_SCHEMA,
                                                    CONDITIONAL_SCHEMA, validate_run)
from punishment_sim.persistent_v2_sweep import run_sweep, scope, prepare, grouped_thresholds

RULES = (Rule("counter_fork", 1), Rule("ignore"), Rule("selfish"))


def population():
    return Population(.2, (("c1", .1), ("c2", .1)), .5, .02, 12, 84)


def spec(rule=RULES[0]):
    return {"expected_model_version": model_version(rule), "expected_network_version": NETWORK_VERSION,
        "punishment_rule": rule.punishment_rule, "counter_fork_k": rule.counter_fork_k,
        "seed": 84, "accepted_blocks": 12, "repetitions": 2, "bootstrap_samples": 12, "tpr": [.5, 1], "fpr": [0, .1],
        "composition": {"target_hash": [.2], "candidate_power": [.2], "gamma": [.5], "natural_fork_rate": [.02],
            "systematic": {"power_step": .1, "minimum_member_power": .1, "member_counts": [2]}}}


def forbidden(*args, **kwargs):
    raise AssertionError("mining forbidden")


@pytest.fixture(scope="module")
def samples():
    cache = {}
    return [research.study(population(), 20, rule, simulation_cache=cache, tprs=(.5, 1), fprs=(0, .1),
                           prior=.3, bootstrap_samples=20) for rule in RULES]


def test_twenty_repetitions_exact_same_h_s0_and_paired_d_b_q_uncertainty(samples):
    assert [s["meta"]["mining_simulations_executed"] for s in samples] == [120, 80, 80]
    assert samples[0]["baseline_references"] == samples[1]["baseline_references"] == samples[2]["baseline_references"]
    for sample in samples:
        rows = sample["repetitions"]
        assert len(rows) == 20
        for key in ("U_H", "U_S0"):
            assert [r[key] for r in rows] == [r[key] for r in samples[0]["repetitions"]]
        h = [r["U_H"]["target"]["payoff"] for r in rows]
        sc = [r["U_SC"]["target"]["payoff"] for r in rows]
        d = legacy.paired_stats([a-b for a, b in zip(h, sc)], h, sc)
        assert sample["summary"][0]["deterrence"] == d
        assert d["sample_sd"] == stdev(a-b for a, b in zip(h, sc))
        assert d["ci95_high"] == pytest.approx(d["mean"]+2.093*d["standard_error"])
        for member in sample["members"]:
            actor = member["member_id"]
            full = [r["U_SC"][actor]["payoff"] for r in rows]
            for name, values in (("baseline", [r["U_S0"][actor]["payoff"] for r in rows]),
                                 ("deviation", [r["leaveouts"][actor][actor]["payoff"] for r in rows])):
                expected = legacy.paired_stats([a-b for a, b in zip(full, values)], full, values)
                assert member[name] == expected and member[name+"_status"] == legacy.status(expected)
        effective = sample["summary"][0]["effectiveness_status"] == "SUPPORTED"
        for kind, key in (("weak", "weak_jointly_feasible"), ("strict", "strictly_jointly_feasible")):
            assert sample["summary"][0][key] == (effective and all(
                m[name+"_refined"][kind+"_supported"] for m in sample["members"] for name in ("baseline", "deviation")))


def test_detector_is_downstream_and_leaveout_retains_population(samples):
    for sample in samples:
        for row in sample["conditional_runs"]:
            result = row["result"]
            assert result["network_version"] == NETWORK_VERSION
            assert result["identity"]["actual_seed"] == population().seed+row["repetition"]
            assert result["actors"]["c1"]["hash_power"] == result["actors"]["c2"]["hash_power"] == .1
            if row["active_coalition"] == ["c2"]:
                assert "c1" not in result["terminal"]["private_states"]
        for detector in sample["detector"]:
            rows = sample["repetitions"]
            for actor in rows[0]["U_H"]:
                h = sum((1-detector["fpr"])*r["U_H"][actor]["payoff"]
                    +detector["fpr"]*r["U_HF"][actor]["payoff"] for r in rows)/20
                s = sum((1-detector["tpr"])*r["U_S0"][actor]["payoff"]
                    +detector["tpr"]*r["U_SC"][actor]["payoff"] for r in rows)/20
                assert detector["expected_honest"][actor] == pytest.approx(h)
                assert detector["expected_selfish"][actor] == pytest.approx(s)
                assert detector["prior_weighted"][actor] == pytest.approx(.3*s+.7*h)


def test_shared_disk_baselines_immutable_and_resume_without_mining(tmp_path, monkeypatch):
    originals = []
    before = None
    for rule in RULES:
        result = research.study(population(), 2, rule, checkpoint_dir=tmp_path, bootstrap_samples=0)
        originals.append(result)
        files = {p.name: p.read_bytes() for p in (tmp_path / "baselines").glob("*.json")}
        assert len(files) == 4
        if before is not None:
            assert before == files and result["meta"]["mining_simulations_executed"] == 8
        before = files
    assert originals[0]["baseline_references"] == originals[1]["baseline_references"] == originals[2]["baseline_references"]
    for path in tmp_path.rglob("*.json"):
        payload = json.loads(path.read_text())
        baseline = path.parent.name == "baselines"
        assert payload["schema"] == (BASELINE_SCHEMA if baseline else CONDITIONAL_SCHEMA)
        if baseline:
            assert payload["identity"]["rule"] is None and payload["result"]["model_version"] == BASELINE_VERSION
    for method in ("step", "discover", "run"):
        monkeypatch.setattr(PersistentSimulation, method, forbidden)
    monkeypatch.setattr(legacy, "ExplicitSimulation", forbidden)
    for rule, original in zip(RULES, originals):
        resumed = research.study(population(), 2, rule, checkpoint_dir=tmp_path, analyze_only=True, bootstrap_samples=0)
        assert resumed["meta"]["mining_simulations_executed"] == 0
        for name in ("summary", "members", "detector", "repetitions", "tpr_thresholds", "baseline_references"):
            assert resumed[name] == original[name]


@pytest.fixture
def native_result():
    result = PersistentSimulation(population(), "selfish", True, ("c1", "c2"), RULES[2], trace_mode=True).run()
    assert result["selfish_reactions"]
    return result


@pytest.mark.parametrize("field", ["identity", "network", "model", "owner", "parent", "publication", "reward",
    "private", "frontier", "lambda_draw", "lambda_eligible", "pending", "choice", "rng", "trace", "reaction",
    "batch", "activation", "opportunities", "boundary", "scripted"])
def test_corruption_rejected_without_mutating_input(native_result, field):
    r = copy.deepcopy(native_result)
    records = r["terminal"]["canonical_blocks"] + r["terminal"]["frontier_blocks"]
    first = min(records, key=lambda b: b["id"])
    if field == "identity": r["identity"]["actual_seed"] += 1
    elif field == "network": r["network_version"] = "persistent-network-v1"
    elif field == "model": r["model_version"] = "persistent-selfish-counter-v1"
    elif field == "owner": first["owner_id"] = "c2" if first["owner_id"] != "c2" else "c1"
    elif field == "parent": first["parent_id"] = first["id"]
    elif field == "publication": next(b for b in records if b["publication_sequence"] is not None)["publication_sequence"] = 999
    elif field == "reward": r["actors"]["target"]["accepted"] += 1
    elif field == "private": r["terminal"]["private_states"]["c1"]["private_chain"].append(1)
    elif field == "frontier": r["terminal"]["public_frontier"].append(999)
    elif field == "lambda_draw": next(e for e in r["public_events"] if e["lambda_eligible"])["lambda_draw"] = .123456
    elif field == "lambda_eligible": r["public_events"][0]["lambda_eligible"] = not r["public_events"][0]["lambda_eligible"]
    elif field == "pending": r["public_events"][0]["pending_window"] = {"blocks": [1]}
    elif field == "choice": next(e for e in r["public_events"] if e["choice"] is not None)["choice"]["parent"] = 999
    elif field == "rng": r["rng"]["natural"]["draw_count"] += 1
    elif field == "trace": r["trace"][0]["rng"]["discoveries"]["draw_count"] += 1
    elif field == "reaction": r["selfish_reactions"][0]["decisions"][0]["blocks"] = []
    elif field == "batch": r["publication_batches"][0]["discovery_event"] += 1
    elif field == "activation": r["member_activations"]["c1"] += 1
    elif field == "opportunities": r["member_opportunities"]["c1"] += 1
    elif field == "boundary": r["terminal"]["boundary"]["actor_payoff_bounds"] = {"target": [.4, .6]}
    elif field == "scripted": r["scripted_discoveries"] = [1]
    before = digest(r)
    with pytest.raises(ValueError):
        validate_run(r, population(), RULES[2], 0, "selfish", True, ("c1", "c2"))
    assert digest(r) == before


@pytest.mark.parametrize("mutation", ["v1_schema", "digest", "identity", "baseline_payload", "network", "event"])
def test_recomputed_checksum_cannot_authorize_wrong_baseline(tmp_path, monkeypatch, mutation):
    store = ConditionStore(tmp_path)
    result = PersistentSimulation(population(), "honest", False, (), RULES[0]).run()
    store.save(result, population(), RULES[0], 0, "honest", False, ())
    path = store.path(result["identity"])
    payload = json.loads(path.read_text())
    if mutation == "v1_schema": payload["schema"] = "persistent-conditional-checkpoint-v1"
    elif mutation == "identity": payload["identity"]["population"]["gamma"] = .7
    elif mutation == "baseline_payload": payload["result"] = HistoricalSimulation(population(), "honest", False, (), PunishmentSpec()).run()
    elif mutation == "network": payload["result"]["network_version"] = "persistent-network-v1"
    elif mutation == "event": payload["result"]["public_events"][0]["lambda_draw"] = .0001
    payload.pop("content_sha256")
    payload["content_sha256"] = "bad" if mutation == "digest" else digest(payload)
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    with pytest.raises(ValueError):
        research.study(population(), 2, RULES[1], checkpoint_dir=tmp_path, bootstrap_samples=0)


def test_corrupt_memory_entry_never_becomes_a_cache_miss(monkeypatch):
    key = mining_cache_key(population(), 0, "honest", False, (), RULES[0])
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    with pytest.raises(ValueError):
        research.study(population(), 2, RULES[0], simulation_cache={key: None}, bootstrap_samples=0)


def test_omitting_a_mandatory_release_cannot_pass_an_empty_reaction_history():
    sim = PersistentSimulation(population(), "selfish", False, (), RULES[0])
    sim.step("target")
    sim.step("honest_residual")
    terminal = sim.terminal_state()
    records = {b["id"]: b for b in terminal["canonical_blocks"] + terminal["frontier_blocks"]}
    view = PublicReplay(population(), RULES[0], sim.identity, records)
    view.events = 2
    view.selfish.states["target"].private_chain = [1]
    # Supply the honest publication but omit the required target release and
    # all reaction frames. Validation must find the missing reaction itself.
    with pytest.raises(ValueError, match="missing mandatory selfish release"):
        view.apply_episode(sim.publication_log[:1])


def test_runner_shared_store_exports_grouping_and_analysis_only(tmp_path, monkeypatch):
    results = []
    for rule in RULES:
        directory = tmp_path / rule.punishment_rule
        results.append(run_sweep(spec(rule), directory, checkpoint_dir=tmp_path / "shared"))
        for path in directory.glob("*.csv"):
            with path.open() as source:
                rows = list(csv.DictReader(source))
            assert rows and all(r["network_version"] == NETWORK_VERSION and r["model_version"] == model_version(rule) for r in rows)
    assert [r["metadata"]["mining_simulations_executed"] for r in results] == [12, 8, 8]
    assert [r["condition_id"] for r in results[0]["baseline_references"]] == [r["condition_id"] for r in results[2]["baseline_references"]]
    groups = grouped_thresholds([row for r in results for row in r["summary"]])
    assert {row["model_version"] for row in groups} == {model_version(r) for r in RULES}
    monkeypatch.setattr(research, "PersistentSimulation", forbidden)
    for rule, original in zip(RULES, results):
        resumed = run_sweep(spec(rule), tmp_path / rule.punishment_rule, checkpoint_dir=tmp_path / "shared", analyze_only=True)
        assert resumed["metadata"]["mining_simulations_executed"] == 0
        for name in ("summary", "members", "detector", "repetitions", "thresholds", "baseline_references"):
            assert resumed[name] == original[name]


def test_scope_defaults_and_v1_design_rejection():
    config = spec()
    del config["repetitions"]
    del config["accepted_blocks"]
    plan = scope(config)
    assert plan["repetitions"] == 10 and plan["accepted_block_target"] == 30000
    assert plan["mining_simulations"] == 60 and not plan["historical_checkpoint_reuse"]
    for field, value in (("expected_network_version", "persistent-network-v1"),
        ("expected_model_version", "persistent-counter-fork-v1"), ("gamma_C", .5), ("punishment_rule", ["ignore", "selfish"])):
        with pytest.raises(ValueError): prepare({**spec(), field: value})


def test_missing_or_incomplete_conditions_never_enter_completed_analysis(tmp_path):
    with pytest.raises(ValueError, match="analysis-only"):
        research.study(population(), 2, RULES[0], checkpoint_dir=tmp_path, analyze_only=True)
    with pytest.raises(research.IncompleteStudyError):
        research.study(population(), 2, RULES[0], checkpoint_dir=tmp_path, max_events=1)
    assert not list(tmp_path.rglob("*.json"))
