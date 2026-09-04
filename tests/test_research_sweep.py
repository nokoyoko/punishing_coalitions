import pytest
import json
from pathlib import Path

from punishment_sim.coalition import Population, mining_cache_key
from punishment_sim.research_sweep import (candidate_structure, dry_run, generate_tasks,
    group_equal_active, output_completeness_audit, run_sweep, tpr_threshold, _thresholds, STRUCTURES,
    composition_space_report, systematic_composition_count, systematic_compositions)


def tiny_spec():
    return {"stage":"test","seed":7,"repetitions":2,"accepted_blocks":30,"bootstrap_samples":50,
        "tpr":[.5,1],"fpr":[0,.1],"robustness_bins":[.0001,.0005],
        "aggregate":{"target_hash":[.2],"coalition_power":[.1],"gamma":[.5],"natural_fork_rate":[0]},
        "composition":{"target_hash":[.2],"candidate_power":[.1],"gamma":[.5],"natural_fork_rate":[0],
                       "structures":["singleton","two_equal"]}}


def test_candidate_structures_normalize_and_residual_is_correct():
    assert all(sum(weights)==pytest.approx(1) for weights in STRUCTURES.values())
    for name in ("singleton","two_equal","two_unequal","three_equal","three_moderate","three_concentrated"):
        candidates=candidate_structure(name,.3)
        assert sum(x[1] for x in candidates)==pytest.approx(.3)
        assert Population(.2,candidates).residual_hash_power==pytest.approx(.5)


def test_singleton_surface_generation_and_deduplication():
    tasks,requested,valid=generate_tasks(tiny_spec())
    assert requested==3 and valid==3 and len(tasks)==2
    singleton=next(t for t in tasks if len(t.population.candidates)==1)
    assert singleton.coalitions==(("c1",),)


def test_systematic_compositions_are_canonical_and_on_one_percent_grid():
    compositions=systematic_compositions(.30,3)
    assert len(compositions)==systematic_composition_count(.30,3)==75
    assert (.10,.10,.10) in compositions
    assert (.01,.14,.15) in compositions
    assert (.01,.01,.28) in compositions
    assert all(tuple(sorted(x))==x for x in compositions)
    assert len(compositions)==len(set(compositions))
    assert all(min(x)>=.01 and sum(x)==pytest.approx(.30,abs=1e-15) for x in compositions)


def test_systematic_sweep_uses_only_full_coalition_and_enforces_residual_floor():
    spec={"stage":"systematic-test","seed":7,"repetitions":1,"accepted_blocks":20,
          "minimum_residual_power":.05,"tpr":[1],"fpr":[0],"aggregate":{
              "target_hash":[.35],"coalition_power":[.60,.61],"gamma":[.5],"natural_fork_rate":[0]},
          "composition":{"target_hash":[.35],"candidate_power":[.05,.60,.61],"gamma":[.5],
              "natural_fork_rate":[0],"systematic":{"member_counts":[2,3,4,5,6],
              "power_step":.01,"minimum_member_power":.01}}}
    tasks,requested,valid=generate_tasks(spec)
    aggregate=[t for t in tasks if t.family=="aggregate"]
    composition=[t for t in tasks if t.family=="composition"]
    assert len(aggregate)==1 and aggregate[0].candidate_total==.60
    assert composition and {len(t.population.candidates) for t in composition}=={2,3,4,5,6}
    assert all(t.population.residual_hash_power>=.05-1e-12 for t in tasks)
    assert all(t.coalitions==(tuple(i for i,_ in t.population.candidates),) for t in composition)
    assert any(len(t.population.candidates)==6 for t in composition)
    report=composition_space_report(spec)
    assert report["grand_total"]==sum(systematic_composition_count(x,k)
        for x in (.05,.60) for k in range(2,7))


def test_expanded_composition_requires_regenerated_profitability_input(tmp_path):
    spec=tiny_spec(); spec["authorized_environment_file"]=str(tmp_path/"not-generated.csv")
    with pytest.raises(FileNotFoundError,match="must be regenerated first"):
        generate_tasks(spec)


def test_hhi_quantile_sampling_is_deterministic_and_spans_inequality():
    from punishment_sim.research_sweep import select_systematic_compositions
    all_compositions=systematic_compositions(.30,3)
    selected=select_systematic_compositions(all_compositions,{"mode":"hhi_quantiles","max_per_cell":5})
    assert len(selected)==5
    assert selected==select_systematic_compositions(all_compositions,{"mode":"hhi_quantiles","max_per_cell":5})
    hhi=lambda x:sum(v*v for v in x)
    assert hhi(selected[0])==min(map(hhi,all_compositions))
    assert hhi(selected[-1])==max(map(hhi,all_compositions))


def test_equal_active_hash_grouping_requires_matched_power():
    base={"target_hash_power":.2,"gamma":.5,"natural_fork_rate":0}
    rows=[{**base,"configuration_id":"a","coalition":"c3","active_hash_power":.1},
          {**base,"configuration_id":"b","coalition":"c1|c2","active_hash_power":.1},
          {**base,"configuration_id":"c","coalition":"c1","active_hash_power":.11}]
    groups=group_equal_active(rows)
    assert len(groups)==1 and {x["active_hash_power"] for x in groups[0]}=={.1}


