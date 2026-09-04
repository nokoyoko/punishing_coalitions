from __future__ import annotations
import csv, json
from pathlib import Path
from .coalition import ExplicitSimulation, Population

def _write_csv(path, rows):
    if not rows:return
    with Path(path).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def build_transition_report(zero_json, natural_json, output_dir):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    datasets=[(0.0,json.loads(Path(zero_json).read_text())),(.02,json.loads(Path(natural_json).read_text()))]
    coalitions=[]; members=[]; variance=[]; recommendations=[]; equal=[]
    for rate,data in datasets:
        byc={x["coalition"]:x for x in data["summary"]}; bym={}
        for x in data["members"]: bym[(x["coalition"],x["member_id"])]=x
        reps={c:[r for r in data["repetitions"] if r["coalition"]==c] for c in byc}
        for c,x in sorted(byc.items()):
            natural={}
            for r in reps[c]:
                for pair,n in r["selfish_natural_pairs"].items():natural[pair]=natural.get(pair,0)+n
            coalitions.append({"natural_fork_rate":rate,"coalition":c,"active_hash_power":x["active_hash_power"],
                "target_honest":x["target_honest"],"target_unpunished_selfish":x["target_unpunished_selfish"],
                "target_punished":x["target_punished"],"deterrence_mean":x["deterrence"]["mean"],
                "deterrence_ci_low":x["deterrence"]["ci95_low"],"deterrence_ci_high":x["deterrence"]["ci95_high"],
                "punishment_reduction_mean":x["punishment_reduction"]["mean"],
                "punishment_reduction_ci_low":x["punishment_reduction"]["ci95_low"],
                "punishment_reduction_ci_high":x["punishment_reduction"]["ci95_high"],
                "effectiveness_status":x["effectiveness_status"],"baseline_credible":x["baseline_credible"],
                "deviation_proof":x["deviation_proof"],"winning":x["winning"],
                "weakest_member":x["weakest_member"],"minimum_member_deviation_margin":x["minimum_member_deviation_margin"],
                "selfish_natural_pairs":json.dumps(natural,sort_keys=True)})
            for metric in ("deterrence","punishment_reduction"):
                s=x[metric]; variance.append({"natural_fork_rate":rate,"coalition":c,"member":"","metric":metric,
                    "paired_variance":s["paired_variance"],"independent_variance_estimate":s["independent_variance_estimate"],
                    "crn_variance_reduction":s["crn_variance_reduction"],"crn_increased_variance":s["crn_increased_variance"]})
                if s["ci95_low"]<=0<=s["ci95_high"]: recommendations.append({"natural_fork_rate":rate,"coalition":c,"member":"","metric":metric,"ci":[s["ci95_low"],s["ci95_high"]]})
        for (c,j),x in sorted(bym.items()):
            members.append({"natural_fork_rate":rate,"coalition":c,"member":j,"member_hash_power":x["member_hash_power"],
                "U_S_empty":x["U_S0"],"U_S_C":x["U_SC"],"U_S_leaveout":x["U_leaveout"],
                "baseline_mean":x["baseline"]["mean"],"baseline_sd":x["baseline"]["sample_sd"],"baseline_se":x["baseline"]["standard_error"],
                "baseline_ci_low":x["baseline"]["ci95_low"],"baseline_ci_high":x["baseline"]["ci95_high"],
                "baseline_sign":x["baseline_point_sign"],"baseline_status":x["baseline_status"],
                "deviation_mean":x["deviation"]["mean"],"deviation_sd":x["deviation"]["sample_sd"],"deviation_se":x["deviation"]["standard_error"],
                "deviation_ci_low":x["deviation"]["ci95_low"],"deviation_ci_high":x["deviation"]["ci95_high"],
                "deviation_sign":x["deviation_point_sign"],"deviation_status":x["deviation_status"],
                "opportunities":x["opportunities"],"activations":x["activations"]})
            for metric in ("baseline","deviation"):
                s=x[metric]; variance.append({"natural_fork_rate":rate,"coalition":c,"member":j,"metric":metric,
                    "paired_variance":s["paired_variance"],"independent_variance_estimate":s["independent_variance_estimate"],
                    "crn_variance_reduction":s["crn_variance_reduction"],"crn_increased_variance":s["crn_increased_variance"]})
                if s["ci95_low"]<=0<=s["ci95_high"]: recommendations.append({"natural_fork_rate":rate,"coalition":c,"member":j,"metric":metric,"ci":[s["ci95_low"],s["ci95_high"]]})
        a,b=byc["c3"],byc["c1|c2"]
        equal.append({"natural_fork_rate":rate,"c3_deterrence":a["deterrence"]["mean"],"c1_c2_deterrence":b["deterrence"]["mean"],
            "deterrence_difference":a["deterrence"]["mean"]-b["deterrence"]["mean"],
            "c3_reduction":a["punishment_reduction"]["mean"],"c1_c2_reduction":b["punishment_reduction"]["mean"],
            "c3_baseline_credible":a["baseline_credible"],"c1_c2_baseline_credible":b["baseline_credible"],
            "c3_deviation_proof":a["deviation_proof"],"c1_c2_deviation_proof":b["deviation_proof"],
            "c3_opportunities":sum(x["opportunities"] for (c,j),x in bym.items() if c=="c3"),
            "c1_c2_opportunities":sum(x["opportunities"] for (c,j),x in bym.items() if c=="c1|c2"),
            "c3_natural_exposure":json.dumps([r["selfish_natural_pairs"] for r in reps["c3"]]),
            "c1_c2_natural_exposure":json.dumps([r["selfish_natural_pairs"] for r in reps["c1|c2"]])})
    _write_csv(out/"coalitions.csv",coalitions); _write_csv(out/"members.csv",members); _write_csv(out/"variance.csv",variance); _write_csv(out/"equal_hash.csv",equal)
    # Deterministic leave-one-out trace.
    p=Population(.25,(("c1",.05),("c2",.075),("c3",.1)),.5,0,2,999)
    traces=[]
    for label,C in (("C_c1_c3",("c1","c3")),("C_without_c1",("c3",))):
        r=ExplicitSimulation(p,"selfish",True,C,["target","honest_residual","c1"],True).run()
        traces.extend({"scenario":label,"c1_hash_power":r["actors"]["c1"]["hash_power"],"c1_reward":r["actors"]["c1"]["accepted"],**x} for x in r["trace"])
    (out/"leave_one_out_trace.jsonl").write_text("".join(json.dumps(x)+"\n" for x in traces))
    report={"coalitions":coalitions,"members":members,"equal_total_hash":equal,"variance":variance,
            "production_recommendations":recommendations,
            "leave_one_out_definition":"Q_c1({c1,c3}) = U_c1^(S,{c1,c3}) - U_c1^(S,{c3})"}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return report
