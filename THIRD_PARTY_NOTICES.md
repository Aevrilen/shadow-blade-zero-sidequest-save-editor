# Third-party components

## This side-quest editor delivery (2026-11-04)

This application reuses PBZ Editor commit
`5fdb13483cefde94e6a2f3dba3d258c84e747582` (MIT). The original notice below is
retained. This portable delivery bundles the official CPython 3.13.15 x64
Windows embeddable distribution, including its `runtime/LICENSE.txt` notices.
The archive source/checksum and the local relative-path configuration are
recorded in `runtime/runtime-origin.json`. It does not bundle Qt/PySide6 or
texture2ddecoder, and does not use an installed Python interpreter.

The native desktop uses CPython's same-version `_tkinter` module and Tcl/Tk
8.6.15 scripts/DLLs, plus their zlib 1.3.1 dependency, copied from the existing
official CPython 3.13.15 Windows x64 distribution. Relative component hashes
and provenance are in `runtime/tk-origin.json`; Tcl/Tk/zlib terms and upstream
source records are retained under `legal/`. No system Tk installation is used.

The native GUI executable's source is retained in `launcher/launcher.c` under the
application's MIT license. It calls Windows system APIs and does not link the
MSVC C runtime or require .NET. Existing build tools are needed only to rebuild
that executable; no compiler or installer is redistributed or run at startup.

The `vendor/` directory contains the existing cryptography 50.0.2, cffi 2.1.1
and pycparser 3.12 packages, with their installed `*.dist-info/licenses/`
texts retained as originally supplied. Additional OpenSSL 4.0.3 terms are in
`legal/openssl-4.0.3/`; native dependency and Rust notices are in `legal/native/`.
See `legal/upstream-license-index.json` for the source and checksum records and
`legal/REDISTRIBUTION.md` for component-specific redistribution notes, including
oozextract's upstream MIT declaration and absence of a separate upstream license
file. No package installation is performed at startup.

The open decoder DLL and its checksum manifest are retained in `native/`,
alongside the original Rust source, Cargo manifests and upstream oozextract
0.5.7 source/notice. No proprietary game DLL or encoder is included.

The approved UI reference supplies Noto Sans CJK SC and Noto Serif CJK SC
subsets. Original WOFF sources and losslessly reconstructed OpenType files are
retained in `assets/fonts/`, with a reproducible reconstruction tool. Their
copyright notices and SIL Open Font License 1.1 are retained in
`legal/OFL-1.1.txt`. Font rights are separate from the application's MIT license.
The native desktop loads these fonts for its process only, without installing
fonts or loading resources from the network.

---

## Original PBZ Editor notice

The following retained text describes the upstream project's components and
historical release process. Paths such as `LICENSES/`, `LICENSES/native` and
`release-manifest.json` refer to those upstream releases, not this package.
This package's actual license locations and component scope are described above;
in particular, its native license collection is `legal/native/`.

PBZ Editor's own source is distributed under the MIT license in `LICENSE`.
Game data remains the property of its respective authors. This repository does
not distribute game archives, images, personal saves or proprietary Oodle DLLs.

The Windows application uses these separately licensed components:

| Component | Upstream | License information |
|---|---|---|
| Python | https://www.python.org/ | Python Software Foundation license and bundled notices |
| PySide6, Shiboken and Qt | https://www.qt.io/qt-for-python | The installed package metadata lists LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; Qt modules also carry their own notices |
| cryptography | https://github.com/pyca/cryptography | Apache-2.0 OR BSD-3-Clause; wheels include additional OpenSSL/Rust dependency notices |
| cffi | https://cffi.readthedocs.io/ | Installed package license metadata and included license text |
| pycparser | https://github.com/eliben/pycparser | BSD-3-Clause |
| texture2ddecoder | https://github.com/K0lb3/texture2ddecoder | MIT; bundled BCn decoder derives from Perfare/AssetStudio under MIT |
| PyInstaller, build tool | https://pyinstaller.org/ | GPL with the upstream bootloader exception; its own license text is retained |

The release builder copies the license and notice files found in installed
package metadata into `LICENSES/` and records the actual package versions in
`release-manifest.json`. Read those texts for the exact terms of the components
you distribute. Qt's upstream source and license texts are available from
https://code.qt.io/ and https://code.qt.io/cgit/pyside/pyside-setup.git/tree/LICENSES.
The standard LGPL-3.0 and GPL-3.0 texts in `legal/` were obtained from Qt for
Python's official upstream `pyside/pyside-setup` repository:
https://github.com/pyside/pyside-setup/tree/dev/LICENSES;
the release builder retains them alongside the package-provided notices.

The default decoder is oozextract 0.5.7, declared MIT by its upstream
https://github.com/lvlvllvlvllvlvl/oozextract. Its published source is retained
in native/vendor/oozextract with the local dependency-only change documented
in native/vendor/NOTICE.md. Rust dependency licenses and standard-library
notices are included in LICENSES/native in the runtime archive.
The separately compiled pbz_codec.dll uses that decoder and a bounded C ABI.
Writes use standard Oodle uncompressed stored blocks; no proprietary encoder
or decoder DLL is shipped or required. An explicit external-library setting
remains available for compatibility and independent verification.

Item thumbnails are read from each user's installed game into the user-local icons cache.
They remain game assets and are excluded from source distributions and clean
release archives. The narrow Zen texture parser was independently implemented
with the public CUE4Parse format structures as documentation; no CUE4Parse code
or game image is bundled.
