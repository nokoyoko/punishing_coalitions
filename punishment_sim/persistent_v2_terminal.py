"""Exact v2 terminal serialization without repeated shared-block conversion."""
from collections import Counter
from dataclasses import asdict
from .ostracism import OstracismSpec
from .selfish_counter import SelfishCounterSpec


def terminal_state(self):
    """Exact v2 terminal snapshot; serialize shared frontier blocks once.

    Paths remain explicit and ordered. The historical TreeEngine serializer
    stays available as the reference implementation. This function only reads
    the completed state; it caches nothing across calls or discoveries.
    """
    hidden = set(self.blocks) - self.public
    private_tips = hidden - {self.blocks[b].parent_id for b in hidden}
    alternatives = []
    frontier_blocks = set()
    for visibility, tips in (("public", self.public_tips - {self.reference_tip}), ("private", private_tips)):
        for tip in sorted(tips):
            ancestor, path = self._branch(tip)
            frontier_blocks.update(path)
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
        "frontier_blocks": [asdict(self.blocks[b]) for b in sorted(frontier_blocks)],
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
