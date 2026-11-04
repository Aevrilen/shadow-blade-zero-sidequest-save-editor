"""Read installed quest metadata and cache only derived names/item relations."""
import hashlib
import json
import re
import struct
from pathlib import Path

from pbz_editor.bootstrap import signature
from pbz_editor.compatibility import load_profile
from pbz_editor.resources_reader import IoStore, name_batch, localization
from pbz_editor.pak_reader import PakReader
from pbz_editor.catalog_builder import build_catalog
from quest_editor import quest_key, is_side_path
from quest_flow_mapping import derive_flow_rewards


def localized_quest_name(data, loc):
    """Read an actual serialized FString localization key, not a name-table guess."""
    labels = set()
    for match in re.finditer(rb'QuestRumor_[0-9]+\x00', data):
        start = match.start()
        if start < 4 or struct.unpack_from('<I', data, start - 4)[0] != len(match.group()):
            continue
        key = match.group()[:-1].decode('ascii')
        if key in loc:
            labels.add(loc[key])
    return next(iter(labels)) if len(labels) == 1 else ''


def build_index(game, codec, local):
    game, local = Path(game), Path(local)
    profile = load_profile()
    identity = signature(game, profile)
    mapping_path = Path(__file__).parent / 'data/quest_rewards.json'
    rules = json.loads(mapping_path.read_text(encoding='utf8'))
    parser_source = (Path(__file__).parent / 'quest_flow_mapping.py').read_bytes()
    cache_key = hashlib.sha256(identity.encode() + mapping_path.read_bytes() + parser_source
                               + Path(__file__).read_bytes()).hexdigest()
    cache = local / 'resources.json'
    try:
        ready = json.loads(cache.read_text(encoding='utf8'))
        if ready['source'] == cache_key:
            (local / 'catalog.json').write_text(json.dumps(ready['items'], ensure_ascii=False), encoding='utf8')
            return ready['quests']
    except (OSError, ValueError, KeyError):
        pass
    root = game / 'ProjectPBZ/Content/Paks'
    store = IoStore(root / 'ProjectPBZ-Windows.utoc', codec)
    pak = PakReader(root / 'ProjectPBZ-Windows.pak', codec)
    loc = localization(pak.read_file('ProjectPBZ/Content/Localization/Game/zh-Hans/Game.locres'))
    catalog = build_catalog(store, loc, {}, profile['resources'],
                            profile.get('item_property_schemas'), tolerant=True)
    items = {item['id'].casefold(): item for item in catalog['items']}
    derived = derive_flow_rewards(store, catalog['items'])
    result = {}
    for path in store.files:
        if '/PBZQuest/' not in path or not path.endswith('.uasset'):
            continue
        package = '/Game/' + path.split('/Content/', 1)[1][:-7]
        key = quest_key(package)
        asset = store.read_file(path)
        names, _ = name_batch(asset)
        # Names often contain localized FText keys. A rule can specify its exact
        # display key; otherwise retain the actual class name without inventing.
        seed = rules.get(key, rules.get(package.rsplit('/', 1)[-1], {}))
        rule = dict(derived.get(key, {}), **seed)
        # Both sources identify this exact task; preserve additional directly
        # associated items, e.g. BaiShan's weapon as well as its accessory.
        if seed.get('rewards') and derived.get(key, {}).get('rewards'):
            merged = {r['id'].casefold(): r for r in derived[key]['rewards']}
            merged.update({r['id'].casefold(): r for r in seed['rewards']})
            rule['rewards'] = list(merged.values())
        label = rule.get('name') or loc.get(rule.get('name_key', ''), '') or localized_quest_name(asset, loc)
        if not label:
            labels = [loc[n] for n in names if n in loc and n.casefold().endswith(('name', 'title'))]
            label = labels[0] if len(set(labels)) == 1 else package.rsplit('/', 1)[-1]
        meta = {'name': label, 'side': is_side_path(package), 'source': path}
        if 'rewards' in rule:
            rewards = []
            for reward in rule['rewards']:
                item = items.get(reward['id'].casefold())
                if item is None:
                    # A resource version mismatch remains a pending quest.
                    break
                rewards.append(dict(reward, id=item['id'], category=item['category'],
                                    name=item.get('name') or item['id']))
            else:
                meta['rewards'] = rewards
                meta['evidence'] = rule.get('evidence', '')
        result[key] = meta
    local.mkdir(parents=True, exist_ok=True)
    supported = [i for i in catalog['items'] if i['category'] in ('goods', 'weapon', 'phantom', 'accessory', 'medicine')]
    cache.write_text(json.dumps({'source': cache_key, 'quests': result, 'items': supported}, ensure_ascii=False), encoding='utf8')
    (local / 'catalog.json').write_text(json.dumps(supported, ensure_ascii=False), encoding='utf8')
    return result
