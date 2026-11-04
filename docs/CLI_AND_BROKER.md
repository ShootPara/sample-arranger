# CLI implementation and intended broker contract

Current AI status: dedicated app enrollment and actual model-plan-to-MP3 verification now pass. See AI_SETUP.md; earlier approval/channel-gap entries below are historical and superseded.

Updated 2026-11-04. Full intended contract below. The executable local JSON interface is src/commands.py; invoke capabilities for its supported operations/arguments. Earlier proposed families are not all implemented. No network listener is installed. See E07/E08, supervisor evidence and the no-live-server-access restriction.

## Executable local requests

`score.locks.set` takes score and indices, replacing the exact-note lock set.
`project.notes.lock` takes project, indices and expected_revision and atomically
persists the same operation. Locks store exact event identities, so removing an
unrelated earlier array entry does not move a lock to the wrong note. score.edit
and project.notes.edit reject changing/removing a locked event. Replacing a saved
score cannot erase locks or retime protected events: explicitly unlock first, or
project.save may carry released_note_indices against its expected saved revision.
Only those explicitly released saved locks are relaxed; other locks remain required.
The desktop toggle supplies those release indices after an explicit unlock action.
Whole-plan rebuild is blocked while notes are protected; it does not silently unlock.
These are note locks, not completed section/harmony/rhythm lock contracts.

`score.harmony.edit` accepts score and1–16 changes `{bar,degree}` (zero-based bar,
diatonic degree1–7); `project.harmony.edit` additionally takes project and
expected_revision. It deterministically revoices selected bars, retaining event
rhythm/velocity and all other bars. Common-tone protected events remain exact;
conflicting locks, crossing-boundary notes and unsupported >3-voice manual chord
textures fail atomically. This edits major/natural-minor diatonic intentions, not
audio harmony or arbitrary jazz/chromatic voicings. Canonical harmonic rows are
validated against key/degree/register/span. Native-instrument/built-in render subsets
keep only relevant note-lock metadata; the full canonical score/locks remain intact.
Desktop Harmony table and chord lane use this same operation, with musical Undo/Redo.

Run `python -B src/commands.py --request request.json`, or provide UTF-8 JSON on stdin.
The byte cap is256000; stdout is one JSON result/error, diagnostics use stderr. Contract1
requires exactly contract, operation and arguments; unknown arguments are rejected.
Example discovery: `{"contract":1,"operation":"capabilities","arguments":{}}`.
Example score: `{"contract":1,"operation":"score.compile","arguments":{"intent":{"bpm":120,"bars":8,"mode":"major","root":0}}}`.
Compose/render adds a local jobs directory to the same intention via compose.render.
arrangement.render accepts catalog, sections and jobs plus the optional fields returned
by capabilities. Paths are local, not remote uploads or shell commands. Failures use
exit2 and a stable broad category: INVALID_REQUEST_OR_STATE, BUSY, TIMEOUT,
ASSET_MISSING, ACCESS_DENIED, CATALOG_ERROR, WORKER_FAILED, LOCAL_IO_ERROR or
CANCELED. Categories use exception types/actual cancellation markers, not filename
string matching; finer state/asset/plugin categories remain open. Durable admission
is implemented below. A lost direct-render response
does not prove no job exists.

### Durable pinned-project jobs

`jobs.submit` requires jobs, canonical request_id UUID, project and project_sha256.
Optional voice requires voice_sha256 too. Hashes are lowercase SHA256. The core
reads a bounded private project snapshot and renders to job-<request_id>. The Qt
Render control uses this operation. Normal direct render commands remain available,
but callers needing retry reconciliation should use admission rather than assume
those direct commands are idempotent. No inference/network call is involved.

Same ID plus identical canonical paths/hashes returns the checked completed manifest
without another render, including after the original temporary project disappears.
Changed payload is a conflict. An active lock returns already-running; `jobs.status`
returns active/state/job. A process exit after atomic publication is reconciled from
the manifest's admission identity and audio checksum. Exit before publication becomes
interrupted and never auto-renders. Failed/canceled/interrupted requests need review
before a new request ID is submitted. UUIDs are correlation/admission IDs, not access
credentials. Authentication and remote enrollment are not implied.

Small local .control records contain request hashes/status and keep the duplicate
guard after manual audio deletion; they do not contain raw requests/audio. Temporary
project snapshots are removed on completion or inactive-status reconciliation.
Automatic record expiry, aggregate admission bounds, finer semantic error codes and
full per-node/frame progress remain unfinished. Explicit receipt forgetting/deletion
and Results UI exist; see JOBS_AND_PRIVACY.md for retained metadata limitations. Owned normal scratch recovery
is implemented separately; it never deletes retained results.
The request byte cap still applies. Terminal result manifests remain in owned job
folders; missing/changed results fail instead of silently regenerating.

