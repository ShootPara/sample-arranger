# AI-enabled sample arranger

A Windows application for local sample arrangement, deterministic MIDI composition,
VST3 instruments/effects, narration mixing and disposable continuous playback.
Normal output is stereo 44.1 kHz MP3 at 192 kbps CBR, at most 240 decoded seconds.

The complete intended app remains in development. The
[acceptance ledger](docs/ACCEPTANCE_LEDGER.md) distinguishes working cases, partial
features, untested behavior and external blockers. Tests and controlled plugin
fixtures do not establish musical quality or universal plugin compatibility.
VST3, the desktop, CLI, narration and continuous mode are all part of the intended
app; they are not deferred release options.

## Start using it

Read the [delivery record](docs/DELIVERY.md), [quick start](docs/QUICKSTART.md) and [known issues](docs/KNOWN_ISSUES.md).
Personal Windows deployment uses `scripts/deploy-local.ps1 -Package <built folder>`
and creates Desktop/Start menu launchers without elevation. Public binary
redistribution and clean-machine acceptance remain separate from source publication.

## Run the desktop

Use the pinned, per-user setup and launch scripts described in [SETUP](docs/SETUP.md):

```powershell
& ./scripts/setup-ui.ps1
& ./scripts/setup-native.ps1
& ./scripts/start-workspace.ps1
```

The Qt workspace is the current interface: library and auditions at left, editable
sample/note timeline and musical form centrally, project/plugin/instrument/continuous/
result controls at right. `src/desktop.py` is an older Tk development surface, not
the professional workspace acceptance target. Existing source files and settings
are preserved; do not infer parity from the legacy entry point.

Connect an existing catalog or add a sample folder. Use metadata-only discovery for
mounted libraries to avoid decoding every source. Inspect filename, embedded and
measured tempo evidence separately; choose half/double-time explicitly. Build a brief,
review/edit the plan, assign installed VST3 components if desired, then Render MP3.
Generic parameters and state capture support plugins without a usable native editor.
Plugin inventory/quarantine is distinct from validator/editor/routing acceptance.

## CLI and coding-platform requests

Desktop work and automation share `src/commands.py`. Requests are bounded UTF-8 JSON
with exactly contract, operation and arguments. stdout is one JSON result/error;
stderr carries bounded diagnostics/events. Discover the implemented operations:

```json
{"contract":1,"operation":"capabilities","arguments":{}}
```

Submit a request through the pinned UI runtime:

```powershell
$arrangerPython = "$env:LOCALAPPDATA/SampleArranger/tools/ui-runtime/Scripts/python.exe"
& $arrangerPython -B ./src/commands.py --request ./request.json
```

For a minimal generated music job, use compose.render with intent and an existing
private jobs folder. For retry reconciliation, save a project and use jobs.submit
with a canonical request UUID and pinned project SHA256. A lost response does not
authorize duplicate rendering. The [CLI contract](docs/CLI_AND_BROKER.md) documents
project edits/revisions, catalog/tempo operations, plugin state/presets/registry,
offline graphs, narration, result deletion and temporary retrieval acknowledgement.

## Persistence and privacy

Normal jobs remain in user-controlled folders. Reviewed deletion checks owned
content and never follows source-asset references. Temporary normal-result sessions
clear their owned results on Close or explicit acknowledgement/expiry; catalogs,
source audio and explicitly saved projects remain independent. Continuous mode is
different: it generates evolving bar-aligned chunks, maintains persistent musical/
plugin state, uses bounded ahead/device buffers, discards consumed audio and exposes
no save/export result. See [retention](docs/JOBS_AND_PRIVACY.md) and
[continuous behavior/evidence](docs/CONTINUOUS_MODE.md).

There is no music-job network listener, telemetry implementation, cloud AI fallback
or bundled model credential. Actual app inference remains separately gated. Compact
planning/schema/transport fixtures run locally; they do not call Trifecta. Do not
reuse coding secrets, bypass the broker or change its selected model/settings.
Mounted storage, third-party plugins, OS caches and any later AI provider have their
own behavior; this app cannot promise forensic erasure or universal nonretention.

## Setup, evidence and distribution

Private frozen GUI/CLI bundles are assembled from version/hash-pinned inputs; see
[PACKAGING](docs/PACKAGING.md). Byte reproducibility, clean-machine/installer,
complete source/notice obligations and broader acceptance remain open. App source
is AGPLv3; dependency, instrument, style, soundfont, sample and other asset terms
remain separate. No user samples/plugins, outputs, narration, weights or secrets
belong in the repository. The owner approved sanitized source publication to ShootPara/sample-arranger; private history and public binary distribution remain separate.

Run the regression suite with the pinned UI runtime:

```powershell
& $arrangerPython -B -m unittest discover -s ./tests
```

Opt-in device/loopback/soak scripts use app-generated signals and record exact
binaries and limitations. Historical failed evidence remains in
[EVIDENCE](docs/EVIDENCE.md); do not replace it with a later success.

## Living documentation

Read [REQUIREMENTS](docs/REQUIREMENTS.md), [ARCHITECTURE](docs/ARCHITECTURE.md),
[CATALOG_AND_MUSIC](docs/CATALOG_AND_MUSIC.md),
[PLUGIN_COMPATIBILITY](docs/PLUGIN_COMPATIBILITY.md),
[UI_AND_ACCEPTANCE](docs/UI_AND_ACCEPTANCE.md) and
[DECISIONS_AND_MAINTENANCE](docs/DECISIONS_AND_MAINTENANCE.md).
Update rationale, contracts, dependency provenance, acceptance evidence and open
work alongside changes. Cloning agents must understand why boundaries exist before
adapting transport, resources, storage or licensing. Research candidates and their
individual practical/license assessments are in
[PLUGINS_AND_LICENSING](docs/PLUGINS_AND_LICENSING.md) and
[THIRD_PARTY](docs/THIRD_PARTY.md); they are not all dependencies.
