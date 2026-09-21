"""Scripted state transitions and tiny local runs, not production simulations."""
from unittest.mock import Mock

import pytest

from punishment_sim.coalition import Population
from punishment_sim.ostracism import MODEL_VERSION, OstracismPolicy, OstracismSpec
from punishment_sim.persistent import PersistentSimulation
from punishment_sim.persistent_checkpoint import validate_run

R = "honest_residual"


def engine(strategy="honest", flagged=True, active=("c1", "c2"), gamma=.5,
           rate=0, horizon=50, seed=12, max_events=None):
    population = Population(.2, (("c1", .1), ("c2", .1), ("c3", .1)), gamma, rate, horizon, seed)
    return PersistentSimulation(population, strategy, flagged, active, OstracismSpec(),
                                max_events=max_events, trace_mode=True)


def activate_after_history(sim):
    # Deliberate fixture attachment, not a new detector schedule for studies.
    sim.flagged = True
    sim.policy = OstracismPolicy(sim, True)


@pytest.mark.parametrize("k", [0, 1, 100, True, "3"])
def test_ignore_has_no_depth_parameter(k):
    with pytest.raises(ValueError, match="no counter_fork_k"):
        OstracismSpec(counter_fork_k=k)


@pytest.mark.parametrize("rule", ["counter_fork", "selfish", "ignore+counter_fork", ["ignore", "counter_fork"]])
def test_no_other_or_combined_rule(rule):
    with pytest.raises(ValueError, match="individual ignore"):
        OstracismSpec(punishment_rule=rule)


def test_pre_activation_history_grandfathered_private_discovery_does_not_activate():
    sim = engine(flagged=False)
    old = sim.step("target")
    hidden = sim.discover("target", old, withheld=True)
    activate_after_history(sim)
    assert sim.policy.activation_publication_sequence == 1
    assert sim.choose_parent("c1") == old and not sim.policy.rejected_roots
    sim.publish([hidden], "target_selfish_release")
    assert sim.policy.rejected_roots == {hidden}
    assert sim.choose_parent("c1") == old  # history is not rebuilt from genesis
    assert old not in sim.policy.rejected_by
    state, events = sim.policy.snapshot(), len(sim.policy.history)
    sim.publish([hidden])
    assert sim.policy.snapshot() == state and len(sim.policy.history) == events


def test_nonzero_activation_fixture_cannot_be_imported_as_standard_flagged_condition():
    sim = engine(flagged=False, horizon=1)
    sim.step("target")
    activate_after_history(sim)
    sim.step("target")
    with pytest.raises(ValueError, match="activation boundary"):
        validate_run(sim.run(), sim.p, sim.rule, 0, "honest", True, ("c1", "c2"))


@pytest.mark.parametrize("flagged,active", [(False, ("c1", "c2")), (True, ())])
def test_miss_or_empty_coalition_never_rejects(flagged, active):
    sim = engine("selfish", flagged=flagged, active=active)
    target = sim.step("target")
    assert target not in sim.public and not sim.policy.rejected_roots
    sim.publish([target])
    assert not sim.policy.armed and not sim.policy.rejected_roots
    assert sim.choose_parent("c1") == target


def test_honest_false_positive_rejects_first_publication_at_genesis_boundary():
    sim = engine()
    target = sim.step("target")
    assert sim.policy.activation_publication_sequence == 0
    assert sim.policy.rejected_roots == {target}
    assert sim.choose_parent("c1") is None and sim.choose_parent(R) == target


def test_stale_post_activation_target_publication_is_also_permanently_rejected():
    sim = engine()
    a = sim.discover(R)
    h = sim.discover(R, a)
    stale = sim.discover("target")
    assert sim.policy.rejected_roots == {stale}
    assert not sim.policy.active and sim.choose_parent("c1") == h
    desc = sim.discover("c3", stale)
    assert desc in sim.policy.rejected_by and desc not in sim.eligible_tips("c1")


def test_ancestry_rejection_survives_honest_tips_and_target_descendants_without_refresh():
    sim = engine()
    t1 = sim.step("target")
    h1 = sim.step(R)
    t2 = sim.step("target")
    h2 = sim.step(R)
    assert sim.policy.rejected_roots == {t1, t2}
    assert sim.policy.minimal_rejected_roots == {t1}
    assert all(sim.policy.rejected_by[b] == t1 for b in (t1, h1, t2, h2))
    assert sim.choose_parent("c1") is None
    assert sim.choose_parent("c3") == sim.choose_parent(R) == h2


