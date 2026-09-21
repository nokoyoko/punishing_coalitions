"""Frozen pre-optimization oracle: no weaker trajectory or JSON equality checks."""
import copy
import math
import random
from itertools import product
import pytest
from analysis import _persistent_v2_compact_validation_reference as old
from punishment_sim import persistent_v2_checkpoint as new
from punishment_sim.coalition import Population
from punishment_sim.persistent_v2 import PersistentSimulation,Rule
from punishment_sim.persistent_v2_shards import VARIANTS


def outcome(fn,a,b):
    try: fn(a,b,'comparison');return True
    except (ValueError,TypeError,RecursionError): return False


def test_json_comparison_identical_including_numeric_types_order_and_invalid_values():
    values=[None,True,False,0,1,1.,0.,-0.,float('nan'),float('inf'),2**1001,'x','\U0001f600','\ud83d\ude00',
            [],(),[1],(1,),[True],[1.],{'x':1,'y':0.},{'y':0.,'x':1},{'x':float('nan')},
            {1:'a'},{'1':'a'},{1:'a','2':'b'},b'x',{'a':{1,2}}]
    for a,b in product(values,repeat=2): assert outcome(new.native_same,a,b)==outcome(old.same,a,b)
    rng=random.Random(991)
    def tree(depth=0):
        if depth>3 or rng.random()<.5:return rng.choice([None,True,False,rng.randrange(100),rng.random(),'abc'])
        return ([tree(depth+1) for _ in range(3)] if rng.random()<.5 else {str(i):tree(depth+1) for i in range(3)})
    for _ in range(500):
        a=tree();b=copy.deepcopy(a)
        assert outcome(new.native_same,a,b)==outcome(old.same,a,b)
        b=tree();assert outcome(new.native_same,a,b)==outcome(old.same,a,b)


@pytest.mark.parametrize('rule',VARIANTS)
@pytest.mark.parametrize('rate',[0,.02])
@pytest.mark.parametrize('production',[False,True])
def test_every_normal_variant_and_mode_matches_frozen_validator(rule,rate,production):
    p=Population(.2,(('c1',.05),('c2',.15)),.5,rate,120,701)
    for strategy,flagged,C in [('honest',False,()),('selfish',False,()),('honest',True,('c1','c2')),('selfish',True,('c1','c2'))]:
        raw=PersistentSimulation(p,strategy,flagged,C,rule,production=production,trace_mode=not production).run()
        old.validate_run(raw,p,rule,0,strategy,flagged,C)
        new.validate_run(raw,p,rule,0,strategy,flagged,C)


@pytest.mark.parametrize('rule',VARIANTS)
def test_all_trajectory_tampering_still_rejected(rule):
    p=Population(.2,(('c1',.05),('c2',.15)),.5,.02,500,701)
    C=('c1','c2');raw=PersistentSimulation(p,'selfish',True,C,rule,production=True).run()
    assert raw['selfish_reactions']
    variants=[]
    def altered():
        result=copy.deepcopy(raw);variants.append(result);return result
    r=altered();r['terminal']['canonical_blocks'][0]['owner_id']='c1' if r['terminal']['canonical_blocks'][0]['owner_id']!='c1' else 'c2'
    r=altered();r['selfish_reactions'].pop(0)
    r=altered();r['publication_batches'][0]['blocks'].append(r['publication_batches'][0]['blocks'][0])
    r=altered();r['terminal']['boundary']['max_exposed_canonical_blocks']+=1
    r=altered();r['actors']['target']['accepted']+=1
    # Preserve ancestry height and availability while changing the chosen parent.
    r=altered();blocks=r['terminal']['canonical_blocks']+r['terminal']['frontier_blocks'];by_id={b['id']:b for b in blocks}
    candidates=[(b,a) for b in blocks if b['parent_id'] is not None for a in blocks
                if a['id']!=b['parent_id'] and a['height']==by_id[b['parent_id']]['height']
                and a['id']<b['id'] and a['publication_sequence'] is not None]
    assert candidates
    block,parent=candidates[0];block['parent_id']=parent['id']
    # This release-label assertion previously existed only in replay_reactions.
    r=altered();ids={b['id'] for b in r['terminal']['canonical_blocks']+r['terminal']['frontier_blocks'] if b['initially_withheld']}
    batch=next(b for b in r['publication_batches'] if b['blocks'][0] in ids)
    batch['kind']='wrong_release'
    for b in r['terminal']['canonical_blocks']+r['terminal']['frontier_blocks']:
        if b['id'] in batch['blocks']:b['publication_kind']='wrong_release'
    for result in variants:
        for validate in (old.validate_run,new.validate_run):
            with pytest.raises(ValueError):validate(result,p,rule,0,'selfish',True,C)


def test_immutable_metadata_cache_preserves_list_population_compatibility():
    p=Population(.2,[('c1',.1),('c2',.1)],.5,.02,40,701)
    rule=Rule('petty');raw=PersistentSimulation(p,'selfish',True,('c1','c2'),rule,production=True).run()
    for validate in (old.validate_run,new.validate_run):validate(raw,p,rule,0,'selfish',True,('c1','c2'))
    assert new._miner_definitions(p)==p.miners
