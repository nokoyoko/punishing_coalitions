"""Exact scientific equivalence, new policy semantics and production boundaries."""
import copy
import csv
from dataclasses import replace
import gzip
import itertools
import json
from pathlib import Path
import sqlite3
from unittest.mock import Mock

import pytest

from analysis import _persistent_v2_reference as before
from punishment_sim import persistent_v2_checkpoint as checkpoints
from punishment_sim import persistent_v2_study as research
from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import Rule, PersistentSimulation, mining_cache_key
from punishment_sim.persistent_v2_production import plan_tasks, iter_tasks
from punishment_sim.persistent_v2_sweep import prepare, run_sweep

RULES = (Rule("petty"), Rule("counter_fork", 1), Rule("counter_fork", 2), Rule("counter_fork", 3), Rule("ignore"), Rule("selfish"))
R = "honest_residual"


def population(n=2, gamma=.5, rate=.02, horizon=80, seed=701):
    return Population(.2, tuple((f"c{i+1}", .2/n) for i in range(n)), gamma, rate, horizon, seed)


def engine(rule=RULES[0], strategy="honest", flagged=True, active=("c1",), gamma=.5, rate=0):
    return PersistentSimulation(population(3, gamma, rate), strategy, flagged, active, rule, trace_mode=True)


@pytest.mark.parametrize("rule", RULES[1:])
@pytest.mark.parametrize("n,gamma,rate,seed", [(1, 0, 0, 84), (2, .5, .005, 701), (3, 1, .02, 702), (6, .5, 1, 999)])
@pytest.mark.parametrize("strategy,flagged", tuple(itertools.product(("honest", "selfish"), (False, True))))
def test_frozen_preoptimization_native_complete_trace_equality(rule, n, gamma, rate, seed, strategy, flagged):
    p = population(n, gamma, rate, seed=seed)
    active = tuple(a for a, _ in p.candidates) if flagged else ()
    old = before.PersistentSimulation(p, strategy, flagged, active,
        before.Rule(rule.punishment_rule, rule.counter_fork_k), trace_mode=True).run()
    new = PersistentSimulation(p, strategy, flagged, active, rule, trace_mode=True).run()
    assert new == old
    checkpoints.validate_run(new, p, rule, 0, strategy, flagged, active)


@pytest.mark.parametrize("k", [1, 2, 3])
def test_active_defending_blocks_and_later_honest_extension_never_count_skipped_heights(k):
    sim = engine(Rule("counter_fork", k))
    trigger = sim.step("target")
    tip = trigger
    for _ in range(5):
        tip = sim.discover("c1", tip)
        assert sim.punishment.episode.depth == 0
    for count in range(1, k+1):
        tip = sim.discover("c2" if count == 1 else R, tip)
        if count < k:
            assert sim.punishment.episode.depth == count
        else:
            assert sim.punishment.history[-1]["outcome"] == "CAPITULATED"
            assert sim.punishment.history[-1]["depth"] == k
    assert sim.punishment.history[-1]["defended_height"] == 6+k


def test_weighted_defending_siblings_do_not_add_across_paths():
    sim = engine(Rule("counter_fork", 3))
    t = sim.step("target")
    c = sim.discover("c1", t)
    a = sim.discover("c2", c)
    b = sim.discover(R, t)
    assert sim.punishment.episode.depth == 1
    sim.discover("c2", b)
    assert sim.punishment.episode.depth == 2
    sim.discover("c1", a)
    assert sim.punishment.episode.depth == 2


@pytest.mark.parametrize("k", [2, 3])
def test_cross_branch_competitive_target_supersedes_then_reanchors(k):
    sim = engine(Rule("counter_fork", k))
    sim.tie_rng.source.random = Mock(return_value=.75)
    for actor in ("target", R, "c1", "c1", "target"):
        sim.step(actor)
    assert not sim.descends(5, 1)
    assert sim.punishment.history[-1]["outcome"] == "REFRESHED"
    assert sim.punishment.episode.trigger == 5 and sim.punishment.episode.anchor == 4
    assert sim.punishment.episode.depth == 0
    stale = sim.discover("target")
    assert sim.punishment.episode.trigger != stale


