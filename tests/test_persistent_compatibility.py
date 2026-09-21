"""Pre-ostracism counter-fork fixtures and bounded target-height exploration."""
import hashlib
import itertools
import json
from pathlib import Path

import pytest

from punishment_sim.coalition import Population
from punishment_sim.persistent import PersistentSimulation, PunishmentSpec, configuration_id, mining_cache_key
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_sweep import run_sweep

GOLDEN = json.loads((Path(__file__).parent / "fixtures/persistent_counter_fork_v1_golden.json").read_text())


@pytest.mark.parametrize("case", GOLDEN["engine_cases"])
def test_counter_fork_v1_complete_trace_result_and_identity_unchanged(case):
    p = Population(.2, (("c1", .1), ("c2", .1)), .6, case["rate"], 40, 73)
    rule = PunishmentSpec(counter_fork_k=case["k"])
    result = PersistentSimulation(p, case["strategy"], True, ("c1", "c2"), rule, trace_mode=True).run()
    assert digest(result) == case["result_sha256"]
    assert configuration_id(p, rule) == case["configuration_id"]
    assert digest(mining_cache_key(p, 0, case["strategy"], True, ("c1", "c2"), rule)) == case["cache_key_sha256"]


def test_counter_fork_v1_checkpoint_and_all_export_bytes_unchanged(tmp_path):
    run_sweep(GOLDEN["runner_specification"], tmp_path)
    actual = {str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert actual == GOLDEN["runner_files_sha256"]


@pytest.mark.parametrize("k", [1, 2, 3])
@pytest.mark.parametrize("strategy", ["honest", "selfish"])
@pytest.mark.parametrize("rate,gamma", [(0, 0), (1, 1), (.5, .5)])
def test_normal_counter_fork_target_discoveries_have_strictly_increasing_heights(k, strategy, rate, gamma):
    # All length-five owner schedules in this small population, through step()
    # only. This is corroboration of the induction in the reachability audit,
    # not a claim that finite exploration proves unreachability.
    p = Population(.2, (("c1", .2),), gamma, rate, 10, 73)
    for owners in itertools.product(("target", "c1", "honest_residual"), repeat=5):
        sim = PersistentSimulation(p, strategy, True, ("c1",), PunishmentSpec(counter_fork_k=k))
        target_height = 0
        for owner in owners:
            bid = sim.step(owner)
            if owner == "target":
                assert sim.height(bid) > target_height, (owners, sim.report())
                target_height = sim.height(bid)
            for actor in sim.miners:
                tips = sim.eligible_tips(actor)
                assert sum(t is not None and sim.blocks[t].owner_id == "target" for t in tips) <= 1
