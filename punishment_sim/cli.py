from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .config import SimulationConfig
from .experiments import aggregate, compare, sweep
from .simulation import Simulation
from .smoke import run_smoke
from .coalition import config_id, population_from_dict, study, subsets
from .transition import build_transition_report
from .followup import build_equal_hash_report, build_marginal_report
from .research_sweep import dry_run as research_dry_run, run_sweep
from .sharded_sweep import build_manifest, merge_shards, run_shard
from .theory import selfish_revenue


def _t95(df: int) -> float:
    """Two-sided 95% Student-t critical values; normal limit above 30."""
    values = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
              6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
              11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
              16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
              21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
              26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}
    return values.get(df, 1.96)


def _write(data, path: str | None) -> None:
    text = json.dumps(data, indent=2)
    if path:
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text + "\n")
    else:
        print(text)


def _csv(rows: list[dict], path: str) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
        if rows: writer.writeheader(); writer.writerows(rows)

def _flat(rows):
    return [{k:(json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else v) for k,v in r.items()} for r in rows]

def _coalition_outputs(result, summary, member, repetition, detector=None):
    _csv(_flat(result["summary"]),summary); _csv(_flat(result["members"]),member)
    _csv(_flat(result["repetitions"]),repetition)
    if detector: _csv(_flat(result["detector"]),detector)
    Path(summary).with_suffix(".json").write_text(json.dumps(result,indent=2)+"\n")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="punishment-sim")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "compare"):
        p = sub.add_parser(command); p.add_argument("--config", required=True); p.add_argument("--output")
    p = sub.add_parser("sweep"); p.add_argument("--config", required=True); p.add_argument("--output", required=True); p.add_argument("--aggregate")
    p = sub.add_parser("validate"); p.add_argument("--config", required=True); p.add_argument("--output", required=True)
    p = sub.add_parser("smoke-test"); p.add_argument("--output", default="results/smoke_report.json"); p.add_argument("--trace-output", default="results/smoke_traces.jsonl")
    p = sub.add_parser("coalition-study"); p.add_argument("--config",required=True); p.add_argument("--summary-output",required=True); p.add_argument("--member-output",required=True); p.add_argument("--repetition-output",required=True); p.add_argument("--detector-output")
    p = sub.add_parser("coalition-sweep"); p.add_argument("--config",required=True); p.add_argument("--output-dir",default="results/coalition_sweep"); p.add_argument("--dry-run",action="store_true")
    p = sub.add_parser("transition-report"); p.add_argument("--zero-json",required=True); p.add_argument("--natural-json",required=True); p.add_argument("--output-dir",required=True)
    p = sub.add_parser("marginal-report"); p.add_argument("--input-json",required=True); p.add_argument("--output-dir",required=True)
    p = sub.add_parser("equal-hash-report"); p.add_argument("--zero-json",required=True); p.add_argument("--natural-json",required=True); p.add_argument("--output-dir",required=True)
    p = sub.add_parser("research-sweep"); p.add_argument("--config",required=True); p.add_argument("--output-dir",required=True); p.add_argument("--dry-run",action="store_true")
    p = sub.add_parser("research-shard-plan"); p.add_argument("--config",required=True); p.add_argument("--output-dir",required=True); p.add_argument("--num-shards",type=int,required=True)
    p = sub.add_parser("research-shard-run"); p.add_argument("--config",required=True); p.add_argument("--output-dir",required=True); p.add_argument("--workers",type=int,default=28); p.add_argument("--num-shards",type=int,default=1); p.add_argument("--shard-index",type=int)
    p = sub.add_parser("research-shard-merge"); p.add_argument("--config",required=True); p.add_argument("--output-dir",required=True); p.add_argument("--num-shards",type=int,required=True)
    args = parser.parse_args(argv)
    if args.command in {"run", "compare"}:
        cfg = SimulationConfig.from_file(args.config)
        data = Simulation(cfg).run() if args.command == "run" else compare(cfg)
        _write(data, args.output or cfg.output_path)
    elif args.command == "sweep":
        spec = json.loads(Path(args.config).read_text()); rows = sweep(spec); _csv(rows, args.output)
        if args.aggregate: _csv(aggregate(rows), args.aggregate)
    elif args.command == "validate":
        spec = json.loads(Path(args.config).read_text()); rows = []
        for alpha in spec["target_hash_power"]:
            for gamma in spec["gamma"]:
                samples = []
                for rep in range(spec.get("repetitions", 5)):
                    cfg = SimulationConfig(target_hash_power=alpha, coalition_hash=0, gamma=gamma,
                        target_accepted_blocks=spec.get("target_accepted_blocks", 100000),
                        seed=spec.get("seed", 100)+rep, strategy="selfish", punishment_enabled=False)
                    samples.append(Simulation(cfg).run()["actors"]["target"]["accepted_revenue_share"])
                summary = aggregate([{"target_hash_power": alpha, "coalition_hash": 0, "gamma": gamma,
                    "tpr": 0, "fpr": 0, "natural_fork_rate": 0,
                    "unpunished_selfish_target_share": x} for x in samples],
                    metric="unpunished_selfish_target_share")[0]
                critical = _t95(len(samples)-1) if len(samples) > 1 else None
                low = summary["mean"] - critical*summary["standard_error"] if critical else None
                high = summary["mean"] + critical*summary["standard_error"] if critical else None
                rows.append({"target_hash_power": alpha, "gamma": gamma, "analytic": selfish_revenue(alpha, gamma),
                    "simulated_mean": summary["mean"], "standard_error": summary["standard_error"],
                    "ci_method": "student_t", "ci95_low": low, "ci95_high": high})
        _csv(rows, args.output)
    elif args.command == "smoke-test":
        report = run_smoke(args.output, args.trace_output)
        print(json.dumps(report, indent=2))
        if report["status"] != "PASS":
            raise SystemExit(1)
    elif args.command == "coalition-study":
        spec=json.loads(Path(args.config).read_text()); pop=population_from_dict(spec)
        result=study(pop,int(spec.get("repetitions",5)),spec.get("tpr",[.9]),spec.get("fpr",[.01]),
                     spec.get("selfish_prior"),spec.get("active_coalitions"))
        _coalition_outputs(result,args.summary_output,args.member_output,args.repetition_output,args.detector_output)
    elif args.command == "coalition-sweep":
        spec=json.loads(Path(args.config).read_text()); populations=spec.get("populations",[])
        reps=int(spec.get("repetitions",3)); tprs=spec.get("tpr",[.9]); fprs=spec.get("fpr",[.01])
        counts=[]
        for p in populations:
            m=len(population_from_dict(p).candidates); counts.append({"configuration_id":config_id(p),
                "coalitions":2**m,"conditional_mining_simulations":(2+2*(2**m-1))*reps,
                "shared_baselines":2*reps,"detector_evaluations":2**m*len(tprs)*len(fprs),
                "estimated_summary_rows":2**m})
        if args.dry_run: print(json.dumps({"population_configurations":len(populations),"counts":counts},indent=2)); return
        out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
        manifest=[]
        for p in populations:
            cid=config_id(p); result=study(population_from_dict(p),reps,tprs,fprs,
                                           spec.get("selfish_prior"),spec.get("active_coalitions"))
            _coalition_outputs(result,str(out/f"{cid}_summary.csv"),str(out/f"{cid}_members.csv"),str(out/f"{cid}_repetitions.csv"),str(out/f"{cid}_detector.csv"))
            manifest.append({"configuration_id":cid,**result["meta"]})
        (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    elif args.command == "transition-report":
        report=build_transition_report(args.zero_json,args.natural_json,args.output_dir)
        print(json.dumps({"coalition_rows":len(report["coalitions"]),"member_rows":len(report["members"]),
                          "production_recommendations":len(report["production_recommendations"])},indent=2))
    elif args.command == "marginal-report":
        report=build_marginal_report(args.input_json,args.output_dir)
        print(json.dumps({"conditions":len(report["conditions"])},indent=2))
    elif args.command == "equal-hash-report":
        report=build_equal_hash_report(args.zero_json,args.natural_json,args.output_dir)
        print(json.dumps({"coalition_rows":len(report["coalitions"]),"member_rows":len(report["members"]),
                          "direct_comparisons":len(report["direct_comparisons"])},indent=2))
    elif args.command=="research-shard-plan":
        spec=json.loads(Path(args.config).read_text());_,summary=build_manifest(spec,args.output_dir,args.num_shards);print(json.dumps(summary,indent=2))
    elif args.command=="research-shard-run":
        spec=json.loads(Path(args.config).read_text());print(json.dumps(run_shard(spec,args.output_dir,args.workers,args.num_shards,args.shard_index),indent=2))
    elif args.command=="research-shard-merge":
        spec=json.loads(Path(args.config).read_text());print(json.dumps(merge_shards(spec,args.output_dir,args.num_shards),indent=2))
    else:
        spec=json.loads(Path(args.config).read_text())
        if args.dry_run:
            estimate=research_dry_run(spec); plan_dir=Path(args.output_dir); plan_dir.mkdir(parents=True,exist_ok=True)
            (plan_dir/"dry_run_estimates.json").write_text(json.dumps(estimate,indent=2)+"\n")
            _csv([estimate],str(plan_dir/"dry_run_estimates.csv"))
            print(json.dumps(estimate,indent=2))
        else:
            result=run_sweep(spec,args.output_dir)
            print(json.dumps(result["cache_audit"],indent=2))


if __name__ == "__main__":
    main()
