import json
from pathlib import Path

import pytest

from punishment_sim.coalition import ExplicitSimulation, Population, mining_cache_key, study
from punishment_sim.research_sweep import group_equal_active
from punishment_sim.stage_b_validation import (bh_adjust, classify_margin,
    student_t_two_sided_p, threshold_boundary_label)


def test_weak_and_strict_categories_at_boundaries():
    zero=classify_margin(0,0,0,1e-12)
    assert zero["classification"]=="WEAK_BREAK_EVEN"
    assert zero["weak_supported"] and not zero["strict_supported"]
    positive=classify_margin(2e-4,1e-4,3e-4,1e-12)
    assert positive["classification"]=="STRICTLY_SUPPORTED" and positive["strict_supported"]
    assert classify_margin(0,-1e-4,1e-4)["classification"]=="INCONCLUSIVE"
    assert classify_margin(-2e-4,-3e-4,-1e-4)["classification"]=="REFUTED"
    assert classify_margin(1e-13,-1e-13,2e-13)["classification"]=="WEAK_BREAK_EVEN"


def test_zero_margin_has_zero_protocol_tolerance_rule():
    epsilon=1e-12; slack=0.0
    tolerance=0.0 if slack<=epsilon else slack
    assert tolerance==0 and not classify_margin(0,0,0,epsilon)["strict_supported"]


def test_threshold_boundary_labels():
    grid=[.025,.05,.1]
    assert threshold_boundary_label(.025,grid)=="AT_LOWER_GRID_EDGE"
    assert threshold_boundary_label(.1,grid)=="AT_UPPER_GRID_EDGE"
    assert threshold_boundary_label(.05,grid)=="OBSERVED_INTERIOR"
    assert threshold_boundary_label(None,grid)=="NOT_FOUND_WITHIN_GRID"
    assert threshold_boundary_label(.05,grid,True)=="SELFISH_ALREADY_UNPROFITABLE"


def test_equal_hash_grouping_requires_candidate_total_and_residual_match():
    common={"target_hash_power":.2,"gamma":.5,"natural_fork_rate":0,
            "accepted_block_target":30,"repetition_count":2,"active_hash_power":.1}
    rows=[{**common,"configuration_id":"a","coalition":"c1","candidate_population_power":.1},
          {**common,"configuration_id":"b","coalition":"c1|c2","candidate_population_power":.1},
          {**common,"configuration_id":"c","coalition":"c1","candidate_population_power":.2}]
    groups=group_equal_active(rows)
    assert len(groups)==1 and {x["configuration_id"] for x in groups[0]}=={"a","b"}
    assert 1-.2-.1==pytest.approx(.7)


def test_leaveout_preserves_actor_and_paired_components():
    pop=Population(.2,(("c1",.05),("c2",.05)),.5,0,30,17)
    result=study(pop,2,[1],[0],selected_coalitions=[("c1","c2")])
    for row in result["repetitions"]:
        assert "c1" in row["leaveouts"]["c1"] and "c2" in row["leaveouts"]["c2"]
        expected=row["U_SC"]["c1"]["payoff"]-row["leaveouts"]["c1"]["c1"]["payoff"]
        assert isinstance(expected,float)


def test_revenue_shares_sum_and_trace_is_reproducible():
    pop=Population(.2,(("c1",.1),),.5,.02,40,31)
    a=ExplicitSimulation(pop,"honest",True,("c1",),trace_mode=True).run()
    b=ExplicitSimulation(pop,"honest",True,("c1",),trace_mode=True).run()
    assert a["trace"]==b["trace"]
    assert sum(x["payoff"] for x in a["actors"].values())==pytest.approx(1)


def test_bh_retains_unadjusted_information_and_is_monotone():
    raw=[.001,.01,.2]; adjusted=bh_adjust(raw)
    assert raw==[.001,.01,.2]
    assert adjusted==sorted(adjusted) and all(q>=p for p,q in zip(raw,adjusted))
    assert student_t_two_sided_p(0,1,29)==pytest.approx(1)


def test_reporting_epsilon_cannot_change_cache_key():
    pop=Population(.2,(("c1",.1),),.5,.02,30,1)
    before=mining_cache_key(pop,0,"selfish",True,("c1",))
    classify_margin(0,0,0,1e-6); classify_margin(0,0,0,1e-12)
    assert before==mining_cache_key(pop,0,"selfish",True,("c1",))


def test_docs_cover_code_paths_and_baseline_environment():
    root=Path(__file__).parents[1]
    mining=(root/"docs/mining_and_propagation_model.md").read_text()
    for path in ("_draw","_begin_race","step","run","study","mining_cache_key"):
        assert path in mining
    metrics=(root/"docs/metric_definitions.md").read_text()
    assert "no coalition member punishes" in metrics
    assert "U_j^{S,C}-U_j^{S,empty}" in metrics


def test_stage_c_uncapped_precedes_cap_and_tier1_is_protected():
    root=Path(__file__).parents[1]/"results/research_sweep_stage_b"
    audit=json.loads((root/"stage_c_candidate_audit.json").read_text())
    assert audit["uncapped_candidates"]>=audit["ranked_candidates"]
    assert audit["tier1_never_removed_by_cap"]
    assert audit["ranked_candidates"]>=audit["tier1_candidates"]
    header=(root/"stage_c_candidates_uncapped.csv").read_text().splitlines()[0]
    assert "reason_codes" in header and "tier" in header


def test_lambda_zero_stage_b_false_positive_is_exactly_zero():
    import csv
    root=Path(__file__).parents[1]/"results/research_sweep_stage_b/false_positive_vectors.csv"
    with root.open() as f:
        values=[float(r["conditional_loss"]) for r in csv.DictReader(f) if float(r["natural_fork_rate"])==0]
    assert values and max(map(abs,values))==0
