"""Start with the bundled isolated interpreter; never install anything."""
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def main():
    if sys.version_info[:2] != (3, 13) or struct.calcsize('P') != 8:
        print('请通过“影之刃零支线存档修改器.exe”使用随包的 Python 3.13（64 位）运行环境。')
        return 1
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from desktop_ui import main as run
        AESGCM.generate_key(128)
    except ImportError as exc:
        print(f'运行依赖不完整：{exc}。请重新解压完整运行包。')
        return 1
    run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
