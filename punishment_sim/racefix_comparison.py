from __future__ import annotations

import csv,json
from collections import Counter
from pathlib import Path


def read(path):
    with Path(path).open(newline="") as f:return list(csv.DictReader(f))


def write(path,rows):
    rows=list(rows); fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def stat(row,column):
    x=json.loads(row[column]);return x["mean"],x["ci95_low"],x["ci95_high"]


def generate(old_dir,new_dir,out_dir):
    old_dir=Path(old_dir);new_dir=Path(new_dir);out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    summary={"comparison_method":"descriptive matched-configuration differences; no old-vs-new paired confidence interval"}

    old=read(old_dir/"coalition_results.csv");new=read(new_dir/"coalition_results.csv")
    oi={(r["configuration_id"],r["coalition"]):r for r in old}; agg=[]; changes=Counter()
    for n in new:
        o=oi[(n["configuration_id"],n["coalition"])]
        for metric,status_col in (("deterrence","effectiveness_status"),("punishment_reduction",None)):
            om,ol,oh=stat(o,metric);nm,nl,nh=stat(n,metric)
            os=o[status_col] if status_col else ("SUPPORTED" if ol>0 else "REFUTED" if oh<0 else "INCONCLUSIVE")
            ns=n[status_col] if status_col else ("SUPPORTED" if nl>0 else "REFUTED" if nh<0 else "INCONCLUSIVE")
            changed=os!=ns;changes[f"{metric}_status_changed"]+=changed
            agg.append({"configuration_id":n["configuration_id"],"coalition":n["coalition"],"metric":metric,
                "target_hash_power":n["target_hash_power"],"gamma":n["gamma"],"natural_fork_rate":n["natural_fork_rate"],
                "structure":n["structure"],"active_hash_power":n["active_hash_power"],"old_estimate":om,"corrected_estimate":nm,
                "direct_difference":nm-om,"old_ci_low":ol,"old_ci_high":oh,"corrected_ci_low":nl,"corrected_ci_high":nh,
                "old_status":os,"corrected_status":ns,"qualitative_conclusion_changed":changed,"statistically_paired_version_comparison":False})
    write(out/"aggregate_metric_changes.csv",agg)

    old=read(old_dir/"member_credibility_refined.csv");new=read(new_dir/"member_credibility_refined.csv")
    oi={(r["configuration_id"],r["coalition"],r["member_id"]):r for r in old}; cred=[]
    for n in new:
        o=oi[(n["configuration_id"],n["coalition"],n["member_id"])]
        for metric in ("baseline","deviation"):
            om,ol,oh=stat(o,metric);nm,nl,nh=stat(n,metric); oc=o[f"{metric}_classification"];nc=n[f"{metric}_classification"]
            weak_changed=o[f"{metric}_weak_supported"]!=n[f"{metric}_weak_supported"]
            strict_changed=o[f"{metric}_strict_supported"]!=n[f"{metric}_strict_supported"]
            changes[f"{metric}_weak_status_changed"]+=weak_changed;changes[f"{metric}_strict_status_changed"]+=strict_changed
            cred.append({"configuration_id":n["configuration_id"],"coalition":n["coalition"],"member_id":n["member_id"],"metric":metric,
                "member_hash_power":n["member_hash_power"],"old_estimate":om,"corrected_estimate":nm,"direct_difference":nm-om,
                "old_ci_low":ol,"old_ci_high":oh,"corrected_ci_low":nl,"corrected_ci_high":nh,
                "old_classification":oc,"corrected_classification":nc,"weak_status_changed":weak_changed,"strict_status_changed":strict_changed,
                "qualitative_conclusion_changed":oc!=nc,"statistically_paired_version_comparison":False})
    write(out/"credibility_changes.csv",cred)

    old=read(old_dir/"continuous_tpr_thresholds.csv");new=read(new_dir/"continuous_tpr_thresholds.csv")
    oi={(r["configuration_id"],r["coalition"]):r for r in old}; tpr=[]
    for n in new:
        o=oi[(n["configuration_id"],n["coalition"])]
        changed=o["status"]!=n["status"];changes["continuous_tpr_classification_changed"]+=changed
        tpr.append({"configuration_id":n["configuration_id"],"coalition":n["coalition"],"old_tpr_min":o["tpr_min"],
            "corrected_tpr_min":n["tpr_min"],"direct_difference":(float(n["tpr_min"])-float(o["tpr_min"]) if n["tpr_min"] and o["tpr_min"] else ""),
            "old_ci_low":o["bootstrap_ci_low"],"old_ci_high":o["bootstrap_ci_high"],"corrected_ci_low":n["bootstrap_ci_low"],
            "corrected_ci_high":n["bootstrap_ci_high"],"old_status":o["status"],"corrected_status":n["status"],
            "qualitative_conclusion_changed":changed,"statistically_paired_version_comparison":False})
    write(out/"tpr_changes.csv",tpr)

    old=read(old_dir/"false_positive_vectors.csv");new=read(new_dir/"false_positive_vectors.csv")
    oi={(r["configuration_id"],r["coalition"],r["actor"],r["fpr"]):r for r in old}; fp=[]
    for n in new:
        o=oi[(n["configuration_id"],n["coalition"],n["actor"],n["fpr"])]; changed=o["conditional_loss_status"]!=n["conditional_loss_status"]
        changes["false_positive_status_changed"]+=changed
        fp.append({"configuration_id":n["configuration_id"],"coalition":n["coalition"],"actor":n["actor"],"fpr":n["fpr"],
            "old_estimate":o["conditional_loss"],"corrected_estimate":n["conditional_loss"],
            "direct_difference":float(n["conditional_loss"])-float(o["conditional_loss"]),
            "old_ci_low":o["conditional_loss_ci95_low"],"old_ci_high":o["conditional_loss_ci95_high"],
            "corrected_ci_low":n["conditional_loss_ci95_low"],"corrected_ci_high":n["conditional_loss_ci95_high"],
            "old_status":o["conditional_loss_status"],"corrected_status":n["conditional_loss_status"],
            "qualitative_conclusion_changed":changed,"statistically_paired_version_comparison":False})
    write(out/"false_positive_changes.csv",fp)

    old=read(old_dir/"equal_hash_comparisons_adjusted.csv");new=read(new_dir/"equal_hash_comparisons_adjusted.csv")
    def eqkey(r):return (r["left_configuration_id"],r["left_coalition"],r["right_configuration_id"],r["right_coalition"],r["metric"])
    oi={eqkey(r):r for r in old}; eq=[]
    for n in new:
        o=oi[eqkey(n)]; changed=o["bh_adjusted_status"]!=n["bh_adjusted_status"]
        changes["equal_hash_adjusted_conclusion_changed"]+=changed
        eq.append({"left_configuration_id":n["left_configuration_id"],"left_coalition":n["left_coalition"],
            "right_configuration_id":n["right_configuration_id"],"right_coalition":n["right_coalition"],"metric":n["metric"],
            "old_estimate":o["difference"],"corrected_estimate":n["difference"],"direct_difference":float(n["difference"])-float(o["difference"]),
            "old_ci_low":o["ci95_low"],"old_ci_high":o["ci95_high"],"corrected_ci_low":n["ci95_low"],"corrected_ci_high":n["ci95_high"],
            "old_status":o["status"],"corrected_status":n["status"],"old_bh_status":o["bh_adjusted_status"],
            "corrected_bh_status":n["bh_adjusted_status"],"qualitative_conclusion_changed":changed,
            "statistically_paired_version_comparison":False})
    write(out/"equal_hash_changes.csv",eq)

    old=read(old_dir/"threshold_audit.csv");new=read(new_dir/"threshold_audit.csv")
    def thkey(r):return (r["target_hash_power"],r["gamma"],r["natural_fork_rate"],r["structure"],r["threshold_metric"],r["threshold_kind"],r.get("tpr",""))
    oi={thkey(r):r for r in old}; th=[]
    for n in new:
        o=oi.get(thkey(n));
        if not o:continue
        changed=o["hash_power"]!=n["hash_power"] or o["boundary_interpretation"]!=n["boundary_interpretation"]
        changes["minimum_threshold_changed"]+=changed
        th.append({"target_hash_power":n["target_hash_power"],"gamma":n["gamma"],"natural_fork_rate":n["natural_fork_rate"],
            "structure":n["structure"],"threshold_metric":n["threshold_metric"],"threshold_kind":n["threshold_kind"],"tpr":n.get("tpr",""),
            "old_hash_power":o["hash_power"],"corrected_hash_power":n["hash_power"],
            "direct_difference":(float(n["hash_power"])-float(o["hash_power"]) if n["hash_power"] and o["hash_power"] else ""),
            "old_boundary_status":o["boundary_interpretation"],"corrected_boundary_status":n["boundary_interpretation"],
            "old_minimizers":o["minimizers"],"corrected_minimizers":n["minimizers"],"qualitative_conclusion_changed":changed})
    write(out/"threshold_changes.csv",th)
    summary.update(changes);summary.update({"aggregate_rows":len(agg),"credibility_rows":len(cred),"tpr_rows":len(tpr),
        "false_positive_rows":len(fp),"equal_hash_rows":len(eq),"threshold_rows":len(th)})
    (out/"comparison_summary.json").write_text(json.dumps(summary,indent=2)+"\n");return summary


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--old",required=True);p.add_argument("--corrected",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();print(json.dumps(generate(a.old,a.corrected,a.output),indent=2))
