# Private Windows packaging and reproducibility

Observed2026-11-04 on Alienware. This is a private development bundle, not publication,
an installer, a signed release, clean-machine acceptance or license clearance.

## Build and execution seam

Run scripts/package.ps1. It creates/reuses an isolated package-runtime environment,
installs hash-pinned Windows wheels, builds the pinned native targets and writes a
new unique packages/build-UUID directory under local application data. The source
checkout and normal UI runtime/settings are preserved. Generated files stay outside
the repository. PyInstaller work/cache paths are confined to that owned build.

The onedir product contains `Sample Arranger.exe` and `arranger-cli.exe` with a shared
private runtime. Keeping the console companion is deliberate: the windowed executable
cannot reliably provide JSON stdout/stderr. runtime.module_command routes catalog
workers through that allowlisted companion instead of trying to run .py files with
a frozen GUI executable. No arbitrary-module/shell execution route is introduced.
Onedir also avoids repeated one-file extraction and makes component/notices review
more practical. Native worker/sink are included; user plugins, catalog, projects,
settings, weights and credentials are not. Built-in sound code needs no soundfont.

Existing FFmpeg9.0.2/ffprobe/ffplay binaries are included only for private execution
testing. This full Gyan build makes the current folder about826MB. A focused audio
build/installer-size decision and exact corresponding-source/notice review are still
required before distribution. The bundle's PRIVATE-DEVELOPMENT.txt states that gate.
The app does not call optional speech/model/network features compiled into FFmpeg.

Packaging now checks exact FFmpeg/FFprobe/FFplay SHA256, size and version lines
against FFMPEG_WINDOWS.lock.json before execution/copy. This pins the observed
existing WinGet Gyan build; it is not an upstream archive attestation or completed
rights review. A changed installed tool fails rather than silently changing render
results. A deliberate upgrade requires a reviewed lock/provenance and signal tests.
The build manifest also fingerprints this lock and the dependency metadata JSON.

Optional schema development tools live in a separate schema-runtime and are not
application/PyInstaller runtime dependencies. See requirements-schema-windows.lock,
SCHEMA_VALIDATION_DEPENDENCIES.json and scripts/setup-schema.ps1. Official PyPI wheel
hashes were checked before installing; no optional format extras are selected.

Packaging PATH contains only the selected interpreter directory and Windows system
directories. Native/FFmpeg inputs are explicit resolved paths. Dependency analysis
is checked against pinned package/Python/native inputs and selected FFmpeg binaries;
an unexpected external binary rejects the build. This protects reproducibility, not
the operating system from arbitrary plugins. No OS security/privacy setting changes.

## Pinned tools and licenses

PyInstaller6.22.3 and its resolved build dependencies are pinned with SHA256 in
requirements-package-windows.lock and provenance in PACKAGING_DEPENDENCIES.json.
Each wheel matched official PyPI release metadata. PyInstaller's GPL exception permits
bundling under an application's chosen license subject to dependency obligations;
it does not waive Qt/FFmpeg/Python/NumPy or asset terms. See the
[publisher's license](https://pyinstaller.org/en/v6.22.3/license.html).
Contrib2026.9's inspected wheel license distinguishes GPL2-or-later build hooks and
Apache2 runtime hooks. No PyInstaller source modifications or commercial key were used.
Qt binding metadata offers LGPL3/GPL2/GPL3 alternatives; exact modules, Microsoft
runtimes, notices and source/relink obligations remain a distribution review. See
[Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html).

Build manifests record current Git commit/dirty status, source hashes, component
versions and packaged-file hashes/sizes. They exclude user settings/audio/credentials.
Build procedures are pinned; byte-for-byte reproducibility has not been established.

## Observed acceptance and rejected build

First build8c019a8c passed CLI/audio smoke but failed GUI QtCore loading. Its inherited
tool PATH supplied an unrelated Poppler ICU78 DLL whose versioned exports did not
match Qt's Windows ICU imports. It remains rejected GUI evidence. Dependency-input
validation rejects that analysis too. No Microsoft runtime/OS installation or policy
change was needed; the controlled PATH fixed discovery.

Buildf384b6bc has217 files/826,352,885bytes and passes tests/check_package.py with only
Windows system PATH, fresh application data and a non-source working directory.
It scans/reads fixture metadata, compiles a score, saves a project, renders through
the bundled native worker and a legally usable owned mono instrument, verifies
44100 decoded stereo frames/nonzero audio/two state files, reconciles a repeated
job and cancels real disposable playback without retained WAVs. No capture occurs.

The actual packaged GUI compiled a2s sparse95BPM Eb-minor request without bass,
rendered through jobs.submit, exposed its Windows accessibility tree, accepted a
velocity edit through the accessible table and rendered that49 value. Evidence is
private under evidence/packaged-workspace-render.jpg and
packaged-workspace-accessibility.txt. This is not full screen-reader, scaling,
high-contrast, vendor-plugin, installer or clean-Windows-machine acceptance.
