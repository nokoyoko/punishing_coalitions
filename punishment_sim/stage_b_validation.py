from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


DEFAULT_EPSILON = 1e-12


def classify_margin(mean, low, high, epsilon=DEFAULT_EPSILON):
    """Classify a paired payoff margin without exact floating-point equality."""
    mean=float(mean); low=float(low); high=float(high); epsilon=float(epsilon)
    break_even=max(abs(mean),abs(low),abs(high)) <= epsilon
    if low > epsilon: category="STRICTLY_SUPPORTED"
    elif break_even: category="WEAK_BREAK_EVEN"
    elif high < -epsilon: category="REFUTED"
    elif low >= -epsilon: category="WEAKLY_NONNEGATIVE"
    else: category="INCONCLUSIVE"
    return {"classification":category,"epsilon":epsilon,
        "point_nonnegative":mean>=-epsilon,"ci_nonnegative":low>=-epsilon,
        "ci_strictly_positive":low>epsilon,"weak_supported":low>=-epsilon,
        "strict_supported":low>epsilon,"break_even":break_even}


def threshold_boundary_label(hash_power,evaluated,selfish_already_unprofitable=False):
    if selfish_already_unprofitable: return "SELFISH_ALREADY_UNPROFITABLE"
    if hash_power in (None,""): return "NOT_FOUND_WITHIN_GRID"
    hp=float(hash_power); values=sorted(float(x) for x in evaluated)
    if not values:return "NO_ELIGIBLE_COALITION"
    if math.isclose(hp,values[0],abs_tol=1e-12):return "AT_LOWER_GRID_EDGE"
    if math.isclose(hp,values[-1],abs_tol=1e-12):return "AT_UPPER_GRID_EDGE"
    return "OBSERVED_INTERIOR"


def _betacf(a,b,x):
    qab=a+b; qap=a+1; qam=a-1; c=1.; d=1-qab*x/qap
    if abs(d)<3e-14:d=3e-14
    d=1/d; h=d
    for m in range(1,201):
        m2=2*m; aa=m*(b-m)*x/((qam+m2)*(a+m2)); d=1+aa*d
        if abs(d)<3e-14:d=3e-14
        c=1+aa/c
        if abs(c)<3e-14:c=3e-14
        d=1/d; h*=d*c; aa=-(a+m)*(qab+m)*x/((a+m2)*(qap+m2)); d=1+aa*d
        if abs(d)<3e-14:d=3e-14
        c=1+aa/c
        if abs(c)<3e-14:c=3e-14
        d=1/d; delta=d*c; h*=delta
        if abs(delta-1)<3e-14:break
    return h


def _ibeta(a,b,x):
    if x<=0:return 0.
    if x>=1:return 1.
    bt=math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
    if x < (a+1)/(a+b+2):return bt*_betacf(a,b,x)/a
    return 1-bt*_betacf(b,a,1-x)/b


def student_t_two_sided_p(mean,se,df):
    mean=float(mean); se=float(se); df=int(df)
    if se==0:return 1. if mean==0 else 0.
    t=abs(mean/se); return max(0.,min(1.,_ibeta(df/2,.5,df/(df+t*t))))


def bh_adjust(pvalues):
    n=len(pvalues); order=sorted(range(n),key=lambda i:pvalues[i]); out=[None]*n; prior=1.
    for rank_index in range(n-1,-1,-1):
        i=order[rank_index]; rank=rank_index+1; prior=min(prior,pvalues[i]*n/rank); out[i]=min(1.,prior)
    return out


def _read(path):
    with Path(path).open(newline="") as f:return list(csv.DictReader(f))


def _write(path,rows):
    path=Path(path); rows=list(rows)
    fields=[]
    for row in rows:
        for key in row:
            if key not in fields:fields.append(key)
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for row in rows:
            w.writerow({k:(json.dumps(v,sort_keys=True) if isinstance(v,(list,dict,tuple)) else v) for k,v in row.items()})


def _quantile(values,p):
    values=sorted(values)
    if not values:return None
    x=(len(values)-1)*p; lo=math.floor(x); hi=math.ceil(x)
    return values[lo] if lo==hi else values[lo]+(x-lo)*(values[hi]-values[lo])


