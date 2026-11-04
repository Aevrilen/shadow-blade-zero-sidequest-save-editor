import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pbz_editor.core import EditorError, PBZSContainer, sha256
from pbz_editor.compression import OpenOodleCodec
from quest_editor import FAILED, SUCCEEDED, QuestSession, latest_auto, prepare_plan, quest_key

ROOT = Path(__file__).resolve().parents[1]
CLASS = '/Game/PBZstory/PBZQuest/Simple/Synthetic.Synthetic_C'


def task(path=CLASS, status=FAILED):
    return {'QuestClass': path, 'QuestCompletion': status,
            'QuestBranches': {'branch': {'TasksProgress': 17.123}}, 'ReachedStateNames': ['Synthetic']}


def slot(quests=None, stamp='2026.11.04-12.00.00', inventory=None):
    return {'PBZGameSystem': {'DateTimeString': stamp, 'CycleCount': 3},
            'Inventory': inventory or {'AccessoryInfos': {}, 'InventoryInfos': {}, 'MainWeaponInfos': {},
                                       'ShaChiWeaponInfo': {}, 'MedicineInfos': {}, 'AccessoryIDs': ['Existing']},
            'Narrative': {'NarrativeSavedQuests': quests or [], 'QuestGameTimes': 999.123},
            'Untouched': {'integer': 123456789012345678901234567890, 'float': 1.0}}