`contracts.schema` returns a Draft2020-12 structural JSON Schema for every registered
operation, or one selected by optional operation. Required/optional keys come from
the actual command allowlist; unsupported argument keys are forbidden. Path roots
are strings for scans while catalog.rank's musical root is an integer. Nested music,
source/state identity, UTF-8 bytes, plugin capabilities and cross-field constraints
still require runtime validation; schema validity is not musical acceptance. Tests
check schema/registry parity and exact field types. Independent jsonschema4.26.0
Draft2020-12 checks now pass for the whole registry and every individual operation,
plus representative valid and nested invalid requests under a no-network registry
and denied sockets. These are development tests, not a runtime dependency or complete
nested musical schema coverage. No schema URI is fetched by the app.

Optional `--events` emits schema1 JSON objects on stderr, alongside the existing
command_ready/child_started diagnostics. Each JSON event is wrapped in event with
kind started/stage/completed/failed; stages currently include graph validation,
source preparation, graph processing, audio rendering, output measurement and
publication. Event content excludes briefs, file paths, raw audio and model content;
no telemetry store/network is involved. stdout remains exactly one terminal JSON.
Qt enables events and displays readable stages. A publishing event means publication
is being attempted, not proof of success: reconcile the terminal result/jobs.status.

Capabilities includes effective configured command-tree/default-plugin memory bytes
and explicitly states no shared cap across concurrent commands. Startup aggregate
budget is ARRANGER_COMMAND_MEMORY_MIB (512–16384, default8192); each command and its
admitted child hierarchy shares this Windows job allowance. Existing
ARRANGER_PLUGIN_MEMORY_MIB (128–8192, default2048) remains a nested plugin-tree cap.
Set startup configuration before launch; it does not change running commands or OS
policy. Invalid startup budget yields one typed JSON failure before child execution,
not a traceback. Separate render/continuous/editor/inspect trees still need overall
resource admission/workload acceptance; this is not an8GiB total-app/PC guarantee.

The desktop brief and arrangement rendering use this dispatcher. Standalone legacy
CLIs remain usable. Native editors are optional interactive commands; plugins.edit
opens the isolated HWND surface and publishes a new app-owned preset folder only
after successful close/state capture. This format is not advertised as .vstpreset.

## Two distinct contracts

TrifectaBroker schedules text/structured inference. It is not documented to accept audio, render music, install plugins or run arbitrary commands. The music app owns composition/rendering, assets and job folders. The owner selected local-only music deployment; remote music service work is a cloner adaptation, not an unresolved owner requirement.

Do not expose raw inference/admin endpoints, reuse coding credentials automatically, bypass TLS, change firewall scope or infer that an authorized coding client is authorized for music uploads. Enroll clients with separate least-privilege identities. Authorization must cover job submission, read, refinement, deletion, uploads and streaming independently. File paths on one PC are not paths on another.

## Discoverable operation families

| Family | Operations |
|---|---|
| capabilities/schema | Supported contract revision, limits, operation schemas, plugin/render compatibility |
| catalog | Import, search/page, inspect, correct, rescan, resolve missing locations |
| plugins | List/scan, inspect exposed parameters, presets, compatibility, missing content |
| jobs | Validate, submit, inspect, events, refine, cancel, retrieve artifacts, delete |
| projects | Read revision, edit bounded changes, set locks, reopen |
| render | Compose, render existing project, mix narration, freeze internal track audio |
| continuous | Start, status, stop, playback transport/acknowledgment |
| privacy | Effective retention, cache inventory and permitted cleanup |

All meaningful app actions use the shared command layer. Native plugin editors are interactive surfaces; CLI can control exposed parameters and stored presets, but cannot guarantee automation of proprietary editor-only functions. Such requirements return setup-needed status rather than simulated clicks.

## Request envelope (field design)

Fields: contract revision; client request UUID/idempotency key; operation; initial brief; optional authoritative refined brief; typed hard constraints; library scope; project ID/expected revision; sample/plugin/preset IDs; narration upload asset ID; duration seconds; output policy; retention policy; resource deadline. Validate before allocating expensive work.

Normal implemented output is stereo44.1kHz MP3 192kbps CBR and <=240 decoded seconds. Reject unsupported format requests instead of silently substituting. Example requests use synthetic paths and assets. Current strict contract1 is discoverable through capabilities; the richer field design below is still a requirement, not implemented idempotency or remote admission.

