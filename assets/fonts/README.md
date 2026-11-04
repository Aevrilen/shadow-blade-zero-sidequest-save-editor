These Noto CJK font subsets come from the approved UI reference. The original
WOFF sources are retained in `sources/`; desktop `.otf` files restore the same
font tables and names without changing glyphs. Rebuild with the bundled Python:

    runtime/python.exe -I -B tools/build_desktop_fonts.py

The fonts are loaded with Windows `FR_PRIVATE` for the desktop application
process, removed at exit, and never installed into Windows Fonts or exposed to
the user's game. Family names, source/output checksums and provenance are in
`manifest.json`. Copyright notices and SIL OFL 1.1 are in `legal/OFL-1.1.txt`.
