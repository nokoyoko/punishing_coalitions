"""Sufficient scientific records with explicit production-validation attestations.

These are completed-run results, not resumable engine states. A trajectory can
be regenerated from identity and checked against its canonical production hash.
The shard store authenticates validation receipts separately from checksums.
"""
from collections import Counter
from dataclasses import asdict
import hashlib
import math
from pathlib import Path
import platform

from .persistent_checkpoint import digest
from .persistent_v2 import condition_identity
from .persistent_v2_checkpoint import validate_run, require, same
from .persistent_v2_validation import (validation_context, validate_lightweight, attestation, validate_attestation, reaction_diagnostics)

SCHEMA = "persistent-scientific-condition-v2-compact-2"


def runtime_identity():
    root = Path(__file__).parent
    names = ("coalition", "persistent", "persistent_checkpoint", "persistent_study", "persistent_sweep",
             "ostracism", "selfish_counter", "selfish_strategy", "selfish_validation", "research_sweep",
             "stage_b_validation", "theory", "persistent_v2", "persistent_v2_index", "persistent_v2_policies",
             "persistent_v2_checkpoint", "persistent_v2_study", "persistent_v2_compact", "persistent_v2_shards",
             "persistent_v2_outputs", "persistent_v2_production", "persistent_v2_sweep", "persistent_v2_validation")
    return {"python": platform.python_version(), "sources": {
        name: hashlib.sha256((root / (name+".py")).read_bytes()).hexdigest() for name in names}}


def sequence_summary(values):
    return {"count": len(values), "sha256": digest(values)}


def ranges(values):
    return {"count": len(values), "min": min(values, default=None), "max": max(values, default=None),
            "sum": sum(values)}


def terminal_summary(terminal):
    """Keep exact existing bounds; summarize visualization/replay-only vectors."""
    branches = terminal["alternative_branches"]
    by_id = {b["id"]: b for b in terminal["canonical_blocks"]+terminal["frontier_blocks"]}
    frontier = {}
    for kind in ("public", "private"):
        ids = terminal[kind+"_frontier"]
        heights = [by_id[b]["height"] for b in ids]
        frontier[kind] = {**sequence_summary(ids), "height": ranges(heights),
            "reference_height_deficit": ranges([terminal["reference_height"]-h for h in heights]),
            "owners": dict(Counter(by_id[b]["owner_id"] for b in ids))}
    private = {}
    for actor, state in terminal["private_states"].items():
        private[actor] = {key: (sequence_summary(value) if isinstance(value, list) else value)
                         for key, value in state.items()}
    retaliation = terminal["retaliation"]
    if retaliation is not None:
        retaliation = {key: (sequence_summary(value) if isinstance(value, list) else value)
                       for key, value in retaliation.items()}
    result = {"schema": "persistent-terminal-science-summary-v2-1",
        "reference_tip": terminal["reference_tip"], "reference_height": terminal["reference_height"],
        "boundary": terminal["boundary"], "pending_publication_window": terminal["pending_publication_window"],
        "reaction_queue": terminal["reaction_queue"], "retaliation": retaliation,
        "frontier": frontier, "private_states": private, "terminal_sha256": digest(terminal),
        "canonical_chain": sequence_summary(terminal["canonical_chain"]),
        "alternative_branches": {**sequence_summary(branches),
            "common_ancestor_height": ranges([b["common_ancestor_height"] for b in branches]),
            "canonical_blocks_exposed": ranges([b["canonical_blocks_exposed"] for b in branches]),
            "path_length": ranges([len(b["path"]) for b in branches]),
            "canonical_rewards_exposed": {a: ranges([b["canonical_rewards_exposed"][a] for b in branches])
                for a in terminal["boundary"]["actor_payoff_bounds"] or {}}},
        "target_private_chain": sequence_summary(terminal["target_private_chain"]),
        "abandoned_private": sequence_summary(terminal["abandoned_private"])}
    if "ostracism_eligible_frontier" in terminal:
        eligible = terminal["ostracism_eligible_frontier"]
        result["ostracism_eligible_frontier"] = {**sequence_summary(eligible),
            "height": ranges([b["height"] for b in eligible]),
            "canonical_blocks_exposed": ranges([b["canonical_blocks_exposed"] for b in eligible])}
    return result


def extract_validated(result, producer, validation):
    """Internal: caller has performed exactly the checks attested by validation."""
    native = {k: v for k, v in result.items() if k not in ("public_events", "trace")}
    native["recording_mode"] = "production-v2"
    actors = result["actors"]
    terminal = terminal_summary(result["terminal"])
    return {"schema": SCHEMA, "identity": result["identity"], "condition_id": result["condition_id"],
        "producer": producer, "validation": validation,
        "status": result["status"], "events": result["events"], "accepted_blocks": result["accepted_blocks"],
        "actors": actors, "member_opportunities": result["member_opportunities"],
        "member_activations": result["member_activations"], "natural_pairs": result["natural_pairs"],
        "terminal": terminal, "rng": result["rng"], "native_result_sha256": digest(native),
        "accounting": {name: sum(a[name] for a in actors.values()) for name in ("discovered", "accepted", "orphaned", "unresolved")},
        "punishment": {"reaction_diagnostics": reaction_diagnostics(result),
            "episodes": sequence_summary(result["episodes"]),
            "outcomes": dict(Counter(e["outcome"] for e in result["episodes"])),
            "selfish_reactions": sequence_summary(result["selfish_reactions"]),
            "publication_batches": sequence_summary(result["publication_batches"]),
            "reorganizations": {**sequence_summary(result["reorganizations"]),
                "removed_depth": ranges([len(e["removed"]) for e in result["reorganizations"]])}}}


