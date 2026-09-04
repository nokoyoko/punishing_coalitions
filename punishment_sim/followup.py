from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean

from .coalition import paired_stats, status


def _csv(path, rows):
    path = Path(path)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _load(path):
    return json.loads(Path(path).read_text())


def _sign(value):
    return "positive" if value > 0 else "negative" if value < 0 else "zero"


def _variance_row(rate, coalition, member, metric, stat):
    return {"natural_fork_rate": rate, "coalition": coalition, "member": member,
            "metric": metric, "paired_variance": stat["paired_variance"],
            "independent_variance_estimate": stat["independent_variance_estimate"],
            "crn_variance_reduction": stat["crn_variance_reduction"],
            "crn_increased_variance": stat["crn_increased_variance"]}


def build_marginal_report(input_json, output_dir):
    data = _load(input_json); out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    wanted = {"c1|c2", "c1|c3"}; summaries = {x["coalition"]: x for x in data["summary"]}
    members = {(x["coalition"], x["member_id"]): x for x in data["members"]}
    rows = []; repetitions = []; variance = []
    for coalition in sorted(wanted):
        member = members[(coalition, "c1")]
        condition_reps=[r for r in data["repetitions"] if r["coalition"] == coalition]
        left=[r["U_SC"]["c1"]["payoff"] for r in condition_reps]
        right=[r["leaveouts"]["c1"]["c1"]["payoff"] for r in condition_reps]
        q=paired_stats([a-b for a,b in zip(left,right)],left,right)
        rows.append({"natural_fork_rate": 0.0, "coalition": coalition, "deviating_member": "c1",
                     "U_S_C": member["U_SC"], "U_S_leaveout": member["U_leaveout"],
                     "Q_mean": q["mean"], "paired_sample_sd": q["sample_sd"],
                     "standard_error": q["standard_error"], "ci95_low": q["ci95_low"],
                     "ci95_high": q["ci95_high"], "point_sign": _sign(q["mean"]),
                     "status": status(q), "crn_variance_reduction": q["crn_variance_reduction"],
                     "punishment_opportunities": member["opportunities"],
                     "punishment_activations": member["activations"]})
        variance.append(_variance_row(0.0, coalition, "c1", "deviation", q))
        for r in condition_reps:
            left = r["U_SC"]["c1"]["payoff"]; right = r["leaveouts"]["c1"]["c1"]["payoff"]
            repetitions.append({"repetition": r["repetition"], "coalition": coalition,
                                "U_S_C": left, "U_S_leaveout": right, "Q": left-right,
                                "opportunities": r["member_opportunities"].get("c1", 0),
                                "activations": r["member_activations"].get("c1", 0)})
    report = {"population": data["population"], "conditions": rows, "variance": variance,
              "definition": "Q_c1^P(C)=U_c1^(S,C)-U_c1^(S,C\\{c1})"}
    _csv(out/"summary.csv", rows); _csv(out/"members.csv", rows)
    _csv(out/"repetitions.csv", repetitions); _csv(out/"variance.csv", variance)
    (out/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def _exposure(rows):
    total = {}
    for r in rows:
        for pair, count in r["selfish_natural_pairs"].items():
            total[pair] = total.get(pair, 0) + count
    return total


def build_equal_hash_report(zero_json, natural_json, output_dir):
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    coalition_rows=[]; member_rows=[]; repetition_rows=[]; variance=[]; comparisons=[]
    structured={"studies": [], "direct_comparisons": comparisons}
    for data in (_load(zero_json), _load(natural_json)):
        rate=data["population"]["natural_fork_rate"]
        by_summary={x["coalition"]:x for x in data["summary"]}
        by_member={(x["coalition"],x["member_id"]):x for x in data["members"]}
        by_reps={c:sorted((r for r in data["repetitions"] if r["coalition"]==c),key=lambda r:r["repetition"])
                 for c in ("c3","c1|c2")}
        study_record={"natural_fork_rate":rate,"coalitions":{}}
        weakest={}
        for coalition in ("c3","c1|c2"):
            summary=by_summary[coalition]; reps=by_reps[coalition]; ids=summary["members"]
            honest=[r["U_H"]["target"]["payoff"] for r in reps]
            selfish=[r["U_S0"]["target"]["payoff"] for r in reps]
            punished=[r["U_SC"]["target"]["payoff"] for r in reps]
            deterrence=paired_stats([a-b for a,b in zip(honest,punished)],honest,punished)
            reduction=paired_stats([a-b for a,b in zip(selfish,punished)],selfish,punished)
            agg=[sum(r["U_SC"][j]["payoff"] for j in ids) for r in reps]
            agg_stat=paired_stats(agg)
            member_set=[]
            for j in ids:
                m=by_member[(coalition,j)]; member_set.append(m)
                ujc=[r["U_SC"][j]["payoff"] for r in reps]
                uj0=[r["U_S0"][j]["payoff"] for r in reps]
                ujlo=[r["leaveouts"][j][j]["payoff"] for r in reps]
                baseline=paired_stats([a-b for a,b in zip(ujc,uj0)],ujc,uj0)
                deviation=paired_stats([a-b for a,b in zip(ujc,ujlo)],ujc,ujlo)
                m={**m,"baseline":baseline,"deviation":deviation,
                   "baseline_status":status(baseline),"deviation_status":status(deviation)}
                member_set[-1]=m
                member_rows.append({"natural_fork_rate":rate,"coalition":coalition,"member":j,
                    "member_hash_power":m["member_hash_power"],"U_S_empty":m["U_S0"],"U_S_C":m["U_SC"],
                    "U_S_leaveout":m["U_leaveout"],"baseline_mean":m["baseline"]["mean"],
                    "baseline_ci_low":m["baseline"]["ci95_low"],"baseline_ci_high":m["baseline"]["ci95_high"],
                    "baseline_status":m["baseline_status"],"deviation_mean":m["deviation"]["mean"],
                    "deviation_ci_low":m["deviation"]["ci95_low"],"deviation_ci_high":m["deviation"]["ci95_high"],
                    "deviation_status":m["deviation_status"],"opportunities":m["opportunities"],
                    "activations":m["activations"]})
                variance.append(_variance_row(rate,coalition,j,"baseline",m["baseline"]))
                variance.append(_variance_row(rate,coalition,j,"deviation",m["deviation"]))
            weak=min(member_set,key=lambda m:m["deviation"]["mean"]); weakest[coalition]=weak
            natural=_exposure(reps)
            row={"natural_fork_rate":rate,"coalition":coalition,"active_hash_power":summary["active_hash_power"],
                 "target_honest":summary["target_honest"],"target_unpunished_selfish":summary["target_unpunished_selfish"],
                 "target_punished":summary["target_punished"],"deterrence_mean":deterrence["mean"],
                 "deterrence_ci_low":deterrence["ci95_low"],"deterrence_ci_high":deterrence["ci95_high"],
                 "punishment_reduction_mean":reduction["mean"],
                 "punishment_reduction_ci_low":reduction["ci95_low"],
                 "punishment_reduction_ci_high":reduction["ci95_high"],
                 "aggregate_active_payoff_mean":agg_stat["mean"],"aggregate_active_payoff_ci_low":agg_stat["ci95_low"],
                 "aggregate_active_payoff_ci_high":agg_stat["ci95_high"],"credibility_slack":weak["deviation"]["mean"],
                 "weakest_member":weak["member_id"],"weakest_ci_low":weak["deviation"]["ci95_low"],
                 "weakest_ci_high":weak["deviation"]["ci95_high"],"credibility_status":weak["deviation_status"],
                 "opportunities":sum(m["opportunities"] for m in member_set),
                 "activations":sum(m["activations"] for m in member_set),
                 "natural_fork_exposure":json.dumps(natural,sort_keys=True)}
            coalition_rows.append(row); study_record["coalitions"][coalition]=row
            variance.append(_variance_row(rate,coalition,"","deterrence",deterrence))
            variance.append(_variance_row(rate,coalition,"","punishment_reduction",reduction))
            for r,aggregate in zip(reps,agg):
                repetition_rows.append({"natural_fork_rate":rate,"repetition":r["repetition"],"coalition":coalition,
                    "target_honest":r["U_H"]["target"]["payoff"],"target_unpunished_selfish":r["U_S0"]["target"]["payoff"],
                    "target_punished":r["U_SC"]["target"]["payoff"],"deterrence":r["U_H"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"],
                    "punishment_reduction":r["U_S0"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"],
                    "aggregate_active_payoff":aggregate,"natural_fork_exposure":json.dumps(r["selfish_natural_pairs"],sort_keys=True)})
        # Direct pairing uses the identical population, repetition seeds, and named streams.
        single=by_reps["c3"]; split=by_reps["c1|c2"]
        d_single=[r["U_H"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"] for r in single]
        d_split=[r["U_H"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"] for r in split]
        r_single=[r["U_S0"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"] for r in single]
        r_split=[r["U_S0"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"] for r in split]
        ws=weakest["c3"]; wp=weakest["c1|c2"]
        q_single=[r["U_SC"][ws["member_id"]]["payoff"]-r["leaveouts"][ws["member_id"]][ws["member_id"]]["payoff"] for r in single]
        q_split=[r["U_SC"][wp["member_id"]]["payoff"]-r["leaveouts"][wp["member_id"]][wp["member_id"]]["payoff"] for r in split]
        for metric,left,right,note in (("deterrence_single_minus_split",d_single,d_split,"direct paired"),
                                       ("reduction_single_minus_split",r_single,r_split,"direct paired"),
                                       ("slack_single_minus_split",q_single,q_split,"point-estimate weakest-member diagnostic")):
            stat=paired_stats([a-b for a,b in zip(left,right)],left,right)
            comparisons.append({"natural_fork_rate":rate,"metric":metric,"single_mean":mean(left),"split_mean":mean(right),
                "difference_mean":stat["mean"],"ci95_low":stat["ci95_low"],"ci95_high":stat["ci95_high"],
                "point_sign":_sign(stat["mean"]),"status":status(stat),"weakest_single":ws["member_id"] if metric.startswith("slack") else "",
                "weakest_split":wp["member_id"] if metric.startswith("slack") else "","interpretation_note":note,
                "paired_variance":stat["paired_variance"],"independent_variance_estimate":stat["independent_variance_estimate"],
                "crn_variance_reduction":stat["crn_variance_reduction"],"crn_increased_variance":stat["crn_increased_variance"]})
            variance.append(_variance_row(rate,"c3 minus c1|c2","",metric,stat))
        structured["studies"].append(study_record)
    structured["coalitions"]=coalition_rows; structured["members"]=member_rows; structured["variance"]=variance
    _csv(out/"summary.csv",coalition_rows); _csv(out/"members.csv",member_rows)
    _csv(out/"repetitions.csv",repetition_rows); _csv(out/"comparisons.csv",comparisons); _csv(out/"variance.csv",variance)
    (out/"report.json").write_text(json.dumps(structured,indent=2)+"\n")
    return structured
