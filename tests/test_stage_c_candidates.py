import copy
import csv

import pytest

from punishment_sim.research_sweep import (
    _write_csv,
    output_completeness_audit,
    select_stage_c_candidates,
)


def candidate_inputs():
    base={"coalition":"c1|c2","members":["c1","c2"],
          "target_hash_power":.3,"gamma":.5,"natural_fork_rate":.005,
          "structure":"two_equal","candidate_population_power":.2,
          "active_hash_power":.2,"effectiveness_status":"SUPPORTED",
          "winning_point":False,"baseline_credible":True,"deviation_proof":True}
    rows=[
        {**base,"configuration_id":"detector"},
        {**base,"configuration_id":"resolved"},
        {**base,"configuration_id":"credibility","winning_point":True,
         "baseline_credible":False},
        {**base,"configuration_id":"effectiveness","effectiveness_status":"INCONCLUSIVE"},
        {**base,"configuration_id":"all_reasons","effectiveness_status":"INCONCLUSIVE",
         "winning_point":True,"deviation_proof":False},
    ]
    tpr={
        (r["configuration_id"],r["coalition"]):{
            "status":"DETERRABLE" if r["configuration_id"] in {"detector","all_reasons"} else "NOT_DETERRENT_AT_TPR_1",
            "bootstrap_ci_low":.65,"bootstrap_ci_high":.75}
        for r in rows
    }
    return rows,tpr


def test_zero_stage_c_limit_retains_all_eligible_candidates_in_existing_priority_order(tmp_path):
    rows,tpr=candidate_inputs()
    before=copy.deepcopy((rows,tpr))
    selected=select_stage_c_candidates(rows,tpr,{"tpr":[.5,.7,.9,1],"stage_c_max_candidates":0})
    assert [r["configuration_id"] for r in selected]==[
        "all_reasons","effectiveness","credibility","detector"]
    assert selected[0]["selection_reason"]==(
        "effectiveness_ci_crosses_zero|winning_point_not_statistically_supported|"
        "tpr_interval_crosses_reporting_threshold")
    assert (rows,tpr)==before
    assert selected==select_stage_c_candidates(list(reversed(rows)),tpr,
        {"tpr":[.5,.7,.9,1],"stage_c_max_candidates":0})

    # The formerly blank CSV and deficient audit can be regenerated from
    # completed analysis alone; no mining or Stage C execution is necessary.
    output=tmp_path/"stage_c_candidates.csv"
    _write_csv(output,selected)
    with output.open(newline="") as stream:
        csv_rows=list(csv.DictReader(stream))
    assert len(csv_rows)==4 and all(r["selection_reason"] for r in csv_rows)
    audit=output_completeness_audit({"stage_c_candidates":selected,
                                     "repetitions":[{"repetition":0}]})
    stage_c=next(r for r in audit if r["required_output"]=="stage_c_candidates")
    assert stage_c["directly_answerable"]=="yes" and not stage_c["deficiency"]


def test_positive_stage_c_limit_preserves_priority_prefix():
    rows,tpr=candidate_inputs()
    unlimited=select_stage_c_candidates(rows,tpr,{"tpr":[.7],"stage_c_max_candidates":0})
    assert select_stage_c_candidates(rows,tpr,{"tpr":[.7],"stage_c_max_candidates":2})==unlimited[:2]


def test_omitted_stage_c_limit_preserves_default_250():
    rows,_=candidate_inputs()
    rows=[{**rows[-1],"configuration_id":f"candidate_{i:03d}"} for i in range(252)]
    tpr={(r["configuration_id"],r["coalition"]):{
        "status":"NOT_DETERRENT_AT_TPR_1","bootstrap_ci_low":None,"bootstrap_ci_high":None}
        for r in rows}
    assert len(select_stage_c_candidates(rows,tpr,{"tpr":[.7]}))==250
    assert len(select_stage_c_candidates(rows,tpr,{"tpr":[.7],"stage_c_max_candidates":0}))==252


def test_negative_stage_c_limit_is_rejected():
    with pytest.raises(ValueError,match="nonnegative"):
        select_stage_c_candidates([],{}, {"stage_c_max_candidates":-1})


def test_uncapped_stage_c_does_not_invent_candidates_for_resolved_cases():
    rows,tpr=candidate_inputs()
    resolved=[r for r in rows if r["configuration_id"]=="resolved"]
    assert select_stage_c_candidates(resolved,tpr,{"tpr":[.7],"stage_c_max_candidates":0})==[]
