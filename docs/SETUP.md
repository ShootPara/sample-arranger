# Local setup and adaptation rationale

Optional independent CLI-schema checks: run scripts/setup-schema.ps1 with
Python3.12 x64. It creates/reuses `%LOCALAPPDATA%/SampleArranger/tools/schema-runtime`
and installs exact hash-pinned developer wheels from official PyPI. Packages/versions/
URLs/hashes/license metadata are in SCHEMA_VALIDATION_DEPENDENCIES.json. This is
separate from the UI, package runtime and music/model processes; the app does not
require or bundle it. Schema validation uses local packaged metaschemas, an explicit
non-network reference registry and socket-denial tests. It does not fetch user data
or call a model. Cloners using another Python/platform must deliberately review wheel
locks rather than assume the Windows cp312 binary fits.

Packaging requires the installed audio tools to match FFMPEG_WINDOWS.lock.json.
Those are observed existing Gyan WinGet binaries. Obtain/review a matching official
build or deliberately update the lock with provenance and signal acceptance; no
unknown alternate binary is accepted merely because it is on PATH. Upstream archive
corroboration and redistribution/source/notices remain open. No automatic FFmpeg or
plugin download, security-policy change or paid purchase is performed by this check.

Updated2026-11-04. Tested on Alienware Windows x64. Personal user-space deployment and launchers are delivered through scripts/deploy-local.ps1. Clean-machine acceptance and a signed public installer are not claimed. The app does not need a public
listener, firewall changes, administrator rights or a paid service for local audio.

## Prerequisites and pinned native build

Current measured runtime: Python3.12.10 with Tk, NumPy2.2.5; FFmpeg9.0.2 full build
from the existing Gyan WinGet installation. FFmpeg/ffprobe/ffplay are on local PATH.
Install compatible Python/FFmpeg from their official distributions on a new machine;
review those packages' licenses. The repository does not bundle them or silently
accept installer agreements. `requirements.txt` pins the numerical dependency.
Use a private virtual environment for a clone rather than changing other projects.

Run `./scripts/setup-native.ps1` from PowerShell. It reuses or fetches the official
w64devkit2.11.0 archive, checks its exact SHA256 before extraction, verifies VST3 SDK
v3.8.1_build_84 commit3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96 and its pinned submodules,
applies the documented three-guard Windows aligned-allocation compatibility change,
and builds the host, owned fixture, output sink and process-loopback diagnostic.
GCC16.2.0/CMake4.4.4/Ninja1.13.2 are supplied by that portable archive. Tools/builds
stay under local application data by default. The process PATH is restored afterward.
No global PATH, registry, security/privacy setting or system plugin directory changes.
This script was rerun successfully against the existing installation; a fresh
download/extraction and offline clean-room replay remain acceptance work.

SDK changes are intentional and narrow: MinGW on Windows needs _aligned_malloc/free
instead of its unavailable std::aligned_alloc path. Do not remove the Windows guard
without retesting allocation/free compatibility. No JUCE/Tracktion dependency is
present: direct SDK hosting was selected to use the already pinned permissive SDK
and explicit isolated worker, with more host engineering required.

## Run and verify

Active Qt workspace: run `./scripts/setup-ui.ps1`, then
`./scripts/start-workspace.ps1`. Setup uses a private Python3.12 runtime and hash-pinned
official Windows x64 wheels from requirements-ui-windows.lock. Use that runtime's
Scripts/python.exe for all tests including Qt controls/processes. Entry point:
src/workspace.py. The earlier src/desktop.py Tk prototype remains during migration;
it is not the professional UI acceptance target. Internal accessibility names pass,
but actual Windows screen-reader acceptance remains unverified.

From the checkout: `python -B src/desktop.py` or
`python -B src/commands.py --request request.json`. The latter accepts stdin if the
file argument is omitted. Use the capabilities request in CLI_AND_BROKER.md to
discover actual commands. `python -B -m unittest discover -s tests` runs local
regressions; native tests require the build and are explicitly skipped otherwise.
Native editor fixture tests briefly create their own window and close it themselves.

