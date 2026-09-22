"""Production validation policy and ledger checks; no simulation RNG or replay here."""
from collections import Counter
from dataclasses import asdict, replace, dataclass

from .persistent_checkpoint import canonical_json, digest
from .persistent_v2 import condition_identity
from .persistent_v2_checkpoint import require, same

POLICY_VERSION = 'persistent-production-validation-v1'
DEFAULT_SALT = 'persistent-v2-production-audit-2026-09'
LIGHT = 'lightweight-ledger-v1'
FULL = 'lightweight-ledger-plus-native-replay-v1'


def normalize_policy(value=None):
    value = {} if value is None else dict(value)
    require(set(value) <= {'version', 'mode', 'salt', 'sample_per_million'}, 'validation policy fields')
    result = {'version': POLICY_VERSION, 'mode': 'full', 'salt': DEFAULT_SALT, 'sample_per_million': 10000, **value}
    require(result['version'] == POLICY_VERSION and result['mode'] in ('full', 'sampled'), 'validation policy version/mode')
    require(type(result['salt']) is str and bool(result['salt']), 'validation salt')
    require(type(result['sample_per_million']) is int and 0 <= result['sample_per_million'] <= 1000000, 'validation sample rate')
    return result


def stratum(population):
    powers = [h for _, h in population.candidates]
    total = sum(powers)
    return canonical_json([len(powers), population.gamma, population.natural_fork_rate,
        'alpha<.20' if population.target_hash_power < .20 else 'alpha<.30' if population.target_hash_power < .30 else 'alpha>=.30',
        'total<.20' if total < .20-1e-12 else 'total<.40' if total < .40-1e-12 else 'total>=.40',
        'equal' if max(powers)-min(powers) < 1e-12 else 'skewed' if max(powers)/min(powers) >= 4 else 'moderate'])


def add_anchor(anchors, population, policy):
    if policy['mode'] == 'full':
        return
    pid = digest(asdict(population))
    key = stratum(population)
    rank = digest([POLICY_VERSION, policy['salt'], 'stratum-anchor', pid])
    candidate = (rank, pid)
    if key not in anchors or candidate < anchors[key]:
        anchors[key] = candidate


def validation_context(policy=None, anchors=None):
    policy = normalize_policy(policy)
    return {'policy': policy, 'anchors': {k: value[1] for k, value in sorted((anchors or {}).items())}}


@dataclass(frozen=True)
class PreparedContext:
    policy_sha256: str
    mode: str
    salt: str
    sample_per_million: int
    anchor_ids: frozenset


def prepare_context(context):
    if isinstance(context, PreparedContext):
        return context
    policy = normalize_policy(context['policy'])
    same(policy, context['policy'], 'noncanonical validation policy')
    return PreparedContext(digest(context), policy['mode'], policy['salt'],
                           policy['sample_per_million'], frozenset(context['anchors'].values()))


def replay_reasons(identity, context, risks=()):
    policy = prepare_context(context)
    if policy.mode == 'full':
        return ['full_policy']
    reasons = []
    # Integer threshold, no floating-point or random-state dependence.
    score = int(digest([POLICY_VERSION, policy.salt, 'condition-sample', digest(identity)]), 16)
    if score*1000000 < policy.sample_per_million*(1 << 256):
        reasons.append('hash_sample')
    # Anchor populations run every rule and all native required condition types.
    # Repetitions 0 and 5 give guaranteed coverage in both fixed study phases.
    if identity['repetition'] in (0, 5) and digest(identity['population']) in policy.anchor_ids:
        reasons.append('stratum_anchor')
    reasons.extend('risk:'+risk for risk in sorted(risks))
    return reasons


def attestation(identity, context, risks):
    reasons = replay_reasons(identity, context, risks)
    return {'policy_sha256': prepare_context(context).policy_sha256, 'level': FULL if reasons else LIGHT,
            'replay_reasons': reasons, 'risk_flags': sorted(risks)}


def reaction_diagnostics(result):
    reactions = result['selfish_reactions']
    rounds = Counter(frame['discovery_event'] for frame in reactions)
    return {'max_simultaneous_decisions': max((len(frame['decisions']) for frame in reactions), default=0),
            'max_rounds_in_discovery': max(rounds.values(), default=0)}


