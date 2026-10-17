"""Prepare an optional generic command seam in a disposable pinned checkout.

This is not an installer, native configuration option or live handoff activation.
"""
import hashlib
from pathlib import Path
import sys

import native_channel_patch as reviewed
import native_ingress_patch as provenance

INPUTS = reviewed.INPUTS
HELPER = 'src/channels/core/authenticatedCommand.ts'
NOTE = """

## Private optional authenticated direct-command seam

An explicitly embedded `AuthenticatedCommand` may consume one fixed direct command
before model dispatch in Telegram or PhantomChat. The channel loop supplies its
existing explicit principal decision, receiving persona and source provenance.
No human registry, organization categories, ACL evaluator, signer, IPC listener,
model executor or additional service is added to PhantomBot by this variant.
With no handler, existing channel behavior remains unchanged.

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
    for name in (HELPER, provenance.HELPER, reviewed.HELPER):
        if (root / name).exists() or (root / name).is_symlink():
            raise ValueError('Existing native helper; use a fresh disposable checkout')
    helper = Path(__file__).with_name('authenticated_command.ts').read_text(encoding='utf-8')
    for name in INPUTS:
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
    # All hashes, absent helpers and hook anchors are checked before any writes.
    provenance.patch(root)
    for name in INPUTS:
        (root / name).write_text(sources[name], encoding='utf-8', newline='\n')
    (root / HELPER).write_text(helper, encoding='utf-8', newline='\n')
    for name in ('README.md', 'AGENTS.md'):
        target = root / name
        target.write_text(target.read_text(encoding='utf-8') + NOTE, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 authenticated_command_patch.py /disposable/pinned/checkout')
    patch(sys.argv[1])
    print('Prepared optional command seam; no channel, signer or live access activated')