@pytest.mark.parametrize("flagged,active,actor,expected", [
    (True, ("c1",), "c1", 2), (False, ("c1",), "c1", 1),
    (True, (), "c1", 1), (True, ("c1",), "c2", 1)])
def test_petty_false_positive_miss_empty_coalition_and_neutral_leaveout(flagged, active, actor, expected):
    sim = engine(flagged=flagged, active=active, gamma=1)
    sim.discover("target")
    sim.discover(R)
    assert sim.choose_parent(actor) == expected
    assert sim.blocks[sim.step(actor)].parent_id == expected


def test_petty_multiway_uniform_remaining_branches_and_explicit_ownership():
    sim = engine(active=("c1", "c2"), gamma=1)
    for owner in ("target", R, "c2", "c3"):
        sim.discover(owner)
    assert sim.eligible_tips("c1") == [2, 3, 4]
    assert sim.branch_probabilities(sim.eligible_tips("c1")) == pytest.approx({2: 1/3, 3: 1/3, 4: 1/3})
    sim.tie_rng.source.random = Mock(return_value=.8)
    assert sim.choose_parent("c1") == 4
    draws = sim.tie_rng.count
    assert sim.choose_parent("c2") == 3 and sim.tie_rng.count == draws
    assert sim.choose_parent("target") == 1


def test_petty_does_not_reject_target_ancestry_or_a_unique_longest_target_tip():
    sim = engine()
    t = sim.discover("target")
    honest = sim.discover(R, t)
    rival = sim.discover("c2")
    sim.discover("c3", rival)
    assert not sim.punishment.active and sim.eligible_tips("c1") == [honest, 4]
    sim.tie_rng.source.random = Mock(return_value=0)
    assert sim.choose_parent("c1") == honest
    target2 = sim.discover("target", honest)
    assert not sim.punishment.active and sim.choose_parent("c1") == target2


def test_delayed_visibility_can_disable_petty_for_the_actual_choice():
    sim = engine(rate=1)
    target = sim.step("target")
    sim.discover(R)  # fixture: public competition, preserve event-one window
    bid = sim.step("c1")
    assert sim.blocks[bid].parent_id == 2  # target tip is delayed; visible view has no target race
    assert sim.blocks[bid].publication_kind == "ordinary"


@pytest.mark.parametrize("rate", [0, .005, .02, 1])
@pytest.mark.parametrize("strategy", ["honest", "selfish"])
def test_six_variant_inactive_baseline_trace_and_initial_stream_equality(rate, strategy):
    p = population(rate=rate)
    sims = [PersistentSimulation(p, strategy, False, (), r, repetition=2, trace_mode=True) for r in RULES]
    assert all(s.rng_snapshot() == sims[0].rng_snapshot() for s in sims)
    results = [s.run() for s in sims]
    assert all(r == results[0] for r in results)
    assert len({mining_cache_key(p, 2, strategy, False, (), r) for r in RULES}) == 1


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("strategy", ["honest", "selfish"])
def test_production_omits_only_reconstructible_events_and_preserves_every_terminal_field(rule, strategy, tmp_path):
    p = population(horizon=100)
    debug = PersistentSimulation(p, strategy, True, ("c1", "c2"), rule).run()
    production = PersistentSimulation(p, strategy, True, ("c1", "c2"), rule, production=True).run()
    assert {k: v for k, v in production.items() if k != "recording_mode"} == {
        k: v for k, v in debug.items() if k != "public_events"}
    store = checkpoints.ConditionStore(tmp_path)
    store.save(production, p, rule, 0, strategy, True, ("c1", "c2"))
    path = store.path(production["identity"], True)
    payload = json.loads(gzip.decompress(path.read_bytes()))
    assert payload["schema"] == checkpoints.PRODUCTION_CONDITIONAL_SCHEMA
    assert digest(store.load(p, rule, 0, strategy, True, ("c1", "c2"))) == digest(production)
    assert checkpoints.encode_checkpoint(production) == path.read_bytes()


