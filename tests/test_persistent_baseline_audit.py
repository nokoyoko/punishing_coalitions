"""Audit current v1 baselines without changing simulator behavior.

Expected failures express the requested invariants that v1 DOES NOT satisfy.
Passing reproductions explain why; they are not approval of divergent baselines.
Only tiny completed runs and short scripted discovery sequences are used.
"""
import copy
from dataclasses import asdict
import hashlib
import itertools
import json
import random

import pytest

from punishment_sim.coalition import Population
from punishment_sim.ostracism import OstracismSpec
from punishment_sim.persistent import PersistentSimulation, PunishmentSpec, mining_cache_key
from punishment_sim.persistent_checkpoint import validate_run
from punishment_sim.selfish_counter import SelfishCounterSpec

R = "honest_residual"
RULES = (PunishmentSpec(), OstracismSpec(), SelfishCounterSpec())
RATES = (0, .005, .02)
STREAMS = ("rng", "tie_rng", "natural_rng")


class CountedRandom:
    def __init__(self, source):
        self.source = source
        self.draws = []

    def random(self):
        value = self.source.random()
        self.draws.append(value)
        return value

    def getstate(self):
        return self.source.getstate()

    def snapshot(self):
        return {"draw_count": len(self.draws),
                "state_sha256": hashlib.sha256(repr(self.getstate()).encode()).hexdigest()}


def private_chain(sim):
    if isinstance(sim.rule, SelfishCounterSpec):
        state = sim.policy.states.get("target")
        return list(state.private_chain) if state else []
    return list(sim.private)


def normalized_trace_event(sim):
    if not sim.trace:
        return None
    raw = sim.trace[-1]
    # Keep every common behavioral trace field, omit the differently shaped
    # policy/metadata envelopes. Complete ledger/frontier/window is below.
    return {"event": raw["event"], "discoverer": raw["discoverer"], "block": raw["block"],
            "reference_tip": raw["reference_tip"], "private": private_chain(sim),
            "rewards": {a: raw["rewards"].get(a, 0) for a in sim.miners}}


def snapshot(sim):
    published = sorted(sim.public, key=lambda b: sim.blocks[b].publication_sequence)
    if isinstance(sim.rule, SelfishCounterSpec):
        window = sim.policy.window
        delayed = list(window["blocks"]) if window else []
        abandoned = sorted(b for s in sim.policy.states.values() for b in s.abandoned_blocks)
    else:
        delayed = [sim.pending] if sim.pending is not None else []
        abandoned = sorted(sim.abandoned_private)
    return {"event": sim.events,
        "discovery_sequence": [(b.id, b.owner_id, b.parent_id, b.height, b.initially_withheld)
                               for b in sim.blocks.values()],
        "publication_sequence": [{k: v for k, v in asdict(sim.blocks[b]).items() if k != "canonical"}
                                 for b in published],
        "block_ledger": [asdict(b) for b in sim.blocks.values()],
        "natural_forks": {"blocks": [b for b in published if sim.blocks[b].publication_kind == "natural_fork"],
                          "pairs": dict(sim.natural_pairs)},
        "private_chain": private_chain(sim), "abandoned_private": abandoned,
        "release_batches": copy.deepcopy(sim.publication_log),
        "public_frontier": sorted(sim.public_tips), "leading_frontier": sorted(sim.longest_tips),
        "canonical_chain": list(sim.canonical_chain), "reference_tip": sim.reference_tip,
        "pending_window": {"origin": sim.pending, "blocks": delayed} if sim.pending is not None else None,
        "rewards": {a: sim.rewards[a] for a in sim.miners},
        "event_trace": normalized_trace_event(sim),
        "rng": {name: getattr(sim, name).snapshot() for name in STREAMS}}


class AuditedSimulation(PersistentSimulation):
    def step(self, discoverer=None):
        bid = super().step(discoverer)
        self.audit.append(snapshot(self))
        return bid


def matched(strategy, rate, seed=701, aligned=False, active=(), horizon=40):
    p = Population(.2, (("c1", .1), ("c2", .1)), .5, rate, horizon, seed)
    runs = [AuditedSimulation(p, strategy, False, active, rule, trace_mode=True) for rule in RULES]
    initial = {name: getattr(runs[0], name).getstate() for name in STREAMS}
    for sim in runs:
        for name in STREAMS:
            source = getattr(sim, name)
            if aligned:
                source = random.Random()
                source.setstate(initial[name])
            setattr(sim, name, CountedRandom(source))
        sim.audit = [snapshot(sim)]
    return runs


