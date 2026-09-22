"""Representation-equivalent replay witness; no alternate mining semantics.

Only redundant paths change encoding. The existing independent Python replay
loop still checks every RNG draw, parent, publication, reaction and endpoint.
"""
from collections import Counter
from dataclasses import asdict

SCHEMA = 'persistent-native-witness-dag-v1'


def path_ref(tip, ancestor, ascending=True):
    return {'__path__': [tip or 0, ancestor or 0, ascending]}


class ReorganizationEndpoints(list):
    def append(self, record):
        # The unchanged reference _adopt computed these paths independently.
        # Retain endpoints after each call instead of every historical suffix.
        ancestor = record['common_ancestor']
        super().append({**record,
            'removed': path_ref(record['removed'][0] if record['removed'] else ancestor, ancestor, False),
            'added': path_ref(record['added'][-1] if record['added'] else ancestor, ancestor)})


def terminal_witness(sim):
    """O(blocks + leaves * actors) reference construction with exact old fields."""
    canonical_ancestor = {None: None}
    for bid, block in sorted(sim.blocks.items()):
        canonical_ancestor[bid] = bid if block.canonical else canonical_ancestor[block.parent_id]
    hidden = set(sim.blocks) - sim.public
    private_tips = hidden - {sim.blocks[b].parent_id for b in hidden}
    states = sim.state_snapshots()
    target_chain = states.get('target', {}).get('private_chain', [])
    active_private = {b for state in states.values() for b in state['private_chain']}
    prefixes, counts = [Counter()], Counter()
    for bid in sim.canonical_chain:
        counts[sim.blocks[bid].owner_id] += 1
        prefixes.append(counts.copy())
    branches = []
    for visibility, tips in (('public', sim.public_tips - {sim.reference_tip}), ('private', private_tips)):
        for tip in sorted(tips):
            ancestor = canonical_ancestor[tip]
            height = sim.height(ancestor)
            branch = {'tip': tip, 'visibility': visibility, 'common_ancestor': ancestor,
                'common_ancestor_height': height, 'path': path_ref(tip, ancestor),
                'height': sim.height(tip), 'canonical_blocks_exposed': sim.public_height-height,
                'active_target_private': tip in target_chain,
                'canonical_rewards_exposed': {a: sim.rewards[a]-prefixes[height][a] for a in sim.miners}}
            if visibility == 'private':
                branch.update(private_actor=sim.blocks[tip].owner_id, active_selfish_private=tip in active_private)
            branches.append(branch)
    unresolved = bool(branches or sim.policy.active or sim.window or sim.selfish.pending)
    boundary = {'method': 'common-persistent-complete-frontier-v2', 'potentially_material': unresolved,
        'max_exposed_canonical_blocks': max((b['canonical_blocks_exposed'] for b in branches), default=0),
        'future_reorganization_excluded': False if unresolved else None,
        'actor_payoff_bounds': {a: [0., 1.] for a in sim.miners} if unresolved else None,
        'interpretation': 'Unresolved branches have no proven small future-payoff bound; intervals are worst-case bounds, not confidence intervals.',
        'private_leads': {a: s['lead_relative_to_public_height'] for a, s in states.items()}}
    terminal = {'reference_tip': sim.reference_tip, 'reference_height': sim.public_height,
        'canonical_chain': list(sim.canonical_chain),
        'canonical_blocks': [asdict(sim.blocks[b]) for b in sim.canonical_chain],
        'public_frontier': sorted(sim.public_tips), 'private_frontier': sorted(private_tips),
        'frontier_blocks': [asdict(b) for _, b in sorted(sim.blocks.items()) if not b.canonical],
        'alternative_branches': branches, 'target_private_chain': target_chain,
        'abandoned_private': sorted(b for s in states.values() for b in s['abandoned_private_blocks']),
        'pending_visibility_block': sim.pending, 'retaliation': sim.policy.snapshot(), 'boundary': boundary,
        'private_states': states, 'pending_publication_window': sim.window,
        'reaction_queue': list(sim.selfish.pending)}
    from .ostracism import OstracismPolicy
    if isinstance(sim.punishment, OstracismPolicy):
        policy = sim.punishment
        eligible = []
        for tip in sorted(policy.eligible_frontier, key=lambda b: -1 if b is None else b):
            ancestor = canonical_ancestor[tip]
            eligible.append({'tip': tip, 'height': sim.height(tip), 'common_ancestor': ancestor,
                'common_ancestor_height': sim.height(ancestor), 'path': path_ref(tip, ancestor),
                'canonical_blocks_exposed': sim.public_height-sim.height(ancestor)})
        terminal['ostracism_eligible_frontier'] = eligible
        for branch in branches:
            tip = branch['tip']
            while tip is not None and tip not in sim.public:
                tip = sim.blocks[tip].parent_id
            root = policy.rejected_by.get(tip)
            branch.update(first_rejected_public_ancestor=root, eligible_by_published_ancestry=root is None)
        boundary.update(max_exposed_canonical_blocks=max(boundary['max_exposed_canonical_blocks'],
            max((b['canonical_blocks_exposed'] for b in eligible), default=0)),
            reference_rejected_by_active_coalition=sim.reference_tip in policy.rejected_by,
            best_eligible_height=policy.best_eligible_height,
            reference_height_minus_best_eligible_height=sim.public_height-policy.best_eligible_height)
    return terminal


def validate_run(result, population, rule, repetition, strategy, flagged, coalition):
    from .persistent_v2_checkpoint import _validate_run
    try:
        _validate_run(result, population, rule, repetition, strategy, flagged, coalition, _dag=True)
    except (KeyError, TypeError, IndexError, AttributeError, ZeroDivisionError) as exc:
        raise ValueError('malformed DAG v2 replay witness') from exc


def expand_fixture(result):
    """Explicit diagnostic adapter only; production never expands this witness."""
    from copy import deepcopy
    result = deepcopy(result)
    records = result['terminal']['canonical_blocks'] + result['terminal']['frontier_blocks']
    parents = {b['id']: b['parent_id'] or 0 for b in records}

    def expand(value):
        if not isinstance(value, dict) or set(value) != {'__path__'}:
            raise ValueError('invalid DAG path descriptor')
        tip, ancestor, ascending = value['__path__']
        if type(tip) is not int or type(ancestor) is not int or type(ascending) is not bool:
            raise ValueError('invalid DAG path fields')
        path = []
        while tip != ancestor:
            if tip not in parents or len(path) > len(parents):
                raise ValueError('invalid DAG ancestry')
            path.append(tip)
            tip = parents[tip]
        return list(reversed(path)) if ascending else path

    for branch in result['terminal']['alternative_branches'] + result['terminal'].get('ostracism_eligible_frontier', []):
        branch['path'] = expand(branch['path'])
    for reorg in result['reorganizations']:
        reorg['removed'] = expand(reorg['removed'])
        reorg['added'] = expand(reorg['added'])
    return result
