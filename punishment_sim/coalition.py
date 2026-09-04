from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
from statistics import mean, stdev
from typing import Iterable

from .model import Disposition, RaceOrigin

MODEL_VERSION = "race-owner-oceanic-residual-v3"
OCEANIC_RESIDUAL_ID = "honest_residual"

@dataclass(frozen=True)
class Miner:
    id: str
    role: str
    hash_power: float


@dataclass(frozen=True)
class Population:
    target_hash_power: float
    candidates: tuple[tuple[str, float], ...]
    gamma: float = .5
    natural_fork_rate: float = 0
    target_accepted_blocks: int = 2000
    seed: int = 1

    def __post_init__(self):
        ids = [x[0] for x in self.candidates]
        if len(ids) != len(set(ids)) or "target" in ids or "honest_residual" in ids:
            raise ValueError("candidate IDs must be unique and reserved IDs are forbidden")
        if not 0 < self.target_hash_power < .5 or any(h <= 0 for _, h in self.candidates):
            raise ValueError("invalid target or candidate hash power")
        if self.residual_hash_power < 0 or self.target_hash_power + sum(h for _, h in self.candidates) >= 1:
            raise ValueError("hash powers must leave a positive residual honest share")
        if not 0 <= self.gamma <= 1 or not 0 <= self.natural_fork_rate <= 1:
            raise ValueError("gamma and natural_fork_rate must be in [0,1]")

    @property
    def residual_hash_power(self):
        return 1-self.target_hash_power-sum(h for _, h in self.candidates)

    @property
    def miners(self):
        return ((Miner("target", "target", self.target_hash_power),) +
                tuple(Miner(i, "candidate", h) for i, h in self.candidates) +
                (Miner("honest_residual", "residual_honest", self.residual_hash_power),))


@dataclass
class EBlock:
    id: int; parent_id: int | None; height: int; owner_id: str
    discovery_sequence: int; initially_withheld: bool
    published: bool = False; selfish_release: bool = False
    disposition: str = "unresolved"


def subsets(ids: Iterable[str], max_exact: int = 12) -> list[tuple[str, ...]]:
    ids = tuple(sorted(ids))
    if len(ids) > max_exact:
        raise ValueError(f"exact enumeration limited to {max_exact} candidates")
    return [x for n in range(len(ids)+1) for x in itertools.combinations(ids, n)]


