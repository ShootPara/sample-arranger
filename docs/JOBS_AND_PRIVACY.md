# Jobs, narration and retention

Updated 2026-11-04. Requirements R11-R17; implementation evidence is distinguished from intended lifecycle below.

## Normal job lifecycle

received -> validated -> needs_input (at most once, when needed) -> queued -> planning -> rendering -> checking -> completed. Failure/cancellation are explicit terminal outcomes; interrupted jobs enter recovery review, not presumed success. Some jobs can proceed directly after validation. Clarification and confirmation should be combined into one consolidated interaction when required, rather than asking once for each stage.

Store initial prompt as background and refined prompt as authoritative. Derive effective constraints from the refinement, with application/security invariants retained. Do not reintroduce rejected preferences from the first prompt. A still-invalid refinement produces an actionable error, not repeated confirmation or silent guessing. A user-initiated new revision is not permission for an automatic confirmation loop.

Proposed folder contents: request/brief history, safe effective plan, project state, input references or explicitly managed copies, final result.mp3, manifest, and bounded diagnostics. Intermediates reside in a clearly marked temporary area and are cleaned after success or according to failed-job policy. Persistent folders are outside the source repository and preferably outside synchronized locations. User chooses their location. No automatic deletion of completed normal jobs is assumed.

User deletion removes the job's owned files and associated index references, not shared catalog assets/plugins. Active deletion first cancels/stops work and waits for handles to close. Resolve paths within the jobs root; never follow an arbitrary manifest path or symlink to delete unrelated data. The public repo must not contain prompts, voice recordings, outputs, license keys or private server settings.

Implemented admission uses a pinned-project SHA256 and UUID with a per-request local
lock. `.control/<UUID>.json` contains hashes/state, not raw briefs/audio. Its temporary
project snapshot is removed after completion or inactive recovery. A manifest/MP3
published before owner death can reconcile successfully; a pre-publication death is
interrupted. No automatic regeneration after failure, missing output or changed input.
Normal GUI renders use this shared command. Small duplicate-guard records currently
remain after manual folder deletion. Explicit jobs.delete/jobs.forget controls now
remove reviewed owned outputs/records; empty UUID lock files remain. This must not
be described as full user-data erasure. Temporary normal-result sessions are now
implemented below; full effective privacy/configuration acceptance remains open.
Owned normal scratch recovery is now implemented below; continuous orphan cleanup
remains a separate path. No remote jobs service is needed for the accepted setup.

## Narration workflow

Accept supplied narration from Codex or another authorized source; do not assume a native Codex audio-fetch API. Local CLI accepts a local file. Remote uploads require a separate cloner adaptation with explicit ownership and limits. No transcription, voice synthesis/cloning or singing workflow is implied.

Validate decoded duration, format and channels. Preserve original timing/content by default. Determine placement, lead-in/out, music density and duration. Analyze activity/levels locally; plan sparse music under speech; apply agreed gain automation/ducking; mix; encode MP3 192 kbps; decode/measure final delivery and verify <=240 seconds. Avoid clipping and excessive pumping. Mastering loudness/true-peak targets remain open and should be named presets rather than invented universal values.

If narration exceeds 240 seconds, reject with a clear duration conflict unless the user separately authorizes a supported edit. Do not truncate, remove pauses, denoise, time-stretch or alter speech without the applicable processing policy. Optional cleanup through installed effects must be visible and reversible in project state. Processing may require licenses or an interactive plugin setup.

Normal render checks include sample alignment after plugin latency, duration including tails/encoder delay, actual bitrate/codec, finite samples and output audibility. MP3 padding makes decoded duration policy/tolerance an explicit engineering decision; no result over the agreed maximum is acceptable. Internal WAV/PCM is allowed as an implementation recommendation, not an additional delivered format.

Implemented narration settings are offset_seconds (0–240, rounded to samples),
voice_gain_db (-24–12), music_gain_db (-60–0, default-5.2) and ducking (defaulttrue).
The decoder checks actual44.1kHz stereo samples within the remaining duration plus
one sentinel frame; overlong audio is rejected without speech truncation. MP3
container padding is excluded. Decoded preview bytes remain bounded in memory,
not a retained raw-voice intermediate. Source files are never modified. Ducking
uses the placed/gained voice as its detector. Voice timing is not stretched or
denoised. The optional master effect does process the complete mix, including voice,
and is labeled accordingly. Full speech intelligibility/loudness acceptance is open.

Normal music has a221-sample entrance and882-sample exit fade (shortened for tiny
jobs), before narration is mixed. This suppresses cut edges without fading speech;
it is recorded in the manifest. Plugin tail policy remains independently bounded.
Schema6 projects pin narration content/settings and reopen it with the arrangement.
Changed referenced narration is blocked; selecting a different file explicitly is
replacement intent. A general same-path update-adoption/relink UI remains open.

## Privacy boundaries

Local persistence is configurable; temporary sessions are supported. The owner's job-folder retention requirement applies to normal jobs; continuous mode has separate mandatory deletion semantics. Catalog/preferences can persist independently of jobs. Optional temporary normal jobs must define when the user retrieves the output before deletion.

