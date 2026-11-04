# Decisions, open questions and documentation maintenance

Updated 2026-11-04.

## Accepted decisions

- Windows, open-source repository intent, free tools preferred and no recurring dependency fees.
- Full-app day-one VST3; effects/other hosting needs not excluded.
- Built-in sounds and user-installed compatible downloaded plugins.
- Local model preference and existing infrastructure must be respected.
- CLI/shared commands on this Windows PC; earlier multi-PC intent was superseded by the local-only owner decision. Narration overlay remains an app workflow.
- One clarification/confirmation where needed; refined prompt authoritative, initial prompt background.
- Normal output MP3 192 kbps, at most four minutes, retained per-job folders removable by user.
- Configurable local persistence/temporary sessions; disposable continuous mode with no save option.
- Sophisticated internal logic, not a named script integration. Arranging/rendering, not recording/live performance.
- Implementation and personal local deployment are authorized and delivered. Sanitized public source publication to ShootPara/sample-arranger was explicitly approved. Purchases/new legal agreements/security expansion remain separately gated.
- Parent update: iBuyPower2022 live environment is NOT authorized for tasks. Alienware and Drive/backup research only. Parent received the source-gap report.

## Historical research questions (accepted decisions below supersede these)

| ID | Question / recommended next evidence |
|---|---|
| O01 | Exact repository license and framework route. Compare compatible open-source engine options before selecting. |
| O02 | Rendering host and x64 support baseline. Recommend testing Alienware rendering with server inference, but server live tests require new permission. |
| O03 | Current broker contract and music-client enrollment. Existing inference broker is identified; separate music-job routing/authentication is not. Any-PC access must not widen existing firewall/auth implicitly. |
| O04 | Essential instruments and effects, custom plugin directories, sidechain/multi-output/MIDI-generator needs. Current inventory proves effects presence only. |
| O05 | Actual sample library roots, representative MAGIX generations and content rights. Backups do not establish current installed content. |
| O06 | Built-in sound palette and download UX: publisher link versus managed installer; verify rights and compatibility. |
| O07 | Continuous playback location: requesting PC or renderer. Confirm internal PCM, roughly bar-aligned minute chunks and permitted startup latency. |
| O08 | Continuous overload/disconnect policy: deterministic repetition, fade/pause or stop; allowed buffer horizon and resource sharing. |
| O09 | MP3 192 kbps interpretation (recommend CBR), sample rate/channels, loudness/true-peak profile and exact decoded-duration tolerance. |
| O10 | Narration placement/lead-in/out and optional cleanup. Recommend preserve timing/content; reject >240-second input rather than alter silently. |
| O11 | Normal-job root, input copy/reference policy, temporary-job output retrieval/cleanup, failed-job retention and allowed network flows. Recommend non-synced data outside repository. |
| O12 | Current model/runtime/hardware and music benchmark. E04 is live tool capability, E05-E10 are historical config evidence. Do not access server live in this task. |
| O13 | Shared broker scheduling under continuous load and other applications. Music cannot override maintenance/quarantine or starve existing work. |

## Continuous documentation practice

Docs live in this existing project. README indexes authoritative documents; REQUIREMENTS owns accepted scope; EVIDENCE owns observations/source dates; the other documents own their respective proposed designs. Do not duplicate mutable API details across documents without references.

Each change must update affected requirements, contract, lifecycle/retention, UI guidance, compatibility matrix and acceptance criteria in the same change. Record decision rationale and superseded text. Mark implemented/tested only with actual evidence. Preserve refined user instructions as authoritative; earlier proposals are background.

Once implementation is authorized, derive CLI reference/JSON schemas from command definitions and test all documented examples using synthetic fixtures. CI should detect broken links, schema/reference drift, undocumented operation changes and forbidden secret/job artifacts. Implementation is now present; use bounded checks appropriate to the change.

Use contract/project-format revisions for compatibility, not to reclassify required features as a later product. Installed CLI should report its contract revision and matching docs. Track plugin/library/model versions and provenance where they affect reproduction.

The latest owner explicitly requests publication and personal deployment. Publish only to a verified exact repository, after a bounded private-content review and exclusion of user jobs/audio/configuration. Preserve raw private operational history locally; publish a clean sanitized source snapshot. Binary redistribution obligations remain separate. Preserve sanitized non-secret facts while moving private operational details outside public documents if needed.

## Change log

- 2026-11-03: Created living documentation in the preserved project; incorporated all sixteen owner answers and prior clarified requirements. Added dated local/Drive evidence, current worker capability limits, distinct inference/music broker boundaries, continuous-mode design and test gates. No application implementation or publication.
- 2026-11-03: Recorded setup-parent restriction prohibiting live iBuyPower2022 tasks and confirmation that the coordination-gap report was received.

## Owner decisions accepted on 2026-11-03

- AGPLv3 is the intended licensing route; verify dependencies before selecting them.
- Alienware Windows x64 hosts the application, CLI, catalog, plugins, rendering and playback for this installation. Keep music jobs local by default. Document deployment alternatives for clones, including why the local default exists.
- The existing inference broker remains a separate integration. Verify its contract through approved documentation or an authorized operator. No live Trifecta access is authorized.
- Start catalog discovery with the supplied Soundloops Drive folder and its local virtual-drive mapping. Treat loop files as private inputs. MAGIX samples can follow when supplied.
- Continuous playback follows the requesting PC; in this installation that is Alienware. Preserve the full VST3, MIDI, narration and continuous-mode scope.
- Accepted output defaults: stereo 44.1 kHz MP3, 192 kbps CBR, maximum 240 seconds for normal jobs.
- Implementation and local Git commits are authorized. Prefer user-space tooling and free dependencies; do not require unattended elevation.


## Usable delivery priority, 2026-11-04

The owner now prioritizes credit containment and usable delivery over exhaustive
acceptance work. Finish the current observed usability fixes, one essential frozen
smoke, local deployment/guide and sanitized source publication after verifying the
exact target. Do not start further long soaks or broaden suites merely to fill the
ledger. Existing full scope remains recorded as working/partial/untested/blocked;
user feedback drives subsequent bug fixes. Preserve historical near-silent output,
RX bypass and failed soak evidence. Do not weaken access/security settings.
