"""Native matched-seed invariants and scripted common-network transitions."""
from collections import Counter
from dataclasses import replace
from unittest.mock import Mock

import pytest

from punishment_sim.coalition import Population
from punishment_sim.persistent_v2 import (PersistentSimulation, Rule, NETWORK_VERSION, BASELINE_VERSION,
                                         mining_cache_key, condition_identity)
from punishment_sim.persistent_v2_checkpoint import validate_run

RULES = (Rule("counter_fork", 1), Rule("ignore"), Rule("selfish"))
R = "honest_residual"


def population(rate=.02, seed=84, horizon=30):
    return Population(.2, (("c1", .1), ("c2", .1)), .5, rate, horizon, seed)


def engine(rule=RULES[0], strategy="selfish", flagged=False, active=(), rate=.02, horizon=30, seed=84, **kwargs):
    return PersistentSimulation(population(rate, seed, horizon), strategy, flagged, active, rule, **kwargs)


@pytest.mark.parametrize("strategy", ["honest", "selfish"])
@pytest.mark.parametrize("rate", [0, .005, .02, 1])
@pytest.mark.parametrize("seed,rep", [(84, 0), (701, 0), (12, 2)])
def test_native_h_s0_exact_invariance_including_all_rng_trace_and_terminal_fields(strategy, rate, seed, rep):
    sims = [engine(rule, strategy, rate=rate, seed=seed, repetition=rep, trace_mode=True) for rule in RULES]
    assert sims[0].rng_snapshot() == sims[1].rng_snapshot() == sims[2].rng_snapshot()
    results = [sim.run() for sim in sims]
    assert results[0] == results[1] == results[2]  # no normalization or RNG overrides
    assert results[0]["model_version"] == BASELINE_VERSION
    assert results[0]["network_version"] == NETWORK_VERSION
    for sim, result in zip(sims, results):
        validate_run(result, sim.base_population, sim.rule, rep, strategy, False, ())


@pytest.mark.parametrize("rate", [0, .005, .02])
def test_seed_84_native_five_discovery_regression(rate):
    sims = [engine(rule, rate=rate, trace_mode=True) for rule in RULES]
    for actor in ("target", "target", "target", R, "c1"):
        for sim in sims:
            sim.step(actor)
        assert sims[0].trace == sims[1].trace == sims[2].trace
    assert sims[0].report() == sims[1].report() == sims[2].report()
    for sim in sims:
        fourth = sim.public_events[3]
        assert fourth["publications"] == [4, 1] and fourth["lambda_eligible"]
        assert fourth["lambda_draw"] == 0.48230038689431753
        assert fourth["pending_window"] is None  # new common namespace, no old seed reinterpretation
        assert sim.canonical_chain == [1, 2, 3] and sim.natural_rng.count == 1


@pytest.mark.parametrize("rate", [.005, .02])
def test_seed_84_audit_natural_draw_replayed_under_all_three_corrected_paths(rate):
    sims = [engine(rule, rate=rate, trace_mode=True) for rule in RULES]
    for sim in sims:
        # Diagnostic replay of the audit's natural variate, separate from native
        # seed provenance. It reproduces the delayed case at the audited rates.
        sim.natural_rng.source.random = Mock(return_value=0.00027760641597729396)
    for actor in ("target", "target", "target", R, "c1"):
        for sim in sims:
            sim.step(actor)
    assert sims[0].report() == sims[1].report() == sims[2].report()
    for sim in sims:
        assert sim.public_events[3]["pending_window"]["blocks"] == [4, 1]
        assert sim.blocks[5].parent_id is None and sim.blocks[5].publication_kind == "natural_fork"
        assert sim.selfish.states["target"].private_chain == [2, 3]
        assert sim.tie_rng.count == 0 and sim.natural_rng.count == 1


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("lead", [1, 2, 3, 12])
def test_all_private_leads_allow_one_public_episode_regardless_of_suffix_exhaustion(rule, lead):
    sim = engine(rule, rate=1)
    for _ in range(lead):
        sim.step("target")
    assert sim.natural_rng.count == 0 and sim.window is None
    honest = sim.step(R)
    released = list(range(1, lead+1)) if lead <= 2 else [1]
    assert sim.window["blocks"] == [honest] + released
    assert sim.natural_rng.count == 1 and sim.events == lead+1
    assert sim.publication_log[-1]["blocks"] == released
    assert len({sim.blocks[b].release_batch for b in released}) == 1
    assert sim.selfish.states["target"].private_chain == ([] if lead <= 2 else list(range(2, lead+1)))
    next_block = sim.step("c1")
    assert sim.blocks[next_block].parent_id == (1 if lead == 2 else None)
    assert sim.blocks[next_block].publication_kind == "natural_fork"
    assert sim.window is None and sim.natural_rng.count == 1  # consumes, never redraws within the episode


