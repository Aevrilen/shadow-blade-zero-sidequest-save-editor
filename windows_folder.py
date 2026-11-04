"""Native Windows folder dialog, using only the bundled Python's ctypes."""
import ctypes
from ctypes import wintypes

from pbz_editor.core import EditorError


class BrowseInfo(ctypes.Structure):
    _fields_ = [('hwndOwner', wintypes.HWND), ('pidlRoot', ctypes.c_void_p),
                ('pszDisplayName', wintypes.LPWSTR), ('lpszTitle', wintypes.LPCWSTR),
                ('ulFlags', wintypes.UINT), ('lpfn', ctypes.c_void_p),
                ('lParam', wintypes.LPARAM), ('iImage', ctypes.c_int)]


def choose_folder():
    # Each HTTP request runs on its own thread; initialize its COM apartment.
    ole = ctypes.WinDLL('ole32')
    shell = ctypes.WinDLL('shell32')
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = []
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    shell.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BrowseInfo)]
    shell.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell.SHGetPathFromIDListEx.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_int]
    shell.SHGetPathFromIDListEx.restype = wintypes.BOOL
    result = ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
    if result < 0:
        raise EditorError('文件夹选择窗口无法初始化；可直接输入游戏目录。')
    pidl = None
    try:
        display = ctypes.create_unicode_buffer(260)
        info = BrowseInfo(None, None, ctypes.cast(display, wintypes.LPWSTR),
                          '选择影之刃零游戏根目录', 0x51, None, 0, 0)
        # BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE | BIF_EDITBOX.
        pidl = shell.SHBrowseForFolderW(ctypes.byref(info))
        if not pidl:
            return ''
        path = ctypes.create_unicode_buffer(32768)
        if not shell.SHGetPathFromIDListEx(pidl, path, len(path), 0):
            raise EditorError('所选位置不是可用的文件系统目录。')
        return path.value
    finally:
        if pidl:
            ole.CoTaskMemFree(pidl)
        ole.CoUninitialize()
