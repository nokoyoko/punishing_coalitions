"""Scripted discoveries and small unit runs only; no production configuration."""
from collections import Counter
from dataclasses import asdict
from unittest.mock import Mock

import pytest

from punishment_sim.coalition import Population
from punishment_sim.persistent import (
    MODEL_VERSION, PersistentSimulation, PunishmentSpec, UnsupportedStateError,
    configuration_id, mining_cache_key)

R = "honest_residual"


def engine(k=1, strategy="honest", flagged=True, active=("c1", "c2"),
           gamma=.5, rate=0, horizon=20, seed=12, max_events=None):
    pop = Population(.2, (("c1", .1), ("c2", .1), ("c3", .1)), gamma, rate, horizon, seed)
    return PersistentSimulation(pop, strategy, flagged, active, PunishmentSpec(counter_fork_k=k),
                                max_events=max_events, trace_mode=True)


@pytest.mark.parametrize("k", [0, -1, 1.5, True, "2"])
def test_invalid_depth(k):
    with pytest.raises(ValueError, match="positive integer"):
        PunishmentSpec(counter_fork_k=k)


@pytest.mark.parametrize("rule", ["petty", "ignore", "selfish", "petty+counter_fork"])
def test_unsupported_rule_or_combination(rule):
    with pytest.raises(ValueError, match="individual counter_fork"):
        PunishmentSpec(rule)


def test_private_discovery_then_publication_and_duplicate():
    sim = engine(strategy="selfish")
    t = sim.step("target")
    assert sim.blocks[t].publication_sequence is None and sim.policy.episode is None
    sim.publish([t], "target_selfish_release")
    assert sim.policy.episode.trigger == t and sim.policy.episode.anchor is None
    snapshot = asdict(sim.policy.episode)
    sim.publish([t])
    assert asdict(sim.policy.episode) == snapshot and sim.publication_sequence == 1


@pytest.mark.parametrize("flagged,active", [(False, ("c1",)), (True, ())])
def test_detector_miss_or_empty_coalition_never_triggers(flagged, active):
    sim = engine(strategy="selfish", flagged=flagged, active=active)
    t = sim.discover("target", withheld=True)
    sim.publish([t])
    assert sim.policy.episode is None and sim.policy.history == []


def test_honest_false_positive_and_irrelevant_target():
    sim = engine()
    t = sim.step("target")
    assert sim.policy.episode.trigger == t
    other = engine()
    h = other.discover(R)
    other.discover(R, h)
    stale = other.discover("target")
    assert stale in other.public and other.policy.episode is None


@pytest.mark.parametrize("k", [1, 2, 3])
def test_exact_defending_depth_capitulation_and_no_other_budget(k):
    sim = engine(k)
    t = sim.discover("target")
    c = sim.step("c1")
    assert sim.blocks[c].parent_id is None
    assert sim.policy.episode.depth == 0  # catching up is not success
    unrelated = sim.discover("c3")
    assert sim.policy.episode.depth == 0
    defender = t
    for depth in range(1, k+1):
        defender = sim.discover(R, defender)
        if depth < k:
            assert sim.policy.episode.depth == depth
            assert sim.choose_parent("c1") == c
    assert sim.policy.episode is None
    assert sim.policy.history[-1]["outcome"] == "CAPITULATED"
    assert sim.policy.history[-1]["depth"] == k
    assert {t, c, unrelated} <= sim.public  # no block deletion
    assert sim.choose_parent("c1") == defender


def test_sibling_on_defending_branch_does_not_double_count_height():
    sim = engine(3)
    t = sim.discover("target")
    sim.discover(R, t)
    sim.discover("c3", t)
    assert sim.policy.episode.depth == 1


@pytest.mark.parametrize("helper", ["c2", "c3", R])
def test_k_one_tie_then_overtake_success_with_individual_owners(helper):
    sim = engine(1)
    t = sim.discover("target")
    c = sim.step("c1")
    assert sim.reference_tip == t and sim.policy.episode.depth == 0
    end = sim.discover(helper, c)
    assert sim.policy.episode is None and sim.policy.history[-1]["outcome"] == "SUCCEEDED"
    assert sim.canonical_chain == [c, end] and not sim.blocks[t].canonical
    assert sim.rewards["target"] == 0 and sim.rewards["c1"] == 1
    assert sim.rewards[helper] == 1
    assert sum(sim.rewards.values()) == 2
    assert len(sim.blocks) == 3
    assert sim.reorganizations[-1]["removed"] == [t]


