"""Bounded local audit probes. No production configuration or runner is used.

Run with: .venv/bin/python -m analysis.audit_persistent_v2_readiness
Outputs only docs/persistent_v2_readiness_evidence.json. Runtime sources are read
and hashed before/after. Horizons and the small matrix are deliberately fixed.
"""
from collections import Counter
import cProfile
import hashlib
import itertools
import json
from pathlib import Path
import platform
import pstats
import random
import sys
from time import perf_counter

from punishment_sim.coalition import ExplicitSimulation, Population
from punishment_sim.model import RaceOrigin
from punishment_sim.persistent_checkpoint import canonical_json, digest
from punishment_sim.persistent_v2 import PersistentSimulation, Rule
from punishment_sim.persistent_v2_checkpoint import validate_run, CONDITIONAL_SCHEMA

ROOT = Path(__file__).resolve().parents[1]
RULES = (Rule("counter_fork", 1), Rule("counter_fork", 2), Rule("counter_fork", 3),
         Rule("ignore"), Rule("selfish"))
STREAMS = ("rng", "tie_rng", "natural_rng")
R = "honest_residual"


def population(n=2, rate=.02, horizon=200, seed=701):
    return Population(.2, (("c1", .2),) if n == 1 else (("c1", .1), ("c2", .1)),
                      .5, rate, horizon, seed)


