"""Native v2 provenance, ledger and event validation, without mining replay.

Validation consumes recorded publication events and reconstructs RNG choices and
policy state. It never calls simulation step(), discover(), run() or publish().
"""
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
import json
import gzip
import hashlib
import tempfile
import marshal
from functools import lru_cache

from .persistent_v2_policies import CounterForkPolicy, PettyPolicy
from .persistent_v2_index import initialize_indexes, advance_frontier, index_publication
from .ostracism import OstracismPolicy
from .selfish_validation import replay_reactions
from .selfish_strategy import release_plan
from .persistent_checkpoint import canonical_json, digest, atomic_json
from .persistent_v2 import (PersistentSimulation, CommonRandom, SelfishActors, Publications,
    condition_identity, eligible_tips, visible_public, NETWORK_VERSION)

BASELINE_SCHEMA = "persistent-common-baseline-checkpoint-v2"
CONDITIONAL_SCHEMA = "persistent-policy-conditional-checkpoint-v2"
PRODUCTION_BASELINE_SCHEMA = "persistent-common-baseline-production-checkpoint-v2"
PRODUCTION_CONDITIONAL_SCHEMA = "persistent-policy-production-checkpoint-v2"


def checkpoint_payload(result):
    production = result.get("recording_mode") == "production-v2"
    flagged = result["identity"]["flagged"]
    schema = ((PRODUCTION_CONDITIONAL_SCHEMA if flagged else PRODUCTION_BASELINE_SCHEMA) if production
              else (CONDITIONAL_SCHEMA if flagged else BASELINE_SCHEMA))
    return {"schema": schema, "identity": result["identity"], "result": result}


def encode_checkpoint(result):
    """Serialize the scientific payload once, then hash/compress those bytes."""
    body = canonical_json(checkpoint_payload(result)).encode()
    checksum = hashlib.sha256(body).hexdigest()
    envelope = b'{"content_sha256":"' + checksum.encode() + b'",' + body[1:] + b'\n'
    return gzip.compress(envelope, compresslevel=6, mtime=0) if result.get("recording_mode") else envelope


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def require(condition, message):
    if not condition:
        raise ValueError("v2 checkpoint validation: " + message)


def same(left, right, message):
    require(canonical_json(left) == canonical_json(right), message)


@lru_cache(maxsize=128)
def _cached_miner_definitions(population):
    return population.miners


def _miner_definitions(population):
    # Cache only fully immutable populations; preserve accepted list-valued
    # caller inputs without retaining a mutable cache key or changing validation.
    try:
        hash(population)
    except TypeError:
        return population.miners
    return _cached_miner_definitions(population)


def native_same(left, right, message):
    """Exact fast path, with the original canonical comparator as fallback.

Marshal v2 has no object-reference memoization. Equal typed bytes imply the
same ordered native tree, including bool/int/float and signed-zero distinctions.
Canonicalizing one operand still enforces JSON representability and key rules.
Different order, tuple/list representation, unsupported types, or any differing
bytes fall back to comparing both canonical JSON strings. Nothing is unmarshaled
or persisted; this is an equality comparison, not a substitute provenance hash.
"""
    try:
        equal = marshal.dumps(left, 2) == marshal.dumps(right, 2)
    except (ValueError, TypeError, RecursionError):
        equal = False
    if equal:
        canonical_json(right)
    else:
        same(left, right, message)


