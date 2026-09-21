"""Validate native multi-selfish state and public reaction provenance."""
from collections import Counter
from types import SimpleNamespace

from .selfish_counter import REACTION_ORDER, PROPAGATION
from .selfish_strategy import release_plan


class PublicView:
    """Publication-prefix view for release-plan validation, with no mining/RNG."""
    def __init__(self, blocks):
        self.blocks = {bid: SimpleNamespace(**b) for bid, b in blocks.items()}
        self.tips = set()
        self.longest_tips = set()
        self.public_height = 0

    def height(self, bid):
        return self.blocks[bid].height if bid is not None else 0

    def descends(self, bid, ancestor):
        height = self.height(ancestor)
        while self.height(bid) > height:
            bid = self.blocks[bid].parent_id
        return bid == ancestor

    def expose(self, bid):
        block = self.blocks[bid]
        self.tips.discard(block.parent_id)
        self.tips.add(bid)
        if block.height > self.public_height:
            self.public_height = block.height
            self.longest_tips = {bid}
        elif block.height == self.public_height:
            self.longest_tips.add(bid)


def replay_reactions(result, blocks, actors, require):
    """Audit decisions against their exact public snapshot and own private chain.

    This reconstructs release decisions, not a mining rerun. Publication facts,
    discovery order and plans are inputs; no random number is generated.
    """
    private = {a: [] for a in actors}
    abandoned = {a: [] for a in actors}
    view = PublicView(blocks)
    published = sorted((b for b in blocks if blocks[b]["publication_sequence"] is not None),
                       key=lambda b: blocks[b]["publication_sequence"])
    publication_events = {b: batch["discovery_event"] for batch in result["publication_batches"] for b in batch["blocks"]}
    publications_by_event = {}
    for bid in published:
        publications_by_event.setdefault(publication_events[bid], []).append(bid)
    batch_ends = {max(blocks[b]["publication_sequence"] for b in batch["blocks"]) for batch in result["publication_batches"]}
    discovered_through = exposed_through = 0
    previous_event = previous_cutoff = 0
    previous_releases = []

    def discoveries_through(event):
        nonlocal discovered_through
        while discovered_through < event:
            discovered_through += 1
            b = blocks[discovered_through]
            if b["initially_withheld"]:
                actor, parent = b["owner_id"], b["parent_id"]
                require(actor in private, "private block belongs to an honest/nonparticipating actor")
                chain = private[actor]
                if chain:
                    require(parent == chain[-1], "shared or branching private chain")
                else:
                    require(parent is None or publication_events.get(parent, result["events"] + 1) < discovered_through,
                            "private base was not public at discovery")
                chain.append(discovered_through)

    for index, frame in enumerate(result["episodes"], 1):
        require(frame["outcome"] == "SELFISH_REACTION_ROUND" and frame["round"] == index,
                "invalid selfish reaction round")
        event, cutoff = frame["discovery_event"], frame["publication_sequence"]
        require(previous_event <= event <= result["events"] and previous_cutoff < cutoff
                and cutoff in batch_ends, "invalid reaction observation order")
        discoveries_through(event)
        while exposed_through < cutoff:
            view.expose(published[exposed_through])
            exposed_through += 1
        if event == previous_event:
            expected_observed = previous_releases
        else:
            expected_observed = [b for b in publications_by_event[event]
                                 if blocks[b]["publication_sequence"] <= cutoff]
        require(frame["observed_publications"] == expected_observed and bool(expected_observed),
                "reaction used wrong public event or unpublished information")
        require(frame["public_height"] == view.public_height, "reaction public height mismatch")
        expected = []
        for actor in actors:
            plan = release_plan(view, private[actor], expected_observed)
            if plan is not None:
                expected.append({"actor_id": actor, "action": plan.action, "blocks": list(plan.blocks),
                                 "private_tip_before": private[actor][-1]})
        require(frame["decisions"] == expected and bool(expected), "selfish release rule/ordering mismatch")
        previous_releases = []
        next_sequence = cutoff + 1
        for decision in expected:
            actor, ids = decision["actor_id"], decision["blocks"]
            if decision["action"] == "ABANDON":
                abandoned[actor].extend(ids)
                private[actor].clear()
            else:
                require([blocks[b]["publication_sequence"] for b in ids]
                        == list(range(next_sequence, next_sequence + len(ids))), "reaction release order mismatch")
                batches = {blocks[b]["release_batch"] for b in ids}
                require(len(batches) == 1 and all(publication_events[b] == event for b in ids),
                        "non-atomic selfish release")
                require(all(blocks[b]["publication_kind"] == (
                    "target_selfish_release" if actor == "target" else "member_selfish_release") for b in ids),
                    "selfish release mislabeled")
                private[actor] = private[actor][len(ids):]
                previous_releases.extend(ids)
                next_sequence += len(ids)
        previous_event, previous_cutoff = event, cutoff
    discoveries_through(result["events"])
    return private, abandoned


