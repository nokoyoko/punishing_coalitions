"""Bounded Python oracle for legacy hashes of representation-equivalent DAGs.

Diagnostic only. This does not change production serialization or validation.
It never uses the native emitter to compute its expected checksum.
"""
import hashlib

from punishment_sim.persistent_checkpoint import canonical_json


def tree(raw):
    blocks = raw['terminal']['canonical_blocks'] + raw['terminal']['frontier_blocks']
    parents = [0] * (len(blocks)+1)
    present = set()
    for block in blocks:
        bid, parent = block['id'], block['parent_id'] or 0
        if type(bid) is not int or bid in present or not 0 < bid < len(parents):
            raise ValueError('invalid reference tree coverage')
        if type(parent) is not int or not 0 <= parent < bid:
            raise ValueError('invalid reference tree ancestry')
        parents[bid] = parent
        present.add(bid)
    if len(present) != len(blocks):
        raise ValueError('incomplete reference tree')
    return parents


def streamed_digest(raw):
    """Exact canonical legacy SHA-256, with O(tree + one path) memory.

    Unchanged subtrees use Python's original canonical serializer. Only arrays
    encoded as DAG paths are streamed, with at most 4,096 cached ID byte strings
    joined at once. Full expanded path lists are never retained per branch.
    """
    parents = tree(raw)
    encoded = [str(b).encode() for b in range(len(parents))]
    marked = set()

    def mark(value):
        if isinstance(value, dict):
            children = [mark(v) for v in value.values()]
            found = set(value) == {'__path__'} or any(children)
        elif isinstance(value, (list, tuple)):
            found = any([mark(v) for v in value])
        else:
            return False
        if found:
            marked.add(id(value))
        return found

    mark(raw)

    def emit(value):
        if id(value) not in marked:
            yield canonical_json(value).encode()
        elif isinstance(value, dict) and set(value) == {'__path__'}:
            tip, ancestor, ascending = value['__path__']
            if type(tip) is not int or type(ancestor) is not int or type(ascending) is not bool:
                raise ValueError('invalid reference path descriptor')
            if not 0 <= ancestor < len(parents):
                raise ValueError('invalid reference path ancestor')
            nodes = []
            while tip != ancestor:
                if not 0 < tip < len(parents):
                    raise ValueError('reference path does not reach ancestor')
                nodes.append(tip)
                tip = parents[tip]
            if ascending:
                nodes.reverse()
            yield b'['
            for offset in range(0, len(nodes), 4096):
                if offset:
                    yield b','
                yield b','.join(encoded[b] for b in nodes[offset:offset+4096])
            yield b']'
        elif isinstance(value, dict):
            yield b'{'
            for index, key in enumerate(sorted(value)):
                if index:
                    yield b','
                yield canonical_json(key).encode()+b':'
                yield from emit(value[key])
            yield b'}'
        else:
            yield b'['
            for index, child in enumerate(value):
                if index:
                    yield b','
                yield from emit(child)
            yield b']'

    checksum = hashlib.sha256()
    for chunk in emit(raw):
        checksum.update(chunk)
    return checksum.hexdigest()


def shape(raw):
    parents = tree(raw)
    heights = [0]*len(parents)
    for b in range(1, len(parents)):
        heights[b] = heights[parents[b]]+1
    def length(path):
        tip, ancestor, _ = path['__path__']
        return heights[tip]-heights[ancestor]
    paths = [length(b['path']) for b in raw['terminal']['alternative_branches']]
    return {'blocks': len(parents)-1, 'terminal_branches': len(paths),
            'terminal_path_entries': sum(paths), 'maximum_terminal_path': max(paths, default=0),
            'reorganizations': len(raw['reorganizations']),
            'removed_block_entries': sum(length(r['removed']) for r in raw['reorganizations']),
            'added_block_entries': sum(length(r['added']) for r in raw['reorganizations'])}
