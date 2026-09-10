"""Planning-only checks; never execute the simulator or production infrastructure."""
import copy
import json
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pytest

from analysis.generate_eyal_sirer_domain import generate
from analysis.plan_composition_1pct import hundredths, refined_plan, feasible
from analysis.plan_oceanic_v4_rerun import analytical_spec
from punishment_sim.checkpoint_compatibility import check_spec_compatibility
from punishment_sim.coalition import MODEL_VERSION, config_id, ExplicitSimulation, mining_cache_key
from punishment_sim.research_sweep import generate_tasks, systematic_compositions, select_systematic_compositions, _thresholds
from punishment_sim.sharded_sweep import shard_for, specification_hash
from punishment_sim.stage_b_validation import threshold_boundary_label
from punishment_sim.theory import vanilla_selfish_mining_profitable

CONFIG=Path('configs/research_sweep_stage_b_oceanic_all_races_v4_expanded_composition_1pct.json')
COARSE=Path('configs/research_sweep_stage_b_oceanic_v3_expanded_composition_sampled.json')


@pytest.fixture(autouse=True)
def prohibit_mining(monkeypatch):
    def prohibited(*a,**k):pytest.fail('no simulations allowed in design tests')
    monkeypatch.setattr(ExplicitSimulation,'run',prohibited)
    monkeypatch.setattr(ExplicitSimulation,'step',prohibited)


@pytest.fixture(scope='module')
def design():return json.loads(CONFIG.read_text())


@pytest.fixture(scope='module')
def inventory(design):return refined_plan(design,json.loads(COARSE.read_text()))


@pytest.fixture(scope='module')
def tasks(design):return generate_tasks(design)[0]


def test_exact_decimal_grids_and_unchanged_dimensions(design):
    old=json.loads(COARSE.read_text());c=design['composition']
    assert c['target_hash']==hundredths(10,35)
    assert c['candidate_power']==hundredths(5,60)
    for values in (c['target_hash'],c['candidate_power']):
        assert len(set(values))==len(values)
        assert all(Decimal(str(v))*100==(Decimal(str(v))*100).to_integral_value() for v in values)
        assert all(Decimal(str(b))-Decimal(str(a))==Decimal('.01') for a,b in zip(values,values[1:]))
    assert '0.30000000000000004' not in CONFIG.read_text()
    for k in ('gamma','natural_fork_rate','systematic'):assert c[k]==old['composition'][k]
    assert design['repetitions']==20
    assert old['repetitions']==30
    for k in ('seed','accepted_blocks','bootstrap_samples','execution_workers','stage_c_max_candidates','minimum_residual_power','tpr','fpr','robustness_bins'):
        assert design[k]==old[k]
    assert design['expected_model_version']==MODEL_VERSION=='race-owner-oceanic-all-races-v4'
    assert 'authorized_environment_file' not in design
    assert 'authorized_environment_triplets' not in design


def test_refined_authorization_export_and_strict_boundaries(design,tmp_path):
    report=generate(CONFIG,tmp_path)
    assert report['target_gamma_pairs']==130
    assert report['profitable_target_gamma_pairs']==62
    assert report['authorized_punishment_environments']==186
    expected={0:hundredths(34,35),.25:hundredths(31,35),.5:hundredths(26,35),.75:hundredths(17,35),1:hundredths(10,35)}
    for gamma,alphas in expected.items():
        assert [a for a in design['composition']['target_hash'] if vanilla_selfish_mining_profitable(a,gamma)]==alphas
    assert not vanilla_selfish_mining_profitable(.30,.25)
    assert not vanilla_selfish_mining_profitable(.25,.5)
    assert not vanilla_selfish_mining_profitable(.33,0)
    assert vanilla_selfish_mining_profitable(.34,0)