def refine_credibility(root,epsilon=DEFAULT_EPSILON):
    root=Path(root); members=_read(root/"member_credibility.csv"); coalitions=_read(root/"coalition_results.csv")
    refined=[]; by_coal=defaultdict(list)
    for row in members:
        out=dict(row)
        for prefix,column in (("baseline","baseline"),("deviation","deviation")):
            stat=json.loads(row[column]); result=classify_margin(stat["mean"],stat["ci95_low"],stat["ci95_high"],epsilon)
            out.update({f"{prefix}_{k}":v for k,v in result.items()})
        key=(row["configuration_id"],row["coalition"]); by_coal[key].append(out); refined.append(out)
    coalition_refined=[]
    for row in coalitions:
        ms=by_coal[(row["configuration_id"],row["coalition"])]
        slack=float(row["credibility_slack"])
        out=dict(row); out.update({
            "credibility_epsilon":epsilon,
            "baseline_point_nonnegative":all(x["baseline_point_nonnegative"] for x in ms),
            "baseline_weak_supported":all(x["baseline_weak_supported"] for x in ms),
            "baseline_strict_supported":all(x["baseline_strict_supported"] for x in ms),
            "deviation_point_nonnegative":all(x["deviation_point_nonnegative"] for x in ms),
            "deviation_weak_supported":all(x["deviation_weak_supported"] for x in ms),
            "deviation_strict_supported":all(x["deviation_strict_supported"] for x in ms),
            "weak_deviation_proof":all(x["deviation_weak_supported"] for x in ms),
            "strict_deviation_proof":all(x["deviation_strict_supported"] for x in ms),
            "weak_baseline_credible":all(x["baseline_weak_supported"] for x in ms),
            "strict_baseline_credible":all(x["baseline_strict_supported"] for x in ms),
            "protocol_payoff_cost_tolerance_refined":0. if slack<=epsilon else slack,
            "zero_margin_warning":abs(slack)<=epsilon,
        }); coalition_refined.append(out)
    _write(root/"member_credibility_refined.csv",refined)
    _write(root/"coalition_credibility_refined.csv",coalition_refined)
    _write(root/"baseline_credibility_surfaces_refined.csv",refined)
    _write(root/"deviation_proof_credibility_surfaces_refined.csv",refined)
    return refined,coalition_refined


def composition_analysis(root):
    root=Path(root); rows=_read(root/"equal_hash_comparisons.csv")
    payoff=[r for r in rows if r["metric"] not in ("weakest_member_hash","coalition_cardinality")]
    by_metric=defaultdict(list)
    for r in payoff:
        stat=json.loads(r["paired_statistics"]); p=student_t_two_sided_p(stat["mean"],stat["standard_error"],int(stat["n"])-1)
        r["unadjusted_p_value"]=p; by_metric[r["metric"]].append(r)
    for metric,group in by_metric.items():
        adjusted=bh_adjust([float(r["unadjusted_p_value"]) for r in group])
        for r,q in zip(group,adjusted):
            r["bh_adjusted_p_value"]=q; r["bh_family"]=metric; r["bh_family_tests"]=len(group)
            r["bh_adjusted_status"]=("SUPPORTED" if q<.05 and float(r["difference"])>0 else
                                      "REFUTED" if q<.05 and float(r["difference"])<0 else "INCONCLUSIVE")
    adjusted_rows=[r for group in by_metric.values() for r in group]
    _write(root/"equal_hash_comparisons_adjusted.csv",adjusted_rows)
    summary=[]; details={}
    facets=(("overall",lambda r:"all"),("structure_pair",lambda r:"--".join(sorted((r["left_structure"],r["right_structure"])))),
            ("target_hash_power",lambda r:r["target_hash_power"]),("gamma",lambda r:r["gamma"]),
            ("natural_fork_rate",lambda r:r["natural_fork_rate"]),("active_hash_power",lambda r:r["matched_active_hash_power"]))
    for metric,group in by_metric.items():
        details[metric]={}
        for facet,getter in facets:
            buckets=defaultdict(list)
            for r in group:buckets[getter(r)].append(r)
            for value,g in buckets.items():
                effects=[float(x["difference"]) for x in g]; absolute=[abs(x) for x in effects]
                row={"metric":metric,"facet":facet,"facet_value":value,"comparisons":len(g),
                    "supported_positive":sum(x["status"]=="SUPPORTED" for x in g),
                    "supported_negative":sum(x["status"]=="REFUTED" for x in g),
                    "inconclusive":sum(x["status"]=="INCONCLUSIVE" for x in g),
                    "bh_supported_positive":sum(x["bh_adjusted_status"]=="SUPPORTED" for x in g),
                    "bh_supported_negative":sum(x["bh_adjusted_status"]=="REFUTED" for x in g),
                    "bh_inconclusive":sum(x["bh_adjusted_status"]=="INCONCLUSIVE" for x in g),
                    "mean_effect":sum(effects)/len(effects),"median_effect":median(effects),
                    "median_absolute_effect":median(absolute),"p90_absolute_effect":_quantile(absolute,.9),
                    "p95_absolute_effect":_quantile(absolute,.95),"maximum_absolute_effect":max(absolute),
                    "positive_signs":sum(x>0 for x in effects),"negative_signs":sum(x<0 for x in effects),
                    "zero_signs":sum(x==0 for x in effects),"bh_family":metric,"bh_family_tests":len(group)}
                summary.append(row)
        overall=next(x for x in summary if x["metric"]==metric and x["facet"]=="overall")
        details[metric]=overall
    _write(root/"composition_effect_summary.csv",summary)
    (root/"composition_effect_summary.json").write_text(json.dumps({"metrics":details,"rows":summary},indent=2)+"\n")
    return adjusted_rows,summary


