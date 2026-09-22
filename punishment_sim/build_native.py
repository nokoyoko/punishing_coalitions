"""Explicit local C++17 build, with atomic binary and compiler/source provenance."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import sysconfig
import tempfile

ROOT=Path(__file__).resolve().parents[1]
DESTINATION=ROOT/'build'/'persistent_v2_native'


def build():
    DESTINATION.mkdir(parents=True,exist_ok=True)
    output=DESTINATION/('_persistent_v2_native'+sysconfig.get_config_var('EXT_SUFFIX'))
    compiler=shlex.split(sysconfig.get_config_var('CXX') or 'c++')
    flags=['-std=c++17','-O3','-fno-fast-math','-ffp-contract=off','-fPIC','-shared']
    if sys.platform=='darwin':
        flags+=['-undefined','dynamic_lookup','-Wl,-install_name,@rpath/'+output.name]
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted((ROOT/'punishment_sim/native').iterdir()) if p.suffix in ('.cpp','.hpp')}
    command=compiler+flags+['-I'+sysconfig.get_paths()['include'],str(ROOT/'punishment_sim/native/persistent_v2.cpp'),'-o',str(output)]
    with tempfile.TemporaryDirectory(dir=DESTINATION,prefix='compile-') as temporary:
        candidate=Path(temporary)/output.name
        subprocess.run(command[:-1]+[str(candidate)],check=True)
        current={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted((ROOT/'punishment_sim/native').iterdir()) if p.suffix in ('.cpp','.hpp')}
        if current!=sources:raise RuntimeError('native sources changed during compilation')
        binary_hash=hashlib.sha256(candidate.read_bytes()).hexdigest()
        artifact=DESTINATION/'objects'/binary_hash/output.name
        artifact.parent.mkdir(parents=True,exist_ok=True)
        metadata={'command':command,'compiler':subprocess.check_output(compiler+['--version'],text=True),
            'python':sys.version,'extension_suffix':sysconfig.get_config_var('EXT_SUFFIX'),
            'compiled_sources':sources,'binary_sha256':binary_hash,
            'binary_file':str(artifact.relative_to(DESTINATION))}
        manifest=Path(temporary)/'build.json'
        manifest.write_text(json.dumps(metadata,indent=2)+'\n')
        if artifact.exists():
            if hashlib.sha256(artifact.read_bytes()).hexdigest()!=binary_hash:
                raise RuntimeError('existing immutable native artifact is corrupted')
        else:
            os.replace(candidate,artifact)
        os.replace(manifest,DESTINATION/'build.json')
    print(artifact)
    return artifact


if __name__=='__main__': build()
