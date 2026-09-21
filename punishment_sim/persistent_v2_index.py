"""Exact append-only tree/height indexes; no fork pruning or stochastic choices."""
from collections import defaultdict


class PublicVisibility:
    def __init__(self, public, hidden):
        self.public, self.hidden = public, hidden

    def __contains__(self, bid):
        return bid in self.public and bid not in self.hidden

    def __iter__(self):
        return (b for b in self.public if b not in self.hidden)


class HeightIndex:
    def __init__(self):
        self.levels = defaultdict(set)
        self.maximum = 0

    def add(self, bid, height):
        self.levels[height].add(bid)
        self.maximum = max(self.maximum, height)

    def best(self, visible):
        height = self.maximum
        while height >= 0:
            choices = [b for b in self.levels.get(height, ()) if b is None or b in visible]
            if choices:
                return sorted(choices, key=lambda b: -1 if b is None else b)
            height -= 1
        return []


class AncestryIndex:
    def __init__(self, blocks):
        self.blocks, self.jumps = blocks, {None: ()}

    def add(self, bid):
        if bid in self.jumps:
            return
        missing, node = [], bid
        while node not in self.jumps:
            missing.append(node)
            node = self.blocks[node].parent_id
        for node in reversed(missing):
            parent = self.blocks[node].parent_id
            jumps = [parent]
            level = 0
            while jumps[level] is not None and level < len(self.jumps[jumps[level]]):
                jumps.append(self.jumps[jumps[level]][level])
                level += 1
            self.jumps[node] = tuple(jumps)

    def descends(self, bid, ancestor):
        height = self.blocks[bid].height if bid is not None else 0
        target_height = self.blocks[ancestor].height if ancestor is not None else 0
        if height < target_height:
            return False
        self.add(bid)
        distance, level = height-target_height, 0
        while distance:
            if distance & 1:
                bid = self.jumps[bid][level]
            distance >>= 1
            level += 1
        return bid == ancestor


def initialize_indexes(sim):
    sim.ancestry_index = AncestryIndex(sim.blocks)
    sim.public_index, sim.acceptable_index = HeightIndex(), HeightIndex()
    sim.public_index.add(None, 0)
    sim.acceptable_index.add(None, 0)


def index_publication(sim, published):
    rejected = getattr(sim.punishment, "rejected_by", {})
    for bid in published:
        sim.ancestry_index.add(bid)
        sim.public_index.add(bid, sim.height(bid))
        if bid not in rejected:
            sim.acceptable_index.add(bid, sim.height(bid))


def advance_frontier(sim, ids):
    """Compute the new maximum before mutation; update leaves in place afterward."""
    maximum = max(sim.public_height, max(sim.height(b) for b in ids))
    longest = {b for b in ids if sim.height(b) == maximum}
    if maximum == sim.public_height:
        longest.update(sim.longest_tips)
    sim._check_target_tips(longest)
    sim.public.update(ids)
    sim.public_tips.update(ids)
    sim.public_tips.difference_update(sim.blocks[b].parent_id for b in ids)
    sim.public_height, sim.longest_tips = maximum, longest