class PublicReplay(PersistentSimulation):
    """Ledger view only; intentionally never initializes or runs a simulation."""
    def __init__(self, population, rule, identity, records, *, cache_metadata=True):
        self.identity, self.rule = identity, rule
        self.base_population = population
        self.p = replace(population, seed=identity["actual_seed"])
        self.strategy, self.enabled = identity["strategy"], identity["flagged"]
        self.flagged, self.active = self.enabled, frozenset(identity["active_coalition"])
        self.miners = {m.id: m for m in (_miner_definitions(population) if cache_metadata else self.p.miners)}
        self.blocks = {b: SimpleNamespace(**record) for b, record in records.items()}
        initialize_indexes(self)
        self.children = defaultdict(set)
        for b in self.blocks.values():
            self.children[b.parent_id].add(b.id)
            b.canonical = False
        self.public, self.public_tips, self.longest_tips = set(), set(), set()
        self.public_height = self.publication_sequence = self.events = 0
        self.reference_tip = None
        self.canonical_chain, self.reorganizations, self.private = [], [], []
        self.abandoned_private = set()
        self.rewards, self.discovered, self.activations, self.opportunities, self.natural_pairs = (
            Counter(), Counter(), Counter(), Counter(), Counter())
        self.punishment = None
        if self.enabled and rule.punishment_rule == "counter_fork":
            self.punishment = CounterForkPolicy(rule, True)
        elif self.enabled and rule.punishment_rule == "ignore":
            self.punishment = OstracismPolicy(self, True)
        elif self.enabled and rule.punishment_rule == "petty":
            self.punishment = PettyPolicy(self)
        actors = {"target"} if self.strategy == "selfish" else set()
        if self.enabled and rule.punishment_rule == "selfish":
            actors.update(self.active)
            self.activations.update({a: 1 for a in self.active})
        self.selfish, self.policy = SelfishActors(self, actors), Publications(self)
        self.window = self.pending = None
        self.rng, self.tie_rng, self.natural_rng = (CommonRandom(self.p.seed, name)
            for name in ("discoveries", "ties", "natural"))

    def apply_batch(self, batch):
        ids = batch["blocks"]
        advance_frontier(self, ids)
        chosen = self.reference_tip if self.reference_tip in self.longest_tips else min(
            self.longest_tips, key=lambda b: (self.blocks[b].publication_sequence, b))
        self._adopt(chosen)
        self.publication_sequence += len(ids)
        if self.punishment is not None:
            self.punishment.on_publication(self, ids)
        index_publication(self, ids)
        for actor, state in self.selfish.states.items():
            state.private_chain = [b for b in state.private_chain if b not in ids]
            for bid in ids:
                block = self.blocks[bid]
                if block.owner_id == actor:
                    state.exposed_tip = bid
                    if block.initially_withheld:
                        state.released_blocks.append(bid)

    def apply_episode(self, batches):
        """Check every reaction opportunity, including absent reaction records."""
        if not batches:
            return
        self.apply_batch(batches[0])
        observed, cursor = batches[0]["blocks"], 1
        while observed:
            decisions = []
            for actor, state in self.selfish.states.items():
                plan = release_plan(self, state.private_chain, observed)
                if plan is not None:
                    decisions.append({"actor_id": actor, "action": plan.action, "blocks": list(plan.blocks),
                                      "private_tip_before": state.private_chain[-1]})
            if not decisions:
                break
            self.selfish.history.append({"outcome": "SELFISH_REACTION_ROUND", "round": len(self.selfish.history)+1,
                "discovery_event": self.events, "observed_publications": list(observed),
                "public_height": self.public_height, "publication_sequence": self.publication_sequence,
                "decisions": decisions})
            observed = []
            for decision in decisions:
                state = self.selfish.states[decision["actor_id"]]
                if decision["action"] == "ABANDON":
                    state.abandoned_blocks.extend(state.private_chain)
                    state.private_chain.clear()
                else:
                    require(cursor < len(batches), "missing mandatory selfish release")
                    same(batches[cursor]["blocks"], decision["blocks"], "unexpected selfish release batch")
                    require(batches[cursor]["kind"] == ("target_selfish_release" if decision["actor_id"] == "target"
                            else "member_selfish_release"), "selfish release mislabeled")
                    self.apply_batch(batches[cursor])
                    observed.extend(decision["blocks"])
                    cursor += 1
        require(cursor == len(batches), "publication without a strategy reaction")

    def step(self, *args, **kwargs):
        raise AssertionError("validation cannot mine")

    discover = publish = run = step


def validate_run(result, population, rule, repetition, strategy, flagged, coalition):
    """Fail closed on identity, seed, behavior, accounting or endpoint corruption."""
    try:
        _validate_run(result, population, rule, repetition, strategy, flagged, coalition)
    except (KeyError, TypeError, IndexError, AttributeError, ZeroDivisionError) as exc:
        raise ValueError("malformed v2 checkpoint") from exc