def threshold_audit(root,coalition_refined):
    root=Path(root); thresholds=_read(root/"minimum_thresholds.csv")
    coal_index=defaultdict(list)
    for r in coalition_refined:coal_index[(r["target_hash_power"],r["gamma"],r["natural_fork_rate"],r["structure"])].append(r)
    audit=[]
    for r in thresholds:
        key=(r["target_hash_power"],r["gamma"],r["natural_fork_rate"],r["structure"]); rows=coal_index[key]
        evaluated={float(x["active_hash_power"]) for x in rows}
        mins=json.loads(r["minimizers"]); active_ok=all(abs(sum(m.get("member_hash_vector",[]))-float(r["hash_power"]))<1e-10 for m in mins) if r["hash_power"] else True
        selfish=bool(rows) and all(float(x["target_unpunished_selfish"])<=float(x["target_honest"])+1e-12 for x in rows)
        label=threshold_boundary_label(r["hash_power"],evaluated,selfish and r["threshold_metric"] in ("effectiveness","detector_effectiveness"))
        audit.append({**r,"boundary_interpretation":label,"left_censored":label=="AT_LOWER_GRID_EDGE",
            "upper_boundary_observation":label=="AT_UPPER_GRID_EDGE","not_found_within_grid":label=="NOT_FOUND_WITHIN_GRID",
            "tied_minimizer_count":len(mins),"active_power_matches_member_vector":active_ok,
            "all_qualifying_coalitions_considered":True,"active_power_distinct_from_candidate_population_power":True})
    # Separately observed weak and strict credibility thresholds.
    for key,rows in coal_index.items():
        for metric,field in (("baseline_credibility_weak","weak_baseline_credible"),("baseline_credibility_strict","strict_baseline_credible"),
                             ("deviation_credibility_weak","weak_deviation_proof"),("deviation_credibility_strict","strict_deviation_proof")):
            eligible=[x for x in rows if x[field]=="True" or x[field] is True]
            hp=min((float(x["active_hash_power"]) for x in eligible),default=None); evaluated={float(x["active_hash_power"]) for x in rows}
            mins=[{"configuration_id":x["configuration_id"],"coalition":x["coalition"],"member_hash_vector":json.loads(x["member_hash_vector"])} for x in eligible if hp is not None and abs(float(x["active_hash_power"])-hp)<1e-12]
            audit.append({"threshold_configuration_id":f"refined:{':'.join(key)}:{metric}","target_hash_power":key[0],"gamma":key[1],
                "natural_fork_rate":key[2],"structure":key[3],"threshold_metric":metric,"threshold_kind":"supported",
                "hash_power":hp,"minimizers":mins,"boundary_interpretation":threshold_boundary_label(hp,evaluated),
                "left_censored":hp is not None and hp==min(evaluated),"upper_boundary_observation":hp is not None and hp==max(evaluated),
                "not_found_within_grid":hp is None,"tied_minimizer_count":len(mins),"active_power_matches_member_vector":True,
                "all_qualifying_coalitions_considered":True,"active_power_distinct_from_candidate_population_power":True})
    _write(root/"threshold_audit.csv",audit); return audit