class ExplicitSimulation:
    def __init__(self, population: Population, strategy: str, flagged: bool,
                 active_coalition: Iterable[str], discoverers=None, trace_mode=False,
                 include_block_records=True):
        self.p = population; self.strategy = strategy; self.flagged = flagged
        self.active = frozenset(active_coalition)
        candidate_ids = {x[0] for x in population.candidates}
        if not self.active <= candidate_ids: raise ValueError("active coalition must be candidate IDs")
        self.miners = {m.id: m for m in population.miners}
        self.rng = self._rng("discoveries"); self.tie_rng = self._rng("ties")
        self.natural_rng = self._rng("natural"); self.forced = iter(discoverers) if discoverers else None
        self.blocks: dict[int,EBlock] = {}; self.next_id=1; self.events=0
        self.accepted_count=0
        self.tip=None; self.private=deque(); self.pending=None; self.race=None
        self.discovered=Counter(); self.race_origins=Counter(); self.natural_pairs=Counter()
        self.opportunities=Counter(); self.activations=Counter()
        self.trace=[] if trace_mode else None
        self.include_block_records = include_block_records

    def _rng(self, name):
        b=hashlib.sha256(f"explicit:{self.p.seed}:{name}".encode()).digest()
        return random.Random(int.from_bytes(b[:8],"big"))
    def _draw(self):
        if self.forced: return next(self.forced)
        x=self.rng.random(); acc=0
        for m in self.p.miners:
            acc += m.hash_power
            if x < acc: return m.id
        return "honest_residual"
    def _new(self, owner, parent, withheld=False):
        bid=self.next_id; self.next_id+=1
        height=self.blocks[parent].height+1 if parent else 1
        self.blocks[bid]=EBlock(bid,parent,height,owner,self.events,withheld,not withheld)
        self.discovered[owner]+=1; return bid
    def _accept(self, ids):
        for x in ids:
            if self.blocks[x].disposition!="accepted": self.accepted_count+=1
            self.blocks[x].disposition="accepted"; self.tip=x
    def _orphan(self, ids):
        for x in ids: self.blocks[x].disposition="orphaned"
    def _honest_publisher(self, actor): return not (actor=="target" and self.strategy=="selfish")
    def is_oceanic_residual(self, actor):
        return actor==OCEANIC_RESIDUAL_ID
    def is_persistent_explicit_actor(self, actor):
        return actor in self.miners and not self.is_oceanic_residual(actor)
    def _begin_race(self,a,b,origin):
        assert self.blocks[a].parent_id==self.blocks[b].parent_id
        oa,ob=self.blocks[a].owner_id,self.blocks[b].owner_id; assert oa!=ob
        target=a if oa=="target" else b if ob=="target" else None
        self.race={"a":a,"b":b,"target":target,"origin":origin}
        self.race_origins[origin.value]+=1
        if origin==RaceOrigin.NATURAL_PROPAGATION:
            self.natural_pairs["--".join(sorted((oa,ob)))]+=1
        if target:
            for j in self.active: self.opportunities[j]+=1
            if self.flagged:
                for j in self.active: self.activations[j]+=1
    def _state(self):
        return "race" if self.race else "propagation_pending" if self.pending else "lead_0" if not self.private else "lead_1" if len(self.private)==1 else "lead_2_plus"
    def _choose_race_branch(self, actor):
        """Choose a public-race branch using explicit identity vs oceanic mass."""
        a,b,target=self.race["a"],self.race["b"],self.race["target"]
        oa,ob=self.blocks[a].owner_id,self.blocks[b].owner_id
        if target:
            other=b if target==a else a; other_owner=self.blocks[other].owner_id
            if actor=="target": return target,"OWN_TARGET_BRANCH"
            # The residual label is aggregate oceanic mass, not the persistent
            # identity of the particular residual miner that found a sibling.
            if self.is_persistent_explicit_actor(actor) and actor==other_owner:
                return other,"OWN_EXPLICIT_COMPETING_BRANCH"
            if actor in self.active and self.flagged: return other,"PETTY_PUNISH_TARGET"
            if self.tie_rng.random()<self.p.gamma:
                return target,("OCEANIC_GAMMA_TARGET" if self.is_oceanic_residual(actor) else "NEUTRAL_EXPLICIT_GAMMA_TARGET")
            return other,("OCEANIC_GAMMA_COMPETING" if self.is_oceanic_residual(actor) else "NEUTRAL_EXPLICIT_GAMMA_COMPETING")
        if actor==oa:return a,"OWN_BRANCH_A"
        if actor==ob:return b,"OWN_BRANCH_B"
        if self.tie_rng.random()<.5:return a,"BENIGN_NEUTRAL_A"
        return b,"BENIGN_NEUTRAL_B"
    def step(self):
        pre=self._state(); self.events+=1; actor=self._draw(); branch_choice=None
        if self.race:
            a,b,target=self.race["a"],self.race["b"],self.race["target"]
            chosen,decision_reason=self._choose_race_branch(actor)
            losing=b if chosen==a else a; r=self._new(actor,chosen); self._accept([chosen,r]); self._orphan([losing]); self.race=None
            branch_choice={"chosen_owner":self.blocks[chosen].owner_id,"target_branch_present":target is not None,
                           "punishing":decision_reason=="PETTY_PUNISH_TARGET","reason":decision_reason}
        elif self.pending:
            pending=self.pending; po=self.blocks[pending].owner_id
            if self.strategy=="selfish" and actor=="target":
                self._accept([pending]); self.private.append(self._new(actor,pending,True))
            elif actor!=po and self._honest_publisher(actor):
                sib=self._new(actor,self.blocks[pending].parent_id); self._begin_race(pending,sib,RaceOrigin.NATURAL_PROPAGATION)
            else:
                child=self._new(actor,pending, actor=="target" and self.strategy=="selfish")
                if actor=="target" and self.strategy=="selfish": self._accept([pending]); self.private.append(child)
                else: self._accept([pending,child])
            self.pending=None
        elif self.strategy=="honest":
            b=self._new(actor,self.tip)
            if self.natural_rng.random()<self.p.natural_fork_rate: self.pending=b
            else: self._accept([b])
        elif actor=="target":
            self.private.append(self._new(actor,self.private[-1] if self.private else self.tip,True))
        else:
            b=self._new(actor,self.tip); lead=len(self.private)
            if lead==0:
                if self.natural_rng.random()<self.p.natural_fork_rate: self.pending=b
                else: self._accept([b])
            elif lead==1:
                t=self.private.popleft(); self.blocks[t].published=True; self.blocks[t].selfish_release=True
                self._begin_race(t,b,RaceOrigin.SELFISH_RELEASE)
            elif lead==2:
                branch=list(self.private); self.private.clear()
                for x in branch: self.blocks[x].published=True; self.blocks[x].selfish_release=True
                self._accept(branch); self._orphan([b])
            else:
                t=self.private.popleft(); self.blocks[t].published=True; self.blocks[t].selfish_release=True
                self._accept([t]); self._orphan([b])
        if self.trace is not None:
            self.trace.append({"event":self.events,"discoverer":actor,"pre_state":pre,"post_state":self._state(),
                "active_coalition":sorted(self.active),"target_label":"flagged" if self.flagged else "unflagged",
                "branch_choice":branch_choice,"rewards":{i:sum(b.disposition=="accepted" and b.owner_id==i for b in self.blocks.values()) for i in self.miners}})
    def run(self):
        while self.accepted_count < self.p.target_accepted_blocks: self.step()
        while self.race or self.pending: self.step()
        accepted=Counter(b.owner_id for b in self.blocks.values() if b.disposition=="accepted")
        orphaned=Counter(b.owner_id for b in self.blocks.values() if b.disposition=="orphaned")
        unresolved=Counter(b.owner_id for b in self.blocks.values() if b.disposition=="unresolved")
        total=sum(accepted.values()); actors={}
        for m in self.p.miners:
            share=accepted[m.id]/total
            actors[m.id]={"role":m.role,"hash_power":m.hash_power,"discovered":self.discovered[m.id],
                "accepted":accepted[m.id],"orphaned":orphaned[m.id],"unresolved":unresolved[m.id],
                "payoff":share,"normalized_revenue":share/m.hash_power}
        result={"strategy":self.strategy,"label":"flagged" if self.flagged else "unflagged",
            "active_coalition":sorted(self.active),"events":self.events,"accepted_blocks":total,
            "actors":actors,"race_origins":dict(self.race_origins),"natural_pairs":dict(self.natural_pairs),
            "member_opportunities":dict(self.opportunities),"member_activations":dict(self.activations)}
        terminal_private=len(self.private)
        result["terminal_private_lead"]=terminal_private
        result["terminal_uncredited_private_blocks"]=terminal_private
        result["terminal_omitted_selfish_share_bound"]=(terminal_private/total if self.strategy=="selfish" else 0.0)
        if self.include_block_records: result["blocks"]=[asdict(b) for b in self.blocks.values()]
        if self.trace is not None: result["trace"]=self.trace
        return result


