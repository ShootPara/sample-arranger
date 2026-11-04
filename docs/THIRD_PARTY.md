# Code, assets and distribution rights inventory

Updated2026-11-04. Application source is under AGPLv3 (LICENSE, official GNU text).
The app is not published. This inventory is incomplete distribution due diligence,
not a declaration that every possible dependency/plugin/asset is compatible.

Development-only independent schema validator (installed2026-11-04 in private
tools/schema-runtime): jsonschema4.26.0, attrs26.1.0,
jsonschema-specifications2025.9.1, referencing0.37.0, rpds-py2026.9.1 report MIT;
typing-extensions4.15.0 reports PSF-2.0. These are official PyPI metadata observations,
with exact selected wheel hashes/URLs in SCHEMA_VALIDATION_DEPENDENCIES.json and the
requirements-schema lock. No optional format extras, recurring fee or application
runtime/bundled dependency is introduced. Metadata is not a complete transitive
binary/source distribution audit. [Validator documentation](https://python-jsonschema.readthedocs.io/en/stable/validate/)
describes Draft2020-12 checking; app-specific music/identity checks remain separate.

| Material | Current use / terms / distribution status |
|---|---|
| App Python/C++/owned fixtures | App source, AGPLv3. Owned synthetic test signals and additive palette use no third-party recordings, styles or presets. Generated palette audio has no additional asset restriction imposed by this app. User content remains subject to its own rights. |
| App icon | App-authored SVG waveform/play mark, same project license; private packaging renders PNG/ICO without third-party art/font assets. |
| VST3 SDK3.8.1_build_84 | MIT SDK pinned externally; no SDK source/binaries vendored here. Preserve SDK/license notices if packaged. Steinberg trademarks are separate. |
| w64devkit2.11.0 | External build tooling: GCC16.2.0, CMake4.4.4, Ninja1.13.2 and MinGW components each have their own licenses/runtime exceptions. Archive/license files remain in private tools; no archive redistributed in repository. |
| Python3.12.10/Tk | Existing runtime, PSF/Tcl/Tk terms; inspect exact bundled runtime notices before packaging. |
| NumPy2.2.5 | BSD-family project code, numerical wheel dependencies have separate notices. Installed locally, version pinned. Review exact wheel licenses if bundled. |
| PySide6-Essentials6.12.0/shiboken6.12.0 | Private Qt UI runtime, official Windows wheel hashes pinned. Binding metadata LGPL3/GPL2/GPL3 alternatives; Qt module notices/relink/source obligations need distribution review. No paid key/subscription. |
| FFmpeg9.0.2 Gyan full build | Existing separate executable, configured --enable-gpl and --enable-version3 with many optional libraries. Do not relabel LGPL or redistribute without matching build/source/notices/dependency review. App currently calls local executables. |
| SDK mda examples | External development reference/instrument fixture built privately; not a chosen built-in palette or redistributed app asset. Review their exact license before packaging any part. |
| iZotope RX10 | User-installed proprietary effects; not redistributed. De-click bypass validator failure remains recorded. Activation/license dialogs are user setup, never autoaccepted. |
| Soundloops/Google Drive library | Private user input; unknown per-pack redistribution rights. Referenced locally, not bundled or committed. |
| MAGIX/Vita | Backup leads, not current verified plugin/content licenses. Native metadata verification awaits actual packs. No redistribution assumption. |
| Model/runtime/weights | No model weights bundled; app identity/transport live use gated. Weight/runtime licenses differ from app source and from provider retention. |
| PyInstaller6.22.3/build dependencies | Free private build tools, hash-pinned official wheels. GPL exception for generated bundles; contrib GPL build hooks/Apache runtime hooks; other resolved licenses recorded in PACKAGING_DEPENDENCIES.json. Dependency obligations remain separate. See PACKAGING.md. |

Tonal, Scribbletune, music21, JJazzLab, MMA, FluidSynth, sfizz, Surge, JUCE, Tracktion
and Carla were individually researched in PLUGINS_AND_LICENSING.md. They are not
all dependencies and are not installed/bundled by this implementation. Cost-free
download is not permission to redistribute code, soundfonts, styles or sample packs.

Before public distribution: inspect exact runtime/transitive notices, decide
source-offer/binary distribution obligations, review assets/presets/weights separately
and sanitize private operational paths/Drive references. Public-repo intent still
does not authorize push/publication. No recurring paid service is required here.

Private local packaging tests include existing FFmpeg executables and Qt/Python/
NumPy runtimes. This is not redistribution clearance. No user VST3 binaries, sample
packs, soundfonts, narration, jobs or model weights were included in the bundle.