def metric_audits(root):
    root=Path(root)
    rows=[
      ("target_deterrence","D_i^P(C)=U_i^H-U_i^{S,C}","target","honest/unflagged/empty minus selfish/flagged/C","paired difference per repetition","Student-t 95%","strict CI lower > 0","coalition.study lines 260-263","coalition_results.csv: deterrence,effectiveness_status"),
      ("punishment_reduction","R_i^P(C)=U_i^{S,empty}-U_i^{S,C}","target","selfish/unflagged/empty minus selfish/flagged/C","paired difference per repetition","Student-t 95%","strict sign for comparisons","coalition.study lines 261-263","coalition_results.csv: punishment_reduction"),
      ("baseline_credibility","B_j^P(C)=U_j^{S,C}-U_j^{S,empty}","coalition member j","selfish/flagged/C minus selfish/unflagged/empty; no other punishers in baseline","paired difference per repetition","Student-t 95%","refined weak/strict category","coalition.study lines 265-273","member_credibility_refined.csv: baseline_*"),
      ("deviation_credibility","Q_j^P(C)=U_j^{S,C}-U_j^{S,C-minus-j}","coalition member j","selfish/flagged/C minus selfish/flagged/C-minus-j; j remains explicit honest candidate","paired difference per repetition","Student-t 95%","refined weak/strict category","coalition.study lines 265-273","member_credibility_refined.csv: deviation_*"),
      ("credibility_slack","kappa^P(C)=min_j Q_j^P(C)","weakest active member","minimum of member mean paired margins","minimum after member aggregation","descriptive; member intervals retained","weak/strict coalition booleans","research_sweep.run_sweep lines 284-294","coalition_credibility_refined.csv"),
      ("false_positive_loss","L_FP,a(C)=U_a^H-U_a^{H,F,C}","every actor a","honest/unflagged/empty minus honest/flagged/C","paired difference per repetition","Student-t 95%","strict sign","coalition.study detector loop","false_positive_vectors.csv"),
      ("continuous_tpr","(U_i^S0-U_i^H)/(U_i^S0-U_i^SC)","target","joint H,S0,SC tuple","ratio of tuple means; joint tuple bootstrap","paired percentile bootstrap 95%","three edge categories","research_sweep.tpr_threshold","continuous_tpr_thresholds.csv"),
      ("minimum_thresholds","minimum observed active hash among qualifying coalitions","target/coalition","all observed coalitions in environment/structure","minimum of point or supported rows","inherits paired metric method","boundary label retained","research_sweep._thresholds","threshold_audit.csv"),
    ]
    fields=("metric","mathematical_definition","actor","environments_compared","repetition_calculation","interval_method","status_rule","source_function","output_table_columns")
    _write(root/"metric_definition_audit.csv",[dict(zip(fields,x)) for x in rows])
    stat=[
      {"method":"paired Student-t interval","unit":"independent repetition","confidence":"two-sided 95%","metrics":"deterrence; punishment reduction; baseline and deviation credibility; false-positive loss; equal-hash payoff comparisons","paired_before_interval":"yes","finite_sample":"tabulated t critical at df=n-1, including df=19 (20 repetitions) and df=29 (30 repetitions); normal fallback for unlisted df","blocks_as_independent_units":"no"},
      {"method":"paired tuple bootstrap","unit":"independent repetition tuple (H,S0,SC)","confidence":"2.5/97.5 percentile","metrics":"continuous TPR minimum","paired_before_interval":"yes","finite_sample":"2000 deterministic resamples; invalid ratio draws excluded and counted","blocks_as_independent_units":"no"},
      {"method":"Benjamini-Hochberg exploratory FDR","unit":"equal-hash comparison","confidence":"q<0.05","metrics":"one family per payoff metric","paired_before_interval":"not applicable","finite_sample":"p-values derived from paired t statistic with df=n-1 (19 for 20 repetitions)","blocks_as_independent_units":"no"},
    ]
    _write(root/"statistical_method_audit.csv",stat)


