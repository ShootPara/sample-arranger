# Catalog and musical decision model

Updated 2026-11-03. Full intended model for R03-R06 below. The real Soundloops catalog, persisted tempo observations, section renderer and deterministic note compiler are implemented in part; see ACCEPTANCE_LEDGER.md for exact evidence and gaps.

## Data model

2026-11-04 runtime reconciliation: whole eligible-catalog ranking and compact
planning-candidate adaptation exist, with explicit role/key filename provenance and
separate corrected/embedded/analysis tempo evidence. Unknown pitched keys require
explicit relaxation under a requested key. Rank IDs are path-derived; content-hash
dedup and durable retrieval bindings remain incomplete. Projects pin content on save.

Accepted score harmony now has a key/degree/register-validated timeline. A bounded
shared edit changes selected diatonic bars and deterministic voicing/pitches while
preserving rhythm, other bars and compatible exact locks. Crossing notes, conflicting
locks or unsupported manual textures reject the complete edit. Qt exposes an editable
degree table, chord-name lane and Undo/Redo. This is narrow major/natural-minor musical
realization, not audio harmony analysis or subjective style/listening acceptance.

Separate asset identity (content hash) from file locations and musical observations. Track format, channels, sample rate, duration, loop/one-shot/phrase type, availability and duplicates. Observations carry value, method/version, source field/path, source fingerprint, timestamp, raw score and calibrated confidence category. Store selected values and user overrides separately. Confidence is per property, not per file.

Music fields: tempo candidates including half/double time, beat/downbeat grid, meter, loop boundaries, bar length, key/chord timeline, tuning, instrument role, energy/density, transient/spectral features and pack/variant relationships. Rights records reference user-supplied licenses; unknown is a valid state. Embeddings, if useful, remain local and independently replaceable; indexed structured filtering comes first.

Import references originals by default; managed copying is explicit. Fingerprint incrementally, detect relocation, resume interruption, and invalidate only affected derived data. Rescans preserve locked corrections. Projects pin the interpretation used at creation; changed analysis does not silently retime old arrangements. Deleting a job never removes shared originals.

## Metadata and MAGIX

Prefer locked user decisions, validated sample-specific metadata, then verified pack metadata, then analysis. Preserve disagreements rather than overwrite evidence. Validate metadata using duration, plausible bars and audio onsets. Pads and isolated impacts can legitimately have no BPM.

MAGIX documentation describes embedded tempo/pitch information in relevant Soundpool material, but this does not establish a universal metadata schema. Inspect representative actual packs before choosing parsers. Candidate discovery targets include embedded chunks/tags, folder relationships, BPM.inf and description.xml where present. Their syntax, scope and variant mapping remain unverified for this user's library. Vita backup folder presence does not prove VST3 availability or Soundpool compatibility.

