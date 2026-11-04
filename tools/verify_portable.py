"""Command-only verification of the actual native desktop EXE and portable ZIP.

All windows are withdrawn. Only synthetic saves below .test-tmp are modified;
no real game, external browser, HTTP server or computer-use tool is involved.
"""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('pid',wintypes.DWORD),
                ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
                ('name',wintypes.WCHAR*260)]


def own_desktop_handle(parent_pid, expected_image):
    """Hold a handle only to our EXE's verified package-local Pythonw child."""
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD,wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE,ctypes.POINTER(ProcessEntry)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise RuntimeError('Cannot identify our desktop child')
    matched = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot,ctypes.byref(entry))
        while more:
            if entry.parent==parent_pid and entry.name.casefold()==expected_image.name.casefold():
                handle = kernel.OpenProcess(0x00100000|0x1000,False,entry.pid)
                if handle:
                    image = ctypes.create_unicode_buffer(32768)
                    size = wintypes.DWORD(len(image))
                    if kernel.QueryFullProcessImageNameW(handle,0,image,ctypes.byref(size)) and Path(image.value).resolve()==expected_image.resolve():
                        matched.append((handle,entry.pid))
                    else:
                        kernel.CloseHandle(handle)
            more = kernel.Process32NextW(snapshot,ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    if len(matched)!=1:
        for handle,_ in matched:
            kernel.CloseHandle(handle)
        raise RuntimeError('Exactly one package-local desktop child must belong to our EXE')
    return kernel,*matched[0]


def own_tcp_listeners(pid):
    """Read only listener rows owned by our known child; never contacts a port."""
    api = ctypes.WinDLL('iphlpapi')
    api.GetExtendedTcpTable.argtypes = [ctypes.c_void_p,ctypes.POINTER(wintypes.DWORD),wintypes.BOOL,
                                       wintypes.ULONG,ctypes.c_int,wintypes.ULONG]
    api.GetExtendedTcpTable.restype = wintypes.DWORD
    result = 0
    for family,row_size,pid_offset in ((2,24,20),(23,56,52)):
        size = wintypes.DWORD()
        status = api.GetExtendedTcpTable(None,ctypes.byref(size),False,family,3,0)
        if status not in (0,122):
            raise RuntimeError('Cannot inspect owned TCP listener table')
        buffer = ctypes.create_string_buffer(size.value)
        if api.GetExtendedTcpTable(buffer,ctypes.byref(size),False,family,3,0):
            raise RuntimeError('Cannot inspect owned TCP listener table')
        rows = int.from_bytes(buffer.raw[:4],'little')
        for index in range(rows):
            start = 4+index*row_size+pid_offset
            if int.from_bytes(buffer.raw[start:start+4],'little')==pid:
                result += 1
    return result


def verify_own_window(handle, pid):
    user = ctypes.WinDLL('user32')
    user.IsWindow.argtypes = [wintypes.HWND]
    user.IsWindow.restype = wintypes.BOOL
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsWindowVisible.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.GetAncestor.argtypes = [wintypes.HWND,wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.PostMessageW.argtypes = [wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user.PostMessageW.restype = wintypes.BOOL
    actual_pid = wintypes.DWORD()
    assert user.IsWindow(handle) and not user.IsWindowVisible(handle)
    user.GetWindowThreadProcessId(handle,ctypes.byref(actual_pid))
    assert actual_pid.value==pid
    top = user.GetAncestor(handle,2)
    assert top and user.IsWindow(top)
    return user,top


def run(command,cwd,env,timeout=30):
    result = subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf8',
                            errors='replace',timeout=timeout,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stdout+result.stderr)
    return result.stdout,result.stderr


def wait_json(path,process):
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        try:
            return json.loads(path.read_text(encoding='utf8'))
        except (FileNotFoundError,json.JSONDecodeError):
            if process.poll() is not None:
                raise RuntimeError('Desktop EXE exited before producing its hidden probe')
            time.sleep(0.04)
    raise RuntimeError('Desktop window creation timed out')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,default=ROOT/'dist/影之刃零支线存档修改器.zip')
    args = parser.parse_args()
    archive = args.archive.resolve()
    base = ROOT/'.test-tmp'
    base.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='desktop-portable-',dir=base) as directory:
        area = Path(directory)
        package = area/'全新解压 desktop app'
        package.mkdir()
        with zipfile.ZipFile(archive) as z:
            assert not any(Path(name).suffix.casefold() in ('.cmd','.bat') for name in z.namelist())
            assert 'server.py' not in z.namelist() and not any(n.startswith('web/') for n in z.namelist())
            z.extractall(package)
        other = area/'其他工作目录 foreign cwd'
        other.mkdir()
        for name in ('sitecustomize.py','usercustomize.py','application.py','desktop_ui.py','tkinter.py','cryptography.py','ctypes.py','startup.py'):
            (other/name).write_text('raise RuntimeError("External configuration must not load")\n',encoding='utf8')
        (other/'init.tcl').write_text('error "External Tcl configuration must not load"\n',encoding='utf8')
        clean = {k:v for k,v in os.environ.items() if not k.upper().startswith(('PYTHON','TCL','TK_'))}
        clean['PATH'] = ''
        hostile = dict(clean,PYTHONHOME=str(other/'missing'),PYTHONPATH=str(other),PYTHONUSERBASE=str(other),
                       PYTHONSTARTUP=str(other/'startup.py'),PYTHONINSPECT='1',PYTHONPYCACHEPREFIX=str(other/'bad-cache'),
                       PYTHONUTF8='0',TCL_LIBRARY=str(other),TK_LIBRARY=str(other),TCLLIBPATH=str(other),
                       TCL8_6_TM_PATH=str(other),TCL8_5_TM_PATH=str(other),BROWSER='must-not-execute')
        console_runtime = package/'runtime/python.exe'
        for environment in (clean,hostile):
            output,_ = run([str(console_runtime),'-I','-B','-X','utf8',str(package/'tools/portable_probe.py')],other,environment)
            runtime = json.loads(output)
            assert runtime['version']=='3.13.15' and runtime['codec']
            assert all(runtime[k]==1 for k in ('isolated','ignore_environment','no_site','no_user_site'))
            assert not any(m['scope']=='external' for m in runtime['loaded_modules'])
            assert runtime['desktop']['tk_patchlevel']=='8.6.15'
            assert runtime['startup_socket_calls']==runtime['startup_external_application_calls']==0
        entry = package/'影之刃零支线存档修改器.exe'
        once = area/'desktop closed.json'
        run([str(entry),'--verify-desktop',str(once)],other,hostile)
        desktop = json.loads(once.read_text(encoding='utf8'))
        assert desktop['initial_state']=='locate' and desktop['window_withdrawn']
        assert not desktop['application_session_open'] and not desktop['startup_created_local_data']
        assert desktop['user_tcl_module_paths_cleared']
        live = area/'desktop running.json'
        process = subprocess.Popen([str(entry),'--verify-desktop',str(live),'--probe-stay-open'],cwd=other,env=hostile,
                                   stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        child_handle = None
        try:
            active = wait_json(live,process)
            kernel,child_handle,pid = own_desktop_handle(process.pid,package/'runtime/pythonw.exe')
            user,top = verify_own_window(active['native_window_handle'],pid)
            listeners = own_tcp_listeners(pid)
            assert listeners==0
            assert user.PostMessageW(top,0x0010,0,0)
            assert kernel.WaitForSingleObject(child_handle,10000)==0
            assert process.wait(timeout=10)==0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            if child_handle:
                kernel.CloseHandle(child_handle)
        output,errors = run([str(console_runtime),'-I','-B','-X','utf8','-m','unittest','discover','-s',str(package/'tests'),'-v'],other,hostile)
        combined = output+errors
        count = int(re.search(r'Ran ([0-9]+) tests?',combined).group(1))
        assert re.search(r'\nOK\s*$',combined)
        assert not (other/'bad-cache').exists() and not (package/'.local').exists()
        desktop.pop('native_window_handle')
        report = {'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                  'application_type':'native offline Tk desktop window','native_exe_subsystem':'Windows GUI',
                  'runtime':'bundled CPython 3.13.15 x64 + Tcl/Tk 8.6.15',
                  'fresh_extract':'Chinese and space-containing directory','unrelated_cwd':True,'empty_path':True,
                  'hostile_python_and_tcl_environment':'ignored or replaced with package paths',
                  'site_and_user_configuration':'not imported','all_import_paths_inside_package':True,
                  'actual_gui_exe_startup':'passed','native_hidden_window_handle_verified':True,
                  'normal_tk_window_close_exited_child_and_launcher':True,'owned_tcp_listeners':listeners,
                  'startup_browser_or_external_application_calls':0,'http_server_started':False,
                  'cmd_or_bat_files_in_zip':False,'obsolete_web_frontend_in_zip':False,
                  'test_console_or_visible_window_opened':False,'startup_created_local_data':False,
                  'synthetic_tests_passed':count,'real_saves_accessed':False,'game_process_changed':False,
                  'desktop_probe':desktop,'runtime_probe':runtime,'game_runtime_verified':False,
                  'full_visual_qa_completed':False,'computer_use_tools_used_for_verification':False}
        (ROOT/'dist/portable-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
