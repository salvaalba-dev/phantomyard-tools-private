# Standard viewer core and optional modules

This is the current product direction and supersedes earlier plans for replacing
ordinary PhantomBot conversation execution or requiring a separate persona memory.
PhantomView is a structured, linked visual window onto existing authorized data.
PhantomOrg remains the source of identity, counterparts, categories and scopes.
The initial interface is standard and generated from the authorized organization
projection; humans do not have to design menus during setup.

## Stable core

Reuse the existing session, source evidence, resource filtering, search, document,
graph and audit components. Read/import/refresh existing information through
adapters rather than duplicating the organization model. Changes in PhantomOrg
must affect the next authorized projection. A menu, count, search result, graph
endpoint, document or assistant context must never bypass backend filtering.
Presentation cannot grant access or independently classify unknown information.

PhantomView does not own a new persona identity, vault, memory, conversation
daemon or model configuration. Its default assistant is the existing runtime's
verified default persona. The intended integration delegates to that persona's
existing runtime, profile, shared knowledge policy, memory and JEV. Do not migrate
ordinary conversation history or add an inference service as a viewer prerequisite.
Assistant transport still requires verification against the actual supported
PhantomBot/PhantomBridge interface; no new compatible endpoint is assumed here.

Avoid source patches and dependencies on private engine implementation details
in the standard viewer integration. Version the adapter and detect incompatible
source formats explicitly. No integration can promise immunity to every upstream
change, but the viewer/module contract must remain independent of engine internals.

## Optional modules

A module adds a declarative group of views to the standard interface. Installation
does not replace the core, add an ACL matrix, create a persona, grant a tool or
start a service. A project module can group partners and tasks; another can expose
different existing resource kinds. Sections with no visible records are omitted.
Data sources and future operational connectors need separate reviewed adapter
contracts; a manifest cannot point the server at arbitrary URLs or files.

`viewer_modules.py` defines manifest and viewer API version 1. The first contract
accepts a bounded ID, version, plain-text label, applicable PhantomOrg scope kinds,
sections using existing record kinds/renderers and an optional assistant persona.
Unknown fields, scripts, commands, source URLs, embedded permissions, conflicting
IDs and unsupported versions fail. `example-project-module.json` is synthetic.
This increment has no package installer, dynamic code loader or browser endpoint.

The registry compiles navigation from a current **server-owned, already authorized**
projection and a validated existing session. It is not a replacement ACL filter.
Never compile counts from a raw catalog or accept the projection/default report
from browser JSON. Core sections are standard; module section IDs are namespaced.
No record payload, hidden record count or raw source path is added to navigation.

## Assistant selection

The core inherits the verified default persona of the selected PhantomBot runtime.
If that observation is unavailable, core navigation remains usable and its
assistant is marked ineligible; no alternate persona is guessed.
A module may select another existing PhantomOrg persona for that module only.
The core default, session identity, issuing persona and other modules do not change.
The selected assistant must have a declared grant for the current scope.

The initial route check uses existing counterpart/scope eligibility. A future
server-owned adapter can resolve additional native human/persona routing authority
from the existing system, while still respecting the target persona's scope.
That callback is not a second browser-configurable permission matrix. Unknown or
unauthorized assistants fail closed; an override never silently falls back to a
different persona. Switching assistants must not manufacture a new human identity.

The emitted `eligible` flag is policy metadata, not connection readiness or an
inference authorization. Before every consultation, the eventual transport adapter
must revalidate the session, current PhantomOrg authority, selected assistant,
human/persona scope and the information actually supplied and returned. Link
issuance does not by itself enforce answer confidentiality. The viewer must show
which persona and module scope are active. Writes require existing independent
operation authorization; read access and category zero do not imply write rights.

## Existing experimental implementation

The ordinary forwarding, private native builds, credential-store and workspace
modules remain experimental, inactive research components. They are not standard
installation requirements and must not drive the viewer's deployment plan. Keep
their tests and history for traceability; do not deploy or continue extending them
as a replacement for existing persona conversation. Existing live AU behavior has
not been changed by this direction or the declarative registry.

Next integration work: verify the smallest existing read/conversation adapters,
connect registry navigation to the viewer shell, add explicit module lifecycle
support, and validate allowed/denied organization and project views end to end.
Resource synchronization should reuse the existing collection/refresh mechanisms.