def test_production_boundary_rejects_tampering_even_with_recomputed_checksum(tmp_path):
    p, rule = population(), Rule("petty")
    result = PersistentSimulation(p, "selfish", True, ("c1",), rule, production=True).run()
    store = checkpoints.ConditionStore(tmp_path)
    store.save(result, p, rule, 0, "selfish", True, ("c1",))
    result["actors"]["target"]["accepted"] += 1
    store.path(result["identity"], True).write_bytes(checkpoints.encode_checkpoint(result))
    with pytest.raises(ValueError):
        store.load(p, rule, 0, "selfish", True, ("c1",))
    mixed = copy.deepcopy(result)
    mixed["public_events"] = []
    with pytest.raises(ValueError, match="mixed"):
        checkpoints.validate_run(mixed, p, rule, 0, "selfish", True, ("c1",))


def test_shared_six_variant_baselines_and_one_validation_per_condition(tmp_path, monkeypatch):
    p = population(horizon=12)
    originals, baseline_files = [], None
    validate = Mock(wraps=checkpoints.validate_run)
    monkeypatch.setattr(checkpoints, "validate_run", validate)
    for rule in RULES:
        validate.reset_mock()
        result = research.study(p, 2, rule, checkpoint_dir=tmp_path, production=True, bootstrap_samples=0)
        assert validate.call_count == 12
        originals.append(result)
        files = {p.name: p.read_bytes() for p in (tmp_path / "baselines").glob("*.json.gz")}
        assert len(files) == 4
        if baseline_files is not None:
            assert files == baseline_files
        baseline_files = files
    assert [r["meta"]["mining_simulations_executed"] for r in originals] == [12, 8, 8, 8, 8, 8]
    assert all(r["baseline_references"] == originals[0]["baseline_references"] for r in originals)
    monkeypatch.setattr(research, "PersistentSimulation", Mock(side_effect=AssertionError("mining forbidden")))
    for rule, original in zip(RULES, originals):
        validate.reset_mock()
        resumed = research.study(p, 2, rule, checkpoint_dir=tmp_path, production=True, bootstrap_samples=0, analyze_only=True)
        assert validate.call_count == 12
        for name in ("summary", "members", "detector", "repetitions", "baseline_references", "conditional_references"):
            assert resumed[name] == original[name]


def specification(rule=RULES[0]):
    from punishment_sim.persistent_v2 import NETWORK_VERSION, model_version
    return {"expected_network_version": NETWORK_VERSION, "expected_model_version": model_version(rule),
        "punishment_rule": rule.punishment_rule, "counter_fork_k": rule.counter_fork_k,
        "seed": 701, "accepted_blocks": 12, "repetitions": 2, "bootstrap_samples": 0, "tpr": [.9], "fpr": [.01],
        "aggregate": {"target_hash": [.2], "coalition_power": [.1, .2], "gamma": [.5], "natural_fork_rate": [0, .02]},
        "composition": {"target_hash": [.2], "candidate_power": [.1, .2], "gamma": [.5],
            "natural_fork_rate": [0, .02], "structures": ["singleton", "two_equal"]}}


@pytest.mark.parametrize("systematic", [False, True])
def test_disk_planner_is_identical_to_existing_deduplicated_task_plan(systematic):
    config = specification()
    if systematic:
        config["composition"].pop("structures")
        config["composition"]["systematic"] = {"member_counts": [2, 3], "power_step": .01,
            "minimum_member_power": .01, "sampling": {"mode": "hhi_quantiles", "max_per_cell": 3}}
        config["authorization_rule"] = "analytic_vanilla_eyal_sirer"
        config["aggregate"]["gamma"] = config["composition"]["gamma"] = [0, .5, 1]
    spec, tasks = prepare(config)
    with sqlite3.connect(":memory:") as connection:
        plan_tasks(connection, spec)
        assert list(iter_tasks(connection, tasks[0].rule)) == tasks


