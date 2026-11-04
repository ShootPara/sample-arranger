# Maintaining Sample Arranger

Read docs/REQUIREMENTS.md, ARCHITECTURE.md, CLI_AND_BROKER.md, KNOWN_ISSUES.md and
DECISIONS_AND_MAINTENANCE.md before changing behavior. Preserve the reasoning behind
local-only deployment, bounded requests and data retention; functionality alone is
not enough to infer intent. Keep requirements, shared command schemas, setup and
known issues synchronized with changes.

Windows x64 is the supported local host. Desktop and CLI share commands; keep audio,
VST3/MIDI and retrieval local. Do not enable a network listener, cloud AI or inherit
coding-agent secrets. App inference requires its own explicitly approved identity.
Do not assume a cloner's model, hardware, paths, plugins or license permissions.

Normal jobs retain user-controlled folders; temporary normal sessions are distinct
from continuous playback, which has no save/export route and consumes/deletes owned
audio. Never delete source library assets during job cleanup. Plugin isolation is
process containment, not a filesystem security boundary or a retention guarantee.

Prefer free tools. Plugin/asset/runtime licenses differ from the AGPLv3 app source.
Do not publish private media, catalogs, credentials or operational history. Public
source publication does not automatically clear bundled third-party binaries.

Use bounded, meaningful verification appropriate to the change. Fix shipping
blockers and deliver usable improvements; do not turn known acceptance gaps into
endless rebuilds, repeated full suites or new long soaks. Preserve failed evidence
honestly and let user reports guide the next fixes. Do not change model/settings or
expand machine/security access without explicit authorization.
