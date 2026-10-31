"""Deterministic core state for the event types emitted by the AI-off service.

The exact JS project() is the independent CI oracle. Runtime is Python-only.
Other evidence workflows fail explicitly until their own projection integration.
"""
def project(prefix):
    nodes = {}
    for envelope in prefix:
        event = envelope['event']
        body, kind = event['body'], event['type']
        if kind == 'node.create':
            if body['id'] in nodes:
                raise ValueError('duplicate node')
            nodes[body['id']] = {'kind': body['kind'], 'sets': {}, 'checks': [], 'withdrawn': False,
                                  'lifecycle': 'proposed' if body['kind'] == 'candidate' else None,
                                  'accepted_ever': False}
        elif kind == 'lifecycle.transition':
            node = nodes[body['node']]
            allowed = {'proposed': {'rejected_schema', 'validated', 'cancelled'},
                       'validated': {'rejected_constraints', 'simulation_pending', 'cancelled'},
                       'simulation_pending': {'failed_run', 'evaluated', 'cancelled'},
                       'evaluated': {'non_improving', 'tie', 'inconclusive', 'reproduction_pending', 'cancelled'},
                       'reproduction_pending': {'reproduction_failed', 'reproduced', 'cancelled'},
                       'reproduced': {'accepted', 'non_improving_current', 'within_margin'}}
            if body['to'] not in allowed.get(node['lifecycle'], set()):
                raise ValueError('illegal lifecycle transition')
            if body['to'] == 'accepted' and event['actor_role'] != 'acceptance_gate':
                raise ValueError('acceptance requires core gate')
            node['lifecycle'] = body['to']
            node['accepted_ever'] |= body['to'] == 'accepted'
        elif kind == 'support.add':
            nodes[body['node']]['sets'][body['set_id']] = body['members']
        elif kind == 'verify.add':
            nodes[body['node']]['checks'].append((body['tier'], body['evidence']))
        elif kind in ('withdraw', 'withdraw.retract'):
            nodes[body['node']]['withdrawn'] = kind == 'withdraw'
        else:
            raise ValueError('unsupported core event type')

    memo = {}
    def validity(node_id, active=frozenset()):
        if node_id in memo:
            return memo[node_id]
        if node_id in active:
            raise ValueError('cyclic support')
        node = nodes[node_id]
        if node['withdrawn']:
            result = ('withdrawn', {node_id})
        elif not node['sets']:
            result = ('valid' if node['kind'] in {'source', 'measurement', 'example', 'dataset', 'adapter'}
                      else 'unverified', set())
        else:
            sets = [[validity(member, active | {node_id}) for member in members]
                    for members in node['sets'].values()]
            if any(all(status == 'valid' for status, _ in members) for members in sets):
                result = ('valid', set())
            else:
                roots = set().union(*(roots for members in sets for _, roots in members))
                result = ('stale' if roots else 'unverified', roots)
        memo[node_id] = result
        return result

    output = {}
    for node_id, node in sorted(nodes.items()):
        status, roots = validity(node_id)
        output[node_id] = {'kind': node['kind'], 'lifecycle': node['lifecycle'],
                           'accepted_ever': node['accepted_ever'], 'validity': status,
                           'stale_because': sorted(roots) if status == 'stale' else [],
                           'support_status': {key: 'valid' if all(validity(member)[0] == 'valid' for member in members)
                                              else 'broken' for key, members in node['sets'].items()},
                           'tiers': sorted({tier for tier, evidence in node['checks']
                                            if evidence and all(validity(member)[0] == 'valid' for member in evidence)}),
                           'tainted_by': [], 'review_required': False}
    return {'nodes': output, 'rejected': []}


def board(prefix, projection=None):
    projection = project(prefix) if projection is None else projection
    for envelope in reversed(prefix):
        event = envelope['event']
        if event['type'] == 'lifecycle.transition' and event['body'].get('to') == 'accepted':
            node = event['body']['node']
            if projection['nodes'].get(node, {}).get('validity') == 'valid':
                decision = event['body']['record']
                return {'candidate_id': node, 'j': decision['inputs']['reproduction']['j'],
                        'seq': event['seq']}
    return None
