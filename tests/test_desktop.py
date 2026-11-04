from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from application import Application
from desktop_ui import DesktopWindow, ItemPicker
from test_application import fixture
from test_quest_editor import ROOT


class DesktopIntegrationTests(unittest.TestCase):
    def setUp(self):
        root = ROOT/'.test-tmp'
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='pbz-desktop-synthetic-',dir=root)
        self.directory = Path(self.temp.name)
        self.app = Application(self.directory/'local')
        self.network = patch('socket.socket',side_effect=AssertionError('Desktop must not create network sockets'))
        self.browser = patch('os.startfile',side_effect=AssertionError('Desktop startup must not open external applications'))
        self.network.start()
        self.browser.start()
        self.window = DesktopWindow(application=self.app,visible=False)

    def tearDown(self):
        self.window.destroy()
        self.network.stop()
        self.browser.stop()
        self.temp.cleanup()

    def settle(self):
        deadline = time.monotonic()+5
        while self.window.busy and time.monotonic()<deadline:
            self.window.root.update()
            time.sleep(0.01)
        self.assertFalse(self.window.busy)

    def test_native_initial_window_has_no_save_or_network_side_effect(self):
        report = self.window.probe()
        self.assertEqual(report['initial_state'],'locate')
        self.assertTrue(report['window_withdrawn'])
        self.assertFalse(report['application_session_open'])
        self.assertFalse(report['startup_created_local_data'])
        self.assertEqual(report['tk_patchlevel'],'8.6.15')
        self.assertEqual(report['tcl_library'],'runtime/tcl/tcl8.6')
        self.assertEqual(report['tk_library'],'runtime/tcl/tk8.6')

    def test_picker_and_async_direct_apply_restore(self):
        session,source = fixture(self.app,self.directory)
        view = dict(session.view(),generation=self.app.generation)
        self.window.show_view(view)
        picker = ItemPicker(self.window,view['rows'][0],visible=False)
        picker.selected.clear()
        picker.items.selection_set('ChosenGoods')
        picker.quantity.set('7')
        picker.add()
        picker.save()
        self.settle()
        self.assertEqual(session.save_path.read_bytes(),source)
        self.assertEqual(self.window.data['rows'][0]['items'][0]['id'],'ChosenGoods')
        with patch('pbz_editor.core._game_processes',return_value=[]):
            self.window.perform('apply')
            self.settle()
            self.assertEqual(self.window.state,'done')
            self.assertEqual(self.window.data['completed_count'],1)
            self.window.perform('restore',{'confirm':True})
            self.settle()
        self.assertEqual(self.window.state,'main')
        self.assertEqual(session.save_path.read_bytes(),source)

    def test_old_async_result_does_not_replace_current_view(self):
        session,_ = fixture(self.app,self.directory)
        view = dict(session.view(),generation=self.app.generation)
        self.window.job_number = 2
        self.window.busy = True
        self.window.state = 'reading'
        self.window.results.put((1,'open',view,None))
        self.window.poll()
        self.assertTrue(self.window.busy)
        self.assertIsNone(self.window.data)
        self.window.results.put((2,'open',view,None))
        self.window.poll()
        self.assertFalse(self.window.busy)
        self.assertEqual(self.window.state,'main')
