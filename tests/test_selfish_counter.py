"""Independent Model-A selfish actors: scripted unit tests and tiny runs."""
from collections import Counter
import itertools
from unittest.mock import Mock

import pytest

from punishment_sim.coalition import Population
from punishment_sim.persistent import PersistentSimulation, UnsupportedStateError
from punishment_sim.persistent_checkpoint import validate_run
from punishment_sim.selfish_counter import SelfishCounterSpec

R = "honest_residual"


def engine(strategy="selfish", flagged=True, active=("c1", "c2"), gamma=.5,
           rate=0, horizon=40, seed=12, max_events=None, trace=True):
    p = Population(.2, (("c1", .1), ("c2", .1), ("c3", .1)), gamma, rate, horizon, seed)
    return PersistentSimulation(p, strategy, flagged, active, SelfishCounterSpec(),
                                max_events=max_events, trace_mode=trace)


def private(sim, actor):
    return sim.policy.states[actor].private_chain


def grow(sim, actor, n):
    return [sim.step(actor) for _ in range(n)]


def assert_accounting(sim):
    expected = Counter(sim.blocks[b].owner_id for b in sim.canonical_chain)
    assert sim.rewards == expected
    assert sum(sim.rewards.values()) == sim.public_height == len(sim.canonical_chain)
    assert all(sim.blocks[b].canonical == (b in sim.canonical_chain) for b in sim.blocks)
    assert all(not sim.blocks[b].canonical for s in sim.policy.states.values() for b in s.private_chain)


@pytest.mark.parametrize("rule,k", [("ignore", None), ("selfish+ignore", None), ("selfish", 1), ("selfish", 0)])
def test_only_individual_selfish_rule_without_depth(rule, k):
    with pytest.raises(ValueError):
        SelfishCounterSpec(rule, k)


def test_three_distinct_private_chains_from_first_discovery_no_shared_information():
    sim = engine()
    bids = {a: sim.step(a) for a in ("c2", "c1", "target")}
    assert not sim.public and not sim.rewards
    assert set(sim.policy.states) == set(bids)
    assert sim.activations == {"c1": 1, "c2": 1}
    assert sim.policy.snapshot()["activation_event"] == 0
    for actor, bid in bids.items():
        assert private(sim, actor) == [bid]
        assert sim.blocks[bid].owner_id == actor and sim.blocks[bid].parent_id is None
    with pytest.raises(ValueError, match="another actor's hidden"):
        sim.discover("c1", bids["c2"], withheld=True)
    with pytest.raises(ValueError, match="own current private tip"):
        sim.discover("c1", withheld=True)
    with pytest.raises(ValueError, match="honest/neutral"):
        sim.discover("c3", withheld=True)
    assert sim.events == 3


@pytest.mark.parametrize("strategy,flagged,active,actors", [
    ("selfish", False, ("c1", "c2"), {"target"}),
    ("selfish", True, ("c1", "c2"), {"target", "c1", "c2"}),
    ("honest", True, ("c1", "c2"), {"c1", "c2"}),
    ("selfish", True, ("c2",), {"target", "c2"}),
    ("honest", False, (), set()), ("selfish", True, (), {"target"})])
def test_detector_and_leaveout_state_is_fixed_from_start(strategy, flagged, active, actors):
    sim = engine(strategy, flagged, active)
    assert set(sim.policy.states) == actors
    bid = sim.step("c1")
    assert sim.blocks[bid].initially_withheld == ("c1" in actors)
    assert sim.miners["c1"].hash_power == .1
    assert sim.blocks[bid].owner_id == "c1"
    if "c1" not in actors:
        assert bid in sim.public and sim.choose_parent("c1") == bid


@pytest.mark.parametrize("actor", ["target", "c1", "c2"])
@pytest.mark.parametrize("lead", [1, 2, 3, 12])
def test_full_unbounded_strategy_leads_release_atomically_and_attribute_actual_owner(actor, lead):
    sim = engine()
    hidden = grow(sim, actor, lead)
    assert private(sim, actor) == hidden and sim.rewards[actor] == 0
    honest = sim.step(R)
    released = hidden if lead <= 2 else hidden[:1]
    assert private(sim, actor) == ([] if lead <= 2 else hidden[1:])
    assert sim.events == lead + 1 and len(sim.blocks) == lead + 1
    assert sim.publication_log[-1]["blocks"] == released
    assert sim.publication_log[-1]["discovery_event"] == lead + 1
    assert len({sim.blocks[b].release_batch for b in released}) == 1
    assert all(sim.blocks[b].owner_id == actor for b in hidden)
    if lead == 2:
        assert sim.canonical_chain == hidden and sim.rewards[actor] == 2
    else:
        assert sim.reference_tip == honest and len(sim.longest_tips) == 2
    assert_accounting(sim)