def first_difference(left, right, fields=None, include_initial=False):
    keys = fields or [k for k in left[0] if k not in ("event", "rng")]
    start = 0 if include_initial else 1
    for a, b in zip(left[start:], right[start:]):
        changed = [k for k in keys if a[k] != b[k]]
        if changed:
            return {"event": a["event"], "fields": changed,
                    "left": {k: a[k] for k in changed}, "right": {k: b[k] for k in changed}}
    if fields is None and len(left) != len(right):
        return {"event": min(len(left), len(right)), "fields": ["run_length"],
                "left": len(left)-1, "right": len(right)-1}
    return None


def first_event(left, right, fields=None, include_initial=False):
    difference = first_difference(left, right, fields, include_initial)
    return difference["event"] if difference else None


@pytest.fixture(scope="module")
def completed_cases():
    cases = {}
    for strategy, rate, aligned in itertools.product(("honest", "selfish"), RATES, (False, True)):
        runs = matched(strategy, rate, aligned=aligned)
        for sim in runs:
            result = sim.run()
            assert result["status"] == "COMPLETE"
            validate_run(result, sim.p, sim.rule, 0, strategy, False, ())
        cases[(strategy, rate, aligned)] = runs
    return cases


@pytest.mark.parametrize("strategy,rate", tuple(itertools.product(("honest", "selfish"), RATES)))
def test_native_v1_seed_namespaces_and_first_discovery_mismatches(completed_cases, strategy, rate):
    runs = completed_cases[(strategy, rate, False)]
    assert [sim.audit[1]["discovery_sequence"][0][1] for sim in runs] == ["c1", R, R]
    for left, right in itertools.combinations(runs, 2):
        assert first_event(left.audit, right.audit, ["rng"], True) == 0
        assert first_event(left.audit, right.audit, ["discovery_sequence"]) == (
            2 if left.rule.punishment_rule == "ignore" else 1)


@pytest.mark.parametrize("strategy,rate", tuple(itertools.product(("honest", "selfish"), RATES)))
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="v1 violates requested baseline invariance: RNG namespace contains punishment model")
def test_required_native_h_s0_trace_and_rng_invariance(completed_cases, strategy, rate):
    runs = completed_cases[(strategy, rate, False)]
    assert runs[0].audit == runs[1].audit == runs[2].audit


@pytest.mark.parametrize("strategy,rate", tuple(itertools.product(("honest", "selfish"), RATES)))
def test_aligned_counter_fork_and_ignore_baselines_match_all_audited_fields(completed_cases, strategy, rate):
    counter, ignore, _ = completed_cases[(strategy, rate, True)]
    assert counter.audit == ignore.audit


@pytest.mark.parametrize("rate", RATES)
def test_aligned_h_matches_all_three_rules_including_rng(completed_cases, rate):
    runs = completed_cases[("honest", rate, True)]
    assert runs[0].audit == runs[1].audit == runs[2].audit


@pytest.mark.parametrize("rate", RATES)
def test_aligned_h_with_actual_delayed_sibling_matches_at_requested_rates(rate):
    runs = matched("honest", rate, seed=84, aligned=True)
    for actor in (R, "c1", "target", R):
        for sim in runs:
            sim.step(actor)
    assert runs[0].audit == runs[1].audit == runs[2].audit
    assert bool(runs[0].audit[2]["natural_forks"]["blocks"]) == bool(rate)


def scripted(rate, lead=3, after=(R, "c1"), seed=84):
    runs = matched("selfish", rate, seed=seed, aligned=True)
    for actor in ("target",)*lead + after:
        for sim in runs:
            sim.step(actor)
    return runs


