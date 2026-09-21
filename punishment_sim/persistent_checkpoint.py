"""Strict native persistent-run validation; no historical checkpoint importer."""
from collections import Counter
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import tempfile

from .persistent import (MODEL_VERSION, IGNORE_MODEL_VERSION, SELFISH_MODEL_VERSION, OstracismSpec,
                         SelfishCounterSpec, model_version, configuration_id)
from .selfish_validation import validate_selfish

SCHEMA = "persistent-conditional-checkpoint-v1"
IGNORE_SCHEMA = "persistent-ignore-conditional-checkpoint-v1"
SELFISH_SCHEMA = "persistent-selfish-counter-conditional-checkpoint-v1"


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            f.write(canonical_json(value) + "\n")
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def validate_run(result, population, rule, repetition, strategy, flagged, coalition):
    """Check seeds, condition, complete block ledger and canonical accounting.

    A content digest detects accidental changes; it is not a signature or proof
    that an external producer actually ran this implementation.
    """
    def require(condition, message):
        if not condition:
            raise ValueError("persistent run validation: " + message)

    actual = replace(population, seed=population.seed + repetition)
    require(result["model_version"] == model_version(rule), "model mismatch")
    require(all(result[k] == v for k, v in asdict(rule).items()), "rule/depth mismatch")
    require(canonical_json(result["population"]) == canonical_json(asdict(actual)), "population/seed mismatch")
    require(result["configuration_id"] == configuration_id(actual, rule), "configuration ID mismatch")
    require(result["strategy"] == strategy and result["label"] == ("flagged" if flagged else "unflagged")
            and result["active_coalition"] == sorted(coalition), "conditional identity mismatch")
    require(result["status"] == "COMPLETE" and result["error"] is None, "incomplete/unsupported condition")
    n, events, terminal = result["accepted_blocks"], result["events"], result["terminal"]
    require(type(n) is int and n >= population.target_accepted_blocks, "horizon not reached")
    require(type(events) is int and events >= n, "invalid discovery count")
    require(terminal["reference_height"] == n, "reference height mismatch")
    records = terminal["canonical_blocks"] + terminal["frontier_blocks"]
    blocks = {b["id"]: b for b in records}
    require(len(blocks) == len(records) == events and set(blocks) == set(range(1, events + 1)),
            "incomplete/duplicate block ledger")
    miners = {m.id: m for m in population.miners}
    public, hidden, canonical = set(), set(), set()
    discovered, credited, noncanonical, private = Counter(), Counter(), Counter(), Counter()
    for bid, block in blocks.items():
        parent, owner = block["parent_id"], block["owner_id"]
        require(owner in miners and block["discovery_sequence"] == bid, "invalid block owner/discovery")
        require(parent is None or (parent in blocks and parent < bid), "invalid parent")
        require(block["height"] == (blocks[parent]["height"] if parent is not None else 0) + 1,
                "invalid block height")
        discovered[owner] += 1
        if block["publication_sequence"] is None:
            hidden.add(bid)
            private[owner] += 1
            require(not block["canonical"] and block["release_batch"] is None, "hidden canonical/published block")
        else:
            public.add(bid)
            require(parent is None or (blocks[parent]["publication_sequence"] is not None
                    and blocks[parent]["publication_sequence"] < block["publication_sequence"]),
                    "publication ancestry/order mismatch")
            if block["canonical"]:
                canonical.add(bid)
                credited[owner] += 1
            else:
                noncanonical[owner] += 1
    chain = terminal["canonical_chain"]
    require(len(chain) == n and set(chain) == canonical, "canonical membership mismatch")
    require([blocks[b]["parent_id"] for b in chain] == [None] + chain[:-1], "broken canonical chain")
    require(terminal["reference_tip"] == chain[-1], "reference tip mismatch")
    require(max(blocks[b]["height"] for b in public) == n, "reference is not longest")
    public_tips = public - {blocks[b]["parent_id"] for b in public}
    private_tips = hidden - {blocks[b]["parent_id"] for b in hidden}
    require(terminal["public_frontier"] == sorted(public_tips)
            and terminal["private_frontier"] == sorted(private_tips), "frontier mismatch")
    require(set(terminal["target_private_chain"]) <= hidden
            and set(terminal["abandoned_private"]) <= hidden, "private storage mismatch")
    require(terminal["pending_visibility_block"] is None
            or terminal["pending_visibility_block"] in public, "pending visibility mismatch")
    branches = terminal["alternative_branches"]
    require(len(branches) == len(public_tips) - 1 + len(private_tips)
            and {b["tip"] for b in branches} == (public_tips - {chain[-1]}) | private_tips,
            "missing alternative branch")
    for branch in branches:
        path, current = [], branch["tip"]
        while current is not None and current not in canonical:
            path.append(current)
            current = blocks[current]["parent_id"]
        height = blocks[current]["height"] if current is not None else 0
        require(branch["path"] == list(reversed(path)) and branch["common_ancestor"] == current
                and branch["common_ancestor_height"] == height
                and branch["canonical_blocks_exposed"] == n - height
                and branch["height"] == blocks[branch["tip"]]["height"], "branch ancestry/exposure mismatch")
        require(branch["visibility"] == ("public" if branch["tip"] in public else "private"),
                "branch visibility mismatch")
    require(set(result["actors"]) == set(miners), "actor population mismatch")
    for actor, miner in miners.items():
        a = result["actors"][actor]
        require(a["role"] == miner.role and a["hash_power"] == miner.hash_power, "actor identity mismatch")
        require((a["discovered"], a["accepted"], a["public_noncanonical"], a["orphaned"], a["unresolved"])
                == (discovered[actor], credited[actor], noncanonical[actor], noncanonical[actor], private[actor]),
                "actor block accounting mismatch")
        require(math.isclose(a["payoff"], credited[actor] / n, rel_tol=0, abs_tol=1e-15)
                and math.isclose(a["normalized_revenue"], credited[actor] / n / miner.hash_power,
                                 rel_tol=1e-14, abs_tol=1e-15), "payoff mismatch")
    published_order = []
    for index, batch in enumerate(result["publication_batches"], 1):
        require(batch["batch"] == index and bool(batch["blocks"]), "invalid release batch")
        for bid in batch["blocks"]:
            require(bid in public and blocks[bid]["release_batch"] == index
                    and blocks[bid]["publication_kind"] == batch["kind"]
                    and blocks[bid]["discovery_sequence"] <= batch["discovery_event"] <= events,
                    "release provenance mismatch")
        published_order.extend(batch["blocks"])
    require(len(published_order) == len(public) and set(published_order) == public
            and [blocks[b]["publication_sequence"] for b in published_order]
            == list(range(1, len(public) + 1)), "publication order/coverage mismatch")
    if isinstance(rule, SelfishCounterSpec):
        active = validate_selfish(result, blocks, public, population, flagged, coalition, require)
        method = "multi-selfish-complete-frontier-conservative-v1"
    elif isinstance(rule, OstracismSpec):
        active = validate_ostracism(result, blocks, public, canonical, flagged, coalition, require)
        method = "ostracism-complete-frontier-conservative-v1"
    else:
        active = terminal["retaliation"]
        method = "complete-frontier-conservative-v1"
    unresolved = bool(branches or active or terminal["pending_visibility_block"])
    require(terminal["boundary"]["method"] == method
            and terminal["boundary"]["potentially_material"] == unresolved, "boundary diagnostic mismatch")


