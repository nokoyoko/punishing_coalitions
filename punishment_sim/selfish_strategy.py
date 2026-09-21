"""The existing persistent target's release rule, shared by every selfish actor.

Only the supplied actor's private chain and the public tree are inspected.
No strategy decision depends on another actor's unpublished discoveries.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReleasePlan:
    action: str
    blocks: tuple[int, ...]


def release_plan(sim, private_chain, newly_public):
    if not private_chain:
        return None
    tip = private_chain[-1]
    rivals = [t for t in sim.longest_tips if not sim.descends(tip, t)]
    if not rivals or not any(b in rivals for b in newly_public):
        return None
    rival_height = max(sim.height(t) for t in rivals)
    gap = sim.height(tip) - rival_height
    if gap < 0:
        return ReleasePlan("ABANDON", tuple(private_chain))
    released = (private_chain if gap <= 1 else
                [b for b in private_chain if sim.height(b) <= rival_height])
    return ReleasePlan("RELEASE", tuple(released)) if released else None
