"""Build the small native Win32 entry point with existing MSVC + Windows SDK.

Discovers installed build tools; does not download, install, or alter the system.
Only the executable, public source and relative build metadata are delivered.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import winreg

ROOT = Path(__file__).resolve().parents[1]
NAME = '影之刃零支线存档修改器.exe'


def version(path):
    return tuple(int(part) for part in path.name.split('.'))


def run(arguments, env=None, cwd=None):
    result = subprocess.run([str(a) for a in arguments], capture_output=True, env=env, cwd=cwd)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).decode('utf8', errors='replace'))
    return result.stdout.decode('utf8', errors='replace')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vs-dir', type=Path)
    parser.add_argument('--sdk-dir', type=Path)
    args = parser.parse_args()
    vs = args.vs_dir
    if vs is None:
        finder = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
        if not finder.is_file():
            raise RuntimeError('Existing MSVC not found; provide --vs-dir. No build tools will be installed automatically.')
        found = run([finder,'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                     '-property','installationPath','-utf8']).strip()
        if not found:
            raise RuntimeError('Existing C++ build tools not found.')
        vs = Path(found)
    compiler_root = max((vs/'VC/Tools/MSVC').iterdir(), key=version)
    sdk = args.sdk_dir
    if sdk is None:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:
            sdk = Path(winreg.QueryValueEx(key, 'KitsRoot10')[0])
    sdk_version = max((sdk/'Include').glob('10.*'), key=version).name
    compiler = compiler_root/'bin/Hostx64/x64/cl.exe'
    linker = compiler_root/'bin/Hostx64/x64/link.exe'
    build = ROOT/'.build/launcher'
    build.mkdir(parents=True, exist_ok=True)
    source = ROOT/'launcher/launcher.c'
    obj = build/'launcher.obj'
    output = ROOT/NAME
    build_environment = dict(os.environ)
    build_environment['PATH'] = os.pathsep.join((str(compiler.parent), str(sdk/'bin'/sdk_version/'x64'),
                                               str(Path(os.environ['SystemRoot'])/'System32')))
    build_environment['TEMP'] = build_environment['TMP'] = str(build)
    includes = [compiler_root/'include', sdk/'Include'/sdk_version/'ucrt',
                sdk/'Include'/sdk_version/'shared', sdk/'Include'/sdk_version/'um']
    run([compiler,'/nologo','/W4','/WX','/utf-8','/TC','/c','/O1','/GS-','/DUNICODE','/D_UNICODE',
         *['/I'+str(p) for p in includes], '/Fo'+str(obj), source], env=build_environment, cwd=build)
    libraries = [sdk/'Lib'/sdk_version/'um/x64'/name for name in ('kernel32.lib','user32.lib','shell32.lib')]
    run([linker,'/NOLOGO','/NODEFAULTLIB','/ENTRY:launcher_entry','/SUBSYSTEM:WINDOWS','/MACHINE:X64',
         '/DYNAMICBASE','/NXCOMPAT','/HIGHENTROPYVA','/INCREMENTAL:NO','/Brepro','/MANIFEST:EMBED',
         "/MANIFESTUAC:level='asInvoker' uiAccess='false'", '/OUT:'+str(output),obj,*libraries], env=build_environment, cwd=build)
    manifest = {'format':1,'architecture':'Windows x64','subsystem':'windows-gui','entrypoint':'launcher_entry',
                'compiler':'Microsoft Visual C++ '+compiler_root.name, 'windows_sdk':sdk_version,
                'crt_dependency':False,'shell_or_cmd_dependency':False,
                'source':'launcher/launcher.c','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'executable':NAME,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                'runtime_entry':'runtime/pythonw.exe',
                'job_lifecycle':'only explicitly assigned desktop process; its explicitly opened folders can break away'}
    (ROOT/'launcher/build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__ == '__main__':
    main()