def test_atomic_target_release_rejects_every_target_and_preserves_first_root():
    sim = engine("selfish")
    targets = [sim.step("target") for _ in range(3)]
    sim.tie_rng = Mock(random=Mock(side_effect=AssertionError("publication is not mining")))
    sim.publish(targets, "target_selfish_release")
    assert sim.events == 3 and sim.private == []
    assert sim.policy.rejected_roots == set(targets)
    assert sim.policy.minimal_rejected_roots == {targets[0]}
    assert sim.choose_parent("c1") is None
    assert {sim.blocks[b].release_batch for b in targets} == {1}
    root_events = [r for r in sim.policy.history if r["outcome"] == "REJECTED_TARGET_ROOT"]
    assert [r["root"] for r in root_events] == targets
    assert [r["first_rejected_ancestor"] for r in root_events] == [targets[0]]*3


@pytest.mark.parametrize("deficit", [1, 10, 100])
def test_no_capitulation_regardless_of_deficit(deficit):
    sim = engine(horizon=500)
    t = sim.step("target")
    c = sim.step("c1")
    for _ in range(deficit):
        sim.step(R)
    assert sim.public_height - sim.height(c) == deficit
    assert sim.choose_parent("c2") == c
    assert sim.policy.armed and sim.policy.active and sim.policy.rejected_roots == {t}
    assert not any(r["outcome"] in {"CAPITULATED", "REFRESHED"} for r in sim.policy.history)


def test_recovery_keeps_roots_and_rejects_later_target_on_acceptable_chain():
    sim = engine()
    t1 = sim.step("target")
    c1 = sim.step("c1")
    c2 = sim.step("c2")
    assert sim.canonical_chain == [c1, c2]
    assert not sim.policy.active and sim.policy.armed
    assert sim.policy.rejected_roots == {t1}
    t2 = sim.step("target")
    assert sim.policy.rejected_roots == sim.policy.minimal_rejected_roots == {t1, t2}
    assert sim.choose_parent("c1") == c2 and sim.policy.active
    assert not sim.blocks[t1].canonical


def test_multiple_roots_and_honest_descendants_on_different_branches():
    sim = engine(gamma=1)
    t1 = sim.discover("target")
    h1 = sim.discover("c1", t1)
    h2 = sim.discover("c3")
    t2 = sim.discover("target", h2)
    assert sim.policy.minimal_rejected_roots == {t1, t2}
    assert sim.policy.competing_rejected_roots == {t1, t2}
    assert sim.choose_parent("c1") == h2  # rejects its own h1, uses eligible interior prefix
    assert h1 not in sim.eligible_tips("c1") and t2 not in sim.eligible_tips("c1")
    assert sim.choose_parent(R) == t2
    h3 = sim.discover(R, t2)
    assert sim.policy.rejected_by[h3] == t2 and sim.choose_parent("c2") == h2


def test_eligible_explicit_owner_and_neutral_uniform_ties():
    sim = engine(active=("c1", "c3"), gamma=1)
    c1, c2 = sim.discover("c1"), sim.discover("c2")
    sim.tie_rng = Mock(random=Mock(return_value=.75))
    assert sim.choose_parent("c1") == c1
    sim.tie_rng.random.assert_not_called()
    assert sim.choose_parent("c3") == c2
    sim.tie_rng.random.assert_called_once()
    assert sim.branch_probabilities(sim.eligible_tips("c3")) == {c1: .5, c2: .5}


def test_gamma_and_residual_ownership_never_override_active_eligibility():
    sim = engine(gamma=1)
    residual = sim.discover(R)
    target = sim.discover("target")
    sim.tie_rng = Mock(random=Mock(return_value=.25))
    assert sim.choose_parent("c1") == residual
    sim.tie_rng.random.assert_not_called()
    assert sim.choose_parent(R) == target  # residual cannot keep its own tip by privilege
    sim.tie_rng.random.assert_called_once()
    assert sim.choose_parent("c3") == target


def test_grandfathered_eligible_target_tip_can_receive_gamma():
    sim = engine(flagged=False, gamma=1)
    t = sim.discover("target")
    sim.discover("c3")
    activate_after_history(sim)
    assert sim.choose_parent("c1") == t
    assert not sim.policy.rejected_roots


