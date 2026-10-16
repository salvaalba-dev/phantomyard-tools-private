"""Prepare a separate, screened text-worker variant in an offline pinned copy."""
from pathlib import Path
import sys

from native_host_review import review
from native_ingress_patch import replace_exact

HELPER = 'src/lib/phantomviewConversation.ts'
NOTE = '''

## Private ordinary conversation worker build

This separate variant accepts `__conversation-worker` compact UTF-8 JSON only
under a fixed nonroot worker UID/persona binding, before normal CLI credential
bootstrap. Its first slice accepts principal private text conversations only;
open/relay/shared contexts fail closed. It keeps persona files and channel-keyed
history, native untrusted screening/JEV and the configured native harness. It
never introduces a trusted flag. Tools, MCP, extensions, skills and prompt
templates are disabled in this variant. Hold metadata is emitted on stderr for
the protected process wrapper; ordinary diagnostics are discarded there.

Do not replace the normal installation binary or use this artifact as the scoped
PhantomView assistant: that path still requires projection-only ephemeral memory.
Provision a separate worker credential/configuration store containing no channel
or issuer secrets. The wrapper's environment and file hash are not isolation of
an existing shared persona vault. Ordinary queue/control parity, background
extraction, all execution paths and single native ingress ownership remain
required before any live cutover. Preserve the rule against per-persona supervisors.
'''


def patch(root):
    root = Path(root)
    review(root)  # Full baseline validation before any mutation.
    helper = root / HELPER
    if helper.exists() or helper.is_symlink():
        raise ValueError('Existing native worker helper; no patch applied')
    sources = {name: (root / name).read_text(encoding='utf-8') for name in
               ('src/index.ts', 'src/cli/ask.ts', 'src/harnesses/pi.ts')}
    entry = sources['src/index.ts']
    entry = replace_exact(entry, 'import { runMain, showUsage } from "citty";',
                          'import { runConversationStdin } from "./lib/phantomviewConversation.ts";\n'
                          'import { runMain, showUsage } from "citty";')
    entry = replace_exact(entry, 'if (process.argv[2] === EMBEDDED_PI_SUBCOMMAND) {',
                          'if (process.argv[2] === "__conversation-worker") {\n'
                          '  process.exitCode = await runConversationStdin();\n'
                          '} else if (process.argv[2] === EMBEDDED_PI_SUBCOMMAND) {')
    sources['src/index.ts'] = entry
    ask = sources['src/cli/ask.ts']
    ask = replace_exact(ask, '  if (harnesses.length === 0) {',
                        '  harnesses = harnesses.filter(h => h.id === "native");\n'
                        '  if (harnesses.length === 0) {')
    ask = replace_exact(ask, '      userMessage: prompt,',
                        '      userMessage: prompt,\n      toolsMode: "none",\n'
                        '      mcpMode: "none",\n      replyAudience: "private",')
    ask = replace_exact(ask, 'if (chunk.type === "done") {',
                        'if (chunk.type === "done") {\n'
                        '        if (chunk.meta?.screenedHold === true) err.write("\\nPHANTOMVIEW_HELD\\n");')
    sources['src/cli/ask.ts'] = ask
    pi = sources['src/harnesses/pi.ts']
    pi = replace_exact(pi, '      if (existsSync(managedExtDir)) {',
                       '      if (req.toolsMode !== "none" && existsSync(managedExtDir)) {')
    pi = replace_exact(pi, '        argv.push("--no-tools");',
                       '        argv.push("--no-tools", "--no-extensions", "--no-skills", "--no-prompt-templates");')
    sources['src/harnesses/pi.ts'] = pi
    sources[HELPER] = Path(__file__).with_name('native_conversation_entry.ts').read_text(encoding='utf-8')
    for name in ('README.md', 'AGENTS.md'):
        sources[name] = (root / name).read_text(encoding='utf-8') + NOTE
    for name, source in sources.items():
        (root / name).write_text(source, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 native_conversation_patch.py /offline/pinned/source')
    patch(sys.argv[1])
    print('Prepared separate native text worker; no live service or ingress enabled')