def validate_selfish(result, blocks, public, population, flagged, coalition, require):
    actors = [m.id for m in population.miners if (m.id == "target" and result["strategy"] == "selfish")
              or (flagged and m.id in coalition)]
    armed = bool(flagged and coalition)
    terminal = result["terminal"]
    require(result["selfish_actor_order"] == actors and result["reaction_order"] == REACTION_ORDER
            and result["propagation_convention"] == PROPAGATION, "selfish model convention mismatch")
    require(terminal["retaliation"] == {"punishment_rule": "selfish", "armed": armed,
        "activation_event": 0 if armed else None, "active_members": sorted(coalition) if armed else []},
        "selfish activation mismatch")
    require(result["member_activations"] == ({a: 1 for a in coalition} if armed else {}),
            "selfish activation accounting mismatch")
    require(result["member_opportunities"] == ({a: result["events"] for a in coalition} if armed else {}),
            "selfish opportunity accounting mismatch")
    require(set(terminal["selfish_states"]) == set(actors), "wrong selfish/private actors")
    require(terminal["reaction_queue"] == [], "unfinished reaction queue at complete observation")
    private, abandoned = replay_reactions(result, blocks, actors, require)
    view = PublicView(blocks)
    for bid in sorted(public, key=lambda b: blocks[b]["publication_sequence"]):
        view.expose(bid)
    released = {a: sorted((b for b in public if blocks[b]["owner_id"] == a and blocks[b]["initially_withheld"]),
                         key=lambda b: blocks[b]["publication_sequence"]) for a in actors}
    for actor in actors:
        state, chain = terminal["selfish_states"][actor], private[actor]
        tip = chain[-1] if chain else None
        own_public = [b for b in public if blocks[b]["owner_id"] == actor]
        exposed = max(own_public, key=lambda b: blocks[b]["publication_sequence"]) if own_public else None
        expected = {"actor_id": actor, "private_chain": chain,
            "private_fork_base": blocks[chain[0]]["parent_id"] if chain else None,
            "private_tip": tip, "private_tip_height": view.height(tip), "private_block_count": len(chain),
            "lead_relative_to_public_height": view.height(tip) - result["accepted_blocks"] if tip is not None else 0,
            "competing_public_tips": sorted(t for t in view.longest_tips if tip is not None and not view.descends(tip, t)),
            "exposed_tip": exposed, "exposure_is_leading": exposed in view.longest_tips,
            "released_blocks": released[actor], "abandoned_private_blocks": abandoned[actor],
            "phase": ("PRIVATE_WITH_PUBLIC_TIE" if chain and len(view.longest_tips) > 1 else "PRIVATE" if chain
                      else "EXPOSED_RACE" if exposed in view.longest_tips and len(view.longest_tips) > 1 else "PUBLIC")}
        require(state == expected, "per-actor private state/provenance mismatch")
    active_ids = {b for chain in private.values() for b in chain}
    abandoned_ids = {b for ids in abandoned.values() for b in ids}
    require(not active_ids & abandoned_ids and active_ids | abandoned_ids == set(blocks) - public,
            "private accounting coverage mismatch")
    require(terminal["target_private_chain"] == private.get("target", [])
            and terminal["abandoned_private"] == sorted(abandoned_ids), "private compatibility aliases mismatch")
    for branch in terminal["alternative_branches"]:
        tip = branch["tip"]
        require(branch["active_target_private"] == (tip in private.get("target", [])), "target private branch mismatch")
        if branch["visibility"] == "private":
            require(branch["private_actor"] == blocks[tip]["owner_id"]
                    and branch["active_selfish_private"] == (tip in active_ids), "private branch owner mismatch")
    window = terminal["pending_publication_window"]
    if window is None:
        require(terminal["pending_visibility_block"] is None, "pending bundle mismatch")
    else:
        ids = [b for batch in result["publication_batches"] if batch["discovery_event"] == result["events"]
               for b in batch["blocks"]]
        require(window["discovery_event"] == result["events"] and window["blocks"] == ids
                and window["origin_block"] == terminal["pending_visibility_block"] == result["events"]
                and not blocks[window["origin_block"]]["initially_withheld"], "pending public bundle provenance mismatch")
    publication_events = {b: batch["discovery_event"] for batch in result["publication_batches"] for b in batch["blocks"]}
    publications_by_event = {}
    for batch in result["publication_batches"]:
        publications_by_event.setdefault(batch["discovery_event"], []).extend(batch["blocks"])
    pairs, natural_ids = Counter(), []
    for event in result["natural_events"]:
        bid, source = event["block"], event["delayed_tip"]
        require(bid in public and blocks[bid]["publication_kind"] == "natural_fork"
                and blocks[bid]["owner_id"] not in actors and event["discovery_event"] == bid,
                "invalid natural discovery")
        require(event["delayed_publications"] == publications_by_event.get(bid - 1)
                and source in event["delayed_publications"] and all(
            b in public and publication_events[b] == bid - 1 for b in event["delayed_publications"]),
            "natural event exposes wrong bundle/private information")
        natural_ids.append(bid)
        pairs["--".join(sorted((blocks[bid]["owner_id"], blocks[source]["owner_id"])))] += 1
    require(len(natural_ids) == len(set(natural_ids)) and set(natural_ids) == {
        b for b in public if blocks[b]["publication_kind"] == "natural_fork"}, "natural discovery coverage mismatch")
    require(dict(pairs) == result["natural_pairs"], "natural pair accounting mismatch")
    unresolved = bool(terminal["alternative_branches"] or window)
    boundary = terminal["boundary"]
    require(boundary["actor_payoff_bounds"] == ({a: [0, 1] for a in result["actors"]} if unresolved else None)
            and boundary["future_reorganization_excluded"] == (False if unresolved else None),
            "multi-selfish conservative bounds mismatch")
    require(boundary["actors_with_unpublished_private_blocks"] == [a for a in actors if private[a]]
            and boundary["private_leads"] == {a: terminal["selfish_states"][a]["lead_relative_to_public_height"] for a in actors},
            "multi-selfish lead diagnostic mismatch")
    return False  # Strategy activation alone is not an unresolved terminal fork.