A refined brief supersedes the initial brief for intent. Explicit security limits and application invariants remain binding. Clarification presents the effective typed plan once so contradictory structured constraints can be resolved. No hidden merge with superseded preferences. If the refinement is still impossible, fail with actionable reasons; do not loop through confirmations or invent authorization.

## Transport and outputs

Local CLI: JSON file/stdin input, JSON stdout, diagnostic stderr, stable exit codes, bounded event streams. Proposed exit categories: success, invalid request, unauthorized, needs input, unavailable/deadline, render failure. Assign exact numeric codes when freezing the contract.

Accepted deployment is local-only on this PC. No remote music-job listener exists or is required for the owner's setup. A future cloner adding remote transport must add authenticated encrypted service, bounded asset uploads and opaque IDs; local filesystem-path requests are not a safe remote protocol. This adaptation must not inherit coding credentials.

Results: job ID/revision/state, MP3 artifact metadata, duration, checksum, actual codec/bitrate, measured levels, warnings and safe provenance. Local clients receive paths; remote clients receive authenticated artifact handles. Never embed audio in model JSON or publish a result URL without access control. Publish final outputs atomically after successful checks.

## Idempotency and failure semantics

Same key + same canonical request returns the existing job; same key + changed payload is conflict. Retain admission records for a documented bounded period consistent with job deletion. Project edits require expected revision. A lost response does not justify a duplicate render.

Broker inference is a subordinate operation. E07 says old client_request_id is not idempotency; E04 advertises keyed admission. Obtain current schema before using that feature. Preserve keys through retries; never bypass broker quarantine or recovery. Admission retry is distinct from generation repair. Application cancellation must report when already-running inference cannot be canceled under the negotiated contract.

Running jobs expose stage/progress/queue/deadline, not fabricated percentages. Errors distinguish malformed request, forbidden access, source unavailable, plugin setup needed, broker busy/quarantined, context exceeded, stale revision, insufficient disk/memory and render failure. Noninteractive clients receive machine-readable NEEDS_INPUT once where permitted. No infinite retry, invisible dialog or silent effect bypass.

## Continuous transport

Current local continuous.play arguments are discoverable through capabilities. It
accepts built-in music or a catalog sample, tempo, bounded chunk count, app-owned native playback
and optional effect/component/preset. It blocks for the session and emits noncontent
health JSON on stderr; the final result contains counters/retention state, never an
audio path. Health uses a bounded queue and nonblocking pipe writes where supported;
events may be dropped rather than stall audio. Final counters are authoritative.
The desktop sends cancellation through its owned marker. CLI callers may provide
`--cancel-file <caller-owned-control-folder>/cancel`; create that initially absent
file to stop. Do not point it at a library asset. The caller owns/removes its control
file. Example disposable request:
`{"contract":1,"operation":"continuous.play","arguments":{"builtin":true,"bpm":128}}`.
No continuous save/download operation exists.

`plugins.preset.import` takes worker/plugin/preset/presets; it validates a bounded
version1 .vstpreset and writes a new app bundle, preserving opaque Comp/Cont streams.
`plugins.preset.export` takes worker/plugin/state/destination and optional class_id;
it refuses an existing destination and publishes atomically after SDK validation.
Program-only presets and broad third-party interoperability remain unaccepted.
`plugins.inspect` optionally restores a state/component before reporting actual
controller values. This avoids presenting factory defaults as loaded preset values.

Schema4 projects layer sequential sample sections and an accepted score. Their
durations must match within one sample; part assignments and master effects remain
available. Mixing happens from PCM before the single MP3 encoding pass. Supplied
narration is mixed after the sample/score ensemble, before the optional master effect.
`assets.waveform` accepts path and returns <=256 stereo min/max bins from <=30s at
8kHz, source duration and stat identity. It writes no cache/audio; the Qt preview
keeps at most32 waveform summaries in memory. Longer sources show only the analyzed
window. Tempo matching remains an explicit clip choice, including half/double time.

`catalog.metadata` takes catalog/path for a previously scanned source. It records
bounded RIFF/ACID observations and duration-consistency warnings without decoding
audio or overwriting filename/audio/correction evidence. `catalog.correct` records
UTC time/source stat identity and correction history; search distinguishes verified
current correction from retained legacy/changed-source observations.

Normal composed projects can assign bass/chords/melody to individual VST3 components
through `instruments`: part -> {plugin, class_id, optional state, optional outputs}.
Outputs explicitly list zero-based bus/gain pairs for multi-output instruments.
Schema3 projects pin plugin, component and controller hashes and preserve accepted
notes. Unassigned parts use the app-owned palette. CLI and Qt render through the
same project command. Changed worker/plugin/state identities now block pinned
rendering until explicitly reviewed/adopted, superseding the old worker warning.

