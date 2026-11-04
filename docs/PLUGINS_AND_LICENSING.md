# Plugins, dependencies and licenses

Updated 2026-11-03. Candidate assessment plus active direct-SDK implementation. AGPLv3 is the accepted app direction; installed portable toolchain and pinned MIT SDK are recorded in README/EVIDENCE. Candidate libraries below are not all dependencies. Inspect exact releases/transitive licenses before distribution.

## Full-app VST3 requirements

Native Windows VST3 hosting is day-one. Current pinned tools/host target Windows x64;
instruments and effects remain in scope. Mono/stereo normalization, sidechains,
multi-output DAGs, exposed parameters, state/editor and preset paths are partially
implemented. MIDI-output generators and broad vendor acceptance remain unfinished.
See [observed compatibility](PLUGIN_COMPATIBILITY.md) for actual component evidence.

Separate scanning from main process, quarantine crashing plugins and retain safe failure details. Runtime worker isolation by instrument/chain is proposed. Track plugin class ID, vendor/version, binary hash, architecture, exposed parameters, content dependencies, preset/state hash, interactive compatibility and unattended compatibility separately.

Support component/controller state lifecycle, editor focus/resizing/DPI, transport and tempo context, bus negotiation, sample-accurate events, parameter automation, bypass, latency changes and tails. Handle offline incompatibility via explicit real-time-paced rendering where tested. GUI/activation requirements return setup-needed rather than hang. Never silently replace a plugin or discard an effect. Freeze audio internally for reliable project playback; normal external deliverable stays MP3 only.

Plugin process isolation limits crashes but is not automatically a filesystem/network sandbox. Plugins may write caches, contact licensing services or require an interactive session. Describe those limits per plugin. Initial licensing/activation is an explicit user workflow.

## Candidate components

| Candidate | Role | License/cost considerations | Proposed disposition |
|---|---|---|---|
| VST3 SDK | Host interface/helpers | Current SDK MIT; older SDK and VST2 terms differ | Core option; direct integration entails more engineering |
| JUCE | Audio/device/UI/hosting foundation | AGPLv3 or JUCE license; not automatically cost-free for every distribution | Leading candidate after repository license decision |
| Tracktion Engine | Arrangement/playback/routing model | GPLv3-or-later or commercial; JUCE separate; conditional free tier is not unconditional | Compare effort/obligations against JUCE alone |
| Carla | Existing host/routing reference | GPLv2-or-later; integration and dependencies require review | Reference or alternative backend, not assumed drop-in |
| Tonal | Notes/chords/scales/interval calculations | MIT | Conditional dependency if JS/TS layer is justified |
| Scribbletune | Concise MIDI patterns | Core MIT; companion free plugins can be closed-source | Prototype/optional pattern layer |
| music21 | Symbolic analysis/voice-leading tests | BSD code; corpus separately restricted | Research/test tool; exclude unreviewed corpus |
| JJazzLab | Accompaniment/toolkit/MIDI exchange | LGPL v2.1 core; Java/dependencies/styles/assets separate | Optional integration/reference |
| MMA | Directive-driven MIDI accompaniment | GPL program/docs/standard library; inspect exact package | Optional external integration/reference |
| FluidSynth | SoundFont rendering | LGPL; soundfonts separate | Built-in playback candidate |
| sfizz | SFZ sampler/library/plugin | Inspect exact library/UI dependency licenses; recordings separate | Candidate sound engine/instrument |
| Surge XT | VST3 synth | GPLv3 code; FAQ permits commercial songs/sounds; content review still required | Free compatibility and sound-palette candidate |
| FFmpeg | Decoding, encoding, loudness/mix utilities | Build-dependent LGPL/GPL and dependency terms | Candidate controlled audio-only build |
| Rubber Band / Essentia | Stretching / analysis | Copyleft/commercial routes and model/dependency terms require review | Evaluate quality and license; do not assume free proprietary compatibility |

Public open-source intent makes copyleft routes possible, not automatically chosen or compatible. Select project license before committing to engine combinations. No subscriptions are accepted. Any necessary paid component must offer acceptable one-time terms and receive separate purchase authorization. Do not copy an entire engine simply because it is free to download.

Application code, plugins, soundfonts, SFZ mappings, recordings, presets/wavetables, styles, MIDI examples and model weights each need their own rights record. Software licensing does not automatically license assets or guarantee generated-output rights. Do not redistribute the user's iZotope/MAGIX binaries or content. Using user-installed proprietary plugins and bundling those plugins are different activities.

## Installation experience proposal

Provide compatible-plugin guidance and user-initiated installation/rescan. Prefer official publisher downloads, integrity/signature information where available, declared format/architecture and a rollback/uninstall path. Do not execute arbitrary download URLs from AI output. Whether the app downloads installers or opens publisher pages is unresolved. Include built-in sounds with verified redistribution/music-use rights; no specific sound pack selected.

E03 confirms only filesystem presence of 15 RX 10 entries, not working hosts or instruments. MAGIX/Vita backups are stale leads. Compatibility matrix must record NOT TESTED until scan, instantiate, editor, parameter, state, offline, latency, crash and continuous-mode tests actually run.

## Primary sources

- [VST3 licensing](https://steinbergmedia.github.io/vst3_dev_portal/pages/FAQ/Licensing.html), [processing interface](https://steinbergmedia.github.io/vst3_doc/vstinterfaces/classSteinberg_1_1Vst_1_1IAudioProcessor.html)
- [JUCE licensing](https://juce.com/get-juce/), [Tracktion license](https://github.com/Tracktion/tracktion_engine/blob/develop/LICENSE.md), [Carla](https://github.com/falkTX/Carla)
- [Tonal](https://github.com/tonaljs/tonal), [Scribbletune](https://github.com/scribbletune/scribbletune), [music21 licensing](https://music21.org/music21docs/about/about.html)
- [JJazzLab](https://github.com/jjazzboss/JJazzLab), [MMA](https://www.mellowood.ca/mma/online-docs/html/ref/node1.html)
- [FluidSynth licensing](https://github.com/FluidSynth/fluidsynth/blob/master/doc/wiki/LicensingFAQ.md), [sfizz](https://github.com/sfztools/sfizz), [Surge FAQ](https://surge-synthesizer.github.io/faq/)
- [FFmpeg license](https://ffmpeg.org/legal.html), [Essentia licensing](https://essentia.upf.edu/licensing_information.html), [Rubber Band publisher](https://www.breakfastquay.com/)
