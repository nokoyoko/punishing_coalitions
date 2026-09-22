"""Backend-bound manifests, resumability, strict failures and scientific parity."""
import json
from pathlib import Path
import shutil
import sqlite3
from unittest.mock import Mock

import pytest

from punishment_sim import persistent_v2_native as native
from punishment_sim import persistent_v2_shards as shards
from punishment_sim.persistent_checkpoint import atomic_json, digest
from test_persistent_v2_compact import design
from test_persistent_v2_validation_policy import records


@pytest.fixture(scope='module', autouse=True)
def compiled():
    from punishment_sim.build_native import build
    build()
    native._module = None
    native.load_extension()


def test_native_and_python_plans_preserve_science_but_bind_execution(tmp_path):
    spec = design(repetitions=2, horizon=12)
    spec['validation_policy'] = {'mode': 'sampled'}
    py = shards.prepare_study(spec, tmp_path/'python')
    cpp = shards.prepare_study(spec, tmp_path/'native', backend='native')
    assert py['backend'] == 'python' and cpp['backend'] == 'native'
    assert cpp['study_id'] != py['study_id']
    assert cpp['design'] == py['design'] and cpp['scope'] == py['scope']
    assert cpp['plan_sha256'] == py['plan_sha256'] and cpp['validation'] == py['validation']
    assert cpp['runtime']['execution_backend'] == native.backend_identity()
    assert shards.load_manifest(tmp_path/'native') == cpp
    with pytest.raises(ValueError, match='different execution backend'):
        shards.prepare_study(spec, tmp_path/'native', backend='python')
    for directory in ('python', 'native'):
        shards.run_shard(tmp_path/directory, 0)
    left, right = records(tmp_path/'python'), records(tmp_path/'native')
    assert left and left.keys() == right.keys()
    for key in left:
        assert {k:v for k,v in left[key].items() if k!='producer'} == {k:v for k,v in right[key].items() if k!='producer'}
    from punishment_sim.persistent_v2_compact import rerun_condition
    for record in right.values():
        if record.get('schema') == 'persistent-scientific-condition-v2-compact-2':
            regenerated = rerun_condition(record, context=cpp['validation'], backend='native')
            assert digest(regenerated) == record['native_result_sha256']
            break
    else:
        pytest.fail('native integration fixture did not create a compact condition')
    # Restart is a cache read, not implicit fallback or re-mining.
    before = (tmp_path/'native'/'shard-00.sqlite3').read_bytes()
    shards.run_shard(tmp_path/'native', 0)
    assert (tmp_path/'native'/'shard-00.sqlite3').read_bytes() == before


@pytest.mark.parametrize('field', ['backend', 'binary', 'header'])
def test_manifest_detects_changed_backend_or_binary_even_with_recomputed_checksum(tmp_path, field):
    manifest = shards.prepare_study(design(horizon=8), tmp_path, backend='native')
    if field == 'backend':
        manifest['backend'] = 'python'
    else:
        name = 'binary' if field == 'binary' else 'header:lightweight.hpp'
        manifest['runtime']['execution_backend']['sha256'][name] = '0'*64
    manifest['study_id'] = digest({k:v for k,v in manifest.items() if k not in ('study_id','receipt_key_sha256')})
    atomic_json(tmp_path/'study.json', manifest)
    with pytest.raises(ValueError, match='backend|source|binary'):
        shards.load_manifest(tmp_path)


def test_native_validation_failure_is_signed_fatal_and_not_retried(tmp_path, monkeypatch):
    shards.prepare_study(design(horizon=8), tmp_path, backend='native')
    execute = Mock(side_effect=ValueError('native fixture validation failure'))
    monkeypatch.setattr(native, 'execute', execute)
    with pytest.raises(ValueError, match='native fixture validation failure'):
        shards.run_shard(tmp_path, 0)
    assert execute.call_count == 1
    with sqlite3.connect(tmp_path/'shard-00.sqlite3') as db:
        assert db.execute("SELECT COUNT(*) FROM records WHERE kind='validation_failure'").fetchone()[0] == 1
    with pytest.raises(ValueError, match='prior validation failure'):
        shards.run_shard(tmp_path, 0)
    assert execute.call_count == 1


def test_build_provenance_rejects_a_tampered_binary_without_loading_it(tmp_path, monkeypatch):
    shutil.copytree(native.BUILD, tmp_path/'bundle')
    monkeypatch.setattr(native, 'BUILD', tmp_path/'bundle')
    metadata = json.loads((native.BUILD/'build.json').read_text())
    binary = native.BUILD/metadata['binary_file']
    binary.write_bytes(binary.read_bytes()+b'fixture tampering')
    with pytest.raises(RuntimeError, match='provenance'):
        native.backend_identity()
