"""Common persistent mining/network engine. Historical v1 modules are immutable.

All rules and conditional runs execute the same step and publication machinery.
An inactive rule has no policy instance and produces a shared baseline payload.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
import hashlib
import random

from .persistent import PersistentSimulation as TreeEngine, UnsupportedStateError
from .persistent_v2_policies import CounterForkPolicy, PettyPolicy
from .persistent_v2_index import PublicVisibility, initialize_indexes, index_publication, advance_frontier
from .ostracism import OstracismPolicy
from .selfish_counter import SelfishState, SelfishStateError
from .selfish_strategy import release_plan
from .persistent_checkpoint import digest

NETWORK_VERSION = "persistent-network-v2"
BASELINE_VERSION = "persistent-common-baseline-v2"
PROPAGATION = "public-announcement-frontier-one-discovery-v2"
REACTION_ORDER = "public-snapshot-rounds-population-order-v1"
STOPPING = "completed-discovery-reference-height-no-finalization-v2"
RNG_VERSION = "sha256-python-random-common-streams-v2"
MODELS = {"counter_fork": "persistent-counter-fork-v2", "ignore": "persistent-ignore-v2",
          "selfish": "persistent-selfish-counter-v2", "petty": "persistent-petty-v2"}


@dataclass(frozen=True)
class Rule:
    punishment_rule: str
    counter_fork_k: int | None = None

    def __post_init__(self):
        if not isinstance(self.punishment_rule, str) or self.punishment_rule not in MODELS:
            raise ValueError("one individual v2 punishment rule required")
        if self.punishment_rule == "counter_fork":
            if type(self.counter_fork_k) is not int or self.counter_fork_k < 1:
                raise ValueError("counter_fork_k must be a positive integer")
        elif self.counter_fork_k is not None:
            raise ValueError("only counter_fork has counter_fork_k")


def model_version(rule):
    if not isinstance(rule, Rule):
        raise ValueError("a v2 Rule is required; v1 specifications are historical")
    return MODELS[rule.punishment_rule]


def configuration_id(population, rule):
    return digest({"network_version": NETWORK_VERSION, "model_version": model_version(rule),
                   "rule": asdict(rule), "population": asdict(population)})[:24]


def condition_identity(population, repetition, strategy, flagged, coalition, rule):
    model_version(rule)
    if type(population.seed) is not int or type(population.target_accepted_blocks) is not int or population.target_accepted_blocks < 1:
        raise ValueError("integer seed and positive integer horizon required")
    if type(repetition) is not int or repetition < 0:
        raise ValueError("repetition must be a nonnegative integer")
    if strategy not in ("honest", "selfish") or type(flagged) is not bool:
        raise ValueError("invalid target strategy or conditional flag")
    C = tuple(sorted(coalition))
    if len(C) != len(set(C)) or not set(C) <= {a for a, _ in population.candidates}:
        raise ValueError("invalid active coalition")
    enabled = bool(flagged and C)
    return {"network_version": NETWORK_VERSION, "propagation": PROPAGATION, "rng_version": RNG_VERSION,
        "stopping": STOPPING, "reaction_order": REACTION_ORDER,
        "model_version": model_version(rule) if enabled else BASELINE_VERSION,
        "rule": asdict(rule) if enabled else None, "population": asdict(population),
        "base_seed": population.seed, "repetition": repetition, "actual_seed": population.seed + repetition,
        "strategy": strategy, "flagged": enabled, "active_coalition": list(C) if enabled else []}


def mining_cache_key(population, repetition, strategy, flagged, coalition, rule):
    return digest(condition_identity(population, repetition, strategy, flagged, coalition, rule))


class CommonRandom:
    """Auditable common stream, independent of policy and target strategy."""
    def __init__(self, seed, name):
        material = f"{NETWORK_VERSION}:{RNG_VERSION}:{seed}:{name}"
        raw = hashlib.sha256(material.encode()).digest()
        self.source = random.Random(int.from_bytes(raw[:8], "big"))
        self.count = 0
        self.last = None

    def random(self):
        self.last = self.source.random()
        self.count += 1
        return self.last

    def getstate(self):
        return self.source.getstate()

    def snapshot(self):
        return {"draw_count": self.count, "last_draw": self.last,
                "state_sha256": hashlib.sha256(repr(self.getstate()).encode()).hexdigest()}


class SelfishActors:
    """Generic target/member strategy scheduling, not a punishment network path."""
    def __init__(self, sim, actors):
        self.sim = sim
        self.states = {m.id: SelfishState(m.id) for m in sim.p.miners if m.id in actors}
        self.history, self.pending = [], []
        self.processing = False

    def on_publication(self, published):
        sim, new = self.sim, set(published)
        for actor, state in self.states.items():
            state.private_chain = [b for b in state.private_chain if b not in new]
            for bid in published:
                block = sim.blocks[bid]
                if block.owner_id == actor:
                    state.exposed_tip = bid
                    if block.initially_withheld:
                        state.released_blocks.append(bid)
        self.pending.extend(published)
        if self.processing:
            return
        self.processing = True
        try:
            while self.pending:
                observed, self.pending = self.pending, []
                decisions = []
                for actor, state in self.states.items():
                    plan = release_plan(sim, state.private_chain, observed)
                    if plan is not None:
                        decisions.append({"actor_id": actor, "action": plan.action, "blocks": list(plan.blocks),
                                          "private_tip_before": state.private_chain[-1]})
                if not decisions:
                    continue
                self.history.append({"outcome": "SELFISH_REACTION_ROUND", "round": len(self.history)+1,
                    "discovery_event": sim.events, "observed_publications": list(observed),
                    "public_height": sim.public_height, "publication_sequence": sim.publication_sequence,
                    "decisions": decisions})
                before = sum(len(s.private_chain) for s in self.states.values())
                for decision in decisions:
                    actor = decision["actor_id"]
                    state = self.states[actor]
                    if decision["action"] == "ABANDON":
                        state.abandoned_blocks.extend(state.private_chain)
                        state.private_chain.clear()
                    else:
                        sim.publish(decision["blocks"], "target_selfish_release" if actor == "target"
                                    else "member_selfish_release")
                if sum(len(s.private_chain) for s in self.states.values()) >= before:
                    raise SelfishStateError("reaction round made no private-state progress")
        finally:
            self.processing = False


class Publications:
    """Notify the active strategy policy and then generic selfish actors."""
    def __init__(self, sim):
        self.sim = sim

    @property
    def active(self):
        p = self.sim.punishment
        return p.active if p is not None else False

    def snapshot(self):
        sim = self.sim
        if sim.punishment is not None:
            return sim.punishment.snapshot()
        if sim.enabled:
            return {"punishment_rule": "selfish", "activation_event": 0, "active_members": sorted(sim.active)}
        return None

    def on_publication(self, sim, published):
        if sim.punishment is not None:
            sim.punishment.on_publication(sim, published)
        index_publication(sim, published)
        sim.selfish.on_publication(published)


def eligible_tips(sim, actor, visible):
    """One visibility-first eligibility path, including interior policy anchors."""
    p = sim.punishment
    if isinstance(p, CounterForkPolicy):
        choices = p.eligible(sim, actor, visible)
    elif isinstance(p, OstracismPolicy) and actor in sim.active:
        choices = sim.acceptable_index.best(visible)
    else:
        choices = None
    if choices is None:
        choices = sim.public_index.best(visible)
    if isinstance(p, PettyPolicy):
        choices = p.restrict(actor, choices)
    if not choices:
        # Only final public tips can be delayed: a trigger's parent/anchor
        # remains visible. Never silently replace the counter-fork anchor.
        raise UnsupportedStateError("policy has no visible eligible parent")
    highest = max(sim.height(b) for b in choices)
    return sorted((b for b in choices if sim.height(b) == highest), key=lambda b: -1 if b is None else b)


def visible_public(sim, actor, window):
    hidden = set(window["delayed_tips"]) if window else set()
    if actor != "honest_residual":
        for bid in list(hidden):
            if sim.blocks[bid].owner_id == actor:
                while bid in hidden:
                    hidden.remove(bid)
                    bid = sim.blocks[bid].parent_id
    return PublicVisibility(sim.public, hidden) if hidden else sim.public


class PersistentSimulation(TreeEngine):
    def __init__(self, population, strategy, flagged, active_coalition=(), rule=None,
                 max_events=None, trace_mode=False, *, repetition=0, production=False):
        rule = rule if rule is not None else Rule("counter_fork", 1)
        self.identity = condition_identity(population, repetition, strategy, flagged, active_coalition, rule)
        self.base_population = population
        self.enabled = self.identity["flagged"]
        if max_events is not None and (type(max_events) is not int or max_events < 1):
            raise ValueError("max_events must be a positive integer")
        self.p = replace(population, seed=self.identity["actual_seed"])
        self.strategy, self.flagged = strategy, self.enabled
        self.active = frozenset(self.identity["active_coalition"])
        self.miners = {m.id: m for m in self.p.miners}
        self.blocks, self.children = {}, defaultdict(set)
        self.public, self.public_tips, self.longest_tips = set(), set(), set()
        self.public_height = self.events = self.publication_sequence = self.release_batch = 0
        self.reference_tip = self.pending = None
        self.canonical_chain, self.publication_log, self.reorganizations = [], [], []
        # These empty legacy containers are used only by inherited tree helpers;
        # all live private state belongs to SelfishActors below.
        self.private, self.abandoned_private = [], set()
        self.rewards, self.discovered, self.natural_pairs = Counter(), Counter(), Counter()
        self.activations, self.opportunities = Counter(), Counter()
        self.max_events = max_events if max_events is not None else max(1000, 100*self.p.target_accepted_blocks)
        self.trace = [] if trace_mode else None
        if type(production) is not bool or (production and trace_mode):
            raise ValueError("production mode requires trace_mode=False")
        self.production = production
        initialize_indexes(self)
        self.rng, self.tie_rng, self.natural_rng = (self._rng(name) for name in ("discoveries", "ties", "natural"))
        self.rule, self.model_version = rule, self.identity["model_version"]
        self.punishment = None
        if self.enabled and rule.punishment_rule == "counter_fork":
            self.punishment = CounterForkPolicy(rule, True)
        elif self.enabled and rule.punishment_rule == "ignore":
            self.punishment = OstracismPolicy(self, True)
        elif self.enabled and rule.punishment_rule == "petty":
            self.punishment = PettyPolicy(self)
        actors = {"target"} if strategy == "selfish" else set()
        if self.enabled and rule.punishment_rule == "selfish":
            actors.update(self.active)
            self.activations.update({a: 1 for a in self.active})
        self.selfish = SelfishActors(self, actors)
        self.policy = Publications(self)
        self.window = None
        self.public_events = []
        self.scripted_discoveries = []

    def _rng(self, name):
        return CommonRandom(self.p.seed, name)

    def descends(self, bid, ancestor):
        return self.ancestry_index.descends(bid, ancestor)

    def publish(self, ids, kind="ordinary"):
        ids = list(ids)
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate ID inside publication batch")
        known, new = set(), []
        for bid in ids:
            if bid not in self.blocks:
                raise ValueError("unknown publication")
            if bid in self.public or bid in known:
                continue
            parent = self.blocks[bid].parent_id
            if parent is not None and parent not in self.public and parent not in known:
                raise ValueError("publication must expose parents before children")
            known.add(bid)
            new.append(bid)
        if not new:
            return
        # Checks the prospective leading tips before mutating the public ledger.
        advance_frontier(self, new)
        self.release_batch += 1
        for bid in new:
            b = self.blocks[bid]
            self.publication_sequence += 1
            b.publication_sequence, b.release_batch, b.publication_kind = self.publication_sequence, self.release_batch, kind
        chosen = self.reference_tip if self.reference_tip in self.longest_tips else min(
            self.longest_tips, key=lambda b: (self.blocks[b].publication_sequence, b))
        self._adopt(chosen)
        self.publication_log.append({"batch": self.release_batch, "blocks": new,
                                     "kind": kind, "discovery_event": self.events})
        self.policy.on_publication(self, new)

    def rng_snapshot(self):
        return {name: stream.snapshot() for name, stream in (
            ("discoveries", self.rng), ("ties", self.tie_rng), ("natural", self.natural_rng))}

    def discover(self, owner, parent=None, withheld=False, kind="ordinary"):
        if withheld:
            state = self.selfish.states.get(owner)
            if state is None:
                raise ValueError("honest actor has no private state")
            if state.private_chain and parent != state.private_chain[-1]:
                raise ValueError("private actor must extend its own private tip")
            if not state.private_chain and parent is not None and parent not in self.public:
                raise ValueError("private chain must start on public history")
        bid = super().discover(owner, parent, withheld, kind)
        self.ancestry_index.add(bid)
        if withheld:
            state.private_chain.append(bid)
        return bid

    def choose_parent(self, actor, window=None):
        tips = eligible_tips(self, actor, visible_public(self, actor, window))
        return self.choose_among_tips(actor, tips)

    def eligible_tips(self, actor, window=None):
        return eligible_tips(self, actor, visible_public(self, actor, window))

    def step(self, discoverer=None):
        actor = self._draw() if discoverer is None else discoverer
        if actor not in self.miners:
            raise ValueError("unknown discoverer")
        if discoverer is not None:
            self.scripted_discoveries.append(self.events+1)
        incoming, self.window = self.window, None
        self.pending = None
        start_height, start_tips = self.public_height, sorted(self.longest_tips)
        start_batch = len(self.publication_log)
        if self.policy.active or (self.enabled and self.rule.punishment_rule == "selfish"):
            self.opportunities.update(self.active)
        state = self.selfish.states.get(actor)
        source, choice = None, None
        if state is not None and state.private_chain:
            bid = self.discover(actor, state.private_chain[-1], withheld=True)
        else:
            visible = self.public if state is not None else visible_public(self, actor, incoming)
            tips = eligible_tips(self, actor, visible)
            before = self.tie_rng.count
            parent = self.choose_among_tips(actor, tips)
            choice = {"tips": tips, "parent": parent,
                      "draw": self.tie_rng.last if self.tie_rng.count > before else None}
            if state is not None:
                bid = self.discover(actor, parent, withheld=len(start_tips) <= 1,
                    kind="target_tie_resolution" if actor == "target" else "member_tie_resolution")
            else:
                full_tips = eligible_tips(self, actor, self.public)
                if incoming and self.height(parent) < self.height(full_tips[0]):
                    hidden = [b for b in full_tips if b is not None and b not in visible]
                    if hidden:
                        source = min(hidden, key=lambda b: self.blocks[b].publication_sequence)
                punishing = self.punishment is not None and self.punishment.active and actor in self.active
                if isinstance(self.punishment, PettyPolicy):
                    punishing = self.punishment.is_punishing(actor, visible)
                kind = self.rule.punishment_rule if punishing else "natural_fork" if source is not None else "ordinary"
                bid = self.discover(actor, parent, kind=kind)
                if kind == "natural_fork":
                    self.natural_pairs["--".join(sorted((actor, self.blocks[source].owner_id)))] += 1
        published = [b for batch in self.publication_log[start_batch:] for b in batch["blocks"]]
        eligible = incoming is None and len(start_tips) <= 1 and bid in self.public and self.height(bid) > start_height
        draw = self.natural_rng.random() if eligible else None
        if draw is not None and draw < self.p.natural_fork_rate:
            self.window = {"discovery_event": self.events, "origin_block": bid, "blocks": published,
                           "delayed_tips": [b for b in published if b in self.public_tips]}
            self.pending = bid
        event = {"event": self.events, "discoverer": actor, "block": bid,
            "public_height_before": start_height, "leading_tips_before": start_tips,
            "incoming_window": incoming, "choice": choice, "delayed_source": source,
            "publications": published, "lambda_eligible": eligible, "lambda_draw": draw,
            "pending_window": self.window}
        if not self.production:
            self.public_events.append(event)
        if self.trace is not None:
            self.trace.append({**event, "private_states": self.state_snapshots(),
                "public_frontier": sorted(self.public_tips), "canonical_chain": list(self.canonical_chain),
                "publication_sequence": self.publication_sequence, "rewards": dict(self.rewards),
                "rng": self.rng_snapshot(), "punishment": self.policy.snapshot()})
        return bid

    def state_snapshots(self):
        return {a: state.snapshot(self) for a, state in self.selfish.states.items()}

    def terminal_state(self):
        terminal = super().terminal_state()
        states = self.state_snapshots()
        terminal.update(private_states=states, pending_publication_window=self.window,
            reaction_queue=list(self.selfish.pending),
            target_private_chain=list(self.selfish.states["target"].private_chain) if "target" in states else [],
            abandoned_private=sorted(b for s in self.selfish.states.values() for b in s.abandoned_blocks))
        active = {b for s in self.selfish.states.values() for b in s.private_chain}
        for branch in terminal["alternative_branches"]:
            tip = branch["tip"]
            branch["active_target_private"] = tip in terminal["target_private_chain"]
            if branch["visibility"] == "private":
                branch.update(private_actor=self.blocks[tip].owner_id, active_selfish_private=tip in active)
        if isinstance(self.punishment, OstracismPolicy):
            self.punishment.terminal_diagnostics(terminal)
        unresolved = bool(terminal["alternative_branches"] or self.policy.active or self.window or self.selfish.pending)
        terminal["boundary"].update(method="common-persistent-complete-frontier-v2", potentially_material=unresolved,
            actor_payoff_bounds={a: [0., 1.] for a in self.miners} if unresolved else None,
            future_reorganization_excluded=False if unresolved else None,
            private_leads={a: s["lead_relative_to_public_height"] for a, s in states.items()})
        return terminal

    def report(self, status="COMPLETE", error=None):
        actors = {}
        for actor, miner in self.miners.items():
            accepted = self.rewards[actor]
            orphaned = sum(b.owner_id == actor and b.id in self.public and not b.canonical for b in self.blocks.values())
            hidden = sum(b.owner_id == actor and b.id not in self.public for b in self.blocks.values())
            payoff = accepted/self.public_height if self.public_height else None
            actors[actor] = {"role": miner.role, "hash_power": miner.hash_power, "discovered": self.discovered[actor],
                "accepted": accepted, "orphaned": orphaned, "public_noncanonical": orphaned, "unresolved": hidden,
                "payoff": payoff, "normalized_revenue": payoff/miner.hash_power if payoff is not None else None}
        result = {"identity": self.identity, "condition_id": digest(self.identity), "network_version": NETWORK_VERSION,
            "model_version": self.model_version, "punishment_rule": self.rule.punishment_rule if self.enabled else None,
            "counter_fork_k": self.rule.counter_fork_k if self.enabled else None, "population": asdict(self.p),
            "status": status, "error": error, "strategy": self.strategy, "label": "flagged" if self.enabled else "unflagged",
            "active_coalition": sorted(self.active), "events": self.events, "accepted_blocks": self.public_height,
            "actors": actors, "member_opportunities": dict(self.opportunities), "member_activations": dict(self.activations),
            "natural_pairs": dict(self.natural_pairs), "episodes": list(self.punishment.history) if self.punishment else [],
            "selfish_reactions": list(self.selfish.history), "selfish_actor_order": list(self.selfish.states),
            "publication_batches": list(self.publication_log), "public_events": list(self.public_events),
            "reorganizations": list(self.reorganizations), "terminal": self.terminal_state(),
            "rng": self.rng_snapshot(), "scripted_discoveries": list(self.scripted_discoveries)}
        if self.trace is not None:
            result["trace"] = self.trace
        if self.production:
            result.pop("public_events")
            result["recording_mode"] = "production-v2"
        return result
