"""Persistent post-activation ancestry rejection, with no capitulation rule."""
from dataclasses import dataclass

MODEL_VERSION = "persistent-ignore-v1"


@dataclass(frozen=True)
class OstracismSpec:
    punishment_rule: str = "ignore"
    counter_fork_k: None = None

    def __post_init__(self):
        if self.punishment_rule != "ignore":
            raise ValueError("only the individual ignore rule is supported")
        if self.counter_fork_k is not None:
            raise ValueError("ignore has no counter_fork_k or capitulation depth")


def ordered(ids):
    return sorted(ids, key=lambda b: -1 if b is None else b)


class OstracismPolicy:
    """Attach at the current publication boundary; existing public history stays.

    Normal conditional runs attach at genesis (publication sequence zero).
    Attaching to an existing tree is useful for deterministic activation tests;
    standard conditional checkpoint validation requires the genesis boundary.
    The first-rejected-ancestor index is propagated once per public block. No
    root-by-root ancestry search is performed at mining/fork-choice time.
    """
    def __init__(self, sim, armed):
        self.sim = sim
        self.armed = bool(armed)
        self.activation_publication_sequence = sim.publication_sequence if armed else None
        self.rejected_roots = set()
        self.minimal_rejected_roots = set()
        self.rejected_by = {}
        self.eligible_frontier = set(sim.public_tips) or {None}
        self.best_eligible_tips = set(sim.longest_tips) or {None}
        self.best_eligible_height = sim.public_height
        self.competing_rejected_roots = set()
        self.history = []

    @property
    def active(self):
        # Immediate conflicts may end; eligibility enforcement never disarms.
        return bool(self.competing_rejected_roots)

    def eligible(self, sim, actor, visible):
        if not self.armed or actor not in sim.active:
            return None
        # The reduced propagation window hides at most one latest block. Its
        # eligible parent is sufficient as a fallback, even far behind the
        # global public frontier. Avoid scanning every old acceptable block.
        choices = self.best_eligible_tips | {
            sim.blocks[b].parent_id for b in self.best_eligible_tips if b is not None}
        return [b for b in choices if b is None or b in visible]

    def on_publication(self, sim, published):
        for bid in published:
            block = sim.blocks[bid]
            root = self.rejected_by.get(block.parent_id)
            if (self.armed and block.owner_id == "target"
                    and block.publication_sequence > self.activation_publication_sequence):
                self.rejected_roots.add(bid)
                if root is None:
                    self.minimal_rejected_roots.add(bid)
                    root = bid
                self.history.append({"outcome": "REJECTED_TARGET_ROOT", "root": bid,
                    "first_rejected_ancestor": root, "publication_sequence": block.publication_sequence,
                    "release_batch": block.release_batch})
                for actor in sim.active:
                    sim.activations[actor] += 1
            if root is not None:
                self.rejected_by[bid] = root
            else:
                self.eligible_frontier.discard(block.parent_id)
                self.eligible_frontier.add(bid)
                self.best_eligible_tips.discard(block.parent_id)
                if block.height > self.best_eligible_height:
                    self.best_eligible_height = block.height
                    self.best_eligible_tips = {bid}
                elif block.height == self.best_eligible_height:
                    self.best_eligible_tips.add(bid)
        competing = {self.rejected_by[b] for b in sim.longest_tips if b in self.rejected_by}
        for root in sorted(competing - self.competing_rejected_roots):
            self.history.append({"outcome": "CONFLICT_OPENED", "root": root,
                                 "publication_sequence": sim.publication_sequence})
        for root in sorted(self.competing_rejected_roots - competing):
            self.history.append({"outcome": "CONFLICT_NO_LONGER_LEADING", "root": root,
                                 "publication_sequence": sim.publication_sequence})
        self.competing_rejected_roots = competing

    def snapshot(self):
        return {"punishment_rule": "ignore", "armed": self.armed,
            "activation_publication_sequence": self.activation_publication_sequence,
            "rejected_roots": sorted(self.rejected_roots),
            "minimal_rejected_roots": sorted(self.minimal_rejected_roots),
            "competing_rejected_roots": sorted(self.competing_rejected_roots),
            "conflict_active": self.active,
            "eligible_public_frontier": ordered(self.eligible_frontier),
            "rejected_public_frontier": sorted(b for b in self.sim.public_tips if b in self.rejected_by),
            "best_eligible_height": self.best_eligible_height,
            "reference_rejected": self.sim.reference_tip in self.rejected_by,
            "reference_height_minus_best_eligible_height": self.sim.public_height - self.best_eligible_height}

    def terminal_diagnostics(self, terminal):
        """Include eligible interior prefixes, which need not be public leaves."""
        sim = self.sim
        frontier = []
        for tip in ordered(self.eligible_frontier):
            ancestor, path = sim._branch(tip)
            frontier.append({"tip": tip, "height": sim.height(tip), "common_ancestor": ancestor,
                "common_ancestor_height": sim.height(ancestor), "path": path,
                "canonical_blocks_exposed": sim.public_height - sim.height(ancestor)})
        terminal["ostracism_eligible_frontier"] = frontier
        for branch in terminal["alternative_branches"]:
            # Hidden target blocks do not offend until published. Public
            # ancestry can already make a hidden descendant unacceptable.
            tip = branch["tip"]
            while tip is not None and tip not in sim.public:
                tip = sim.blocks[tip].parent_id
            root = self.rejected_by.get(tip)
            branch["first_rejected_public_ancestor"] = root
            branch["eligible_by_published_ancestry"] = root is None
        boundary = terminal["boundary"]
        boundary["method"] = "ostracism-complete-frontier-conservative-v1"
        boundary["max_exposed_canonical_blocks"] = max(
            boundary["max_exposed_canonical_blocks"],
            max((b["canonical_blocks_exposed"] for b in frontier), default=0))
        boundary["reference_rejected_by_active_coalition"] = sim.reference_tip in self.rejected_by
        boundary["best_eligible_height"] = self.best_eligible_height
        boundary["reference_height_minus_best_eligible_height"] = sim.public_height - self.best_eligible_height
