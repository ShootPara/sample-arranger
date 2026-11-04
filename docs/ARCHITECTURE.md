# Application architecture and remaining design work

Updated 2026-11-04. Intended complete architecture for [R01-R18](REQUIREMENTS.md). Current implementation/evidence is tracked in ACCEPTANCE_LEDGER.md. Python owns orchestration/SQLite and the Qt workspace; the older Tk surface remains during migration. The app-owned C++ host uses the pinned MIT VST3 SDK directly. JUCE/Tracktion remain evaluated alternatives, not installed dependencies.

## Shared core

Current routing persistence is schema7 in graph_project.py, sharing the exact
offline graph decoder/DAG with graph.render. Source files, worker, plugin bundle,
external MIDI/automation and paired states are content-pinned. Inline lanes and
accepted score parts live in canonical project JSON. Source preparation and MP3
publication validate the saved asset snapshot. Schema1–6 remain supported. Qt's
separate routing workspace edits this model through the shared dispatcher and
durable jobs.submit. It is an offline graph editor: continuous processing still
uses three compensated persistent instruments and an effect, not arbitrary DAGs.

Retrieval ranks the whole eligible stored catalog before keeping a compact
shortlist; current availability checks are bounded to the best100. Role/key hints
stay distinct from measurement/correction/embedded evidence. This is retrieval
infrastructure, not an audio-harmony detector. Parallel placement/tempo matching
is explicit; conservative reviewable percussion+one-pitched-layer graph proposals now work with fresh content pins. Rich harmonic/energy/transition planning remains unfinished.
The registry generates structural schemas, broad errors and local stderr stages;
runtime musical/content/lifecycle checks remain authoritative. See the ledger and
IMPLEMENTATION_QUEUE.md for the entire remaining app, not just this graph path.

Owned command process trees now share an aggregate Windows-job memory cap:8GiB
default, configurable at startup via ARRANGER_COMMAND_MEMORY_MIB512–16384. This
includes the command and its explicitly admitted children, layered with individual
plugin/worker-tree caps (default2GiB). Actual512MiB group test allows a300MiB child
allocation and denies a second despite each child's1GiB allowance. This is local
resource management, not OS security policy or a sandbox. Separate concurrent command
trees do not yet share one combined PC-wide memory cap; activity locks alone do not
prove aggregate hardware fit. Capabilities reports that limitation explicitly.

Desktop UI and CLI call one typed command layer. A music-job controller owns persistent job state, revisions, authorization, cancellation and output publication. An inference adapter calls the existing TrifectaBroker; an audio engine owns timing and rendering. Do not turn the inference broker into a file store or expose its credential to every UI/browser.

| Component | Responsibility |
|---|---|
| Catalog | SQLite candidate; asset identity, location, observations, corrections, tags, search indexes |
| Import/analysis workers | Hashing, metadata adapters, waveforms, beat/harmony estimates; resumable resource-bounded jobs |
| Planner | Brief interpretation, sample/preset retrieval, form, harmonic plan, MIDI intentions |
| Realization/validation | Typed plan to exact clip/note placement, constraints, transitions and duration |
| Audio engine | Sample playback, MIDI scheduling, buses, fades, gain, latency compensation |
| VST3 workers | Discovery, process isolation, instrument/effect rendering, state/editor lifecycle |
| Local job controller | Pinned UUID/hash requests, per-request/engine locks, result reconciliation, cancellation and resource backpressure; remote uploads/service are a separate cloner adaptation |
| Narration mixer | Placement, activity analysis, agreed processing and music ducking |
| Continuous controller | Bounded lookahead, persistent musical state, playback acknowledgments and eviction |
| Artifact manager | Per-job folders, safe deletion, MP3 encoding and atomic completion manifests |

Audio deadlines must never wait for inference, SQLite queries, filesystem scans or UI rendering. Background preparation and bounded buffers feed the implemented app-owned SDK host/device path. JUCE/Tracktion were research alternatives, not current dependencies. AGPLv3 direction is accepted; distribution notices and broader plugin acceptance remain open.

## Accepted deployment and adaptation boundary

