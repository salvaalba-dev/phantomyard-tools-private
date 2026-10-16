"""Private opt-in pre-model hooks layered on the pinned provenance variant."""
import hashlib
from pathlib import Path
import sys

import native_ingress_patch as provenance

INPUTS = {
    'src/channels/core/engine.ts': 'c4013e2292d4b248092903dd9f953143a6bdd5ffb45595f5b1aaaedcafe9fea6',
    'src/channels/phantomchat/server.ts': 'db54a61f647a535bd562e133c9309d1bdfb825854e31fb577a59d2b416201917',
}
HELPER = 'src/channels/core/nativeAccess.ts'
NOTE = '''

## Private opt-in pre-model access adapters

Both Telegram and PhantomChat accept an optional protected `NativeAccessRouter`
binding. Startup rejects shared/root/unsupported account configurations and
persona mismatch before polling. Reserved `/phantomview` variants are consumed
before ordinary slash commands, voice processing, reactions or model dispatch.
Only explicit allowlisted direct senders with fresh source provenance reach the
fixed-scope host callback. PhantomChat uses a snapshot of its configured allowlist,
excludes relays and never uses TOFU to grant this command authority. The callback
must implement protected signing/IPC/direct delivery and honor cancellation;
no callback output or exception text becomes model input.

These hooks are inactive without explicit trusted embedding. They do not isolate
a daemon, implement the native host, connect a live signer, add CLI/config flags,
start a poller or alter ordinary behavior when absent. A shared model daemon must
not declare its own account safe. Preserve one channel consumer and the rule
against per-persona supervisors. Review every model/fallback entry point before
any reversible channel-ownership cutover.
'''


def patch(root):
    root = Path(root).resolve()
    sources = {}
    for name, expected in INPUTS.items():
        target = root / name
        if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent != root):
            raise ValueError('Native channel patch paths must not contain symlinks')
        source = target.read_text(encoding='utf-8')
        if hashlib.sha256(source.encode()).hexdigest() != expected:
            raise ValueError('Unsupported native channel source; no patch applied')
        sources[name] = source
    helper = root / HELPER
    if helper.exists() or helper.is_symlink():
        raise ValueError('Native access helper already exists; no patch applied')
    source_helper = Path(__file__).with_name('native_channel_access.ts').read_text(encoding='utf-8')
    for name, source in list(sources.items()):
        telegram = name.endswith('engine.ts')
        relative = './nativeAccess.ts' if telegram else '../core/nativeAccess.ts'
        source = provenance.replace_exact(source, 'export interface Run' + ('Telegram' if telegram else 'Phantomchat') + 'ServerInput {',
            'export interface Run' + ('Telegram' if telegram else 'Phantomchat') + 'ServerInput {\n'
            '  /** Inactive protected native host binding; never a model tool. */\n'
            '  nativeAccess?: NativeAccessRouter;')
        anchor = '  const serverStartedAt = Date.now();' if telegram else '  const { channel } = input;'
        source = provenance.replace_exact(source, anchor,
            '  verifyNativeAccess(input.nativeAccess, input.persona);\n' + anchor)
        source = f'import {{ NativeAccessRouter, verifyNativeAccess }} from "{relative}";\n' + source
        if telegram:
            anchor = '        const isVoice = Boolean(msg.voice);'
            source = provenance.replace_exact(source, anchor,
                '        if (input.nativeAccess && await input.nativeAccess.consume(\n'
                '          "telegram", msg, principalAuthenticated, input.signal)) continue;\n\n' + anchor)
        else:
            anchor = '  const allowedSet = new Set(input.allowedHex.map((h) => h.toLowerCase()));'
            source = provenance.replace_exact(source, anchor, anchor + '\n'
                '  const nativeAllowed = new Set(allowedSet); // Explicit startup allowlist; never TOFU. ')
            anchor = '  for await (const msg of channel.listen(input.signal)) {'
            source = provenance.replace_exact(source, anchor, anchor + '\n'
                '    if (input.nativeAccess && await input.nativeAccess.consume("phantomchat", msg,\n'
                '      nativeAllowed.size > 0 && nativeAllowed.has(msg.senderId.toLowerCase())\n'
                '        && !relaySet.has(msg.senderId.toLowerCase()), input.signal)) continue;')
        sources[name] = source
    # All additional hook replacements are prepared before the base patch writes.
    provenance.patch(root)
    sources[HELPER] = source_helper
    for name, source in sources.items():
        (root / name).write_text(source, encoding='utf-8', newline='\n')
    for name in ('README.md', 'AGENTS.md'):
        target = root / name
        target.write_text(target.read_text(encoding='utf-8') + NOTE, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 native_channel_patch.py /disposable/pinned/checkout')
    patch(sys.argv[1])
    print('Prepared private Telegram/PhantomChat hooks; no native host or live access enabled')