def source_hashes():
    paths = [*sorted((ROOT / "punishment_sim").glob("*.py")),
             ROOT / "configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_1pct.json"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


class CountedRandom:
    def __init__(self, source, constant=None):
        self.source, self.constant, self.draws = source, constant, []

    def random(self):
        value = self.source.random() if self.constant is None else self.constant
        self.draws.append(value)
        return value

    def getstate(self):
        return self.source.getstate()

    @property
    def count(self):
        return len(self.draws)

    @property
    def last(self):
        return self.draws[-1] if self.draws else None

    def snapshot(self):
        return {"draw_count": len(self.draws), "last_draw": self.draws[-1] if self.draws else None,
                "state_sha256": hashlib.sha256(repr(self.getstate()).encode()).hexdigest()}


class ObservedPetty(ExplicitSimulation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.publication_order, self.releases, self.natural_ids, self.observations = [], [], [], []
        self.tie_choices = []

    def _new(self, owner, parent, withheld=False):
        bid = super()._new(owner, parent, withheld)
        if not withheld:
            self.publication_order.append(bid)
        return bid

    def step(self):
        old_races = self.race_origins.copy()
        incoming_race = self.race
        super().step()
        if incoming_race is not None:
            self.tie_choices.append({"event": self.events,
                "tips": sorted((incoming_race["a"], incoming_race["b"])),
                "parent": self.blocks[self.events].parent_id})
        known = set(self.publication_order)
        released = [b.id for b in self.blocks.values() if b.published and b.id not in known]
        self.publication_order.extend(released)
        if released:
            self.releases.append({"event": self.events, "blocks": released})
        if self.race_origins[RaceOrigin.NATURAL_PROPAGATION.value] > old_races[RaceOrigin.NATURAL_PROPAGATION.value]:
            self.natural_ids.append(self.events)
        self.observations.append(snapshot(self))


class ObservedPersistent(PersistentSimulation):
    def step(self, discoverer=None):
        bid = super().step(discoverer)
        self.observations.append(snapshot(self))
        return bid


def snapshot(sim):
    petty = isinstance(sim, ExplicitSimulation)
    published = sim.publication_order if petty else [b for batch in sim.publication_log for b in batch["blocks"]]
    if petty:
        chain, tip = [], sim.tip
        while tip is not None:
            chain.append(tip)
            tip = sim.blocks[tip].parent_id
        chain.reverse()
        private = list(sim.private)
        window = [sim.pending] if sim.pending is not None else []
        rewards = Counter(b.owner_id for b in sim.blocks.values() if b.disposition == "accepted")
        releases = sim.releases
        natural_ids = sim.natural_ids
        ties = sim.tie_choices
    else:
        chain = list(sim.canonical_chain)
        private = list(sim.selfish.states["target"].private_chain) if "target" in sim.selfish.states else []
        window = sim.window["delayed_tips"] if sim.window else []
        rewards = sim.rewards
        releases = [{"event": b["discovery_event"], "blocks": b["blocks"]} for b in sim.publication_log
                    if b["kind"] == "target_selfish_release"]
        natural_ids = [b.id for b in sim.blocks.values() if b.publication_kind == "natural_fork"]
        ties = [{"event": e["event"], "tips": e["choice"]["tips"], "parent": e["choice"]["parent"]}
                for e in sim.public_events if e["choice"] is not None and len(e["choice"]["tips"]) > 1]
    pub = set(published)
    tips = pub - {sim.blocks[b].parent_id for b in pub}
    return {"event": sim.events,
        "discoveries": [(b.id, b.owner_id) for b in sim.blocks.values()],
        "ancestry": [(b.id, b.parent_id, b.height, b.initially_withheld) for b in sim.blocks.values()],
        "publications": list(published), "releases": list(releases),
        "natural": {"blocks": list(natural_ids), "pairs": dict(sim.natural_pairs)},
        "private": private, "pending_delayed_tips": list(window), "public_frontier": sorted(tips),
        "canonical": chain, "rewards": {a: rewards[a] for a in sim.miners},
        "tie_choices": list(ties),
        "rng": {name: getattr(sim, name).snapshot() for name in STREAMS}}


def paired_engines(strategy, rate, seed=701, aligned=False, owners=None, natural=None, tie=None):
    p = population(rate=rate, seed=seed)
    old = ObservedPetty(p, strategy, False, (), discoverers=owners, trace_mode=True)
    new = ObservedPersistent(p, strategy, False, (), RULES[0], trace_mode=True)
    for name in STREAMS:
        state = getattr(new, name).getstate()
        for sim in (old, new):
            source = getattr(sim, name)
            if aligned:
                source = random.Random()
                source.setstate(state)
            constant = natural if name == "natural_rng" else tie if name == "tie_rng" else None
            setattr(sim, name, CountedRandom(source, constant))
    new.observations = []
    old.observations = [snapshot(old)]
    new.observations = [snapshot(new)]
    return old, new


def differences(old, new):
    fields = [f for f in old.observations[0] if f != "event"]
    first = {}
    examples = {}
    for field in fields:
        first[field] = None
        for left, right in zip(old.observations, new.observations):
            if left[field] != right[field]:
                first[field] = left["event"]
                if field not in ("discoveries", "ancestry", "public_frontier") or left["event"] <= 8:
                    examples[field] = {"event": left["event"], "petty_v4": left[field], "persistent_v2": right[field]}
                break
    return {"first_divergence_by_field": first, "first_difference_examples": examples,
        "compared_events": min(old.events, new.events), "events": [old.events, new.events],
        "terminal": {"petty_v4": snapshot(old), "persistent_v2": snapshot(new)},
        "native_endpoint_state": {
            "petty_v4": {"accepted_count": old.accepted_count, "tip": old.tip, "pending": old.pending,
                         "race": old.race, "private": list(old.private)},
            "persistent_v2": {"reference_height": new.public_height, "reference_tip": new.reference_tip,
                              "pending_window": new.window, "private_states": new.state_snapshots(),
                              "boundary": new.terminal_state()["boundary"]}},
        "trajectory_sha256": [digest(old.observations), digest(new.observations)]}


def compatibility():
    completed, scripted = [], []
    for strategy, rate, aligned in itertools.product(("honest", "selfish"), (0, .005, .02), (False, True)):
        old, new = paired_engines(strategy, rate, aligned=aligned)
        a, b = old.run(), new.run()
        assert b["status"] == "COMPLETE"
        completed.append({"strategy": strategy, "lambda": rate, "seed": 701, "repetition": 0,
            "horizon": 200, "aligned_diagnostic_streams": aligned,
            "result_sha256": [digest(a), digest(b)], **differences(old, new)})
    for strategy, rate in itertools.product(("honest", "selfish"), (0, .005, .02)):
        owners = [R, R] if strategy == "honest" else ["target", "target", "target", R, "c1"]
        old, new = paired_engines(strategy, rate, seed=84, aligned=True, owners=owners, natural=.001, tie=.75)
        for actor in owners:
            old.step()
            new.step(actor)
        scripted.append({"strategy": strategy, "lambda": rate, "owners": owners,
            "diagnostic_only": True, "natural_variate": .001, "tie_variate": .75,
            **differences(old, new)})
    return {"completed": completed, "scripted": scripted}


def k_semantics():
    # Preserve the dated readiness audit's reproduction of the pre-fix gap.
    # Current enforcement is tested separately in the production-readiness tests.
    from ._persistent_v2_reference import PersistentSimulation as AuditedEngine, Rule as AuditedRule
    cases = []
    for k in (1, 2, 3):
        def engine(rate=0):
            return AuditedEngine(population(rate=rate), "honest", True, ("c1",), AuditedRule("counter_fork", k))

        sim = engine()
        target = sim.step("target")
        counter = sim.step("c1")
        tie_depth = sim.punishment.episode.depth
        sim.discover(R)  # unrelated genesis sibling, no defending advancement
        unrelated_depth = sim.punishment.episode.depth
        tip, depths = target, []
        for i in range(k):
            tip = sim.discover("c2" if i == 0 else R, tip)
            depths.append(sim.punishment.episode.depth if sim.punishment.episode else sim.punishment.history[-1]["depth"])
        ordinary = {"counter_parent": sim.blocks[counter].parent_id, "tie_depth": tie_depth,
            "unrelated_depth": unrelated_depth, "defending_depths": depths,
            "outcome": sim.punishment.history[-1]["outcome"], "leaveout_first_extension_owner": "c2"}

        refresh = engine()
        tip = refresh.step("target")
        for _ in range(k-1):
            tip = refresh.discover(R, tip)
        target2 = refresh.discover("target", tip)
        refreshed = {"episode": refresh.punishment.snapshot(), "history": refresh.punishment.history,
                     "target2": target2, "expected_anchor": tip}

        helper = engine()
        helper.step("target")
        c = helper.step("c1")
        helper.discover("c2", c)
        assistance = helper.punishment.history[-1]

        sibling = engine()
        t = sibling.step("target")
        sibling.discover(R, t)
        sibling.discover("c2", t)
        sibling_state = sibling.punishment.snapshot() or sibling.punishment.history[-1]

        guard = engine()
        tip = guard.step("target")
        for _ in range(k-1):
            tip = guard.discover(R, tip)
        guard.discover("c1", tip)  # direct fixture intervention, not native fork choice
        cases.append({"k": k, "ordinary_and_leaveout": ordinary, "target_refresh": refreshed,
            "honest_counter_branch_assistance": assistance,
            "defending_same_height_siblings": sibling_state,
            "active_member_on_defended_branch_diagnostic": {"native_reachable": False,
                "actual_outcome": guard.punishment.history[-1]["outcome"],
                "actual_depth": guard.punishment.history[-1]["depth"], "intended_depth": k-1}})
    return cases


class MeasuredPersistent(PersistentSimulation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = Counter()

    def step(self, discoverer=None):
        prior = self.public_height
        episode = getattr(self.punishment, "episode", None)
        trigger = episode.trigger if episode is not None else None
        bid = super().step(discoverer)
        if trigger is not None and self.blocks[bid].owner_id in self.active:
            assert not self.descends(bid, trigger), "native active coalition discovery on defended branch"
        states = list(self.selfish.states.values())
        values = {"public_frontier_max": len(self.public_tips), "block_store_max": len(self.blocks),
            "private_states_max": sum(bool(s.private_chain) for s in states),
            "private_state_slots": len(states),
            "private_lead_max": max([0] + [self.height(s.private_chain[-1])-self.public_height
                                          for s in states if s.private_chain]),
            "private_blocks_per_actor_max": max([0] + [len(s.private_chain) for s in states])}
        for name, value in values.items():
            self.metrics[name] = max(self.metrics[name], value)
        assert len(self.blocks) == self.events
        assert sum(self.rewards.values()) == self.public_height
        assert sum(self.blocks[t].owner_id == "target" for t in self.longest_tips) <= 1
        assert self.public_height >= prior
        return bid


def probe(rule, n, rate, horizon, repetition, strategy="selfish"):
    p = population(n, rate, horizon)
    active = tuple(a for a, _ in p.candidates)
    t0 = perf_counter()
    sim = MeasuredPersistent(p, strategy, True, active, rule, repetition=repetition)
    while sim.public_height < horizon and sim.events < sim.max_events:
        before_height = sim.public_height
        sim.step()
    t1 = perf_counter()
    before = (sim.events, sim.publication_sequence, sim.state_snapshots())
    result = sim.run()  # endpoint reached: must only report, never settle
    t2 = perf_counter()
    assert before == (sim.events, sim.publication_sequence, sim.state_snapshots())
    assert result["status"] == "COMPLETE" and before_height < horizon <= sim.public_height
    for actor, record in result["actors"].items():
        assert record["discovered"] == record["accepted"] + record["public_noncanonical"] + record["unresolved"]
    envelope = {"schema": CONDITIONAL_SCHEMA, "identity": result["identity"], "result": result}
    envelope["content_sha256"] = digest(envelope)
    data = canonical_json(envelope).encode()
    t3 = perf_counter()
    validate_run(result, p, rule, repetition, strategy, True, active)
    t4 = perf_counter()
    rerun = PersistentSimulation(p, strategy, True, active, rule, repetition=repetition).run()
    assert result == rerun
    bounds = result["terminal"]["boundary"]["actor_payoff_bounds"]
    return {"rule": rule.punishment_rule, "k": rule.counter_fork_k, "members": n,
        "strategy": strategy, "lambda": rate, "horizon": horizon, "seed": p.seed, "repetition": repetition,
        "runtime_seconds": t2-t0, "discovery_loop_seconds": t1-t0, "terminal_report_seconds": t2-t1,
        "serialization_seconds": t3-t2, "validation_seconds": t4-t3,
        "checkpoint_bytes_compact": len(data), "checkpoint_bytes_indented": len(json.dumps(envelope, indent=2).encode()),
        "events": sim.events, "reference_blocks": sim.public_height,
        "discoveries_per_reference_block": sim.events/sim.public_height,
        **sim.metrics, "reorganizations": len(sim.reorganizations),
        "reorganization_depth_max": max([0]+[len(r["removed"]) for r in sim.reorganizations]),
        "unresolved_at_horizon": result["terminal"]["boundary"]["potentially_material"],
        "active_private_at_horizon": sum(bool(s.private_chain) for s in sim.selfish.states.values()),
        "terminal_payoff_bound_width": max(v[1]-v[0] for v in bounds.values()) if bounds else None,
        "resource_or_censoring": None, "deterministic_rerun_exact": True,
        "condition_id": result["condition_id"], "result_sha256": digest(result)}


def profiles():
    output = []
    for rule in RULES:
        p = population(horizon=500)
        profile = cProfile.Profile()
        sim = PersistentSimulation(p, "selfish", True, ("c1", "c2"), rule)
        profile.runcall(sim.run)
        stats = pstats.Stats(profile)
        entries = []
        for (filename, line, function), (primitive, calls, own, cumulative, _) in stats.stats.items():
            if "punishing_coalitions" in filename and "site-packages" not in filename:
                entries.append({"file": str(Path(filename).relative_to(ROOT)), "line": line, "function": function,
                                "calls": calls, "own_seconds": own, "cumulative_seconds": cumulative})
        output.append({"rule": rule.punishment_rule, "k": rule.counter_fork_k,
                       "profiled_horizon": 500, "top_cumulative": sorted(entries, key=lambda e: -e["cumulative_seconds"])[:15]})
    return output


def reuse_scope():
    inventory = json.loads((ROOT / "docs/oceanic_v4_1pct_scope.json").read_text())
    configurations = inventory["top_level_configurations"]
    repetitions = inventory["repetitions"]
    single_rule = inventory["mining_simulations"]
    baseline_runs = 2*configurations*repetitions
    cases = []
    for variants in (3, 5):
        independent = variants*single_rule
        saved = (variants-1)*baseline_runs
        cases.append({"rule_variants": variants, "independent_runs": independent,
            "shared_baseline_runs": baseline_runs, "saved_runs": saved, "remaining_runs": independent-saved,
            "saved_fraction": saved/independent,
            "nominal_accepted_block_work": (independent-saved)*inventory["accepted_blocks_per_simulation"]})
    return {"basis": "arithmetic over existing scope artifact, hypothetical identical grid; no new grid or mining",
        "source": "docs/oceanic_v4_1pct_scope.json", "configurations_per_variant": configurations,
        "repetitions": repetitions, "single_variant_runs": single_rule, "cases": cases}


def main():
    started = perf_counter()
    before = source_hashes()
    result = {"audit_date": "2026-09-21", "purpose": "bounded local implementation/performance diagnostics",
        "python": sys.version, "platform": {"system": platform.system(), "machine": platform.machine()},
        "prohibition_compliance": {"production_simulations": False, "ssh": False, "xtra_access": False,
                                   "remote_jobs": False, "runtime_or_production_configuration_edits": False},
        "compatibility": compatibility(), "counter_fork_semantics": k_semantics(), "probes": []}
    for rule, n, rate, horizon, rep in itertools.product(RULES, (1, 2), (0, .02), (200, 500), (0, 1)):
        row = probe(rule, n, rate, horizon, rep)
        result["probes"].append(row)
        print(f"probe {len(result['probes'])}/100 {row['rule']} k={row['k']} n={n} lambda={rate} h={horizon}: {row['runtime_seconds']:.4f}s", flush=True)
    for rule, n, rate in itertools.product(RULES, (1, 2), (0, .02)):
        result["probes"].append(probe(rule, n, rate, 200, 0, "honest"))
    result["profiles"] = profiles()
    result["baseline_reuse_scope"] = reuse_scope()
    result["source_sha256_before"] = before
    result["source_sha256_after"] = source_hashes()
    assert before == result["source_sha256_after"]
    result["audit_wall_seconds"] = perf_counter()-started
    path = ROOT / "docs/persistent_v2_readiness_evidence.json"
    path.write_text(json.dumps(result, indent=2)+"\n")
    print(f"Completed {len(result['probes'])} probes plus exact reruns; wrote {path.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
