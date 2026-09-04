from __future__ import annotations

import csv, hashlib, json, math, subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

MODEL_VERSION = "race-owner-precedence-v2"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "results/research_sweep_stage_b_racefix"
OLD_COMPARISON = ROOT / "results/racefix_comparison"
TABLE_NAMES = [
 "aggregate_effectiveness_thresholds.csv","aggregate_effectiveness_thresholds_compact.csv",
 "continuous_tpr_summary.csv","tpr_at_supported_threshold.csv","member_credibility_summary.csv",
 "coalition_credibility_summary.csv","credibility_by_structure.csv","weak_vs_strict_credibility.csv",
 "weakest_member_summary.csv","equal_hash_effect_summary.csv","equal_hash_by_structure_pair.csv",
 "equal_hash_deterrence.csv","equal_hash_credibility.csv","false_positive_target_summary.csv",
 "false_positive_actor_summary.csv","false_positive_expected_costs.csv","high_false_positive_conditions.csv",
 "terminal_boundary_review.csv","minimal_winning_coalitions_summary.csv",
 "minimal_winning_coalitions_by_environment.csv","figure_stage_c_mapping.csv","table_stage_c_mapping.csv",
 "publication_critical_confirmation_cases.csv","racefix_internal_comparison.csv"]

def read_csv(path):
    with Path(path).open(newline="") as f: return list(csv.DictReader(f))

def write_csv(path, rows):
    rows=list(rows); path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in rows:
            w.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(list,dict,tuple)) else v for k,v in r.items()})

def obj(value, default=None):
    if value in (None,""): return default
    return json.loads(value) if isinstance(value,str) else value

def truth(value): return value is True or str(value).lower()=="true"
def f(value): return None if value in (None,"") else float(value)
def quantile(xs,p):
    xs=sorted(float(x) for x in xs); q=(len(xs)-1)*p; lo=math.floor(q); hi=math.ceil(q)
    return xs[lo] if lo==hi else xs[lo]+(q-lo)*(xs[hi]-xs[lo])

def git_commit():
    try:return subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    except Exception:return None

