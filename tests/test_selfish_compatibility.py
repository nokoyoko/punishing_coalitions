"""Pre-change ignore outputs and single-actor equivalence; no old test edits."""
from dataclasses import asdict
import hashlib
import itertools
import json
from pathlib import Path

import pytest

from punishment_sim.coalition import Population
from punishment_sim.ostracism import OstracismSpec
from punishment_sim.persistent import PersistentSimulation, PunishmentSpec, configuration_id, mining_cache_key
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_sweep import run_sweep
from punishment_sim.selfish_counter import SelfishCounterSpec

GOLDEN = json.loads((Path(__file__).parent / "fixtures/persistent_ignore_v1_golden.json").read_text())
R = "honest_residual"


@pytest.mark.parametrize("case", GOLDEN["engine_cases"])
def test_ignore_complete_pre_selfish_trace_result_and_identity_unchanged(case):
    p = Population(.2, (("c1", .1), ("c2", .1)), .6, case["rate"], 40, 73)
    rule = OstracismSpec()
    result = PersistentSimulation(p, case["strategy"], case["flagged"], case["active"], rule, trace_mode=True).run()
    assert digest(result) == case["result_sha256"]
    assert configuration_id(p, rule) == case["configuration_id"]
    assert digest(mining_cache_key(p, 0, case["strategy"], case["flagged"], case["active"], rule)) == case["cache_key_sha256"]


def test_ignore_pre_selfish_checkpoint_and_export_bytes_unchanged(tmp_path):
    run_sweep(GOLDEN["runner_specification"], tmp_path)
    actual = {str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert actual == GOLDEN["runner_files_sha256"]


def align_streams(old, new):
    # Rule namespaces intentionally differ. Equivalence uses the same supplied
    # owner schedule and tie/propagation draws, not changed production seeding.
    new.tie_rng.setstate(old.tie_rng.getstate())
    new.natural_rng.setstate(old.natural_rng.getstate())


def assert_single_actor_equal(old, new, actor="target", swap=False):
    def rename(value):
        return {"target": "c1", "c1": "target"}.get(value, value) if swap else value
    expected = {bid: asdict(b) for bid, b in old.blocks.items()}
    for block in expected.values():
        block["owner_id"] = rename(block["owner_id"])
        if swap and block["publication_kind"]:
            block["publication_kind"] = block["publication_kind"].replace("target_", "member_")
    assert {bid: asdict(b) for bid, b in new.blocks.items()} == expected
    assert new.canonical_chain == old.canonical_chain
    assert new.public_tips == old.public_tips
    assert dict(new.rewards) == {rename(a): n for a, n in old.rewards.items()}
    assert new.policy.states[actor].private_chain == old.private
    assert set(new.policy.states[actor].abandoned_blocks) == old.abandoned_private
    assert new.events == old.events


@pytest.mark.parametrize("rule", [PunishmentSpec(), OstracismSpec()])
@pytest.mark.parametrize("gamma", [0, .5, 1])
def test_single_target_same_strategy_for_all_short_owner_schedules(rule, gamma):
    p = Population(.2, (("c1", .2),), gamma, 0, 10, 73)
    schedules = list(itertools.product(("target", "c1", R), repeat=5))
    schedules += [("target",)*12 + (R,)*14, ("target", R, "target", "c1", R)*8]
    for schedule in schedules:
        old = PersistentSimulation(p, "selfish", False, (), rule)
        new = PersistentSimulation(p, "selfish", False, (), SelfishCounterSpec())
        align_streams(old, new)
        for owner in schedule:
            old.step(owner)
            new.step(owner)
            assert_single_actor_equal(old, new)


def test_single_coalition_selfish_actor_matches_target_at_neutral_binary_gamma():
    p = Population(.2, (("c1", .2),), .5, 0, 10, 73)
    # There are only two published branches in these schedules: the selfish
    # miner and the residual. Both receive neutral 1/2 support after swapping.
    for schedule in itertools.product(("target", R), repeat=7):
        old = PersistentSimulation(p, "selfish", False, (), PunishmentSpec())
        new = PersistentSimulation(p, "honest", True, ("c1",), SelfishCounterSpec())
        align_streams(old, new)
        for owner in schedule:
            old.step(owner)
            new.step("c1" if owner == "target" else owner)
            assert_single_actor_equal(old, new, "c1", swap=True)


@pytest.mark.parametrize("rate", [0, .2, 1])
def test_all_honest_baseline_preserves_old_natural_forks(rate):
    p = Population(.2, (("c1", .2),), .7, rate, 10, 73)
    for schedule in itertools.product(("target", "c1", R), repeat=5):
        old = PersistentSimulation(p, "honest", False, (), PunishmentSpec())
        new = PersistentSimulation(p, "honest", False, (), SelfishCounterSpec())
        align_streams(old, new)
        for owner in schedule:
            old.step(owner)
            new.step(owner)
            assert old.blocks == new.blocks and old.natural_pairs == new.natural_pairs
            assert old.pending == new.pending and old.canonical_chain == new.canonical_chain


def test_private_lead_delay_extension_is_explicitly_new_model_behavior():
    p = Population(.2, (("c1", .2),), .5, 1, 10, 73)
    old = PersistentSimulation(p, "selfish", False, (), PunishmentSpec())
    new = PersistentSimulation(p, "selfish", False, (), SelfishCounterSpec())
    align_streams(old, new)
    for owner in ("target", "target", "target", R):
        old.step(owner)
        new.step(owner)
    assert old.private == new.policy.states["target"].private_chain == [2, 3]
    assert old.pending is None and new.policy.window["blocks"] == [4, 1]
    old.step("c1")
    new.step("c1")
    assert not old.natural_pairs and new.natural_pairs == {"c1--honest_residual": 1}