Continuous built-in planning accepts assignments for all three composed parts.
Only main bus0 is currently available in continuous mode, with explicit finite
gain from-4 to4; full sidechain/multi-output continuous routing remains unfinished.
ARV1 bounded native packets carry at most512 frames and256 events, <=128 active
voices, paired note IDs and off-before-on scheduling. Instrument and optional
effect processes persist across chunks; PCM mix is aligned to the instrument's
reported latency (<=2s). No notes, plugin snapshots or audio result are saved.

Playback occurs on this PC in the accepted local deployment. A cloner adding remote
continuous transport must introduce bounded stream buffers, sequence numbers,
receiver acknowledgments and disconnect/timeout policy. Delivery is not proof audio
was heard. No completed MP3 artifact/download route exists for continuous mode.

`project.relink` requires project, expected_revision and replacements mapping
zero-based section indices (decimal strings) to selected local paths. Replacement
bytes/SHA256 must match the original content; a different recording is rejected.
It updates all references to that same original asset, records location history and
increments the revision atomically. Schema5 binds sources directly to the saved
asset identities, so a relocated project can render without its old catalog.
Schema5 may contain samples alone or samples plus score/instrument assignments.
Older project schemas retain their existing catalog cross-check behavior.

`project.save` optionally accepts source_assets: sample alias -> {path, bytes,
sha256}. It verifies these bindings before accepting edits, preventing a changed
file from being silently repinned during a desktop snapshot. The GUI preserves
loaded sample bindings, opens missing projects for recovery, and offers relink for
the selected saved sample. Content replacement and portable audio-copy export
remain unfinished. Processing updates now have explicit review/adopt operations.

Narration-enabled render operations accept voice_settings: offset_seconds,
voice_gain_db, music_gain_db and ducking. project.save accepts voice/voice_settings
and optional voice_asset {path, bytes, sha256} to preserve a loaded reference when
making a snapshot. Schema6 contains narration identity/settings plus samples and/or
accepted score/instruments. project.render restores narration automatically; an
explicit supplied voice/settings override is still a local user-selected action.
jobs.submit optionally accepts voice_settings and includes explicit overrides in
its canonical payload; omitted settings preserve existing admission-key behavior.
jobs.status now separates historical completion from artifact_available, so deleted
or modified completed audio does not produce a usable job path or silent rerender.
# Generic plugin state capture (implemented 2026-11-04)

`plugins.state.save` takes the same arguments as `plugins.edit`: worker, plugin,
class_id, presets; optional state and parameters. It saves actual component and,
when supplied by the plugin, controller state without opening an editor. Parameters
are at most128 writable normalized ID/value pairs. Unknown/read-only IDs fail;
failed captures publish no preset. This is available in the desktop as Save parameter
state and Instrument parameters. `plugins.inspect` now accepts class_id without a
state, isolating inspection to one selected component. No plugin is downloaded.
# Explicit processing identity review and voice measurement

`project.processing.review` takes project and returns revision plus changed/missing
processing identities. `project.processing.adopt` takes project, expected_revision
and updates: selector -> reviewed current SHA256. It rejects missing content,
unreviewed/changed hashes and stale revisions, updates only selected hashes, and
keeps dated history. It does not certify binary safety/compatibility. Native plugin
agreements and activation remain separate. `project.save` accepts expected_processing
and expected_instruments bindings; the desktop preserves loaded pins in render
snapshots. Save to an existing project also checks its prior identities. Selecting
a different file remains explicit replacement intent; changing bytes at the same
path requires review. `narration.inspect` takes voice, seconds, optional voice_settings
and returns bounded decoded-frame placement/source stat identity without retaining
PCM. Desktop Check voice placement uses this shared operation.
# Compact planning fixtures and note edits

`planning.prepare` accepts musical_state and candidates, optional context/output_limit;
it returns a bounded prompt, inline output_schema, revision/state hash and retrieved
IDs. musical_state contains revision/seconds/effective brief, optional tempo/key/
previous chord/required asset IDs/accepted-state hash. Candidate local filenames stay
host-side; only IDs and compact musical features reach the proposed model request.
Up to100 host candidates reduce to<=24; required IDs and hard state are never silently
truncated. Oversized hard state fails before transport. `planning.validate` takes the
same fields plus an untrusted structured response and returns locally resolved clip
names/explicit tempo choices only after duration, key, IDs and revision checks.
Neither command calls AI or a network. They enable fixtures/adaptation while actual
app inference credentials remain gated. This boundary currently proposes sequential
clips, not a complete multi-track AI arranger. Required asset inclusion is not yet a
general timing/harmony/section lock implementation.

