#!/usr/bin/env python3
from __future__ import annotations

import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analysis.stage_b_racefix import DEFAULT_SOURCE, ROOT, git_commit, obj, read_csv, truth, write_csv

STYLE={"figure.figsize":(7.2,4.4),"font.size":9,"axes.grid":True,"grid.alpha":.25,
       "axes.spines.top":False,"axes.spines.right":False,"savefig.dpi":180}
plt.rcParams.update(STYLE)
plt.rcParams["svg.hashsalt"]="stage-b-racefix-v1"
COLORS={"SUPPORTED":"#0072B2","INCONCLUSIVE":"#777777","REFUTED":"#D55E00",
        "STRICTLY_DEVIATION_PROOF":"#0072B2","WEAK_BREAK_EVEN_ONLY":"#E69F00","NEITHER":"#777777"}

def save(fig,out,name,rows,sources,metrics,filters="none",confidence="source intervals",stage_count=0):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    for ext in ("png","pdf","svg"):fig.savefig(out/f"{name}.{ext}",bbox_inches="tight")
    plt.close(fig); write_csv(out/f"{name}.csv",rows)
    meta={"source_files":sources,"filters":filters,"metrics":metrics,"confidence_method":confidence,
      "plotted_configuration_count":len({r.get('configuration_id') for r in rows if r.get('configuration_id')}),
      "plotted_observation_count":len(rows),"stage_c_dependent_point_count":stage_count,
      "generation_timestamp":datetime.fromtimestamp((DEFAULT_SOURCE/"mining_configurations.csv").stat().st_mtime,timezone.utc).isoformat(),"git_commit":git_commit(),"script_version":"racefix-analysis-v1"}
    (out/f"{name}.metadata.json").write_text(json.dumps(meta,indent=2)+"\n")

def _response(source,out,metric,label,prefix):
    rows=read_csv(source/"coalition_results.csv"); rows=[r for r in rows if r["structure"]=="singleton" and r["family"] in ("aggregate","both")]
    stage={(r["configuration_id"],r["coalition"]) for r in read_csv(source/"stage_c_candidates_reasoned_uncapped.csv")}
    for lam in ("0","0.005","0.02"):
      rr=[r for r in rows if float(r["natural_fork_rate"])==float(lam)]
      fig,axs=plt.subplots(2,3,figsize=(10.5,6.2),sharex=True,sharey=True); plotted=[]
      for ax,(env,g) in zip(axs.flat,sorted(_groups(rr,("target_hash_power","gamma")).items(),key=lambda z:tuple(map(float,z[0])))[:6]):
        g=sorted(g,key=lambda r:float(r["active_hash_power"])); stats=[obj(r[metric]) for r in g]
        x=[float(r["active_hash_power"]) for r in g]; y=[s["mean"] for s in stats]
        ax.plot(x,y,color="#0072B2",lw=1); ax.fill_between(x,[s["ci95_low"] for s in stats],[s["ci95_high"] for s in stats],color="#56B4E9",alpha=.25)
        ax.axhline(0,color="black",lw=.7);ax.set_title(f"α={env[0]}, γ={env[1]}")
        for r,s in zip(g,stats):
            pr={"configuration_id":r["configuration_id"],"coalition":r["coalition"],"target_hash_power":r["target_hash_power"],"gamma":r["gamma"],"natural_fork_rate":r["natural_fork_rate"],"active_hash_power":r["active_hash_power"],"estimate":s["mean"],"ci_low":s["ci95_low"],"ci_high":s["ci95_high"],"status":r.get("effectiveness_status",r.get("punishment_reduction_status","")),"terminal_sensitive":r["boundary_effect_status"]!="BOUNDARY_EFFECT_NEGLIGIBLE","stage_c":(r["configuration_id"],r["coalition"]) in stage};plotted.append(pr)
            if pr["terminal_sensitive"]:ax.scatter([x[g.index(r)]],[s["mean"]],facecolors="none",edgecolors="#D55E00",s=28)
      fig.supxlabel("Active coalition hash power");fig.supylabel(label);fig.suptitle(f"{label}; λ={lam}")
      save(fig,out,f"{prefix}_lambda_{lam.replace('.','')}",plotted,["coalition_results.csv"],metric,f"aggregate singleton; lambda={lam}","paired Student-t 95%",sum(x["stage_c"] for x in plotted))