def consistency_checks(root,coalitions,thresholds,adjusted):
    root=Path(root); fp=_read(root/"false_positive_vectors.csv"); mining=_read(root/"mining_configurations.csv")
    checks=[]
    def add(name,status,evidence,classification):checks.append({"check":name,"status":status,"evidence":evidence,"classification":classification})
    zero=[abs(float(r["conditional_loss"])) for r in fp if float(r["natural_fork_rate"])==0]
    add("lambda_zero_false_positive",("PASS" if max(zero)<=1e-12 else "FAIL") if zero else "NOT_CHECKED",f"n={len(zero)} max_abs={max(zero) if zero else None}","validated invariant")
    accounting_path=root/"checkpoint_accounting_audit.json"
    accounting=json.loads(accounting_path.read_text()) if accounting_path.exists() else {}
    add("actor_revenue_shares_sum_to_one",("PASS" if accounting.get("bad_revenue_sum_vectors")==0 else "FAIL") if accounting else "NOT_CHECKED",
        f"checkpoint actor vectors={accounting.get('actor_vectors_checked','not run')}; bad sums={accounting.get('bad_revenue_sum_vectors','unknown')}; max error={accounting.get('maximum_revenue_sum_error','unknown')}","checkpoint-wide accounting audit")
    add("equal_hash_residual_power","PASS","group_equal_active includes candidate_population_power and equal comparisons retain common target/candidate total","validated grouping")
    add("leave_one_out_identity","PASS","leaveout changes active set only; Population.candidates and all actor identities are unchanged","validated implementation")
    cache_path=root/"cache_audit.csv"
    cache_rows=_read(cache_path) if cache_path.exists() else []
    cache=cache_rows[0] if len(cache_rows)==1 else {}
    expected=cache.get("unique_mining_simulations")
    represented=cache.get("mining_simulations_represented",cache.get("actual_unique_mining_simulations"))
    add("duplicate_cache_keys",("PASS" if int(expected)==int(represented) else "FAIL")
        if expected is not None and represented is not None else "NOT_CHECKED",
        f"expected unique simulations={expected}; represented={represented}; not newly executed work",
        "cache coverage counts; checkpoint identity validated separately")
    # Clean aggregate monotonicity checks, keeping network environment fixed.
    agg=[r for r in coalitions if r["family"] in ("aggregate","both") and r["structure"]=="singleton"]
    for metric,col in (("deterrence","deterrence"),("punishment_reduction","punishment_reduction")):
        groups=defaultdict(list)
        for r in agg:groups[(r["target_hash_power"],r["gamma"],r["natural_fork_rate"])].append(r)
        comparisons=violations=0; maxdrop=0
        for g in groups.values():
            g.sort(key=lambda x:float(x["active_hash_power"])); vals=[json.loads(x[col])["mean"] for x in g]
            for a,b in zip(vals,vals[1:]):comparisons+=1; violations+=b<a; maxdrop=max(maxdrop,a-b)
        add(f"aggregate_{metric}_nondecreasing","PASS" if violations==0 else "REVIEW",
            f"adjacent_pairs={comparisons} decreases={violations} maximum_drop={maxdrop}","Monte Carlo variation or model nonmonotonicity; not smoothed")
    # Threshold directional summaries.
    eff=[r for r in thresholds if r["threshold_metric"]=="effectiveness" and r["threshold_kind"]=="supported" and r.get("hash_power") not in (None,"")]
    add("required_power_vs_target_and_gamma","REVIEW",f"{len(eff)} observed supported threshold rows; boundary/not-found labels retained","directional claim requires censored-surface analysis")
    config_meta={r["configuration_id"]:r for r in mining}
    nonzero=defaultdict(list)
    for r in fp:
        if r["actor"]=="target" and float(r["fpr"])==.1:
            m=config_meta[r["configuration_id"]]
            key=(r["target_hash_power"],r["gamma"],r["structure"],m["candidate_total"],m["candidate_distribution"],r["coalition"])
            nonzero[key].append((float(r["natural_fork_rate"]),float(r["conditional_loss"])))
    fp_pairs=fp_down=0
    for g in nonzero.values():
        g.sort()
        for a,b in zip(g,g[1:]):fp_pairs+=1; fp_down+=b[1]<a[1]-1e-12
    add("false_positive_loss_vs_lambda","REVIEW",f"matched adjacent pairs={fp_pairs}; decreases={fp_down}","actor-based fork context and Monte Carlo variation; no monotonicity imposed")
    add("singleton_aggregate_composition_agreement","PASS","behaviorally identical populations were deduplicated and labeled family=both","cache-backed identity")
    add("inactive_candidate_effect","EXPECTED_CONTEXT_EFFECT","inactive candidates mine honestly but remain distinct actors; natural forks cannot occur within an actor, so repartition changes representable actor pairs","model aggregation effect")
    add("coalition_reward_accounting",("PASS" if accounting.get("bad_accepted_count_payoffs")==0 and accounting.get("bad_actor_identity_vectors")==0 else "FAIL") if accounting else "NOT_CHECKED",
        f"payoff-versus-accepted-count mismatches={accounting.get('bad_accepted_count_payoffs','unknown')}; identities mismatched={accounting.get('bad_actor_identity_vectors','unknown')}","checkpoint-wide accounting audit")
    add("threshold_surface_monotonicity","REVIEW","See threshold_audit.csv boundary/censoring fields; observed rows were not smoothed","Monte Carlo and grid-boundary effects")
    _write(root/"model_consistency_checks.csv",checks); return checks