def validate_inputs(source=DEFAULT_SOURCE):
    source=Path(source)
    required=["mining_configurations.csv","coalition_results.csv","threshold_audit.csv",
      "continuous_tpr_thresholds.csv","member_credibility_refined.csv","coalition_credibility_refined.csv",
      "equal_hash_comparisons_adjusted.csv","false_positive_vectors.csv","terminal_boundary_diagnostics.csv",
      "minimal_winning_coalitions.csv","stage_c_candidates_reasoned_uncapped.csv","repetition_metrics.csv"]
    missing=[x for x in required if not (source/x).exists()]
    details=[]; versions=set(); configs=set()
    for name in required:
        if name in missing:continue
        rows=read_csv(source/name); v={r.get("model_version") for r in rows if r.get("model_version")}
        versions |= v; configs |= {r["configuration_id"] for r in rows if r.get("configuration_id")}
        details.append({"file":name,"rows":len(rows),"model_versions":sorted(v),
                        "unique_configuration_ids":len({r.get('configuration_id') for r in rows if r.get('configuration_id')})})
    try: source_label=str(source.relative_to(ROOT))
    except ValueError: source_label=str(source)
    audit={"source_directory":source_label,"source_files":details,"model_version":MODEL_VERSION,
      "unique_configuration_count":len(configs),"missing_expected_outputs":missing,
      "old_model_configuration_detected":any(x!=MODEL_VERSION for x in versions),
      "corrected_only":versions=={MODEL_VERSION},"repetition_data_available":(source/"repetition_metrics.csv").exists(),
      "repetition_uncertainty_coverage":"paired repetition statistics embedded in source rows; repetition_metrics available",
      "mining_executed":False,"stage_c_executed":False,
      "branch_rule":"owners remain on owned branches; gamma applies only to neutral miners"}
    if missing or audit["old_model_configuration_detected"] or not audit["corrected_only"]:
        raise RuntimeError(f"unsafe analysis inputs: {audit}")
    (source/"analysis_input_audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    return audit

def _stage_index(source):
    rows=read_csv(Path(source)/"stage_c_candidates_reasoned_uncapped.csv")
    return {(r["configuration_id"],r["coalition"]):r for r in rows}

def _common(c, stage):
    s=stage.get((c["configuration_id"],c["coalition"]),{})
    return {"configuration_id":c["configuration_id"],"coalition":c["coalition"],
      "target_hash_power":c["target_hash_power"],"active_coalition_hash_power":c["active_hash_power"],
      "candidate_population_hash_power":c.get("candidate_population_power",c.get("total_candidate_power")),
      "residual_honest_power":c.get("residual_honest_power"),"gamma":c["gamma"],
      "natural_fork_rate":c["natural_fork_rate"],"structure":c["structure"],
      "member_hash_vector":c.get("member_hash_vector"),"coalition_cardinality":c.get("cardinality"),
      "terminal_boundary_diagnostic":c.get("boundary_effect_status"),
      "stage_c_confirmation_recommended":bool(s),"stage_c_reason_codes":s.get("reason_codes","[]"),
      "publication_critical_protected":s.get("tier")=="Tier 1"}

def generate_tables(source=DEFAULT_SOURCE):
    source=Path(source); validate_inputs(source); out=source/"analysis_tables"; out.mkdir(exist_ok=True)
    stage=_stage_index(source); coals=read_csv(source/"coalition_credibility_refined.csv")
    cindex={(r["configuration_id"],r["coalition"]):r for r in coals}
    terminals={(r["configuration_id"],r["coalition"]):r for r in read_csv(source/"terminal_boundary_diagnostics.csv")}
    thresholds=read_csv(source/"threshold_audit.csv")
    groups=defaultdict(dict)
    for r in thresholds:
        if r["structure"]=="singleton" and r["threshold_metric"] in ("effectiveness","detector_effectiveness"):
            groups[(r["target_hash_power"],r["gamma"],r["natural_fork_rate"])][(r["threshold_metric"],r["threshold_kind"],r.get("tpr",""))]=r
    aggregate=[]
    for key,g in sorted(groups.items(),key=lambda x:tuple(map(float,x[0]))):
        point=g.get(("effectiveness","point","")); supported=g.get(("effectiveness","supported",""))
        if not point or not supported:continue
        mins=obj(supported["minimizers"],[]); keys=[(m["configuration_id"],m["coalition"]) for m in mins]
        overlap=any(truth(terminals.get(k,{}).get("point_deterrence_could_change")) or truth(terminals.get(k,{}).get("supported_deterrence_could_be_affected")) for k in keys)
        sc=[stage[k] for k in keys if k in stage]
        detector={}
        for (metric,kind,tpr),r in g.items():
            if metric=="detector_effectiveness" and kind=="supported":detector[str(tpr)]=r.get("hash_power")
        row={"target_hash_power":key[0],"gamma":key[1],"natural_fork_rate":key[2],
          "unpunished_selfish_profitability_status":"SELFISH_ALREADY_UNPROFITABLE" if supported["boundary_interpretation"]=="SELFISH_ALREADY_UNPROFITABLE" else "PROFITABLE",
          "point_minimum_effective_coalition_power":point.get("hash_power"),
          "supported_minimum_effective_coalition_power":supported.get("hash_power"),
          "threshold_boundary_classification":supported["boundary_interpretation"],
          "point_tied_minimizers":point["minimizers"],"supported_tied_minimizers":supported["minimizers"],
          "configuration_ids":json.dumps(sorted({k[0] for k in keys})),"detector_adjusted_supported_thresholds":json.dumps(detector,sort_keys=True),
          "terminal_boundary_overlap":overlap,"stage_c_confirmation_recommended":bool(sc),
          "stage_c_reason_codes":json.dumps(sorted({x for s in sc for x in obj(s["reason_codes"],[])}))}
        aggregate.append(row)
    write_csv(out/TABLE_NAMES[0],aggregate)
    compact_keys=["target_hash_power","gamma","natural_fork_rate","unpunished_selfish_profitability_status","point_minimum_effective_coalition_power","supported_minimum_effective_coalition_power","threshold_boundary_classification","terminal_boundary_overlap","stage_c_confirmation_recommended"]
    write_csv(out/TABLE_NAMES[1],[{k:r[k] for k in compact_keys} for r in aggregate])

    tprs=read_csv(source/"continuous_tpr_thresholds.csv"); tpr_summary=[]
    for r in tprs:
        c=cindex[(r["configuration_id"],r["coalition"])]
        tpr_summary.append({**_common(c,stage),"tpr_status":r["status"],
          "continuous_tpr_minimum":r["tpr_min"] if r["status"]=="DETERRABLE" else "",
          "bootstrap_ci_low":r["bootstrap_ci_low"],"bootstrap_ci_high":r["bootstrap_ci_high"],
          "bootstrap_valid_samples":r["bootstrap_valid_samples"],"bootstrap_invalid_samples":r["bootstrap_invalid_samples"]})
    write_csv(out/"continuous_tpr_summary.csv",tpr_summary)
    selected=[]
    byenv=defaultdict(list)
    for r in tpr_summary:byenv[(r["target_hash_power"],r["gamma"],r["natural_fork_rate"],r["structure"])].append(r)
    for env,rows in byenv.items():
        a=next((x for x in aggregate if (x["target_hash_power"],x["gamma"],x["natural_fork_rate"])==env[:3]),None)
        if not a:continue
        for kind,col in (("point","point_minimum_effective_coalition_power"),("supported","supported_minimum_effective_coalition_power")):
            hp=f(a[col]); powers=sorted({f(x["active_coalition_hash_power"]) for x in rows})
            if hp is None:continue
            near=sorted(powers,key=lambda x:abs(x-hp))[:3]
            for x in rows:
                if f(x["active_coalition_hash_power"]) in near:selected.append({**x,"threshold_basis":kind,"threshold_power":hp})
    write_csv(out/"tpr_at_supported_threshold.csv",selected)

    members=read_csv(source/"member_credibility_refined.csv"); member_out=[]
    for r in members:
        c=cindex[(r["configuration_id"],r["coalition"])]
        b=obj(r["baseline"]); d=obj(r["deviation"])
        member_out.append({**_common(c,stage),"member_id":r["member_id"],"member_hash_power":r["member_hash_power"],
          "baseline_classification":r["baseline_classification"],"baseline_estimate":b["mean"],"baseline_ci_low":b["ci95_low"],"baseline_ci_high":b["ci95_high"],
          "deviation_classification":r["deviation_classification"],"deviation_estimate":d["mean"],"deviation_ci_low":d["ci95_low"],"deviation_ci_high":d["ci95_high"]})
    write_csv(out/"member_credibility_summary.csv",member_out)
    coalition_out=[]
    for c in coals:
        status="STRICTLY_DEVIATION_PROOF" if truth(c["strict_deviation_proof"]) else "WEAK_BREAK_EVEN_ONLY" if truth(c["weak_deviation_proof"]) else "NEITHER"
        coalition_out.append({**_common(c,stage),"credibility_classification":status,"weak_deviation_proof":c["weak_deviation_proof"],
          "strict_deviation_proof":c["strict_deviation_proof"],"weakest_member":c["weakest_member"],
          "weakest_member_hash_power":min(obj(c["member_hash_vector"])),"credibility_slack":c["credibility_slack"],
          "protocol_payoff_tolerance":c["protocol_payoff_cost_tolerance_refined"]})
    counts=Counter(x["credibility_classification"] for x in coalition_out)
    expected={"STRICTLY_DEVIATION_PROOF":58,"WEAK_BREAK_EVEN_ONLY":1128,"NEITHER":4358}
    if counts!=expected:raise RuntimeError(f"corrected credibility counts differ: {dict(counts)} != {expected}")
    write_csv(out/"coalition_credibility_summary.csv",coalition_out)
    bystruct=[]
    for s in sorted({x["structure"] for x in coalition_out}):
        rr=[x for x in coalition_out if x["structure"]==s]; cc=Counter(x["credibility_classification"] for x in rr)
        for status,n in cc.items():bystruct.append({"structure":s,"credibility_classification":status,"count":n,"fraction":n/len(rr),"total":len(rr)})
    write_csv(out/"credibility_by_structure.csv",bystruct); write_csv(out/"weak_vs_strict_credibility.csv",bystruct)
    write_csv(out/"weakest_member_summary.csv",coalition_out)

    eq=read_csv(source/"equal_hash_comparisons_adjusted.csv"); metrics=defaultdict(list)
    for r in eq:metrics[r["metric"]].append(r)
    eqsum=[]
    for metric,rr in metrics.items():
        vals=[abs(float(x["difference"])) for x in rr]
        eqsum.append({"metric":metric,"eligible_comparisons":len(rr),"unadjusted_positive":sum(x["status"]=="SUPPORTED" for x in rr),
          "unadjusted_negative":sum(x["status"]=="REFUTED" for x in rr),"unadjusted_inconclusive":sum(x["status"]=="INCONCLUSIVE" for x in rr),
          "bh_positive":sum(x["bh_adjusted_status"]=="SUPPORTED" for x in rr),"bh_negative":sum(x["bh_adjusted_status"]=="REFUTED" for x in rr),
          "bh_inconclusive":sum(x["bh_adjusted_status"]=="INCONCLUSIVE" for x in rr),"median_absolute_effect":quantile(vals,.5),
          "p90_absolute_effect":quantile(vals,.9),"p95_absolute_effect":quantile(vals,.95),"maximum_absolute_effect":max(vals)})
    write_csv(out/"equal_hash_effect_summary.csv",eqsum)
    pair=[]
    for (metric,sp),rr in sorted(defaultdict(list, {k:[x for x in eq if (x["metric"],"--".join(sorted((x["left_structure"],x["right_structure"]))))==k] for k in {(x["metric"],"--".join(sorted((x["left_structure"],x["right_structure"])))) for x in eq}}).items()):
        vals=[abs(float(x["difference"])) for x in rr]; pair.append({"metric":metric,"structure_pair":sp,"comparisons":len(rr),"bh_positive":sum(x["bh_adjusted_status"]=="SUPPORTED" for x in rr),"bh_negative":sum(x["bh_adjusted_status"]=="REFUTED" for x in rr),"median_absolute_effect":quantile(vals,.5),"p95_absolute_effect":quantile(vals,.95)})
    write_csv(out/"equal_hash_by_structure_pair.csv",pair)
    write_csv(out/"equal_hash_deterrence.csv",[r for r in eq if r["metric"] in ("deterrence","punishment_reduction")])
    write_csv(out/"equal_hash_credibility.csv",[r for r in eq if r["metric"] in ("baseline_credibility","deviation_credibility","credibility_slack")])

    fps=read_csv(source/"false_positive_vectors.csv")
    if any(float(r["conditional_loss"])!=0 for r in fps if float(r["natural_fork_rate"])==0):raise RuntimeError("nonzero lambda-zero false-positive loss")
    fpo=[]
    for r in fps:
        c=cindex[(r["configuration_id"],r["coalition"])]
        fpo.append({**_common(c,stage),"actor":r["actor"],"fpr":r["fpr"],"conditional_loss":r["conditional_loss"],
          "conditional_loss_ci_low":r["conditional_loss_ci95_low"],"conditional_loss_ci_high":r["conditional_loss_ci95_high"],
          "conditional_loss_status":r["conditional_loss_status"],"expected_cost":r["expected_cost"]})
    write_csv(out/"false_positive_actor_summary.csv",fpo); write_csv(out/"false_positive_expected_costs.csv",fpo)
    target=[r for r in fpo if r["actor"]=="target"]; write_csv(out/"false_positive_target_summary.csv",target)
    cutoff=quantile([float(r["expected_cost"]) for r in target],.99)
    write_csv(out/"high_false_positive_conditions.csv",[r for r in fpo if float(r["expected_cost"])>=cutoff and float(r["expected_cost"])>0])

    review=[]
    for k,t in terminals.items():
        if truth(t["point_deterrence_could_change"]) or truth(t["supported_deterrence_could_be_affected"]):
            c=cindex[k]; d=obj(c["deterrence"]); review.append({**_common(c,stage),"deterrence_estimate":d["mean"],"deterrence_ci_low":d["ci95_low"],"deterrence_ci_high":d["ci95_high"],
              "maximum_terminal_lead":t["maximum_terminal_private_lead"],"mean_terminal_lead":t["mean_terminal_private_lead"],
              "maximum_omitted_share_bound":t["maximum_omitted_share_bound"],"point_overlap":t["point_deterrence_could_change"],
              "supported_interval_overlap":t["supported_deterrence_could_be_affected"],"effectiveness_status":c["effectiveness_status"]})
    if sum(truth(r["point_overlap"]) for r in review)!=14 or sum(truth(r["supported_interval_overlap"]) for r in review)!=5:raise RuntimeError("terminal overlap count mismatch")
    write_csv(out/"terminal_boundary_review.csv",review)

    # Recompute set-minimal winning coalitions separately under weak and strict
    # refined credibility. This retains tied/incomparable minima.
    tpr_idx={(r["configuration_id"],r["coalition"]):r for r in tprs}
    fp_target={(r["configuration_id"],r["coalition"]):r for r in fpo if r["actor"]=="target" and float(r["fpr"])==.1}
    mwout=[]
    byconfig=defaultdict(list)
    for c in coals:byconfig[c["configuration_id"]].append(c)
    for cid,available in byconfig.items():
      for basis,field in (("weak","weak_deviation_proof"),("strict","strict_deviation_proof")):
        eligible=[c for c in available if c["effectiveness_status"]=="SUPPORTED" and truth(c[field])]
        sets={c["coalition"]:set(obj(c["members"],c["coalition"].split("|"))) for c in eligible}
        minimal=[c for c in eligible if not any(sets[o["coalition"]] < sets[c["coalition"]] for o in eligible)]
        for c in minimal:
            tr=tpr_idx[(cid,c["coalition"])]; fr=fp_target.get((cid,c["coalition"]),{})
            mwout.append({**_common(c,stage),"credibility_basis":basis,"members":c["members"],"deterrence":c["deterrence"],
              "minimum_tpr":tr["tpr_min"] if tr["status"]=="DETERRABLE" else "","tpr_status":tr["status"],
              "false_positive_conditional_target_loss_fpr_0_1":fr.get("conditional_loss",""),"credibility_slack":c["credibility_slack"]})
    write_csv(out/"minimal_winning_coalitions_by_environment.csv",mwout)
    summary=[]
    for basis in ("weak","strict"):
        rr=[x for x in mwout if x["credibility_basis"]==basis];summary.append({"credibility_basis":basis,"coalitions":len(rr),"environments":len({(x["target_hash_power"],x["gamma"],x["natural_fork_rate"]) for x in rr})})
    write_csv(out/"minimal_winning_coalitions_summary.csv",summary)

    stage_rows=read_csv(source/"stage_c_candidates_reasoned_uncapped.csv")
    pub=[r for r in stage_rows if r["tier"]=="Tier 1"]
    if len(pub)!=429:raise RuntimeError(f"protected Stage C count {len(pub)} != 429")
    mapping=[]
    for r in stage_rows:
        c=cindex[(r["configuration_id"],r["coalition"])]
        key=(r["configuration_id"],r["coalition"]); categories=obj(r["reason_categories"],[]); reason_codes=obj(r["reason_codes"],[])
        if key in terminals and (truth(terminals[key]["point_deterrence_could_change"]) or truth(terminals[key]["supported_deterrence_could_be_affected"])):
            categories=sorted(set(categories+["terminal-boundary overlap"]));reason_codes=sorted(set(reason_codes+["TERMINAL_BOUNDARY_OVERLAP"]))
        identifiers=[]
        for category in categories:
            identifiers.extend({"publication-critical threshold confirmation":["aggregate_effectiveness_thresholds","effectiveness_threshold_heatmaps"],
              "detector-threshold transition":["continuous_tpr_summary","continuous_tpr_representative"],
              "unresolved credibility margin":["coalition_credibility_summary","credibility_figures"],
              "composition comparison":["equal_hash_tables","composition_figures"],
              "terminal-boundary overlap":["terminal_boundary_review"],
              "boundary or anomaly review":["high_false_positive_conditions","terminal_boundary_review"]}.get(category,["analysis_review"]))
        mapping.append({"figure_table_identifiers":sorted(set(identifiers)),"configuration_id":r["configuration_id"],"coalition":r["coalition"],"reason_codes":reason_codes,
          "reason_categories":categories,"publication_critical_protected":r["tier"]=="Tier 1",
          "current_deterrence":obj(c["deterrence"])["mean"],"current_uncertainty":c["deterrence"],"source_identifiers":r["sources"]})
    write_csv(out/"figure_stage_c_mapping.csv",mapping);write_csv(out/"table_stage_c_mapping.csv",mapping);write_csv(out/"publication_critical_confirmation_cases.csv",[x for x in mapping if x["publication_critical_protected"]])

    comp=json.loads((OLD_COMPARISON/"comparison_summary.json").read_text())
    internal=[{"diagnostic_label":"INTERNAL MODEL-CORRECTION DIAGNOSTIC — NOT A SCIENTIFIC COMPARISON","metric":k,"value":json.dumps(v,sort_keys=True),"paired_version_ci":False,"note":"random-stream alignment changed"} for k,v in comp.items()]
    write_csv(out/"racefix_internal_comparison.csv",internal)
    return {"tables":TABLE_NAMES,"credibility_counts":dict(counts),"terminal_rows":len(review),"protected_stage_c":len(pub),"stage_c_candidates":len(stage_rows)}