def validate_ostracism(result, blocks, public, canonical, flagged, coalition, require):
    """Reconstruct rejected ancestry from raw publication facts, not policy code."""
    terminal = result["terminal"]
    armed = bool(flagged and coalition)
    state = terminal["retaliation"]
    require(state["activation_publication_sequence"] == (0 if armed else None),
            "nonstandard ostracism activation boundary")
    published = sorted(public, key=lambda b: blocks[b]["publication_sequence"])
    roots, minimal, rejected_by, root_events = [], set(), {}, []
    for bid in published:
        b = blocks[bid]
        root = rejected_by.get(b["parent_id"])
        if armed and b["owner_id"] == "target":
            roots.append(bid)
            if root is None:
                minimal.add(bid)
                root = bid
            root_events.append({"outcome": "REJECTED_TARGET_ROOT", "root": bid,
                "first_rejected_ancestor": root, "publication_sequence": b["publication_sequence"],
                "release_batch": b["release_batch"]})
        if root is not None:
            rejected_by[bid] = root
    eligible = public - set(rejected_by)
    frontier = (eligible - {blocks[b]["parent_id"] for b in eligible}) or {None}
    best_height = max(blocks[b]["height"] if b is not None else 0 for b in frontier)
    rejected_frontier = set(terminal["public_frontier"]) & set(rejected_by)
    competing = {rejected_by[b] for b in rejected_frontier if blocks[b]["height"] == result["accepted_blocks"]}
    expected_state = {"punishment_rule": "ignore", "armed": armed,
        "activation_publication_sequence": 0 if armed else None,
        "rejected_roots": sorted(roots), "minimal_rejected_roots": sorted(minimal),
        "competing_rejected_roots": sorted(competing), "conflict_active": bool(competing),
        "eligible_public_frontier": sorted(frontier, key=lambda b: -1 if b is None else b),
        "rejected_public_frontier": sorted(rejected_frontier), "best_eligible_height": best_height,
        "reference_rejected": terminal["reference_tip"] in rejected_by,
        "reference_height_minus_best_eligible_height": result["accepted_blocks"] - best_height}
    require(state == expected_state, "ostracism roots/eligibility/state mismatch")
    require(not armed or all(blocks[b]["owner_id"] not in coalition for b in rejected_by),
            "active member extended rejected ancestry")
    require([r for r in result["episodes"] if r["outcome"] == "REJECTED_TARGET_ROOT"] == root_events,
            "ostracism root publication history mismatch")
    require(all(r["outcome"] in {"REJECTED_TARGET_ROOT", "CONFLICT_OPENED", "CONFLICT_NO_LONGER_LEADING"}
                for r in result["episodes"]), "invalid ostracism transition/capitulation")
    require(result["member_activations"] == ({actor: len(roots) for actor in coalition} if roots else {}),
            "ostracism activation accounting mismatch")
    expected_frontier = []
    for tip in expected_state["eligible_public_frontier"]:
        current, path = tip, []
        while current is not None and current not in canonical:
            path.append(current)
            current = blocks[current]["parent_id"]
        height = blocks[current]["height"] if current is not None else 0
        expected_frontier.append({"tip": tip, "height": blocks[tip]["height"] if tip is not None else 0,
            "common_ancestor": current, "common_ancestor_height": height, "path": list(reversed(path)),
            "canonical_blocks_exposed": result["accepted_blocks"] - height})
    require(terminal["ostracism_eligible_frontier"] == expected_frontier, "ostracism eligible frontier mismatch")
    for branch in terminal["alternative_branches"]:
        tip = branch["tip"]
        while tip is not None and tip not in public:
            tip = blocks[tip]["parent_id"]
        root = rejected_by.get(tip)
        require(branch["first_rejected_public_ancestor"] == root
                and branch["eligible_by_published_ancestry"] == (root is None), "branch rejection mismatch")
    boundary = terminal["boundary"]
    require(boundary["reference_rejected_by_active_coalition"] == expected_state["reference_rejected"]
            and boundary["best_eligible_height"] == best_height
            and boundary["reference_height_minus_best_eligible_height"] == result["accepted_blocks"] - best_height,
            "ostracism boundary deficit mismatch")
    require(boundary["max_exposed_canonical_blocks"] == max(
        b["canonical_blocks_exposed"] for b in [*expected_frontier, *terminal["alternative_branches"]]),
        "ostracism canonical exposure mismatch")
    unresolved = bool(terminal["alternative_branches"] or competing or terminal["pending_visibility_block"])
    require(boundary["actor_payoff_bounds"] == ({a: [0, 1] for a in result["actors"]} if unresolved else None)
            and boundary["future_reorganization_excluded"] == (False if unresolved else None),
            "ostracism conservative bounds mismatch")
    return bool(competing)


