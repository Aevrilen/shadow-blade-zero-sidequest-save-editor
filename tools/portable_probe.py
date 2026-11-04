"""Print relative runtime/import/DLL evidence without machine-specific paths."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import cryptography
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pbz_editor.compression import OpenOodleCodec
from desktop_ui import DesktopWindow

ROOT = Path(__file__).resolve().parents[1]


def loaded_modules():
    kernel = ctypes.WinDLL('kernel32')
    psapi = ctypes.WinDLL('psapi')
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetModuleFileNameW.restype = wintypes.DWORD
    psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE),
                                         wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    psapi.EnumProcessModules.restype = wintypes.BOOL
    modules = (wintypes.HMODULE * 2048)()
    size = wintypes.DWORD()
    if not psapi.EnumProcessModules(kernel.GetCurrentProcess(), modules, ctypes.sizeof(modules), ctypes.byref(size)):
        raise RuntimeError('Unable to inspect current-process loaded modules')
    if size.value > ctypes.sizeof(modules):
        raise RuntimeError('Module evidence buffer too small')
    windows = Path(os.environ['SystemRoot']).resolve()
    result = []
    for handle in modules[:size.value // ctypes.sizeof(wintypes.HMODULE)]:
        buffer = ctypes.create_unicode_buffer(32768)
        if not kernel.GetModuleFileNameW(handle, buffer, len(buffer)):
            raise RuntimeError('Unable to identify a loaded module')
        path = Path(buffer.value).resolve()
        if path.is_relative_to(ROOT):
            result.append({'scope':'package', 'path':path.relative_to(ROOT).as_posix()})
        elif path.is_relative_to(windows):
            result.append({'scope':'Windows', 'path':path.relative_to(windows).as_posix()})
        else:
            result.append({'scope':'external', 'path':path.name})
    return result


def main():
    codec = OpenOodleCodec(ROOT/'native')
    key = AESGCM.generate_key(128)
    aes = AESGCM(key)
    nonce = bytes(12)
    sealed = aes.encrypt(nonce,b'portable',None)
    assert aes.decrypt(nonce,sealed,None) == b'portable'
    assert all(Path(p).is_relative_to(ROOT) for p in sys.path)
    with patch('socket.socket',side_effect=AssertionError('Desktop startup must not create sockets')) as sockets, \
         patch('os.startfile',side_effect=AssertionError('Desktop startup must not open external applications')) as external:
        window = DesktopWindow(visible=False)
        try:
            desktop = window.probe()
            desktop.pop('native_window_handle')
            assert not sockets.called and not external.called
        finally:
            window.destroy()
    report = {'version':sys.version.split()[0], 'executable':Path(sys.executable).relative_to(ROOT).as_posix(),
              'isolated':sys.flags.isolated, 'ignore_environment':sys.flags.ignore_environment,
              'no_site':sys.flags.no_site, 'no_user_site':sys.flags.no_user_site,
              'path':[Path(p).relative_to(ROOT).as_posix() for p in sys.path],
              'crypto':cryptography.__version__, 'aes_gcm_roundtrip':True,
              'codec':codec.decompress(codec.compress(b'portable'),8)==b'portable',
              'desktop':desktop,'startup_socket_calls':0,'startup_external_application_calls':0,
              'loaded_modules':loaded_modules()}
    print(json.dumps(report,ensure_ascii=False))


if __name__ == '__main__':
    main()
