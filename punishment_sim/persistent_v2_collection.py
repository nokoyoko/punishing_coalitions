"""Explicit cardinality-scoped, authenticated cross-study analysis; never mines.

Collections reference immutable source studies, keeping each HMAC receipt in its
original study/shard domain. Extensions are selected explicitly, never discovered.
The default analysis is always core 2–4, including for an extended collection.
"""
import argparse
from collections import Counter
from contextlib import contextmanager, ExitStack, closing
import csv
import hashlib
from itertools import groupby
import json
from pathlib import Path
import sqlite3
import tempfile

from .coalition import Population
from .persistent_checkpoint import atomic_json, canonical_json, digest
from .persistent_sweep import analysis_group_key
from .persistent_v2 import Rule
from .persistent_v2_checkpoint import require, same
from .persistent_v2_outputs import paired_comparisons
from .persistent_v2_shards import load_manifest, merge_shards, shard_lock, ShardStore, task_analysis
from .persistent_v2_sweep import grouped_thresholds
from .research_sweep import SweepTask, _flat

LAYOUT = 'persistent-v2-cardinality-collection-1'
ROLE_MEMBERS = {'core': [2, 3, 4], 'extension_5': [5], 'extension_6': [6]}
SCOPES = {'core': ('core',), 'extended_2to5': ('core', 'extension_5'),
          'extended_2to6': ('core', 'extension_5', 'extension_6'),
          'extension_5': ('extension_5',), 'extension_6': ('extension_6',)}
OUTPUTS = ('summary', 'members', 'detector', 'tpr_thresholds', 'false_positive_costs',
           'weakest_members', 'minimal_winning_coalitions', 'minimum_tested_thresholds',
           'scope_minimum_tested_thresholds', 'stage_c_candidates', 'boundary_diagnostics',
           'equal_power_comparisons', 'six_variant_comparisons')


def analysis_metadata(scope):
    require(scope in SCOPES, 'unknown analysis scope')
    return {'analysis_scope': scope,
            'analysis_cardinalities': [m for role in SCOPES[scope] for m in ROLE_MEMBERS[role]]}


def _source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _common_design(manifest, role):
    design = json.loads(canonical_json(manifest['design']))
    members = design['composition']['systematic'].pop('member_counts')
    same(members, ROLE_MEMBERS[role], 'source cardinalities do not match role')
    require(set(map(int, manifest['scope']['by_cardinality'])) <= set(members), 'foreign cardinality in source')
    require(manifest['scope']['populations'] > 0, 'empty source')
    require(design['repetitions'] == 10, 'collection requires fixed ten-repetition design')
    design.pop('shard_count')  # ownership can differ; receipts retain original owners
    return design


@contextmanager
def _validated_sources(sources, scope, preliminary, pinned=None):
    """Use the existing strict merger unchanged; bounded disk index, no mining.

The temporary per-source catalog is discarded after its authenticated coverage
check. Native records are always read through the original source's ShardStore.
"""
    metadata = analysis_metadata(scope)
    selected = {}
    common = None
    for role in SCOPES[scope]:
        require(role in sources and sources[role] is not None, 'missing source for '+role)
        directory = Path(sources[role]).resolve()
        manifest = load_manifest(directory)
        if pinned is not None:
            same(manifest['study_id'], pinned[role], 'collection source study changed')
        design = _common_design(manifest, role)
        if common is not None:
            same(design, common, 'incompatible scientific designs')
        common = design
        selected[role] = (directory, manifest)
    with ExitStack() as stack:
        scratch = stack.enter_context(tempfile.TemporaryDirectory(prefix='persistent-v2-collection-'))
        for directory, manifest in selected.values():
            for shard in range(manifest['design']['shard_count']):
                stack.enter_context(shard_lock(directory, shard, shared=True))
        plan = sqlite3.connect(Path(scratch)/'union.sqlite3')
        stack.callback(plan.close)
        plan.execute('CREATE TABLE populations(population_key TEXT PRIMARY KEY,role TEXT,owner INTEGER,analysis_group TEXT,body TEXT)')
        plan.execute('CREATE INDEX groups ON populations(analysis_group,population_key)')
        plan.execute('CREATE TABLE task_ids(task_id TEXT PRIMARY KEY,role TEXT)')
        for role, (directory, manifest) in selected.items():
            catalog = Path(scratch)/(role+'.sqlite3')
            merge_shards(directory, catalog, preliminary=preliminary)
            with closing(sqlite3.connect(f'file:{catalog}?mode=ro', uri=True)) as validated:
                try:
                    plan.executemany('INSERT INTO task_ids VALUES (?,?)',
                                     ((tid, role) for tid, in validated.execute('SELECT task_id FROM tasks')))
                except sqlite3.IntegrityError as exc:
                    raise ValueError('duplicate task identity across sources') from exc
            catalog.unlink()
            with closing(sqlite3.connect(f'file:{directory / "plan.sqlite3"}?mode=ro', uri=True)) as source:
                for pid, owner, group, body in source.execute('SELECT population_key,owner,analysis_group,body FROM tasks'):
                    raw = json.loads(body)
                    require(len(raw['population']['candidates']) in ROLE_MEMBERS[role], 'foreign population cardinality')
                    require(pid == digest(raw['population']), 'population identity mismatch')
                    try:
                        plan.execute('INSERT INTO populations VALUES (?,?,?,?,?)', (pid, role, owner, group, body))
                    except sqlite3.IntegrityError as exc:
                        raise ValueError('duplicate population identity across sources') from exc
        plan.commit()
        yield selected, plan, metadata


