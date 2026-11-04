import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from application import Application
from quest_editor import QuestSession
from pbz_editor.core import EditorError, PBZSContainer
from test_quest_editor import ROOT, container_source, index, slot, task


def fixture(application, directory):
    container = PBZSContainer(bytes(range(32)))
    source = container_source(container,[('AutoSave0',slot([task()])),('ManualSave1',slot())])
    save = directory/'synthetic-account/PBZSaveGame.sav'
    save.parent.mkdir()
    save.write_bytes(source)
    session = QuestSession(save,directory/'synthetic-game',container,source,application.local).configure(index())
    session.catalog = [{'id':'ChosenGoods','name':'合成物品','category':'goods'}]
    application.session,application.generation = session,'synthetic-generation'
    return session,source


class DirectApplicationTests(unittest.TestCase):
    def setUp(self):
        root = ROOT/'.test-tmp'
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='pbz-direct-synthetic-',dir=root)
        self.directory = Path(self.temp.name)
        self.app = Application(self.directory/'local')
        self.processes = patch('pbz_editor.core._game_processes',return_value=[])
        self.processes.start()

    def tearDown(self):
        self.processes.stop()
        self.temp.cleanup()

    def test_startup_does_not_open_or_write_any_save(self):
        self.assertIsNone(self.app.session)
        self.assertFalse(self.app.local.exists())

    def test_stale_generation_and_snapshot_are_rejected(self):
        session,source = fixture(self.app,self.directory)
        with self.assertRaises(EditorError):
            self.app.dispatch('apply',{'generation':'stale','source_sha256':session.source_sha256})
        with self.assertRaises(EditorError):
            self.app.dispatch('apply',{'generation':self.app.generation,'source_sha256':'wrong'})
        self.assertEqual(session.save_path.read_bytes(),source)
        self.assertFalse(session.backup_dir.exists())

    def test_direct_choice_apply_and_restore_only_isolated_fixture(self):
        session,source = fixture(self.app,self.directory)
        generation = self.app.generation
        configured = self.app.dispatch('configure',{'generation':generation,'quest_index':0,
                                                   'rewards':[{'id':'ChosenGoods','quantity':7}]})
        self.assertEqual(configured['rows'][0]['items'][0]['id'],'ChosenGoods')
        self.assertEqual(session.save_path.read_bytes(),source)
        result = self.app.dispatch('apply',{'generation':generation,'source_sha256':session.source_sha256})
        self.assertEqual(result['completed_count'],1)
        self.assertEqual(session._entry('AutoSave0')['json']['Inventory']['InventoryInfos']['ChosenGoods']['CurrentAmount'],7)
        self.assertTrue(result['result']['file_verified'])
        restored = self.app.dispatch('restore',{'generation':generation,'confirm':True})
        self.assertTrue(restored['restored'])
        self.assertEqual(session.save_path.read_bytes(),source)