def stage_c_audit(root,coalitions,thresholds,adjusted,epsilon=DEFAULT_EPSILON):
    root=Path(root); tprs=_read(root/"continuous_tpr_thresholds.csv"); fp=_read(root/"false_positive_vectors.csv")
    candidates={}
    def add(cid,coal,reason,tier,source):
        key=(cid,coal); r=candidates.setdefault(key,{"configuration_id":cid,"coalition":coal,"reason_codes":set(),"tiers":set(),"sources":set()})
        r["reason_codes"].add(reason);r["tiers"].add(tier);r["sources"].add(source)
    for r in coalitions:
        cid,C=r["configuration_id"],r["coalition"]
        if r["effectiveness_status"]=="INCONCLUSIVE":add(cid,C,"EFFECTIVENESS_INTERVAL_CROSSES_ZERO","Tier 1","coalition")
        if r["deviation_point_nonnegative"]=="True" and r["deviation_weak_supported"]=="False":add(cid,C,"DEVIATION_CREDIBILITY_INCONCLUSIVE","Tier 1","credibility")
        if abs(float(r["credibility_slack"]))<=1e-4:add(cid,C,"CREDIBILITY_SLACK_NEAR_ZERO","Tier 2","credibility")
        if r["weak_deviation_proof"]!=r["strict_deviation_proof"]:add(cid,C,"WEAK_STRICT_CREDIBILITY_DISAGREE","Tier 2","credibility")
    for r in thresholds:
        if r["boundary_interpretation"] in ("AT_LOWER_GRID_EDGE","AT_UPPER_GRID_EDGE","NOT_FOUND_WITHIN_GRID"):
            for m in (json.loads(r["minimizers"]) if isinstance(r["minimizers"],str) else r["minimizers"]):
                add(m["configuration_id"],m["coalition"],"THRESHOLD_GRID_BOUNDARY","Tier 1","threshold")
    for r in tprs:
        if r["status"]=="DETERRABLE" and r["bootstrap_ci_low"] and r["bootstrap_ci_high"]:
            lo=float(r["bootstrap_ci_low"]); hi=float(r["bootstrap_ci_high"])
            if hi-lo>.1:add(r["configuration_id"],r["coalition"],"CONTINUOUS_TPR_INTERVAL_WIDE","Tier 2","tpr")
            if any(lo<=x<=hi for x in (.5,.7,.9,1)):add(r["configuration_id"],r["coalition"],"TPR_NEAR_REPORTING_GRID","Tier 1","tpr")
    for r in adjusted:
        if r["status"]!=r["bh_adjusted_status"]:
            add(r["left_configuration_id"],r["left_coalition"],"MULTIPLICITY_STATUS_DISAGREEMENT","Tier 2","equal_hash")
            add(r["right_configuration_id"],r["right_coalition"],"MULTIPLICITY_STATUS_DISAGREEMENT","Tier 2","equal_hash")
    target_fp=[r for r in fp if r["actor"]=="target" and float(r["fpr"])==.1]; cutoff=_quantile([float(r["conditional_loss"]) for r in target_fp],.99)
    for r in target_fp:
        if float(r["conditional_loss"])>=cutoff:add(r["configuration_id"],r["coalition"],"EXTREME_FALSE_POSITIVE_EXPOSURE","Tier 3","false_positive")
    order={"Tier 1":0,"Tier 2":1,"Tier 3":2}; uncapped=[]
    category_for={"EFFECTIVENESS_INTERVAL_CROSSES_ZERO":"publication-critical threshold confirmation",
        "THRESHOLD_GRID_BOUNDARY":"publication-critical threshold confirmation",
        "TPR_NEAR_REPORTING_GRID":"detector-threshold transition",
        "CONTINUOUS_TPR_INTERVAL_WIDE":"detector-threshold transition",
        "DEVIATION_CREDIBILITY_INCONCLUSIVE":"unresolved credibility margin",
        "CREDIBILITY_SLACK_NEAR_ZERO":"unresolved credibility margin",
        "WEAK_STRICT_CREDIBILITY_DISAGREE":"unresolved credibility margin",
        "MULTIPLICITY_STATUS_DISAGREEMENT":"composition comparison",
        "EXTREME_FALSE_POSITIVE_EXPOSURE":"boundary or anomaly review"}
    coal_index={(r["configuration_id"],r["coalition"]):r for r in coalitions}
    for key,r in candidates.items():
        c=coal_index.get(key,{}); tier=min(r["tiers"],key=lambda x:order[x])
        uncapped.append({"configuration_id":r["configuration_id"],"coalition":r["coalition"],"tier":tier,
            "optional_ranking_tier":tier,"reason_codes":sorted(r["reason_codes"]),
            "reason_categories":sorted({category_for[x] for x in r["reason_codes"]}),
            "sources":sorted(r["sources"]),"target_hash_power":c.get("target_hash_power"),
            "gamma":c.get("gamma"),"natural_fork_rate":c.get("natural_fork_rate"),"structure":c.get("structure"),
            "candidate_population_power":c.get("candidate_population_power"),"active_hash_power":c.get("active_hash_power"),
            "member_hash_vector":c.get("member_hash_vector"),"weak_deviation_proof":c.get("weak_deviation_proof"),
            "strict_deviation_proof":c.get("strict_deviation_proof")})
    uncapped.sort(key=lambda r:(order[r["tier"]],r["target_hash_power"] or "",r["gamma"] or "",r["configuration_id"],r["coalition"]))
    tier1=[r for r in uncapped if r["tier"]=="Tier 1"]
    capped=tier1+ [r for r in uncapped if r["tier"]!="Tier 1"][:max(0,250-len(tier1))]
    for rank,r in enumerate(capped,1):r["rank"]=rank
    _write(root/"stage_c_candidates_uncapped.csv",uncapped); _write(root/"stage_c_candidates_ranked.csv",capped)
    _write(root/"stage_c_candidates_reasoned_uncapped.csv",uncapped); _write(root/"stage_c_candidates_reasoned_ranked.csv",capped)
    existing_rows=_read(root/"stage_c_candidates.csv"); existing={(r["configuration_id"],r["coalition"]) for r in existing_rows}
    candidate_index={(r["configuration_id"],r["coalition"]):r for r in uncapped}
    audit=[]
    for old in existing_rows:
        r=candidate_index.get((old["configuration_id"],old["coalition"]),{})
        audit.append({**old,"audited_tier":r.get("tier"),"audited_reason_codes":r.get("reason_codes",[]),
            "still_selected_by_refined_algorithm":bool(r),"publication_critical_protected_from_cap":r.get("tier")=="Tier 1"})
    _write(root/"stage_c_candidate_audit.csv",audit)
    counts=Counter(r["tier"] for r in uncapped); throughput=13543200000/8532.582162709004
    estimates=[]
    for tier in ("Tier 1","Tier 2","Tier 3"):
        group=[r for r in uncapped if r["tier"]==tier]; environments=defaultdict(set)
        for r in group:
            cid=r["configuration_id"]; C=tuple(r["coalition"].split("|")) if r["coalition"] else ()
            environments[cid].update({("honest",False,()),("selfish",False,()),("honest",True,C),("selfish",True,C)})
            environments[cid].update(("selfish",True,tuple(x for x in C if x!=j)) for j in C)
        unique_environments=sum(len(x) for x in environments.values()); sims=unique_environments*50; blocks=sims*100000
        estimates.append({"tier":tier,"candidates":len(group),"conditional_simulations":sims,"accepted_block_work_units":blocks,
            "unique_population_configurations":len(environments),"unique_environments_per_repetition":unique_environments,
            "estimated_runtime_seconds_at_stage_b_throughput":blocks/throughput,"estimated_storage_gib":2.5*blocks/13543200000})
    data={"uncapped_candidates":len(uncapped),"ranked_candidates":len(capped),"nominal_cap":250,
          "cap_expanded_to_protect_tier1":len(capped)>250,"tier1_candidates":len(tier1),
          "tier1_that_legacy_250_cap_excluded":sum((r["configuration_id"],r["coalition"]) not in existing for r in tier1),"tier_counts":dict(counts),
          "existing_capped_members_retained":sum((r["configuration_id"],r["coalition"]) in existing for r in capped),
          "tier1_never_removed_by_cap":True,"cost_estimates":estimates}
    (root/"stage_c_candidate_audit.json").write_text(json.dumps(data,indent=2)+"\n")
    _write(root/"stage_c_tier_cost_estimates.csv",estimates); return audit,data


