"""Prepare an optional generic command seam in a disposable pinned checkout.

This is not an installer, native configuration option or live handoff activation.
"""
import hashlib
from pathlib import Path
import sys

import native_channel_patch as reviewed
import native_ingress_patch as provenance

INPUTS = reviewed.INPUTS | {
    'src/channels/commands.ts': 'd69a2953e7ecd4fa23868ffa47336285b39b5d410a3dd062d33adb6d0f7b2f22',
    'src/cli/run.ts': 'dd4463ad141598fe86f54fb1dd67ea0f9468c5a21ecf2c788f795ed557636122',
}
HELPER = 'src/channels/core/authenticatedCommand.ts'
REGISTRY = 'src/channels/core/authenticatedCommandRegistry.ts'
NOTE = """

## Private optional authenticated direct-command seam

An explicitly embedded `AuthenticatedCommand` may consume one fixed direct command
before model dispatch in Telegram or PhantomChat. The channel loop supplies its
existing explicit principal decision, receiving persona and source provenance.
No human registry, organization categories, ACL evaluator, signer, IPC listener,
model executor or additional service is added to PhantomBot by this variant.
With no handler, existing channel behavior remains unchanged.
Optional commands cannot replace any native control command. Source preparation
also verifies the pinned native dispatcher before adding the optional hook.

`runRun` accepts an optional `AuthenticatedCommandRegistry` from trusted host code.
It validates the registry before configuration loading and resolves each listener
by its actual channel and persona. The immutable registry has no default route,
rejects duplicates and never reads browser, model, environment or JSON claims.
This is a programmatic startup API, not CLI auto-discovery or an installed plugin.

The callback is trusted native embedding, never a model tool or browser identity
API. PhantomChat context uses its verified native hexadecimal sender ID; an
integration must use the existing NIP-19 encoder when resolving PhantomOrg npubs.
The callback must honor cancellation before signing, issuing or delivering links.
Its errors and return values never enter model context. This seam does not isolate
processes or turn a shared model/tool account into a protected issuer. Existing
handoff peer policies are unchanged; compatible protected transport and reviewed
PhantomOrg declarations remain required before identified-link activation.

This private source proposal targets the reviewed revision only. It is not applied
to a running installation and does not claim installed-version compatibility.
"""


def patch(root):
    root = Path(root).resolve()
    sources = {}
    for name, expected in (provenance.INPUTS | INPUTS).items():
        target = root / name
        if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent != root):
            raise ValueError('Native command paths must not contain symlinks')
        source = target.read_text(encoding='utf-8')
        if hashlib.sha256(source.encode()).hexdigest() != expected:
            raise ValueError('Unsupported native source; no command seam prepared')
        sources[name] = source
    for name in (HELPER, REGISTRY, provenance.HELPER, reviewed.HELPER):
        if (root / name).exists() or (root / name).is_symlink():
            raise ValueError('Existing native helper; use a fresh disposable checkout')
    helper = Path(__file__).with_name('authenticated_command.ts').read_text(encoding='utf-8')
    registry = Path(__file__).with_name('authenticated_command_registry.ts').read_text(encoding='utf-8')
    registry = provenance.replace_exact(registry, '"./authenticated_command.ts"',
                                        '"./authenticatedCommand.ts"')
    for name in reviewed.INPUTS:
        source = sources[name]
        telegram = name.endswith('engine.ts')
        relative = './authenticatedCommand.ts' if telegram else '../core/authenticatedCommand.ts'
        source = provenance.replace_exact(source,
            'export interface Run' + ('Telegram' if telegram else 'Phantomchat') + 'ServerInput {',
            'export interface Run' + ('Telegram' if telegram else 'Phantomchat') + 'ServerInput {\n'
            '  /** Optional trusted native binding; never populated from message content. */\n'
            '  authenticatedCommand?: AuthenticatedCommand;')
        anchor = '  const serverStartedAt = Date.now();' if telegram else '  const { channel } = input;'
        source = provenance.replace_exact(source, anchor,
            '  verifyAuthenticatedCommand(input.authenticatedCommand, input.persona);\n' + anchor)
        source = f'import {{ AuthenticatedCommand, verifyAuthenticatedCommand }} from "{relative}";\n' + source
        if telegram:
            anchor = '        const isVoice = Boolean(msg.voice);'
            source = provenance.replace_exact(source, anchor,
                '        if (input.authenticatedCommand && await input.authenticatedCommand.consume(\n'
                '          "telegram", msg, principalAuthenticated, input.signal)) continue;\n\n' + anchor)
        else:
            anchor = '  const allowedSet = new Set(input.allowedHex.map((h) => h.toLowerCase()));'
            source = provenance.replace_exact(source, anchor, anchor + '\n'
                '  const commandPrincipals = new Set(allowedSet); // Explicit startup identities; no TOFU. ')
            anchor = '  for await (const msg of channel.listen(input.signal)) {'
            source = provenance.replace_exact(source, anchor, anchor + '\n'
                '    if (input.authenticatedCommand && await input.authenticatedCommand.consume("phantomchat", msg,\n'
                '      commandPrincipals.size > 0 && commandPrincipals.has(msg.senderId.toLowerCase())\n'
                '        && !relaySet.has(msg.senderId.toLowerCase()), input.signal)) continue;')
        sources[name] = source
    entry = sources['src/cli/run.ts']
    entry = provenance.replace_exact(entry, 'export interface RunInput {',
        'export interface RunInput {\n'
        '  /** Fixed trusted host registration; never resolved from message or browser input. */\n'
        '  authenticatedCommands?: AuthenticatedCommandRegistry;')
    entry = provenance.replace_exact(entry,
        'export async function runRun(input: RunInput = {}): Promise<number> {',
        'export async function runRun(input: RunInput = {}): Promise<number> {\n'
        '  verifyAuthenticatedCommandRegistry(input.authenticatedCommands);')
    entry = provenance.replace_exact(entry, '        persona: l.persona,',
        '        persona: l.persona,\n'
        '        authenticatedCommand: input.authenticatedCommands?.resolve("telegram", l.persona),')
    entry = provenance.replace_exact(entry, '            persona: spec.persona,\n            runningPersonas,',
        '            persona: spec.persona,\n'
        '            authenticatedCommand: input.authenticatedCommands?.resolve("phantomchat", spec.persona),\n'
        '            runningPersonas,')
    sources['src/cli/run.ts'] = (
        'import { AuthenticatedCommandRegistry, verifyAuthenticatedCommandRegistry } '
        'from "../channels/core/authenticatedCommandRegistry.ts";\n' + entry)
    # All hashes, absent helpers and hook anchors are checked before any writes.
    provenance.patch(root)
    for name in reviewed.INPUTS:
        (root / name).write_text(sources[name], encoding='utf-8', newline='\n')
    (root / 'src/cli/run.ts').write_text(sources['src/cli/run.ts'], encoding='utf-8', newline='\n')
    (root / HELPER).write_text(helper, encoding='utf-8', newline='\n')
    (root / REGISTRY).write_text(registry, encoding='utf-8', newline='\n')
    for name in ('README.md', 'AGENTS.md'):
        target = root / name
        target.write_text(target.read_text(encoding='utf-8') + NOTE, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 authenticated_command_patch.py /disposable/pinned/checkout')
    patch(sys.argv[1])
    print('Prepared optional command seam; no channel, signer or live access activated')