def merge_studies(sources, destination, *, analysis_scope='core', preliminary=False):
    """Write a verified logical union, retaining original sources and receipts.

The manifest is a derived index, not a checkpoint or a substitute for its source
studies. Every later export revalidates the selected sources. No baseline copies.
"""
    destination = Path(destination)
    require(not destination.exists(), 'collection destination exists')
    with _validated_sources(sources, analysis_scope, preliminary) as (selected, plan, metadata):
        body = {'layout': LAYOUT, **metadata, 'preliminary': preliminary,
                'analysis_status': 'PRELIMINARY_5_REPETITIONS' if preliminary else 'FINAL_10_REPETITIONS',
                'analysis_repetitions': 5 if preliminary else 10, 'planned_repetitions': 10,
                'collection_source_sha256': _source_hash(),
                'sources': {role: {'directory': str(directory), 'study_id': manifest['study_id'],
                                   'plan_sha256': manifest['plan_sha256'], 'runtime': manifest['runtime'],
                                   'cardinalities': ROLE_MEMBERS[role]}
                            for role, (directory, manifest) in selected.items()},
                'populations': plan.execute('SELECT COUNT(*) FROM populations').fetchone()[0],
                'tasks': plan.execute('SELECT COUNT(*) FROM task_ids').fetchone()[0],
                'mining_simulations_executed': 0, 'baseline_payloads_duplicated': 0}
        body['collection_id'] = digest(body)
        atomic_json(destination, body)
        return body


def export_collection(collection, destination, *, analysis_scope='core', include_repetitions=False):
    body = json.loads(Path(collection).read_text())
    require(body['layout'] == LAYOUT, 'collection layout')
    same(body['collection_id'], digest({k: v for k, v in body.items() if k != 'collection_id'}), 'collection checksum')
    same(body['collection_source_sha256'], _source_hash(), 'collection analysis source changed')
    return export_studies({role: value['directory'] for role, value in body['sources'].items()}, destination,
                          analysis_scope=analysis_scope, include_repetitions=include_repetitions,
                          preliminary=body['preliminary'],
                          pinned={role: value['study_id'] for role, value in body['sources'].items()})


