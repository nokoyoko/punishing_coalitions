"""Focused audit reproductions; these tests never change engine semantics."""
import pytest

from analysis.audit_persistent_v2_readiness import (
    RULES, R, CountedRandom, compatibility, k_semantics, population, reuse_scope)
from punishment_sim.persistent_v2 import PersistentSimulation, Rule
from punishment_sim.persistent_v2_study import study


@pytest.mark.parametrize("case", k_semantics(), ids=lambda row: f"k{row['k']}")
def test_clarified_native_counter_fork_examples(case):
    k = case["k"]
    ordinary = case["ordinary_and_leaveout"]
    assert ordinary["counter_parent"] is None
    assert ordinary["tie_depth"] == ordinary["unrelated_depth"] == 0
    assert ordinary["defending_depths"] == list(range(1, k+1))
    assert ordinary["outcome"] == "CAPITULATED"
    assert ordinary["leaveout_first_extension_owner"] == "c2"
    refresh = case["target_refresh"]
    assert refresh["episode"]["trigger"] == refresh["target2"]
    assert refresh["episode"]["anchor"] == refresh["expected_anchor"]
    assert refresh["episode"]["depth"] == 0
    assert refresh["history"][-1]["outcome"] == "REFRESHED"
    assert refresh["history"][-1]["depth"] == k-1
    assert case["honest_counter_branch_assistance"]["outcome"] == "SUCCEEDED"
    assert case["honest_counter_branch_assistance"]["depth"] == 0
    assert case["defending_same_height_siblings"]["depth"] == 1


@pytest.mark.parametrize("case", k_semantics(), ids=lambda row: f"k{row['k']}")
def test_audit_reproduces_missing_active_owner_exclusion_without_changing_it(case):
    gap = case["active_member_on_defended_branch_diagnostic"]
    assert gap["native_reachable"] is False
    assert gap["actual_outcome"] == "CAPITULATED"
    assert gap["actual_depth"] == case["k"] != gap["intended_depth"]


@pytest.mark.parametrize("k", [2, 3])
def test_current_refresh_can_follow_a_new_target_on_the_counter_branch(k):
    sim = PersistentSimulation(population(rate=0), "honest", True, ("c1",), Rule("counter_fork", k))
    sim.tie_rng = CountedRandom(sim.tie_rng, constant=.75)
    for owner in ("target", R, "c1", "c1", "target"):
        sim.step(owner)
    assert not sim.descends(5, 1)
    assert sim.punishment.history[-1]["outcome"] == "REFRESHED"
    assert sim.punishment.episode.trigger == 5 and sim.punishment.episode.anchor == 4


@pytest.mark.parametrize("k", [2, 3])
def test_natural_defending_sibling_does_not_double_count_height(k):
    sim = PersistentSimulation(population(rate=1), "honest", True, ("c1",), Rule("counter_fork", k))
    sim.step("target")
    sim.step("target")  # owner sees its delayed tip; refresh consumes the window
    sim.step(R)  # advances defended branch once and opens another window
    assert sim.punishment.episode.depth == 1 and sim.window is not None
    natural = sim.step("c2")
    assert sim.blocks[natural].publication_kind == "natural_fork"
    assert sim.punishment.episode.depth == 1


@pytest.fixture(scope="module")
def compared():
    return compatibility()


@pytest.mark.parametrize("strategy", ["honest", "selfish"])
@pytest.mark.parametrize("rate", [0, .005, .02])
def test_native_petty_v4_and_v2_stream_and_discovery_divergence(compared, strategy, rate):
    row = next(r for r in compared["completed"] if r["strategy"] == strategy and r["lambda"] == rate
               and not r["aligned_diagnostic_streams"])
    first = row["first_divergence_by_field"]
    assert first["rng"] == 0 and first["discoveries"] == 2


def test_honest_zero_lambda_aligned_control_matches_all_observed_behavior(compared):
    row = next(r for r in compared["completed"] if r["strategy"] == "honest" and r["lambda"] == 0
               and r["aligned_diagnostic_streams"])
    assert all(v is None for v in row["first_divergence_by_field"].values())


@pytest.mark.parametrize("rate", [.005, .02])
def test_same_residual_label_has_different_pending_window_behavior(compared, rate):
    row = next(r for r in compared["scripted"] if r["strategy"] == "honest" and r["lambda"] == rate)
    assert row["first_divergence_by_field"]["canonical"] == 1
    assert row["first_divergence_by_field"]["ancestry"] == 2
    assert row["terminal"]["petty_v4"]["ancestry"][-1][1] == 1
    assert row["terminal"]["persistent_v2"]["ancestry"][-1][1] is None


@pytest.mark.parametrize("rate", [0, .005, .02])
def test_selfish_long_private_prefix_differs_even_with_all_randomness_matched(compared, rate):
    row = next(r for r in compared["scripted"] if r["strategy"] == "selfish" and r["lambda"] == rate)
    assert row["first_divergence_by_field"]["canonical"] == 4
    assert row["first_divergence_by_field"]["rng"] == 4
    assert row["first_divergence_by_field"]["ancestry"] == 5


def test_all_five_rule_k_choices_reuse_the_same_validated_baselines(tmp_path):
    results, files = [], None
    for rule in RULES:
        result = study(population(horizon=12), 2, rule, checkpoint_dir=tmp_path, bootstrap_samples=0)
        results.append(result)
        current = {p.name: p.read_bytes() for p in (tmp_path / "baselines").glob("*.json")}
        assert len(current) == 4
        if files is not None:
            assert current == files
        files = current
    assert [r["meta"]["mining_simulations_executed"] for r in results] == [12, 8, 8, 8, 8]
    assert all(r["baseline_references"] == results[0]["baseline_references"] for r in results)


def test_shared_baseline_scope_arithmetic_uses_existing_grid_without_mining():
    scope = reuse_scope()
    assert scope["configurations_per_variant"] == 250170
    assert scope["repetitions"] == 20
    three, five = scope["cases"]
    assert three["saved_runs"] == 20013600 and three["remaining_runs"] == 99789000
    assert five["saved_runs"] == 40027200 and five["remaining_runs"] == 159643800