def diagnostic_risks(diag):
    return [name for key, name in [('max_simultaneous_decisions', 'simultaneous_selfish_reactions'),
                                   ('max_rounds_in_discovery', 'cascading_selfish_reactions')] if diag[key] > 1]


def risk_flags(result):
    return diagnostic_risks(reaction_diagnostics(result))


def validate_attestation(record, context):
    value = record['validation']
    require(set(value) == {'policy_sha256', 'level', 'replay_reasons', 'risk_flags'}, 'validation attestation fields')
    require(type(value['risk_flags']) is list and value['risk_flags'] == sorted(set(value['risk_flags']))
            and set(value['risk_flags']) <= {'simultaneous_selfish_reactions', 'cascading_selfish_reactions'}, 'validation risk flags')
    diag = record['punishment']['reaction_diagnostics']
    require(set(diag) == {'max_simultaneous_decisions', 'max_rounds_in_discovery'} and all(type(x) is int and x >= 0 for x in diag.values()), 'reaction audit diagnostics')
    count = record['punishment']['selfish_reactions']['count']
    require(type(count) is int and count >= 0 and (diag['max_rounds_in_discovery'] == 0) == (count == 0)
            and diag['max_rounds_in_discovery'] <= count and diag['max_simultaneous_decisions'] <= len(record['actors']), 'reaction audit bounds')
    same(value['risk_flags'], sorted(diagnostic_risks(diag)), 'validation risk evidence mismatch')
    same(value, attestation(record['identity'], context, value['risk_flags']), 'validation policy/level/selection mismatch')


def validate_lightweight(result, population, rule, repetition, strategy, flagged, coalition):
    """Linear ledger/accounting scans, without re-executing policy decisions.

No replay object, RNG draw, fork-choice helper or release-plan call is used.
This checks structural consistency; it does not certify the trajectory rules.
"""
    try:
        _validate_lightweight(result, population, rule, repetition, strategy, flagged, coalition)
        return risk_flags(result)
    except (KeyError, TypeError, IndexError, AttributeError, ZeroDivisionError) as exc:
        raise ValueError('malformed lightweight v2 result') from exc


