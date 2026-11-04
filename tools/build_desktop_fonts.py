"""Restore approved UI WOFF subsets as process-private desktop OpenType fonts.

Uses only the standard library and retains font tables/names unchanged. Font
licenses are in legal/OFL-1.1.txt. WOFF specification: https://www.w3.org/TR/WOFF/
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
SPECS = [
    ('body', 'NotoSansCJKsc-Regular', 'Noto Sans CJK SC'),
    ('medium', 'NotoSansCJKsc-Medium', 'Noto Sans CJK SC Medium'),
    ('title', 'NotoSerifCJKsc-SemiBold', 'Noto Serif CJK SC SemiBold'),
    ('seal', 'NotoSerifCJKsc-Black', 'Noto Serif CJK SC Black'),
]


def checksum(data):
    padded = data + bytes((-len(data)) % 4)
    return sum(struct.unpack('>' + 'I' * (len(padded) // 4), padded)) & 0xffffffff


def restore_sfnt(data):
    magic, flavor, length, count, reserved, expected_size = struct.unpack_from('>4sIIHHI', data)
    if magic != b'wOFF' or length != len(data) or not count or reserved:
        raise ValueError('Invalid WOFF header')
    selector = count.bit_length() - 1
    search = 16 * (1 << selector)
    result = bytearray(struct.pack('>IHHHH', flavor, count, search, selector, count * 16 - search))
    result.extend(bytes(count * 16))
    head = None
    for i in range(count):
        tag, offset, compressed, size, original_checksum = struct.unpack_from('>4sIIII', data, 44 + i * 20)
        payload = data[offset:offset + compressed]
        if compressed < size:
            payload = zlib.decompress(payload)
        if len(payload) != size:
            raise ValueError('Invalid font table length')
        if tag == b'head':
            head = len(result)
            payload = payload[:8] + bytes(4) + payload[12:]
        if checksum(payload) != original_checksum:
            raise ValueError('Invalid font table checksum')
        struct.pack_into('>4sIII', result, 12 + i * 16, tag, original_checksum, len(result), size)
        result.extend(payload)
        result.extend(bytes((-len(result)) % 4))
    if len(result) != expected_size or head is None:
        raise ValueError('Invalid restored font size')
    struct.pack_into('>I', result, head + 8, (0xb1b0afba - checksum(result)) & 0xffffffff)
    if checksum(result) != 0xb1b0afba:
        raise ValueError('Invalid restored font checksum')
    return bytes(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference-web', type=Path,
                        help='Optional approved UI HTML, used only to populate original WOFF sources')
    args = parser.parse_args()
    directory = ROOT / 'assets/fonts'
    sources = directory / 'sources'
    sources.mkdir(parents=True, exist_ok=True)
    if args.reference_web:
        blocks = re.findall(r'@font-face[^}]+}', args.reference_web.read_text(encoding='utf8'))
        encoded = [re.search(r'base64,([A-Za-z0-9+/=]+)', block).group(1) for block in blocks]
        # The first four faces are distinct families. The fifth CSS fallback
        # duplicates the title family with a seal-only subset and is not loaded.
        for (_, filename, _), payload in zip(SPECS, encoded[:4]):
            (sources / (filename + '.woff')).write_bytes(base64.b64decode(payload))
    records = []
    for role, filename, family in SPECS:
        source = sources / (filename + '.woff')
        restored = restore_sfnt(source.read_bytes())
        target = directory / (filename + '.otf')
        target.write_bytes(restored)
        records.append({'role': role, 'family': family, 'file': target.name,
                        'sha256': hashlib.sha256(restored).hexdigest(),
                        'woff_source': 'sources/' + source.name,
                        'woff_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    manifest = {'origin': 'Font subsets embedded in the user-approved UI reference',
                'license': 'SIL Open Font License 1.1; see legal/OFL-1.1.txt',
                'transformation': 'WOFF decompression and sfnt checksum restoration only; font tables and names retained',
                'loading': 'Windows FR_PRIVATE; visible only to this application process',
                'fonts': records}
    (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'fonts': len(records), 'restored_bytes': sum((directory / x['file']).stat().st_size for x in records)}))


if __name__ == '__main__':
    main()