def compact_run(result, population, rule, repetition, strategy, flagged, coalition, producer):
    risks = validate_lightweight(result, population, rule, repetition, strategy, flagged, coalition)
    validate_run(result, population, rule, repetition, strategy, flagged, coalition)
    return extract_validated(result, producer, attestation(result["identity"], validation_context(), risks))


def validate_compact(record, population, rule, repetition, strategy, flagged, coalition, producer, context=None):
    """Strict scientific/schema checks; authenticated native receipt checked by store.

No compact checksum is represented as an independent proof of a mining trace.
Unauthenticated external summaries cannot enter the native shard store.
"""
    try:
        require(record["schema"] == SCHEMA and record["producer"] == producer, "compact schema/producer")
        identity = condition_identity(population, repetition, strategy, flagged, coalition, rule)
        same(record["identity"], identity, "compact identity")
        require(record["condition_id"] == digest(identity), "compact condition ID")
        require(record["status"] == "COMPLETE", "compact completion")
        validate_attestation(record, validation_context() if context is None else context)
        n, events = record["accepted_blocks"], record["events"]
        require(type(n) is int and type(events) is int and events >= n >= population.target_accepted_blocks, "compact horizon")
        actors = record["actors"]
        require(set(actors) == {m.id for m in population.miners}, "compact actor coverage")
        for miner in population.miners:
            a = actors[miner.id]
            require(a["role"] == miner.role and a["hash_power"] == miner.hash_power, "compact actor identity")
            require(all(type(a[k]) is int and a[k] >= 0 for k in ("discovered", "accepted", "orphaned", "unresolved")), "compact counts")
            require(a["discovered"] == a["accepted"]+a["orphaned"]+a["unresolved"], "compact actor conservation")
            require(a["public_noncanonical"] == a["orphaned"] and a["payoff"] == a["accepted"]/n
                    and a["normalized_revenue"] == a["payoff"]/miner.hash_power, "compact payoff")
        totals = {k: sum(a[k] for a in actors.values()) for k in ("discovered", "accepted", "orphaned", "unresolved")}
        require(record["accounting"] == totals and totals["discovered"] == events and totals["accepted"] == n, "compact global conservation")
        t = record["terminal"]
        require(t["schema"] == "persistent-terminal-science-summary-v2-1" and t["reference_height"] == n
                and t["canonical_chain"]["count"] == n and not t["reaction_queue"], "compact terminal")
        boundary = t["boundary"]
        if boundary["potentially_material"]:
            require(boundary["actor_payoff_bounds"] == {a: [0., 1.] for a in actors}
                    and boundary["future_reorganization_excluded"] is False, "compact conservative bounds")
        else:
            require(boundary["actor_payoff_bounds"] is None, "compact nonmaterial bounds")
        require(0 <= boundary["max_exposed_canonical_blocks"] <= n, "compact exposed height")
        require(record["rng"]["discoveries"]["draw_count"] == events, "compact discovery draws")
        require(len(record["native_result_sha256"]) == len(t["terminal_sha256"]) == 64, "compact trajectory hashes")
        # Canonical serialization rejects NaN/Inf, including nested diagnostics.
        digest(record)
    except (KeyError, TypeError, AttributeError, ZeroDivisionError) as exc:
        raise ValueError("malformed compact v2 result") from exc


def analysis_record(record):
    return {**record, "_raw_result_digest": record["native_result_sha256"],
        "terminal_private_lead": record["terminal"]["target_private_chain"]["count"],
        "terminal_uncredited_private_blocks": record["terminal"]["frontier"]["private"]["count"],
        "terminal_omitted_selfish_share_bound": None}


def rerun_condition(record, *, trace=False, context=None):
    """Explicit audit mining only: regenerate and compare a compact condition."""
    from .coalition import Population
    from .persistent_v2 import Rule, PersistentSimulation
    identity = record["identity"]
    values = dict(identity["population"])
    values["candidates"] = tuple(tuple(x) for x in values["candidates"])
    population = Population(**values)
    rule = Rule(**identity["rule"]) if identity["flagged"] else Rule("petty")
    condition = (identity["repetition"], identity["strategy"], identity["flagged"], tuple(identity["active_coalition"]))
    producer = digest(runtime_identity())
    validate_compact(record, population, rule, *condition, producer, context)
    raw = PersistentSimulation(population, condition[1], condition[2], condition[3], rule,
        repetition=condition[0], production=not trace, trace_mode=trace).run()
    regenerated = compact_run(raw, population, rule, *condition, producer)
    # A deterministic audit can fully replay a formerly lightweight condition.
    same({k: v for k, v in record.items() if k != "validation"},
         {k: v for k, v in regenerated.items() if k != "validation"}, "deterministic compact audit mismatch")
    return raw
