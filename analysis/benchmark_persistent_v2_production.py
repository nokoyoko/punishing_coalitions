"""Fixed, tiny LOCAL performance diagnostic; never reads a sweep configuration.

Run with python -m analysis.benchmark_persistent_v2_production after correctness
tests. Each measurement runs in a fresh local subprocess for peak RSS. The only
30,000-block runs are the twelve fixed SC cases below, one repetition each.
"""
import hashlib
import json
from pathlib import Path
import platform
import resource
import subprocess
import sys
from time import perf_counter

from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import canonical_json, digest

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = (("petty", None), ("counter_fork", 1), ("counter_fork", 2),
            ("counter_fork", 3), ("ignore", None), ("selfish", None))


def rss_bytes():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)


def measure(case):
    mode, name, k, rate, horizon = case
    if (mode not in ("before", "debug", "production") or (name, k) not in VARIANTS
            or rate not in (0, .02) or horizon not in (500, 30000)
            or (horizon == 30000 and mode != "production") or (mode == "before" and name == "petty")):
        raise ValueError("only the fixed local benchmark matrix is allowed")
    if mode == "before":
        from analysis import _persistent_v2_reference as engine
        from analysis import _persistent_v2_reference_checkpoint as checkpoint
    else:
        from punishment_sim import persistent_v2 as engine
        from punishment_sim import persistent_v2_checkpoint as checkpoint
    population = Population(.2, (("c1", .1), ("c2", .1)), .5, rate, horizon, 701)
    rule = engine.Rule(name, k)
    options = {"production": mode == "production"} if mode != "before" else {}
    sim = engine.PersistentSimulation(population, "selfish", True, ("c1", "c2"), rule, **options)
    counters = {"eligibility_seconds": 0., "fork_choice_seconds": 0., "terminal_report_seconds": 0.}
    peak = {"public_frontier": 0, "private_blocks": 0, "active_private_actors": 0, "private_lead": 0}

    def timed(original, key):
        def call(*args, **kwargs):
            start = perf_counter()
            value = original(*args, **kwargs)
            counters[key] += perf_counter()-start
            return value
        return call

    original_eligible = engine.eligible_tips
    engine.eligible_tips = timed(original_eligible, "eligibility_seconds")
    sim.choose_among_tips = timed(sim.choose_among_tips, "fork_choice_seconds")
    sim.report = timed(sim.report, "terminal_report_seconds")
    original_step = sim.step

    def step():
        value = original_step()
        peak["public_frontier"] = max(peak["public_frontier"], len(sim.public_tips))
        states = list(sim.selfish.states.values())
        peak["private_blocks"] = max(peak["private_blocks"], sum(len(s.private_chain) for s in states))
        peak["active_private_actors"] = max(peak["active_private_actors"], sum(bool(s.private_chain) for s in states))
        peak["private_lead"] = max(peak["private_lead"], *(sim.height(s.private_chain[-1])-sim.public_height
                                    for s in states if s.private_chain), 0)
        return value

    sim.step = step
    start = perf_counter()
    result = sim.run()
    runtime = perf_counter()-start
    engine.eligible_tips = original_eligible
    if result["status"] != "COMPLETE":
        raise AssertionError(result["error"] or result["status"])
    engine_rss = rss_bytes()
    start = perf_counter()
    checkpoint.validate_run(result, population, rule, 0, "selfish", True, ("c1", "c2"))
    validation = perf_counter()-start
    validation_rss = rss_bytes()
    start = perf_counter()
    if mode == "before":
        payload = {"schema": checkpoint.CONDITIONAL_SCHEMA, "identity": result["identity"], "result": result}
        payload["content_sha256"] = digest(payload)
        encoded = (canonical_json(payload)+"\n").encode()
    else:
        encoded = checkpoint.encode_checkpoint(result)
    encoding = perf_counter()-start
    checkpoint_bytes = len(encoded)
    del encoded
    start = perf_counter()
    result_bytes = canonical_json(result).encode()
    result_serialization = perf_counter()-start
    result_hash, result_size = hashlib.sha256(result_bytes).hexdigest(), len(result_bytes)
    del result_bytes
    terminal = result["terminal"]
    normalized = {key: value for key, value in result.items() if key not in ("public_events", "recording_mode")}
    timings = {**counters, "run_seconds": runtime, "mining_seconds": runtime-counters["terminal_report_seconds"],
        "validation_seconds": validation, "checkpoint_encoding_seconds": encoding,
        "result_json_serialization_seconds": result_serialization}
    timings["eligibility_and_choice_percent_of_mining"] = 100*(counters["eligibility_seconds"]+
        counters["fork_choice_seconds"])/timings["mining_seconds"]
    return {"mode": mode, "rule": name, "k": k, "lambda": rate, "horizon": horizon, "seed": 701,
        "repetition": 0, "condition": "SC", "status": result["status"], **timings,
        "discovered_blocks": sim.events, "reference_blocks": sim.public_height,
        "public_frontier": len(sim.public_tips), "retained_blocks": len(sim.blocks),
        "peak_after_completed_events": peak,
        "private_blocks_at_horizon": sum(len(s.private_chain) for s in sim.selfish.states.values()),
        "reorganizations": len(sim.reorganizations),
        "max_reorganization_depth": max((len(r["removed"]) for r in sim.reorganizations), default=0),
        "unresolved_boundary": terminal["boundary"], "pending_window": terminal["pending_publication_window"],
        "active_punishment_at_horizon": sim.policy.active,
        "private_states_at_horizon": sim.state_snapshots(),
        "raw_event_rows_retained": len(sim.public_events), "full_trace_rows_retained": 0,
        "result_json_bytes": result_size, "checkpoint_bytes": checkpoint_bytes,
        "peak_rss_after_run_bytes": engine_rss, "peak_rss_after_validation_bytes": validation_rss,
        "peak_rss_after_serialization_bytes": rss_bytes(),
        "result_sha256": result_hash, "scientific_sha256": digest(normalized)}


