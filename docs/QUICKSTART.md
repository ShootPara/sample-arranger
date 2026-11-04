# Start making music

Open **Sample Arranger** from the Desktop or Start menu. The installed app and CLI
are in `%LOCALAPPDATA%/SampleArranger/app`. Setup needs no administrator access.
Existing catalog, plugins, projects, jobs and settings stay where they were.

For a first result, select **Built-in instruments**, enter “20 seconds of upbeat
music in C major at120 BPM”, and click **Build plan**, then **Render MP3**.
Click **Play result** to preview. Normal output is stereo44.1kHz MP3,192kbps CBR,
at most four minutes. Results stay in your chosen job folders until you delete them.

For samples, use **Add folder**, or choose an existing catalog in the Project
inspector. Search, audition, add clips and edit their durations. **Build layered
sample plan** proposes parallel layers in Routing. Review key/tempo evidence and
half/double-time choices; filenames are hints, not measured musical facts.

For composition, edit Notes or Harmony, drag note events, use **Melody rhythm**,
or **Protect music** to preserve a section, harmony or rhythm. Ctrl+Z/Y undo/redo.
Ctrl+S saves, Ctrl+O reopens, Ctrl+Enter renders, and Cancel job stops active work.
The UI labels render results made from an earlier edited snapshot.

For VST3, choose an installed Windows x64 bundle/module and inspect its components.
Assign instruments to parts and effects to processing routes. Native editors,
generic parameters/programs and captured presets are available where compatible.
Routing supports offline sidechains, buses, mixing and step automation. Apply each
edited panel before Save/render; unapplied controls are preserved when switching nodes.
User plugin licenses/activation and internal sample libraries remain separate.

For narration, choose your existing voice file in Project, set its start/levels,
check placement, and render. There is no microphone recording, TTS or voice cloning.

Continuous mode is disposable playback: stop it when finished. It has no save or
export route. Its supported persistent instrument/effect path is narrower than
offline routing; see KNOWN_ISSUES.md before relying on complex continuous graphs.

## Automation

The installed `arranger-cli.exe` accepts one JSON request through stdin or
`--request path.json`, returning one JSON result/error. Start with:

```json
{"contract":1,"operation":"capabilities","arguments":{}}
```

Use `contracts.schema` for request schemas, `compose.render` for a deterministic
music job, or Save a project and use `jobs.submit` with a UUID and project SHA256
for retry reconciliation. See CLI_AND_BROKER.md for precise operations and limits.
Audio, VST3, MIDI and retrieval run locally. Use AI connection and AI plan for the dedicated local-model broker adapter.
This installation is now enrolled and has passed a real model-plan-to-MP3 check.
Use **AI plan** for model-guided choices. See AI_SETUP.md. Coding-platform credentials are never inherited.

This is a usable development delivery with known gaps, not a claim of universal
plugin compatibility or finished musical/visual quality. Report a problem with the
job ID, steps, expected result and plugin name/version. Keep private audio and keys
out of public reports. Start with KNOWN_ISSUES.md and the acceptance ledger.