The owner chose this one Windows PC for the application. UI, CLI, catalog, audio, plugins, projects and playback therefore use a local process boundary. No music-job network listener, remote filesystem, audio upload service or public reverse proxy is needed. This avoids unnecessary enrollment, content transfer and plugin-license migration. Repository cloners can adapt transport, but must introduce their own authenticated asset ownership, upload bounds, deployment and licensing decisions rather than infer authorization from local CLI behavior.

The existing broker is an optional inference dependency, not an audio renderer or music-job service. App identity remains separately gated. The app implements local musical compilation and injectable transport fixtures while that gate is open; this task must not access live Trifecta or reuse coding credentials.

## Local model strategy

The supervisor's read-only2026-11-04 01:59–02:00UTC evidence establishes Ollama0.40.3, configured qwen3.5:4b4.2B Q4_K_M, broker context512–4096 and output1–1024, thinking off. It is a dated observation, not a performance guarantee or app authorization. Respect the server-selected model/provider; never send model overrides or fall back to raw Ollama on overload.

Use short typed requests: interpret intent; choose among retrieved candidates; propose section roles; propose a bounded phrase or revision. Model outputs cannot execute commands, load arbitrary plugins, run SQL or mutate projects directly. Catalog metadata and uploaded text are untrusted data, not model instructions.

Canonical state: brief revisions, hard constraints, tempo/meter, harmonic timeline, sections, motifs, asset IDs, accepted notes/clips, locks, current project revision, unresolved issues. Retrieve one role/section plus neighboring boundaries. Never send the entire catalog, full conversation or raw narration by default. Structured schemas and host validation are mandatory; one bounded repair may precede deterministic fallback or explicit failure. No silent musical constraint relaxation.

Use the measured conservative broker admission formula: UTF-8 input bytes +256 +12 per message + output limit <= context. At4096/1024 with one message, only2804 input bytes remain, including system/prompt text. The earlier illustrative token allocation is superseded. Schema is Draft2020-12, <=16000bytes/16levels, without $ref/$dynamicRef. Retrieve fewer candidates or split tasks before submission; never truncate hard constraints. A minute of audio is not a minute-long model request. Truncated structured results and HTTP200 terminal failures must fail local validation.

Historical coding accuracy does not establish musical quality. Evaluate intent, candidate selection, lock preservation and compact note intentions separately. Keep duration arithmetic, bar alignment and render compilation deterministic. Respect broker queue/backpressure/quarantine; no automatic admin recovery or model unloading by the music app.

## Network flows

Local CLI/Qt -> shared command core: brief and user-selected local assets. Core -> optional separately authorized inference broker: minimal text/structured features only. Core -> isolated installed plugins: local audio/events/state. Normal outputs stay in per-job folders; continuous device audio is disposable. Optional plugin/update downloads are explicit setup operations, not a runtime necessity.

Any public reverse proxy can introduce third-party traffic handling; its use requires a documented choice. Existing public Trifecta workspace does not establish authorization for audio uploads. No telemetry, hosted AI, CDN dependency or automatic cloud fallback is proposed.


## Portable-project rationale and adaptation boundary

project_bundle.py uses a separate portable-folder descriptor, not a new render
format. Its asset paths are confined relative names; normal schema1–7 projects are
materialized with explicit absolute paths anchored to a newly selected folder. This
avoids silently reinterpreting relative paths against a coding platform's working
directory. Moving the portable folder is supported; moving an already materialized
project requires reimport/relink. A cloner adding relative normal-project paths must
anchor them to the project file and validate containment across every renderer,
plugin state reader and content pin, rather than change only the UI.

Only referenced audio, notes/automation and component/available controller files
are copied. Plugin/worker binaries remain external hash identities; exact known
local candidates can be matched by a bounded child command. Missing bindings keep
the imported project in recovery, without download, activation or silent replacement.
A new Windows directory is published by same-volume rename after validation; an
existing destination is never overwritten. Do not infer cross-platform rename
semantics from this Windows implementation. Owned locked normal scratch handles
copy exceptions, cancellation and later recovery of dead marked copies; active and
unrecognized directories remain protected. Opaque vendor library paths/activation
are not portable, and raw state/history/brief may still contain private content.
This is a local project copy, not repository publication or asset rights clearance.
