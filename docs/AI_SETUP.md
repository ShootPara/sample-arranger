# Connecting the local model

The owner authorized live app AI and the resources needed to connect it on
2026-11-04. This is no longer an approval hold. The app now has **AI plan** and
**AI connection** controls and matching shared CLI operations.

Use a dedicated broker inference principal named `sample-arranger`. Keep existing
coding credentials separate. The broker selects the model; the app sends no model,
provider, tool, shell, audio or image override. Only effective brief text and compact
musical features cross the verified connection. Catalog paths, recordings, plugin
state and rendering remain local. There is no automatic cloud/raw-provider fallback.

In **AI connection**, enter the verified HTTPS broker address, its existing public
CA certificate file if required, and the dedicated app token. Save protects the
token with Windows current-user DPAPI outside the repository and projects, then
checks the authenticated broker status. Configuration presence is not proof of
live successful inference. Do not paste credentials into chat, source, prompts or
public reports. Old protected credential files are retained locally on replacement;
they are not copied into projects or public packages.

**AI plan** uses the effective/refined brief. Local rules keep accepted duration,
key, tempo, exclusions, exact note lifecycles and source identities authoritative.
Built-in mode asks the model for a bounded phrase progression/rhythm and realizes
it through the deterministic compiler over the accepted song form. Sample mode
retrieves at most eight compatible candidates, hashes at most64MiB, sends compact
IDs/features without names/paths, and freshly resolves the validated selection.
Uncertain admission is not retried. One bounded semantic correction is allowed.
Cancellation distinguishes queued stop from running refusal/unknown execution.

The current natural-language timing/key constraints still use the local brief parser;
model proposals provide phrase intentions and sample decisions. Richer free-form
interpretation and varied phrase assembly remain follow-up scope. Existing **Build
plan** remains the explicit deterministic option; failures do not silently switch it.

CLI operations:

- `ai.status {}`: local configuration presence only; no network request or secret.
- `ai.connection.check {}`: authenticated broker status, no inference.
- `ai.score.plan {initial,intent,refined?}`: bounded model MIDI intentions realized
  as an editable score. `intent` supplies accepted timing/key/parts/form.
- `ai.samples.plan {catalog,initial,intent,refined?}`: local retrieval plus model
  sample decisions, returned as sections and freshly verified source bindings.

Use `contracts.schema` for structural requests. Both plan operations return a normal
reviewable plan; render through the existing project/job workflow.

## Server enrollment prerequisite

A working authorized operator on the AI Server must provision the dedicated
inference-only credential. Existing broker credentials are read at service startup
in the inspected source, so enrollment may require the server's managed drain and
recovery/reload procedure. Verify current live files first; do not edit a Drive
backup as though it were the running service. Preserve other principals, model,
network/firewall/security settings and paused/maintenance state. Never interrupt
active work or clear an uncertain quarantine just to enable the app.

For the server's existing Codex chat, the concrete instruction is:

> Enable a dedicated sample-arranger inference-only broker client for the owner's
> Windows app. Verify current configuration and healthy/idle state, use the existing
> managed enrollment/reload procedure, preserve coding clients/model/network settings,
> and supply the owner the app credential through an existing protected channel.
> Do not print secrets in chat or put them in source/cloud backups. Return the
> non-secret endpoint/CA setup and enrollment outcome. No broad tests or new services.

At this update, the saved remote chat failed to start with an internal absolute-path
error. SSH reached the machine but this client had no known host entry/authentication
setup, so host verification was preserved. No live enrollment or model request is
claimed until a working administrative session and dedicated credential are available.
The app's local HTTP fixture is not evidence of a live Trifecta connection.


## Sealed run-once handoff

The owner subsequently arranged for Dot on the server to run a supplied script.
`scripts/Enable-SampleArrangerAI.ps1` has Prepare/Server/Complete modes. Prepare
runs on the client using its existing verified broker endpoint and public CA;
it creates a3072-bit RSA key, retains the private half under current-user DPAPI
outside the project, and writes only a public request into ignored local data.
Server checks the owner-approved request hash, intended host, existing trusted CA,
healthy idle broker, protected existing storage and unchanged model/network config.
It creates/reuses only sample-arranger/inference, uses the existing managed reload
procedure if needed, checks authenticated TLS status and writes an RSA-OAEP-SHA256
sealed reply. It submits no inference. Complete imports that reply only on the
prepared Windows user, verifies request/endpoint/CA binding and writes the ordinary
DPAPI-protected app connection. No coding token or private key is copied.

The portable handoff folder contains the generic helper, public request, README
and a hash-pinned RUN-ON-TRIFECTA wrapper. It is ignored by Git. It may be copied
through the owner's chosen shared folder: only public information and the sealed
reply travel; the unencrypted broker token/private key do not. A sync/backup service
may retain that public/ciphertext material. The app private key remains local.
If server guards fail, report the safe stage/error type; never print private logs or
credential files into chat. Script host guards reflect this owner's measured setup;
cloners must deliberately adapt them and use their own broker/CA/identities.

Pending state is now the operator's sealed reply, not another permission request.
Do not claim live AI until Complete and one actual validated app inference succeed.