@pytest.mark.parametrize("rule", RULES)
def test_window_before_private_discovery_then_after_release_and_atomic_consumption(rule):
    sim = engine(rule, rate=1)
    sim.step(R)
    assert sim.window["blocks"] == [1]
    sim.step("target")
    assert sim.window is None and sim.selfish.states["target"].private_chain == [2]
    sim.step("target")
    sim.step("target")
    sim.step("c1")
    assert sim.window["blocks"] == [5, 2] and sim.natural_rng.count == 2
    sim.step("c1")  # explicit owner knows block 5, unlike the oceanic residual
    assert sim.blocks[6].parent_id == 5
    assert sim.publication_log[-1]["blocks"] == [3, 4]
    assert sim.events == 6 and sim.window is None and sim.natural_rng.count == 2


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("strategy", ["honest", "selfish"])
def test_inactive_policy_never_instantiated_and_nonempty_unflagged_membership_is_inert(rule, strategy, monkeypatch):
    import punishment_sim.persistent_v2 as module
    forbidden = Mock(side_effect=AssertionError("disabled policy constructed"))
    monkeypatch.setattr(module.CounterForkPolicy, "__init__", forbidden)
    monkeypatch.setattr(module.OstracismPolicy, "__init__", forbidden)
    sim = engine(rule, strategy, active=("c1", "c2"))
    assert sim.punishment is None and not sim.enabled and not sim.active
    assert sim.run()["status"] == "COMPLETE"
    forbidden.assert_not_called()


def test_flagged_hf_sc_leaveouts_share_common_initial_and_discovery_streams():
    sims = []
    for rule in RULES:
        for strategy, flagged, C in (("honest", False, ()), ("selfish", False, ()),
                ("honest", True, ("c1", "c2")), ("selfish", True, ("c1", "c2")), ("selfish", True, ("c2",))):
            sims.append(engine(rule, strategy, flagged, C))
    assert all(s.rng_snapshot() == sims[0].rng_snapshot() for s in sims)
    for _ in range(30):
        for sim in sims:
            sim.step()
    assert all([b.owner_id for b in s.blocks.values()] == [b.owner_id for b in sims[0].blocks.values()] for s in sims)
    assert all(s.rng.getstate() == sims[0].rng.getstate() for s in sims)


@pytest.mark.parametrize("rule", RULES)
def test_flagged_policy_cannot_suppress_common_lambda_when_target_remains_private(rule):
    sim = engine(rule, flagged=True, active=("c1", "c2"), rate=1)
    for actor in ("target",)*3 + (R,):
        sim.step(actor)
    assert sim.window["blocks"] == [4, 1] and sim.natural_rng.count == 1
    assert sim.selfish.states["target"].private_chain == [2, 3]


@pytest.mark.parametrize("k", [1, 2, 3])
def test_counter_defended_depth_refresh_and_capitulation_are_preserved(k):
    sim = engine(Rule("counter_fork", k), "honest", True, ("c1", "c2"), rate=0)
    target = sim.discover("target")
    counter = sim.step("c1")
    assert sim.blocks[counter].parent_id is None and sim.punishment.episode.depth == 0
    defending = target
    for depth in range(1, k+1):
        defending = sim.discover(R, defending)
        if depth < k:
            assert sim.punishment.episode.depth == depth
    assert sim.punishment.history[-1]["outcome"] == "CAPITULATED"
    refresh = sim.discover("target", defending)
    assert sim.punishment.episode.trigger == refresh and sim.punishment.episode.depth == 0
    again = sim.discover("target", refresh)
    assert sim.punishment.episode.trigger == again and sim.punishment.episode.refresh_count == 1


def test_counter_success_and_atomic_last_target_refresh_preserved():
    sim = engine(RULES[0], "honest", True, ("c1",), rate=0)
    target = sim.step("target")
    counter = sim.step("c1")
    sim.discover("c2", counter)
    assert sim.punishment.history[-1]["outcome"] == "SUCCEEDED" and not sim.blocks[target].canonical
    atomic = engine(RULES[0], flagged=True, active=("c1",), rate=0)
    ids = [atomic.step("target") for _ in range(3)]
    atomic.publish(ids, "target_selfish_release")
    assert atomic.punishment.episode.trigger == ids[-1]
    assert atomic.punishment.episode.refresh_count == 2 and atomic.events == 3