def _validate_run(result, population, rule, repetition, strategy, flagged, coalition,
                  optimizations=frozenset(("reactions", "comparison", "debug", "metadata"))):
    compare = native_same if "comparison" in optimizations else same
    identity = condition_identity(population, repetition, strategy, flagged, coalition, rule)
    compare(result["identity"], identity, "identity mismatch")
    require(result["condition_id"] == digest(identity) and result["network_version"] == NETWORK_VERSION,
            "condition/network mismatch")
    require(result["model_version"] == identity["model_version"], "model mismatch")
    enabled = identity["flagged"]
    require(result["punishment_rule"] == (rule.punishment_rule if enabled else None)
            and result["counter_fork_k"] == (rule.counter_fork_k if enabled else None), "rule mismatch")
    require(result["strategy"] == strategy and result["label"] == ("flagged" if enabled else "unflagged")
            and result["active_coalition"] == identity["active_coalition"], "condition mismatch")
    compare(result["population"], asdict(replace(population, seed=identity["actual_seed"])), "population/seed mismatch")
    require(result["status"] == "COMPLETE" and result["error"] is None, "incomplete condition")
    require(result["scripted_discoveries"] == [], "scripted discoveries are not native checkpoint provenance")
    production = result.get("recording_mode") == "production-v2"
    require("recording_mode" not in result or production, "unknown recording mode")
    if production:
        require("trace" not in result and "public_events" not in result, "production/debug provenance mixed")
    terminal, events = result["terminal"], result["events"]
    require(type(events) is int and events > 0, "invalid discovery count")
    records = terminal["canonical_blocks"] + terminal["frontier_blocks"]
    blocks = {b["id"]: dict(b) for b in records}
    require(len(blocks) == len(records) == events and set(blocks) == set(range(1, events+1)), "block ledger coverage")
    miners = {m.id: m for m in (_miner_definitions(population) if "metadata" in optimizations else population.miners)}
    for bid, b in blocks.items():
        require(b["owner_id"] in miners and b["discovery_sequence"] == bid, "owner/discovery mismatch")
        parent = b["parent_id"]
        require(parent is None or (type(parent) is int and parent in blocks and parent < bid), "invalid parent")
        require(b["height"] == (blocks[parent]["height"] if parent is not None else 0)+1, "invalid height")
        require(type(b["initially_withheld"]) is bool and type(b["canonical"]) is bool, "invalid block flags")
        if b["publication_sequence"] is None:
            require(b["release_batch"] is None and b["publication_kind"] is None and not b["canonical"], "hidden block fields")
    by_event = defaultdict(list)
    public_order, seen_public, last_event = [], set(), 0
    for index, batch in enumerate(result["publication_batches"], 1):
        require(batch["batch"] == index and bool(batch["blocks"]), "invalid publication batch")
        event = batch["discovery_event"]
        require(type(event) is int and 1 <= event <= events, "invalid publication event")
        require(event >= last_event, "publication time went backwards")
        last_event = event
        for bid in batch["blocks"]:
            b = blocks[bid]
            require(bid <= event and bid not in seen_public, "publication before discovery or duplicate")
            parent = b["parent_id"]
            require(parent is None or parent in seen_public, "publication ancestry/order mismatch")
            require(b["publication_sequence"] == len(public_order)+1 and b["release_batch"] == index
                    and b["publication_kind"] == batch["kind"], "publication provenance mismatch")
            public_order.append(bid)
            seen_public.add(bid)
        by_event[event].append(batch)
    public = set(public_order)
    require(public == {b for b in blocks if blocks[b]["publication_sequence"] is not None}, "public coverage")
    view = PublicReplay(population, rule, identity, blocks, cache_metadata="metadata" in optimizations)
    actors = list(view.selfish.states)
    require(result["selfish_actor_order"] == actors, "selfish actor identity mismatch")
    if "reactions" not in optimizations:
        private, abandoned = replay_reactions({**result, "episodes": result["selfish_reactions"]}, blocks, actors, require)
    plans = [d["blocks"] for frame in result["selfish_reactions"] for d in frame["decisions"] if d["action"] == "RELEASE"]
    released_batches = [b["blocks"] for b in result["publication_batches"] if blocks[b["blocks"][0]]["initially_withheld"]]
    require(plans == released_batches, "release batch/plan mismatch")
    if not production:
        require(len(result["public_events"]) == events, "public-event coverage")
    traces = []
    for event in range(1, events+1):
        require(view.public_height < population.target_accepted_blocks, "discoveries beyond observation horizon")
        view.events = event
        bid, b = event, blocks[event]
        actor = view._draw()
        require(actor == b["owner_id"], "discovery RNG/owner mismatch")
        incoming = view.window
        start_height, start_tips = view.public_height, sorted(view.longest_tips)
        if view.policy.active or (enabled and rule.punishment_rule == "selfish"):
            view.opportunities.update(view.active)
        state = view.selfish.states.get(actor)
        source, choice = None, None
        if state is not None and state.private_chain:
            parent, withheld, kind = state.private_chain[-1], True, None
        else:
            visible = view.public if state is not None else visible_public(view, actor, incoming)
            tips = eligible_tips(view, actor, visible)
            before = view.tie_rng.count
            parent = view.choose_among_tips(actor, tips)
            if not production or "debug" not in optimizations:
                choice = {"tips": tips, "parent": parent,
                          "draw": view.tie_rng.last if view.tie_rng.count > before else None}
            if state is not None:
                withheld = len(start_tips) <= 1
                kind = "target_tie_resolution" if actor == "target" else "member_tie_resolution"
            else:
                withheld = False
                full_tips = eligible_tips(view, actor, view.public)
                if incoming and view.height(parent) < view.height(full_tips[0]):
                    hidden = [t for t in full_tips if t is not None and t not in visible]
                    if hidden:
                        source = min(hidden, key=lambda t: blocks[t]["publication_sequence"])
                punishing = view.punishment is not None and view.punishment.active and actor in view.active
                if isinstance(view.punishment, PettyPolicy):
                    punishing = view.punishment.is_punishing(actor, visible)
                kind = rule.punishment_rule if punishing else "natural_fork" if source is not None else "ordinary"
        require(b["parent_id"] == parent and b["initially_withheld"] == withheld, "fork choice/private discovery mismatch")
        view.discovered[actor] += 1
        if withheld:
            state.private_chain.append(bid)
            require(not by_event[event], "private discovery unexpectedly published")
        else:
            require(bool(by_event[event]) and by_event[event][0]["blocks"] == [bid]
                    and by_event[event][0]["kind"] == kind, "ordinary discovery publication mismatch")
            if kind == "natural_fork":
                view.natural_pairs["--".join(sorted((actor, blocks[source]["owner_id"])))] += 1
        view.apply_episode(by_event[event])
        publications = [b for batch in by_event[event] for b in batch["blocks"]]
        eligible = incoming is None and len(start_tips) <= 1 and bid in view.public and view.height(bid) > start_height
        draw = view.natural_rng.random() if eligible else None
        view.window = ({"discovery_event": event, "origin_block": bid, "blocks": publications,
                        "delayed_tips": [b for b in publications if b in view.public_tips]}
                       if draw is not None and draw < population.natural_fork_rate else None)
        view.pending = bid if view.window else None
        if not production or "debug" not in optimizations:
            expected = {"event": event, "discoverer": actor, "block": bid, "public_height_before": start_height,
                "leading_tips_before": start_tips, "incoming_window": incoming, "choice": choice,
                "delayed_source": source, "publications": publications, "lambda_eligible": eligible,
                "lambda_draw": draw, "pending_window": view.window}
        if not production:
            compare(result["public_events"][event-1], expected, "public event/propagation mismatch")
        if "trace" in result:
            traces.append({**expected, "private_states": view.state_snapshots(), "public_frontier": sorted(view.public_tips),
                "canonical_chain": list(view.canonical_chain), "publication_sequence": view.publication_sequence,
                "rewards": dict(view.rewards), "rng": view.rng_snapshot(), "punishment": view.policy.snapshot()})
    if "reactions" not in optimizations:
        for a, state in view.selfish.states.items():
            require(state.private_chain == private[a] and state.abandoned_blocks == abandoned[a], "private replay mismatch")
    else:
        private = {a: state.private_chain for a, state in view.selfish.states.items()}
        abandoned = {a: state.abandoned_blocks for a, state in view.selfish.states.items()}
    hidden = set(blocks)-public
    require(hidden == {b for ids in (*private.values(), *abandoned.values()) for b in ids}, "hidden coverage")
    require(view.public_height == result["accepted_blocks"] >= population.target_accepted_blocks, "horizon mismatch")
    # terminal_state uses dataclass serialization; the replay ledger was built
    # independently from the raw records and publication/discovery provenance.
    from .persistent import Block
    view.blocks = {bid: Block(**vars(b)) for bid, b in view.blocks.items()}
    compare(terminal, view.terminal_state(), "terminal/frontier/boundary mismatch")
    compare(result["rng"], view.rng_snapshot(), "RNG state/consumption mismatch")
    compare(result["episodes"], view.punishment.history if view.punishment else [], "policy history mismatch")
    compare(result["selfish_reactions"], view.selfish.history, "missing or incorrect selfish reaction history")
    compare(result["reorganizations"], view.reorganizations, "reorganization mismatch")
    compare(result["member_activations"], dict(view.activations), "activation accounting mismatch")
    compare(result["member_opportunities"], dict(view.opportunities), "opportunity accounting mismatch")
    compare(result["natural_pairs"], dict(view.natural_pairs), "natural pair mismatch")
    require(set(result["actors"]) == set(miners), "actor coverage")
    canonical = set(view.canonical_chain)
    for a, miner in miners.items():
        accepted = view.rewards[a]
        orphaned = sum(blocks[b]["owner_id"] == a and b not in canonical for b in public)
        unreleased = sum(blocks[b]["owner_id"] == a for b in hidden)
        payoff = accepted/view.public_height
        expected = {"role": miner.role, "hash_power": miner.hash_power, "discovered": view.discovered[a],
            "accepted": accepted, "orphaned": orphaned, "public_noncanonical": orphaned, "unresolved": unreleased,
            "payoff": payoff, "normalized_revenue": payoff/miner.hash_power}
        compare(result["actors"][a], expected, "actor/reward ledger mismatch")
    if "trace" in result:
        compare(result["trace"], traces, "trace mismatch")