def _groups(rows,keys):
    d={}
    for r in rows:d.setdefault(tuple(r[k] for k in keys),[]).append(r)
    return d

def generate(source=DEFAULT_SOURCE):
    source=Path(source); out=source/"analysis_figures"; tables=source/"analysis_tables"
    thresholds=read_csv(tables/"aggregate_effectiveness_thresholds.csv")
    heat_names=[]
    for lam,suffix in ((0,"0"),(.005,"0005"),(.02,"002")):
        rr=[r for r in thresholds if float(r["natural_fork_rate"])==lam]; xs=sorted({float(r["gamma"]) for r in rr});ys=sorted({float(r["target_hash_power"]) for r in rr})
        grid=np.full((len(ys),len(xs)),np.nan); labels=[]
        for r in rr:
            i=ys.index(float(r["target_hash_power"]));j=xs.index(float(r["gamma"]));v=r["supported_minimum_effective_coalition_power"]
            if v not in (None,""):grid[i,j]=float(v)
        fig,ax=plt.subplots(figsize=(6.4,4.6));im=ax.imshow(grid,origin="lower",aspect="auto",cmap="cividis")
        ax.set_xticks(range(len(xs)),xs);ax.set_yticks(range(len(ys)),ys);ax.set_xlabel("Gamma (neutral propagation)");ax.set_ylabel("Target hash power")
        for r in rr:
            i=ys.index(float(r["target_hash_power"]));j=xs.index(float(r["gamma"]));v=r["supported_minimum_effective_coalition_power"];status=r["threshold_boundary_classification"]
            text=(f"{float(v):.3f}" if v else {"SELFISH_ALREADY_UNPROFITABLE":"SAU","NOT_FOUND_WITHIN_GRID":"NF"}.get(status,"—"))
            if status=="AT_LOWER_GRID_EDGE":text="≤"+text
            if status=="AT_UPPER_GRID_EDGE":text="≥"+text
            if truth(r["terminal_boundary_overlap"]):text+="*"
            ax.text(j,i,text,ha="center",va="center",fontsize=7,color="white" if not np.isnan(grid[i,j]) and grid[i,j]>.12 else "black")
        fig.colorbar(im,ax=ax,label="Minimum supported active hash");ax.set_title(f"Supported deterrence threshold, λ={lam}\nSAU already unprofitable; NF not found; * terminal review")
        name=f"effectiveness_threshold_heatmap_lambda_{suffix}";heat_names.append(name)
        save(fig,out,name,rr,["threshold_audit.csv"],"minimum supported coalition power",f"lambda={lam}","classification from paired Student-t interval",sum(truth(x["stage_c_confirmation_recommended"]) for x in rr))
    fig,axs=plt.subplots(1,3,figsize=(11,3.6),sharey=True)
    for ax,(lam,name) in zip(axs,((0,heat_names[0]),(.005,heat_names[1]),(.02,heat_names[2]))):
        rr=[r for r in thresholds if float(r["natural_fork_rate"])==lam];xs=sorted({float(r["gamma"]) for r in rr});ys=sorted({float(r["target_hash_power"]) for r in rr});grid=np.full((len(ys),len(xs)),np.nan)
        for r in rr:
            if r["supported_minimum_effective_coalition_power"]:grid[ys.index(float(r["target_hash_power"])),xs.index(float(r["gamma"]))]=float(r["supported_minimum_effective_coalition_power"])
        ax.imshow(grid,origin="lower",aspect="auto",cmap="cividis");ax.set_xticks(range(len(xs)),xs);ax.set_yticks(range(len(ys)),ys);ax.set_title(f"λ={lam}");ax.set_xlabel("γ")
    axs[0].set_ylabel("Target hash power");save(fig,out,"effectiveness_threshold_heatmap_overview",thresholds,["threshold_audit.csv"],"minimum supported coalition power","all lambda","paired Student-t classification",sum(truth(x["stage_c_confirmation_recommended"]) for x in thresholds))
    _response(source,out,"deterrence",r"Deterrence $U^H-U^{S,C}$","deterrence_response")
    _response(source,out,"punishment_reduction",r"Punishment reduction $U^{S,0}-U^{S,C}$","punishment_reduction_response")

    tpr=read_csv(tables/"continuous_tpr_summary.csv"); reps=[]
    # Deterministic representative environments: cover all lambda and all three
    # categorical outcomes, then add low/middle/high alpha and gamma endpoints.
    envs=_groups([r for r in tpr if r["structure"]=="singleton"],("target_hash_power","gamma","natural_fork_rate"))
    chosen=[]
    for lam in (0,.005,.02):
        candidates=[(k,g) for k,g in envs.items() if float(k[2])==lam]
        for wanted in ("SELFISH_ALREADY_UNPROFITABLE","DETERRABLE","NOT_DETERRENT_AT_TPR_1"):
            match=next(((k,g) for k,g in candidates if wanted in {x["tpr_status"] for x in g}),None)
            if match and match[0] not in chosen:chosen.append(match[0])
    for target in ((.1,0),(.2,.5),(.35,1)):
        match=next((k for k in envs if float(k[0])==target[0] and float(k[1])==target[1]),None)
        if match and match not in chosen:chosen.append(match)
    for k in chosen:reps.extend(envs[k])
    fig,ax=plt.subplots(); numeric=[r for r in reps if r["tpr_status"]=="DETERRABLE"]
    for env,g in _groups(numeric,("target_hash_power","gamma","natural_fork_rate")).items():
        g=sorted(g,key=lambda r:float(r["active_coalition_hash_power"]));ax.plot([float(x["active_coalition_hash_power"]) for x in g],[float(x["continuous_tpr_minimum"]) for x in g],marker="o",ms=3,label=f"α={env[0]}, γ={env[1]}, λ={env[2]}")
    ax.set(xlabel="Active coalition hash power",ylabel="Minimum TPR",title="Representative continuous detector thresholds")
    if numeric:ax.legend(fontsize=7)
    save(fig,out,"continuous_tpr_representative",reps,["continuous_tpr_thresholds.csv"],"continuous TPR minimum","documented low/mid/high environments","paired tuple bootstrap",sum(truth(r["stage_c_confirmation_recommended"]) for r in reps))

    cred=read_csv(tables/"coalition_credibility_summary.csv"); by=read_csv(tables/"credibility_by_structure.csv")
    fig,ax=plt.subplots(); structures=sorted({r["structure"] for r in by});bottom=np.zeros(len(structures))
    for status in ("STRICTLY_DEVIATION_PROOF","WEAK_BREAK_EVEN_ONLY","NEITHER"):
        vals=[next((int(r["count"]) for r in by if r["structure"]==s and r["credibility_classification"]==status),0) for s in structures];ax.bar(structures,vals,bottom=bottom,label=status,color=COLORS[status]);bottom+=vals
    ax.set(ylabel="Coalition conditions",title="Weak versus strict credibility by structure");ax.tick_params(axis="x",rotation=25);ax.legend(fontsize=7)
    save(fig,out,"credibility_by_structure",by,["coalition_credibility_refined.csv"],"credibility counts","all corrected coalitions","member paired intervals")
    fig,ax=plt.subplots();
    powers=sorted({float(r["active_coalition_hash_power"]) for r in cred});structures=sorted({r["structure"] for r in cred})
    grid=np.zeros((len(structures),len(powers)))
    for i,s in enumerate(structures):
        for j,p in enumerate(powers):
            g=[r for r in cred if r["structure"]==s and float(r["active_coalition_hash_power"])==p]
            grid[i,j]=sum(r["credibility_classification"]!="NEITHER" for r in g)/len(g) if g else np.nan
    im=ax.imshow(grid,origin="lower",aspect="auto",cmap="cividis",vmin=0,vmax=1);ax.set_xticks(range(len(powers)),[f"{p:.3g}" for p in powers],rotation=45);ax.set_yticks(range(len(structures)),structures);ax.set(xlabel="Active coalition hash power",ylabel="Structure",title="Fraction weakly deviation-proof");fig.colorbar(im,ax=ax)
    save(fig,out,"credibility_by_power_structure",cred,["coalition_credibility_refined.csv"],"weak credibility fraction","active power by structure","member paired intervals",sum(truth(r["stage_c_confirmation_recommended"]) for r in cred))
    fig,ax=plt.subplots();
    for s,g in _groups(cred,("structure",)).items():ax.scatter([float(x["active_coalition_hash_power"]) for x in g],[float(x["credibility_slack"]) for x in g],s=5,alpha=.25,label=s[0])
    ax.axhline(0,color="black",lw=.7);ax.set(xlabel="Active coalition hash power",ylabel="Credibility slack",title="Credibility slack by structure");ax.legend(fontsize=6)
    save(fig,out,"credibility_slack_distribution",cred,["coalition_credibility_refined.csv"],"credibility slack","all corrected coalitions","member paired intervals",sum(truth(r["stage_c_confirmation_recommended"]) for r in cred))
    fig,ax=plt.subplots();
    for s,g in _groups(cred,("structure",)).items():ax.scatter([float(x["weakest_member_hash_power"]) for x in g],[float(x["credibility_slack"]) for x in g],s=5,alpha=.25,label=s[0])
    ax.axhline(0,color="black",lw=.7);ax.set(xlabel="Weakest-member hash power",ylabel="Credibility slack",title="Weakest member and credibility");ax.legend(fontsize=6)
    save(fig,out,"weakest_member_vs_credibility_slack",cred,["coalition_credibility_refined.csv"],"weakest-member power; slack","all corrected coalitions","member paired intervals",sum(truth(r["stage_c_confirmation_recommended"]) for r in cred))

    eq=read_csv(source/"equal_hash_comparisons_adjusted.csv");eqsum=read_csv(tables/"equal_hash_effect_summary.csv")
    for metric,name in (("deterrence","composition_deterrence_distribution"),("credibility_slack","composition_credibility_slack_distribution")):
        rr=[r for r in eq if r["metric"]==metric]; pairs=_groups(rr,("left_structure","right_structure"));fig,ax=plt.subplots(figsize=(8,4.8));labs=[];data=[]
        for k,g in sorted(pairs.items()):labs.append("→".join(k));data.append([float(x["difference"]) for x in g])
        ax.boxplot(data,labels=labs,showfliers=False);ax.axhline(0,color="black",lw=.7);ax.tick_params(axis="x",rotation=35);ax.set(ylabel="Matched difference",title=f"Equal-active-hash {metric.replace('_',' ')}")
        save(fig,out,name,rr,["equal_hash_comparisons_adjusted.csv"],metric,"corrected equal-active-hash comparisons","paired Student-t; BH statuses retained")
    fig,ax=plt.subplots();ax.bar([r["metric"] for r in eqsum],[float(r["p95_absolute_effect"]) for r in eqsum],color="#0072B2");ax.tick_params(axis="x",rotation=30);ax.set(ylabel="95th percentile |effect|",title="Composition effect magnitudes")
    save(fig,out,"composition_absolute_effect_sizes",eqsum,["equal_hash_comparisons_adjusted.csv"],"absolute effect quantiles","all metrics","descriptive")
    fig,ax=plt.subplots();x=np.arange(len(eqsum));ax.bar(x-.18,[int(r["bh_positive"]) for r in eqsum],.36,label="positive",color="#0072B2");ax.bar(x+.18,[int(r["bh_negative"]) for r in eqsum],.36,label="negative",color="#D55E00");ax.set_xticks(x,[r["metric"] for r in eqsum],rotation=30);ax.set(ylabel="BH-supported comparisons",title="Composition comparisons after BH adjustment");ax.legend()
    save(fig,out,"composition_bh_supported_counts",eqsum,["equal_hash_comparisons_adjusted.csv"],"BH-supported counts","all metrics","Benjamini-Hochberg")
    examples=sorted(eq,key=lambda r:(r["bh_adjusted_status"]=="INCONCLUSIVE",abs(float(r["difference"]))))[::max(1,len(eq)//20)][:12]
    fig,ax=plt.subplots();y=np.arange(len(examples));ax.errorbar([float(r["difference"]) for r in examples],y,xerr=[[float(r["difference"])-float(r["ci95_low"]) for r in examples],[float(r["ci95_high"])-float(r["difference"]) for r in examples]],fmt="o");ax.axvline(0,color="black",lw=.7);ax.set_yticks(y,[r["metric"] for r in examples]);ax.set(xlabel="Matched difference",title="Systematically sampled composition examples")
    save(fig,out,"composition_representative_examples",examples,["equal_hash_comparisons_adjusted.csv"],"matched differences","systematic ordered sample, not extrema","paired Student-t")

    fp=read_csv(tables/"false_positive_target_summary.csv");fpactor=read_csv(tables/"false_positive_actor_summary.csv")
    variants=[("false_positive_target_vs_power",fp,"active_coalition_hash_power","conditional_loss"),("false_positive_expected_target",fp,"active_coalition_hash_power","expected_cost"),("false_positive_member_by_structure",[r for r in fpactor if r["actor"]!="target"],"structure","conditional_loss"),("false_positive_vs_lambda",fp,"natural_fork_rate","conditional_loss")]
    for name,rr,xcol,ycol in variants:
        fig,ax=plt.subplots();cats=xcol=="structure"
        if cats:
            groups=_groups(rr,(xcol,));ax.boxplot([[float(x[ycol]) for x in g] for g in groups.values()],labels=[k[0] for k in groups],showfliers=False);ax.tick_params(axis="x",rotation=25)
        else:ax.scatter([float(r[xcol]) for r in rr],[float(r[ycol]) for r in rr],s=5,alpha=.2)
        ax.set(xlabel=xcol.replace("_"," "),ylabel=ycol.replace("_"," "),title=name.replace("_"," ").title())
        save(fig,out,name,rr,["false_positive_vectors.csv"],ycol,"corrected false-positive rows","paired Student-t")
    coal=read_csv(source/"coalition_results.csv");ci={(r["configuration_id"],r["coalition"]):obj(r["deterrence"])["mean"] for r in coal};trade=[]
    for r in fp:
        x=dict(r);x["deterrence"]=ci[(r["configuration_id"],r["coalition"])];trade.append(x)
    fig,ax=plt.subplots();ax.scatter([float(r["conditional_loss"]) for r in trade],[float(r["deterrence"]) for r in trade],s=5,alpha=.2);ax.set(xlabel="Conditional false-positive loss",ylabel="Deterrence",title="Deterrence–false-positive tradeoff (not welfare)")
    save(fig,out,"deterrence_false_positive_tradeoff",trade,["false_positive_vectors.csv","coalition_results.csv"],"deterrence; conditional FP loss","tradeoff only","paired Student-t")

    term=read_csv(tables/"terminal_boundary_review.csv");fig,ax=plt.subplots();ax.scatter([abs(float(r["deterrence_estimate"])) for r in term],[float(r["maximum_omitted_share_bound"]) for r in term],c=["#D55E00" if truth(r["supported_interval_overlap"]) else "#0072B2" for r in term]);lim=max(max(abs(float(r["deterrence_estimate"])) for r in term),max(float(r["maximum_omitted_share_bound"]) for r in term));ax.plot([0,lim],[0,lim],color="black",lw=.7);ax.set(xlabel="Absolute deterrence margin",ylabel="Conservative omitted-share bound",title="Internal terminal-boundary review")
    save(fig,out,"terminal_boundary_review",term,["terminal_boundary_diagnostics.csv","coalition_results.csv"],"absolute deterrence; terminal bound","14 point overlaps / 5 supported overlaps","paired Student-t plus conservative bound",sum(truth(r["stage_c_confirmation_recommended"]) for r in term))

    internal=read_csv(tables/"racefix_internal_comparison.csv");fig,ax=plt.subplots(figsize=(8,4));vals=[];labs=[]
    for r in internal:
        try:v=json.loads(r["value"]);v=v if isinstance(v,(int,float)) else sum(x for x in v.values() if isinstance(x,(int,float))) if isinstance(v,dict) else 0
        except Exception:v=0
        vals.append(v);labs.append(r["metric"])
    ax.bar(labs,vals,color="#777777");ax.tick_params(axis="x",rotation=35);ax.set(ylabel="Reported change count/value",title="INTERNAL MODEL-CORRECTION DIAGNOSTIC — NOT A SCIENTIFIC COMPARISON")
    save(fig,out,"racefix_internal_comparison",internal,["results/racefix_comparison/comparison_summary.json"],"old/corrected changes","internal diagnostic only","not paired; random streams realigned")
    return sorted(p.name for p in out.glob("*.png"))

if __name__=="__main__":
    p=argparse.ArgumentParser(description="Plot corrected Stage B tables without simulation");p.add_argument("--source",default=str(DEFAULT_SOURCE));a=p.parse_args();print(json.dumps(generate(a.source),indent=2))
