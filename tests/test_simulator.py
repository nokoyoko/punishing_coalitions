from dataclasses import replace
import math

import pytest

from punishment_sim.config import SimulationConfig
from punishment_sim.detection import NoisyOracle
from punishment_sim.experiments import combine_conditional, compare, sweep
from punishment_sim.model import Actor, Disposition, RaceOrigin
from punishment_sim.random_streams import stream
from punishment_sim.simulation import Simulation
from punishment_sim.smoke import run_smoke
from punishment_sim.theory import selfish_revenue


def cfg(**kw):
    return SimulationConfig(target_accepted_blocks=kw.pop("target_accepted_blocks", 20), **kw)


@pytest.mark.parametrize("key,value", [("target_hash_power", 0), ("target_hash_power", .5),
    ("coalition_hash", .8), ("gamma", 1.1), ("tpr", -.1), ("fpr", 2),
    ("natural_fork_rate", 1.1)])
def test_invalid_configuration(key, value):
    with pytest.raises(ValueError): cfg(**{key: value})


def test_shares_and_reproducibility():
    c = cfg(seed=91, target_accepted_blocks=200)
    assert math.isclose(c.target_hash_power + c.coalition_hash + c.honest_hash, 1)
    assert Simulation(c).run() == Simulation(c).run()


def test_accounting_and_chain_invariants():
    sim = Simulation(cfg(seed=8, target_accepted_blocks=1000))
    r = sim.run()
    assert sum(x["blocks_discovered"] for x in r["actors"].values()) == r["total_discovery_events"]
    assert sum(x["accepted_revenue"] for x in r["actors"].values()) == r["total_accepted_blocks"]
    assert math.isclose(sum(x["accepted_revenue_share"] for x in r["actors"].values()), 1)
    for block in sim.blocks.values():
        assert block.disposition in set(Disposition)
        if block.disposition == Disposition.ACCEPTED and block.parent_id is not None:
            assert sim.blocks[block.parent_id].disposition == Disposition.ACCEPTED


def test_honest_mode_tracks_hash_power():
    c = cfg(target_hash_power=.2, coalition_hash=.15, strategy="honest", target_accepted_blocks=30000)
    r = Simulation(c).run()
    assert abs(r["actors"]["target"]["accepted_revenue_share"] - .2) < .015
    assert r["total_orphaned_blocks"] == 0


def test_zero_coalition_and_disabled_detector_do_not_change_behavior():
    base = cfg(coalition_hash=0, seed=5, target_accepted_blocks=1000, punishment_enabled=True)
    a = Simulation(base).run()
    b = Simulation(replace(base, punishment_enabled=False, tpr=0, fpr=1)).run()
    assert a["actors"] == b["actors"]
    x = Simulation(replace(base, punishment_enabled=False, tpr=0, fpr=0)).run()
    y = Simulation(replace(base, punishment_enabled=False, tpr=1, fpr=1)).run()
    assert x["actors"] == y["actors"]


@pytest.mark.parametrize("tpr,fpr,truth,expected", [(1,0,True,True), (1,0,False,False),
    (0,0,True,False), (0,0,False,False), (1,1,True,True), (1,1,False,True)])
def test_detector_extremes(tpr, fpr, truth, expected):
    oracle = NoisyOracle(tpr, fpr, stream(1, "test"))
    assert oracle.classify(truth) is expected
    report = oracle.report(truth)
    assert report["epochs"] == 1
    assert report["flagged_count"] == int(expected)
    assert report["observed_flag_rate"] == int(expected)
    assert report["expected_flag_rate"] == (tpr if truth else fpr)


def test_lead_one_creates_and_resolves_race_with_forced_flag(tmp_path):
    c = cfg(target_hash_power=.25, coalition_hash=.25, gamma=1, forced_label=True,
            target_accepted_blocks=2, trace_path=str(tmp_path / "trace.jsonl"))
    sim = Simulation(c, [Actor.TARGET, Actor.HONEST, Actor.COALITION])
    r = sim.run()
    assert r["public_races"] == 1 and r["punishment_activations"] == 1
    assert r["actors"]["target"]["blocks_accepted"] == 0
    assert sim.trace[1]["race_began"] and sim.trace[2]["coalition_branch_choice"] == "non_target"


def test_forced_unflagged_label_uses_default_gamma(tmp_path):
    c = cfg(target_hash_power=.25, coalition_hash=.25, gamma=1, forced_label=False,
            target_accepted_blocks=2, trace_path=str(tmp_path / "trace.jsonl"))
    r = Simulation(c, ["target", "honest", "coalition"]).run()
    assert r["punishment_activations"] == 0
    assert r["actors"]["target"]["blocks_accepted"] == 1


