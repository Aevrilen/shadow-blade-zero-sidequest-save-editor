"""Collect redistribution notices from locked, checksummed upstream sources.

Downloads public license/source-package metadata only; installs nothing.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'legal'


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'PBZ-Quest-Editor-license-collector/1'})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read(30 * 1024 * 1024)


def crate_notices(package):
    name, version = package['name'], package['version']
    url = f'https://static.crates.io/crates/{name}/{name}-{version}.crate'
    payload = download(url)
    if hashlib.sha256(payload).hexdigest() != package['checksum']:
        raise ValueError(f'Checksum mismatch for {name}')
    destination = DEST / 'native' / f'{name}-{version}'
    licenses = []
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as source:
        prefix = f'{name}-{version}/'
        manifest = source.extractfile(prefix + 'Cargo.toml').read()
        metadata = tomllib.loads(manifest.decode())['package']
        for member in source.getmembers():
            relative = member.name.removeprefix(prefix)
            if (not member.isfile() or not member.name.startswith(prefix)
                    or '..' in Path(relative).parts):
                continue
            if not any(word in Path(relative).name.upper() for word in ('LICENSE', 'COPYING', 'NOTICE', 'COPYRIGHT')):
                continue
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.extractfile(member).read())
            licenses.append(path.relative_to(DEST).as_posix())
    return {'component': name, 'version': version, 'license': metadata.get('license'),
            'source': url, 'source_sha256': package['checksum'], 'files': licenses}


def main():
    packages = tomllib.loads((ROOT / 'native/Cargo.lock').read_text(encoding='utf8'))['package']
    packages = [p for p in packages if p.get('source', '').startswith('registry+')]
    records, failures = [], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [(p, pool.submit(crate_notices, p)) for p in packages]
        for package, future in futures:
            try:
                records.append(future.result())
            except Exception as error:
                failures.append({'component': package['name'], 'error': str(error)})
    dll = (ROOT / 'native/pbz_codec.dll').read_bytes()
    commits = sorted(set(m.decode() for m in re.findall(rb'/rustc/([a-f0-9]{40})', dll)))
    raw_files = [(f'https://raw.githubusercontent.com/rust-lang/rust/{commit}/{name}',
                  DEST / 'native' / ('rust-' + commit) / name)
                 for commit in commits for name in ('LICENSE-MIT', 'LICENSE-APACHE', 'COPYRIGHT')]
    raw_files.extend((f'https://raw.githubusercontent.com/openssl/openssl/openssl-4.0.3/{name}',
                      DEST / 'openssl-4.0.3' / name)
                     for name in ('LICENSE.txt',))
    raw_files.extend((f'https://raw.githubusercontent.com/tcltk/{project}/core-8-6-15/license.terms',
                      DEST / f'{project}-8.6.15.license.terms')
                     for project in ('tcl', 'tk'))
    raw_files.append(('https://raw.githubusercontent.com/madler/zlib/v1.3.1/LICENSE',
                      DEST / 'zlib-1.3.1.LICENSE'))
    for url, path in raw_files:
        try:
            contents = download(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
            records.append({'source': url, 'files': [path.relative_to(DEST).as_posix()],
                            'source_sha256': hashlib.sha256(contents).hexdigest()})
        except Exception as error:
            failures.append({'source': url, 'error': str(error)})
    report = {'components': records, 'unavailable': failures,
              'notes': ['OpenSSL 4.0.3 upstream has no separate NOTICE.md at the pinned tag; LICENSE.txt is retained.'],
              'oozextract': {'version': '0.5.7', 'declared_license': 'MIT',
                             'source_manifest': 'native/vendor/oozextract/Cargo.toml',
                             'note': 'Published source package contains a license declaration, but no standalone license text.'}}
    DEST.mkdir(exist_ok=True)
    (DEST / 'upstream-license-index.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'collected': len(records), 'failures': failures}, ensure_ascii=False))
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
