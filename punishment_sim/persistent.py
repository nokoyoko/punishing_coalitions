"""Versioned persistent public forks. The historical v4 engines are untouched.

See docs/persistent_counter_fork.md for publication, target-strategy, visibility,
reference-chain and finite-horizon conventions. No simulation runs on import.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
import random
from typing import Protocol

from .coalition import Population, OCEANIC_RESIDUAL_ID
from .ostracism import OstracismSpec, OstracismPolicy, MODEL_VERSION as IGNORE_MODEL_VERSION
from .selfish_counter import (SelfishCounterSpec, SelfishCounterPolicy, SelfishStateError,
                             MODEL_VERSION as SELFISH_MODEL_VERSION, REACTION_ORDER, PROPAGATION)
from .selfish_strategy import release_plan

MODEL_VERSION = "persistent-counter-fork-v1"


class UnsupportedStateError(RuntimeError):
    """No scientifically specified transition exists; never guess a policy."""


@dataclass(frozen=True)
class PunishmentSpec:
    punishment_rule: str = "counter_fork"
    counter_fork_k: int = 1

    def __post_init__(self):
        if self.punishment_rule != "counter_fork":
            raise ValueError("only the individual counter_fork rule is supported")
        if type(self.counter_fork_k) is not int or self.counter_fork_k < 1:
            raise ValueError("counter_fork_k must be a positive integer")


def model_version(rule):
    if isinstance(rule, SelfishCounterSpec):
        return SELFISH_MODEL_VERSION
    if isinstance(rule, OstracismSpec):
        return IGNORE_MODEL_VERSION
    if isinstance(rule, PunishmentSpec):
        return MODEL_VERSION
    raise ValueError("rule must be a PunishmentSpec, OstracismSpec or SelfishCounterSpec")


def identity(population, rule):
    return {"model_version": model_version(rule), **asdict(rule), "population": asdict(population)}


def configuration_id(population, rule):
    return hashlib.sha256(json.dumps(identity(population, rule), sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()[:24]


def mining_cache_key(population, repetition, strategy, flagged, coalition, rule):
    return (model_version(rule), rule.punishment_rule, rule.counter_fork_k,
            population.target_hash_power, population.candidates, population.gamma,
            population.natural_fork_rate, population.target_accepted_blocks,
            population.seed + repetition, strategy, bool(flagged and coalition),
            tuple(sorted(coalition)))


@dataclass
class Block:
    id: int
    parent_id: int | None
    height: int
    owner_id: str
    discovery_sequence: int
    initially_withheld: bool
    publication_sequence: int | None = None
    release_batch: int | None = None
    publication_kind: str | None = None
    canonical: bool = False


@dataclass
class Episode:
    episode_id: int
    trigger: int
    anchor: int | None
    publication_index: int
    defended_height: int
    depth: int = 0
    refresh_count: int = 0


class ForkPolicy(Protocol):
    """Policies select parents/react to public facts; they never assign rewards.

    A future composite must specify precedence explicitly before implementing
    this contract. Construction currently rejects combined rules.
    """
    history: list
    armed: bool
    @property
    def active(self): ...
    def snapshot(self): ...
    def eligible(self, sim, actor, visible): ...
    def on_publication(self, sim, published): ...


class CounterForkPolicy:
    def __init__(self, rule, armed):
        self.rule = rule
        self.armed = armed
        self.episode: Episode | None = None
        self.history = []
        self.next_episode = 1

    @property
    def active(self):
        return self.episode is not None

    def snapshot(self):
        return asdict(self.episode) if self.episode else None

    def eligible(self, sim, actor, visible):
        e = self.episode
        if not e or actor not in sim.active:
            return None
        return [b for b in sim.subtree(e.anchor)
                if (b is None or b in visible) and not sim.descends(b, e.trigger)]

    def finish(self, outcome):
        self.history.append({**asdict(self.episode), "outcome": outcome})
        self.episode = None

    def on_publication(self, sim, published):
        if not self.armed:
            return
        # Relevance is evaluated against the complete post-batch public tree.
        # A newly public target ancestor of a longest tip is relevant even if
        # another block in the same release is now that tip.
        qualifying = [b for b in published if sim.blocks[b].owner_id == "target"
                      and any(sim.descends(t, b) for t in sim.longest_tips)]
        for t in qualifying:
            refresh = self.episode.refresh_count + 1 if self.episode else 0
            if self.episode:
                self.finish("REFRESHED")
            block = sim.blocks[t]
            self.episode = Episode(self.next_episode, t, block.parent_id,
                                   block.publication_sequence, block.height,
                                   refresh_count=refresh)
            self.next_episode += 1
            for j in sim.active:
                sim.activations[j] += 1
        e = self.episode
        if not e:
            return
        # High-water height, not a count of siblings, unrelated publications,
        # discoveries, reference-chain adoptions, or counter-fork work.
        for bid in published:
            b = sim.blocks[bid]
            if (b.publication_sequence > e.publication_index
                    and b.owner_id != "target" and sim.descends(bid, e.trigger)
                    and b.height > e.defended_height):
                e.depth += b.height - e.defended_height
                e.defended_height = b.height
        defended = max(sim.height(t) for t in sim.public_tips if sim.descends(t, e.trigger))
        if not sim.descends(sim.reference_tip, e.trigger) and sim.public_height > defended:
            self.finish("SUCCEEDED")
        elif e.depth >= self.rule.counter_fork_k:
            self.finish("CAPITULATED")


class PersistentSimulation:
    def __init__(self, population: Population, strategy: str, flagged: bool,
                 active_coalition=(), rule=None, max_events=None, trace_mode=False):
        if strategy not in ("honest", "selfish"):
            raise ValueError("target strategy must be honest or selfish")
        if type(flagged) is not bool:
            raise ValueError("flagged must be boolean")
        if type(population.target_accepted_blocks) is not int or population.target_accepted_blocks < 1:
            raise ValueError("canonical horizon must be a positive integer")
        if max_events is not None and (type(max_events) is not int or max_events < 1):
            raise ValueError("max_events must be a positive integer")
        self.p = population
        self.rule = rule if rule is not None else PunishmentSpec()
        self.model_version = model_version(self.rule)
        self.strategy, self.flagged = strategy, flagged
        self.active = frozenset(active_coalition)
        if not self.active <= {i for i, _ in population.candidates}:
            raise ValueError("active members must be explicit candidates")
        self.miners = {m.id: m for m in population.miners}
        self.blocks = {}
        self.children = defaultdict(set)
        self.public = set()
        self.public_tips = set()
        self.longest_tips = set()
        self.public_height = 0
        self.reference_tip = None
        self.canonical_chain = []
        self.rewards = Counter()
        self.discovered = Counter()
        self.private = []
        self.abandoned_private = set()
        self.pending = None
        self.events = self.publication_sequence = self.release_batch = 0
        self.reorganizations = []
        self.publication_log = []
        self.natural_pairs = Counter()
        self.activations = Counter()
        self.opportunities = Counter()
        self.policy = (SelfishCounterPolicy(self, flagged and bool(self.active)) if isinstance(self.rule, SelfishCounterSpec)
                       else OstracismPolicy(self, flagged and bool(self.active)) if isinstance(self.rule, OstracismSpec)
                       else CounterForkPolicy(self.rule, flagged and bool(self.active)))
        self.max_events = max_events if max_events is not None else max(1000, 100 * population.target_accepted_blocks)
        self.trace = [] if trace_mode else None
        self.rng = self._rng("discoveries")
        self.tie_rng = self._rng("ties")
        self.natural_rng = self._rng("natural")

    def _rng(self, name):
        digest = hashlib.sha256(f"{self.model_version}:{self.p.seed}:{name}".encode()).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    def height(self, bid):
        return self.blocks[bid].height if bid is not None else 0

    def descends(self, bid, ancestor):
        target_height = self.height(ancestor)
        while self.height(bid) > target_height:
            bid = self.blocks[bid].parent_id
        return bid == ancestor

    def subtree(self, anchor):
        pending = [anchor]
        while pending:
            bid = pending.pop()
            yield bid
            pending.extend(sorted(self.children[bid], reverse=True))

    def discover(self, owner, parent=None, withheld=False, kind="ordinary"):
        """One real discovery; also usable for deterministic scripted fixtures."""
        if owner not in self.miners or (parent is not None and parent not in self.blocks):
            raise ValueError("unknown owner or parent")
        if parent is not None and parent not in self.public and self.blocks[parent].owner_id != owner:
            raise ValueError("cannot mine on another actor's hidden block")
        if withheld and isinstance(self.rule, SelfishCounterSpec):
            self.policy.check_private_parent(owner, parent)
        self.events += 1
        bid = len(self.blocks) + 1
        self.blocks[bid] = Block(bid, parent, self.height(parent) + 1, owner, self.events, withheld)
        self.children[parent].add(bid)
        self.discovered[owner] += 1
        if withheld and isinstance(self.rule, SelfishCounterSpec):
            self.policy.record_private(owner, bid)
        if not withheld:
            self.publish([bid], kind)
        return bid

    def publish(self, ids, kind="ordinary"):
        """Atomic parent-before-child release; no discovery or RNG draw here."""
        ids = list(ids)
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate ID inside publication batch")
        known = set()
        new = []
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
        # Check the unsupported state before mutating the public ledger.
        prospective_tips = (self.public_tips | set(new)) - {self.blocks[b].parent_id for b in new}
        max_height = max(self.height(t) for t in prospective_tips)
        longest = {t for t in prospective_tips if self.height(t) == max_height}
        self._check_target_tips(longest)
        self.release_batch += 1
        for bid in new:
            b = self.blocks[bid]
            self.publication_sequence += 1
            b.publication_sequence = self.publication_sequence
            b.release_batch = self.release_batch
            b.publication_kind = kind
        self.public.update(new)
        self.private = [b for b in self.private if b not in known]
        self.abandoned_private.difference_update(known)
        self.public_tips = prospective_tips
        self.longest_tips, self.public_height = longest, max_height
        # Reference choice is sticky at equal height; otherwise earliest public
        # highest tip. Actor-specific mining choices remain independent of it.
        chosen = self.reference_tip if self.reference_tip in longest else min(
            longest, key=lambda b: (self.blocks[b].publication_sequence, b))
        self._adopt(chosen)
        self.publication_log.append({"batch": self.release_batch, "blocks": new,
                                     "kind": kind, "discovery_event": self.events})
        self.policy.on_publication(self, new)

    def _adopt(self, tip):
        old, new = self.reference_tip, tip
        removed, added = [], []
        while old != new:
            if self.height(old) >= self.height(new):
                removed.append(old)
                old = self.blocks[old].parent_id
            else:
                added.append(new)
                new = self.blocks[new].parent_id
        for bid in removed:
            self.blocks[bid].canonical = False
            self.rewards[self.blocks[bid].owner_id] -= 1
        if removed:
            del self.canonical_chain[-len(removed):]
        for bid in reversed(added):
            self.blocks[bid].canonical = True
            self.rewards[self.blocks[bid].owner_id] += 1
            self.canonical_chain.append(bid)
        if removed:
            self.reorganizations.append({"event": self.events, "removed": removed,
                                         "added": list(reversed(added)), "common_ancestor": old})
        self.reference_tip = tip

    def _check_target_tips(self, tips):
        if sum(t is not None and self.blocks[t].owner_id == "target" for t in tips) > 1:
            raise UnsupportedStateError("multiple simultaneous target-owned competing tips")

    def branch_probabilities(self, tips):
        tips = sorted(tips, key=lambda b: -1 if b is None else b)
        if not tips or len({self.height(t) for t in tips}) != 1:
            raise ValueError("tie candidates must be nonempty and equal height")
        self._check_target_tips(tips)
        if len(tips) == 1:
            return {tips[0]: 1.0}
        target = [t for t in tips if t is not None and self.blocks[t].owner_id == "target"]
        if target:
            return {t: self.p.gamma if t == target[0] else (1-self.p.gamma)/(len(tips)-1) for t in tips}
        return {t: 1/len(tips) for t in tips}

    def eligible_tips(self, actor, hidden=None):
        # Only a single most-recent publication can be delayed by the reduced
        # natural-fork window. Policies still share the public announcement log.
        selected = self.policy.eligible(self, actor, self.public)
        if selected is not None and hidden is not None:
            selected = [b for b in selected if b != hidden]
        if selected is None:
            if hidden is None:
                selected = list(self.longest_tips) or [None]
            else:
                selected = list((self.public_tips - {hidden}) | {self.blocks[hidden].parent_id})
        highest = max(self.height(b) for b in selected)
        return sorted((b for b in selected if self.height(b) == highest), key=lambda b: -1 if b is None else b)

    def choose_parent(self, actor, hidden=None):
        tips = self.eligible_tips(actor, hidden)
        return self.choose_among_tips(actor, tips)

    def choose_among_tips(self, actor, tips):
        tips = sorted(tips, key=lambda b: -1 if b is None else b)
        probabilities = self.branch_probabilities(tips)
        owned = [t for t in tips if t is not None and self.blocks[t].owner_id == actor]
        if actor != OCEANIC_RESIDUAL_ID and owned:
            # If it owns several eligible tips, retain its most recent own tip.
            return max(owned, key=lambda t: self.blocks[t].publication_sequence)
        if len(tips) == 1:
            return tips[0]
        draw = self.tie_rng.random()
        total = 0.0
        for tip, probability in probabilities.items():
            total += probability
            if draw < total:
                return tip
        return tips[-1]

    def _draw(self):
        draw = self.rng.random()
        total = 0.0
        for m in self.p.miners:
            total += m.hash_power
            if draw < total:
                return m.id
        return OCEANIC_RESIDUAL_ID

    def _target_response(self, newly_public):
        plan = release_plan(self, self.private, newly_public)
        if plan is None:
            return
        if plan.action == "ABANDON":
            self.abandoned_private.update(self.private)
            self.private.clear()
            return
        self.publish(plan.blocks, "target_selfish_release")

    def step(self, discoverer=None):
        if isinstance(self.rule, SelfishCounterSpec):
            return self.policy.step(discoverer)
        actor = self._draw() if discoverer is None else discoverer
        if actor not in self.miners:
            raise ValueError("unknown discoverer")
        window = self.pending
        self.pending = None
        had_private = bool(self.private)
        had_tie = len(self.longest_tips) > 1
        punishing = self.policy.active and actor in self.active
        if self.policy.active:
            for j in self.active:
                self.opportunities[j] += 1
        if actor == "target" and self.strategy == "selfish":
            if self.private:
                bid = self.discover(actor, self.private[-1], withheld=True)
                self.private.append(bid)
            else:
                parent = self.choose_parent(actor)
                # Preserve the current target convention of publicly resolving
                # a visible tie; isolated discoveries begin an unbounded fork.
                bid = self.discover(actor, parent, withheld=not had_tie,
                                    kind="target_tie_resolution")
                if not had_tie:
                    self.private.append(bid)
        else:
            hidden = window if window is not None and (
                actor == OCEANIC_RESIDUAL_ID or self.blocks[window].owner_id != actor) else None
            parent = self.choose_parent(actor, hidden)
            natural = (not punishing and hidden is not None
                       and parent == self.blocks[hidden].parent_id)
            kind = self.rule.punishment_rule if punishing else "natural_fork" if natural else "ordinary"
            bid = self.discover(actor, parent, kind=kind)
            if natural:
                self.natural_pairs["--".join(sorted((actor, self.blocks[hidden].owner_id)))] += 1
            self._target_response([bid])
            if (window is None and not had_private and not had_tie
                    and self.longest_tips == {bid}
                    and self.natural_rng.random() < self.p.natural_fork_rate):
                self.pending = bid
        if self.trace is not None:
            self.trace.append({"event": self.events, "discoverer": actor, "block": bid,
                               "reference_tip": self.reference_tip, "private": list(self.private),
                               "episode": self.policy.snapshot(),
                               "rewards": dict(self.rewards)})
        return bid

    def _branch(self, tip):
        path = []
        while tip is not None and not self.blocks[tip].canonical:
            path.append(tip)
            tip = self.blocks[tip].parent_id
        return tip, list(reversed(path))

    def terminal_state(self):
        hidden = set(self.blocks) - self.public
        private_tips = hidden - {self.blocks[b].parent_id for b in hidden}
        alternatives = []
        frontier_blocks = {}
        for visibility, tips in (("public", self.public_tips - {self.reference_tip}), ("private", private_tips)):
            for tip in sorted(tips):
                ancestor, path = self._branch(tip)
                for b in path:
                    frontier_blocks[b] = asdict(self.blocks[b])
                alternatives.append({"tip": tip, "visibility": visibility,
                    "common_ancestor": ancestor, "common_ancestor_height": self.height(ancestor),
                    "path": path, "height": self.height(tip),
                    "canonical_blocks_exposed": self.public_height-self.height(ancestor),
                    "active_target_private": tip in self.private})
        unresolved = bool(alternatives or self.policy.active or self.pending)
        # Attribute the exposed canonical suffix to its actual independent
        # owners, without assuming that any of these blocks are finalized.
        ancestor_heights = {x["common_ancestor_height"] for x in alternatives}
        prefix, at_height = Counter(), {0: Counter()}
        for height, bid in enumerate(self.canonical_chain, 1):
            prefix[self.blocks[bid].owner_id] += 1
            if height in ancestor_heights:
                at_height[height] = prefix.copy()
        for branch in alternatives:
            before = at_height[branch["common_ancestor_height"]]
            branch["canonical_rewards_exposed"] = {
                actor: self.rewards[actor] - before[actor] for actor in self.miners}
        terminal = {"reference_tip": self.reference_tip, "reference_height": self.public_height,
            "canonical_chain": list(self.canonical_chain),
            "canonical_blocks": [asdict(self.blocks[b]) for b in self.canonical_chain],
            "public_frontier": sorted(self.public_tips), "private_frontier": sorted(private_tips),
            "frontier_blocks": [frontier_blocks[b] for b in sorted(frontier_blocks)],
            "alternative_branches": alternatives, "target_private_chain": list(self.private),
            "abandoned_private": sorted(self.abandoned_private), "pending_visibility_block": self.pending,
            "retaliation": self.policy.snapshot(),
            "boundary": {"method": "complete-frontier-conservative-v1",
                "potentially_material": unresolved,
                "max_exposed_canonical_blocks": max((x["canonical_blocks_exposed"] for x in alternatives), default=0),
                "future_reorganization_excluded": False if unresolved else None,
                "actor_payoff_bounds": {a: [0.0, 1.0] for a in self.miners} if unresolved else None,
                "interpretation": "Unresolved branches have no proven small future-payoff bound; intervals are worst-case bounds, not confidence intervals."}}
        if isinstance(self.rule, (OstracismSpec, SelfishCounterSpec)):
            self.policy.terminal_diagnostics(terminal)
        return terminal

    def report(self, status="COMPLETE", error=None):
        actors = {}
        for actor, miner in self.miners.items():
            canonical = self.rewards[actor]
            noncanonical = sum(b.owner_id == actor and b.id in self.public and not b.canonical for b in self.blocks.values())
            private = sum(b.owner_id == actor and b.id not in self.public for b in self.blocks.values())
            payoff = canonical/self.public_height if self.public_height else None
            actors[actor] = {"role": miner.role, "hash_power": miner.hash_power,
                "discovered": self.discovered[actor], "accepted": canonical,
                "orphaned": noncanonical, "public_noncanonical": noncanonical,
                "unresolved": private, "payoff": payoff,
                "normalized_revenue": payoff/miner.hash_power if payoff is not None else None}
        result = {"model_version": self.model_version, **asdict(self.rule),
            "configuration_id": configuration_id(self.p, self.rule), "population": asdict(self.p),
            "status": status, "error": error, "strategy": self.strategy,
            "label": "flagged" if self.flagged else "unflagged", "active_coalition": sorted(self.active),
            "events": self.events, "accepted_blocks": self.public_height, "actors": actors,
            "member_opportunities": dict(self.opportunities), "member_activations": dict(self.activations),
            "natural_pairs": dict(self.natural_pairs), "episodes": list(self.policy.history),
            "reorganizations": list(self.reorganizations), "publication_batches": list(self.publication_log),
            "terminal": self.terminal_state()}
        if self.trace is not None:
            result["trace"] = self.trace
        if isinstance(self.rule, SelfishCounterSpec):
            result.update(selfish_actor_order=list(self.policy.states), reaction_order=REACTION_ORDER,
                          propagation_convention=PROPAGATION, natural_events=list(self.policy.natural_events))
        return result

    def run(self):
        try:
            while self.public_height < self.p.target_accepted_blocks:
                if self.events >= self.max_events:
                    return self.report("INCOMPLETE_RESOURCE_LIMIT")
                self.step()
        except (UnsupportedStateError, SelfishStateError) as exc:
            return self.report("UNSUPPORTED_STATE", str(exc))
        # No finalization discoveries, forced releases, or policy transitions.
        return self.report()