def test_success_on_boundary_precedes_timeout_in_atomic_publication():
    sim = engine(1)
    t = sim.discover("target")
    c = sim.discover("c1")
    h = sim.discover(R, t, withheld=True)
    c2 = sim.discover("c1", c, withheld=True)
    c3 = sim.discover("c1", c2, withheld=True)
    sim.publish([h, c2, c3], "scripted_atomic_batch")
    assert sim.policy.history[-1]["depth"] == 1
    assert sim.policy.history[-1]["outcome"] == "SUCCEEDED"


def test_refresh_accepts_old_target_ancestor_and_resets_depth():
    sim = engine(3)
    t = sim.discover("target")
    h = sim.discover(R, t)
    assert sim.policy.episode.depth == 1
    t2 = sim.discover("target", h)
    assert sim.policy.episode.trigger == t2 and sim.policy.episode.anchor == h
    assert sim.policy.episode.depth == 0 and sim.choose_parent("c1") == h
    t3 = sim.discover("target", t2)
    assert sim.policy.episode.anchor == t2 and sim.policy.episode.refresh_count == 2
    assert sim.policy.history[-1]["outcome"] == "REFRESHED"


def test_t1_t2_k_one_refresh_and_existing_alternative_reuse():
    sim = engine(1)
    t1 = sim.discover("target")
    t2 = sim.discover("target", t1)
    assert sim.policy.episode.trigger == t2 and sim.choose_parent("c1") == t1
    other = engine(2)
    c = other.discover("c1")
    other.discover("target")
    assert other.choose_parent("c2") == c


def test_atomic_target_release_last_relevant_block_and_no_extra_discoveries():
    sim = engine(1, strategy="selfish")
    t1 = sim.step("target")
    t2 = sim.step("target")
    t3 = sim.step("target")
    assert sim.policy.episode is None
    sim.publish([t1, t2, t3], "target_selfish_release")
    assert sim.events == 3
    assert [sim.blocks[t].publication_sequence for t in (t1, t2, t3)] == [1, 2, 3]
    assert {sim.blocks[t].release_batch for t in (t1, t2, t3)} == {1}
    assert sim.policy.episode.trigger == t3 and sim.policy.episode.anchor == t2
    assert sim.policy.episode.depth == 0 and sim.policy.next_episode == 4
    assert sim.policy.episode.refresh_count == 2
    assert [e["outcome"] for e in sim.policy.history] == ["REFRESHED", "REFRESHED"]
    assert sim.private == []


def test_invalid_publication_order_is_rejected_without_partial_publication():
    sim = engine()
    a = sim.discover("target", withheld=True)
    b = sim.discover("target", a, withheld=True)
    with pytest.raises(ValueError, match="parents before children"):
        sim.publish([b, a])
    assert not sim.public and sim.publication_sequence == 0


def test_multiway_neutral_probabilities_tip_gamma_only():
    sim = engine(flagged=False, gamma=.7)
    c = sim.discover("c1")
    h = sim.discover(R)
    t = sim.discover("target")
    assert sim.branch_probabilities([c, h]) == {c: .5, h: .5}
    assert sim.branch_probabilities([t, h]) == pytest.approx({t: .7, h: .3})
    assert sim.branch_probabilities([c, h, t]) == pytest.approx({c: .15, h: .15, t: .7})
    ht = sim.discover(R, t)
    hc = sim.discover("c2", c)
    assert sim.branch_probabilities([ht, hc]) == {ht: .5, hc: .5}
    neutral = engine(flagged=False)
    tips = [neutral.discover(a) for a in ("c1", "c2", R)]
    assert list(neutral.branch_probabilities(tips).values()) == [1/3]*3