def checkpoint_schema(manifest):
    if manifest["model_version"] == SELFISH_MODEL_VERSION:
        return SELFISH_SCHEMA
    if manifest["model_version"] == MODEL_VERSION:
        return SCHEMA
    if manifest["model_version"] == IGNORE_MODEL_VERSION:
        return IGNORE_SCHEMA
    raise ValueError("unknown persistent checkpoint model")


def write_checkpoint(path, manifest, conditional_runs):
    payload = {"schema": checkpoint_schema(manifest), "manifest": manifest, "conditional_runs": conditional_runs}
    atomic_json(path, {**payload, "content_sha256": digest(payload)})


def read_checkpoint(path, manifest):
    payload = json.loads(Path(path).read_text())
    checksum = payload.pop("content_sha256", None)
    if set(payload) != {"schema", "manifest", "conditional_runs"} or payload["schema"] != checkpoint_schema(manifest):
        raise ValueError("persistent checkpoint schema mismatch; historical checkpoints are ineligible")
    if digest(payload) != checksum:
        raise ValueError("persistent checkpoint content digest mismatch")
    if canonical_json(payload["manifest"]) != canonical_json(manifest):
        raise ValueError("persistent checkpoint manifest mismatch (including model/rule/k/repetitions)")
    return payload["conditional_runs"]
