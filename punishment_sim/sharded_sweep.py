from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import json
import multiprocessing
import os
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from .coalition import MODEL_VERSION, Population, config_id, study
from .research_sweep import SweepTask, generate_tasks, run_sweep

CHECKPOINT_SCHEMA = "population-batch-v1"


def specification_hash(spec):
    payload=json.dumps(spec,sort_keys=True,separators=(",",":"))
    return hashlib.sha256((MODEL_VERSION+"\n"+payload).encode()).hexdigest()


def task_id(task):
    return config_id(asdict(task.population))


def shard_for(task_identifier,num_shards):
    if num_shards < 1: raise ValueError("num_shards must be positive")
    return int(task_identifier,16)%num_shards


def _task_record(task,num_shards):
    identifier=task_id(task)
    return {"task_id":identifier,"num_shards":num_shards,"shard_index":shard_for(identifier,num_shards),
            "family":task.family,"structure":task.structure,"candidate_total":task.candidate_total,
            "population":asdict(task.population),"coalitions":[list(x) for x in task.coalitions]}


def build_manifest(spec,output_dir,num_shards):
    if spec.get("expected_model_version",MODEL_VERSION)!=MODEL_VERSION:
        raise ValueError("configuration model version does not match simulator")
    tasks,requested,valid=generate_tasks(spec); out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    records=sorted((_task_record(t,num_shards) for t in tasks),key=lambda x:x["task_id"])
    manifest=out/"task_manifest.jsonl"; temp=manifest.with_name(f".{manifest.name}.{os.getpid()}.tmp")
    with temp.open("w") as f:
        for row in records:f.write(json.dumps(row,sort_keys=True)+"\n")
        f.flush();os.fsync(f.fileno())
    os.replace(temp,manifest)
    summary={"schema":"sharded-sweep-manifest-v1","model_version":MODEL_VERSION,
             "configuration_hash":specification_hash(spec),"num_shards":num_shards,
             "requested_population_configurations":requested,"valid_population_requests":valid,
             "unique_population_configurations":len(records),
             "tasks_by_shard":{str(i):sum(r["shard_index"]==i for r in records) for i in range(num_shards)}}
    _atomic_json(out/"manifest_audit.json",summary);return tasks,summary


def _population_from_dict(d):
    return Population(float(d["target_hash_power"]),tuple((str(i),float(h)) for i,h in d["candidates"]),
                      float(d["gamma"]),float(d["natural_fork_rate"]),
                      int(d["target_accepted_blocks"]),int(d["seed"]))


def _run_population(record,repetitions,tprs,fprs,prior):
    population=_population_from_dict(record["population"]);audit={"hits":0,"misses":0}
    result=study(population,repetitions,tprs,fprs,prior,
                 selected_coalitions=tuple(tuple(x) for x in record["coalitions"]),
                 simulation_cache={},cache_audit=audit)
    return audit,result