def paired_stats(values, left=None, right=None):
    n=len(values); mu=mean(values); sd=stdev(values) if n>1 else 0.; se=sd/math.sqrt(n) if n else None
    critical={1:12.706,2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306,9:2.262,
              10:2.228,11:2.201,12:2.179,13:2.160,14:2.145,15:2.131,
              29:2.045,49:2.010}.get(n-1,1.96)
    lo=mu-critical*se; hi=mu+critical*se
    paired_var=sd*sd
    independent_var=(stdev(left)**2+stdev(right)**2) if left is not None and right is not None and n>1 else None
    reduction=(1-paired_var/independent_var) if independent_var else None
    return {"n":n,"mean":mu,"sample_sd":sd,"standard_error":se,"ci95_low":lo,"ci95_high":hi,
            "paired_variance":paired_var,"independent_variance_estimate":independent_var,
            "crn_variance_reduction":reduction,
            "crn_increased_variance":paired_var>independent_var if independent_var is not None else None}

def status(stat, strict=False):
    if stat["ci95_low"] > 0 if strict else stat["ci95_low"] >= 0: return "SUPPORTED"
    if stat["ci95_high"] < 0 if strict else stat["ci95_high"] < 0: return "REFUTED"
    return "INCONCLUSIVE"


def mining_cache_key(population, repetition, strategy, flagged, coalition):
    """Behavior-only key; detector-quality parameters are deliberately absent."""
    if not coalition:
        flagged = False
    return (MODEL_VERSION,population.target_hash_power, population.candidates, population.gamma,
            population.natural_fork_rate, population.target_accepted_blocks,
            population.seed + repetition, strategy, bool(flagged), tuple(sorted(coalition)))


