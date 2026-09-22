"""Opt-in H/S0/petty prototype. Not registered with production orchestration.

Native summaries are UNATTESTED until the unchanged Python validators run.
Exact Python-created MT states and Python-computed miner weights cross once.
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
BUILD=ROOT/'build'/'persistent_v2_prototype'
BACKEND='persistent-h-s0-petty-native-prototype-v1'
_module=None


def load_extension():
    global _module
    if _module is None:
        binary=BUILD/('_persistent_v2_prototype'+sysconfig.get_config_var('EXT_SUFFIX'))
        if not binary.exists():
            raise RuntimeError('Build explicitly: python -m analysis.build_persistent_v2_native_prototype')
        spec=importlib.util.spec_from_file_location('_persistent_v2_prototype',binary)
        _module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_module)
    return _module


def backend_identity():
    extension=load_extension()
    paths={'native_source':ROOT/'analysis/native/persistent_v2_prototype.cpp',
           'wrapper':Path(__file__),'binary':Path(extension.__file__),'build':BUILD/'build.json'}
    return {'backend':BACKEND,'sha256':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()}}


@dataclass
class PrototypeResult:
    native: dict
    compact_unattested: dict
    timings: dict


def run(population, strategy, flagged, coalition=(), rule=None, *, repetition=0,
        production=True, trace=False, actions=None, stop_after=None, max_events=None):
    extension=load_extension()
    cpu0,wall0=process_time(),perf_counter()
    rule=rule or Rule('petty')
    identity=condition_identity(population,repetition,strategy,flagged,coalition,rule)
    if identity['flagged'] and rule.punishment_rule!='petty':
        raise ValueError('prototype supports H/S0 baselines and petty only')
    if not 1<=population.target_accepted_blocks<=30000:
        raise ValueError('prototype supports horizons 1..30000 only')
    p=replace(population,seed=identity['actual_seed'])
    miners=p.miners; names=[m.id for m in miners]
    if not all(isinstance(name,str) and name.isascii() for name in names):
        raise ValueError('prototype requires ASCII miner IDs')
    if type(production) is not bool or type(trace) is not bool or (production and trace):
        raise ValueError('trace and production are mutually exclusive')
    if stop_after is not None and (type(stop_after) is not int or stop_after<0):
        raise ValueError('nonnegative prefix discovery limit required')
    limit=max_events if max_events is not None else max(1000,100*p.target_accepted_blocks)
    if type(limit) is not int or not 1<=limit<=3_000_000:
        raise ValueError('prototype event limit must be in 1..3000000')
    states=tuple(CommonRandom(p.seed,name).getstate() for name in ('discoveries','ties','natural'))
    if any(state[0]!=3 or state[2] is not None for state in states):
        raise ValueError('unsupported Python RNG state contract')
    metadata={'identity':identity,'condition_id':digest(identity),'network_version':identity['network_version'],
        'model_version':identity['model_version'],'population':asdict(p),'strategy':strategy,
        'label':'flagged' if identity['flagged'] else 'unflagged',
        'active_coalition':identity['active_coalition'],
        'punishment_rule':'petty' if identity['flagged'] else None,'counter_fork_k':None}
    commands=None
    if actions is not None:
        commands=[]
        for action in actions:
            if action[0]=='step': commands.append((0,-1 if action[1] is None else names.index(action[1])))
            elif action[0]=='discover':
                commands.append((1,names.index(action[1]),action[2] or 0,action[3],action[4]))
            elif action[0]=='publish': commands.append((2,list(action[1]),action[2]))
            else: raise ValueError('unknown prototype action')
    payload={'gamma':p.gamma,'lambda':p.natural_fork_rate,'horizon':p.target_accepted_blocks,
        'max_events':limit,'stop_after':stop_after if stop_after is not None else -1,
        'selfish':strategy=='selfish','enabled':identity['flagged'],'production':production,'trace':trace,
        'miners':[(m.id,m.role,m.hash_power,canonical_json(m.hash_power)) for m in miners],
        'active':[names.index(a) for a in identity['active_coalition']],
        'rng_states':tuple(state[1] for state in states),
        'metadata':{k:canonical_json(v) for k,v in metadata.items()},'actions':commands}
    prepared_cpu,prepared_wall=process_time(),perf_counter()
    raw_bytes,compact_bytes,simulation_wall,emission_wall=extension.run(payload)
    returned_cpu,returned_wall=process_time(),perf_counter()
    raw=json.loads(raw_bytes); compact=json.loads(compact_bytes)
    # JSON's list/tuple normalization is restored for the original Python API's
    # two metadata objects. The complete canonical JSON is already identical.
    raw['identity']=identity;raw['population']=metadata['population'];compact['identity']=identity
    end_cpu,end_wall=process_time(),perf_counter()
    return PrototypeResult(raw,compact,{'prepare_cpu_seconds':prepared_cpu-cpu0,
        'native_call_cpu_seconds':returned_cpu-prepared_cpu,'boundary_decode_cpu_seconds':end_cpu-returned_cpu,
        'total_cpu_seconds':end_cpu-cpu0,'total_wall_seconds':end_wall-wall0,
        'native_simulation_wall_seconds':simulation_wall,'native_emission_wall_seconds':emission_wall,
        'raw_json_bytes':len(raw_bytes),'compact_json_bytes':len(compact_bytes)})