Source: [MAGIX Sequoia manual](https://www.magix.com/fileadmin/user_upload/Support/Pro-Audio-Downloadpage/manual-sequoia-pro-17-en.pdf), consulted 2026-11-03. User-specific evidence: E03 and Google Drive section of EVIDENCE.md.

Analysis compares rhythmic confidence, onset alignment and length hypotheses; short loops need different methods from full songs. A calibrated holdout set must include incorrect metadata, 60/120 ambiguity, pickup notes, swing, non-4/4, drifting tempo and unpitched material. Expose unknowns and a metronome-assisted correction UI.

## Arrangement and MIDI

Hard constraints: available assets, valid event timing, explicit duration <=240 seconds for normal output, locks, authorized plugins and requested exclusions. Soft scores: groove, harmonic compatibility, roles, texture, density, repetition, transformations and voice space. Rank ensembles, not only individual samples.

Use chord timelines, not key labels alone. Sample harmony can be uncertain; ask once or choose conservative musical material according to the accepted job policy. Prefer compatible recorded variants before large transposition/stretch. Limit transformations by instrument and audition quality.

Model intentions can specify scale degree, contour, rhythmic motif, role, density and articulation. A deterministic compiler produces stored notes with pitch, beat position, duration, velocity, channel, articulation and instrument mapping. Use exact beat fractions/ticks and sample positions, not cumulative floating-point additions. Validate note lifecycle, boundaries, register, polyphony and neighboring phrase transitions.

Voice leading and consonance rules are style-specific preferences, not universal bans on parallel fifths or chromatic notes. Keep motifs across sections; vary support; reserve space for narration; plan musical resolutions and audible tails. A 32-bar 4/4 piece at 128 BPM occupies 60 seconds before tail policy, illustrating why musical endpoint and final file length are separate.

Store accepted notes/clips, seeds, generator versions and plugin states. Seeds alone do not guarantee future identical music. Do not claim that rules guarantee aesthetic quality; listening evaluation is required.

## Implemented metadata/correction boundaries (2026-11-04)

`catalog.metadata` reads only selected RIFF/WAVE chunk headers/known bounded fields,
with4096-chunk and container bounds, skipping PCM payloads. It inventories unknown
chunks and parses24-byte ACID observations using a primary implementation reference:
[libsndfile wav.c](https://raw.githubusercontent.com/libsndfile/libsndfile/master/src/wav.c).
No libsndfile dependency/code is included. RF64/RIFX, proprietary MAGIX chunks and
external pack files remain explicit unsupported adapters. Meter/root observations
are not a harmonic key/major-minor inference. One-shot flags and duration/beat tempo
conflicts require review; duration agreement is evidence, not calibrated confidence.
The real Soundloops case in EVIDENCE.md demonstrates a120-versus130BPM conflict.

Metadata and manual corrections are stored against bytes/mtime with a UTC observation
date. Manual history is append-only locally. Changed-source rescans invalidate use
without erasing the previous value. Legacy corrections without identity/date remain
visible as unverified; no migration invents provenance. These are stat fingerprints,
not content hashes; content-identity/dedup and confidence calibration remain open.
# Form and accepted note edits — implemented 2026-11-04

Intention compiler2 supports explicit bounded form sections (bars, role, density,
parts) and a `bed` rule. Bed/underscore/narration briefs request intro/main/lift/outro
where duration permits, with fewer parts and lower velocities at the edges. Form
bars must match duration; sections cannot reintroduce excluded parts. Exact timing,
register, voice-leading and note-off validation remain deterministic. This improves
structure but does not establish genre/listening acceptance. Existing accepted
scores are preserved, not automatically regenerated by compiler changes.

`score.edit` and `project.notes.edit` implement ordered atomic set/add/remove note
changes (<=256 per request). Invalid timing/register/overlap rejects the whole edit.
Project edits require expected_revision and preserve other notes, assets and pins.
Large scores should use project-path edits rather than exceed CLI256kB requests.
Desktop note table and drag/resize use the same score edit operation; Undo/Redo keeps
at most32 in-memory snapshots/8MiB encoded musical state. No audio enters history;
saved projects change only on Save. Full inspector undo/dirty-close recovery remains
unfinished. Timeline form markers are visual; full editable chord/automation lanes
remain accepted work.


## Content identities and catalog locations (2026-11-04)

Explicit content hashing is opt-in per file, read-only, streamed with a512MiB cap.
The `content_identity` table records SHA256, bytes, mtime and inspection time;
`matches_catalog_stat` explicitly does not mean live content verification. A file
changed while preserving size/mtime requires a fresh hash to detect; tests cover
this distinction. Duplicate paging lists identical observed content without deleting
aliases. Catalog relocation requires an identical freshly hashed destination;
renaming/moving audio is the user's action, never performed by the application.
Dated location history and old correction history remain. Sources and saved project
pins are independent. GUI Hash audio/Relocate entry use the same commands; newest
manual UI acceptance is pending. Content-bound retrieval and user role/key
corrections remain in the whole-app queue.


Content-pinned role/key corrections are now separate dated user assertions, with
per-property provenance carried into musical ranking and compact planning. They are
not measured harmony or calibrated confidence. Explicit clear keeps audit history.
Hash IDs survive catalog relocation and collapse identical aliases. Retrieval hash
observations alone remain historical: planning.resolve freshly reads selected audio,
refuses same-size/mtime substitutions and produces project-ready source bindings.

The conservative ensemble planner proposes parallel role layers with reviewed
normal-time tempo ratios, phrase-bar entries, conservative linear route gains and
missing-role warnings. It keeps one pitched layer by default because tonic/mode
labels do not establish shared progressions. Per-role filename search terms preserve
piano/guitar/pad requests; exclusions remain active. Default output is reviewable in
the routing workspace, then pinned through shared Save/render. Chord progression,
loop/downbeat joins, automatic level matching, full energy form and listening quality
remain partial; additional pitched loops need explicit unverified-harmony review.


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