def test_three_simultaneous_releases_share_snapshot_and_population_order():
    sim = engine(gamma=.7)
    hidden = {a: sim.step(a) for a in ("c2", "c1", "target")}
    honest = sim.step(R)
    assert sim.events == 4 and sim.longest_tips == {*hidden.values(), honest}
    frame = sim.policy.history[0]
    assert frame["observed_publications"] == [honest] and frame["publication_sequence"] == 1
    assert [d["actor_id"] for d in frame["decisions"]] == ["target", "c1", "c2"]
    assert [batch["blocks"] for batch in sim.publication_log] == [[honest], [hidden["target"]], [hidden["c1"]], [hidden["c2"]]]
    assert sim.branch_probabilities(sorted(sim.longest_tips)) == pytest.approx(
        {hidden["target"]: .7, hidden["c1"]: .1, hidden["c2"]: .1, honest: .1})
    win = sim.step("c1")
    assert sim.blocks[win].parent_id == hidden["c1"]
    assert sim.rewards["c1"] == 2 and sim.rewards["c2"] == sim.rewards["target"] == 0
    assert_accounting(sim)


def test_release_cascades_in_finite_snapshot_rounds_without_discoveries_between():
    sim = engine()
    target, c1, c2 = grow(sim, "target", 5), grow(sim, "c1", 3), grow(sim, "c2", 2)
    honest = sim.step(R)
    rounds = sim.policy.history
    assert len(rounds) == 3 and {r["discovery_event"] for r in rounds} == {11}
    assert [d["blocks"] for d in rounds[0]["decisions"]] == [target[:1], c1[:1], c2]
    assert rounds[1]["observed_publications"] == target[:1] + c1[:1] + c2
    assert [d["blocks"] for d in rounds[1]["decisions"]] == [target[1:2], c1[1:]]
    assert [d["blocks"] for d in rounds[2]["decisions"]] == [target[2:3]]
    assert private(sim, "target") == target[3:] and not private(sim, "c1") and not private(sim, "c2")
    assert sim.events == len(sim.blocks) == 11 and honest in sim.public
    assert_accounting(sim)


def test_other_release_and_stale_siblings_do_not_blindly_reduce_private_lead():
    sim = engine()
    target, c1, c2 = grow(sim, "target", 4), grow(sim, "c1", 6), grow(sim, "c2", 5)
    sim.step(R)
    assert private(sim, "target") == target[1:] and private(sim, "c1") == c1[1:]
    assert private(sim, "c2") == c2[1:]
    before = sim.policy.state_snapshots()
    rounds = len(sim.policy.history)
    sim.discover("c3")  # equal-height unrelated sibling: no extra unpublished prefix to release
    after = sim.policy.state_snapshots()
    for actor in before:
        assert after[actor]["private_chain"] == before[actor]["private_chain"]
        assert after[actor]["lead_relative_to_public_height"] == before[actor]["lead_relative_to_public_height"]
    assert len(sim.policy.history) == rounds
    sim.step(R)
    before = {a: list(private(sim, a)) for a in sim.policy.states}
    sim.discover("c3")  # strictly stale public branch
    assert {a: private(sim, a) for a in sim.policy.states} == before


def test_abandonment_against_scripted_overtake_preserves_unrewarded_private_archive():
    sim = engine()
    abandoned = grow(sim, "target", 2)
    competitor = grow(sim, "c1", 5)
    # Deliberate external atomic publication probes gap<0, rather than claiming
    # this intervention is a normal standard-strategy release schedule.
    sim.publish(competitor, "scripted_overtake")
    assert private(sim, "target") == []
    assert sim.policy.states["target"].abandoned_blocks == abandoned
    assert sim.rewards["target"] == 0 and sim.rewards["c1"] == 5
    with pytest.raises(ValueError, match="start on public history"):
        sim.discover("target", abandoned[-1], withheld=True)
    assert_accounting(sim)


@pytest.mark.parametrize("owners,probabilities", [
    (("target", "c1"), (.7, .3)), (("c1", R), (.5, .5)),
    (("c1", "c2"), (.5, .5)), (("target", "c1", R), (.7, .15, .15)),
    (("c1", "c2", R), (1/3, 1/3, 1/3))])
def test_binary_and_multiway_propagation_uses_target_tip_only(owners, probabilities):
    sim = engine(gamma=.7)
    tips = [sim.discover(a) for a in owners]
    assert sim.branch_probabilities(tips) == pytest.approx(dict(zip(tips, probabilities)))
    for owner, tip in zip(owners, tips):
        if owner != R:
            sim.tie_rng = Mock(random=Mock(side_effect=AssertionError("owned tip needs no random draw")))
            assert sim.choose_parent(owner) == tip
    sim.tie_rng = Mock(random=Mock(return_value=0))
    assert sim.choose_parent(R) == tips[0]
    sim.tie_rng.random.assert_called_once()  # even when the residual owns a public tip


def test_target_ancestry_confers_no_propagation_advantage():
    sim = engine(gamma=1)
    target, c1 = sim.discover("target"), sim.discover("c1")
    tips = [sim.discover(R, target), sim.discover("c3", c1)]
    assert sim.branch_probabilities(tips) == {b: .5 for b in tips}