class ConditionStore:
    """A shared immutable baseline namespace, alongside rule-specific conditions."""
    def __init__(self, directory):
        self.directory = Path(directory)

    def path(self, identity, production=False):
        return self.directory / ("baselines" if not identity["flagged"] else "conditions") / (digest(identity)+(".json.gz" if production else ".json"))

    def load(self, population, rule, repetition, strategy, flagged, coalition):
        identity = condition_identity(population, repetition, strategy, flagged, coalition, rule)
        path = self.path(identity)
        compressed = self.path(identity, True)
        require(not (path.exists() and compressed.exists()), "ambiguous duplicate condition encodings")
        if compressed.exists():
            path = compressed
        if not path.exists():
            return None
        try:
            payload = json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())
        except (OSError, EOFError, UnicodeError, ValueError) as exc:
            raise ValueError("invalid v2 checkpoint encoding") from exc
        require(isinstance(payload, dict), "invalid checkpoint envelope")
        checksum = payload.pop("content_sha256", None)
        require(isinstance(payload.get("result"), dict), "missing result")
        schema = ((PRODUCTION_CONDITIONAL_SCHEMA if identity["flagged"] else PRODUCTION_BASELINE_SCHEMA)
                  if path.suffix == ".gz" else (CONDITIONAL_SCHEMA if identity["flagged"] else BASELINE_SCHEMA))
        require((path.suffix == ".gz") == (payload["result"].get("recording_mode") == "production-v2"),
                "production/debug encoding mismatch")
        require(set(payload) == {"schema", "identity", "result"} and payload["schema"] == schema, "schema mismatch; no v1 import")
        require(digest(payload) == checksum, "content digest mismatch")
        same(payload["identity"], identity, "stored identity mismatch")
        validate_run(payload["result"], population, rule, repetition, strategy, flagged, coalition)
        return payload["result"]

    def save(self, result, population, rule, repetition, strategy, flagged, coalition):
        validate_run(result, population, rule, repetition, strategy, flagged, coalition)
        identity = condition_identity(population, repetition, strategy, flagged, coalition, rule)
        path = self.path(identity, result.get("recording_mode") == "production-v2")
        if self.path(identity).exists() or self.path(identity, True).exists():
            previous = self.load(population, rule, repetition, strategy, flagged, coalition)
            same(previous, result, "refusing to overwrite different existing result")
            return
        atomic_bytes(path, encode_checkpoint(result))
