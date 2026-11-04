"""Failed side quests and their items, prepared as one lossless slot edit."""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path

from pbz_editor.core import (CATEGORY_FIELDS, EditorError, LosslessJSON,
                             MAX_FILE_BYTES, PBZSContainer, SaveSession,
                             edit_inventory)

FAILED = 'EQuestCompletion::QC_Failed'
SUCCEEDED = 'EQuestCompletion::QC_Succeded'  # Native spelling is intentional.


def quest_key(value):
    """Canonical package path, accepting class suffixes and UE quoted paths."""
    if not isinstance(value, str):
        raise EditorError('任务类路径无效。')
    value = value.strip("'\"")
    if "'" in value:
        value = value.split("'", 1)[1].rstrip("'")
    return value.split('.', 1)[0].casefold()


def latest_auto(entries):
    candidates = []
    for entry in entries:
        if not re.fullmatch(r'AutoSave\d+', entry['name']):
            continue
        stamp = entry['json'].get('PBZGameSystem', {}).get('DateTimeString')
        try:
            date = dt.datetime.strptime(stamp, '%Y.%m.%d-%H.%M.%S')
        except (ValueError, TypeError):
            raise EditorError(f"自动槽 {entry['name']} 的时间无法识别，不能确定最近自动存档。")
        candidates.append((date, entry))
    if not candidates:
        raise EditorError('此文件没有可识别的自动存档槽。')
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    tied = [entry for date, entry in candidates if date == candidates[0][0]]
    current = next((e['json'].get('LastContinueSlot') for e in entries if e['name'] == '__Advanced__'), None)
    if current:
        preferred = next((e for e in tied if e['name'] == current), None)
        if preferred:
            return preferred
    return candidates[0][1]


def is_side_path(path):
    path = quest_key(path)
    if '/pbzquest/' not in path:
        return False
    tail = path.split('/pbzquest/', 1)[1].split('/')
    return tail[0] not in ('main', 'tutorial', 'demo', 'test')


def missing_operation(inventory, reward):
    """Keep existing unique records and previously acquired consumables intact."""
    category, ident = reward['category'], reward['id']
    if category not in CATEGORY_FIELDS:
        raise EditorError(f'物品 {ident} 的类别 {category} 尚未适配。')
    records = inventory.get(CATEGORY_FIELDS[category], {})
    if not isinstance(records, dict):
        raise EditorError(f'背包 {CATEGORY_FIELDS[category]} 结构异常。')
    matches = [v for k, v in records.items() if k.casefold() == ident.casefold()]
    if len(matches) > 1 or (matches and not isinstance(matches[0], dict)):
        raise EditorError(f'物品 {ident} 的已有记录异常。')
    quantity = reward.get('quantity', 1)
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise EditorError(f'物品 {ident} 的数量无效。')
    record = matches[0] if matches else None
    if category == 'goods':
        if reward.get('ensure_current'):
            obtained = record.get('CurrentAmount', 0) if record else 0
        else:
            obtained = max(record.get('MaxAmount', 0), record.get('CurrentAmount', 0)) if record else 0
        if not isinstance(obtained, int) or obtained < 0:
            raise EditorError(f'物品 {ident} 的已有数量异常。')
        if obtained >= quantity:
            return None
        quantity -= obtained
    elif record is not None:
        return None
    op = dict(reward, action='add', level=0)
    if category == 'medicine':
        # Unlock a medicine without changing the user's equipment or charges.
        op.pop('quantity', None)
    else:
        op['quantity'] = quantity
    return op


def changed_paths(a, b, prefix=()):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in a.keys() | b.keys():
            if key not in a or key not in b:
                yield prefix + (key,)
            else:
                yield from changed_paths(a[key], b[key], prefix + (key,))
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (left, right) in enumerate(zip(a, b)):
            yield from changed_paths(left, right, prefix + (i,))
    elif a != b:
        yield prefix