@pytest.mark.parametrize("actors", [("target",), ("c1",), ("c1", "c2"), ("target", "c1", "c2")])
def test_natural_fork_coexists_with_independent_retained_private_chains(actors):
    sim = engine(rate=1)
    hidden = {a: grow(sim, a, 3) for a in actors}
    assert sim.policy.window is None and sim.natural_pairs == {}
    ordinary = sim.step(R)
    bundle = sim.policy.window["blocks"]
    assert bundle == [ordinary] + [hidden[a][0] for a in sim.policy.states if a in hidden]
    assert all(b in sim.public for b in bundle)
    natural = sim.step("c3")
    assert sim.blocks[natural].parent_id is None and sim.blocks[natural].publication_kind == "natural_fork"
    assert sim.natural_pairs == {"c3--honest_residual": 1}
    assert len(sim.policy.natural_events) == 1
    assert all(private(sim, a) == hidden[a][1:] for a in actors)
    before = len(sim.policy.natural_events)
    for actor in actors:
        bid = sim.step(actor)
        assert sim.blocks[bid].parent_id == hidden[actor][-1] and bid not in sim.public
    assert len(sim.policy.natural_events) == before
    assert_accounting(sim)


def test_deep_reorganization_reverses_rewards_without_pooling():
    sim = engine(strategy="honest", active=("c1",))
    own = grow(sim, "c1", 12)
    sim.tie_rng = Mock(random=Mock(return_value=.99))  # follow residual competing tip
    for _ in range(11):
        sim.step(R)
        assert_accounting(sim)
    assert sim.canonical_chain == own
    assert sim.rewards["c1"] == 12 and sim.rewards[R] == sim.rewards["c2"] == 0
    assert len(sim.reorganizations[-1]["removed"]) == 11


def test_reference_30000_horizon_preserves_three_private_frontiers_without_finalization():
    # Deterministic linear ledger fixture, not a research run or benchmark.
    sim = engine(horizon=30000, trace=False)
    for _ in range(29999):
        sim.step(R)
    chains = {a: grow(sim, a, 3) for a in ("target", "c1", "c2")}
    sim.step(R)
    events = sim.events
    result = sim.run()
    assert result["status"] == "COMPLETE" and result["accepted_blocks"] == 30000
    assert sim.events == events and all(private(sim, a) == ids[1:] for a, ids in chains.items())
    terminal = result["terminal"]
    assert terminal["private_frontier"] == sorted(ids[-1] for ids in chains.values())
    assert terminal["boundary"]["private_leads"] == {a: 2 for a in chains}
    assert terminal["boundary"]["actor_payoff_bounds"] == {a: [0, 1] for a in sim.miners}
    assert terminal["boundary"]["potentially_material"]
    assert sim.rewards[R] == 30000 and all(sim.rewards[a] == 0 for a in chains)
    validate_run(result, sim.p, sim.rule, 0, sim.strategy, sim.flagged, tuple(sim.active))


@pytest.mark.parametrize("strategy", ["honest", "selfish"])
@pytest.mark.parametrize("rate", [0, .2, 1])
@pytest.mark.parametrize("seed", [12, 73, 701])
def test_short_complete_runs_repeat_exactly_and_validate_provenance(strategy, rate, seed):
    a, b = engine(strategy=strategy, rate=rate, seed=seed), engine(strategy=strategy, rate=rate, seed=seed)
    result = a.run()
    assert result == b.run() and result["status"] == "COMPLETE"
    validate_run(result, a.p, a.rule, 0, strategy, True, ("c1", "c2"))
    assert_accounting(a)


def test_resource_limit_preserves_private_blocks_and_reports_incomplete():
    sim = engine(max_events=1)
    sim.step("c1")
    result = sim.run()
    assert result["status"] == "INCOMPLETE_RESOURCE_LIMIT"
    assert result["terminal"]["selfish_states"]["c1"]["private_chain"] == [1]
    assert not sim.public and sim.events == 1


def test_multiple_current_target_tips_remain_explicitly_unsupported():
    sim = engine()
    sim.discover("target")
    with pytest.raises(UnsupportedStateError):
        sim.discover("target")


@pytest.mark.parametrize("strategy", ["honest", "selfish"])
@pytest.mark.parametrize("rate,gamma", [(0, 0), (1, 1), (.5, .5)])
def test_target_height_uniqueness_under_all_short_multi_actor_schedules(strategy, rate, gamma):
    # Finite corroboration of the documented height induction, not a proof by
    # exploration. Four actors permit three simultaneous private chains.
    for schedule in itertools.product(("target", "c1", "c2", R), repeat=5):
        sim = engine(strategy=strategy, rate=rate, gamma=gamma, trace=False)
        height = 0
        for actor in schedule:
            bid = sim.step(actor)
            if actor == "target":
                assert sim.height(bid) > height, schedule
                height = sim.height(bid)
            assert sum(sim.blocks[t].owner_id == "target" for t in sim.longest_tips) <= 1
