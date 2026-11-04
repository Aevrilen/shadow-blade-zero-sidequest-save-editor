"""Create a reproducible allowlist-only delivery; exclude all local/private data."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ['.gitignore','launcher.py','application.py','desktop_ui.py','desktop_fonts.py',
         'quest_editor.py','quest_resources.py','quest_flow_mapping.py','windows_folder.py',
         '影之刃零支线存档修改器.exe','README.md','LICENSE','THIRD_PARTY_NOTICES.md']
DIRS = ['pbz_editor','data','assets','native','legal','vendor','tests','runtime','launcher']
SKIP = {'__pycache__', '.git', '.pytest_cache'}


def main():
    chosen = [ROOT / name for name in FILES]
    chosen.append(ROOT / 'tools/package.py')
    chosen.append(ROOT / 'tools/verify_portable.py')
    chosen.append(ROOT / 'tools/portable_probe.py')
    chosen.append(ROOT / 'tools/collect_licenses.py')
    chosen.append(ROOT / 'tools/build_launcher.py')
    chosen.append(ROOT / 'tools/build_desktop_fonts.py')
    chosen.append(ROOT / 'tools/desktop_qa.py')
    for directory in DIRS:
        chosen.extend(p for p in (ROOT / directory).rglob('*') if p.is_file()
                      and not any(part in SKIP for part in p.relative_to(ROOT).parts)
                      and p.suffix.casefold() not in ('.pyc', '.pyo', '.sav', '.obj', '.pdb', '.ilk'))
    manifest = {'format': 1, 'upstream_commit': '5fdb13483cefde94e6a2f3dba3d258c84e747582',
                'application':'Native offline desktop window; direct core calls; no HTTP/browser',
                'runtime':'Bundled CPython 3.13.15 x64 + Tcl/Tk 8.6.15; isolated relative paths',
                'files': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(chosen)}}
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    archive = out / '影之刃零支线存档修改器.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(chosen):
            item = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(2026, 11, 4, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, path.read_bytes())
        metadata = zipfile.ZipInfo('delivery-manifest.json', date_time=(2026, 11, 4, 0, 0, 0))
        metadata.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(metadata, json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf8'))
    checked = zipfile.ZipFile(archive)
    if checked.testzip() is not None:
        raise RuntimeError('Archive validation failed')
    forbidden = ('.local/', '.research/', '.library-tools/', 'references/', '.test-tmp/')
    if any(n.startswith(forbidden) or Path(n).suffix.casefold() in ('.sav','.cmd','.bat','.obj','.pdb','.ilk') for n in checked.namelist()):
        raise RuntimeError('Private/local data found in package')
    if 'server.py' in checked.namelist() or any(n.startswith('web/') for n in checked.namelist()):
        raise RuntimeError('Obsolete browser implementation found in desktop package')
    required = ('runtime/python.exe', 'runtime/python313.dll', 'runtime/python313.zip',
                'runtime/python313._pth', 'runtime/LICENSE.txt', 'windows_folder.py',
                '影之刃零支线存档修改器.exe','launcher/launcher.c','launcher/build-manifest.json',
                'desktop_ui.py','application.py','desktop_fonts.py','runtime/pythonw.exe',
                'runtime/_tkinter.pyd','runtime/tcl86t.dll','runtime/tk86t.dll','runtime/zlib1.dll',
                'runtime/tcl/tcl8.6/init.tcl','runtime/tcl/tk8.6/tk.tcl','runtime/tk-origin.json')
    if any(name not in checked.namelist() for name in required):
        raise RuntimeError('Portable runtime missing from package')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.sha256.txt').write_text(digest + '  ' + archive.name + '\n', encoding='utf8')
    print(json.dumps({'archive': str(archive), 'file_count': len(checked.namelist()),
                      'bytes': archive.stat().st_size, 'sha256': digest}, ensure_ascii=False))


if __name__ == '__main__':
    main()