def _atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temp.open("w") as f:
        json.dump(data,f,separators=(",",":"));f.write("\n");f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def _validate_checkpoint_payload(saved,record,config_hash,repetitions,model_version):
    """Validate native batch identity, complete conditions, and payoff accounting."""
    from .checkpoint_compatibility import canonical
    if saved.get("checkpoint_schema")!=CHECKPOINT_SCHEMA:return False,"schema"
    if saved.get("model_version")!=model_version:return False,"model_version"
    if saved.get("configuration_hash")!=config_hash:return False,"configuration_hash"
    if saved.get("configuration_id")!=record["task_id"]:return False,"task_id"
    if saved.get("num_shards")!=record["num_shards"]:return False,"num_shards"
    if saved.get("shard_index")!=shard_for(record["task_id"],record["num_shards"]):return False,"shard_assignment"
    if canonical(saved.get("population"))!=canonical(record["population"]):return False,"population"
    if canonical(saved.get("coalitions"))!=canonical(record["coalitions"]):return False,"coalitions"
    if saved.get("repetitions")!=repetitions:return False,"repetitions"
    result=saved["result"]; population=_population_from_dict(record["population"])
    if json.loads(canonical(result["population"]))!=json.loads(canonical(asdict(population))):return False,"result_population"
    coalitions={"|".join(c):set(c) for c in record["coalitions"]}
    expected={(rep,c) for rep in range(repetitions) for c in coalitions}
    observed=[(r["repetition"],r["coalition"]) for r in result["repetitions"]]
    if len(observed)!=len(expected) or set(observed)!=expected:return False,"repetition_coverage"
    if sorted(r["coalition"] for r in result["summary"])!=sorted(coalitions):return False,"coalition_coverage"
    expected_members={(c,j) for c,ms in coalitions.items() for j in ms}
    actual_members=[(r["coalition"],r["member_id"]) for r in result["members"]]
    if len(actual_members)!=len(expected_members) or set(actual_members)!=expected_members:return False,"member_coverage"
    powers={m.id:m.hash_power for m in population.miners}
    def valid_vector(vector):
        if set(vector)!=set(powers):return False
        total=sum(v["accepted"] for v in vector.values())
        if total<population.target_accepted_blocks:return False
        for actor,v in vector.items():
            if v["hash_power"]!=powers[actor]:return False
            if type(v["accepted"]) is not int or v["accepted"]<0:return False
            if abs(v["payoff"]-v["accepted"]/total)>1e-12:return False
        return abs(sum(v["payoff"] for v in vector.values())-1)<1e-12
    for row in result["repetitions"]:
        members=coalitions[row["coalition"]]
        if set(row["coalition_members"])!=members:return False,"coalition_members"
        if set(row["leaveouts"])!=members or set(row["terminal_leaveouts"])!=members:return False,"leaveout_coverage"
        vectors=[row[k] for k in ("U_H","U_HF","U_S0","U_SC")]+list(row["leaveouts"].values())
        if not all(valid_vector(v) for v in vectors):return False,"actor_payoff_accounting"
    for collection in ("summary","members","detector","repetitions"):
        for row in result[collection]:
            if row["configuration_id"]!=config_id(asdict(population)):return False,"row_configuration_id"
            if row["natural_fork_rate"]!=population.natural_fork_rate or row["gamma"]!=population.gamma:return False,"row_environment"
            if row["repetition_count"]!=repetitions or row["accepted_block_target"]!=population.target_accepted_blocks:return False,"row_stopping_rule"
    conditions={("honest",False,()),("selfish",False,())};requests=2
    for c in record["coalitions"]:
        c=tuple(c);requests+=2+len(c)
        conditions.update((("honest",bool(c),c),("selfish",bool(c),c)))
        conditions.update(("selfish",bool(remaining),remaining) for j in c for remaining in [tuple(x for x in c if x!=j)])
    expected_misses=len(conditions)*repetitions; expected_hits=requests*repetitions-expected_misses
    if saved["cache_audit"].get("misses")!=expected_misses or saved["cache_audit"].get("hits")!=expected_hits:return False,"cache_accounting"
    if result["meta"]["mining_simulations"]!=expected_misses:return False,"result_cache_accounting"
    return True,"valid"


def validate_checkpoint(path,record,config_hash,repetitions):
    try:
        from .checkpoint_compatibility import validate_compatibility
        saved=json.loads(Path(path).read_text())
        valid,reason=_validate_checkpoint_payload(saved,record,config_hash,repetitions,MODEL_VERSION)
        if not valid:return valid,reason
        if saved.get("compatibility_provenance"):
            return validate_compatibility(saved,record,config_hash,repetitions)
        if saved.get("simulation_model_version",MODEL_VERSION)!=MODEL_VERSION:return False,"simulation_model_version"
        return True,"valid"
    except Exception as exc:
        return False,f"corrupt:{type(exc).__name__}"


def _set_worker_thread_limits():
    for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS"):
        os.environ[name]="1"
    os.environ.setdefault("MPLBACKEND","Agg")


def _status(out,data):_atomic_json(Path(out)/"run_status.json",data)


def select_execution_records(records,natural_fork_rates=None):
    """Filter execution only; never change the full manifest, IDs, or spec hash."""
    if natural_fork_rates is None:
        return records
    rates=frozenset(float(x) for x in natural_fork_rates)
    available={float(r["population"]["natural_fork_rate"]) for r in records}
    if not rates or not rates <= available:
        raise ValueError("execution natural-fork rates must be a nonempty subset of the full manifest")
    return [r for r in records if float(r["population"]["natural_fork_rate"]) in rates]