@pytest.mark.parametrize("rate", RATES)
def test_long_lead_reproduction_separates_rng_pending_and_physical_divergence(rate):
    counter, ignore, selfish = scripted(rate)
    assert counter.audit == ignore.audit
    assert first_event(counter.audit, selfish.audit, ["rng"]) == 4
    assert counter.audit[4]["release_batches"] == selfish.audit[4]["release_batches"]
    assert counter.audit[4]["private_chain"] == selfish.audit[4]["private_chain"] == [2, 3]
    assert len(counter.natural_rng.draws) == 0 and selfish.natural_rng.draws == [0.00027760641597729396]
    if rate:
        assert first_event(counter.audit, selfish.audit) == 4
        assert counter.audit[4]["pending_window"] is None
        assert selfish.audit[4]["pending_window"] == {"origin": 4, "blocks": [4, 1]}
        assert first_event(counter.audit, selfish.audit, ["discovery_sequence"]) == 5
        assert first_event(counter.audit, selfish.audit, ["rewards"]) == 5
        assert counter.audit[5]["natural_forks"]["blocks"] == []
        assert selfish.audit[5]["natural_forks"]["blocks"] == [5]
        assert len(counter.tie_rng.draws) == 1 and len(selfish.tie_rng.draws) == 0
    else:
        assert first_event(counter.audit, selfish.audit) is None
        assert len(counter.tie_rng.draws) == len(selfish.tie_rng.draws) == 1


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="v1 selfish policy dispatch consumes an extra natural draw after private-prefix release")
def test_required_aligned_s0_rng_and_transition_invariance_during_private_release(rate):
    counter, ignore, selfish = scripted(rate)
    assert counter.audit == ignore.audit == selfish.audit


@pytest.mark.parametrize("lead", [1, 2, 3, 12])
@pytest.mark.parametrize("rate", RATES)
def test_lead_release_batch_atomicity_and_window_eligibility_audit(lead, rate):
    runs = scripted(rate, lead=lead, after=(R,))
    for sim in runs:
        expected = list(range(1, lead+1)) if lead <= 2 else [1]
        assert sim.publication_log[-1]["blocks"] == expected
        assert sim.events == lead + 1
        assert sim.publication_log[-1]["discovery_event"] == lead + 1
        assert len({sim.blocks[b].release_batch for b in expected}) == 1
    assert len(runs[0].natural_rng.draws) == len(runs[1].natural_rng.draws) == 0
    assert len(runs[2].natural_rng.draws) == (1 if lead > 2 else 0)
    assert (runs[2].pending is not None) == bool(rate and lead > 2)


@pytest.mark.parametrize("rate", [.005, .02])
def test_existing_window_consumed_by_private_discovery_before_later_release(rate):
    runs = matched("selfish", rate, seed=84, aligned=True)
    for actor in (R, "target", "target", "target", "c1"):
        for sim in runs:
            sim.step(actor)
    for sim in runs:
        assert sim.audit[1]["pending_window"] == {"origin": 1, "blocks": [1]}
        # A real private discovery consumes the one-discovery window, despite
        # creating no public block. It does not wait for the next honest actor.
        assert sim.audit[2]["private_chain"] == [2] and sim.audit[2]["pending_window"] is None
        assert sim.audit[5]["release_batches"][-1]["blocks"] == [2]
    assert len(runs[0].natural_rng.draws) == len(runs[1].natural_rng.draws) == 1
    assert len(runs[2].natural_rng.draws) == 2  # draw .364...; no new window at these rates


@pytest.mark.parametrize("rate", [.005, .02])
def test_new_ordinary_publication_after_completed_release_can_open_window_in_all_models(rate):
    runs = scripted(rate, lead=2, after=(R, "c1"))
    for sim in runs:
        assert sim.audit[3]["pending_window"] is None
        assert sim.audit[3]["private_chain"] == []
        assert sim.audit[4]["pending_window"] == {"origin": 4, "blocks": [4]}
        assert len(sim.natural_rng.draws) == 1
    assert runs[0].audit == runs[1].audit == runs[2].audit


@pytest.mark.parametrize("rate", [.005, .02])
def test_private_discovery_consumes_new_window_without_natural_fork_or_publication(rate):
    counter, ignore, selfish = scripted(rate, after=(R, "target"))
    assert selfish.audit[4]["pending_window"] == {"origin": 4, "blocks": [4, 1]}
    for sim in (counter, ignore, selfish):
        assert sim.audit[5]["pending_window"] is None
        assert sim.audit[5]["private_chain"] == [2, 3, 5]
        assert sim.audit[5]["publication_sequence"] == sim.audit[4]["publication_sequence"]
        assert not sim.natural_pairs


