"""Exact native condition backend with independent ledger checks and DAG replay.

Python initializes the existing MT streams and selects replay under its unchanged
policy. Execution/backend provenance is separate from scientific condition IDs.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sysconfig
from time import process_time, perf_counter

from punishment_sim.persistent_checkpoint import canonical_json, digest
from punishment_sim.persistent_v2 import CommonRandom, Rule, condition_identity

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build'/'persistent_v2_native'
BACKEND='persistent-native-v2-1'
_module=None
_loaded_binary_sha256=None


def _bundle_identity():
    build=BUILD/'build.json'
    if not build.exists():
        raise RuntimeError('Build explicitly: python -m punishment_sim.build_native')
    metadata=json.loads(build.read_text())
    expected_file='objects/'+metadata.get('binary_sha256','')+'/_persistent_v2_native'+sysconfig.get_config_var('EXT_SUFFIX')
    if metadata.get('binary_file')!=expected_file:
        raise RuntimeError('invalid native binary build provenance; rebuild explicitly')
    binary=BUILD/expected_file
    if not binary.exists():
        raise RuntimeError('native binary missing; rebuild explicitly')
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted((ROOT/'punishment_sim/native').iterdir()) if p.suffix in ('.cpp','.hpp')}
    binary_hash=hashlib.sha256(binary.read_bytes()).hexdigest()
    if metadata.get('compiled_sources')!=sources or metadata.get('binary_sha256')!=binary_hash:
        raise RuntimeError('native source/binary does not match its build provenance; rebuild explicitly')
    if metadata.get('extension_suffix')!=sysconfig.get_config_var('EXT_SUFFIX'):
        raise RuntimeError('native Python ABI mismatch')
    hashes={'native_source':sources.pop('persistent_v2.cpp'),
            **{'header:'+name:value for name,value in sources.items()},
            'wrapper':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'binary':binary_hash,'build':hashlib.sha256(build.read_bytes()).hexdigest()}
    return binary,{'backend':BACKEND,'sha256':hashes,
        'lightweight_validator':'native-lightweight-ledger-v1','replay_validator':'native-independent-ledger-replay-v1'}


def load_extension():
    global _module, _loaded_binary_sha256
    if _module is None:
        binary,identity=_bundle_identity()
        spec=importlib.util.spec_from_file_location('_persistent_v2_native',binary)
        _module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_module)
        _loaded_binary_sha256=identity['sha256']['binary']
    return _module


def backend_identity():
    _,identity=_bundle_identity()
    load_extension()
    if identity['sha256']['binary']!=_loaded_binary_sha256:
        raise RuntimeError('native binary changed after loading; restart with a matching fresh manifest')
    return identity


@dataclass
class NativeResult:
    native: dict | None
    compact_unattested: dict
    timings: dict


def run(population, strategy, flagged, coalition=(), rule=None, *, repetition=0,
        production=True, trace=False, actions=None, stop_after=None, max_events=None,
        _checked=False, _selector=None, _capture_witness=True):
    extension=load_extension()
    cpu0,wall0=process_time(),perf_counter()
    rule=rule or Rule('petty')
    identity=condition_identity(population,repetition,strategy,flagged,coalition,rule)
    if not 1<=population.target_accepted_blocks<=30000:
        raise ValueError('native supports horizons 1..30000 only')
    p=replace(population,seed=identity['actual_seed'])
    miners=p.miners; names=[m.id for m in miners]
    if not all(isinstance(name,str) for name in names):
        raise ValueError('native miner IDs must be strings')
    if type(production) is not bool or type(trace) is not bool or (production and trace):
        raise ValueError('trace and production are mutually exclusive')
    if stop_after is not None and (type(stop_after) is not int or stop_after<0):
        raise ValueError('nonnegative prefix discovery limit required')
    limit=max_events if max_events is not None else max(1000,100*p.target_accepted_blocks)
    if type(limit) is not int or not 1<=limit<=3_000_000:
        raise ValueError('native event limit must be in 1..3000000')
    states=tuple(CommonRandom(p.seed,name).getstate() for name in ('discoveries','ties','natural'))
    if any(state[0]!=3 or state[2] is not None for state in states):
        raise ValueError('unsupported Python RNG state contract')
    metadata={'identity':identity,'condition_id':digest(identity),'network_version':identity['network_version'],
        'model_version':identity['model_version'],'population':asdict(p),'strategy':strategy,
        'label':'flagged' if identity['flagged'] else 'unflagged',
        'active_coalition':identity['active_coalition'],
        'punishment_rule':rule.punishment_rule if identity['flagged'] else None,
        'counter_fork_k':rule.counter_fork_k if identity['flagged'] else None}
    commands=None
    if actions is not None:
        commands=[]
        for action in actions:
            if action[0]=='step': commands.append((0,-1 if action[1] is None else names.index(action[1])))
            elif action[0]=='discover':
                commands.append((1,names.index(action[1]),action[2] or 0,action[3],action[4]))
            elif action[0]=='publish': commands.append((2,list(action[1]),action[2]))
            else: raise ValueError('unknown native action')
    payload={'rule':rule.punishment_rule if identity['flagged'] else 'none',
        'counter_fork_k':(rule.counter_fork_k or 0) if identity['flagged'] else 0,'gamma':p.gamma,'lambda':p.natural_fork_rate,'horizon':p.target_accepted_blocks,
        'max_events':limit,'stop_after':stop_after if stop_after is not None else -1,
        'selfish':strategy=='selfish','enabled':identity['flagged'],'production':production,'trace':trace,
        'miners':[(m.id,m.role,m.hash_power,canonical_json(m.hash_power)) for m in miners],
        'active':[names.index(a) for a in identity['active_coalition']],
        'rng_states':tuple(state[1] for state in states),
        'metadata':{k:canonical_json(v) for k,v in metadata.items()},'actions':commands}
    prepared_cpu,prepared_wall=process_time(),perf_counter()
    checked_detail={}
    if _checked:
        if not production or trace or actions is not None or stop_after is not None:
            raise ValueError('checked execution requires a complete production-mode condition')
        payload['replay_selector']=_selector
        payload['capture_witness']=_capture_witness
        raw_bytes,compact_bytes,risks,simulation_wall,emission_wall,light_wall,paths,simulation_cpu,emission_cpu,light_cpu,replay_cpu,replay_wall=extension.run_checked(payload)
        checked_detail={'native_lightweight_wall_seconds':light_wall,
                        'native_simulation_cpu_seconds':simulation_cpu,'native_emission_cpu_seconds':emission_cpu,
                        'native_lightweight_cpu_seconds':light_cpu,'risk_flags':risks,'path_descriptors':paths,
                        'witness_schema':'persistent-native-witness-dag-v1' if raw_bytes else None}
        if replay_cpu >= 0:
            checked_detail.update(replay_cpu_seconds=replay_cpu,replay_wall_seconds=replay_wall,
                                  replay_implementation='native-independent-ledger-replay-v1')
    else:
        raw_bytes,compact_bytes,simulation_wall,emission_wall=extension.run(payload)
    returned_cpu,returned_wall=process_time(),perf_counter()
    raw=json.loads(raw_bytes) if raw_bytes else None; compact=json.loads(compact_bytes)
    # JSON's list/tuple normalization is restored for the original Python API's
    # two metadata objects. The complete canonical JSON is already identical.
    if raw is not None:
        raw['identity']=identity;raw['population']=metadata['population']
    compact['identity']=identity
    end_cpu,end_wall=process_time(),perf_counter()
    return NativeResult(raw,compact,{'prepare_cpu_seconds':prepared_cpu-cpu0,
        'native_call_cpu_seconds':returned_cpu-prepared_cpu,'boundary_decode_cpu_seconds':end_cpu-returned_cpu,
        'total_cpu_seconds':end_cpu-cpu0,'total_wall_seconds':end_wall-wall0,
        'native_simulation_wall_seconds':simulation_wall,'native_emission_wall_seconds':emission_wall,
        'raw_json_bytes':len(raw_bytes),'compact_json_bytes':len(compact_bytes),**checked_detail})


def validate_lightweight(result, population, rule, repetition, strategy, flagged, coalition):
    """Native semantic checker for external fixtures; Python only encodes input."""
    identity=condition_identity(population,repetition,strategy,flagged,coalition,rule)
    p=replace(population,seed=identity['actual_seed'])
    metadata={'identity':identity,'condition_id':digest(identity),'network_version':identity['network_version'],
        'model_version':identity['model_version'],'population':asdict(p),'strategy':strategy,
        'label':'flagged' if identity['flagged'] else 'unflagged','active_coalition':identity['active_coalition'],
        'punishment_rule':rule.punishment_rule if identity['flagged'] else None,
        'counter_fork_k':rule.counter_fork_k if identity['flagged'] else None}
    reference={'horizon':p.target_accepted_blocks,'metadata':{k:canonical_json(v) for k,v in metadata.items()},
        'miners':[(m.id,m.role,m.hash_power,canonical_json(m.hash_power)) for m in p.miners]}
    return load_extension().validate_lightweight(canonical_json(result).encode(),reference)


def validate_replay(result, population, rule, repetition, strategy, flagged, coalition):
    """Native reference-ledger reconstruction; never invokes a mining method."""
    identity=condition_identity(population,repetition,strategy,flagged,coalition,rule)
    p=replace(population,seed=identity['actual_seed'])
    names=[m.id for m in p.miners]
    metadata={'identity':identity,'condition_id':digest(identity),'network_version':identity['network_version'],
        'model_version':identity['model_version'],'population':asdict(p),'strategy':strategy,
        'label':'flagged' if identity['flagged'] else 'unflagged','active_coalition':identity['active_coalition'],
        'punishment_rule':rule.punishment_rule if identity['flagged'] else None,
        'counter_fork_k':rule.counter_fork_k if identity['flagged'] else None}
    payload={'rule':rule.punishment_rule if identity['flagged'] else 'none',
        'counter_fork_k':(rule.counter_fork_k or 0) if identity['flagged'] else 0,
        'gamma':p.gamma,'lambda':p.natural_fork_rate,'horizon':p.target_accepted_blocks,
        'max_events':max(1000,100*p.target_accepted_blocks),'stop_after':-1,
        'selfish':strategy=='selfish','enabled':identity['flagged'],'production':True,'trace':False,
        'miners':[(m.id,m.role,m.hash_power,canonical_json(m.hash_power)) for m in p.miners],
        'active':[names.index(a) for a in identity['active_coalition']],
        'rng_states':tuple(CommonRandom(p.seed,name).getstate()[1] for name in ('discoveries','ties','natural')),
        'metadata':{k:canonical_json(v) for k,v in metadata.items()},'actions':None}
    load_extension().validate_replay(canonical_json(result).encode(),payload)


def execute(population, strategy, flagged, coalition, rule, *, repetition=0, producer, context):
    """Production pipeline with native ledger checks and selected native replay."""
    from .persistent_v2_validation import attestation, FULL
    from .persistent_v2_compact import validate_compact
    identity=condition_identity(population,repetition,strategy,flagged,coalition,rule)
    validation=None
    def select(risks):
        nonlocal validation
        validation=attestation(identity,context,risks)
        return validation['level']==FULL
    result=run(population,strategy,flagged,coalition,rule,repetition=repetition,
               _checked=True,_selector=select,_capture_witness=False)
    if validation is None or sorted(result.timings['risk_flags'])!=validation['risk_flags']:
        raise ValueError('missing or inconsistent native validation selection')
    if validation['level']==FULL:
        if result.timings.get('replay_implementation')!='native-independent-ledger-replay-v1':
            raise ValueError('selected native replay did not execute')
    elif 'replay_cpu_seconds' in result.timings:
        raise ValueError('unselected native replay unexpectedly executed')
    if result.native is not None:
        raise ValueError('production returned an unnecessary Python witness')
    record={**result.compact_unattested,'producer':producer,'validation':validation}
    cpu,wall=process_time(),perf_counter()
    validate_compact(record,population,rule,repetition,strategy,flagged,coalition,producer,context)
    result.timings.update(compact_validation_cpu_seconds=process_time()-cpu,
                          compact_validation_wall_seconds=perf_counter()-wall)
    return record,result.timings