The injected orchestration function allows one semantic repair, budget permitting;
timeout/busy/unavailable/failed/truncated responses never trigger raw/cloud fallback
or unbounded retries. The caller still owns transport deadlines/admission and must
increment canonical revision when effective context changes. `score.edit` takes
score/changes; `project.notes.edit` takes project/changes/expected_revision. Changes
are ordered set(index,field,value), add(note), remove(index) objects with action.

# Retained results and explicit deletion

`jobs.list` takes jobs and optional limit1–100. It returns bounded summaries and
review hashes, not briefs or raw narration. New jobs carry a complete owned-file/
directory inventory. `jobs.delete` takes jobs, canonical job_id and
expected_manifest_sha256; optional forget_receipt defaultsfalse. It locks the
admission, checks exact reviewed manifest/content, rejects redirected trees,
unknown files/directories and changed artifacts before deleting anything, and
never follows original sample/plugin/voice/project reference paths. Older jobs
without ownership inventories require manual folder review/removal. Current
deletion is a local owner operation, not a remote authenticated API.

`jobs.forget` takes jobs/request_id/request_sha256 and refuses active requests or
an existing retained folder. It removes the hash/status record and stale request
snapshot. Empty UUID-named lock files remain for cross-process locking correctness;
this is not a guarantee of forensic erasure or zero retained filesystem metadata.
Explicit forgetting removes duplicate protection; no automatic regeneration occurs.
The Results inspector implements refresh/play/open-folder and one deletion dialog,
with an optional receipt checkbox. New Results controls await manual acceptance;
automated tests delete only generated fixtures, never the owner's existing jobs.
# Installed plugin registry

`plugins.scan` takes registry, worker and a user-selected installed-plugin root.
`plugins.list` takes registry and optional limit/offset. `plugins.retry` takes registry,
worker, plugin and expected_sha256, and only retries a registered quarantined binary.
These commands never download/install software or accept vendor agreements. Cached
inventory is not a validator pass. SDK inspection remains isolated/bounded30s per
bundle; the caller can cancel. Discovery is bounded, and unchanged quarantine cannot
be cleared by ordinary scan. The desktop Plugin library dialog uses the same commands
for scan/list/retry and component assignment. No public/remote registry service exists.
# Verified command cancellation

On Windows the command process emits `command_ready <PID> <creation FILETIME>` on
diagnostic stderr before request execution. stdout remains one JSON result. The
desktop opens that exact kernel process object, verifies creation identity and
keeps its handle until completion. Cancel first sets the cooperative marker; after
6s it may terminate the verified command object and its Qt launcher. The command's
owned job releases descendants. This avoids killing a reused PID. It is lifecycle
coordination, not a credential or a plugin sandbox. Closing the window keeps the
event loop responsive while stopping work, then closes automatically after cleanup.
Startup before the identity handshake remains a separate bootstrap limitation;
do not claim arbitrary pre-startup helper containment from the running-job test.

`continuous.cleanup` takes no arguments, inspects only the app-owned continuous
root and reports removed chunks, protected active sessions, inactive bytes and
inspection limits. Forced-stop UI runs this check before claiming inactive audio
cleared. Unknown ownership/redirected roots are not broadly deleted. Cleanup/status
caps1000 session wrappers and16 chunks per wrapper; unexpected larger leftovers
need explicit investigation. A normal forced render may leave recoverable owned
scratch and an interrupted receipt; no partial result is automatically published.
# Temporary normal-result CLI workflow

`jobs.temporary` requires project/project_sha256/ack_file; optional timeout_seconds
is1–3600 (default300), starting after artifact_ready. The pinned project may include
narration/instruments/effects. Read JSON diagnostic events from stderr while stdout
is pending; command_ready/child_started lifecycle lines are distinct diagnostics.
Retrieve audio/manifest from the artifact_ready event, verify its audio_sha256, then
atomically publish {"audio_sha256":"the reported hash"} at the initially absent
caller-owned ack_file. The terminal JSON result confirms acknowledged/expired/
canceled cleanup; it never claims an expired path is usable. Do not acknowledge
before retrieval. Caller files stay caller-controlled. No external service runs.
`jobs.temporary.cleanup` takes no arguments and recovers only inactive owned temporary
normal sessions. This is separate from continuous.cleanup and from normal retained
jobs.delete. Configurable GUI temporary results use the same owned session manager.
# Decoded output measurements

`audio.inspect` takes path and returns bounded decoded duration, sample peak/RMS,
true peak, integrated R128 loudness when available, tool version and limitations.
Normal jobs run the same check before publication, reject nonfinite/overlong or
wrong-length delivery and store measurements in their manifest. Silence is reported
as a warning, not invented audibility; intentional mute remains representable.
No normalization or alternative deliverable format is implied. Short/below-gate
content can have no integrated LUFS; less-than3s content has no accepted LRA value.