def test_leaveout_is_present_neutral_and_has_no_inherited_rejection_state():
    full = engine(active=("c1", "c2"))
    leave = engine(active=("c2",))
    for sim in (full, leave):
        sim.step("target")
    assert full.p == leave.p and full.miners["c1"] == leave.miners["c1"]
    assert full.choose_parent("c1") is None and leave.choose_parent("c1") == 1
    full.step("c1")
    leave.step("c1")
    assert full.blocks[2].parent_id is None and leave.blocks[2].parent_id == 1
    assert 2 not in full.policy.rejected_by and leave.policy.rejected_by[2] == 1
    full.step("target")
    assert full.policy.rejected_roots != leave.policy.rejected_roots


def test_natural_fork_between_acceptable_branches():
    sim = engine(rate=1)
    a = sim.step("c3")
    b = sim.step("c1")
    assert sim.blocks[b].parent_id is None and sim.pending is None
    assert sim.blocks[b].publication_kind == "natural_fork"
    assert sim.policy.eligible_frontier == {a, b} and not sim.policy.rejected_roots


def test_natural_acceptable_rejected_race_differs_from_intentional_ostracism():
    sim = engine(rate=1)
    t = sim.step("target")
    h = sim.step(R)
    assert sim.blocks[h].parent_id is None and sim.blocks[h].publication_kind == "natural_fork"
    c = sim.step("c1")
    assert sim.blocks[c].parent_id == h and sim.blocks[c].publication_kind == "ignore"
    assert sim.natural_pairs == {"honest_residual--target": 1}
    other = engine(rate=1)
    other.step("target")
    c = other.step("c1")
    assert other.blocks[c].publication_kind == "ignore" and not other.natural_pairs
    assert t in sim.policy.rejected_roots


def test_natural_fork_on_network_branch_while_coalition_is_far_behind():
    sim = engine(rate=1)
    parent = sim.discover("target")
    for _ in range(30):
        parent = sim.discover(R, parent)
    latest = sim.step(R)
    natural = sim.step("c3")
    assert sim.blocks[natural].parent_id == sim.blocks[latest].parent_id
    assert sim.blocks[natural].publication_kind == "natural_fork"
    assert sim.policy.rejected_by[natural] == 1
    assert sim.choose_parent("c1") is None and sim.policy.active
    assert sim.blocks[sim.step("c1")].publication_kind == "ignore"


def test_natural_acceptable_fork_after_recovery_does_not_forget_old_root():
    sim = engine(rate=1)
    t = sim.step("target")
    sim.step("c1")
    sim.step("c2")
    assert not sim.policy.active
    a = sim.step("c3")
    b = sim.step("c1")
    assert sim.blocks[b].parent_id == sim.blocks[a].parent_id
    assert sim.blocks[b].publication_kind == "natural_fork"
    assert t in sim.policy.rejected_roots and {a, b} <= sim.policy.eligible_frontier


def test_target_publishes_onto_one_of_multiple_acceptable_alternatives():
    sim = engine()
    a, b = sim.discover("c1"), sim.discover("c2")
    target = sim.step("target")
    assert sim.blocks[target].parent_id in (a, b)
    assert sim.policy.rejected_roots == {target}
    assert sim.eligible_tips("c1") == [a, b]
    assert sim.choose_parent("c1") == a and sim.choose_parent("c2") == b


def test_deep_two_way_reorganization_individual_rewards_and_reopened_conflict():
    sim = engine(horizon=100)
    rejected = sim.step("target")
    for _ in range(20):
        rejected = sim.step(R)
    for index in range(21):
        sim.step(("c1", "c2")[index % 2])
    assert sim.reference_tip == rejected and sim.policy.active  # tie, not recovery
    eligible = sim.step("c2")
    assert sim.reference_tip == eligible and not sim.policy.active
    assert sim.rewards["c1"] == sim.rewards["c2"] == 11
    assert sim.rewards["target"] == sim.rewards[R] == 0
    h1 = sim.discover(R, rejected)
    h2 = sim.discover(R, h1)
    assert sim.reference_tip == h2 and sim.policy.active
    assert sim.rewards["target"] == 1 and sim.rewards[R] == 22
    assert sim.rewards["c1"] == sim.rewards["c2"] == 0
    assert sim.choose_parent("c1") == eligible and sim.policy.rejected_roots == {1}
    for actor in sim.report()["actors"].values():
        assert actor["discovered"] == actor["accepted"] + actor["public_noncanonical"] + actor["unresolved"]
    assert sum(sim.rewards.values()) == len(set(sim.canonical_chain)) == sim.public_height