@pytest.mark.parametrize("rate", [.005, .02])
def test_existing_bundle_consumed_on_discovery_does_not_delay_or_split_following_atomic_release(rate):
    runs = scripted(rate, after=("c1", "c1"))
    assert runs[2].audit[4]["pending_window"] == {"origin": 4, "blocks": [4, 1]}
    for sim in runs:
        assert sim.blocks[5].parent_id == 4  # explicit owner knows its own block
        assert sim.audit[5]["release_batches"][-1]["blocks"] == [2, 3]
        assert sim.audit[5]["release_batches"][-1]["discovery_event"] == 5
        assert sim.audit[5]["pending_window"] is None
        assert sim.events == 5 and not sim.natural_pairs
    assert len(runs[0].natural_rng.draws) == len(runs[1].natural_rng.draws) == 0
    assert len(runs[2].natural_rng.draws) == 1  # no redraw on release


@pytest.mark.parametrize("strategy,rate", tuple(itertools.product(("honest", "selfish"), RATES)))
def test_unflagged_membership_does_not_arm_punishment_but_model_dispatch_persists(strategy, rate):
    empty = matched(strategy, rate, aligned=True)
    candidates = matched(strategy, rate, aligned=True, active=("c1", "c2"))
    for actor in ("target", "target", "target", R, "c1"):
        for sim in (*empty, *candidates):
            sim.step(actor)
    for a, b in zip(empty, candidates):
        assert a.audit == b.audit
        assert not b.policy.armed and not b.activations
        if isinstance(b.rule, SelfishCounterSpec):
            assert set(b.policy.states) == ({"target"} if strategy == "selfish" else set())


def test_current_rule_specific_cache_and_validator_prevent_unsafe_baseline_relabeling(completed_cases):
    runs = completed_cases[("honest", .02, False)]
    keys = [mining_cache_key(s.p, 0, "honest", False, (), s.rule) for s in runs]
    assert len(set(keys)) == 3
    payload = runs[0].report()
    for recipient in runs[1:]:
        with pytest.raises(ValueError, match="model mismatch"):
            validate_run(payload, recipient.p, recipient.rule, 0, "honest", False, ())


def evidence():
    """Compact reproducible audit summary. Does not modify any simulator file."""
    result = {"population": {"target": .2, "c1": .1, "c2": .1, "residual": .6},
              "gamma": .5, "repetition": 0, "native_seed": 701, "accepted_block_target": 40,
              "scripted_seed": 84, "completed_cases": [], "scripted_cases": []}
    for strategy, rate, aligned in itertools.product(("honest", "selfish"), RATES, (False, True)):
        runs = matched(strategy, rate, aligned=aligned)
        for sim in runs:
            assert sim.run()["status"] == "COMPLETE"
        comparisons = []
        for left, right in itertools.combinations(runs, 2):
            comparison = {"pair": [left.rule.punishment_rule, right.rule.punishment_rule],
                          "first_state_or_behavior_difference": first_event(left.audit, right.audit)}
            for field in ("discovery_sequence", "publication_sequence", "natural_forks", "private_chain",
                          "release_batches", "public_frontier", "canonical_chain", "rng", "event_trace", "rewards"):
                comparison[field] = first_event(left.audit, right.audit, [field], field == "rng")
            comparisons.append(comparison)
        result["completed_cases"].append({"strategy": strategy, "lambda": rate, "aligned_streams": aligned,
            "comparisons": comparisons, "final": {s.rule.punishment_rule: {
                "events": s.events, "rewards": s.audit[-1]["rewards"], "rng": s.audit[-1]["rng"]} for s in runs}})
    for rate in RATES:
        runs = scripted(rate)
        result["scripted_cases"].append({"lambda": rate, "schedule": ["target"]*3 + [R, "c1"],
            "first_rng_difference": first_difference(runs[0].audit, runs[2].audit, ["rng"]),
            "first_transition_difference": first_difference(runs[0].audit, runs[2].audit, ["pending_window"]),
            "events": {s.rule.punishment_rule: s.audit[4:] for s in runs}})
    return result


if __name__ == "__main__":
    print(json.dumps(evidence(), indent=2))