def study(population: Population, repetitions: int, tprs=(.9,), fprs=(.01,), prior=None,
          selected_coalitions=None, simulation_cache=None, cache_audit=None):
    candidate_ids=tuple(i for i,_ in population.candidates)
    coalitions=(subsets(candidate_ids) if selected_coalitions is None else
                sorted({tuple(sorted(x)) for x in selected_coalitions},key=lambda x:(len(x),x)))
    if any(not set(C)<=set(candidate_ids) for C in coalitions): raise ValueError("selected coalition contains unknown miner")
    cache={} if simulation_cache is None else simulation_cache; repetition_rows=[]
    if cache_audit is None: cache_audit={}
    cache_audit.setdefault("hits",0); cache_audit.setdefault("misses",0)
    def get(rep,strategy,flagged,C):
        if not C: flagged=False  # empty coalition cannot act on the label
        key=mining_cache_key(population,rep,strategy,flagged,C)
        if key not in cache:
            cache_audit["misses"]+=1
            p=Population(population.target_hash_power,population.candidates,population.gamma,
                         population.natural_fork_rate,population.target_accepted_blocks,population.seed+rep)
            cache[key]=ExplicitSimulation(p,strategy,flagged,C,include_block_records=False).run()
        else:
            cache_audit["hits"]+=1
        return cache[key]
    for rep in range(repetitions):
        H=get(rep,"honest",False,()); S0=get(rep,"selfish",False,())
        for C in coalitions:
            HF=get(rep,"honest",True,C); SC=get(rep,"selfish",True,C)
            row={"repetition":rep,"coalition":"|".join(C),"coalition_members":list(C),
                 "U_H":H["actors"],"U_HF":HF["actors"],"U_S0":S0["actors"],"U_SC":SC["actors"],
                 "member_opportunities":SC["member_opportunities"],"member_activations":SC["member_activations"],
                 "selfish_natural_pairs":SC["natural_pairs"],"honest_natural_pairs":HF["natural_pairs"]}
            row["terminal"]={name:{"private_lead":env["terminal_private_lead"],
                "uncredited_private_blocks":env["terminal_uncredited_private_blocks"],
                "accepted_blocks":env["accepted_blocks"],"omitted_share_bound":env["terminal_omitted_selfish_share_bound"]}
                for name,env in (("U_H",H),("U_HF",HF),("U_S0",S0),("U_SC",SC))}
            leaveout_results={j:get(rep,"selfish",True,tuple(x for x in C if x!=j)) for j in C}
            row["leaveouts"]={j:x["actors"] for j,x in leaveout_results.items()}
            row["terminal_leaveouts"]={j:{"private_lead":x["terminal_private_lead"],
                "uncredited_private_blocks":x["terminal_uncredited_private_blocks"],
                "accepted_blocks":x["accepted_blocks"],"omitted_share_bound":x["terminal_omitted_selfish_share_bound"]}
                for j,x in leaveout_results.items()}
            repetition_rows.append(row)
    summaries=[]; members=[]; detector=[]
    byC={C:[r for r in repetition_rows if tuple(r["coalition_members"])==C] for C in coalitions}
    for C,rows in byC.items():
        h=[r["U_H"]["target"]["payoff"] for r in rows]; sc=[r["U_SC"]["target"]["payoff"] for r in rows]
        s0=[r["U_S0"]["target"]["payoff"] for r in rows]
        D=paired_stats([x-y for x,y in zip(h,sc)],h,sc)
        R=paired_stats([x-y for x,y in zip(s0,sc)],s0,sc)
        member_stats={}
        for j in C:
            ujc=[r["U_SC"][j]["payoff"] for r in rows]; uj0=[r["U_S0"][j]["payoff"] for r in rows]
            ujlo=[r["leaveouts"][j][j]["payoff"] for r in rows]
            B=paired_stats([x-y for x,y in zip(ujc,uj0)],ujc,uj0)
            Q=paired_stats([x-y for x,y in zip(ujc,ujlo)],ujc,ujlo)
            member_stats[j]=(B,Q)
            members.append({"coalition":"|".join(C),"member_id":j,
                "member_hash_power":dict(population.candidates)[j],"baseline":B,"baseline_status":status(B),
                "deviation":Q,"deviation_status":status(Q),
                "baseline_point_sign":"positive" if B["mean"]>0 else "negative" if B["mean"]<0 else "zero",
                "deviation_point_sign":"positive" if Q["mean"]>0 else "negative" if Q["mean"]<0 else "zero",
                "U_S0":mean(r["U_S0"][j]["payoff"] for r in rows),
                "U_SC":mean(r["U_SC"][j]["payoff"] for r in rows),
                "U_leaveout":mean(r["leaveouts"][j][j]["payoff"] for r in rows),
                "opportunities":sum(r["member_opportunities"].get(j,0) for r in rows),
                "activations":sum(r["member_activations"].get(j,0) for r in rows)})
        basecred=all(status(x[0])=="SUPPORTED" for x in member_stats.values())
        devcred=all(status(x[1])=="SUPPORTED" for x in member_stats.values())
        basepoint=all(x[0]["mean"]>=0 for x in member_stats.values())
        devpoint=all(x[1]["mean"]>=0 for x in member_stats.values())
        effective=status(D,True); active_power=sum(dict(population.candidates)[j] for j in C)
        weakest_margin=min((member_stats[j][1]["mean"] for j in C),default=None)
        weakest_members=[j for j in C if math.isclose(member_stats[j][1]["mean"],weakest_margin,abs_tol=1e-15)] if C else []
        weakest=weakest_members[0] if weakest_members else None
        summaries.append({"coalition":"|".join(C),"members":list(C),"cardinality":len(C),
            "active_hash_power":active_power,"target_honest":mean(r["U_H"]["target"]["payoff"] for r in rows),
            "target_unpunished_selfish":mean(r["U_S0"]["target"]["payoff"] for r in rows),
            "target_punished":mean(r["U_SC"]["target"]["payoff"] for r in rows),
            "deterrence":D,"punishment_reduction":R,"effectiveness_status":effective,
            "effectiveness_point":D["mean"]>0,"baseline_credible":basecred,
            "baseline_credible_point":basepoint,"deviation_proof":devcred,
            "deviation_proof_point":devpoint,
            "weakest_member":weakest,"weakest_members":weakest_members,
            "minimum_member_deviation_margin":member_stats[weakest][1]["mean"] if weakest else None,
            "winning":bool(C) and effective=="SUPPORTED" and devcred,
            "winning_point":bool(C) and D["mean"]>0 and devpoint})
        for tpr,fpr in itertools.product(tprs,fprs):
            selfish={a:mean((1-tpr)*r["U_S0"][a]["payoff"]+tpr*r["U_SC"][a]["payoff"] for r in rows) for a in rows[0]["U_H"]}
            honest={a:mean((1-fpr)*r["U_H"][a]["payoff"]+fpr*r["U_HF"][a]["payoff"] for r in rows) for a in rows[0]["U_H"]}
            detstat=paired_stats([r["U_H"]["target"]["payoff"]-
                ((1-tpr)*r["U_S0"]["target"]["payoff"]+tpr*r["U_SC"]["target"]["payoff"])
                for r in rows])
            fp_stats={a:paired_stats([r["U_H"][a]["payoff"]-r["U_HF"][a]["payoff"] for r in rows],
                                     [r["U_H"][a]["payoff"] for r in rows],
                                     [r["U_HF"][a]["payoff"] for r in rows]) for a in rows[0]["U_H"]}
            fp_cond={a:v["mean"] for a,v in fp_stats.items()}
            fp_expected={a:fpr*v for a,v in fp_cond.items()}
            dr={"coalition":"|".join(C),"members":list(C),"active_hash_power":active_power,
                "tpr":tpr,"fpr":fpr,"expected_selfish":selfish,"expected_honest":honest,
                "expected_target_deterrence":detstat,"expected_effectiveness_status":status(detstat,True),
                "false_positive_conditional_cost":fp_cond,
                "false_positive_conditional_stats":fp_stats,
                "false_positive_expected_cost":fp_expected}
            if prior is not None: dr["prior_weighted"]={a:prior*selfish[a]+(1-prior)*honest[a] for a in selfish}
            detector.append(dr)
    winning=[tuple(x["members"]) for x in summaries if x["winning"]]
    winning_point=[tuple(x["members"]) for x in summaries if x["winning_point"]]
    minimal=[C for C in winning if not any(set(D)<set(C) for D in winning)]
    minimal_point=[C for C in winning_point if not any(set(D)<set(C) for D in winning_point)]
    def threshold(predicate):
        q=[x for x in summaries if predicate(x) and x["members"]]
        if not q:return None
        m=min(x["active_hash_power"] for x in q); return {"hash_power":m,"coalitions":[x["members"] for x in q if x["active_hash_power"]==m]}
    expected_thresholds={}
    for tpr in tprs:
        candidates=[x for x in detector if x["tpr"]==tpr and x["members"] and
                    x["expected_effectiveness_status"]=="SUPPORTED"]
        if candidates:
            hp=min(x["active_hash_power"] for x in candidates)
            unique=sorted({tuple(x["members"]) for x in candidates if x["active_hash_power"]==hp})
            expected_thresholds[str(tpr)]={"hash_power":hp,"coalitions":[list(x) for x in unique]}
        else: expected_thresholds[str(tpr)]=None
    meta={"min_effective_point":threshold(lambda x:x["effectiveness_point"]),
          "min_effective":threshold(lambda x:x["effectiveness_status"]=="SUPPORTED"),
          "min_effective_baseline_credible_point":threshold(lambda x:x["effectiveness_point"] and x["baseline_credible_point"]),
          "min_effective_baseline_credible":threshold(lambda x:x["effectiveness_status"]=="SUPPORTED" and x["baseline_credible"]),
          "min_winning_point":threshold(lambda x:x["winning_point"]),
          "min_winning":threshold(lambda x:x["winning"]),
          "minimal_winning_coalitions_point":[list(x) for x in minimal_point],
          "minimal_winning_coalitions":[list(x) for x in minimal],
          "min_expected_effective_by_tpr":expected_thresholds,
          "mining_simulations":cache_audit["misses"],"detector_evaluations":len(detector),
          "cache_hits":cache_audit["hits"],"cache_misses":cache_audit["misses"]}
    identity={"configuration_id":config_id(asdict(population)),
        "target_hash_power":population.target_hash_power,
        "total_candidate_power":sum(h for _,h in population.candidates),
        "candidate_distribution":dict(population.candidates),
        "residual_honest_power":population.residual_hash_power,"gamma":population.gamma,
        "natural_fork_rate":population.natural_fork_rate,
        "repetition_count":repetitions,"accepted_block_target":population.target_accepted_blocks}
    for collection in (summaries,members,detector,repetition_rows):
        for row in collection:
            for k,v in reversed(tuple(identity.items())): row.setdefault(k,v)
    return {"population":asdict(population),"summary":summaries,"members":members,
            "detector":detector,"repetitions":repetition_rows,"meta":meta}


def population_from_dict(d):
    if "coalition_candidates" in d:
        candidates=tuple((x["id"],float(x["hash_power"])) for x in d["coalition_candidates"])
    else:
        spec=d["candidate_distribution"]; m=int(spec["members"]); total=float(spec["total_power"])
        mode=spec.get("mode","equal")
        if "weights" in spec: weights=[float(x) for x in spec["weights"]]
        elif mode=="equal": weights=[1]*m
        elif mode=="moderately_unequal": weights=list(range(1,m+1))
        elif mode=="one_large_many_small": weights=[.6]+[.4/(m-1)]*(m-1)
        else: raise ValueError("unknown candidate distribution mode")
        if len(weights)!=m or sum(weights)<=0: raise ValueError("invalid candidate weights")
        candidates=tuple((f"c{i+1}",total*w/sum(weights)) for i,w in enumerate(weights))
    return Population(float(d["target_hash_power"]),candidates,float(d.get("gamma",.5)),
        float(d.get("natural_fork_rate",0)),int(d.get("target_accepted_blocks",2000)),int(d.get("seed",1)))

def config_id(d): return hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()[:16]