App-owned FFmpeg/ffprobe/ffplay inputs now allow filesystem/pipe protocols only.
This prevents implicit URL media retrieval; it does not change OS settings or
constrain mounted storage providers or third-party plugin network behavior.
# Saved routing projects (schema7)

`catalog.rank` accepts catalog plus optional term/BPM/role/root/mode/limit,
excluded_roles and allow_unknown_key. It scores all uniquely named stored entries
(hard100000-row budget) before checking the best100 for current stat identity and
returning at most100 (default24). Duplicate names remain excluded from filename
resolution; unavailable/stale best matches are omitted with an explicit availability
window warning. User stat-pinned correction, duration-consistent embedded ACID,
high-confidence heuristic analysis and filename hints have separate provenance.
Conflicting otherwise-consistent embedded/filename BPM is not auto-preferred.
Role/key are filename hints, not audio classifiers. A key lock rejects unknown or
different pitched keys unless allow_unknown_key explicitly relaxes unknowns;
percussion is key-independent. No transpose or half/double interpretation is applied.
Returned catalog_observation preserves original evidence; compact metadata omits
the full RIFF chunk inventory available through catalog.metadata. Brief sample
planning now uses this ranking instead of an alphabetically truncated256-row pool.
`planning_candidates` is a separate planning.prepare/validate-ready list: normalized
role (FX maps to texture), known tempo/key and bounded per-property provenance.
It does not invent numeric confidence. Filenames remain host-side; prepare sends
IDs/features/provenance only. Unknown pitched keys fail a requested key lock unless
musical_state.allow_unknown_key is explicitly true; percussion remains independent.
IDs currently identify catalog paths, not content hashes. Revalidate host-side source
identity and create pinned project assets before accepting/rendering a proposal;
do not treat a filename-based proposal as a durable asset snapshot.

`project.graph.save` accepts `project`, `graph`, `sources`, `worker`, `seconds`;
optional `expected_revision` (0 for new), `tempo`, `tail_seconds`, `brief`, `voice`,
`voice_settings`. It preserves the explicit graph.render DAG: main/sidechain buses,
mixers, multiple outputs and gains. It pins worker, source audio, plugin bundle,
component/controller state, MIDI and automation file SHA256 identities. Inline
`automation_points:[{frame,id,value}]` may replace an automation file on a plugin
node: at most8192 ordered points, one value per parameter/frame, normalized0..1.
Frame positions use44.1kHz; the native worker validates exposed parameter IDs.
Sources may also be `{ "silence": true }` for instruments. An accepted `score`
may be saved with the graph; its exact frames and BPM must match project timing.
A plugin node's `score_part` (`bass`, `chords`, `melody`) replaces an external
`notes` file. Deterministic native event rows are generated only in owned scratch.
Empty accepted parts are valid silent MIDI tracks; the explicit MIDI argument
identifies the instrument even when no note is scheduled. No fabricated notes.
File sources optionally carry offset_seconds and the complete source_bpm,
target_bpm, beat_scale group. Offset is inside logical duration; target equals the
project tempo when set; beat_scale is explicitly0.5/1/2 and resulting atempo speed
must be0.5–2. Original source and hints are preserved. Parallel audio sources share
the graph clock; the source inspector exposes placement, repetition and reviewed
tempo. There is no automatic transposition, beat-grid correction or harmonic lock
in this source decoder. Two-frequency regression proves pitch-preserving stretch,
independent placement and exact logical duration through MP3 delivery.

`project.inspect`, `project.render`, `jobs.submit/status`, processing review/adopt
and normal job deletion/temporary delivery work with schema7. Durable admission
hashes the saved revision, so graph changes require a new request UUID. Processing
overrides on graph rendering are rejected: save a reviewed revision instead.
`project.graph.relink` accepts project, expected_revision and replacements mapping
source names to identical-content local paths. Missing or changed inputs block
publication. Processing adoption records explicit reviewed hashes; it cannot
adopt changed source/narration content. Select replacement content in a saved
revision/new project. Plugin-internal sample libraries/licensing/opaque references
remain unverified. Schema1–6 are preserved; their save operation cannot flatten7.



## Explicit catalog content lifecycle (2026-11-04)