def prepare_plan(raw, index):
    original = LosslessJSON(raw).value
    quests = original.get('Narrative', {}).get('NarrativeSavedQuests')
    if not isinstance(quests, list):
        raise EditorError('目标自动槽没有可识别的任务列表。')
    inventory = original.get('Inventory')
    if not isinstance(inventory, dict):
        raise EditorError('目标自动槽没有可识别的背包。')
    working = raw
    rows, changes, allowed = [], [], set()
    for i, quest in enumerate(quests):
        if not isinstance(quest, dict):
            raise EditorError('任务列表中存在无效记录。')
        if quest.get('QuestCompletion') != FAILED:
            continue
        key = quest_key(quest.get('QuestClass', ''))
        meta = index.get(key)
        if meta and not meta.get('side', True):
            continue
        if not meta and not is_side_path(quest.get('QuestClass', '')):
            continue
        row = {'index': i, 'class': quest.get('QuestClass'),
               'name': (meta or {}).get('name') or quest.get('QuestClass', '').rsplit('/', 1)[-1].split('.')[0],
               'items': [], 'ready': False, 'reason': ''}
        row['explicit_none'] = bool(meta and meta.get('rewards') == [])
        rows.append(row)
        if not meta or 'rewards' not in meta:
            row['reason'] = '未解析到对应物品，保留失败记录。'
            continue
        try:
            # This task's items and completion are committed together or discarded.
            before = LosslessJSON(working).value
            operations = []
            for reward in meta['rewards']:
                op = missing_operation(before['Inventory'], reward)
                row['items'].append(dict(reward, have=op is None))
                if op:
                    operations.append(op)
            candidate, item_changes = edit_inventory(working, operations) if operations else (working, [])
            editor = LosslessJSON(candidate)
            status_path = ('Narrative', 'NarrativeSavedQuests', i, 'QuestCompletion')
            editor.set(list(status_path), SUCCEEDED)
            candidate = editor.bytes()
            task_allowed = {status_path}
            for change in item_changes:
                task_allowed.add(('Inventory', CATEGORY_FIELDS[change['category']], change['id']))
            for path in changed_paths(before, editor.value):
                if not any(path[:len(root)] == root for root in task_allowed):
                    raise EditorError('任务修改超出计划字段，已保留原记录。')
            working = candidate
            allowed.update(task_allowed)
            row['ready'] = True
            changes.append({'name': row['name'], 'quest_index': i, 'items': item_changes})
        except (EditorError, ValueError, TypeError, KeyError) as exc:
            row['reason'] = str(exc)
    after = LosslessJSON(working).value
    for path in changed_paths(original, after):
        if not any(path[:len(root)] == root for root in allowed):
            raise EditorError('最终计划超出允许字段。')
    return {'raw': working, 'rows': rows, 'changes': changes,
            'failed_count': len(rows), 'ready_count': len(changes),
            'pending_count': sum(not row['ready'] for row in rows),
            'item_count': sum(not item['have'] for row in rows if row['ready'] for item in row['items'])}