No automatic telemetry or external AI service. Diagnostics exclude raw prompts, audio, tokens and sensitive plugin state by default. Catalog paths, embeddings, waveforms, prompts and voice are user data even when stored locally. Cloud-synced folders can upload them independently of the application; warn rather than promise locality.

Authorized remote music requests may transmit briefs, voice and results through the chosen service; document transport, owner, access policy and retention. Broker text requests should contain compact musical features rather than narration bytes. The older inference API documents short-lived in-memory results; reconcile current policy, including request retention and operational metadata, before integration.

Plugin activation, updates and content downloads are possible online needs, but not required for the core arrangement logic. Any automatic update check requires a product decision and disclosure. Third-party plugins may create files/logs or contact servers independently; strict app-controlled cleanup cannot guarantee removal of their data, OS paging, crash dumps, backups or external recordings.

Temporary mode removes application-owned files on stop and attempts orphan cleanup after crash. Report cleanup failures accurately. Never claim secure erasure from SSDs or prevention of recording audio output.
# Normal render scratch recovery — implemented 2026-11-04

Normal jobs retain their published folders as before. New normal render/compose/
graph/PCM scratch lives under the chosen jobs root's `.scratch/work-<UUID>/data`.
An exact owner marker and file lock live outside data, allowing atomic publication
while the ownership lock remains held. A subsequent render recovers inactive owned
scratch only. It protects active locks, never treats legacy `.render-*` directories
as owned, refuses redirected/reparse trees and unknown wrapper files, and bounds
recovery inspection to8192 entries/4GiB. Unrecognized or oversized leftovers require
explicit investigation, not broad deletion. This is separate from continuous spools.
Cooperative errors clean immediately. Actual killed-owner tests verify recovery,
active protection and published/foreign content preservation. Recovery does not
auto-regenerate an interrupted job or delete normal completed output.
# Temporary normal-result sessions — implemented 2026-11-04

This is distinct from continuous mode. The desktop offers Temporary result session:
normal MP3 results/states/receipts live in an owned locked session until Clear
temporary results or workspace Close. Results can be played/retrieved while open.
The setting defaults off for each workspace. Existing normal folders, catalogs,
source narration/samples/plugins and explicitly saved projects are independent
and preserved. This is not a promise that every application/OS/plugin cache vanishes.
Each temporary session admits at most8 results/attempts and reserves320MiB for a
new job before a2GiB retained-output bound. Normal render work has its own limits.
Unexpected oversized/redirected leftovers require review, not unbounded deletion.
The active owner lock protects another workspace's temporary session. Subsequent
temporary-session startup/cleanup recovers inactive app-owned crash leftovers.

CLI `jobs.temporary` offers explicit retrieval acknowledgement: render a pinned
project, emit a bounded artifact_ready diagnostic event with local MP3/manifest
paths and checksum, then wait1–3600s (default300) for a caller-owned initially absent
acknowledgement file containing exactly {audio_sha256: reported hash}. The caller
must retrieve before acknowledging; acknowledgement authorizes cleanup, not proof
of a physical copy. Terminal stdout reports acknowledged/canceled/expired and
cleanup state, without a dead audio path. Caller control/ack files are not removed.
Cancellation and expiry clear the temporary job; source projects remain. A killed
owner is recovered by jobs.temporary.cleanup or the next session startup. No cloud
transport, secret or music-job listener is involved. Standard retained jobs.submit
remains the simpler single-result request for clients that manage job folders.

Automated tests exercise real CLI MP3 retrieval, hash acknowledgement, cancellation,
expiry, active protection, actual process crash recovery and allocation checks.
Temporary-result UI controls are implemented but not manually accepted yet.


## Editable workspace recovery (2026-11-04)

Normal workspaces default to configurable local recovery under local app data,
not the repository/sample folders. A draft stores brief/background/refinement,
notes, harmony/locks, clips, paths, narration settings and existing content pins;
it includes no audio, plugin binaries, credentials or rendered result. A two-second
timer persists changed state atomically, up to2MiB/draft,16 retained drafts plus at
most16 interrupted temporary staging files. Full stores report an error rather
than evicting older work. Drafts are separate from explicitly saved project files.
Temporary-result mode disables and clears this workspace's own draft. Continuous
playback never writes generated audio into recovery; automatic writes pause during
active operations. Disabling recovery clears only this workspace's own draft;
earlier drafts remain user-managed. Explicit Restore reviews local draft state;
normal asset content/revision validation still gates Save/render. Recovery is not
secure deletion or protection against OS/provider/plugin caches.


## Portable local copies

Explicit project packaging copies required audio and state assets into a new folder;
it does not copy the sample catalog, plugins/host executables or normal job outputs.
No publication/upload is performed. Portable folders and materialized projects remain
until the user deletes them. Brief/history and opaque plugin state can contain private
paths or vendor data; a portable package is not automatically safe to publish. Opaque
plugin sample libraries/activation are not discovered or copied. Missing external
identities remain recovery issues. Interrupted unpublished copies use the same marked,
live-lock-protected normal scratch recovery; they never become partial accepted folders.
