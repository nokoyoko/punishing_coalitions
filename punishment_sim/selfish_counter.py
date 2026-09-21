"""Model A: independent full selfish state machines, no shared private chain."""
from dataclasses import dataclass, field

from .selfish_strategy import release_plan

MODEL_VERSION = "persistent-selfish-counter-v1"
REACTION_ORDER = "public-snapshot-rounds-population-order-v1"
PROPAGATION = "one-discovery-publication-bundle-window-v1"


@dataclass(frozen=True)
class SelfishCounterSpec:
    punishment_rule: str = "selfish"
    counter_fork_k: None = None

    def __post_init__(self):
        if self.punishment_rule != "selfish":
            raise ValueError("only the individual selfish rule is supported")
        if self.counter_fork_k is not None:
            raise ValueError("selfish counter-mining has no counter_fork_k")


class SelfishStateError(RuntimeError):
    """An invalid private-state/reaction transition cannot be treated as success."""


@dataclass
class SelfishState:
    actor_id: str
    private_chain: list[int] = field(default_factory=list)
    abandoned_blocks: list[int] = field(default_factory=list)
    released_blocks: list[int] = field(default_factory=list)
    exposed_tip: int | None = None

    def snapshot(self, sim):
        tip = self.private_chain[-1] if self.private_chain else None
        rivals = sorted(t for t in sim.longest_tips if tip is not None and not sim.descends(tip, t))
        exposed = self.exposed_tip in sim.longest_tips
        return {"actor_id": self.actor_id, "private_chain": list(self.private_chain),
            "private_fork_base": sim.blocks[self.private_chain[0]].parent_id if self.private_chain else None,
            "private_tip": tip, "private_tip_height": sim.height(tip),
            "private_block_count": len(self.private_chain),
            "lead_relative_to_public_height": sim.height(tip) - sim.public_height if tip is not None else 0,
            "competing_public_tips": rivals, "exposed_tip": self.exposed_tip,
            "exposure_is_leading": exposed, "released_blocks": list(self.released_blocks),
            "abandoned_private_blocks": list(self.abandoned_blocks),
            "phase": ("PRIVATE_WITH_PUBLIC_TIE" if self.private_chain and len(sim.longest_tips) > 1 else
                      "PRIVATE" if self.private_chain else "EXPOSED_RACE" if exposed and len(sim.longest_tips) > 1
                      else "PUBLIC")}