def test_exact_scope_and_representation_counts(inventory,tasks):
    assert inventory['authorized_pair_count']==62 and inventory['authorized_environment_count']==186
    assert inventory['composition_cells']==280 and inventory['feasible_composition_cells']==279
    assert inventory['sampled_structures_across_total_cardinality_cells']==1345
    assert inventory['top_level_configurations']==len(tasks)==250170
    assert inventory['repetitions']==20
    assert inventory['mining_simulations']==39934200
    assert inventory['accepted_block_work_units']==1198026000000
    assert inventory['by_lambda']==[
        {'natural_fork_rate':r,'configurations':83390,'mining_simulations':13311400,
         'accepted_block_work_units':399342000000} for r in (0,.005,.02)]
    assert inventory['theoretical_reuse']['configurations']==3934
    assert inventory['theoretical_reuse']['source_repetitions']==30
    assert inventory['theoretical_reuse']['destination_repetitions']==20
    assert inventory['theoretical_reuse']['source_mining_simulations']==942060
    assert inventory['theoretical_reuse']['source_accepted_block_work_units']==28261800000
    assert inventory['theoretical_reuse']['mining_simulations']==628040
    assert inventory['theoretical_reuse']['accepted_block_work_units']==18841200000
    assert inventory['theoretical_reuse']['selected_repetition_indices']==list(range(20))
    assert inventory['theoretical_reuse']['selected_repetition_seeds']==list(range(51000,51020))
    assert inventory['current_importer_reuse']=={
        'supported':False,'rejection':'source and destination scientific configurations differ',
        'repetition_counts_match':False,'prefix_import_implemented':False,
        'configurations':0,'mining_simulations':0,'accepted_block_work_units':0}
    fresh=inventory['fresh_v4']
    assert fresh['configurations']==250170
    assert fresh['mining_simulations']==39934200
    assert fresh['accepted_block_work_units']==1198026000000
    assert fresh['zero_lambda_configurations']==83390
    assert fresh['zero_lambda_mining_simulations']==13311400
    assert fresh['zero_lambda_accepted_block_work_units']==399342000000
    conditional=inventory['fresh_v4_if_validated_prefix_reuse']
    assert conditional['configurations']==246236
    assert conditional['mining_simulations']==39306160
    assert conditional['accepted_block_work_units']==1179184800000
    assert conditional['new_zero_lambda_configurations']==79456
    assert conditional['new_zero_lambda_mining_simulations']==12683360
    assert conditional['new_zero_lambda_accepted_block_work_units']==380500800000
    for scope in (fresh,conditional):
        assert scope['positive_lambda_configurations']==166780
        assert scope['positive_lambda_mining_simulations']==26622800
        assert scope['positive_lambda_accepted_block_work_units']==798684000000
    assert Counter(t.population.natural_fork_rate for t in tasks)=={0:83390,.005:83390,.02:83390}
    assert sum((4+len(t.population.candidates))*20 for t in tasks)==inventory['mining_simulations']


def test_committed_scope_matches_planner(inventory):
    # Compare the JSON representation because cardinality keys serialize as strings.
    assert json.loads(Path('docs/oceanic_v4_1pct_scope.json').read_text())==json.loads(json.dumps(inventory))


def test_repetition_change_alone_invalidates_spec_compatibility(design):
    historical={**design,'repetitions':30,'expected_model_version':'race-owner-oceanic-residual-v3'}
    with pytest.raises(ValueError,match='scientific configurations differ'):
        check_spec_compatibility(historical,design)
    same_repetitions={**design,'repetitions':30}
    check_spec_compatibility(historical,same_repetitions)
    assert specification_hash(same_repetitions)!=specification_hash(design)


def test_residual_constraints_and_member_sums(design,inventory,tasks):
    assert {r['valid_candidate_total_count'] for r in inventory['environments']}=={56}
    assert feasible(design,.35,.60)
    for t in tasks:
        assert t.population.residual_hash_power>=.05-1e-12
        assert t.population.target_hash_power+sum(h for i,h in t.population.candidates)<1
        assert sum(Decimal(str(h)) for i,h in t.population.candidates)==Decimal(str(t.candidate_total))
    # Exercise existing feasibility filtering beyond a boundary without mining.
    check=copy.deepcopy(design);check['minimum_residual_power']=.06
    check['composition'].update(target_hash=[.35],candidate_power=[.59,.60],gamma=[1],natural_fork_rate=[0])
    selected=generate_tasks(check)[0]
    assert {t.candidate_total for t in selected}=={.59}