def test_eligibility_before_ownership_and_residual_no_ownership_draw():
    sim = engine(3, gamma=1)
    t = sim.discover("target")
    owned_rejected = sim.discover("c1", t)  # scripted owner on defended chain
    sim.tie_rng = Mock(random=Mock(side_effect=AssertionError("unneeded tie draw")))
    assert sim.choose_parent("c1") is None  # cannot follow its rejected own tip
    assert owned_rejected not in sim.eligible_tips("c1")
    normal = engine(flagged=False)
    c = normal.discover("c1")
    r = normal.discover(R)
    normal.tie_rng = Mock(random=Mock(return_value=.1))
    assert normal.choose_parent("c1") == c
    normal.tie_rng.random.assert_not_called()
    assert normal.choose_parent(R) == c
    normal.tie_rng.random.assert_called_once()


def test_multiple_competing_target_tips_rejected_before_public_ledger_change():
    sim = engine(flagged=False)
    first = sim.discover("target")
    second = sim.discover("target", withheld=True)
    with pytest.raises(UnsupportedStateError, match="multiple simultaneous"):
        sim.publish([second])
    assert sim.public == {first} and sim.reference_tip == first


def test_natural_fork_during_retaliation_is_distinct_from_intentional_fork():
    sim = engine(3, rate=1)
    t = sim.step("target")
    assert sim.pending == t and sim.policy.episode.trigger == t
    h = sim.step(R)
    assert sim.blocks[h].parent_id is None and sim.blocks[h].publication_kind == "natural_fork"
    assert sim.natural_pairs == {"honest_residual--target": 1}
    c = sim.step("c1")
    assert sim.blocks[c].parent_id == h
    assert sim.blocks[c].publication_kind == "counter_fork"
    assert sum(sim.natural_pairs.values()) == 1


def test_leaveout_remains_neutral_and_states_are_independent():
    full = engine(active=("c1", "c2"), gamma=1)
    leave = engine(active=("c2",), gamma=1)
    for sim in (full, leave):
        sim.discover("target")
    assert full.p == leave.p
    assert full.choose_parent("c1") is None and leave.choose_parent("c1") == 1
    full.step("c1")
    leave.step("c1")
    assert full.policy.episode is not None
    assert leave.policy.episode is None  # neutral c1 advances defender at k=1
    assert full.blocks[2].owner_id == leave.blocks[2].owner_id == "c1"


def test_target_private_growth_and_public_retaliation_can_coexist():
    sim = engine(2, strategy="selfish")
    for _ in range(4):
        sim.step("target")
    sim.step(R)
    assert len(sim.private) == 3 and len(sim.longest_tips) == 2
    assert sim.policy.episode is not None
    # New independent target discovery extends its own hidden chain.
    tip = sim.private[-1]
    b = sim.step("target")
    assert sim.blocks[b].parent_id == tip and b not in sim.public


def test_horizon_30000_does_not_force_capitulation_or_resolution():
    sim = engine(2, horizon=30000)
    parent = None
    for _ in range(29998):
        parent = sim.discover(R, parent)
    t = sim.discover("target", parent)
    c = sim.discover("c1", parent)
    sim.discover(R, t)
    assert sim.public_height == 30000 and sim.policy.episode.depth == 1
    events = sim.events
    result = sim.run()
    assert result["status"] == "COMPLETE" and sim.events == events
    assert result["terminal"]["retaliation"]["trigger"] == t
    assert c in result["terminal"]["public_frontier"]
    assert result["terminal"]["boundary"]["potentially_material"]
    assert result["terminal"]["boundary"]["actor_payoff_bounds"]["target"] == [0, 1]


def test_horizon_does_not_publish_private_blocks_and_resource_limit_is_incomplete():
    sim = engine(horizon=1, strategy="selfish")
    t = sim.step("target")
    sim.discover(R)
    result = sim.run()
    assert t not in sim.public and t in result["terminal"]["private_frontier"]
    short = engine(horizon=30, max_events=1)
    assert short.run()["status"] == "INCOMPLETE_RESOURCE_LIMIT"


@pytest.mark.parametrize("k", [1, 2, 3])
@pytest.mark.parametrize("strategy", ["honest", "selfish"])
@pytest.mark.parametrize("rate", [0, .2])
def test_seeded_small_runs_reproduce_and_conserve_accounting(k, strategy, rate):
    first = engine(k, strategy=strategy, rate=rate, horizon=40).run()
    second = engine(k, strategy=strategy, rate=rate, horizon=40).run()
    assert first == second and first["status"] == "COMPLETE"
    assert first["model_version"] == MODEL_VERSION
    assert sum(a["accepted"] for a in first["actors"].values()) == first["accepted_blocks"]
    assert sum(a["payoff"] for a in first["actors"].values()) == pytest.approx(1)
    for a in first["actors"].values():
        assert a["discovered"] == a["accepted"] + a["public_noncanonical"] + a["unresolved"]
    assert sum(a["discovered"] for a in first["actors"].values()) == first["events"]