class QuestSession(SaveSession):
    def configure(self, index):
        self.quest_index = {quest_key(k): v for k, v in index.items()}
        self.target = latest_auto(self.entries)['name']
        return self

    def set_rewards(self, quest_index, rewards, no_items=False):
        quests = self._entry(self.target)['json']['Narrative']['NarrativeSavedQuests']
        if not isinstance(quest_index, int) or isinstance(quest_index, bool) or not 0 <= quest_index < len(quests):
            raise EditorError('任务序号无效。')
        quest = quests[quest_index]
        key = quest_key(quest['QuestClass'])
        if quest.get('QuestCompletion') != FAILED or not is_side_path(quest['QuestClass']):
            raise EditorError('只能配置当前自动槽中的失败支线。')
        if not isinstance(rewards, list) or len(rewards) > 100:
            raise EditorError('每条支线最多配置 100 种物品。')
        if not rewards and not no_items:
            raise EditorError('请添加物品，或明确选择不获取物品。')
        catalog = {i['id'].casefold(): i for i in getattr(self, 'catalog', [])}
        selected, seen = [], set()
        for reward in rewards:
            item = catalog.get(str(reward.get('id', '')).casefold())
            if not item or item['category'] not in CATEGORY_FIELDS:
                raise EditorError('请从本地物品目录中选择已支持的物品 ID。')
            quantity = reward.get('quantity', 1)
            if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 9999:
                raise EditorError('物品数量应为 1 到 9999 的整数。')
            if item['category'] != 'goods' and quantity != 1:
                raise EditorError('唯一物品的数量应为 1。')
            if item['id'].casefold() in seen:
                raise EditorError('同一条支线中不要重复选择同一物品。')
            seen.add(item['id'].casefold())
            entry = dict(id=item['id'], name=item.get('name', item['id']), category=item['category'], quantity=quantity,
                         ensure_current=True)
            if item.get('base_capacity') is not None:
                entry['base_capacity'] = item['base_capacity']
            selected.append(entry)
        meta = dict(self.quest_index.get(key, {}), side=True, rewards=selected, user_selected=True)
        self.quest_index[key] = meta
        return key, meta

    @classmethod
    def open_quests(cls, save, game, local):
        from pbz_editor.compatibility import load_profile, resolve_key
        from pbz_editor.bootstrap import signature
        from pbz_editor.compression import OpenOodleCodec
        from quest_resources import build_index
        game, save, local = Path(game).resolve(), Path(save).resolve(), Path(local).resolve()
        if save.stat().st_size > MAX_FILE_BYTES:
            raise EditorError('存档文件超过支持大小。')
        source = save.read_bytes()
        initial = signature(game, load_profile())
        key, _ = resolve_key(game, source)
        codec = OpenOodleCodec(Path(__file__).parent / 'native')
        session = cls(save, game, PBZSContainer(key, codec), source, local)
        index = build_index(game, codec, local)
        if signature(game, load_profile()) != initial:
            raise EditorError('读取期间游戏资源发生变化，请重新读取。')
        session.game_signature = initial
        session.configure(index)
        session.catalog = json.loads((local / 'catalog.json').read_text(encoding='utf8'))
        try:
            choices = json.loads((local / 'user_rewards.json').read_text(encoding='utf8'))
            if choices.get('source') == initial:
                for key, meta in choices.get('quests', {}).items():
                    if key in session.quest_index:
                        session.quest_index[key] = meta
        except (OSError, ValueError, KeyError):
            pass
        return session

    def plan(self):
        return prepare_plan(self._entry(self.target)['raw'], self.quest_index)

    def view(self):
        plan = self.plan()
        slot = self._entry(self.target)['json']['PBZGameSystem']
        return {k: v for k, v in plan.items() if k not in ('raw', 'changes')} | {
            'slot': self.target, 'date': slot.get('DateTimeString'), 'cycle': slot.get('CycleCount', 0),
            'account': self.save_path.parent.name, 'save_path': str(self.save_path),
            'source_sha256': self.source_sha256,
            'catalog': [{key: item[key] for key in ('id', 'name', 'category') if key in item}
                        for item in getattr(self, 'catalog', [])]}

    def _candidate(self, slot, operations, compression='preserve'):
        if slot != self.target or operations:
            raise EditorError('此修改器只处理最近自动槽的失败支线。')
        if self.read_only:
            raise EditorError('此存档版本尚未验证写入。')
        plan = self.plan()
        if not plan['changes']:
            return self.source, []
        replacements = {slot: plan['raw']}
        candidate = self.container.encode(self.entries, replacements, compression)
        checked = self.container.decode(candidate)
        if len(checked) != len(self.entries):
            raise EditorError('重建后槽数量不一致。')
        for before, after in zip(self.entries, checked):
            if before['name'] != after['name']:
                raise EditorError('重建后槽顺序不一致。')
            if before['name'] == slot:
                if after['raw'] != replacements[slot]:
                    raise EditorError('目标槽重读校验失败。')
            elif before['block'] != after['block'] or before['raw'] != after['raw']:
                raise EditorError('非目标槽发生变化。')
        return candidate, [dict(change, slot=slot) for change in plan['changes']]
