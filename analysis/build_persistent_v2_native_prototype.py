"""Build the opt-in research prototype; no install or production configuration change."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import sysconfig

ROOT=Path(__file__).resolve().parents[1]
DESTINATION=ROOT/'build'/'persistent_v2_prototype'


def build():
    DESTINATION.mkdir(parents=True,exist_ok=True)
    output=DESTINATION/('_persistent_v2_prototype'+sysconfig.get_config_var('EXT_SUFFIX'))
    compiler=shlex.split(sysconfig.get_config_var('CXX') or 'c++')
    flags=['-std=c++17','-O3','-fno-fast-math','-ffp-contract=off','-fPIC','-shared']
    if sys.platform=='darwin': flags+=['-undefined','dynamic_lookup']
    command=compiler+flags+['-I'+sysconfig.get_paths()['include'],str(ROOT/'analysis/native/persistent_v2_prototype.cpp'),'-o',str(output)]
    subprocess.run(command,check=True)
    metadata={'command':command,'compiler':subprocess.check_output(compiler+['--version'],text=True),'python':sys.version}
    (DESTINATION/'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(output)
    return output


if __name__=='__main__': build()
