# Observed plugin compatibility

Updated2026-11-04. These are narrow observations, not universal compatibility labels.
Windows x64 host, VST3 SDK3.8.1_build_84, portable GCC16.2.0. Native audio is44.1kHz
float32; plugins requiring other-only sample formats/layouts remain unsupported
until an adapter is implemented/tested. No proprietary plugin is redistributed.

| Component | Exercised | Status / remaining evidence |
|---|---|---|
| Owned stereo delay, class66231001… | Known128-frame delay/256-frame echo; exact replay; parameter offsets; component/controller save/restore; actual HWND editor; .vstpreset round-trip; real stream/device/engine-loopback | Working for specified fixtures. Not a musical sound-quality recommendation. |
| Owned stereo instrument, class66231003… | Polyphonic IDs/offs; known nonzero latency/tail; assigned score part; state attachments; persistent MIDI packets and dry PDC | Working narrow. Full multi-instrument continuous graph remains incomplete. |
| Owned sidechain/two-output, class66231004… | Independent known bus signals, explicit DAG, internal mixers and per-node PDC | Working narrow offline graph. Native routing/automation desktop surfaces remain incomplete. |
| Owned fixed-mono effect, class66231005… | Rejects stereo; native mono fallback; L/R average input; output duplicated to stereo; measured delay/echo | Working test_native. Broader vendor/layout negotiation remains untested. |
| Owned fixed-mono instrument, class66231006… | Native mono fallback; persistent MIDI packet output equals stereo fixture after duplication/dry alignment | Working test_stream; current2h controlled device soak started05:56:42UTC, pending. |
| Installed RX10 De-click | Historical SDK validator47/48; actual stereo render and nine-second byte-identical MP3 replay; reported latency29445/tail0 | **Partial.** Validator `Parameter Bypass persistence` said bypass was not correctly set in processor AND controller. Parameter string round-trip diagnostics also occurred. No bypass fix or full compatibility claimed. |
| Other14 installed RX10 entries | Filesystem inventory only | Untested; no inference from De-click or filenames. Activation/editor/license requirements remain vendor-specific. |
| SDK mda DX10/JX10 | Three-instance native ensemble with real loop; actual component recall -> byte-identical MP3; synth-only peak0.684/RMS0.130 proves signal; permissive source notices inspected | Working narrow offline case. No controller-only state returned; editor/continuous/vendor matrix and whole-bundle/asset rights remain separate. Historical silent effect probe stays rejected. Not bundled. |

Current adapters first request stereo, then try the plugin's reported native mono
or stereo arrangements when stereo is rejected. Mono input is arithmetic mean of
L/R (opposite polarity can cancel); mono output is duplicated. Input/output channel
counts are recorded in processing/graph provenance. Wider layouts are rejected,
not silently remapped. Dynamic latency changes fail explicitly pending reconfiguration.

Plugin processes have adjustable owned memory/deadline limits and tested actual
abort containment. They are not filesystem/network sandboxes. Persistent registry
and explicit quarantine/retry commands are now implemented; the Plugin library
dialog wires scanning, selection and retry, with manual acceptance pending. Vendor
editor/DPI/key matrix, activation setup, MIDI-output
generators, full automation lanes and real-time graph acceptance remain open.
Plugin installation/rescan must not imply license acceptance or instrument-content
redistribution. Keep these rows and tests current after SDK/host/plugin updates.

Registry keys include exact plugin binary and worker hashes, checked UTC and compact
component inventory. An unchanged quarantined binary does not load again, even on
an ordinary rescan; explicit retry requires its reviewed current hash. Changed
plugin content is new evidence. An updated worker invalidates ready cache, but does
not silently clear quarantine. Cancellation is not recorded as a plugin failure;
missing/unlaunchable host infrastructure is not a compatibility certification or
automatic quarantine. Native initialization std::abort is exercised in an owned
fixture. Actual vendor failures remain distinct. Discovery caps256 bundles/10000
visited entries and skips redirected trees; unreadable sources are reported.


## Program and displayed-value controls, 2026-11-04

Host A8162BE4DBBC9AEAD5DDE78704AF19A06660D2717162DE19056F6FDBF2DFEFF9
adds controller-owned string/normalized conversion, bounded program lists/unit
mapping and length-bounded UTF16 reads. Generic state capture applies program
selectors before explicit overrides in controller and separate processor flushes,
rather than accidentally letting a high numeric program ID erase lower-ID edits.
SDK JX10 exposes52 named programs; Analog Bass (index17) plus parameter0=.13 survives
component recall/controller component-sync and produces nonzero, equivalent replay.
This component returns no independent controller state (null SHA, no controller file);
that is explicitly tested, not described as paired recall. The owned gain fixture
independently saves/restores its4-byte controller state as well as component state.

Desktop shared controls now provide displayed-value conversion, program list/named
or zero-based selection and generic state capture for master effects, instruments
and routing nodes. Normalized overrides remain available; untouched controls follow
a newly selected program. Qt actual-worker conversion tests pass; newest packaged
manual native/editor/program/keyboard/DPI acceptance remains open. Unsupported or
ambiguous program mapping fails explicitly. Programs, app state bundles and external
.vstpreset files remain distinct. RX10 bypass failure is unchanged. The running
A126-host soak uses copied earlier binaries, not this newly rebuilt controller host.