def test_forced_flag_is_behaviorally_meaningful_in_synthetic_tie():
    c = cfg(target_hash_power=.25, coalition_hash=.25, gamma=1, forced_label=True,
            strategy="honest", target_accepted_blocks=2)
    sim = Simulation(c, ["coalition"])
    target, competing = sim.inject_public_race(origin=RaceOrigin.NATURAL_PROPAGATION)
    result = sim.run()
    assert result["classification"]["mode"] == "forced"
    assert result["classification"]["label"] == "flagged"
    assert "sampled_epoch" not in result
    assert sim.blocks[target].disposition == Disposition.ORPHANED
    assert sim.blocks[competing].disposition == Disposition.ACCEPTED


def test_natural_propagation_creates_opportunity_for_flagged_honest_miner():
    c = cfg(target_hash_power=.25, coalition_hash=.25, gamma=1, forced_label=True,
            natural_fork_rate=1, strategy="honest", target_accepted_blocks=2)
    sim = Simulation(c, ["honest", "target", "coalition"])
    result = sim.run()
    assert result["natural_propagation_windows"] == 1
    assert result["races_by_origin"] == {"natural_propagation": 1}
    assert result["classification"]["label"] == "flagged"
    assert result["punishment_activations_by_origin"] == {"natural_propagation": 1}
    assert result["actors"]["target"]["blocks_orphaned"] == 1
    assert result["total_discovery_events"] == 3


def test_natural_fork_can_begin_with_target_miner():
    c = cfg(target_hash_power=.25, coalition_hash=.25, gamma=1, forced_label=True,
            natural_fork_rate=1, strategy="honest", target_accepted_blocks=2)
    result = Simulation(c, ["target", "honest", "coalition"]).run()
    assert result["races_by_origin"] == {"natural_propagation": 1}
    assert result["classification"]["label"] == "flagged"
    assert result["actors"]["target"]["blocks_orphaned"] == 1


def test_selfish_type_allows_only_coalition_honest_natural_forks():
    c = cfg(strategy="selfish", natural_fork_rate=1, forced_label=True,
            target_accepted_blocks=2)
    sim = Simulation(c, ["coalition", "honest", "coalition"])
    result = sim.run()
    assert result["natural_races_by_actor_pair"] == {"coalition--honest": 1}
    assert result["target_involved_races"] == 0
    assert result["punishment_activations"] == 0


@pytest.mark.parametrize("first,second,pair", [
    ("target", "coalition", "coalition--target"),
    ("coalition", "target", "coalition--target"),
    ("target", "honest", "honest--target"),
    ("honest", "target", "honest--target"),
    ("coalition", "honest", "coalition--honest"),
    ("honest", "coalition", "coalition--honest"),
])
def test_distinct_honest_actor_classes_create_natural_forks(first, second, pair):
    c = cfg(strategy="honest", natural_fork_rate=1, forced_label=False,
            target_accepted_blocks=2)
    result = Simulation(c, [first, second, first]).run()
    assert result["natural_races_by_actor_pair"] == {pair: 1}
    assert result["total_discovery_events"] == 3


@pytest.mark.parametrize("actor", ["target", "coalition", "honest"])
def test_same_actor_does_not_create_cross_actor_fork(actor):
    c = cfg(strategy="honest", natural_fork_rate=1, forced_label=True,
            target_accepted_blocks=2)
    result = Simulation(c, [actor, actor]).run()
    assert result["public_races"] == 0


def test_target_label_does_not_affect_coalition_honest_race():
    base = cfg(strategy="selfish", natural_fork_rate=1, target_accepted_blocks=2)
    flagged = Simulation(replace(base, forced_label=True),
                         ["coalition", "honest", "coalition"]).run()
    unflagged = Simulation(replace(base, forced_label=False),
                           ["coalition", "honest", "coalition"]).run()
    assert flagged["actors"] == unflagged["actors"]
    assert flagged["punishment_activations"] == unflagged["punishment_activations"] == 0


def test_coalition_publishes_ordinary_discovery_immediately():
    sim = Simulation(cfg(strategy="selfish", natural_fork_rate=0,
                         target_accepted_blocks=1), ["coalition"])
    result = sim.run()
    block = sim.blocks[1]
    assert not block.initially_withheld
    assert block.publication_sequence is not None
    assert result["actors"]["coalition"]["blocks_accepted"] == 1


def test_selfish_target_closes_pending_window_without_benign_target_fork():
    sim = Simulation(cfg(strategy="selfish", natural_fork_rate=1,
                         target_accepted_blocks=2), ["coalition", "target"])
    sim.step()
    sim.step()
    assert sim.public_races == 0
    assert len(sim.private) == 1
    assert sim.blocks[sim.private[0]].initially_withheld
    assert sim.blocks[sim.private[0]].parent_id == 1