def test_rule_depth_and_model_namespace_change_identity():
    p = engine().p
    one, two = PunishmentSpec(counter_fork_k=1), PunishmentSpec(counter_fork_k=2)
    assert configuration_id(p, one) != configuration_id(p, two)
    assert mining_cache_key(p, 0, "selfish", True, ("c1",), one) != mining_cache_key(p, 0, "selfish", True, ("c1",), two)
    assert mining_cache_key(p, 0, "selfish", True, (), one) == mining_cache_key(p, 0, "selfish", False, (), one)


def test_generic_k_and_rearming_after_success_or_capitulation():
    assert PunishmentSpec(counter_fork_k=17).counter_fork_k == 17
    for outcome in ("SUCCEEDED", "CAPITULATED"):
        sim = engine(1)
        t = sim.step("target")
        c = sim.step("c1")
        sim.discover(R, c if outcome == "SUCCEEDED" else t)
        assert sim.policy.history[-1]["outcome"] == outcome and sim.policy.episode is None
        new = sim.discover("target", sim.reference_tip)
        assert sim.policy.armed and sim.policy.episode.trigger == new
        assert sim.policy.episode.depth == 0


def test_deep_fork_catchup_and_two_way_reorganization_conserve_individual_rewards():
    sim = engine(3)
    t = sim.discover("target")
    h1 = sim.discover(R, t)
    h2 = sim.discover(R, h1)
    counter = [sim.step("c1"), sim.step("c2"), sim.step("c1")]
    assert sim.height(counter[-1]) == 3 and sim.reference_tip == h2
    assert sim.policy.episode.depth == 2
    end = sim.step("c2")
    assert sim.canonical_chain == counter + [end]
    assert sim.rewards["c1"] == sim.rewards["c2"] == 2
    assert sim.rewards["target"] == sim.rewards[R] == 0
    h3 = sim.discover(R, h2)
    h4 = sim.discover(R, h3)
    assert sim.canonical_chain == [t, h1, h2, h3, h4]
    assert sim.rewards["target"] == 1 and sim.rewards[R] == 4
    assert sim.rewards["c1"] == sim.rewards["c2"] == 0
    assert sim.policy.episode is None  # old target returning is not a new publication
    report = sim.report()
    for actor in report["actors"].values():
        assert actor["discovered"] == actor["accepted"] + actor["public_noncanonical"] + actor["unresolved"]
    branch = report["terminal"]["alternative_branches"][0]
    assert branch["canonical_blocks_exposed"] == 5
    assert branch["canonical_rewards_exposed"] == {"target": 1, "c1": 0, "c2": 0, "c3": 0, R: 4}


def test_natural_first_publisher_privilege_is_explicit_not_residual():
    explicit = engine(flagged=False, rate=1)
    first = explicit.step("c1")
    second = explicit.step("c1")
    assert explicit.blocks[second].parent_id == first
    residual = engine(flagged=False, rate=1)
    first = residual.step(R)
    second = residual.step(R)
    assert residual.blocks[second].parent_id is None
    assert residual.natural_pairs == {"honest_residual--honest_residual": 1}


def test_atomic_reaction_may_overshoot_horizon_but_never_adds_a_discovery():
    sim = engine(3, strategy="selfish", horizon=1)
    first, second = sim.step("target"), sim.step("target")
    sim.step(R)  # ordinary target response releases both, in one batch
    assert sim.events == 3 and sim.public_height == 2
    before = sim.report()
    assert sim.run() == before
    assert sim.canonical_chain == [first, second]
    assert sim.policy.episode.trigger == second


def test_neutral_honest_helper_actually_selects_counter_branch_and_resolves_tie():
    sim = engine(1, gamma=0)
    t = sim.step("target")
    c = sim.step("c1")
    h = sim.step("c3")
    assert sim.blocks[h].parent_id == c and sim.blocks[t].canonical is False
    assert sim.policy.history[-1]["outcome"] == "SUCCEEDED"