def test_production_runner_streams_complete_scientific_outputs_and_resumes(tmp_path, monkeypatch):
    # Explicit compatibility test for the prior full-ledger recording layout.
    from punishment_sim.persistent_v2_production import run_full_ledger_production
    config = specification()
    diagnostic = run_sweep(config, tmp_path / "debug")
    production = run_full_ledger_production(config, tmp_path / "prod")
    assert production["metadata"]["mining_simulations"] == diagnostic["metadata"]["mining_simulations"]
    assert "conditional_runs" not in production and "repetitions" not in production
    for name in ("summary", "members", "detector", "tpr_thresholds", "thresholds"):
        with (tmp_path / "prod" / production["csv_files"][name]).open() as source:
            actual = list(csv.DictReader(source))
        with (tmp_path / "debug" / production["csv_files"][name]).open() as source:
            expected = list(csv.DictReader(source))
        assert actual == expected
    with sqlite3.connect(tmp_path / "prod/persistent_v2_analysis.sqlite3") as connection:
        rows = [json.loads(x[0]) for x in connection.execute("SELECT body FROM outputs WHERE collection='repetitions'")]
    for row in rows:
        for terminal in row["terminal"].values():
            assert "canonical_blocks" not in terminal and terminal["terminal_location"] == "validated-condition-checkpoint"
            assert terminal["content_sha256"] and "actor_payoff_bounds" in terminal["boundary"]
    monkeypatch.setattr(research, "PersistentSimulation", Mock(side_effect=AssertionError("mining forbidden")))
    resumed = run_full_ledger_production(config, tmp_path / "prod", analyze_only=True)
    assert resumed["metadata"]["mining_simulations_executed"] == 0
    assert resumed["row_counts"] == production["row_counts"]
    with pytest.raises(ValueError, match="different"):
        run_full_ledger_production(config, tmp_path / "debug")


@pytest.mark.parametrize("version", ["race-owner-oceanic-all-races-v4", "persistent-counter-fork-v1",
                                    "persistent-ignore-v1", "persistent-selfish-counter-v1"])
def test_compressed_store_rejects_historical_models_even_with_fresh_checksum(version, tmp_path):
    p, rule = population(horizon=12), Rule("petty")
    result = PersistentSimulation(p, "honest", False, (), rule, production=True).run()
    result["model_version"] = version
    store = checkpoints.ConditionStore(tmp_path)
    path = store.path(result["identity"], True)
    path.parent.mkdir(parents=True)
    path.write_bytes(checkpoints.encode_checkpoint(result))
    with pytest.raises(ValueError, match="model mismatch"):
        store.load(p, rule, 0, "honest", False, ())


def test_same_condition_in_two_recording_formats_is_ambiguous(tmp_path):
    p, rule = population(horizon=12), Rule("petty")
    store = checkpoints.ConditionStore(tmp_path)
    for production in (False, True):
        result = PersistentSimulation(p, "honest", False, (), rule, production=production).run()
        path = store.path(result["identity"], production)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(checkpoints.encode_checkpoint(result))
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        store.load(p, rule, 0, "honest", False, ())


def test_benchmark_coverage_exact_scope_and_output_equality_evidence():
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads((root / "docs/persistent_v2_production_benchmark.json").read_text())
    rows = evidence["measurements"]
    long = [r for r in rows if r["horizon"] == 30000]
    assert {(r["rule"], r["k"], r["lambda"]) for r in long} == {
        (rule.punishment_rule, rule.counter_fork_k, rate) for rule in RULES for rate in (0, .02)}
    assert len(long) == 12
    assert all(r["reference_blocks"] == 30000 and r["retained_blocks"] == r["discovered_blocks"]
               and r["status"] == "COMPLETE" and r["raw_event_rows_retained"] == 0 for r in long)
    for rule in RULES:
        for rate in (0, .02):
            group = [r for r in rows if (r["rule"], r["k"], r["lambda"], r["horizon"]) ==
                     (rule.punishment_rule, rule.counter_fork_k, rate, 500)]
            assert len({r["scientific_sha256"] for r in group}) == 1
            assert len({r["result_sha256"] for r in group if r["mode"] != "production"}) == 1
    scope = evidence["six_variant_scope"]
    saved = 250170 * 20 * 2 * 5
    assert saved == scope["saved_runs"] == 50034000
    assert scope["independent_runs"] == 6 * 39934200 == 239605200
    assert scope["remaining_runs"] == 6 * 39934200 - saved == 189571200
    assert scope["nominal_accepted_block_work"] == scope["remaining_runs"] * 30000 == 5687136000000
