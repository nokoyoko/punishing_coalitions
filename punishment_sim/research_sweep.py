from __future__ import annotations

import csv
import concurrent.futures
import hashlib
import itertools
import json
import math
import random
import time
from decimal import Decimal
from functools import lru_cache
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from .coalition import MODEL_VERSION, Population, config_id, mining_cache_key, paired_stats, status, study, subsets


@dataclass(frozen=True)
class SweepTask:
    population: Population
    family: str
    structure: str
    candidate_total: float
    coalitions: tuple[tuple[str, ...], ...]


STRUCTURES = {
    "singleton": (1.0,),
    "two_equal": (.5, .5),
    "two_unequal": (.25, .75),
    "three_equal": (1/3, 1/3, 1/3),
    "three_moderate": (.2, .3, .5),
    "three_concentrated": (.1, .2, .7),
}


def _mine_task_checkpoint(task,repetitions,tprs,fprs):
    audit={"hits":0,"misses":0}
    result=study(task.population,repetitions,tprs,fprs,selected_coalitions=task.coalitions,
                 simulation_cache={},cache_audit=audit)
    return config_id(asdict(task.population)),audit,result


def candidate_structure(name, total):
    weights=STRUCTURES[name]
    shares=[total*w/sum(weights) for w in weights]
    # Put any floating remainder in the last actor so shares sum exactly to total.
    shares[-1]=total-sum(shares[:-1])
    return tuple((f"c{i+1}",share) for i,share in enumerate(shares))


def _grid_units(value, step, name):
    """Convert a decimal hash-power value to exact integer grid units."""
    ratio=Decimal(str(value))/Decimal(str(step))
    if ratio != ratio.to_integral_value():
        raise ValueError(f"{name}={value} is not an exact multiple of composition step {step}")
    return int(ratio)


