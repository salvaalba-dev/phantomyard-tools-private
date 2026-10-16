"""Preserve source message provenance in a disposable pinned native checkout."""
import hashlib
from pathlib import Path
import sys

SOURCE_REVISION = '5af27060327ee8c53fe730dd8b98b6b305c62add'
INPUTS = {
    'src/channels/core/types.ts': '5c051c116ca8b50e1d9f7e3693a83f5bfdb2c644c3b0a3822de4256745de36c0',
    'src/channels/telegram/parse.ts': '1fd79fc11ee49fc49440a177cf1c2b0f7bac60709eb7dc0220ba90ed78dbf7f9',
    'src/channels/phantomchat/channel.ts': 'fb8ad1289ba6b7bf37e01a4af3f6a93caf123dac06814fb9994853ff0533c83a',
    'README.md': '802e64b2fffb4562f50a49911e814928829238ec6a8301b7d862c8abbd1aa8fe',
    'AGENTS.md': 'c5c6dee176c6c82abefd2d8f2a3e404a7b732e6ed22bd2aee9e15c01a27cd509',
}
HELPER = 'src/channels/core/sourceMessage.ts'
SOURCE = '''/** Transport-owned provenance, never a principal or access grant. */
export interface SourceMessage {
  readonly id: string;
  readonly sentAt: number;
}

function timestamp(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

export function telegramSourceMessage(id: unknown, date: unknown): SourceMessage | undefined {
  if (!timestamp(id) || !timestamp(date)) return undefined;
  return Object.freeze({ id: String(id), sentAt: date });
}

export function nostrSourceMessage(id: unknown, createdAt: unknown): SourceMessage | undefined {
  if (typeof id !== "string" || !/^[a-f0-9]{64}$/.test(id) || !timestamp(createdAt)) return undefined;
  return Object.freeze({ id, sentAt: createdAt });
}
'''
NOTE = '''

## Private source-message provenance variant

The private PhantomView integration preserves optional immutable `sourceMessage`
metadata on normalized messages: Telegram API message ID/date, or PhantomChat
canonical inner rumor ID/created_at after the existing verifying unwrap. It does
not use app-envelope delivery IDs/timestamps or randomized outer-wrap time for
access-command freshness. Missing or invalid provenance remains absent; never
substitute receipt time. Existing receipt IDs, parsing, crypto verification,
allowlists, group routing and ordinary model dispatch remain unchanged.

This metadata is not authentication or an ACL grant. A future isolated pre-model
host must still require verified direct allowlisted senders and independently
enforce protected reader/persona/scope policy. No native command, new poller,
per-persona supervisor, isolated host or live deployment is enabled by this patch.
'''


def replace_exact(source, old, new, count=1):
    if source.count(old) != count:
        raise ValueError('Unsupported native ingress source shape')
    return source.replace(old, new)


def patch(root):
    root = Path(root).resolve()
    names = [*INPUTS, HELPER]
    for name in names:
        target = root / name
        if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent != root):
            raise ValueError('Native patch paths must not contain symlinks')
    sources = {}
    for name, expected in INPUTS.items():
        source = (root / name).read_text(encoding='utf-8')
        if hashlib.sha256(source.encode()).hexdigest() != expected:
            raise ValueError('Unsupported native ingress source; no patch applied')
        sources[name] = source
    if (root / HELPER).exists():
        raise ValueError('Native provenance helper already exists; no patch applied')
    # Validate and prepare every source before writing any changed file.
    types = sources['src/channels/core/types.ts']
    sources['src/channels/core/types.ts'] = replace_exact(
        types, 'export interface ChannelMessage {',
        'export interface ChannelMessage {\n  /** Native source ID/time; not proof of principal authority. */\n'
        '  sourceMessage?: import("./sourceMessage.ts").SourceMessage;')
    telegram = sources['src/channels/telegram/parse.ts']
    telegram = replace_exact(telegram, 'import { xdgDataHome }',
                             'import { telegramSourceMessage } from "../core/sourceMessage.ts";\n'
                             'import { xdgDataHome }')
    telegram = replace_exact(telegram, '  message?: {\n    message_id?: number;',
                             '  message?: {\n    date?: number;\n    message_id?: number;')
    telegram = replace_exact(telegram, '    const chatType = normalizeChatType(msg.chat?.type);',
                             '    const chatType = normalizeChatType(msg.chat?.type);\n'
                             '    const sourceMessage = telegramSourceMessage(msg.message_id, msg.date);')
    telegram = replace_exact(telegram, '        updateId: u.update_id,',
                             '        updateId: u.update_id,\n'
                             '        ...(sourceMessage ? { sourceMessage } : {}),', count=3)
    sources['src/channels/telegram/parse.ts'] = telegram
    phantomchat = sources['src/channels/phantomchat/channel.ts']
    phantomchat = replace_exact(phantomchat, 'import { log }',
                               'import { nostrSourceMessage } from "../core/sourceMessage.ts";\nimport { log }')
    phantomchat = replace_exact(phantomchat, '        const senderHex = rumor.pubkey.toLowerCase();',
                               '        const senderHex = rumor.pubkey.toLowerCase();\n'
                               '        const sourceMessage = nostrSourceMessage(rumor.id, rumor.created_at);')
    phantomchat = replace_exact(phantomchat, '            senderId: senderHex,\n            text,',
                               '            senderId: senderHex,\n'
                               '            ...(sourceMessage ? { sourceMessage } : {}),\n            text,')
    phantomchat = replace_exact(phantomchat, '          senderId: senderHex,\n          text,',
                               '          senderId: senderHex,\n'
                               '          ...(sourceMessage ? { sourceMessage } : {}),\n          text,')
    sources['src/channels/phantomchat/channel.ts'] = phantomchat
    for name in ('README.md', 'AGENTS.md'):
        sources[name] += NOTE
    sources[HELPER] = SOURCE
    for name, source in sources.items():
        (root / name).write_text(source, encoding='utf-8', newline='\n')
    return {name: hashlib.sha256(source.encode()).hexdigest() for name, source in sources.items()}


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 native_ingress_patch.py /disposable/pinned/checkout')
    patch(sys.argv[1])
    print('Prepared private native provenance variant; no service or access enabled')
