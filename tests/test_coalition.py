import json

import pytest

from punishment_sim.coalition import ExplicitSimulation, Population, paired_stats, population_from_dict, status, study, subsets


def pop(**kw):
    return Population(kw.get("target_hash_power",.25),
        kw.get("candidates",(("c1",.05),("c2",.075),("c3",.10))),
        kw.get("gamma",.5),kw.get("natural_fork_rate",0),kw.get("blocks",100),kw.get("seed",1))


def test_population_and_exact_actor_accounting():
    p=pop(); assert sum(m.hash_power for m in p.miners)==pytest.approx(1)
    r=ExplicitSimulation(p,"honest",False,()).run()
    assert set(r["actors"])=={"target","c1","c2","c3","honest_residual"}
    assert all(b["owner_id"] in r["actors"] for b in r["blocks"])
    assert sum(x["discovered"] for x in r["actors"].values())==r["events"]


def test_candidate_ids_and_invalid_power_rejected():
    with pytest.raises(ValueError): pop(candidates=(("c1",.1),("c1",.2)))
    with pytest.raises(ValueError): pop(target_hash_power=.4,candidates=(("c1",.6),))


def test_all_subsets_canonical():
    x=subsets(["c3","c1","c2"]); assert len(x)==8 and len(set(x))==8
    assert x[0]==() and x[-1]==("c1","c2","c3")


def test_active_members_punish_independently_without_reward_pooling():
    p=pop(candidates=(("c1",.1),("c2",.1)),blocks=2)
    r=ExplicitSimulation(p,"selfish",True,("c1",),["target","honest_residual","c1"]).run()
    assert r["member_opportunities"]=={"c1":1} and r["member_activations"]=={"c1":1}
    assert r["actors"]["c1"]["accepted"]==1 and r["actors"]["c2"]["accepted"]==0


def test_explicit_candidate_natural_forks_and_no_target_punishment():
    p=pop(candidates=(("c1",.1),("c2",.1)),natural_fork_rate=1,blocks=2)
    r=ExplicitSimulation(p,"selfish",True,("c1",),["c1","c2","c1"]).run()
    assert r["natural_pairs"]=={"c1--c2":1}; assert not r["member_activations"]
    r=ExplicitSimulation(p,"selfish",True,("c1",),["c1","honest_residual","c1"]).run()
    assert r["natural_pairs"]=={"c1--honest_residual":1}


def test_selfish_target_does_not_make_benign_target_fork():
    p=pop(candidates=(("c1",.1),),natural_fork_rate=1,blocks=2)
    sim=ExplicitSimulation(p,"selfish",True,("c1",),["c1","target"])
    sim.step(); sim.step(); assert not sim.race and len(sim.private)==1


def test_study_empty_and_singleton_identities():
    result=study(pop(candidates=(("c1",.15),),blocks=150),3,[.5,1],[0,.1])
    empty=next(x for x in result["summary"] if x["members"]==[])
    assert empty["target_punished"]==pytest.approx(empty["target_unpunished_selfish"])
    member=result["members"][0]
    assert member["baseline"]["mean"]==pytest.approx(member["deviation"]["mean"])
    assert result["meta"]["mining_simulations"]==12  # 4 environments x 3 repetitions
    assert result["meta"]["detector_evaluations"]==8


def test_paired_statistics_statuses():
    s=paired_stats([1,2,3,4]); assert s["n"]==4 and status(s)=="SUPPORTED"
    assert status(paired_stats([-4,-3,-2,-1]))=="REFUTED"


def test_paired_statistics_use_requested_student_t_critical_values():
    for n, critical in ((30, 2.045), (50, 2.010)):
        s=paired_stats(list(range(n)))
        assert s["ci95_high"]-s["mean"] == pytest.approx(critical*s["standard_error"])


def test_no_prior_means_no_unconditional_mixture():
    r=study(pop(candidates=(("c1",.1),),blocks=50),2,[.9],[.01])
    assert all("prior_weighted" not in x for x in r["detector"])


def test_false_positive_expected_cost_is_fpr_weighted():
    r=study(pop(candidates=(("c1",.1),),natural_fork_rate=1,blocks=80),2,[.9],[.25])
    row=next(x for x in r["detector"] if x["coalition"]=="c1")
    for actor,cost in row["false_positive_conditional_cost"].items():
        assert row["false_positive_expected_cost"][actor]==pytest.approx(.25*cost)


def test_leave_one_out_keeps_deviator_identity_hash_and_account():
    p=pop(blocks=2)
    full=ExplicitSimulation(p,"selfish",True,("c1","c3"),["target","honest_residual","c1"],True).run()
    leave=ExplicitSimulation(p,"selfish",True,("c3",),["target","honest_residual","c1"],True).run()
    assert set(full["actors"])==set(leave["actors"])
    assert full["actors"]["c1"]["hash_power"]==leave["actors"]["c1"]["hash_power"]==.05
    assert "c1" in full["member_activations"] and "c1" not in leave["member_activations"]
    assert "c3" in full["active_coalition"] and "c3" in leave["active_coalition"]
    assert full["actors"]["c1"]["accepted"]==leave["actors"]["c1"]["accepted"]==1
    assert full["trace"][-1]["branch_choice"]["punishing"] is True
    assert leave["trace"][-1]["branch_choice"]["punishing"] is False


@pytest.mark.parametrize("members",[4,5,6])
def test_full_coalition_credibility_supports_larger_cardinalities(members):
    candidates=tuple((f"c{i+1}",.01) for i in range(members))
    coalition=tuple(x[0] for x in candidates)
    result=study(pop(candidates=candidates,blocks=20),1,[1],[0],selected_coalitions=[coalition])
    assert len(result["summary"])==1
    assert result["summary"][0]["cardinality"]==members
    assert len(result["members"])==members
    assert result["meta"]["mining_simulations"]==4+members


def test_detector_grid_does_not_add_mining_runs(monkeypatch):
    import punishment_sim.coalition as coalition
    calls=0; original=coalition.ExplicitSimulation.run
    def counted(sim):
        nonlocal calls; calls+=1; return original(sim)
    monkeypatch.setattr(coalition.ExplicitSimulation,"run",counted)
    r=study(pop(candidates=(("c1",.1),),blocks=40),1,[.5,.7,.9,1],[0,.01,.1])
    assert calls==4 and r["meta"]["detector_evaluations"]==24


@pytest.mark.parametrize("mode,expected", [
    ("equal",[1/3,1/3,1/3]),
    ("moderately_unequal",[1/6,2/6,3/6]),
    ("one_large_many_small",[.6,.2,.2]),
])
def test_candidate_distribution_generators(mode,expected):
    p=population_from_dict({"target_hash_power":.2,
        "candidate_distribution":{"total_power":.3,"members":3,"mode":mode}})
    assert [h/.3 for _,h in p.candidates]==pytest.approx(expected)