class SelfishCounterPolicy:
    """Strategy activation and deterministic coordination of public reactions.

    Coordination here is event scheduling, not pooled strategic information.
    Every release plan is computed by the same single-actor rule, using only
    that actor's own chain and an identical public snapshot for the round.
    """
    def __init__(self, sim, armed):
        self.sim = sim
        self.armed = bool(armed)
        actors = {"target"} if sim.strategy == "selfish" else set()
        if self.armed:
            actors.update(sim.active)
        self.states = {m.id: SelfishState(m.id) for m in sim.p.miners if m.id in actors}
        if self.armed:
            sim.activations.update({actor: 1 for actor in sim.active})
        self.history = []
        self.pending_publications = []
        self.processing = False
        self.window = None
        self.natural_events = []

    @property
    def active(self):
        return self.armed

    def eligible(self, sim, actor, visible):
        return None  # No rejected ancestry, coalition preference or pooled fork.

    def snapshot(self):
        return {"punishment_rule": "selfish", "armed": self.armed,
                "activation_event": 0 if self.armed else None,
                "active_members": sorted(self.sim.active) if self.armed else []}

    def record_private(self, owner, bid):
        self.states[owner].private_chain.append(bid)

    def check_private_parent(self, owner, parent):
        if owner not in self.states:
            raise ValueError("honest/neutral actor has no selfish private state")
        chain = self.states[owner].private_chain
        if chain and parent != chain[-1]:
            raise ValueError("a selfish actor must extend its own current private tip")
        if not chain and parent is not None and parent not in self.sim.public:
            raise ValueError("a new private chain must start on public history")

    def on_publication(self, sim, published):
        # Publication makes the blocks public to every state machine. Only the
        # actual owner's storage is updated; other private chains remain private.
        new = set(published)
        for actor, state in self.states.items():
            state.private_chain = [b for b in state.private_chain if b not in new]
            for bid in published:
                b = sim.blocks[bid]
                if b.owner_id == actor:
                    state.exposed_tip = bid
                    if b.initially_withheld:
                        state.released_blocks.append(bid)
        self.pending_publications.extend(published)
        if self.processing:
            return
        self.processing = True
        try:
            self._react()
        finally:
            self.processing = False

    def _react(self):
        sim = self.sim
        while self.pending_publications:
            observed = self.pending_publications
            self.pending_publications = []
            decisions = []
            for actor, state in self.states.items():
                plan = release_plan(sim, state.private_chain, observed)
                if plan is not None:
                    decisions.append({"actor_id": actor, "action": plan.action, "blocks": list(plan.blocks),
                                      "private_tip_before": state.private_chain[-1]})
            if not decisions:
                continue
            self.history.append({"outcome": "SELFISH_REACTION_ROUND", "round": len(self.history) + 1,
                "discovery_event": sim.events, "observed_publications": list(observed),
                "public_height": sim.public_height, "publication_sequence": sim.publication_sequence,
                "decisions": decisions})
            before = sum(len(s.private_chain) for s in self.states.values())
            # Plans are irrevocable within a round. New publications are queued
            # for the NEXT round, so a later actor cannot see an earlier plan
            # while choosing its own action for this same public snapshot.
            for decision in decisions:
                actor = decision["actor_id"]
                state = self.states[actor]
                if decision["action"] == "ABANDON":
                    state.abandoned_blocks.extend(state.private_chain)
                    state.private_chain.clear()
                else:
                    kind = "target_selfish_release" if actor == "target" else "member_selfish_release"
                    sim.publish(decision["blocks"], kind)
            if sum(len(s.private_chain) for s in self.states.values()) >= before:
                raise SelfishStateError("selfish reaction round made no finite private-state progress")

    def _honest_parent(self, actor, window):
        sim = self.sim
        if window is None:
            return sim.choose_parent(actor), None
        hidden = set(window["blocks"])
        if actor != "honest_residual":
            # An explicit publisher knows its own blocks and their ancestors.
            for bid in window["blocks"]:
                if sim.blocks[bid].owner_id == actor:
                    while bid in hidden:
                        hidden.remove(bid)
                        bid = sim.blocks[bid].parent_id
        if not hidden:
            return sim.choose_parent(actor), None
        visible = sim.public - hidden
        # Every hidden descendant is part of the same publication bundle; this
        # view is ancestry-closed. A private chain never enters the window.
        tips = (visible - {sim.blocks[b].parent_id for b in visible}) or {None}
        height = max(sim.height(b) for b in tips)
        tips = [b for b in tips if sim.height(b) == height]
        parent = sim.choose_among_tips(actor, tips)
        delayed = sorted(sim.longest_tips & hidden, key=lambda b: sim.blocks[b].publication_sequence)
        source = delayed[0] if delayed and sim.height(parent) < sim.public_height else None
        return parent, source

    def step(self, discoverer=None):
        sim = self.sim
        actor = sim._draw() if discoverer is None else discoverer
        if actor not in sim.miners:
            raise ValueError("unknown discoverer")
        window, self.window = self.window, None
        sim.pending = None
        start_sequence, start_height = sim.publication_sequence, sim.public_height
        start_batch = len(sim.publication_log)
        had_tie = len(sim.longest_tips) > 1
        had_private = any(s.private_chain for s in self.states.values())
        if self.active:
            for member in sim.active:
                sim.opportunities[member] += 1
        state = self.states.get(actor)
        if state is not None:
            if state.private_chain:
                bid = sim.discover(actor, state.private_chain[-1], withheld=True)
            else:
                parent = sim.choose_parent(actor)
                # Exactly the existing target discovery rule, generalized by ID.
                kind = "target_tie_resolution" if actor == "target" else "member_tie_resolution"
                bid = sim.discover(actor, parent, withheld=len(sim.longest_tips) <= 1, kind=kind)
        else:
            parent, delayed_source = self._honest_parent(actor, window)
            kind = "natural_fork" if delayed_source is not None else "ordinary"
            bid = sim.discover(actor, parent, kind=kind)
            if delayed_source is not None:
                owner = sim.blocks[delayed_source].owner_id
                sim.natural_pairs["--".join(sorted((actor, owner)))] += 1
                self.natural_events.append({"discovery_event": sim.events, "block": bid,
                    "delayed_tip": delayed_source, "delayed_publications": list(window["blocks"])})
        # This new model's one-discovery delay covers the complete public
        # discovery/reaction bundle. It can coexist with retained private leads;
        # withholding alone cannot create a propagation window or natural fork.
        if (window is None and not had_tie and bid in sim.public and sim.height(bid) > start_height
                and (not had_private or any(s.private_chain for s in self.states.values()))
                and sim.natural_rng.random() < sim.p.natural_fork_rate):
            published = [b for batch in sim.publication_log[start_batch:] for b in batch["blocks"]
                         if sim.blocks[b].publication_sequence > start_sequence]
            published.sort(key=lambda b: sim.blocks[b].publication_sequence)
            self.window = {"discovery_event": sim.events, "origin_block": bid, "blocks": published}
            sim.pending = bid
        if sim.trace is not None:
            sim.trace.append({"event": sim.events, "discoverer": actor, "block": bid,
                "reference_tip": sim.reference_tip, "selfish_states": self.state_snapshots(),
                "pending_publication_window": self.window, "rewards": dict(sim.rewards)})
        return bid

    def state_snapshots(self):
        return {a: state.snapshot(self.sim) for a, state in self.states.items()}

    def terminal_diagnostics(self, terminal):
        sim = self.sim
        terminal["selfish_states"] = self.state_snapshots()
        target = self.states.get("target")
        terminal["target_private_chain"] = list(target.private_chain) if target else []
        terminal["abandoned_private"] = sorted(b for s in self.states.values() for b in s.abandoned_blocks)
        terminal["pending_publication_window"] = self.window
        terminal["reaction_queue"] = list(self.pending_publications)
        active_private = {b for s in self.states.values() for b in s.private_chain}
        for branch in terminal["alternative_branches"]:
            tip = branch["tip"]
            branch["active_target_private"] = bool(target and tip in target.private_chain)
            if branch["visibility"] == "private":
                branch["private_actor"] = sim.blocks[tip].owner_id
                branch["active_selfish_private"] = tip in active_private
        unresolved = bool(terminal["alternative_branches"] or self.window or self.pending_publications)
        terminal["boundary"].update(method="multi-selfish-complete-frontier-conservative-v1",
            potentially_material=unresolved, future_reorganization_excluded=False if unresolved else None,
            actor_payoff_bounds={a: [0.0, 1.0] for a in sim.miners} if unresolved else None,
            actors_with_unpublished_private_blocks=[a for a, s in self.states.items() if s.private_chain],
            private_leads={a: s["lead_relative_to_public_height"] for a, s in terminal["selfish_states"].items()})
