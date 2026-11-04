# Disposable continuous playback

Updated 2026-11-04. R16 is part of the full intended app. Current narrow evidence and remaining gates are distinguished below; this is not a general performance promise.

At2026-11-04 09:49–09:50UTC the actual mda three-instrument/effect/device soak
completed120chunks in7201.719s (controller7201.157s). Peak observed spool32800752bytes
was below the88000000-byte logical cap; per-chunk admission cap22000000bytes.
Native process peak working sets were11.30/9.31/9.31/9.13/12.87MB; Python peak36.64MB.
All five recorded native PIDs exited. Subsequent owned spool status reported zero
active/inactive sessions and zero inactive audio bytes, no limited/unverified scan.
Private evidence: evidence/mda-ensemble-soak-120min.jsonl (122validJSON lines) and
matching stderr; copied host5f0da1c0…/mda fingerprint2ff8e475… are recorded in each
progress sample. This used evolving A-minor plans, JX10bass0.15 and DX10chords/melody
0.12, owned delay effect and actual Windows waveOut. No recording or export occurred.
It did not capture device output or prove physical/acoustic gaplessness; process-only
synthetic WASAPI loopback evidence remains separate. Newer app binaries/graph routing,
arbitrary vendors, full topology/model contention/device removal still need acceptance.
Failed historical soaks/probes are retained below/in EVIDENCE.md, not replaced by this pass.

## Required behavior

Generate successive roughly one-minute musical chunks, append/play continuously, delete audio already heard, offer no save option. Do not create a retained normal-job folder, downloadable finished song, rewind archive or hidden full-session recording. This is separate from the <=240-second normal MP3 workflow.

Interpretation to confirm: a chunk is approximately one minute but can align to musical bars. At 128 BPM, 32 bars of 4/4 are 60 seconds; many other tempi need a slightly different chunk duration. Internal PCM rather than encoded MP3 chunks is recommended. Independent MP3 files introduce encoder delay/padding and do not by themselves ensure gapless playback.

## Scheduling and continuity

Use a monotonic sample clock and bounded producer/consumer ring. Prepare enough audio before starting; render future audio while the current buffer plays. Maintain global tempo/meter, harmonic direction, motif IDs, energy trajectory, final notes/chords, active instrument state and boundary envelopes. Keep only compact musical state, not a transcript or past audio archive.

Prefer persistent plugin instances for stateful voices, delays and reverbs, processing sequential blocks while filling the ring. Reinitializing every minute loses tails and can reset instruments. Independent render workers require tested pre-roll/state restoration and controlled overlap; merely joining two exports is insufficient. Never schedule a note-on twice at a chunk seam. Preserve note-offs and sustain-controller state across boundaries.

Use musical transitions first; short equal-power fades can hide small discontinuities but must not duplicate beats or mask broken harmony. Retain only boundary audio still required for playback/overlap. Continuous tails do not justify retaining already-consumed output indefinitely.

## Feasibility and budgets

For chunk length L, queued inference + planning + render + transfer time T must stay below the remaining playable lookahead with safety margin. Sustained production must exceed consumption; warm token throughput alone does not establish this. Existing broker queue contention and deadlines can dominate. Reserve music work only through an agreed broker scheduling policy; do not bypass shared admission or starve other apps.

Proposed initial benchmark: L approximately 60 seconds, maximum two future chunks plus current chunk, with measured p95 production <=0.75L under agreed load. This is a target to evaluate, not a supported limit or user-approved latency. Bound memory by sample rate/channels/sample representation: stereo 48 kHz float32 PCM is 384,000 bytes/second, about 23.0 MB per minute. Three minutes is about 69.1 MB of PCM alone; plugin samples, model memory, transport copies and working buffers are additional.

Choose startup buffer and high/low watermarks from measured worst-case load. Cap disk spool, RAM, future audio duration, plugin voices and outstanding AI requests. Prefer RAM-only playback buffers if feasible. Pause planning at high watermark. Keep source catalog/precomputed reusable source analysis separate from generated-session audio.

If lookahead runs low, use a preauthorized deterministic extension of the musical plan or another disclosed fallback. If none is available, fade and report underrun instead of producing noise, pretending continuity or starting cloud inference. Acceptable repetition versus fade/stop remains open. Paused playback must stop production at its high watermark.

## Heard-audio deletion

Local playback: evict consumed PCM after the playback cursor passes it and any overlap dependency is released. Remote playback: use client playback acknowledgments, not network delivery acknowledgments, before normal eviction. Also enforce a strict unacknowledged-buffer limit and disconnect timeout, so a lost client cannot cause unlimited retention. A malicious/failed acknowledgment must not defeat hard storage limits.

Delete temporary rendered segments when their last playback/overlap reference is released. Stop cancels generation, stops or drains according to policy, releases plugins/buffers and cleans the session spool. Crash-start cleanup removes abandoned continuous audio using an app-owned session manifest with validated paths. Do not persist continuous prompts, notes or plugin states as a replayable project unless the owner changes the no-save requirement; small noncontent health counters may be separately configured.

No export command, result download, save button or persistent generated-audio cache in this mode. Security cannot prevent OS loopback capture or third-party recording; do not promise that. Plugin/OS caches are a separately disclosed limitation.

## Acceptance gates