@lru_cache(maxsize=None)
def systematic_compositions(total, members, step=.01, minimum_member_power=.01):
    """Canonical nondecreasing compositions; permutations occur exactly once."""
    if members < 1: raise ValueError("members must be positive")
    total_units=_grid_units(total,step,"total")
    minimum_units=_grid_units(minimum_member_power,step,"minimum_member_power")
    if minimum_units < 1: raise ValueError("minimum_member_power must be at least one grid step")
    def visit(remaining, count, floor, prefix):
        if count == 1:
            if remaining >= floor: yield prefix+(remaining,)
            return
        for value in range(floor,remaining//count+1):
            yield from visit(remaining-value,count-1,value,prefix+(value,))
    scale=Decimal(str(step))
    output=[]
    for units in visit(total_units,members,minimum_units,()):
        shares=[float(scale*x) for x in units]
        shares[-1]=float(Decimal(str(total))-sum(Decimal(str(x)) for x in shares[:-1]))
        output.append(tuple(shares))
    return tuple(output)


@lru_cache(maxsize=None)
def _composition_count_units(total_units, members, minimum_units=1):
    if members == 0: return int(total_units == 0)
    if total_units < members*minimum_units: return 0
    return sum(_composition_count_units(total_units-x,members-1,x)
               for x in range(minimum_units,total_units//members+1))


def systematic_composition_count(total, members, step=.01, minimum_member_power=.01):
    """Count canonical compositions without materializing the potentially huge set."""
    return _composition_count_units(_grid_units(total,step,"total"),members,
                                    _grid_units(minimum_member_power,step,"minimum_member_power"))


def select_systematic_compositions(compositions, sampling=None):
    """Optionally sample deterministic quantiles of HHI; exhaustive is the default."""
    if not sampling or sampling.get("mode","exhaustive") == "exhaustive": return tuple(compositions)
    if sampling.get("mode") != "hhi_quantiles": raise ValueError("unknown systematic composition sampling mode")
    limit=int(sampling["max_per_cell"])
    if limit < 1: raise ValueError("max_per_cell must be positive")
    ordered=sorted(compositions,key=lambda x:(sum(v*v for v in x),x))
    if len(ordered) <= limit: return tuple(ordered)
    if limit == 1: return (ordered[len(ordered)//2],)
    indices=[round(i*(len(ordered)-1)/(limit-1)) for i in range(limit)]
    return tuple(ordered[i] for i in dict.fromkeys(indices))


def composition_space_report(spec):
    """Analytical top-level composition counts before gamma/fork/detection/repetitions."""
    comp=spec.get("composition",{}); systematic=comp.get("systematic")
    if not systematic: return {"rows":[],"by_cardinality":{},"by_target":{},"grand_total":0}
    step=float(systematic.get("power_step",.01)); minimum=float(systematic.get("minimum_member_power",step))
    floor=float(spec.get("minimum_residual_power",0)); rows=[]
    by_cardinality={}; by_target={}
    for alpha,total,members in itertools.product(comp.get("target_hash",[]),comp.get("candidate_power",[]),
                                                  systematic.get("member_counts",[])):
        feasible=1-float(alpha)-float(total) >= floor-1e-12
        count=systematic_composition_count(total,int(members),step,minimum) if feasible else 0
        rows.append({"target_hash_power":alpha,"coalition_total":total,"cardinality":members,
                     "composition_count":count,"feasible":feasible})
        by_cardinality[str(members)]=by_cardinality.get(str(members),0)+count
        by_target[str(alpha)]=by_target.get(str(alpha),0)+count
    return {"power_step":step,"minimum_member_power":minimum,"minimum_residual_power":floor,
            "rows":rows,"by_cardinality":by_cardinality,"by_target":by_target,
            "grand_total":sum(x["composition_count"] for x in rows)}


def generate_tasks(spec):
    seed=int(spec.get("seed",41000)); blocks=int(spec["accepted_blocks"]); tasks=[]; requested=0
    residual_floor=float(spec.get("minimum_residual_power",0))
    authorized={tuple(map(float,x)) for x in spec.get("authorized_environment_triplets",[])}
    authorized_file=spec.get("authorized_environment_file")
    if authorized_file:
        path=Path(authorized_file)
        if not path.exists():
            raise FileNotFoundError(f"profitable-environment classification must be regenerated first: {path}")
        with path.open(newline="") as f:
            rows=list(csv.DictReader(f))
        if rows and "authorized_for_punishment_study" in rows[0]:
            admitted=[r for r in rows if str(r["authorized_for_punishment_study"]).lower()=="true"]
        elif rows and "profitable_vanilla_selfish_mining" in rows[0]:
            admitted=[r for r in rows if str(r["profitable_vanilla_selfish_mining"]).lower()=="true"]
        else:  # Historical representation-sensitivity files remain readable.
            admitted=[r for r in rows if r.get("statistically_supported_profitability_status")=="SELFISH_PROFITABLE"]
        authorized={(float(r["target_hash_power"]),float(r["gamma"]),float(r["natural_fork_rate"])) for r in admitted}
        if not authorized: raise ValueError("authorized_environment_file contains no admitted environments")
    def environment_allowed(alpha,gamma,rate):
        return not authorized or (float(alpha),float(gamma),float(rate)) in authorized
    agg=spec.get("aggregate",{})
    for alpha,power,gamma,rate in itertools.product(agg.get("target_hash",[]),agg.get("coalition_power",[]),
                                                   agg.get("gamma",[]),agg.get("natural_fork_rate",[])):
        if not environment_allowed(alpha,gamma,rate): continue
        requested+=1
        if 1-alpha-power < residual_floor-1e-12 or alpha+power >= 1: continue
        pop=Population(alpha,candidate_structure("singleton",power),gamma,rate,blocks,seed)
        tasks.append(SweepTask(pop,"aggregate","singleton",power,(("c1",),)))
    comp=spec.get("composition",{})
    systematic=comp.get("systematic")
    if systematic:
        step=float(systematic.get("power_step",.01)); minimum=float(systematic.get("minimum_member_power",step))
        for alpha,total,gamma,rate,members in itertools.product(comp.get("target_hash",[]),comp.get("candidate_power",[]),
                comp.get("gamma",[]),comp.get("natural_fork_rate",[]),systematic.get("member_counts",[])):
            if not environment_allowed(alpha,gamma,rate): continue
            exhaustive=systematic_compositions(total,int(members),step,minimum)
            selected=select_systematic_compositions(exhaustive,systematic.get("sampling")); requested+=len(selected)
            if 1-alpha-total < residual_floor-1e-12 or alpha+total >= 1: continue
            for shares in selected:
                candidates=tuple((f"c{i+1}",share) for i,share in enumerate(shares))
                pop=Population(alpha,candidates,gamma,rate,blocks,seed)
                ids=tuple(i for i,_ in candidates)
                # The full composition is the top-level coalition. study() separately
                # evaluates every member's leave-one-out deviation.
                structure="systematic_"+"_".join(f"{int(round(x/step))}" for x in shares)
                tasks.append(SweepTask(pop,"composition",structure,total,(ids,)))
    else:
        for alpha,total,gamma,rate,structure in itertools.product(comp.get("target_hash",[]),comp.get("candidate_power",[]),
                comp.get("gamma",[]),comp.get("natural_fork_rate",[]),comp.get("structures",[])):
            if not environment_allowed(alpha,gamma,rate): continue
            requested+=1
            if 1-alpha-total < residual_floor-1e-12 or alpha+total >= 1: continue
            candidates=candidate_structure(structure,total)
            pop=Population(alpha,candidates,gamma,rate,blocks,seed)
            ids=tuple(i for i,_ in candidates)
            tasks.append(SweepTask(pop,"composition",structure,total,tuple(C for C in subsets(ids) if C)))
    # Identical populations are mined once; union requested coalitions and retain family labels.
    grouped={}
    for task in tasks:
        key=asdict(task.population).__repr__()
        if key not in grouped: grouped[key]=task
        else:
            old=grouped[key]
            grouped[key]=SweepTask(old.population,"both" if old.family!=task.family else old.family,
                old.structure,old.candidate_total,tuple(sorted(set(old.coalitions)|set(task.coalitions),key=lambda x:(len(x),x))))
    return list(grouped.values()),requested,len(tasks)


def _required_keys(tasks,repetitions):
    keys=set(); requests=0
    for task in tasks:
        p=task.population
        for rep in range(repetitions):
            environments=[("honest",False,()),("selfish",False,())]
            for C in task.coalitions:
                environments.extend((("honest",True,C),("selfish",True,C)))
                environments.extend(("selfish",True,tuple(x for x in C if x!=j)) for j in C)
            for strategy,flagged,C in environments:
                requests+=1; keys.add(mining_cache_key(p,rep,strategy,flagged,C))
    return keys,requests


def dry_run(spec):
    tasks,requested,valid=generate_tasks(spec); repetitions=int(spec["repetitions"])
    keys,requests=_required_keys(tasks,repetitions)
    coalition_conditions=sum(len(t.coalitions) for t in tasks)
    algebraic=coalition_conditions*len(spec["tpr"])*len(spec["fpr"])
    return {"stage":spec.get("stage","unspecified"),"requested_population_configurations":requested,
        "valid_population_requests":valid,"unique_population_configurations":len(tasks),
        "coalition_conditions":coalition_conditions,"conditional_environment_requests":requests,
        "unique_mining_simulations":len(keys),"estimated_cache_hits":requests-len(keys),
        "algebraic_detector_evaluations":algebraic,
        "accepted_block_work_units":len(keys)*int(spec["accepted_blocks"])}


def _quantile(values,p):
    values=sorted(values); x=(len(values)-1)*p; lo=math.floor(x); hi=math.ceil(x)
    return values[lo] if lo==hi else values[lo]+(x-lo)*(values[hi]-values[lo])


def tpr_threshold(rows,bootstrap_samples=1000,seed=0):
    s0=[r["U_S0"]["target"]["payoff"] for r in rows]
    h=[r["U_H"]["target"]["payoff"] for r in rows]
    sc=[r["U_SC"]["target"]["payoff"] for r in rows]
    a,b,c=mean(s0),mean(h),mean(sc)
    common={"bootstrap_seed":seed,"bootstrap_requested_samples":bootstrap_samples}
    if a<=b: return {"tpr_min":0.0,"status":"SELFISH_ALREADY_UNPROFITABLE","bootstrap_ci_low":None,"bootstrap_ci_high":None,
                     "bootstrap_valid_samples":0,"bootstrap_invalid_samples":bootstrap_samples,**common}
    if c>=b or a<=c: return {"tpr_min":None,"status":"NOT_DETERRENT_AT_TPR_1","bootstrap_ci_low":None,"bootstrap_ci_high":None,
                            "bootstrap_valid_samples":0,"bootstrap_invalid_samples":bootstrap_samples,**common}
    value=max(0,min(1,(a-b)/(a-c))); rng=random.Random(seed); estimates=[]; n=len(rows)
    for _ in range(bootstrap_samples):
        idx=[rng.randrange(n) for _ in range(n)]; aa=mean(s0[i] for i in idx); bb=mean(h[i] for i in idx); cc=mean(sc[i] for i in idx)
        if aa>bb and cc<bb and aa>cc: estimates.append(max(0,min(1,(aa-bb)/(aa-cc))))
    return {"tpr_min":value,"status":"DETERRABLE",
        "bootstrap_ci_low":_quantile(estimates,.025) if estimates else None,
        "bootstrap_ci_high":_quantile(estimates,.975) if estimates else None,
        "bootstrap_valid_samples":len(estimates),"bootstrap_invalid_samples":bootstrap_samples-len(estimates),**common}


def group_equal_active(rows,tolerance=1e-12):
    groups={}
    for row in rows:
        if not row["coalition"] or row["active_hash_power"] <= tolerance:
            continue
        key=(row["target_hash_power"],row["gamma"],row["natural_fork_rate"],
             row.get("candidate_population_power"),row.get("accepted_block_target"),
             row.get("repetition_count"),round(row["active_hash_power"],12))
        groups.setdefault(key,[]).append(row)
    return [v for v in groups.values() if len({(x["configuration_id"],x["coalition"]) for x in v})>1]


def _flat(row):
    return {k:(json.dumps(v,sort_keys=True) if isinstance(v,(dict,list,tuple)) else v) for k,v in row.items()}


def _write_csv(path,rows):
    rows=[_flat(r) for r in rows]; path=Path(path)
    if not rows: path.write_text(""); return
    fields=[]
    for row in rows:
        for key in row:
            if key not in fields: fields.append(key)
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def _write_cache_key_audit(path,tasks,repetitions):
    keys,_=_required_keys(tasks,repetitions)
    fields=["cache_key_id","model_version","target_hash_power","candidate_distribution","gamma","natural_fork_rate",
            "accepted_block_target","seed","strategy","flagged","active_coalition","result"]
    with Path(path).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for key in sorted(keys,key=repr):
            w.writerow(dict(zip(fields[:-1],[hashlib.sha256(repr(key).encode()).hexdigest()[:20],key[0],key[1],json.dumps(key[2]),
                key[3],key[4],key[5],key[6],key[7],key[8],json.dumps(key[9])]),result="cache_miss_or_resumed"))


def output_completeness_audit(outputs):
    """Verify that named outputs contain the fields needed by each paper question."""
    specs=[
      ("punishment power needed","thresholds",["threshold_configuration_id","hash_power","threshold_kind"],"repetitions"),
      ("threshold covariates","thresholds",["target_hash_power","gamma","natural_fork_rate"],"repetitions"),
      ("composition effect on deterrence","equal_hash_comparisons",["matched_active_hash_power","metric","difference","ci95_low","ci95_high"],"repetitions"),
      ("composition effect on baseline credibility","equal_hash_comparisons",["metric","difference","status"],"repetitions"),
      ("composition effect on deviation credibility","equal_hash_comparisons",["metric","difference","status"],"repetitions"),
      ("weakest member","coalitions",["configuration_id","weakest_member","weakest_members","credibility_slack"],"repetitions"),
      ("minimum detector TPR","tpr_thresholds",["configuration_id","tpr_min","status","bootstrap_seed"],"repetitions"),
      ("false-positive actor costs","false_positive_vectors",["configuration_id","actor","conditional_loss","expected_cost"],"repetitions"),
      ("minimal winning coalitions","minimal_winning_coalitions",["configuration_id","coalition","members","active_hash_power"],"repetitions"),
      ("deviation-margin robustness","coalitions",["credibility_slack","robustness_bin","protocol_payoff_tolerance"],"repetitions"),
      ("Stage C confirmation candidates","stage_c_candidates",["configuration_id","selection_reason"],"repetitions"),
      ("paper outputs without mining rerun","coalitions",["configuration_id","target_hash_power","gamma","natural_fork_rate"],"repetitions"),
    ]
    filenames={"thresholds":"minimum_thresholds.csv","coalitions":"coalition_results.csv",
        "tpr_thresholds":"continuous_tpr_thresholds.csv","repetitions":"repetition_metrics.csv"}
    audit=[]
    for question,name,required,rep_name in specs:
        rows=outputs.get(name,[]); available=set().union(*(set(r) for r in rows)) if rows else set()
        missing=[x for x in required if x not in available]
        rep_available=bool(outputs.get(rep_name))
        complete=bool(rows) and not missing and rep_available
        audit.append({"research_question":question,"required_output":name,"source_file":filenames.get(name,f"{name}.csv"),
            "required_columns":required,"repetition_level_source":filenames.get(rep_name,f"{rep_name}.csv"),
            "repetition_level_data_available":"yes" if rep_available else "no",
            "directly_answerable":"yes" if complete else "no",
            "deficiency":"" if complete else ("missing columns: "+", ".join(missing) if missing else "output has no rows"),
            "recommended_correction":"none" if complete else "emit the missing fields before paper analysis"})
    return audit


def _thresholds(coalitions,detector):
    output=[]
    base_groups={}
    for row in coalitions:
        key=(row["target_hash_power"],row["gamma"],row["natural_fork_rate"],row["structure"])
        base_groups.setdefault(key,[]).append(row)
    for key,rows in base_groups.items():
        for metric,point_key,supported_key in (("effectiveness","effectiveness_point","effectiveness_status"),
                ("baseline_credibility","baseline_credible_point","baseline_credible"),
                ("deviation_credibility","deviation_proof_point","deviation_proof")):
            for kind,predicate in (("point",lambda r:r[point_key]),
                                   ("supported",lambda r:r[supported_key] is True or r[supported_key]=="SUPPORTED")):
                eligible=[r for r in rows if r["coalition"] and predicate(r)]
                hp=min((r["active_hash_power"] for r in eligible),default=None)
                minimizers=[{"configuration_id":r["configuration_id"],"coalition":r["coalition"],
                    "member_hash_vector":r.get("member_hash_vector",[]),"coalition_cardinality":r.get("cardinality",len(r.get("members",[]))),
                    "candidate_structure":r["structure"]} for r in eligible if hp is not None and abs(r["active_hash_power"]-hp)<1e-12]
                evaluated=sorted({r["active_hash_power"] for r in rows if r["coalition"]})
                output.append({"target_hash_power":key[0],"gamma":key[1],"natural_fork_rate":key[2],"structure":key[3],
                    "threshold_metric":metric,"threshold_kind":kind,"hash_power":hp,"minimizers":minimizers,
                    "no_qualifying_coalition":hp is None,"threshold_at_grid_edge":hp in ({evaluated[0],evaluated[-1]} if evaluated else set())})
    for tpr in sorted({r["tpr"] for r in detector}):
        groups={}
        for r in detector:
            if r["tpr"]!=tpr:continue
            key=(r["target_hash_power"],r["gamma"],r["natural_fork_rate"],r["structure"])
            groups.setdefault(key,[]).append(r)
        for key,rows in groups.items():
            eligible=[r for r in rows if r["coalition"] and r["expected_effectiveness_status"]=="SUPPORTED"]
            hp=min((r["active_hash_power"] for r in eligible),default=None)
            minimizers=[{"configuration_id":r["configuration_id"],"coalition":r["coalition"],
                "member_hash_vector":next((c["member_hash_vector"] for c in coalitions if c["configuration_id"]==r["configuration_id"] and c["coalition"]==r["coalition"]),[]),
                "coalition_cardinality":len(r["members"]),"candidate_structure":r["structure"]}
                for r in eligible if hp is not None and abs(r["active_hash_power"]-hp)<1e-12]
            evaluated=sorted({r["active_hash_power"] for r in rows if r["coalition"]})
            output.append({"target_hash_power":key[0],"gamma":key[1],"natural_fork_rate":key[2],"structure":key[3],
                "threshold_metric":"detector_effectiveness","threshold_kind":"supported","tpr":tpr,"hash_power":hp,
                "minimizers":minimizers,"no_qualifying_coalition":hp is None,
                "threshold_at_grid_edge":hp in ({evaluated[0],evaluated[-1]} if evaluated else set())})
    return output


def run_sweep(spec,output_dir):
    if spec.get("expected_model_version",MODEL_VERSION)!=MODEL_VERSION:
        raise ValueError(f"configuration expects {spec['expected_model_version']}, simulator is {MODEL_VERSION}")
    started=time.monotonic(); out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    tasks,requested,valid=generate_tasks(spec); audit={"hits":0,"misses":0}
    checkpoint_dir=out/"checkpoints"; checkpoint_dir.mkdir(exist_ok=True)
    mining_configs=[]; coalition_rows=[]; member_rows=[]; detector_rows=[]; tpr_rows=[]; fp_rows=[]; repetition_rows=[]; boundary_rows=[]
    raw_results={}; reps_n=int(spec["repetitions"]); bootstrap=int(spec.get("bootstrap_samples",1000))
    false_positive_keys=set()
    missing=[t for t in tasks if not (checkpoint_dir/f"{config_id(asdict(t.population))}.json").exists()]
    resumed_at_start=len(tasks)-len(missing); new_checkpoints=len(missing)
    workers=max(1,int(spec.get("execution_workers",1)))
    if missing and workers>1:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            futures=[executor.submit(_mine_task_checkpoint,t,reps_n,spec["tpr"],spec["fpr"]) for t in missing]
            for future in concurrent.futures.as_completed(futures):
                cid,task_audit,result=future.result()
                (checkpoint_dir/f"{cid}.json").write_text(json.dumps(
                    {"configuration_id":cid,"cache_audit":task_audit,"result":result})+"\n")
    for task in tasks:
        cid=config_id(asdict(task.population)); checkpoint=checkpoint_dir/f"{cid}.json"
        if checkpoint.exists():
            saved=json.loads(checkpoint.read_text()); result=saved["result"]
            task_audit=saved["cache_audit"]
        else:
            task_audit={"hits":0,"misses":0}
            result=study(task.population,reps_n,spec["tpr"],spec["fpr"],selected_coalitions=task.coalitions,
                         simulation_cache={},cache_audit=task_audit)
            checkpoint.write_text(json.dumps({"configuration_id":cid,"cache_audit":task_audit,"result":result})+"\n")
        audit["hits"]+=task_audit["hits"]; audit["misses"]+=task_audit["misses"]
        raw_results[cid]=result
        mining_configs.append({"configuration_id":cid,"family":task.family,"structure":task.structure,"model_version":MODEL_VERSION,
            "target_hash_power":task.population.target_hash_power,"candidate_total":task.candidate_total,
            "candidate_distribution":dict(task.population.candidates),"residual_honest_power":task.population.residual_hash_power,
            "gamma":task.population.gamma,"natural_fork_rate":task.population.natural_fork_rate,
            "repetitions":reps_n,"accepted_blocks":task.population.target_accepted_blocks})
        rep_by_c={c:[r for r in result["repetitions"] if r["coalition"]==c] for c in {r["coalition"] for r in result["repetitions"]}}
        members_by_c={}
        for m in result["members"]: members_by_c.setdefault(m["coalition"],[]).append(m)
        for s in result["summary"]:
            C=s["coalition"]; ms=members_by_c.get(C,[]); weak=min(ms,key=lambda x:x["deviation"]["mean"]) if ms else None
            slack=weak["deviation"]["mean"] if weak else None
            reps=rep_by_c[C]; sc_terminal=[r["terminal"]["U_SC"] for r in reps]
            s0_terminal=[r["terminal"]["U_S0"] for r in reps]
            sc_bounds=[x["omitted_share_bound"] for x in sc_terminal]
            reduction_bounds=[a["omitted_share_bound"]+b["omitted_share_bound"] for a,b in zip(s0_terminal,sc_terminal)]
            max_bound=max(sc_bounds); dstat=s["deterrence"]
            boundary_label=("BOUNDARY_EFFECT_NEGLIGIBLE" if max_bound==0 else
                "BOUNDARY_EFFECT_OVERLAPS_POINT_MARGIN" if abs(dstat["mean"])<=max_bound else
                "BOUNDARY_EFFECT_REQUIRES_REVIEW" if dstat["ci95_low"]<=max_bound else "BOUNDARY_EFFECT_NEGLIGIBLE")
            robustness=("near-zero" if slack is not None and slack<=spec["robustness_bins"][0] else
                        "small-positive" if slack is not None and slack<=spec["robustness_bins"][1] else
                        "moderate-positive" if slack is not None else None)
            row={**s,"configuration_id":cid,"family":task.family,"structure":task.structure,"model_version":MODEL_VERSION,
                "candidate_population_power":task.candidate_total,"member_hash_vector":[dict(task.population.candidates)[j] for j in s["members"]],
                "credibility_slack":slack,"protocol_payoff_tolerance":slack,"robustness_bin":robustness,
                "terminal_private_lead_mean":mean(x["private_lead"] for x in sc_terminal),
                "terminal_private_lead_max":max(x["private_lead"] for x in sc_terminal),
                "terminal_private_lead_nonzero_fraction":mean(x["private_lead"]>0 for x in sc_terminal),
                "terminal_omitted_share_bound_mean":mean(sc_bounds),"terminal_omitted_share_bound_max":max_bound,
                "boundary_effect_status":boundary_label,
                "boundary_could_change_point_deterrence":abs(dstat["mean"])<=max_bound,
                "boundary_could_affect_supported_deterrence":dstat["ci95_low"]>0 and dstat["ci95_low"]<=max_bound,
                "target_hash_power":task.population.target_hash_power,"gamma":task.population.gamma,
                "natural_fork_rate":task.population.natural_fork_rate}
            coalition_rows.append(row)
            trs=tpr_threshold(rep_by_c[C],bootstrap,int(hashlib.sha256(f"{cid}:{C}".encode()).hexdigest()[:16],16))
            tpr_rows.append({"configuration_id":cid,"coalition":C,"active_hash_power":s["active_hash_power"],"model_version":MODEL_VERSION,
                "target_hash_power":task.population.target_hash_power,"gamma":task.population.gamma,
                "natural_fork_rate":task.population.natural_fork_rate,"structure":task.structure,**trs})
            for r in rep_by_c[C]:
                repetition_rows.append({"configuration_id":cid,"repetition":r["repetition"],"coalition":C,"model_version":MODEL_VERSION,
                    "target_hash_power":task.population.target_hash_power,"gamma":task.population.gamma,"natural_fork_rate":task.population.natural_fork_rate,
                    "deterrence":r["U_H"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"],
                    "punishment_reduction":r["U_S0"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"],
                    "member_baseline":{j:r["U_SC"][j]["payoff"]-r["U_S0"][j]["payoff"] for j in s["members"]},
                    "member_deviation":{j:r["U_SC"][j]["payoff"]-r["leaveouts"][j][j]["payoff"] for j in s["members"]},
                    "baseline_credibility_margin":min((r["U_SC"][j]["payoff"]-r["U_S0"][j]["payoff"]
                                                        for j in s["members"]),default=None),
                    "deviation_credibility_margin":min((r["U_SC"][j]["payoff"]-r["leaveouts"][j][j]["payoff"]
                                                         for j in s["members"]),default=None),
                    "credibility_slack":min((r["U_SC"][j]["payoff"]-r["leaveouts"][j][j]["payoff"]
                                              for j in s["members"]),default=None),
                    "terminal_private_lead_sc":r["terminal"]["U_SC"]["private_lead"],
                    "terminal_uncredited_private_blocks_sc":r["terminal"]["U_SC"]["uncredited_private_blocks"],
                    "terminal_accepted_blocks_sc":r["terminal"]["U_SC"]["accepted_blocks"],
                    "terminal_omitted_share_bound_sc":r["terminal"]["U_SC"]["omitted_share_bound"],
                    "deterrence_margin_overlaps_terminal_bound":abs(r["U_H"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"])<=r["terminal"]["U_SC"]["omitted_share_bound"],
                    "punishment_reduction_margin_overlaps_terminal_bound":abs(r["U_S0"]["target"]["payoff"]-r["U_SC"]["target"]["payoff"])<=(r["terminal"]["U_S0"]["omitted_share_bound"]+r["terminal"]["U_SC"]["omitted_share_bound"])})
            boundary_rows.append({"configuration_id":cid,"coalition":C,"structure":task.structure,"model_version":MODEL_VERSION,
                "target_hash_power":task.population.target_hash_power,"gamma":task.population.gamma,
                "natural_fork_rate":task.population.natural_fork_rate,"active_hash_power":s["active_hash_power"],
                "mean_terminal_private_lead":mean(x["private_lead"] for x in sc_terminal),
                "maximum_terminal_private_lead":max(x["private_lead"] for x in sc_terminal),
                "fraction_nonzero_terminal_private_lead":mean(x["private_lead"]>0 for x in sc_terminal),
                "mean_omitted_share_bound":mean(sc_bounds),"maximum_omitted_share_bound":max_bound,
                "point_deterrence_could_change":abs(dstat["mean"])<=max_bound,
                "supported_deterrence_could_be_affected":dstat["ci95_low"]>0 and dstat["ci95_low"]<=max_bound,
                "boundary_effect_status":boundary_label})
        for m in result["members"]:
            member_rows.append({**m,"configuration_id":cid,"family":task.family,"structure":task.structure,"model_version":MODEL_VERSION,
                "target_hash_power":task.population.target_hash_power,"gamma":task.population.gamma,"natural_fork_rate":task.population.natural_fork_rate})
        for d in result["detector"]:
            detector_rows.append({**d,"configuration_id":cid,"family":task.family,"structure":task.structure,"model_version":MODEL_VERSION,
                "target_hash_power":task.population.target_hash_power,"gamma":task.population.gamma,"natural_fork_rate":task.population.natural_fork_rate})
            for actor,loss in d["false_positive_conditional_cost"].items():
                fp_key=(cid,d["coalition"],actor,d["fpr"])
                if fp_key in false_positive_keys: continue
                false_positive_keys.add(fp_key)
                fp_stat=d["false_positive_conditional_stats"][actor]
                fp_rows.append({"configuration_id":cid,"coalition":d["coalition"],"actor":actor,"fpr":d["fpr"],"model_version":MODEL_VERSION,
                    "conditional_loss":loss,"expected_cost":d["false_positive_expected_cost"][actor],
                    "conditional_loss_ci95_low":fp_stat["ci95_low"],"conditional_loss_ci95_high":fp_stat["ci95_high"],
                    "conditional_loss_status":status(fp_stat,strict=True),"paired_statistics":fp_stat,
                    "target_hash_power":task.population.target_hash_power,"gamma":task.population.gamma,
                    "natural_fork_rate":task.population.natural_fork_rate,"structure":task.structure})
    # Equal-active-hash paired comparisons.
    comparisons=[]; rep_index={(r["configuration_id"],r["coalition"]):[] for r in repetition_rows}
    for r in repetition_rows: rep_index[(r["configuration_id"],r["coalition"])].append(r)
    for group in group_equal_active(coalition_rows):
        for a,b in itertools.combinations(sorted(group,key=lambda x:(x["configuration_id"],x["coalition"])),2):
            if a["configuration_id"]==b["configuration_id"] and a["coalition"]==b["coalition"]:continue
            # A population may enter through both sweep families. Do not report a
            # duplicate representation as a composition comparison.
            composition_a=(a["cardinality"],tuple(sorted(a["member_hash_vector"])))
            composition_b=(b["cardinality"],tuple(sorted(b["member_hash_vector"])))
            if composition_a==composition_b: continue
            ar=sorted(rep_index[(a["configuration_id"],a["coalition"])],key=lambda x:x["repetition"])
            br=sorted(rep_index[(b["configuration_id"],b["coalition"])],key=lambda x:x["repetition"])
            common={"left_configuration_id":a["configuration_id"],"left_coalition":a["coalition"],
                "right_configuration_id":b["configuration_id"],"right_coalition":b["coalition"],
                "target_hash_power":a["target_hash_power"],"gamma":a["gamma"],"natural_fork_rate":a["natural_fork_rate"],
                "matched_active_hash_power":a["active_hash_power"],"left_cardinality":a["cardinality"],
                "right_cardinality":b["cardinality"],"left_weakest_hash":min(a["member_hash_vector"]),
                "right_weakest_hash":min(b["member_hash_vector"]),"left_structure":a["structure"],
                "right_structure":b["structure"],"left_member_hash_vector":a["member_hash_vector"],
                "right_member_hash_vector":b["member_hash_vector"],"directly_paired":True,
                "pairing_basis":"matched repetition identifiers and common-random-number seeds"}
            for metric in ("deterrence","punishment_reduction","baseline_credibility_margin",
                           "deviation_credibility_margin","credibility_slack"):
                left=[x[metric] for x in ar]; right=[x[metric] for x in br]; stat=paired_stats([x-y for x,y in zip(left,right)],left,right)
                comparisons.append({**common,"metric":metric,"difference":stat["mean"],
                    "ci95_low":stat["ci95_low"],"ci95_high":stat["ci95_high"],"status":status(stat, strict=True),
                    "paired_statistics":stat})
            for metric,left,right in (("weakest_member_hash",common["left_weakest_hash"],common["right_weakest_hash"]),
                                      ("coalition_cardinality",a["cardinality"],b["cardinality"])):
                difference=left-right
                comparisons.append({**common,"metric":metric,"difference":difference,
                    "ci95_low":difference,"ci95_high":difference,"status":"EXACT_DESCRIPTIVE",
                    "paired_statistics":None})
    thresholds=_thresholds(coalition_rows,detector_rows)
    for r in thresholds:
        r["model_version"]=MODEL_VERSION
        r["threshold_configuration_id"]=hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()[:16]
    tpr_index={(r["configuration_id"],r["coalition"]):r for r in tpr_rows}
    fp_index={}
    for r in fp_rows:
        fp_index.setdefault((r["configuration_id"],r["coalition"]),[]).append(r)
    minimal=[]
    for r in coalition_rows:
        if r["winning"] and not any(x["winning"] and x["configuration_id"]==r["configuration_id"] and set(x["members"])<set(r["members"]) for x in coalition_rows):
            minimal.append({**r,"minimum_tpr":tpr_index[(r["configuration_id"],r["coalition"])]["tpr_min"],
                            "false_positive_losses":fp_index.get((r["configuration_id"],r["coalition"]),[])})
    stage_c=[]
    for r in coalition_rows:
        reasons=[]
        if r["effectiveness_status"]=="INCONCLUSIVE": reasons.append("effectiveness_ci_crosses_zero")
        if r["members"] and r["winning_point"] and (not r["baseline_credible"] or not r["deviation_proof"]):
            reasons.append("winning_point_not_statistically_supported")
        t=tpr_index[(r["configuration_id"],r["coalition"])]
        if t["status"]=="DETERRABLE" and t["bootstrap_ci_low"] is not None and any(
                t["bootstrap_ci_low"]<=q<=t["bootstrap_ci_high"] for q in spec["tpr"]):
            reasons.append("tpr_interval_crosses_reporting_threshold")
        if reasons: stage_c.append({"configuration_id":r["configuration_id"],"coalition":r["coalition"],
            "target_hash_power":r["target_hash_power"],"gamma":r["gamma"],"natural_fork_rate":r["natural_fork_rate"],
            "structure":r["structure"],"candidate_population_power":r["candidate_population_power"],
            "active_hash_power":r["active_hash_power"],"selection_reason":"|".join(reasons)})
    priority={"effectiveness_ci_crosses_zero":0,"winning_point_not_statistically_supported":1,
              "tpr_interval_crosses_reporting_threshold":2}
    stage_c.sort(key=lambda r:(min(priority[x] for x in r["selection_reason"].split("|")),
                               r["target_hash_power"],r["gamma"],r["natural_fork_rate"],r["active_hash_power"],
                               r["configuration_id"],r["coalition"]))
    stage_c=stage_c[:int(spec.get("stage_c_max_candidates",250))]
    plan=dry_run(spec); plan.update({"actual_cache_hits":audit["hits"],"actual_cache_misses":audit["misses"],
        "actual_unique_mining_simulations":audit["misses"],"resumed_population_checkpoints":resumed_at_start,
        "new_population_checkpoints":new_checkpoints,"runtime_seconds":time.monotonic()-started})
    outputs={"mining_configurations":mining_configs,"coalitions":coalition_rows,"members":member_rows,
        "detector":detector_rows,"tpr_thresholds":tpr_rows,"false_positive_vectors":fp_rows,
        "equal_hash_comparisons":comparisons,"thresholds":thresholds,"minimal_winning_coalitions":minimal,
        "repetitions":repetition_rows,"cache_audit":plan,"stage_c_candidates":stage_c,"terminal_boundary_diagnostics":boundary_rows}
    audit_rows=output_completeness_audit(outputs); outputs["output_completeness_audit"]=audit_rows
    names={"mining_configurations":mining_configs,"coalition_results":coalition_rows,"member_credibility":member_rows,
        "detector_evaluations":detector_rows,"continuous_tpr_thresholds":tpr_rows,"false_positive_vectors":fp_rows,
        "equal_hash_comparisons":comparisons,"minimum_thresholds":thresholds,"minimal_winning_coalitions":minimal,
        "repetition_metrics":repetition_rows,"stage_c_candidates":stage_c,
        "output_completeness_audit":audit_rows,
        "aggregate_effectiveness_surfaces":[r for r in coalition_rows if r["family"] in ("aggregate","both")],
        "aggregate_supported_threshold_surfaces":[r for r in thresholds if r["structure"]=="singleton"],
        "continuous_tpr_threshold_surfaces":tpr_rows,"false_positive_conditional_loss_surfaces":fp_rows,
        "baseline_credibility_surfaces":member_rows,"deviation_proof_credibility_surfaces":member_rows,
        "credibility_slack_surfaces":coalition_rows,"weakest_member_summaries":coalition_rows,
        "terminal_boundary_diagnostics":boundary_rows}
    for name,rows in names.items(): _write_csv(out/f"{name}.csv",rows)
    _write_csv(out/"cache_audit.csv",[plan]); _write_csv(out/"dry_run_estimates.csv",[dry_run(spec)])
    _write_cache_key_audit(out/"cache_key_audit.csv",tasks,reps_n)
    _write_csv(out/"rejected_configurations.csv",[])
    (out/"output_completeness_audit.json").write_text(json.dumps(audit_rows,indent=2)+"\n")
    (out/"results.json").write_text(json.dumps(outputs,indent=2)+"\n")
    return outputs