def test_target_label_is_sampled_once_and_reused_across_races():
    c = cfg(target_hash_power=.25, coalition_hash=.25, gamma=1, fpr=.5,
            natural_fork_rate=1, strategy="honest", target_accepted_blocks=4)
    sim = Simulation(c, ["target", "honest", "coalition"] * 2,
                     oracle_outcomes=[True])
    result = sim.run()
    assert result["public_races"] == 2
    assert result["sampled_epoch"]["epochs"] == 1
    assert result["sampled_epoch"]["flagged_count"] == 1
    assert result["punishment_activations"] == 2
    assert result["classification"]["label"] == "flagged"


@pytest.mark.parametrize("strategy,origin", [
    ("honest", RaceOrigin.SELFISH_RELEASE),
    ("selfish", RaceOrigin.NATURAL_PROPAGATION),
])
def test_race_origin_does_not_drive_miner_classification(strategy, origin):
    c = cfg(strategy=strategy, target_hash_power=.25, coalition_hash=.25,
            tpr=1, fpr=1, target_accepted_blocks=2)
    sim = Simulation(c, ["coalition"])
    sim.inject_public_race(origin=origin)
    result = sim.run()
    assert result["sampled_epoch"]["epochs"] == 1
    assert result["sampled_epoch"]["flagged_count"] == 1


def test_compare_uses_four_forced_label_conditions():
    result = compare(cfg(target_accepted_blocks=100, natural_fork_rate=.1))
    assert set(result["conditional_payoffs"]) == {
        "H_unflagged", "H_flagged", "S_unflagged", "S_flagged"}
    for run in result["conditional_runs"].values():
        assert run["classification"]["mode"] == "forced"
        assert "sampled_epoch" not in run


def test_conditional_payoffs_are_mixed_algebraically():
    p = {"H_unflagged": {"target": .2, "coalition": .1, "honest": .7},
         "H_flagged": {"target": .1, "coalition": .2, "honest": .7},
         "S_unflagged": {"target": .4, "coalition": .1, "honest": .5},
         "S_flagged": {"target": .3, "coalition": .2, "honest": .5}}
    mixed = combine_conditional(p, tpr=.75, fpr=.25)
    assert mixed["expected_honest_target_payoff"] == pytest.approx(.175)
    assert mixed["expected_selfish_target_payoff"] == pytest.approx(.325)


def test_tpr_fpr_sweep_reuses_four_mining_runs(monkeypatch):
    import punishment_sim.experiments as experiments
    calls = 0
    original = experiments.Simulation.run
    def counted(sim):
        nonlocal calls
        calls += 1
        return original(sim)
    monkeypatch.setattr(experiments.Simulation, "run", counted)
    rows = sweep({"base": {"target_accepted_blocks": 30, "seed": 4},
                  "grid": {"target_hash_power": [.25], "coalition_hash": [.1],
                           "gamma": [.5], "natural_fork_rate": [.1],
                           "tpr": [.5, 1], "fpr": [0, .1]},
                  "repetitions": 1})
    assert len(rows) == 4
    assert calls == 4


def test_smoke_report_is_deterministic(tmp_path):
    a = run_smoke(str(tmp_path / "a.json"), str(tmp_path / "a.jsonl"))
    b = run_smoke(str(tmp_path / "b.json"), str(tmp_path / "b.jsonl"))
    assert a == b
    assert a["status"] == "PASS"


def test_large_private_lead_and_publication_resolution(tmp_path):
    seq = ["target"] * 4 + ["honest"] * 4
    sim = Simulation(cfg(target_accepted_blocks=4, trace_path=str(tmp_path / "trace.jsonl")), seq)
    sim.run()
    assert max(row["private_lead"] for row in sim.trace) > 2
    assert sim.accepted_count == 4
    assert all(sim.blocks[x].owner == Actor.TARGET for x in range(1, 5))


def test_unpublished_private_not_rewarded():
    sim = Simulation(cfg(strategy="selfish", target_accepted_blocks=1), ["honest", "target"])
    result = sim.run()
    assert result["actors"]["target"]["blocks_accepted"] == 0


def test_hand_constructed_lead_two_override():
    sim = Simulation(cfg(target_accepted_blocks=2), ["target", "target", "honest"])
    r = sim.run()
    assert r["actors"]["target"]["blocks_accepted"] == 2
    assert r["actors"]["honest"]["blocks_orphaned"] == 1


@pytest.mark.statistical
@pytest.mark.parametrize("alpha,gamma", [(.15, 0), (.25, .5), (.35, 1)])
def test_selfish_revenue_matches_theory(alpha, gamma):
    values = []
    for seed in range(2):
        c = cfg(target_hash_power=alpha, coalition_hash=0, gamma=gamma, seed=seed,
                target_accepted_blocks=8000, punishment_enabled=False)
        values.append(Simulation(c).run()["actors"]["target"]["accepted_revenue_share"])
    assert abs(sum(values)/len(values) - selfish_revenue(alpha, gamma)) < .035
