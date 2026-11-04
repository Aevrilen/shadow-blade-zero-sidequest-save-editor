"""Derive item suggestions from directly connected quest/reward asset nodes.

Reads packaged resources only. It never opens or writes game saves. Associations
follow actual node GUID connections, through at most one unconditional helper,
rather than combining every award found in a quest directory.
"""
import struct
from pbz_editor.region_builder import header
from pbz_editor.resources_reader import name_batch

MAPPING_VERSION = 2
UNIQUE_CATEGORIES = {'weapon', 'phantom', 'accessory'}
PASS_THROUGH = {'SetTag_C', 'PlayTutorialUI_Complex_C', 'LootItems_C', 'AddWeaponItem_C'}


def _nodes(data):
    names, _ = name_batch(data)
    body = struct.unpack_from('<I', data, 4)[0]
    start, end = struct.unpack_from('<II', data, 32)
    if start > end or (end - start) % 72:
        raise ValueError('Unsupported Zen export map')
    imports = struct.unpack_from('<I', data, 28)[0]
    package_names = struct.unpack_from('<I', data, 48)[0]
    packages, _ = name_batch(bytes(60) + data[package_names:])
    result = []
    for pos in range(start, end, 72):
        offset, size, name, number = struct.unpack_from('<QQII', data, pos)
        name &= 0x3fffffff
        if name >= len(names) or body + offset + size > len(data):
            raise ValueError('Unsupported Zen export range')
        result.append({'kind': names[name], 'number': number,
                       'raw': data[body + offset:body + offset + size]})
    # The asset export owns a GUID -> local export map. Decode that exact map
    # instead of guessing 16-byte sequences inside arbitrary node payloads.
    roots = [n for n in result if not n['kind'].endswith('_C')
             and not n['kind'].startswith('FlowNode_')]
    node_guids = {}
    for root in roots:
        try:
            fields, zero, pos = header(root['raw'], 0)
            if fields != [0, 2] or zero:
                continue
            pos += 16  # Flow asset's own GUID.
            removed, count = struct.unpack_from('<II', root['raw'], pos)
            pos += 8
            if removed or count != len(result) - 1 or pos + count * 20 > len(root['raw']):
                continue
            current = {}
            for _ in range(count):
                guid = root['raw'][pos:pos + 16]
                index = struct.unpack_from('<i', root['raw'], pos + 16)[0] - 1
                pos += 20
                if not 0 <= index < len(result) or index in current or guid == bytes(16):
                    raise ValueError('Invalid flow node map')
                current[index] = guid
            node_guids = current
            break
        except (ValueError, struct.error, IndexError):
            continue
    if not node_guids:
        return []
    for index, guid in node_guids.items():
        result[index]['guid'] = guid
    for node in result:
        node['refs'] = set()
        if node['kind'] != 'FinishQuest_C':
            continue
        fields, zero, pos = header(node['raw'], 0)
        if not fields or fields[0] != 1 or 1 in zero:
            continue
        # QuestClass is the first serialized property of FinishQuest. Resolve
        # its FPackageIndex through the Zen imported-package list.
        ref = struct.unpack_from('<i', node['raw'], pos)[0]
        if ref >= 0:
            continue
        imp_pos = imports + (-ref - 1) * 8
        if not imports <= imp_pos < start:
            continue
        imported = struct.unpack_from('<Q', data, imp_pos)[0]
        if imported >> 62 != 2:
            continue
        package_index = (imported >> 32) & 0x3fffffff
        if package_index < len(packages) and '/PBZQuest/' in packages[package_index]:
            node['refs'].add(packages[package_index].casefold())
    for node in result:
        node['names'] = names
    return [n for n in result if 'guid' in n]


def _award(node, items):
    raw, names = node['raw'], node['names']
    if node['kind'] not in {'LootItems_C', 'AddWeaponItem_C'}:
        return None
    fields, zero, pos = header(raw, 0)
    if not fields or fields[0] != 1 or 1 in zero:
        return None
    if pos + 8 > len(raw):
        return None
    index, number = struct.unpack_from('<II', raw, pos)
    if index >= len(names) or number:
        return None
    identifier = names[index]
    # Loot row names conventionally end in the exact item ID. Auto-fill only
    # unique equipment, whose grant quantity is one. Stack quantities and
    # multi-item loot rows need a separate adapter or the user's selection.
    item = items.get(identifier.casefold())
    if item is None and node['kind'] == 'LootItems_C':
        item = items.get(identifier.rsplit('.', 1)[-1].casefold())
    if item is None or item.get('category') not in UNIQUE_CATEGORIES:
        return None
    return {'id': item['id'], 'category': item['category'],
            'name': item.get('name') or item['id'], 'quantity': 1}


def _connected_finishes(award, nodes, finishes):
    connected = []
    for finish in finishes:
        if award['guid'] in finish['raw'] or finish['guid'] in award['raw']:
            connected.append(finish)
            continue
        for middle in nodes:
            if middle is award or middle['kind'] not in PASS_THROUGH:
                continue
            to_award = award['guid'] in middle['raw'] or middle['guid'] in award['raw']
            to_finish = finish['guid'] in middle['raw'] or middle['guid'] in finish['raw']
            if to_award and to_finish:
                connected.append(finish)
                break
    return connected


def derive_flow_rewards(store, items):
    """Return unambiguous nearby quest -> unique-item relations.

    ``items`` accepts either an ID-keyed dict or an iterable of catalog items.
    Different award sets for the same quest are left for explicit selection.
    """
    values = items.values() if isinstance(items, dict) else items
    by_id = {item['id'].casefold(): item for item in values}
    candidates = {}
    for path in store.files:
        if '/QuestFlowGraph/' not in path or not path.endswith('.uasset'):
            continue
        data = store.read_file(path)
        try:
            nodes = _nodes(data)
        except (ValueError, struct.error, IndexError, UnicodeError):
            continue  # Other package layouts supply no automatic relation.
        finishes = [n for n in nodes if n['kind'] == 'FinishQuest_C' and n['refs']]
        awards = []
        for node in nodes:
            try:
                reward = _award(node, by_id)
            except (ValueError, struct.error, IndexError):
                continue
            if reward:
                awards.append((node, reward))
        per_finish = {}
        for award, reward in awards:
            connected = _connected_finishes(award, nodes, finishes)
            quests = {q for n in connected for q in n['refs']}
            if len(quests) != 1:
                continue
            quest = next(iter(quests))
            key = (quest, tuple(sorted(n['guid'] for n in connected)))
            group = per_finish.setdefault(key, {'rewards': {}, 'evidence': []})
            group['rewards'][reward['id'].casefold()] = reward
            group['evidence'].append({'source': path, 'node': award['kind'],
                                      'association': 'GUID connection to FinishQuest, at most one unconditional helper'})
        for (quest, _), group in per_finish.items():
            candidates.setdefault(quest, []).append(group)
    result = {}
    for quest, groups in candidates.items():
        signatures = {tuple(sorted(group['rewards'])) for group in groups}
        if len(signatures) != 1:
            continue
        result[quest] = {'rewards': list(groups[0]['rewards'].values()),
                         'evidence': [e for group in groups for e in group['evidence']]}
    return result
