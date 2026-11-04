import ctypes
from unittest import TestCase
from unittest.mock import MagicMock, patch

from pbz_editor.core import EditorError
from windows_folder import choose_folder


class NativeFolderTests(TestCase):
    def libraries(self):
        ole, shell = MagicMock(), MagicMock()
        ole.CoInitializeEx.return_value = 0
        shell.SHBrowseForFolderW.return_value = None
        return ole, shell

    def test_cancel_releases_com_without_using_tk(self):
        ole, shell = self.libraries()
        with patch('ctypes.WinDLL', side_effect=[ole, shell]):
            self.assertEqual(choose_folder(), '')
        ole.CoInitializeEx.assert_called_once_with(None, 2)
        ole.CoUninitialize.assert_called_once()
        ole.CoTaskMemFree.assert_not_called()

    def test_selected_path_and_pidl_are_handled(self):
        ole, shell = self.libraries()
        shell.SHBrowseForFolderW.return_value = 1234
        def convert(pidl, path, capacity, flags):
            self.assertEqual((pidl, capacity, flags), (1234, 32768, 0))
            path.value = 'X:\\合成目录 with spaces'
            return True
        shell.SHGetPathFromIDListEx.side_effect = convert
        with patch('ctypes.WinDLL', side_effect=[ole, shell]):
            self.assertEqual(choose_folder(), 'X:\\合成目录 with spaces')
        ole.CoTaskMemFree.assert_called_once_with(1234)
        ole.CoUninitialize.assert_called_once()

    def test_conversion_failure_frees_native_resources(self):
        ole, shell = self.libraries()
        shell.SHBrowseForFolderW.return_value = 1234
        shell.SHGetPathFromIDListEx.return_value = False
        with patch('ctypes.WinDLL', side_effect=[ole, shell]):
            with self.assertRaises(EditorError):
                choose_folder()
        ole.CoTaskMemFree.assert_called_once_with(1234)
        ole.CoUninitialize.assert_called_once()