def run_shard(spec,output_dir,workers=28,num_shards=1,shard_index=None,progress_interval=5.0,
              natural_fork_rates=None):
    if workers < 1:raise ValueError("workers must be positive")
    if shard_index is not None and not 0<=shard_index<num_shards:raise ValueError("shard-index outside [0,num-shards)")
    _set_worker_thread_limits();out=Path(output_dir);checkpoint_dir=out/"checkpoints";checkpoint_dir.mkdir(parents=True,exist_ok=True)
    tasks,manifest=build_manifest(spec,out,num_shards);config_hash=manifest["configuration_hash"]
    records=select_execution_records([_task_record(t,num_shards) for t in tasks],natural_fork_rates)
    if shard_index is not None:records=[r for r in records if r["shard_index"]==shard_index]
    records.sort(key=lambda x:x["task_id"]);repetitions=int(spec["repetitions"])
    reusable=[];pending=[];invalid=[]
    for record in records:
        path=checkpoint_dir/f'{record["task_id"]}.json'
        valid,reason=validate_checkpoint(path,record,config_hash,repetitions) if path.exists() else (False,"missing")
        if valid:reusable.append(record)
        else:
            pending.append(record)
            if reason!="missing":invalid.append({"task_id":record["task_id"],"reason":reason})
    suffix=f"_shard_{shard_index}" if shard_index is not None else ""
    log_path=out/f"progress{suffix}.log";fail_path=out/f"failures{suffix}.jsonl";status_path=out/f"run_status{suffix}.json"
    started=time.monotonic();completed=0;completed_work=0;failed=0
    base={"model_version":MODEL_VERSION,"configuration_hash":config_hash,"num_shards":num_shards,
          "shard_index":shard_index,"workers":workers,"total_tasks":len(records),
          "manifest_total_tasks":len(tasks),"execution_natural_fork_rates":sorted(set(natural_fork_rates)) if natural_fork_rates is not None else None,
          "reused_checkpoints":len(reusable),"initial_invalid_checkpoints":len(invalid)}
    def update(force=False):
        elapsed=max(time.monotonic()-started,1e-9);done=len(reusable)+completed
        data={**base,"completed_tasks":done,"newly_completed_tasks":completed,"failed_tasks":failed,
              "remaining_tasks":len(records)-done,"percent_complete":100*done/len(records) if records else 100,
              "throughput_new_tasks_per_second":completed/elapsed,
              "cumulative_accepted_block_work":completed_work,
              "elapsed_seconds":elapsed,"updated_epoch":time.time()}
        _atomic_json(status_path,data)
        with log_path.open("a") as f:f.write(json.dumps(data,sort_keys=True)+"\n")
        return data
    update(True);last=time.monotonic()
    def save_success(record,audit,result):
        nonlocal completed,completed_work
        payload={"checkpoint_schema":CHECKPOINT_SCHEMA,"model_version":MODEL_VERSION,"simulation_model_version":MODEL_VERSION,
            "configuration_hash":config_hash,"configuration_id":record["task_id"],"num_shards":record["num_shards"],"shard_index":record["shard_index"],
            "population":record["population"],"coalitions":record["coalitions"],"repetitions":repetitions,
            "cache_audit":audit,"result":result}
        _atomic_json(checkpoint_dir/f'{record["task_id"]}.json',payload);completed+=1
        completed_work+=audit["misses"]*int(spec["accepted_blocks"])
    def save_failure(record,exc):
        nonlocal failed
        failed+=1;failure={"task_id":record["task_id"],"shard_index":record["shard_index"],
            "population":record["population"],"coalitions":record["coalitions"],
            "repetitions":list(range(repetitions)),"exception_type":type(exc).__name__,
            "exception":str(exc),"traceback":traceback.format_exc(),"time":time.time()}
        with fail_path.open("a") as f:f.write(json.dumps(failure,sort_keys=True)+"\n")
    if workers==1:
        for record in pending:
            try:save_success(record,*_run_population(record,repetitions,spec["tpr"],spec["fpr"],spec.get("selfish_prior")))
            except Exception as exc:save_failure(record,exc)
            if time.monotonic()-last>=progress_interval:update();last=time.monotonic()
    else:
      context=multiprocessing.get_context("spawn")
      with concurrent.futures.ProcessPoolExecutor(max_workers=workers,mp_context=context) as executor:
          iterator=iter(pending);active={}
          def submit_one():
              try:record=next(iterator)
              except StopIteration:return False
              future=executor.submit(_run_population,record,repetitions,spec["tpr"],spec["fpr"],spec.get("selfish_prior"))
              active[future]=record;return True
          for _ in range(min(len(pending),workers*2)):submit_one()
          while active:
              done,_=concurrent.futures.wait(active,return_when=concurrent.futures.FIRST_COMPLETED)
              for future in done:
                  record=active.pop(future)
                  try:save_success(record,*future.result())
                  except Exception as exc:save_failure(record,exc)
                  submit_one()
              if time.monotonic()-last>=progress_interval:update();last=time.monotonic()
    final=update(True);final["status"]="COMPLETE" if failed==0 else "INCOMPLETE_WITH_FAILURES";_atomic_json(status_path,final)
    return final


