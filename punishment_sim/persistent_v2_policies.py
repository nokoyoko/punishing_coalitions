"""V2-only policies. Historical v1 implementations stay unchanged."""
from .persistent import CounterForkPolicy as HistoricalCounterForkPolicy, Episode
from .persistent_v2_index import HeightIndex


class CounterForkPolicy(HistoricalCounterForkPolicy):
    """Maximum non-coalition, non-target depth along a defending path."""
    def _refresh_index(self, sim):
        e = self.episode
        self.defending_depth = {e.trigger: 0}
        self.defending_maximum = sim.height(e.trigger)
        self.counter_index = HeightIndex()
        pending = [e.anchor]
        while pending:
            bid = pending.pop()
            if bid == e.trigger:
                continue
            if bid is None or bid in sim.public:
                self.counter_index.add(bid, sim.height(bid))
                pending.extend(sim.children[bid])

    def eligible(self, sim, actor, visible):
        if self.episode is None or actor not in sim.active:
            return None
        return self.counter_index.best(visible)

    def on_publication(self, sim, published):
        if not self.armed:
            return
        qualifying = [b for b in published if sim.blocks[b].owner_id == "target"
                      and any(sim.descends(t, b) for t in sim.longest_tips)]
        for bid in qualifying:
            refresh = self.episode.refresh_count+1 if self.episode else 0
            if self.episode:
                self.finish("REFRESHED")
            b = sim.blocks[bid]
            self.episode = Episode(self.next_episode, bid, b.parent_id, b.publication_sequence,
                                   b.height, refresh_count=refresh)
            self.next_episode += 1
            for actor in sim.active:
                sim.activations[actor] += 1
            self._refresh_index(sim)
        e = self.episode
        if e is None:
            return
        for bid in published:
            b = sim.blocks[bid]
            if sim.descends(bid, e.trigger):
                self.defending_maximum = max(self.defending_maximum, b.height)
                if bid != e.trigger:
                    # Ancestral publication order guarantees the parent entry.
                    increment = b.owner_id != "target" and b.owner_id not in sim.active
                    self.defending_depth[bid] = self.defending_depth[b.parent_id] + int(increment)
                    e.depth = max(e.depth, self.defending_depth[bid])
                    e.defended_height = max(e.defended_height, b.height)
            elif sim.descends(bid, e.anchor):
                self.counter_index.add(bid, b.height)
        if not sim.descends(sim.reference_tip, e.trigger) and sim.public_height > self.defending_maximum:
            self.finish("SUCCEEDED")
        elif e.depth >= self.rule.counter_fork_k:
            self.finish("CAPITULATED")


class PettyPolicy:
    """Reject a target-owned *tip* only in an eligible equal-height competition."""
    def __init__(self, sim):
        self.sim, self.history = sim, []
        self.race = None

    @property
    def active(self):
        return self.race is not None

    @staticmethod
    def target_tip(sim, tips):
        targets = [b for b in tips if b is not None and sim.blocks[b].owner_id == "target"]
        sim._check_target_tips(tips)
        return targets[0] if len(targets) == 1 and len(tips) > 1 else None

    def is_punishing(self, actor, visible):
        return actor in self.sim.active and self.target_tip(self.sim, self.sim.public_index.best(visible)) is not None

    def restrict(self, actor, tips):
        target = self.target_tip(self.sim, tips) if actor in self.sim.active else None
        return [b for b in tips if b != target] if target is not None else tips

    def on_publication(self, sim, published):
        tips = sorted(sim.longest_tips)
        target = self.target_tip(sim, tips)
        race = {"target_tip": target, "tips": tips} if target is not None else None
        if race == self.race:
            return
        if self.race is not None:
            self.history.append({"outcome": "PETTY_RACE_CLOSED", **self.race,
                "discovery_event": sim.events, "publication_sequence": sim.publication_sequence})
        self.race = race
        if race is not None:
            self.history.append({"outcome": "PETTY_RACE_OPENED", **race,
                "discovery_event": sim.events, "publication_sequence": sim.publication_sequence})
            for actor in sim.active:
                sim.activations[actor] += 1

    def snapshot(self):
        return {"punishment_rule": "petty", "active_members": sorted(self.sim.active), "race": self.race}
