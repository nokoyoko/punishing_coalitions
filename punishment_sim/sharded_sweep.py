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


def validate_checkpoint(path,record,config_hash,repetitions):
    try:
        saved=json.loads(Path(path).read_text())
        if saved.get("checkpoint_schema")!=CHECKPOINT_SCHEMA:return False,"schema"
        if saved.get("model_version")!=MODEL_VERSION:return False,"model_version"
        if saved.get("configuration_hash")!=config_hash:return False,"configuration_hash"
        if saved.get("configuration_id")!=record["task_id"]:return False,"task_id"
        if saved.get("num_shards")!=record["num_shards"]:return False,"num_shards"
        result=saved["result"]
        if len(result.get("repetitions",[]))!=repetitions*len(record["coalitions"]):return False,"repetition_coverage"
        if {r["repetition"] for r in result["repetitions"]}!=set(range(repetitions)):return False,"repetition_ids"
        if len(result.get("summary",[]))!=len(record["coalitions"]):return False,"coalition_coverage"
        return True,"valid"
    except Exception as exc:return False,f"corrupt:{type(exc).__name__}"


def _set_worker_thread_limits():
    for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS"):
        os.environ[name]="1"
    os.environ.setdefault("MPLBACKEND","Agg")


def _status(out,data):_atomic_json(Path(out)/"run_status.json",data)


def run_shard(spec,output_dir,workers=28,num_shards=1,shard_index=None,progress_interval=5.0):
    if workers < 1:raise ValueError("workers must be positive")
    if shard_index is not None and not 0<=shard_index<num_shards:raise ValueError("shard-index outside [0,num-shards)")
    _set_worker_thread_limits();out=Path(output_dir);checkpoint_dir=out/"checkpoints";checkpoint_dir.mkdir(parents=True,exist_ok=True)
    tasks,manifest=build_manifest(spec,out,num_shards);config_hash=manifest["configuration_hash"]
    records=[_task_record(t,num_shards) for t in tasks]
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
        payload={"checkpoint_schema":CHECKPOINT_SCHEMA,"model_version":MODEL_VERSION,
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
    expected_envs={(t.population.target_hash_power,t.population.gamma,t.population.natural_fork_rate) for t in tasks}
    audit={"status":"COMPLETE" if not problems else "INCOMPLETE","model_version":MODEL_VERSION,
           "configuration_hash":config_hash,"expected_task_count":len(records),
           "valid_checkpoint_count":len(records)-len(problems),"problem_count":len(problems),
           "expected_authorized_environment_count":len(expected_envs),"tasks_by_shard":by_shard,"problems":problems}
    _atomic_json(out/"merge_audit.json",audit)
    with (out/"merge_audit.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["task_id","problem"]);writer.writeheader();writer.writerows(problems)
    if problems:raise RuntimeError(f"merge refused: {len(problems)} missing, corrupt, duplicate, or inconsistent tasks")
    result=run_sweep(spec,out)
    audit["merged_output_configuration_count"]=len(result["mining_configurations"])
    audit["analysis_ready"]=audit["merged_output_configuration_count"]==len(records)
    audit["status"]="COMPLETE" if audit["analysis_ready"] else "INCOMPLETE"
    _atomic_json(out/"merge_audit.json",audit)
    if not audit["analysis_ready"]:raise RuntimeError("merge output configuration count mismatch")
    return audit