def test_direct_zero_composition_difference_is_inconclusive():
    from punishment_sim.coalition import paired_stats, status
    assert status(paired_stats([0.0, 0.0, 0.0]), strict=True)=="INCONCLUSIVE"


def _payoff_rows(h,s0,sc,n=10):
    actor=lambda x:{"target":{"payoff":x}}
    return [{"U_H":actor(h),"U_S0":actor(s0),"U_SC":actor(sc)} for _ in range(n)]


def test_continuous_tpr_threshold_and_edge_cases_are_reproducible():
    rows=_payoff_rows(.25,.30,.20)
    a=tpr_threshold(rows,100,19); b=tpr_threshold(rows,100,19)
    assert a==b and a["status"]=="DETERRABLE" and a["tpr_min"]==pytest.approx(.5)
    expected=(1-a["tpr_min"])*.30+a["tpr_min"]*.20
    assert expected==pytest.approx(.25)
    assert tpr_threshold(_payoff_rows(.3,.3,.2))["status"]=="SELFISH_ALREADY_UNPROFITABLE"
    assert tpr_threshold(_payoff_rows(.25,.3,.26))["status"]=="NOT_DETERRENT_AT_TPR_1"


def test_cache_key_covers_behavior_and_ignores_detector_parameters():
    p=Population(.2,(("c1",.1),),.5,.02,100,4)
    key=mining_cache_key(p,0,"selfish",True,("c1",))
    assert key==mining_cache_key(p,0,"selfish",True,("c1",))
    assert key!=mining_cache_key(Population(.2,(("c1",.1),),.75,.02,100,4),0,"selfish",True,("c1",))
    # TPR and FPR cannot be supplied to, and therefore cannot affect, the mining key.
    assert len(key)==10 and key[0]=="race-owner-oceanic-residual-v3"


def test_thresholds_retain_tied_minimizers():
    common={"target_hash_power":.2,"gamma":.5,"natural_fork_rate":0,"structure":"two_equal",
            "coalition":"c1","active_hash_power":.05,"effectiveness_point":True,"effectiveness_status":"SUPPORTED",
            "baseline_credible_point":True,"baseline_credible":True,"deviation_proof_point":True,"deviation_proof":True}
    rows=[{**common,"configuration_id":"a"},{**common,"configuration_id":"b","coalition":"c2"}]
    result=_thresholds(rows,[])
    eff=next(x for x in result if x["threshold_metric"]=="effectiveness" and x["threshold_kind"]=="supported")
    assert len(eff["minimizers"])==2


def test_development_dry_run_matches_actual_cache_and_outputs(tmp_path):
    spec=tiny_spec(); estimate=dry_run(spec); result=run_sweep(spec,tmp_path)
    assert estimate["unique_mining_simulations"]==result["cache_audit"]["actual_unique_mining_simulations"]
    assert result["cache_audit"]["actual_cache_misses"]==estimate["unique_mining_simulations"]
    assert all(r["configuration_id"] for r in result["coalitions"])
    for row in result["coalitions"]:
        if row["members"]:
            margins=[m["deviation"]["mean"] for m in result["members"]
                     if m["configuration_id"]==row["configuration_id"] and m["coalition"]==row["coalition"]]
            assert row["credibility_slack"]==min(margins)
    for row in result["false_positive_vectors"]:
        assert row["expected_cost"]==pytest.approx(row["fpr"]*row["conditional_loss"])
    fp_keys={(r["configuration_id"],r["coalition"],r["actor"],r["fpr"])
             for r in result["false_positive_vectors"]}
    assert len(fp_keys)==len(result["false_positive_vectors"])
    comparisons=result["equal_hash_comparisons"]
    assert comparisons and {round(x["matched_active_hash_power"],8) for x in comparisons}<={.05,.1}
    assert any(x["matched_active_hash_power"]==pytest.approx(.1) for x in comparisons)
    assert {"deterrence","punishment_reduction","credibility_slack",
            "weakest_member_hash","coalition_cardinality"}<={x["metric"] for x in comparisons}
    assert all(x["left_cardinality"]!=x["right_cardinality"] or
               x["left_weakest_hash"]!=x["right_weakest_hash"] for x in comparisons)


def test_output_audit_detects_missing_required_fields():
    fixture={"thresholds":[{"hash_power":.1}],"repetitions":[{"repetition":0}]}
    audit=output_completeness_audit(fixture)
    first=audit[0]
    assert first["directly_answerable"]=="no"
    assert "threshold_configuration_id" in first["deficiency"]


def test_full_stage_b_grid_generation_and_fork_rates():
    spec=json.loads((Path(__file__).parents[1]/"configs/research_sweep_stage_b.json").read_text())
    tasks,requested,valid=generate_tasks(spec)
    assert requested==2142 and valid==2142 and len(tasks)==1980
    assert {t.population.natural_fork_rate for t in tasks}=={0,.005,.02}
    assert sum(len(t.coalitions) for t in tasks)==5544
    for task in tasks:
        assert all(task.coalitions)
        assert len(task.coalitions)==len(set(task.coalitions))