def _validate_lightweight(r, p, rule, rep, strategy, flagged, coalition):
    identity = condition_identity(p, rep, strategy, flagged, coalition, rule)
    same(r['identity'], identity, 'light identity')
    require(r['condition_id'] == digest(identity) and r['network_version'] == identity['network_version']
            and r['model_version'] == identity['model_version'], 'light condition/model')
    same(r['population'], asdict(replace(p, seed=identity['actual_seed'])), 'light seed/population')
    require(r['status'] == 'COMPLETE' and r['error'] is None and r['scripted_discoveries'] == [], 'light completion/native provenance')
    require(r['strategy'] == strategy and r['label'] == ('flagged' if identity['flagged'] else 'unflagged'), 'light condition label')
    same(r['active_coalition'], identity['active_coalition'], 'light coalition')
    require(r['punishment_rule'] == (rule.punishment_rule if identity['flagged'] else None)
            and r['counter_fork_k'] == (rule.counter_fork_k if identity['flagged'] else None), 'light rule')
    require('recording_mode' not in r or (r['recording_mode'] == 'production-v2' and 'trace' not in r and 'public_events' not in r), 'light recording mode')
    n, events, t = r['accepted_blocks'], r['events'], r['terminal']
    require(type(n) is int and type(events) is int and events >= n >= p.target_accepted_blocks, 'light horizon')
    records = t['canonical_blocks']+t['frontier_blocks']
    blocks = {b['id']: b for b in records}
    require(len(blocks) == len(records) == events and set(blocks) == set(range(1, events+1)), 'light ledger coverage')
    miners = {m.id: m for m in p.miners}
    discovered, accepted, orphaned, hidden_counts = Counter(), Counter(), Counter(), Counter()
    public = set()
    for bid, b in blocks.items():
        parent = b['parent_id']
        require(type(bid) is int and b['discovery_sequence'] == bid and b['owner_id'] in miners, 'light block identity')
        require(parent is None or (type(parent) is int and parent in blocks and parent < bid), 'light ancestry')
        require(b['height'] == (0 if parent is None else blocks[parent]['height'])+1, 'light height')
        require(type(b['canonical']) is bool and type(b['initially_withheld']) is bool, 'light block flags')
        discovered[b['owner_id']] += 1
        if b['publication_sequence'] is not None:
            public.add(bid)
            (accepted if b['canonical'] else orphaned)[b['owner_id']] += 1
        else:
            require(not b['canonical'] and b['release_batch'] is None and b['publication_kind'] is None, 'light hidden fields')
            hidden_counts[b['owner_id']] += 1
    published = set()
    last_event = 0
    for index, batch in enumerate(r['publication_batches'], 1):
        event = batch['discovery_event']
        require(batch['batch'] == index and batch['blocks'] and type(event) is int and last_event <= event <= events, 'light publication batch')
        last_event = event
        for bid in batch['blocks']:
            require(type(bid) is int and bid in blocks and bid <= event and bid not in published, 'light publication coverage')
            b = blocks[bid]
            require(b['parent_id'] is None or b['parent_id'] in published, 'light publication ancestry')
            require(b['publication_sequence'] == len(published)+1 and b['release_batch'] == index and b['publication_kind'] == batch['kind'], 'light publication metadata')
            published.add(bid)
    require(published == public, 'light public coverage')
    chain = t['canonical_chain']
    require(len(chain) == n and len(set(chain)) == n and chain[-1] == t['reference_tip'] and t['reference_height'] == n, 'light canonical endpoint')
    require(set(chain) == {bid for bid, b in blocks.items() if b['canonical']}, 'light canonical flags')
    for i, bid in enumerate(chain):
        require(bid in public and blocks[bid]['parent_id'] == (chain[i-1] if i else None), 'light canonical chain')
    require(n == max(blocks[bid]['height'] for bid in public), 'light public height')
    hidden = set(blocks)-public
    require(t['public_frontier'] == sorted(public-{blocks[bid]['parent_id'] for bid in public}), 'light public frontier')
    require(t['private_frontier'] == sorted(hidden-{blocks[bid]['parent_id'] for bid in hidden}), 'light private frontier')
    actors = {'target'} if strategy == 'selfish' else set()
    if identity['flagged'] and rule.punishment_rule == 'selfish':
        actors.update(identity['active_coalition'])
    require(set(t['private_states']) == actors and r['selfish_actor_order'] == [m for m in miners if m in actors], 'light selfish actors')
    private, abandoned = set(), set()
    for actor, state in t['private_states'].items():
        owned = state['private_chain']
        lost = state['abandoned_private_blocks']
        released = state['released_blocks']
        require(len(owned) == len(set(owned)) and len(lost) == len(set(lost)) and len(released) == len(set(released)), 'light private duplicates')
        require(not set(owned)&set(lost) and not private&set(owned) and not abandoned&set(lost), 'light private overlap')
        for bid in owned+lost:
            require(bid in hidden and blocks[bid]['owner_id'] == actor and blocks[bid]['initially_withheld'], 'light private ownership')
        for i, bid in enumerate(owned):
            parent = blocks[bid]['parent_id']
            require(parent == owned[i-1] if i else parent is None or parent in public, 'light private chain')
        tip = owned[-1] if owned else None
        height = blocks[tip]['height'] if tip else 0
        require(state['actor_id'] == actor and state['private_block_count'] == len(owned)
                and state['private_tip'] == tip and state['private_tip_height'] == height
                and state['lead_relative_to_public_height'] == (height-n if tip else 0), 'light private state')
        require(state['private_fork_base'] == (blocks[owned[0]]['parent_id'] if owned else None), 'light private base')
        require(set(released) == {bid for bid in public if blocks[bid]['owner_id'] == actor and blocks[bid]['initially_withheld']}, 'light released ownership')
        private.update(owned); abandoned.update(lost)
    require(not private&abandoned and hidden == private|abandoned, 'light hidden coverage')
    same(t['target_private_chain'], t['private_states'].get('target', {}).get('private_chain', []), 'light target private chain')
    require(t['abandoned_private'] == sorted(abandoned) and not t['reaction_queue'], 'light terminal private/queue')
    require(set(r['actors']) == set(miners), 'light actor coverage')
    for actor, miner in miners.items():
        value = r['actors'][actor]
        require(value['role'] == miner.role and value['hash_power'] == miner.hash_power, 'light actor identity')
        for key, expected in [('discovered', discovered[actor]), ('accepted', accepted[actor]), ('orphaned', orphaned[actor]), ('unresolved', hidden_counts[actor])]:
            require(type(value[key]) is int and value[key] == expected, 'light ledger accounting')
        require(value['public_noncanonical'] == orphaned[actor] and value['payoff'] == accepted[actor]/n
                and value['normalized_revenue'] == value['payoff']/miner.hash_power, 'light payoff')
        require(value['discovered'] == value['accepted']+value['orphaned']+value['unresolved'], 'light conservation')
    require(sum(accepted.values()) == n and sum(discovered.values()) == events, 'light global accounting')
    # Check recorded frontier paths and conservative bounds without reconstructing
    # any fork-choice/strategy trajectory. Work is linear in the supplied ledger.
    branches = t['alternative_branches']
    exposed = []
    branch_tips = set()
    ancestors = {b['common_ancestor_height'] for b in branches}
    prefixes, counts = {0: Counter()}, Counter()
    canonical_ids = set(chain)
    for height, bid in enumerate(chain, 1):
        counts[blocks[bid]['owner_id']] += 1
        if height in ancestors:
            prefixes[height] = counts.copy()
    for branch in branches:
        path, ancestor = branch['path'], branch['common_ancestor']
        require(bool(path) and path[-1] == branch['tip'] and branch['tip'] not in branch_tips, 'light branch path')
        branch_tips.add(branch['tip'])
        h = 0 if ancestor is None else blocks[ancestor]['height']
        require(ancestor is None or ancestor in canonical_ids, 'light branch ancestor')
        require(branch['common_ancestor_height'] == h and branch['height'] == blocks[path[-1]]['height'], 'light branch height')
        for i, bid in enumerate(path):
            require(bid in blocks and not blocks[bid]['canonical'] and blocks[bid]['parent_id'] == (path[i-1] if i else ancestor), 'light branch ancestry')
        require(branch['visibility'] == ('public' if path[-1] in public else 'private'), 'light branch visibility')
        require(branch['canonical_blocks_exposed'] == n-h, 'light exposed depth')
        same(branch['canonical_rewards_exposed'], {actor: accepted[actor]-prefixes[h][actor] for actor in miners}, 'light exposed rewards')
        exposed.append(n-h)
    require(branch_tips == (set(t['public_frontier'])-{t['reference_tip']})|set(t['private_frontier']), 'light branch coverage')
    require(('ostracism_eligible_frontier' in t) == (identity['flagged'] and rule.punishment_rule == 'ignore'), 'light eligible frontier presence')
    for branch in t.get('ostracism_eligible_frontier', []):
        tip, path, ancestor = branch['tip'], branch['path'], branch['common_ancestor']
        require(tip is None or tip in public, 'light eligible frontier visibility')
        h = blocks[ancestor]['height'] if ancestor is not None else 0
        require(ancestor is None or ancestor in canonical_ids, 'light eligible ancestor')
        require(branch['common_ancestor_height'] == h and branch['height'] == (blocks[tip]['height'] if tip else 0)
                and branch['canonical_blocks_exposed'] == n-h, 'light eligible frontier exposure')
        require((path[-1] if path else ancestor) == tip, 'light eligible frontier endpoint')
        for i, bid in enumerate(path):
            require(bid in public and not blocks[bid]['canonical'] and blocks[bid]['parent_id'] == (path[i-1] if i else ancestor), 'light eligible path')
        exposed.append(n-h)
    require(t['boundary']['max_exposed_canonical_blocks'] == max(exposed, default=0), 'light boundary exposure')
    window = t['pending_publication_window']
    require(t['pending_visibility_block'] == (window['origin_block'] if window else None), 'light pending window')
    if window:
        require(window['discovery_event'] == events and window['origin_block'] in public and set(window['delayed_tips']) <= public, 'light window endpoint')
    if branches or window:
        require(t['boundary']['potentially_material'] is True, 'light unresolved boundary')
    require(r['rng']['discoveries']['draw_count'] == events, 'light discovery draws')
    for name in ('ties', 'natural'):
        require(type(r['rng'][name]['draw_count']) is int and 0 <= r['rng'][name]['draw_count'] <= events, 'light RNG draw bounds')
    for values in (r['member_activations'], r['member_opportunities'], r['natural_pairs']):
        require(all(type(x) is int and x >= 0 for x in values.values()), 'light counter bounds')
    # Same finite-value/JSON contract as durable serialization, including fields
    # not otherwise involved in these accounting checks. No policy replay.
    canonical_json(r)