def source_hashes():
    paths = [*sorted((ROOT / "punishment_sim").glob("*.py")),
             *sorted((ROOT / "tests/fixtures").glob("*persistent*")),
             *sorted((ROOT / "analysis").glob("*persistent_v2*.py")),
             ROOT / "configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_1pct.json"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    initial = source_hashes()
    rows = []
    matrix = [(mode, name, k, rate, 500) for name, k in VARIANTS for rate in (0, .02)
              for mode in (("debug", "production") if name == "petty" else ("before", "debug", "production"))]
    matrix += [("production", name, k, rate, 30000) for name, k in VARIANTS for rate in (0, .02)]
    for case in matrix:
        completed = subprocess.run([sys.executable, "-m", "analysis.benchmark_persistent_v2_production", "--case", json.dumps(case)],
                                   cwd=ROOT, check=True, text=True, capture_output=True)
        row = json.loads(completed.stdout)
        rows.append(row)
        print(f"{case}: run={row['run_seconds']:.3f}s validate={row['validation_seconds']:.3f}s", flush=True)
    for name, k in VARIANTS:
        for rate in (0, .02):
            group = [r for r in rows if (r["rule"], r["k"], r["lambda"], r["horizon"]) == (name, k, rate, 500)]
            assert len({r["scientific_sha256"] for r in group}) == 1
            debug = [r for r in group if r["mode"] != "production"]
            assert len({r["result_sha256"] for r in debug}) == 1
    final = source_hashes()
    assert initial == final
    old = json.loads((ROOT / "docs/persistent_baseline_audit_evidence.json").read_text())["engine_sha256"]
    assert all(final[path] == value for path, value in old.items())
    scope = {"configurations_per_variant": 250170, "repetitions": 20, "single_variant_runs": 39934200,
             "variants": 6, "independent_runs": 239605200, "shared_baseline_runs": 10006800,
             "saved_runs": 50034000, "remaining_runs": 189571200,
             "nominal_accepted_block_work": 5687136000000,
             "saved_fraction": 50034000/239605200, "baseline_saved_fraction": 5/6}
    evidence = {"purpose": "fixed local performance diagnostic, not scientific inference or a production sweep",
        "python": sys.version, "platform": platform.platform(), "population": {"target": .2, "c1": .1, "c2": .1, "residual": .6},
        "gamma": .5, "case_count_30000": 12, "measurements_per_case": 1,
        "method": "fresh subprocess per case; perf_counter wrappers and post-event peak counters included in mining time; no full traces; peak RSS includes Python and validator/serialization allocations; encoding times exclude disk I/O",
        "small_case_exact_output_equality": True, "historical_v1_source_hashes_match_prior_audit": True,
        "source_hashes_before_and_after": initial, "six_variant_scope": scope, "measurements": rows,
        "production_sweep_launched": False, "remote_job_launched": False, "ssh": False, "xtra_access": False}
    path = ROOT / "docs/persistent_v2_production_benchmark.json"
    path.write_text(json.dumps(evidence, indent=2, allow_nan=False)+"\n")
    print(path)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--case":
        print(json.dumps(measure(json.loads(sys.argv[2])), allow_nan=False))
    elif len(sys.argv) == 1:
        main()
    else:
        raise SystemExit("only the fixed local matrix or a validated fixed --case is supported")