`catalog.hash {catalog,path}` streams SHA256 up to512MiB and checks scanned stat
before/after. `catalog.duplicates {catalog,limit?,offset?}` returns at most100 hash
groups and16 paths/group, with truncation flags. Only hash observations matching
catalog stat participate; this query does not freshly verify mounted audio.
`catalog.relocate {catalog,path,replacement,expected_sha256}` freshly hashes the
replacement, requires identical pinned content and an unindexed replacement path,
and updates the catalog only. Projects remain pinned independently. Valid current
observations migrate; stale corrections remain historical and are never blessed.
`catalog.forget {catalog,path,expected_sha256}` removes the indexed row/current
observations, never the source file; correction/location audit history remains.
All operations use the shared strict request registry/schema. These are local-only
operations; no filesystem mutation of sample sources or automatic dedup deletion.


`catalog.annotate {catalog,path,expected_sha256,role?,root?,mode?,clear?}` verifies
actual content again, then stores a dated user assertion separately from filename
hints. Root/mode must be complete; role may be drum/bass/chords/melody/fx/unknown.
Omitted valid properties persist. `clear:true` is exclusive and retains history.
Changed scanned stat invalidates active corrections. Relocation of identical content
migrates valid musical assertions; their original history is retained.

`catalog.rank` emits content-derived IDs for explicitly hashed current observations,
deduplicates aliases and attaches the full hash to host-side planning candidates.
The compact model prompt omits full hashes, filenames and paths. Unhashed IDs remain
provisional. `planning.resolve {catalog,musical_state,candidates,response,context?,
output_limit?}` performs existing bounded musical validation and fresh source hashing;
its returned `sections/source_assets` feed `project.save`. Missing hashes or changed
content fail; ordinary planning.validate alone is not content acceptance.

`arrangement.ensemble {catalog,seconds,bpm?,root?,mode?,roles?,role_terms?,
excluded_roles?,allow_unverified_harmony?}` returns a proposed graph/sources, fresh
source_assets, decisions, warnings and missing roles. Default percussion+one pitched
layer is conservative, not a chord-progression guarantee. Multiple pitched roles
require explicit unverified-harmony choice; no half/double-time choice or transpose
is automatic. `project.graph.save` accepts optional source_assets preconditions and
checks them before and after constructing canonical pins. User-added unbound sources
are separately pinned during Save; supplied expectations cannot be silently changed.


`plugins.parameter.convert {worker,plugin,class_id,parameter_id,state?,display?,
normalized?}` requires exactly one displayed string or normalized number. UTF16
text fits127 units; normalized numbers are finite0..1. An isolated controller restores
optional component/available controller state and uses its native conversion API;
result includes normalized/display/plain/units/steps/flags and `state_changed:false`.
Apply the result through state capture/automation separately. No plugin code enters
the GUI. Inspection now reports bounded program lists (128 lists,65536programs/list,
64 names total, explicit truncation) and program-selector mappings via unit IDs.
Large unnamed lists remain accessible by explicit zero-based index. This is an
inspection snapshot, not support for live list-change notifications or all vendors.


Continuous output selection uses effect_output_bus0..7 (requires an effect for
nonzero values); each continuous instrument currently accepts one selected output
with gain. Unselected native outputs are discarded in memory. Simultaneous multi-bus
DAG mixing remains open. Public continuous.play no longer accepts a sink override;
app-owned playback has no save/export/destination operation. Development harness
injection is internal only. Returned processing_policy records latency, one-second
per-stage declared-tail caps and finite completion padding; cancel remains immediate.


## Portable project folders

- project.bundle.export {project,destination}: a new folder containing package.json
  and only referenced copied assets. No plugins, native host, catalog or normal job
  outputs are copied. Limits:64 references/files,512MiB/file,1GiB total,4MB descriptor.
- project.bundle.inspect {package}: compact manifest hash, counts and required external
  identities; it does not emit the full project/brief into the response.
- project.bundle.match {package,expected_manifest_sha256,available_assets?}: candidates
  are worker/plugin arrays of up to32 explicit local paths each. Hash matching runs
  in the command process, not the UI; it neither loads plugins nor installs anything.
- project.bundle.import {package,destination,expected_manifest_sha256,bindings?}:
  destination is a new directory. Explicit selector-to-path bindings must exactly
  match external pins. Unbound externals become missing recovery requirements. The
  result gives project_path, normal project inspection, readiness and copied count.

The project descriptor/content are validated before publication. Import rejects
path escapes, extra unmapped files, changed manifest/asset content and malformed
processing. Copying is streamed and cancellation checked between blocks and before
publication. Dead marked copy scratch is recovered on the next operation in that
parent; active locks protect concurrent work. Normal imported projects and portable
folders are retained user-controlled data. Continuous mode cannot be packaged.