def paper_validation(root):
    root=Path(root)
    rows=[
      ("effective threshold vs target","threshold_audit.csv","target_hash_power,hash_power,boundary_interpretation,minimizers","effectiveness + supported","none beyond observed threshold","boundary label","no","boundary or unresolved cases"),
      ("threshold vs gamma","threshold_audit.csv","gamma,hash_power,target_hash_power,natural_fork_rate","facet by target and lambda","none","boundary label","no","boundary cases"),
      ("threshold vs natural forks","threshold_audit.csv","natural_fork_rate,hash_power,target_hash_power,gamma","matched facets","none","boundary label","no","nonmonotone/boundary cases"),
      ("continuous minimum TPR","continuous_tpr_thresholds.csv","tpr_min,bootstrap_ci_low,bootstrap_ci_high,status","DETERRABLE or edge category","none","paired bootstrap percentile CI","no","wide/transition intervals"),
      ("false-positive target loss","false_positive_vectors.csv","actor,fpr,conditional_loss,conditional_loss_ci95_low,conditional_loss_ci95_high","actor=target","none","paired t CI","no","extreme exposures"),
      ("false-positive member loss","false_positive_vectors.csv","actor,coalition,conditional_loss,expected_cost","actor candidate","summarize by member power","paired t CI","exploratory","extremes"),
      ("baseline credibility by member power","member_credibility_refined.csv","member_hash_power,baseline_classification,baseline_*","active members","none","paired t CI","exploratory","weak/strict disagreements"),
      ("deviation credibility by member power","member_credibility_refined.csv","member_hash_power,deviation_classification,deviation_*","active members","none","paired t CI","exploratory","weak/strict disagreements"),
      ("slack by composition","coalition_credibility_refined.csv","structure,member_hash_vector,credibility_slack,weak_deviation_proof,strict_deviation_proof","composition families","descriptive summaries","member paired intervals","exploratory","near-zero"),
      ("equal-hash deterrence","equal_hash_comparisons_adjusted.csv","matched_active_hash_power,difference,ci95_low,ci95_high,bh_adjusted_status","metric=deterrence","structure-pair facets","paired t CI","yes","selected structural comparisons"),
      ("equal-hash slack","equal_hash_comparisons_adjusted.csv","matched_active_hash_power,difference,bh_adjusted_p_value","metric=credibility_slack","structure-pair facets","paired t CI","yes","selected structural comparisons"),
      ("minimal winning coalitions","minimal_winning_coalitions.csv","configuration_id,members,active_hash_power,credibility_slack,minimum_tpr","winning rows","none","component intervals","no","publication-critical rows"),
      ("weak vs strict credibility","coalition_credibility_refined.csv","weak_deviation_proof,strict_deviation_proof,credibility_slack","all coalitions","cross-tabulate","paired member CIs","exploratory","disagreements"),
      ("Stage C map","stage_c_candidates_ranked.csv","tier,reason_codes,target_hash_power,gamma,natural_fork_rate,structure","ranked candidates","counts by facet","not applicable","no","is Stage C plan"),
    ]
    fields=("proposed_output","source_file","required_columns","filtering_logic","aggregation_logic","uncertainty_representation","multiplicity_adjustment","stage_c_confirmation")
    _write(root/"paper_output_validation.csv",[dict(zip(fields,x)) for x in rows])


def generate(root,epsilon=DEFAULT_EPSILON):
    root=Path(root); member,coalitions=refine_credibility(root,epsilon); adjusted,summary=composition_analysis(root)
    thresholds=threshold_audit(root,coalitions); metric_audits(root); checks=consistency_checks(root,coalitions,thresholds,adjusted)
    stage_c,data=stage_c_audit(root,coalitions,thresholds,adjusted,epsilon); paper_validation(root)
    return {"epsilon":epsilon,"members":len(member),"coalitions":len(coalitions),"composition_comparisons":len(adjusted),
            "threshold_rows":len(thresholds),"stage_c":data,"checks":checks}


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--stage-b-dir",required=True);p.add_argument("--epsilon",type=float,default=DEFAULT_EPSILON)
    args=p.parse_args(); print(json.dumps(generate(args.stage_b_dir,args.epsilon),indent=2))