def merge_shards(spec,output_dir,num_shards):
    out=Path(output_dir);tasks,manifest=build_manifest(spec,out,num_shards);config_hash=manifest["configuration_hash"]
    repetitions=int(spec["repetitions"]);records=sorted((_task_record(t,num_shards) for t in tasks),key=lambda x:x["task_id"])
    seen=set();problems=[];by_shard={str(i):0 for i in range(num_shards)}
    provenance_counts={};simulation_counts={}
    for record in records:
        identifier=record["task_id"]
        if identifier in seen:problems.append({"task_id":identifier,"problem":"duplicate_expected_task_id"})
        seen.add(identifier);path=out/"checkpoints"/f"{identifier}.json"
        if not path.exists():problems.append({"task_id":identifier,"problem":"missing"});continue
        valid,reason=validate_checkpoint(path,record,config_hash,repetitions)
        if not valid:problems.append({"task_id":identifier,"problem":reason});continue
        saved=json.loads(path.read_text())
        if saved["shard_index"]!=record["shard_index"]:problems.append({"task_id":identifier,"problem":"shard_assignment"});continue
        by_shard[str(record["shard_index"])]+=1
        from .checkpoint_compatibility import checkpoint_provenance
        kind=checkpoint_provenance(saved)["execution_provenance"]
        provenance_counts[kind]=provenance_counts.get(kind,0)+1
        simulation_counts[kind]=simulation_counts.get(kind,0)+saved["cache_audit"]["misses"]
    expected_envs={(t.population.target_hash_power,t.population.gamma,t.population.natural_fork_rate) for t in tasks}
    audit={"status":"COMPLETE" if not problems else "INCOMPLETE","model_version":MODEL_VERSION,
           "configuration_hash":config_hash,"expected_task_count":len(records),
           "valid_checkpoint_count":len(records)-len(problems),"problem_count":len(problems),
           "expected_authorized_environment_count":len(expected_envs),"tasks_by_shard":by_shard,"problems":problems,
           "checkpoints_by_execution_provenance":provenance_counts,"represented_simulations_by_execution_provenance":simulation_counts,
           "mining_simulations_executed_by_merge":0}
    _atomic_json(out/"merge_audit.json",audit)
    with (out/"merge_audit.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["task_id","problem"]);writer.writeheader();writer.writerows(problems)
    if problems:raise RuntimeError(f"merge refused: {len(problems)} missing, corrupt, duplicate, or inconsistent tasks")
    result=run_sweep(spec,out,require_checkpoints=True)
    audit["merged_output_configuration_count"]=len(result["mining_configurations"])
    audit["analysis_ready"]=audit["merged_output_configuration_count"]==len(records)
    audit["status"]="COMPLETE" if audit["analysis_ready"] else "INCOMPLETE"
    _atomic_json(out/"merge_audit.json",audit)
    if not audit["analysis_ready"]:raise RuntimeError("merge output configuration count mismatch")
    return audit
