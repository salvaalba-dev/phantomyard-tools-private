/** Native startup composition with synthetic identities and a disposable IPC probe. */
import { expect, test } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { verifyEvent } from "nostr-tools/pure";
import { generateIdentity } from "../src/lib/nostrIdentity.ts";
import { nativeListenerRuntime } from "../src/channels/core/nativeListenerRuntime.ts";
import { phantomViewStartupCommands } from "../src/channels/core/phantomViewStartup.ts";

test("both channels bind their own native signer and private transport without exposing credentials", async () => {
  const root = await mkdtemp(join(tmpdir(), "phantomview-startup-binding-"));
  try {
    const origin = "https://view.example:8790", link = origin + "/#c=" + "a".repeat(43);
    const script = join(root, "probe.py"), capture = join(root, "capture.json");
    await writeFile(script, `import json,sys
raw=json.load(sys.stdin)
with open(${JSON.stringify(capture)},'w') as f: json.dump({'frame':raw,'argv':sys.argv[1:]},f)
print(${JSON.stringify(JSON.stringify({ schema_version: 1, link }))})
`);
    const first = generateIdentity(), second = generateIdentity(), sender = generateIdentity();
    const uid = process.getuid!();
    const config = { scopeId: "river-project", origin, issuerUid: uid, readerUid: uid + 10000,
      python: Bun.which("python3")!, clientScript: script, socketPath: join(root, "unused.sock") };
    const registry = phantomViewStartupCommands([
      { ...config, persona: "coordinator", channel: "telegram" },
      { ...config, persona: "administrator", channel: "phantomchat" },
    ]);
    const delivered: string[][] = [];
    let ordinary = 0;
    for (const [channel, persona, identity, from, messageId] of [
      ["telegram", "coordinator", first, "101", "42"],
      ["phantomchat", "administrator", second, sender.publicKeyHex, "b".repeat(64)],
    ] as const) {
      const transport = { sendPrivateControlMessage: async (to: string, text: string) => {
        delivered.push([persona, to, text]); return true;
      }, sendMessage: async () => { ordinary++; } };
      const runtime = nativeListenerRuntime(transport, identity);
      expect(Object.keys(runtime)).not.toContain("secretKey");
      expect(runtime.transport).not.toBe(transport);
      expect(Object.keys(runtime.transport)).toEqual(["sendPrivateControlMessage"]);
      const command = registry.bind(channel, persona, () => runtime)!;
      expect(await command.consume(channel, { senderId: from, conversationId: from,
        text: "/phantomview", chatType: "private",
        sourceMessage: { id: messageId, sentAt: Math.floor(Date.now() / 1000) } }, true)).toBe(true);
      const captured = JSON.parse(await readFile(capture, "utf8"));
      const event = JSON.parse(Buffer.from(captured.frame.authorization.slice(6), "base64").toString());
      expect(event.pubkey).toBe(identity.publicKeyHex);
      expect(verifyEvent(event)).toBe(true);
      expect(captured.frame.sender).toBe(channel === "telegram" ? from : sender.npub);
      expect(captured.argv).not.toContain("--model-uid");
      expect(captured.argv[captured.argv.indexOf("--trust-boundary") + 1]).toBe("daemon");
      expect(delivered.at(-1)).toEqual([persona, from, link]);
    }
    expect(delivered).toHaveLength(2);
    expect(ordinary).toBe(0);
    expect(registry.bind("telegram", "unregistered", () => { throw Error("No fallback"); })).toBeUndefined();
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("missing native identity or private delivery capability refuses the configured route", () => {
  const uid = process.getuid!();
  const options = { persona: "coordinator", channel: "telegram" as const,
    scopeId: "river-project", origin: "https://view.example", issuerUid: uid,
    readerUid: uid + 10000, python: "/usr/bin/python3", clientScript: "/fixed/client.py",
    socketPath: "/fixed/reader.sock" };
  const missingIdentity = phantomViewStartupCommands([options]);
  expect(() => missingIdentity.bind("telegram", "coordinator", () =>
    nativeListenerRuntime({ sendPrivateControlMessage: async () => true }))).toThrow("existing native signing identity");
  const missingPrivate = phantomViewStartupCommands([options]);
  expect(() => missingPrivate.bind("telegram", "coordinator", () =>
    nativeListenerRuntime({}, generateIdentity()))).toThrow("Private control transport");
});
