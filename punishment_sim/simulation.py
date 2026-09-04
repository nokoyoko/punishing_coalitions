from __future__ import annotations

from collections import Counter, deque
import json
from pathlib import Path
from typing import Iterable, Iterator

from .config import SimulationConfig
from .detection import NoisyOracle
from .model import Actor, Block, Disposition, RaceOrigin
from .punishments import NoPunishment, PettyPunishment
from .random_streams import stream


class Simulation:
    """Event-driven Eyal--Sirer state machine with an explicit public race."""

    def __init__(self, config: SimulationConfig,
                 discoverers: Iterable[Actor | str] | None = None,
                 oracle_outcomes: Iterable[bool] | None = None):
        self.config = config
        self.discovery_rng = stream(config.seed, "discoveries")
        self.honest_tie_rng = stream(config.seed, "honest-ties")
        self.coalition_tie_rng = stream(config.seed, "coalition-ties")
        self.oracle = NoisyOracle(config.tpr, config.fpr, stream(config.seed, "oracle"))
        self.natural_fork_rng = stream(config.seed, "natural-forks")
        self.discoverers: Iterator | None = iter(discoverers) if discoverers is not None else None
        self.oracle_outcomes: Iterator | None = iter(oracle_outcomes) if oracle_outcomes is not None else None
        self.target_is_selfish = config.strategy == "selfish"
        if config.forced_label is not None:
            self.target_flagged = config.forced_label
            self.classification_mode = "forced"
        elif self.oracle_outcomes is None:
            self.target_flagged = self.oracle.classify(self.target_is_selfish)
            self.classification_mode = "sampled"
        else:
            self.target_flagged = self.oracle.record(
                self.target_is_selfish, bool(next(self.oracle_outcomes)))
            self.classification_mode = "sampled"
        self.rule = PettyPunishment() if config.punishment_enabled else NoPunishment()
        self.blocks: dict[int, Block] = {}
        self.private: deque[int] = deque()
        self.public_tip: int | None = None
        self.public_height = 0
        self.race: dict | None = None
        self.propagation_pending: int | None = None
        self.events = 0
        self.next_id = 1
        self.publication_sequence = 0
        self.discovered = Counter()
        self.selfish_releases = 0
        self.public_races = 0
        self.races_by_origin = Counter()
        self.natural_races_by_actor_pair = Counter()
        self.target_involved_races = 0
        self.non_target_races = 0
        self.punishment_opportunities = 0
        self.natural_propagation_windows = 0
        self.punishment_activations = 0
        self.punishments_by_origin = Counter()
        self.trace: list[dict] = []

    def _discoverer(self) -> Actor:
        if self.discoverers is not None:
            return Actor(next(self.discoverers))
        x = self.discovery_rng.random()
        if x < self.config.target_hash_power:
            return Actor.TARGET
        if x < self.config.target_hash_power + self.config.coalition_hash:
            return Actor.COALITION
        return Actor.HONEST

    def _new(self, owner: Actor, parent: int | None, withheld: bool) -> int:
        height = self.blocks[parent].height + 1 if parent is not None else 1
        bid = self.next_id
        self.next_id += 1
        self.blocks[bid] = Block(bid, parent, height, owner, self.events, withheld)
        self.discovered[owner.value] += 1
        return bid

    def _publish(self, ids: Iterable[int], selfish: bool) -> list[int]:
        out = list(ids)
        for bid in out:
            block = self.blocks[bid]
            if block.publication_sequence is None:
                self.publication_sequence += 1
                block.publication_sequence = self.publication_sequence
            block.selfish_release |= selfish
        return out

    def _accept(self, ids: Iterable[int]) -> list[int]:
        out = list(ids)
        for bid in out:
            assert self.blocks[bid].disposition == Disposition.UNRESOLVED
            self.blocks[bid].disposition = Disposition.ACCEPTED
            self.public_tip = bid
            self.public_height = self.blocks[bid].height
        return out

    def _orphan(self, ids: Iterable[int]) -> list[int]:
        out = list(ids)
        for bid in out:
            assert self.blocks[bid].disposition == Disposition.UNRESOLVED
            self.blocks[bid].disposition = Disposition.ORPHANED
        return out

    def _state(self) -> str:
        return "race" if self.race else ("propagation_pending" if self.propagation_pending is not None else
               "lead_0" if not self.private else
               "lead_1" if len(self.private) == 1 else "lead_2_plus")

    def _begin_race(self, branch_a: int, branch_b: int,
                    origin: RaceOrigin) -> None:
        owner_a = self.blocks[branch_a].owner
        owner_b = self.blocks[branch_b].owner
        assert owner_a != owner_b
        assert self.blocks[branch_a].parent_id == self.blocks[branch_b].parent_id
        target_branch = (branch_a if owner_a == Actor.TARGET else
                         branch_b if owner_b == Actor.TARGET else None)
        self.race = {"branch_a": branch_a, "branch_b": branch_b,
                     "target_branch": target_branch, "origin": origin}
        self.public_races += 1
        self.races_by_origin[origin.value] += 1
        if origin == RaceOrigin.NATURAL_PROPAGATION:
            pair = "--".join(sorted((owner_a.value, owner_b.value)))
            self.natural_races_by_actor_pair[pair] += 1
        if target_branch is None:
            self.non_target_races += 1
        else:
            self.target_involved_races += 1
            if self.config.punishment_enabled and self.config.coalition_hash > 0:
                self.punishment_opportunities += 1
        if (target_branch is not None and self.config.punishment_enabled and
                self.target_flagged and self.config.coalition_hash > 0):
            self.punishment_activations += 1
            self.punishments_by_origin[origin.value] += 1

    def inject_public_race(self, origin: RaceOrigin = RaceOrigin.NATURAL_PROPAGATION,
                           competing_owner: Actor = Actor.HONEST) -> tuple[int, int]:
        """Construct a target-involved tie for deterministic policy tests.

        This is deliberately outside the standard strategy path: it permits a
        either diagnostic origin without inventing an event in normal mining.
        """
        if self.race or self.private or self.propagation_pending is not None:
            raise ValueError("synthetic race requires a clean lead-zero state")
        self.events += 1
        target = self._new(Actor.TARGET, self.public_tip, False)
        self._publish([target], origin == RaceOrigin.SELFISH_RELEASE)
        self.events += 1
        competing = self._new(competing_owner, self.public_tip, False)
        self._publish([competing], False)
        self._begin_race(target, competing, origin)
        return target, competing

    def step(self) -> None:
        pre = self._state()
        self.events += 1
        actor = self._discoverer()
        published: list[int] = []
        accepted: list[int] = []
        orphaned: list[int] = []
        coalition_choice = None
        race_origin = self.race["origin"] if self.race else None
        race_began = race_ended = False

        if self.race:
            branch_a = self.race["branch_a"]
            branch_b = self.race["branch_b"]
            target_branch = self.race["target_branch"]
            owner_a = self.blocks[branch_a].owner
            owner_b = self.blocks[branch_b].owner
            if target_branch is not None:
                other_branch = branch_b if target_branch == branch_a else branch_a
                if actor == Actor.TARGET:
                    chosen = target_branch
                elif actor == Actor.HONEST:
                    chosen = (target_branch if self.honest_tie_rng.random() < self.config.gamma
                              else other_branch)
                else:
                    supports_target = self.rule.coalition_supports_target(
                        self.target_flagged, self.coalition_tie_rng.random(), self.config.gamma)
                    chosen = target_branch if supports_target else other_branch
                    coalition_choice = "target" if supports_target else "non_target"
            else:
                # Ordinary tie: each represented branch owner supports its own
                # block; a third actor splits evenly. Target label is irrelevant.
                if actor == owner_a:
                    chosen = branch_a
                elif actor == owner_b:
                    chosen = branch_b
                else:
                    chosen = branch_a if self.honest_tie_rng.random() < .5 else branch_b
                if actor == Actor.COALITION:
                    coalition_choice = "own" if actor in (owner_a, owner_b) else "ordinary"
            losing = branch_b if chosen == branch_a else branch_a
            bid = self._new(actor, chosen, False)
            published = self._publish([bid], False)
            accepted = self._accept([chosen, bid])
            orphaned = self._orphan([losing])
            self.race = None
            race_ended = True
        elif self.propagation_pending is not None:
            competing = self.propagation_pending
            pending_owner = self.blocks[competing].owner
            if self.target_is_selfish and actor == Actor.TARGET:
                # Pure-type rule: the target receives the pending honest block,
                # then mines its next block privately on top of it. No benign
                # target-involved fork is created.
                accepted = self._accept([competing])
                self.private.append(self._new(actor, competing, True))
            elif actor != pending_owner:
                # The second miner has not yet received the pending publication
                # and honestly publishes a sibling on the prior public tip.
                sibling = self._new(actor, self.public_tip, False)
                published = self._publish([sibling], False)
                origin = RaceOrigin.NATURAL_PROPAGATION
                self._begin_race(competing, sibling, origin)
                race_origin = origin
                race_began = True
            else:
                bid = self._new(actor, competing, False)
                published = self._publish([bid], False)
                accepted = self._accept([competing, bid])
            self.propagation_pending = None
        elif self.config.strategy == "honest":
            bid = self._new(actor, self.public_tip, False)
            published = self._publish([bid], False)
            if (self.config.natural_fork_rate > 0 and
                    self.natural_fork_rng.random() < self.config.natural_fork_rate):
                self.propagation_pending = bid
                self.natural_propagation_windows += 1
            else:
                accepted = self._accept([bid])
        elif actor == Actor.TARGET:
            parent = self.private[-1] if self.private else self.public_tip
            self.private.append(self._new(actor, parent, True))
        else:
            competing = self._new(actor, self.public_tip, False)
            published = self._publish([competing], False)
            lead = len(self.private)
            if lead == 0:
                if (self.config.natural_fork_rate > 0 and
                        self.natural_fork_rng.random() < self.config.natural_fork_rate):
                    self.propagation_pending = competing
                    self.natural_propagation_windows += 1
                else:
                    accepted = self._accept([competing])
            elif lead == 1:
                released = self.private.popleft()
                published += self._publish([released], True)
                origin = RaceOrigin.SELFISH_RELEASE
                self._begin_race(released, competing, origin)
                race_origin = origin
                self.selfish_releases += 1
                race_began = True
            elif lead == 2:
                branch = list(self.private)
                self.private.clear()
                published += self._publish(branch, True)
                accepted = self._accept(branch)
                orphaned = self._orphan([competing])
                self.selfish_releases += 1
            else:
                released = self.private.popleft()
                published += self._publish([released], True)
                accepted = self._accept([released])
                orphaned = self._orphan([competing])
                self.selfish_releases += 1

        if self.config.trace_path is not None:
            rewards = Counter(b.owner.value for b in self.blocks.values()
                              if b.disposition == Disposition.ACCEPTED)
            self.trace.append({"event": self.events, "discoverer": actor.value,
                "pre_state": pre, "post_state": self._state(), "private_lead": len(self.private),
                "published": published, "race_began": race_began, "race_ended": race_ended,
                "target_miner_truth": "selfish" if self.target_is_selfish else "honest",
                "target_miner_label": "flagged" if self.target_flagged else "not_flagged",
                "race_origin": race_origin.value if race_origin else RaceOrigin.NONE.value,
                "race_origin_truth": (race_origin == RaceOrigin.SELFISH_RELEASE
                                      if race_origin else None),
                "race_branch_owners": ([self.blocks[x].owner.value for x in
                    (self.race["branch_a"], self.race["branch_b"])]
                    if race_began and self.race else None),
                "target_branch_present": (self.race["target_branch"] is not None
                    if race_began and self.race else None),
                "coalition_branch_choice": coalition_choice, "accepted": accepted,
                "orphaned": orphaned, "cumulative_rewards": dict(rewards)})

    def run(self) -> dict:
        while self.accepted_count < self.config.target_accepted_blocks:
            self.step()
        final_events = 0
        while (self.race is not None or self.propagation_pending is not None) and final_events < self.config.max_finalization_events:
            self.step()
            final_events += 1
        result = self.report()
        if self.config.trace_path:
            path = Path(self.config.trace_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(row) + "\n" for row in self.trace))
        return result

    @property
    def accepted_count(self) -> int:
        return sum(b.disposition == Disposition.ACCEPTED for b in self.blocks.values())

    def report(self) -> dict:
        accepted = Counter(b.owner.value for b in self.blocks.values() if b.disposition == Disposition.ACCEPTED)
        orphaned = Counter(b.owner.value for b in self.blocks.values() if b.disposition == Disposition.ORPHANED)
        unresolved = Counter(b.owner.value for b in self.blocks.values() if b.disposition == Disposition.UNRESOLVED)
        total_a = sum(accepted.values())
        actors = {}
        shares = {"target": self.config.target_hash_power, "coalition": self.config.coalition_hash,
                  "honest": self.config.honest_hash}
        for name, share in shares.items():
            revenue_share = accepted[name] / total_a if total_a else None
            actors[name] = {"hash_power_share": share, "blocks_discovered": self.discovered[name],
                "blocks_accepted": accepted[name], "blocks_orphaned": orphaned[name],
                "blocks_unresolved_or_private": unresolved[name], "accepted_revenue": accepted[name],
                "accepted_revenue_share": revenue_share,
                "normalized_revenue": revenue_share / share if share and revenue_share is not None else None}
        total_orphaned = sum(orphaned.values())
        result = {"parameters": self.config.to_dict(), "seed": self.config.seed,
            "total_discovery_events": self.events, "total_accepted_blocks": total_a,
            "total_orphaned_blocks": total_orphaned,
            "stale_block_fraction": total_orphaned / self.events if self.events else 0,
            "selfish_release_events": self.selfish_releases, "public_races": self.public_races,
            "races_by_origin": dict(self.races_by_origin),
            "natural_races_by_actor_pair": dict(self.natural_races_by_actor_pair),
            "target_involved_races": self.target_involved_races,
            "non_target_races": self.non_target_races,
            "punishment_opportunities": self.punishment_opportunities,
            "natural_propagation_windows": self.natural_propagation_windows,
            "punishment_activations": self.punishment_activations,
            "punishment_activations_by_origin": dict(self.punishments_by_origin),
            "unresolved_private_blocks": len(self.private),
            "classification": {"mode": self.classification_mode,
                "target_miner_type": "selfish" if self.target_is_selfish else "honest",
                "label": "flagged" if self.target_flagged else "unflagged"},
            "actors": actors}
        if self.classification_mode == "sampled":
            result["sampled_epoch"] = self.oracle.report(self.target_is_selfish)
        if self.config.include_block_records:
            result["blocks"] = [b.to_dict() for b in self.blocks.values()]
        return result