Manual Windows audio-engine measurement: `python -B tests/measure_loopback.py`.
It opens only a process-filtered WASAPI capture for its own synthetic player. No
microphone/other-process output is captured, PCM is temporary and deleted. It tests
the endpoint engine path, not speakers/room acoustics. Windows build20348+ is required;
failure prints the actual HRESULT, with no fallback to broad audio capture.

`python -B tests/soak_device.py --minutes 120` runs the controlled persistent-effect
device soak. It copies owned binaries to temporary storage so later builds cannot
change the running test, produces quiet synthetic audio and prints noncontent health
counters. It is not an inference-contention or continuous MIDI-instrument test.

Keep catalog databases, projects, normal job folders and plugin state under a private
user-controlled directory outside this repository. Reference library originals;
do not commit user's audio, proprietary plugin binaries, model weights or secrets.
Continuous sessions use owned locked disposable spools and have no export route.

## For another owner's coding agent

Local-only is deliberate: this owner has no present need for remote music requests.
Do not infer that the inference broker accepts audio/music jobs. CLI contracts are
the adaptation seam if another clone needs a remote service; add authentication,
uploads, ownership and bounded playback acknowledgments explicitly before exposing
anything. Filesystem paths here are host-local, not cross-machine identifiers.

Live music-app inference is disabled pending its own authorized identity. Never copy
coding-worker credentials, connect directly to Ollama, enable cloud fallback, change
the selected model or widen network access during setup. The actual broker envelope
is small:4096 context/1024 output, conservative UTF-8 input accounting. Keep retrieval,
notes/audio/VST processing and semantic validation local; don't send whole libraries.

Normal MP3 jobs and disposable continuous sessions have different retention. A clone
must preserve that distinction rather than adding an automatic continuous recording.
Projects currently pin referenced sources/processing assets; copying/relinking a
project with all its dependencies remains a separate portability workflow.

Maintain REQUIREMENTS, ACCEPTANCE_LEDGER, command capabilities, tests, dependency
pins and rationale together whenever behavior changes. Preserve rejected historical
evidence. Do not turn a partial fixture result into a general compatibility claim.

Native plugin inspection/editor/render/continuous children default to a2GiB owned
Windows job commit limit. Set ARRANGER_PLUGIN_MEMORY_MIB to128–8192 for a local
plugin's needs. The budget covers that child's helpers too. Allocation failure is
an actionable render/setup failure, never silent bypass. This does not change OS
security/privacy policy and is not a plugin sandbox. A safe native256MiB allocation
probe succeeds without the limit and is rejected inside a128MiB owned job. Global
concurrent-job and whole-app budgets still require acceptance; the old long soak
predates this cap and is not evidence for its effect on all plugins.

App-owned per-user lock files now permit one offline render, one disposable session,
one plugin inspector and one plugin editor concurrently across CLI processes. Nested
steps reuse their slot. Busy work fails before durable render admission and can be
retried with the same request ID. OS releases locks on owner exit. These are local
backpressure limits, not a remote authorization boundary or a strict aggregate RAM
guarantee. Existing old running processes do not acquire newly added locks retroactively.
# Adding user-owned plugins

Obtain Windows x64 VST3 instruments/effects from their legitimate vendors and inspect
their license/content/activation requirements individually. This application does
not accept agreements, supply keys or redistribute downloaded instruments for you.
For a vendor-provided portable bundle, preserve the entire `.vst3` bundle/resources
in a user-chosen folder (a per-user folder avoids needing a global installation).
Some vendors require their own installer, licensed libraries or system locations;
follow their supported instructions instead of moving individual DLLs. The host can
load a selected compatible bundle by path; VST2/32-bit/ARM-only formats are unsupported.

In Plugin library, scan that installed folder, inspect the discovered components and
assign an instrument to Bass/Chords/Melody or an effect to the master. Main bus0 is
the library dialog default; explicit assignment/routing handles other supported
offline outputs. A scan reports inventory, not full compatibility. Failed bundles
remain quarantined until reviewed retry; do not bypass activation/safety prompts.
Native editors are optional where generic exposed parameters suffice. Plugins remain
capable of their own filesystem/network/cache behavior; process isolation is not a
filesystem sandbox or a guarantee about a third-party plugin's data retention.