1. At least two-hour soak with representative instruments/effects and shared inference contention: bounded memory/disk and no monotonically growing audio archive.
2. Seam tests: impulses, sustained notes, tempo-synced effects and chord changes; no missing/duplicate samples, clicks, stuck notes or reset tails.
3. Fault tests: slow inference, queue rejection, plugin crash, CPU load, pause, disconnect, missing playback acknowledgments and process termination.
4. Confirm startup delay and p95/p99 production time on authorized target hardware.
5. Confirm deletion after playback and orphan cleanup; no save/download route; no continuous data in normal-job folders.
6. Distinguish musical novelty from structural correctness through listening tests.

Gates are partially exercised as itemized in ACCEPTANCE_LEDGER.md and EVIDENCE.md.
The failed historical soak remains rejected. The corrected177.55-second device run
and synthetic process-WASAPI loopback are separate evidence. A two-hour controlled
effect/device soak was launched on2026-11-03; launch is not a pass. It does not cover
continuous MIDI instruments or inference contention. Live iBuyPower2022/Trifecta
access remains prohibited in this task.

That controlled baseline completed on2026-11-04 around05:18:57UTC:120 minute chunks,
7201.032s elapsed, normal exit, no remaining tested child processes or chunk WAVs.
The monitor observed at most31,752,426bytes/3 files at its sampling instants; other
manual samples observed4 files. These observations do not replace the88MB logical
allocation cap, continuous whole-process telemetry or an instrument/load soak.
Current code additionally streams one MIDI part through a persistent instrument
and optional effect; a separate4-chunk device run passed. Multiple continuous
instrument parts/full routing and two-hour representative current-code acceptance
remain unfinished. Orphan recovery now retires the exact empty owned metadata set
after releasing its lock; unknown files and active sessions are preserved.
# Persistent instrument ensemble update — 2026-11-04

Continuous playback now supports all three composed parts as persistent VST3
instances, followed by an optional master effect and the existing device sink.
Each instance reports its latency before admission; the aggregate instrument delay
must be <=88200 frames. A serial accumulator delays incoming dry audio by each
instance's latency and shifts downstream MIDI by upstream latency, aligning the
parts without rendering whole chunks in RAM. Bridges hold one512-frame block and
use pipe backpressure. Startup is bounded30s per instance, processing stalls15s;
failures terminate the owned pipeline. End-of-session release pads aggregate delay
plus512 frames. This is an explicit bounded tail policy, not arbitrary vendor-tail
preservation. Main stereo/mono output with bounded per-part gain in this path; full
sidechain/multi-output routing remains accepted unfinished work.

Known-signal test_stream covers three128-frame instances, exact384-frame aggregate
delay, nonzero output, echo and note-ID handoffs over two score chunks with no signal
drop. This is pre-device evidence. A separate four-chunk generated-music run used
five unchanged real processes (three instruments, effect, waveOut), completed in5s,
and deleted its disposable WAVs. It did not capture the endpoint or measure audible
gaplessness. The older2h soak remains separate and uses copied earlier binaries.
# Musical context preservation

Built-in continuous.play now accepts intent with root/mode/progression/parts/density/
seed. Other intention fields are rejected; the controller owns bar offset, duration
and ending state. The desktop supplies its selected key and accepted part selection.
Density evolves around the requested base while harmonic/seed state persists. A
four-chunk no-device test verifies F# minor, no bass, seed7, advancing bar state,
varying harmony and consumed-file deletion. It is generator evidence, not device
acceptance. Full sample tempo/harmonic ensembles and persistent graph remain open.


## Explicit output selection and completion bounds (2026-11-04)

Streaming now selects one plugin output bus0–7 explicitly. Unselected outputs are
discarded in memory: no auxiliary -.busN/state/audio files are opened by this path.
The former native guard rejected all multi-output stdout before processing; no
retention leak was demonstrated. The new fixture covers real distinct bus0/bus1
signals and absence of files. Simultaneous multi-bus mixing/sidechain DAG streaming
is still unfinished; this single-bus adapter does not waive that requirement.

Effect/instrument startup handshakes report latency and declared tail. Latency is
bounded to88200frames per stage/aggregate instrument pipeline. Natural completion
feeds zero input for aggregate latency plus declared instrument/effect tails, each
capped at44100frames, plus512frames to release instrument boundary notes. Infinite
or longer declared tails are explicitly clamped; cancellation stops owned processes
without waiting for completion tails. processing_policy records exact allowances.
Reported plugin tails are not proof of perceptual silence or accurate vendor reports.

Public continuous.play uses the app-owned device sink; its former diagnostic sink
path override is removed from the public request schema, along with any save/export
argument. Internal tests can inject a known-signal measurement sink, distinctly
labelled pre-device rather than hardware capture. Third-party plugin/OS recording
behavior remains outside app guarantees. The current long A126-host soak predates
these new completion/bus changes; it is not evidence for the new CC040 host.


Playback failure now wakes the waiting session immediately through a first-failure
latch. Once output has started, acknowledged-buffer exhaustion with no fresh input
for the bounded debounce interval stops the stream instead of silently resuming after
a gap; startup still has its own generation/worker deadlines. Submitted frames are
counted per block rather than only after an entire minute. Device/worker exit cancels
the producer and retires owned chunks. User cancellation remains distinct, and a
failed/closed stream cannot consume another file. Tests use an actual exiting sink
process and an acknowledged fast sink with intentionally delayed generation; these
simulate output-device failure/underrun, not physical device removal. Fresh startup
cancellation is checked before creating processes and during worker handshakes.