def raw(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf8')


def index(rewards=None):
    return {quest_key(CLASS): {'name': '合成支线', 'side': True,
                              'rewards': rewards if rewards is not None else [
                                  {'id': 'SyntheticAccessory', 'category': 'accessory', 'name': '合成饰品', 'quantity': 1}]}}


def container_source(container, definitions, algorithm=0):
    entries = []
    for name, value in definitions:
        data = raw(value)
        entries.append({'name': name, 'algorithm': algorithm, 'flag': 1, 'raw': data,
                        'block': container.seal(data)})
    return container.encode(entries, {e['name']: e['raw'] for e in entries})


class PlanTests(unittest.TestCase):
    def test_latest_auto_uses_time_and_continue_for_ties(self):
        entries = [{'name': 'AutoSave9', 'json': slot(stamp='2026.11.04-11.59.59')},
                   {'name': 'ManualSave0', 'json': slot(stamp='2026.11.04-23.00.00')},
                   {'name': 'AutoSave0', 'json': slot()},
                   {'name': 'AutoSave1', 'json': slot()},
                   {'name': '__Advanced__', 'json': {'LastContinueSlot': 'AutoSave1'}}]
        self.assertEqual(latest_auto(entries)['name'], 'AutoSave1')
        entries.pop()
        self.assertEqual(latest_auto(entries)['name'], 'AutoSave0')
        entries[2]['json']['PBZGameSystem']['DateTimeString'] = 'invalid'
        with self.assertRaises(EditorError):
            latest_auto(entries)

    def test_only_failed_side_quests_change_with_items(self):
        paths = [CLASS, CLASS.replace('/Simple/', '/Branch/'), CLASS.replace('/Simple/', '/Collect/'),
                 CLASS.replace('/Simple/', '/Quest_Branchline/MemoryFlower/'), CLASS.replace('/Simple/', '/Main/'),
                 CLASS.replace('/Simple/', '/Tutorial/')]
        value = slot([task(p) for p in paths] + [task(status=SUCCEEDED), task(status='Active')])
        mappings = {quest_key(p): copy.deepcopy(next(iter(index().values()))) for p in paths[:4]}
        before = raw(value)
        plan = prepare_plan(before, mappings)
        result = json.loads(plan['raw'])
        self.assertEqual((plan['failed_count'], plan['ready_count'], plan['item_count']), (4, 4, 1))
        self.assertEqual([q['QuestCompletion'] for q in result['Narrative']['NarrativeSavedQuests']][:4], [SUCCEEDED]*4)
        self.assertEqual(result['Narrative']['NarrativeSavedQuests'][4:], value['Narrative']['NarrativeSavedQuests'][4:])
        self.assertEqual(result['Narrative']['QuestGameTimes'], value['Narrative']['QuestGameTimes'])
        self.assertIn(b'123456789012345678901234567890', plan['raw'])
        self.assertIn(b'"float": 1.0', plan['raw'])
        self.assertEqual(result['Inventory']['AccessoryIDs'], ['Existing'])
        added = result['Inventory']['AccessoryInfos']['SyntheticAccessory']
        self.assertEqual(added['AcquiredCycle'], 3)
        self.assertEqual(added['CurrentLevel'], 0)
        self.assertEqual(prepare_plan(plan['raw'], mappings)['raw'], plan['raw'])

    def test_existing_unique_record_case_and_level_remain_exact(self):
        value = slot([task()])
        value['Inventory']['AccessoryInfos']['syntheticACCESSORY'] = {'CurrentLevel': 9, 'Odd': 1.2345678901}
        plan = prepare_plan(raw(value), index())
        self.assertEqual(plan['item_count'], 0)
        self.assertTrue(plan['rows'][0]['items'][0]['have'])
        self.assertEqual(json.loads(plan['raw'])['Inventory'], value['Inventory'])

    def test_unknown_task_and_failed_item_adapter_preserve_entire_task(self):
        unknown = CLASS.replace('Synthetic', 'Unmapped')
        value = slot([task(), task(unknown)])
        rewards = [{'id': 'First', 'category': 'accessory', 'quantity': 1},
                   {'id': 'Unsupported', 'category': 'unknown', 'quantity': 1}]
        before = raw(value)
        plan = prepare_plan(before, index(rewards))
        self.assertEqual((plan['ready_count'], plan['pending_count']), (0, 2))
        self.assertEqual(plan['raw'], before)

    def test_consumed_native_goods_and_user_selected_goods(self):
        value = slot([task()])
        value['Inventory']['InventoryInfos']['SyntheticGoods'] = {'CurrentAmount': 0, 'MaxAmount': 3, 'Odd': 42}
        reward = {'id': 'SyntheticGoods', 'category': 'goods', 'quantity': 2}
        plan = prepare_plan(raw(value), index([reward]))
        self.assertEqual(json.loads(plan['raw'])['Inventory'], value['Inventory'])
        reward['ensure_current'] = True
        plan = prepare_plan(raw(value), index([reward]))
        record = json.loads(plan['raw'])['Inventory']['InventoryInfos']['SyntheticGoods']
        self.assertEqual((record['CurrentAmount'], record['MaxAmount'], record['Odd']), (2, 3, 42))


class IsolatedSessionTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / '.test-tmp'
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='pbz-synthetic-', dir=temp_root)
        self.root = Path(self.temp.name)
        self.container = PBZSContainer(bytes(range(32)))
        self.definitions = [('AutoSave0', slot([task()], stamp='2026.11.04-11.59.00')),
                            ('AutoSave4', slot([task()])), ('ManualSave1', slot([task()])),
                            ('__Advanced__', {'LastContinueSlot': 'AutoSave4'}),
                            ('__Achievements__', {'NeverTouch': 123})]
        self.source = container_source(self.container, self.definitions)
        self.path = self.root / 'synthetic-account/PBZSaveGame.sav'
        self.path.parent.mkdir()
        self.path.write_bytes(self.source)
        self.session = QuestSession(self.path, self.root/'synthetic-game', self.container, self.source,
                                    self.root/'local').configure(index())
        self.mock_processes = patch('pbz_editor.core._game_processes', return_value=[])
        self.mock_processes.start()

    def tearDown(self):
        self.mock_processes.stop()
        self.temp.cleanup()

    def test_candidate_preserves_every_unrelated_raw_and_sealed_block(self):
        candidate, changes = self.session._candidate('AutoSave4', [])
        before = self.container.decode(self.source)
        after = self.container.decode(candidate)
        self.assertEqual(len(changes), 1)
        for a, b in zip(before, after):
            if a['name'] != 'AutoSave4':
                self.assertEqual((a['raw'], a['block']), (b['raw'], b['block']))
        self.assertEqual(self.path.read_bytes(), self.source)

    def test_apply_backup_repeat_noop_and_restore(self):
        result = self.session.apply(self.session.target, [])
        edited = self.path.read_bytes()
        self.assertEqual(result['sha256'], sha256(edited))
        backup = Path(result['backup_path'])
        self.assertEqual(backup.read_bytes(), self.source)
        count = len(list(backup.parent.iterdir()))
        repeated = self.session.apply(self.session.target, [])
        self.assertIsNone(repeated['backup_path'])
        self.assertEqual(repeated['operation_count'], 0)
        self.assertEqual(len(list(backup.parent.iterdir())), count)
        self.assertEqual(self.path.read_bytes(), edited)
        restored = self.session.restore(backup)
        self.assertEqual(self.path.read_bytes(), self.source)
        self.assertEqual(Path(restored['backup_path']).read_bytes(), edited)

    def test_changed_source_and_running_game_abort_without_backup(self):
        self.path.write_bytes(self.source+b'changed')
        with self.assertRaises(EditorError):
            self.session.apply(self.session.target, [])
        self.assertFalse(self.session.backup_dir.exists())
        self.path.write_bytes(self.source)
        with patch('pbz_editor.core._game_processes', return_value=[123]):
            with self.assertRaises(EditorError):
                self.session.apply(self.session.target, [])
        self.assertEqual(self.path.read_bytes(), self.source)
        self.assertFalse(self.session.backup_dir.exists())

    def test_user_choice_supports_unmapped_side_quest_and_explicit_no_items(self):
        self.session.quest_index = {}
        self.session.catalog = [{'id': 'AnyWeapon', 'name': '任意物品', 'category': 'weapon'}]
        self.assertEqual(self.session.plan()['ready_count'], 0)
        self.session.set_rewards(0, [{'id': 'anyweapon', 'quantity': 1}])
        self.assertEqual(self.session.plan()['ready_count'], 1)
        self.assertEqual(self.session.plan()['rows'][0]['items'][0]['id'], 'AnyWeapon')
        with self.assertRaises(EditorError):
            self.session.set_rewards(0, [{'id': 'not-in-catalog'}])
        self.session.set_rewards(0, [], no_items=True)
        plan = self.session.plan()
        self.assertTrue(plan['rows'][0]['explicit_none'])
        self.assertEqual(json.loads(plan['raw'])['Inventory'], slot()['Inventory'])

    def test_oodle_stored_block_roundtrip_and_unrelated_preservation(self):
        codec = OpenOodleCodec(ROOT / 'native')
        container = PBZSContainer(bytes(range(32)), codec)
        source = container_source(container, self.definitions, algorithm=2)
        session = QuestSession(self.path, self.root/'synthetic-game', container, source,
                               self.root/'local').configure(index())
        candidate, _ = session._candidate(session.target, [])
        for a, b in zip(container.decode(source), container.decode(candidate)):
            if a['name'] != session.target:
                self.assertEqual((a['raw'], a['block']), (b['raw'], b['block']))
        self.assertNotEqual(source, candidate)


if __name__ == '__main__':
    unittest.main()
