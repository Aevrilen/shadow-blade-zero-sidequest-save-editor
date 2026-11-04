"""Load the approved UI fonts for this process without installing system fonts."""
import ctypes
import os
from pathlib import Path

FAMILIES = {'body': 'Noto Sans CJK SC', 'medium': 'Noto Sans CJK SC Medium',
            'title': 'Noto Serif CJK SC SemiBold', 'seal': 'Noto Serif CJK SC Black'}
FILENAMES = ('NotoSansCJKsc-Regular.otf', 'NotoSansCJKsc-Medium.otf',
             'NotoSerifCJKsc-SemiBold.otf', 'NotoSerifCJKsc-Black.otf')
FR_PRIVATE = 0x10


def register_fonts(directory=None):
    """Return paths successfully loaded; missing fonts use the GUI's fallback."""
    if os.name != 'nt':
        return ()
    directory = Path(directory) if directory else Path(__file__).resolve().parent / 'assets/fonts'
    gdi = ctypes.WinDLL('gdi32')
    gdi.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    gdi.AddFontResourceExW.restype = ctypes.c_int
    loaded = []
    for filename in FILENAMES:
        path = (directory / filename).resolve()
        if path.is_file() and gdi.AddFontResourceExW(str(path), FR_PRIVATE, None):
            loaded.append(path)
    return tuple(loaded)


def unregister_fonts(paths):
    """Release only this call's private font registrations."""
    if os.name != 'nt' or not paths:
        return
    gdi = ctypes.WinDLL('gdi32')
    gdi.RemoveFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    gdi.RemoveFontResourceExW.restype = ctypes.c_int
    for path in paths:
        gdi.RemoveFontResourceExW(str(path), FR_PRIVATE, None)