def test_delayed_atomic_release_keeps_counter_fork_anchor_visible():
    sim = engine(RULES[0], flagged=True, active=("c1",), rate=1)
    for actor in ("target", "target", R):
        sim.step(actor)
    assert sim.window["blocks"] == [3, 1, 2] and sim.window["delayed_tips"] == [3, 2]
    assert sim.punishment.episode.anchor == 1 and sim.punishment.episode.trigger == 2
    counter = sim.step("c1")
    assert sim.blocks[counter].parent_id == 1 and sim.blocks[counter].publication_kind == "counter_fork"
    assert sim.punishment.episode.depth == 0  # coalition sibling is not defended advancement


def test_ostracism_rejected_roots_and_ancestry_never_capitulate():
    sim = engine(RULES[1], "honest", True, ("c1", "c2"), rate=0)
    first = sim.step("target")
    tip = first
    for _ in range(8):
        tip = sim.discover(R, tip)
    assert sim.choose_parent("c1") is None
    second = sim.discover("target", tip)
    assert sim.punishment.rejected_roots == {first, second}
    assert sim.punishment.minimal_rejected_roots == {first}
    member = sim.step("c1")
    assert sim.blocks[member].parent_id is None
    assert not any(e["outcome"] == "CAPITULATED" for e in sim.punishment.history)


def test_independent_selfish_members_and_no_extra_coalition_gamma():
    sim = engine(RULES[2], flagged=True, active=("c1", "c2"), rate=0)
    for actor in ("c2", "c1", "target"):
        sim.step(actor)
    assert {a: s.private_chain for a, s in sim.selfish.states.items()} == {"target": [3], "c1": [2], "c2": [1]}
    sim.step(R)
    assert sim.events == 4 and [b["blocks"] for b in sim.publication_log] == [[4], [3], [2], [1]]
    assert sim.branch_probabilities([1, 2, 3, 4]) == pytest.approx({1: 1/6, 2: 1/6, 3: .5, 4: 1/6})
    sim.step("c1")
    assert sim.rewards["c1"] == 2 and sim.rewards["c2"] == 0
    assert sum(sim.rewards.values()) == sim.public_height


@pytest.mark.parametrize("rule", RULES)
def test_boundary_keeps_private_work_and_pending_window_without_forced_settlement(rule):
    sim = engine(rule, rate=1, horizon=1)
    for actor in ("target",)*3 + (R,):
        sim.step(actor)
    before = sim.events
    result = sim.run()
    assert sim.events == before and result["terminal"]["target_private_chain"] == [2, 3]
    assert result["terminal"]["pending_publication_window"]["blocks"] == [4, 1]
    assert result["terminal"]["boundary"]["actor_payoff_bounds"] == {a: [0, 1] for a in sim.miners}


def test_shared_baseline_key_has_no_rule_but_retains_environment_seed_repetition_and_stop():
    p = population()
    keys = [mining_cache_key(p, 0, "selfish", False, (), r) for r in RULES]
    assert len(set(keys)) == 1
    for changed in (replace(p, gamma=.7), replace(p, natural_fork_rate=.005), replace(p, seed=85),
                    replace(p, target_accepted_blocks=31), replace(p, candidates=(("c1", .15), ("c2", .05)))):
        assert mining_cache_key(changed, 0, "selfish", False, (), RULES[0]) != keys[0]
    assert mining_cache_key(p, 1, "selfish", False, (), RULES[0]) != keys[0]
    assert mining_cache_key(p, 0, "honest", False, (), RULES[0]) != keys[0]
    assert len({mining_cache_key(p, 0, "selfish", True, ("c1",), r) for r in RULES}) == 3


@pytest.mark.parametrize("strategy", ["honest", "selfish"])
def test_inactive_counter_depth_and_empty_flagged_coalition_are_behaviorally_irrelevant(strategy):
    reference = engine(RULES[0], strategy, trace_mode=True).run()
    for rule in (*RULES, Rule("counter_fork", 9)):
        assert engine(rule, strategy, True, (), trace_mode=True).run() == reference
        assert engine(rule, strategy, False, ("c1", "c2"), trace_mode=True).run() == reference
