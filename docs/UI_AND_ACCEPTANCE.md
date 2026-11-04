# UI direction and acceptance plan

Updated 2026-11-03. Intended complete design below. Actual implemented/tested status is in ACCEPTANCE_LEDGER.md; this plan does not establish acceptance.

2026-11-04 implementation reconciliation: the Qt library/timeline/inspector workspace
and a separate routing diagram now operate through shared commands. Routing includes
main/sidechain buses, multi-output gains, mixers, source repetition/placement and
reviewed half/double tempo, native editor and normalized automation/parameter-ID
tables. Packaged09c33ac was manually reopened, source start0.25s and explicit half-time
selected, saved revision3 and rendered to a measured132300-frame MP3. Fit diagram
and scrolling controls were visually checked. Newer source adds bounded routing
Undo/Redo, unsaved-change protection, processing review and progress mirroring;
targeted Qt tests pass, but the newer controls need packaged/manual acceptance.
Exact-note locks have shared validation and non-drag controls; section/harmony locks
remain open. Raw table drafts still require Apply; broader draft/Undo/dirty recovery,
timeline automation/chord lanes, scrub/meters and professional visual/accessibility
acceptance remain in scope. A passing pane layout is not completion of R09.

## Professional workflow

Graphite/neutral studio surfaces, restrained teal accent, clear typography and role colors reinforced with labels. Library at left, arrangement timeline centrally, contextual inspector/plugin rack at right, transport/meters below. Audio and MIDI share section markers, chord lane and one authoritative timeline. No chat transcript should displace the musical workspace.

Brief/constraint cards show current interpretation and a consolidated one-time clarification. Proposal cards offer audition, compare, apply and discard with factual reasons. Allow locks on sections, assets, rhythm, harmony and notes. Show original versus tempo-matched sample preview, loudness-matched comparisons, missing-asset recovery, confidence/provenance and metronome-assisted corrections.

Plugin rack distinguishes instrument/effect roles and interactive/unattended readiness. Download/install compatibility guidance is user initiated. Native editor accessibility depends on each plugin; provide a generic exposed-parameter inspector where practical without claiming it replaces all editor features.

Narration lane shows source waveform, placement and ducking automation. Continuous mode has a visibly distinct temporary-session surface with start/stop, buffer health and privacy explanation; no save/export controls. Normal jobs have a folder/results view and explicit deletion.

Keyboard access, visible focus, screen-reader labels, scaling, high contrast, reduced motion and non-drag alternatives are acceptance requirements. Resource-heavy tasks cannot freeze transport/UI. Suggested indexed query p95 target <200 ms on an agreed benchmark library; actual load, audio-buffer size and supported track counts must be measured.

## Traceable acceptance matrix

| Gate | Requirements | Evidence needed |
|---|---|---|
| Repository/platform/license | R01,R02 | Windows build/package, dependency bill of materials, compatible chosen license, no subscription requirement |
| Catalog | R03 | Interrupted import resumes; duplicates/relinks correct; originals unchanged; correction survives rescan; uncertainty visible |
| Arrangement | R04,R06,R17 | Real assets only; valid event timing; style-specific musical checks; listening evaluation; locked edits preserved |
| Local AI | R05 | Verified authorized contract; bounded tokens/results; no raw-provider/cloud fallback; overload/quarantine behavior |
| VST3 | R07,R08 | Test instruments and effects; scan crash containment; state recall; editors; automation; offline/real-time render; latency/tails |
| UI | R09 | Keyboard/screen-reader/manual workflow review and responsive transport under background load |
| CLI/security | R10,R11 | Schema examples execute; UI/CLI parity; owner isolation; idempotency; one clarification; refined-prompt precedence |
| Narration/output | R12,R13 | Aligned speech, agreed processing, MP3 192 kbps only, decoded duration <=240 seconds, measured loudness/peaks |
| Jobs/privacy | R14,R15 | Delete only owned folder data; temporary cleanup; no secrets/content logs; documented actual network flows |
| Continuous | R16 | Soak/boundary/fault/deletion tests in CONTINUOUS_MODE.md |
| Documentation | R18 | Requirement-to-test links, schema/reference consistency, example checks and change review |

## Work sequence, not deferred features

Establish evidence/license decisions; design and test shared contracts; build vertical sample+MIDI+VST3+MP3 path; add narration and broker client parity; implement continuous scheduling/deletion; complete accessibility, recovery and compatibility validation. These are engineering dependencies within the full app. VST3, CLI, narration and continuous mode are not assigned to optional future releases.

This plan is not acceptance evidence; implemented subsets and actual tests are tracked in ACCEPTANCE_LEDGER.md and EVIDENCE.md. Further tests must record exact app/contract/plugin/model versions, hardware, fixtures, dates and observed outcomes. Test downloads/content must have reviewed rights. Use synthetic speech/audio where user data is unnecessary.


Routing unapplied controls are separate from applied graph/history. Switching nodes
preserves even invalid text; Save/render/package requires Apply or explicit Restore
applied values for pending panels. Source, routing, automation, mixer and output
panels commit independently. Unsaved-change guards include unapplied controls. This
is live-dialog protection; routing crash-draft persistence remains an acceptance gap.


Routing Automation includes a parameter-selectable step timeline. Dragging writes
pending table frame/value cells with quarter-beat/0.01 snapping; Apply validates and
commits the lane. The same cells are keyboard editable. Invalid rows are retained
and labeled hidden, and large lanes preview only512 points without claiming the
unshown tail. Musical/audio timeline automation overlays and live meters remain.
