# Redistribution notices

The application's source and the reused PBZ Editor source retain the root MIT
license. This does not change the separate licenses of bundled dependencies,
fonts or the Python runtime.

- `runtime/LICENSE.txt` is retained from the official CPython embeddable package.
  It contains the Python license and notices for incorporated components.
- The native desktop runtime additionally bundles Tkinter and Tcl/Tk 8.6.15
  from the matching CPython 3.13.15 Windows x64 distribution. Tcl and Tk retain
  their own terms in `tcl-8.6.15.license.terms` and
  `tk-8.6.15.license.terms`; the original Tk script-tree notice is also retained.
  Its zlib1.dll dependency is version 1.3.1 from the same signed CPython
  distribution, with the corresponding upstream text in `zlib-1.3.1.LICENSE`.
- Python package license texts remain in `vendor/*dist-info/licenses/`.
- The existing cryptography binary reports `OpenSSL 4.0.3 29 Sep 2026`.
  The corresponding official Apache 2.0 license is retained in
  `openssl-4.0.3/LICENSE.txt`. That upstream tag has no separate `NOTICE.md`.
- `native/` below this directory retains the license texts supplied by all 21
  registry packages in `native/Cargo.lock`, including proc-macro/build inputs.
  Packages offering a choice of licenses retain the texts supplied in their
  published package; `wide` supplies its Zlib license text.
- The decoder DLL contains Rust compiler source revision
  `58cf8f9c35b355199727627d07ae34a4e2846d67`. The MIT, Apache 2.0 and COPYRIGHT
  texts from that revision are retained in the corresponding `native/rust-*`
  directory.
- oozextract 0.5.7 declares `MIT` in its published Cargo manifest. Its source
  package does not supply a separate LICENSE file. The original declaration,
  source and attribution are retained in `../native/vendor/oozextract/` and
  `../native/vendor/NOTICE.md`; no copyright holder or missing license wording
  has been invented. This is a documented upstream licensing boundary for
  anyone preparing a public release.
- Embedded UI font notices and the SIL OFL 1.1 text are in `OFL-1.1.txt`.
  The desktop application retains the approved WOFF subset sources under
  `assets/fonts/sources/` and restores their original OpenType tables for
  process-private loading. No fonts are installed into the operating system.
  `assets/fonts/manifest.json` identifies the original family names and hashes.

`upstream-license-index.json` identifies the license sources, source archive
checksums and retained paths. Registry packages were checked against their
checksums in Cargo.lock before extracting their notice files. No dependency
was installed by this collection process.

No game archives, game executable, proprietary Oodle DLL, user saves, account
data or runtime caches are part of this distribution. Runtime-generated game
metadata stays in the user's local tool directory and is not covered by the
application's MIT grant.