def test_hhi_representatives_cover_every_feasible_cell(inventory):
    counts=Counter()
    for c in inventory['composition_coverage']:
        counts[c['selected_count']]+=1
        if not c['feasible_member_count']:
            assert (c['candidate_total'],c['cardinality'])==(.05,6)
            continue
        assert c['selected_count']==min(5,c['exhaustive_compositions'])
        assert c['includes_least_concentrated'] and c['includes_most_concentrated']
        assert c['includes_one_percent_member']
        if c['distinct_available_hhi_levels']>2:assert c['interior_hhi_representatives']>0
        selected=[tuple(x) for x in c['selected_compositions']]
        assert all(tuple(sorted(x))==x for x in selected)
        assert len(set(selected))==len(selected)
        assert all(min(x)>=.01 for x in selected)
        assert any(max(x)-min(x)<=.01+1e-12 for x in selected)
        assert tuple([.01]*(c['cardinality']-1)+[float(Decimal(str(c['candidate_total']))-Decimal('.01')*(c['cardinality']-1))]) in selected
        # Recompute the actual deterministic selector, independently of the report.
        source=systematic_compositions(c['candidate_total'],c['cardinality'])
        assert tuple(selected)==select_systematic_compositions(source,{'mode':'hhi_quantiles','max_per_cell':5})
    assert counts=={0:1,1:5,2:5,3:6,4:3,5:260}


def test_old_overlap_ids_and_shards_are_stable(design,tasks):
    old=generate_tasks(analytical_spec(json.loads(COARSE.read_text())))[0]
    # Match complete raw scientific records, preserving gamma/lambda numeric types.
    old_ids={config_id(asdict(t.population)):t for t in old}
    matched={}
    ids=set()
    for t in tasks:
        p=asdict(t.population);cid=config_id(p)
        assert cid not in ids;ids.add(cid)
        if cid in old_ids:
            assert json.dumps(p,sort_keys=True)==json.dumps(asdict(old_ids[cid].population),sort_keys=True)
            assert t.coalitions==old_ids[cid].coalitions
            assert shard_for(cid,7)==shard_for(config_id(asdict(old_ids[cid].population)),7)
            matched[cid]=t
    assert set(matched)==set(old_ids) and len(matched)==11802
    assert sum(t.population.natural_fork_rate==0 for t in matched.values())==3934
    # First-20 seeds/CRN conditions match independently of total repetition count.
    # Cache keys here use the current model for both populations; they do not
    # relabel historical execution or authorize a cross-version import.
    for cid,t in matched.items():
        if t.population.natural_fork_rate!=0:continue
        C=tuple(i for i,h in t.population.candidates)
        conditions=[('honest',False,()),('selfish',False,()),('honest',True,C),('selfish',True,C)]
        conditions += [('selfish',True,tuple(i for i in C if i!=j)) for j in C]
        for strategy,flagged,coalition in conditions:
            old_keys=[mining_cache_key(old_ids[cid].population,rep,strategy,flagged,coalition) for rep in range(30)]
            new_keys=[mining_cache_key(t.population,rep,strategy,flagged,coalition) for rep in range(20)]
            assert old_keys[:20]==new_keys
            assert [key[6] for key in new_keys]==list(range(51000,51020))
    # A fresh task-generation call on a representative subset retains ordering/IDs.
    small=copy.deepcopy(design);small['composition'].update(target_hash=[.24],candidate_power=[.23,.24])
    identity=lambda: [config_id(asdict(t.population)) for t in generate_tasks(small)[0]]
    assert identity()==identity()


def test_refined_authorization_cannot_silently_use_coarse_admission(design):
    for name,value in [('authorized_environment_file','nonexistent.csv'),('authorized_environment_triplets',[])]:
        wrong={**design,name:value}
        with pytest.raises(ValueError,match='cannot be combined'):generate_tasks(wrong)
    with pytest.raises(ValueError,match='unknown authorization'):generate_tasks({**design,'authorization_rule':'unknown'})
    with pytest.raises(ValueError,match='scientific configurations differ'):
        check_spec_compatibility(json.loads(COARSE.read_text()),design)


def test_thresholds_and_stage_c_use_observed_one_percent_powers():
    common={'target_hash_power':.24,'gamma':1,'natural_fork_rate':.005,'structure':'test_observed_support',
        'coalition':'c1','baseline_credible_point':True,'baseline_credible':True,
        'deviation_proof_point':True,'deviation_proof':True}
    rows=[{**common,'configuration_id':str(p),'active_hash_power':p,'effectiveness_point':p>=.24,
        'effectiveness_status':'SUPPORTED' if p>=.24 else 'REFUTED'} for p in (.23,.24,.25)]
    threshold=next(r for r in _thresholds(rows,[]) if r['threshold_metric']=='effectiveness' and r['threshold_kind']=='supported')
    assert threshold['hash_power']==.24 and not threshold['threshold_at_grid_edge']
    assert threshold_boundary_label(.24,[.23,.24,.25])=='OBSERVED_INTERIOR'