def test_height_30000_keeps_active_ostracism_and_deep_frontier_without_extra_event():
    # Scripted horizon fixture, not a stochastic production run.
    sim = engine(horizon=30000)
    target = sim.step("target")
    coalition = sim.step("c1")
    parent = target
    for _ in range(29999):
        parent = sim.discover(R, parent)
    before = sim.events
    result = sim.run()
    assert result["status"] == "COMPLETE" and result["accepted_blocks"] == 30000
    assert sim.events == before and sim.policy.active and sim.choose_parent("c2") == coalition
    terminal = result["terminal"]
    assert terminal["retaliation"]["rejected_roots"] == [target]
    assert terminal["retaliation"]["reference_height_minus_best_eligible_height"] == 29999
    assert terminal["ostracism_eligible_frontier"][0]["tip"] == coalition
    assert terminal["boundary"]["potentially_material"]
    assert terminal["boundary"]["max_exposed_canonical_blocks"] == 30000
    assert terminal["boundary"]["actor_payoff_bounds"]["c1"] == [0, 1]
    assert terminal["boundary"]["reference_rejected_by_active_coalition"]


def test_eligible_interior_prefix_exposure_recorded_even_without_competing_public_leaf():
    sim = engine()
    old = sim.step(R)
    target = sim.step("target")
    sim.step(R)
    terminal = sim.report()["terminal"]
    assert not terminal["alternative_branches"]
    assert terminal["ostracism_eligible_frontier"][0]["tip"] == old
    assert terminal["boundary"]["max_exposed_canonical_blocks"] == 2
    assert terminal["retaliation"]["rejected_roots"] == [target]


def test_private_frontier_is_not_forced_public_or_counted_as_new_root_at_horizon():
    sim = engine("selfish", horizon=2)
    t1 = sim.step("target")
    sim.step(R)
    t2 = sim.step("target")
    hidden = sim.step("target")
    result = sim.run()
    assert hidden not in sim.public and sim.private == [hidden]
    assert sim.policy.rejected_roots == {t1, t2}
    private = [b for b in result["terminal"]["alternative_branches"] if b["visibility"] == "private"]
    assert private[0]["first_rejected_public_ancestor"] == t1
    assert not private[0]["eligible_by_published_ancestry"]


def test_resource_guard_censors_without_changing_policy_or_rewards():
    sim = engine(horizon=100, max_events=2)
    t = sim.step("target")
    sim.step(R)
    before = dict(sim.rewards)
    result = sim.run()
    assert result["status"] == "INCOMPLETE_RESOURCE_LIMIT"
    assert sim.policy.active and sim.policy.rejected_roots == {t}
    assert dict(sim.rewards) == before and sim.choose_parent("c1") is None


def test_mining_eligibility_uses_ancestry_index_instead_of_depth_scan(monkeypatch):
    sim = engine()
    parent = sim.step("target")
    for _ in range(100):
        parent = sim.discover(R, parent)
    c = sim.step("c1")
    monkeypatch.setattr(sim, "descends", Mock(side_effect=AssertionError("per-choice ancestry scan")))
    assert sim.choose_parent("c2") == c
    assert len(sim.policy.rejected_by) == 101


@pytest.mark.parametrize("strategy", ["honest", "selfish"])
@pytest.mark.parametrize("rate", [0, .2, 1])
def test_seeded_tiny_runs_reproduce_and_conserve_discoveries(strategy, rate):
    sim = engine(strategy, rate=rate, horizon=40)
    a, b = sim.run(), engine(strategy, rate=rate, horizon=40).run()
    assert a == b and a["status"] == "COMPLETE"
    assert a["model_version"] == MODEL_VERSION and a["counter_fork_k"] is None
    assert sum(r["accepted"] for r in a["actors"].values()) == a["accepted_blocks"]
    assert sum(r["discovered"] for r in a["actors"].values()) == a["events"]
    for actor in a["actors"].values():
        assert actor["discovered"] == actor["accepted"] + actor["public_noncanonical"] + actor["unresolved"]
    validate_run(a, sim.p, sim.rule, 0, strategy, True, ("c1", "c2"))