def export_studies(sources, destination, *, analysis_scope='core', include_repetitions=False,
                   preliminary=False, pinned=None):
    """Reconstruct paired outputs across explicitly selected cardinalities.

Existing structure-specific thresholds are retained. A separate scope threshold
uses the same predicates/statistics across all structures in the chosen scope.
"""
    destination = Path(destination)
    require(not destination.exists(), 'export destination exists')
    with _validated_sources(sources, analysis_scope, preliminary, pinned) as (selected, plan, metadata):
        destination.mkdir(parents=True)
        status = {**metadata, 'analysis_status': 'PRELIMINARY_5_REPETITIONS' if preliminary else 'FINAL_10_REPETITIONS',
                  'analysis_repetitions': 5 if preliminary else 10, 'planned_repetitions': 10,
                  'sources': {role: manifest['study_id'] for role, (_, manifest) in selected.items()},
                  'collection_source_sha256': _source_hash(), 'mining_simulations_executed': 0,
                  'automatic_followup': False, 'repetitions_exported': include_repetitions}
        atomic_json(destination/'status.json', {**status, 'status': 'INCOMPLETE'})
        counts, writers = Counter(), {}
        with ExitStack() as stack:
            stores = {}
            for role, (directory, manifest) in selected.items():
                for shard in range(manifest['design']['shard_count']):
                    store = ShardStore(directory, manifest, shard, readonly=True)
                    stack.callback(store.close)
                    stores[role, shard] = store

            def emit(name, rows, source_role='selected_scope'):
                for row in rows:
                    row = {**row, **metadata, 'source_dataset_role': source_role}
                    if name not in writers:
                        handle = stack.enter_context((destination/(name+'.csv')).open('w', newline=''))
                        writers[name] = csv.DictWriter(handle, fieldnames=list(row))
                        writers[name].writeheader()
                    writers[name].writerow(_flat(row))
                    counts[name] += 1

            plan.execute('CREATE TABLE summaries(group_key TEXT,scope_group TEXT,body TEXT)')
            plan.execute('CREATE INDEX thresholds ON summaries(group_key)')
            plan.execute('CREATE INDEX scope_thresholds ON summaries(scope_group)')
            cursor = plan.execute('SELECT analysis_group,role,owner,body FROM populations ORDER BY analysis_group,population_key')
            for _, group in groupby(cursor, key=lambda row: row[0]):
                results = []
                for _, role, owner, body in group:
                    raw = json.loads(body)
                    raw['population']['candidates'] = tuple(tuple(x) for x in raw['population']['candidates'])
                    raw['population'] = Population(**raw['population'])
                    raw['coalitions'] = tuple(tuple(c) for c in raw['coalitions'])
                    task, baselines = SweepTask(**raw), {}
                    for variant in selected[role][1]['design']['variants']:
                        result = task_analysis(stores[role, owner], task, Rule(**variant), analyze_only=True,
                                               baseline_cache=baselines, preliminary=preliminary)
                        results.append(result)
                        for name, rows in result.items():
                            if name == 'minimum_tested_thresholds' or (name == 'repetitions' and not include_repetitions):
                                continue
                            emit(name, rows, role)
                        for row in result['summary']:
                            pooled = dict(row, structure='all_selected_cardinalities')
                            plan.execute('INSERT INTO summaries VALUES (?,?,?)',
                                         (canonical_json(analysis_group_key(row)), canonical_json(analysis_group_key(pooled)), canonical_json(row)))
                emit('equal_power_comparisons', paired_comparisons(results))
                emit('six_variant_comparisons', paired_comparisons(results, cross_rule=True))
                plan.commit()
            for column, name in (('group_key', 'minimum_tested_thresholds'), ('scope_group', 'scope_minimum_tested_thresholds')):
                for key, in plan.execute(f'SELECT DISTINCT {column} FROM summaries ORDER BY {column}'):
                    rows = [json.loads(body) for body, in plan.execute(f'SELECT body FROM summaries WHERE {column}=? ORDER BY rowid', (key,))]
                    if column == 'scope_group':
                        rows = [dict(row, structure='all_selected_cardinalities') for row in rows]
                    emit(name, grouped_thresholds(rows))
        for name in OUTPUTS:
            if name not in writers:
                (destination/(name+'.csv')).write_text('')
                counts[name] = 0
        status.update(status='PRELIMINARY_5_REPETITIONS' if preliminary else 'COMPLETE', row_counts=dict(counts))
        atomic_json(destination/'status.json', status)
        return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('merge', 'export', 'export-collection'))
    parser.add_argument('destination', type=Path)
    parser.add_argument('--core', type=Path)
    parser.add_argument('--extension-5', type=Path)
    parser.add_argument('--extension-6', type=Path)
    parser.add_argument('--collection', type=Path)
    parser.add_argument('--analysis-scope', choices=SCOPES, default='core')
    parser.add_argument('--preliminary', action='store_true')
    parser.add_argument('--include-repetitions', action='store_true')
    args = parser.parse_args()
    sources = {'core': args.core, 'extension_5': args.extension_5, 'extension_6': args.extension_6}
    if args.command == 'export-collection':
        require(args.collection is not None and not args.preliminary and not any(sources.values()),
                'export-collection uses sources and phase pinned by --collection')
        result = export_collection(args.collection, args.destination, analysis_scope=args.analysis_scope,
                                   include_repetitions=args.include_repetitions)
    else:
        require(args.collection is None, '--collection is only for export-collection')
        require(args.command != 'merge' or not args.include_repetitions, 'merge does not export repetitions')
        function = merge_studies if args.command == 'merge' else export_studies
        kwargs = {} if args.command == 'merge' else {'include_repetitions': args.include_repetitions}
        result = function(sources, args.destination, analysis_scope=args.analysis_scope, preliminary=args.preliminary, **kwargs)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