Qt provides Package saved project/Open portable project in Project and Package
project in Routing. Unsaved edits require Save first. Exact known host/plugin paths
can be matched without an installer; unresolved externals open in recovery. Routing
has explicit host selection and module/bundle location controls retaining the saved
component ID; new paths are pinned on Save, and render still validates state/layout.


## Bounded injected inference and stale-context guards, 2026-11-04

`inference_session.py` adds an internal normalized, injected port with no network,
endpoint, credentials or enabled service. It applies conservative UTF-8 budgets,
one canonical admission UUID/receipt, no blind retry after uncertain admission,
240-second logical/two-generation bounds and explicit queued/running cancellation
uncertainty. A future authorized adapter must map the real wire contract and honor
call deadlines; synchronous Python callbacks cannot be forcibly interrupted here.
This is fixture-tested orchestration, not evidence of live app inference.

`planning.current` validates revision and compact-state SHA before applying delayed
responses. Desktop sample/ensemble proposals refuse to replace newer edits; render
completion identifies an older rendered snapshot while allowing its preview. Five
normalized-port fixtures cover capacity, timeout/cancel races, truncated/invalid
results, stale revision and one bounded semantic repair. Two Qt tests cover delayed
planning and render snapshot races. Full suite156 ran98.559s, two optional schema
tests skipped; private suite-injected-inference-context.log. No server calls.


## Compact MIDI phrases and editable melody rhythm, 2026-11-04

midi.planning.prepare/validate/current accept musical_state with revision, brief,
intent and optional protected_notes (at most32 exact phrase events). Explicit
bpm/root/mode are required. Phrases are at most four bars; the canonical song and
boundary state stay outside each request. Hard intent values cannot be overwritten.
The model proposes a degree progression, density and one-bar relative triad/rest
pattern, not MIDI bytes, paths or code. Local compilation owns pitches/voicing,
register, note-offs, duration and locks. Over-budget hard context fails rather than
being truncated. Optional injected-port orchestration allows one semantic repair;
no network adapter or app credentials are supplied. Stale state must pass current
before application. Phrase/section assembly and broader style acceptance remain.

melody_pattern cells contain tone(-1 rest,0..2 voiced triad index), ticks(multiple
of120), velocity(rest0, notes1..121). One to16 cells total3840 ticks, at most eight
sounding notes per bar. Optional compile support preserves previous default output.
score.pattern.apply {score,bars,pattern} replaces melody only in explicit zero-based
bars, refusing crossing boundary/changed locked events. Other parts and bars remain
unchanged. Melody rhythm in the workspace supplies keyboard-accessible tone/beat/
velocity controls, bar range, validation and shared-command Apply with Undo/Redo.
Accepted event notes remain authoritative after edits; stored patterns are provenance.
Continuous built-in planning carries the pattern across compact bar/voicing state.


## Explicit composed-score protections, 2026-11-04

score.musical.locks.set {score,selections} replaces up to512 explicit selections
{bar,kind,part}. Bars are zero-based. Section/harmony require part=all; rhythm may
select all/bass/chords/melody. Section pins exact intersecting notes, harmonic
intention and form membership. Harmony pins accepted key/degree/voicing, allowing
rhythmic changes. Rhythm pins intersecting note timings/counts by part, allowing
pitch/velocity changes. All pin the accepted clock/bar endpoint. These protect
composed scores, not sampled audio harmony, waveforms or library sections.

Validated content fingerprints are immutable within an edit. Atomic saved-project
replacement also compares prior lock records: dropping or recomputing a protection
cannot silently unlock it. project.save and project.graph.save support explicit
released_musical_locks selections against the saved revision. Other locks survive.
Normal workspace Protect music provides bar/part scopes and explicit selected
unlock; its release intentions persist in recovery drafts. Whole-plan replacement
refuses protected score content. Undo/Redo preserve score lock metadata. Internal
render subsets remove these metadata only from copies after canonical validation,
so assigning a protected part to VST3 does not invalidate its dry palette subset.

Broader audio section locks, model-context compaction of these projections and a
routing-dialog lock editor remain unfinished. Existing exact note locks are separate.


## Configured AI adapter, 2026-11-04 owner authorization

Owner authorization now covers enabling app AI and accessing resources needed for
that connection. AI_SETUP.md supersedes older approval-hold wording. ai.status,
ai.connection.check, ai.score.plan and ai.samples.plan are shared operations;
Windows DPAPI stores only the dedicated app credential outside source/projects.
BrokerPort maps the documented normal v1 jobs envelope, owned polling/cancellation,
instance identity, bounded verified TLS and authenticated-denial/no-retry semantics.
It never invokes coding keyed routes, chooses a model or falls back to a provider.
Live enrollment remains an actual execution-channel gap, not a permission question.
