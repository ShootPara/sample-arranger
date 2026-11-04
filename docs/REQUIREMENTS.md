# Requirements

Updated 2026-11-04. Source U1: owner instructions and clarifications in the current conversation, including subsequent implementation authorization. All rows below are accepted requirements; technical mechanisms elsewhere are proposals unless stated otherwise.

| ID | Requirement |
|---|---|
| R01 | Windows standalone application, intended for a public open-source repository. Sanitized source published to the owner-approved ShootPara/sample-arranger; personal local Windows deployment delivered. |
| R02 | Prefer free tools. No recurring dependency fees; necessary one-time purchases require separate approval. Open source does not select a license automatically. |
| R03 | Import/query a local sample catalog; reliable metadata first, audio analysis where needed; confidence, provenance, correction and rescanning. Investigate actual MAGIX formats. |
| R04 | Interpret natural-language music goals, retrieve suitable samples and produce coherent editable arrangements. |
| R05 | Prefer the actual local AI Server/model. Respect its broker, limits, admission, privacy and resource policies. No automatic external AI fallback. |
| R06 | AI-guided MIDI structure and note intentions, with deterministic musical realization and validation. |
| R07 | VST3 hosting is day-one. Instruments and effects, native/generic controls, presets, automation and validated routing/sidechain/multiple outputs are in the complete app. Other plugin categories remain to be investigated, not silently excluded. |
| R08 | Built-in sounds plus user-installed compatible downloaded plugins. Reputable prerequisite installation is authorized; new plugin licenses/agreements, unknown software and purchases retain their separate approval boundaries. |
| R09 | Professional cohesive UI; arranging, previewing and rendering are the focus, not recording or live performance. |
| R10 | Application features available through documented CLI requests. Owner's later decision selects this one PC; no remote music listener is required. Preserve explicit architecture/contracts/rationale so cloners can adapt transport safely. Actual inference broker identity and separate app admission must be respected. |
| R11 | Ask for clarification/confirmation once where needed per job. Refined prompt is authoritative; initial prompt is background. Security and authorization constraints still apply. |
| R12 | Accept supplied narration, currently produced through Codex, and return it mixed with generated or supplied music. No voice cloning, transcription or synthesis requirement is implied. |
| R13 | Standard generated output: MP3, 192 kbps, duration at most 240 seconds. Earlier suggested WAV/stem/MIDI deliverables are not accepted output requirements. Internal intermediates are distinct from deliverables. |
| R14 | Normal jobs use folders that the user can delete when no longer needed. Configurable local persistence and optional temporary sessions are accepted. |
| R15 | Offline-only is not required. Every network dependency must have a purpose and documented data flow; no unexplained telemetry/cloud inference. |
| R16 | Continuous mode generates successive chunks of roughly one minute, plays continuously, deletes audio already heard, and has no save option. It is distinct from retained normal jobs. |
| R17 | Sophisticated internal automation and musical logic; no assumed existing scripts or named integration. |
| R18 | Documentation is continuously maintained with application changes and usable by coding platforms. |

## Scope boundaries

The owner subsequently authorized implementation, reputable local dependencies and local commits. The owner now requests usable local delivery and sanitized source publication. Exact repository ShootPara/sample-arranger was approved and sanitized source published; public binary redistribution is not cleared. Purchases, new legal agreements, credential reuse and security/access expansion remain separately gated. Existing model/settings remain untouched. Local-only Windows deployment and AGPLv3 direction are accepted, subject to dependency review. Document rationale for future cloners.

R13 applies to normal deliverables; R16 is ongoing disposable internal PCM beyond four minutes. Normal output is stereo44.1 kHz MP3 192 kbps CBR. Current evidence and unfinished requirements are in ACCEPTANCE_LEDGER.md.

## Delivery priority (latest owner steering)

Prefer a bounded essential smoke of the usable build, fix genuine shipping blockers, document known gaps and let user feedback guide follow-up. Do not start new long soaks or repeatedly widen testing. Existing historical failures remain failures. Full intended scope stays in the ledger without blocking personal usable delivery on every acceptance gap.

## Main workflows

1. Connect sample folders; index incrementally; inspect uncertain tempo/harmony; correct and lock facts.
2. Submit a music brief through UI or CLI; validate constraints; ask one consolidated clarification if needed; plan, render, inspect and return MP3.
3. Add MIDI parts and chosen VST3 instruments/effects; audition changes, preserve locks and restore project state.
4. Supply narration; align music and speech, apply agreed processing and return a bounded MP3.
5. Start continuous playback; buffer ahead, vary music coherently, discard heard audio and clear session state on stop.
6. Reopen or delete a retained normal job; never delete original library assets merely because a job is removed.
