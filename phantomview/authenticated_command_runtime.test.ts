/** Real native dispatch loops, synthetic transports and no external model calls. */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { generateSecretKey, getPublicKey } from "nostr-tools/pure";
import { AuthenticatedCommand, type AuthenticatedCommandContext } from "../src/channels/core/authenticatedCommand.ts";
import { runTelegramServer } from "../src/channels/core/engine.ts";
import { runPhantomchatServer } from "../src/channels/phantomchat/server.ts";
import { createPhantomchatChannel } from "../src/channels/phantomchat/channel.ts";
import { SimplePoolPhantomchatTransport } from "../src/channels/phantomchat/transport.ts";
import { wrapNip17Message, unwrapNip17Message, type NTNostrEvent } from "../src/lib/nostrCrypto.ts";
import { openMemoryStore } from "../src/memory/store.ts";
import { TELEGRAM_BOT_COMMANDS } from "../src/channels/commands.ts";

let root: string, agentDir: string, memory: Awaited<ReturnType<typeof openMemoryStore>>;
beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "phantomview-authenticated-command-"));
  agentDir = join(root, "personas", "phantom");
  await mkdir(agentDir, { recursive: true });
  await writeFile(join(agentDir, "BOOT.md"), "Synthetic persona");
  memory = await openMemoryStore(":memory:");
});
afterEach(async () => { await memory.close(); await rm(root, { recursive: true, force: true }); });

function options(request: (context: AuthenticatedCommandContext, signal: AbortSignal) => Promise<void>) {
  return { persona: "phantom", command: "/phantomview", handle: request };
}
function message(extra = {}) {
  return { conversationId: "101", senderId: "101", text: "/phantomview", chatType: "private",
    updateId: 900, sourceMessage: { id: "42", sentAt: Math.floor(Date.now() / 1000) }, ...extra };
}
function config(allowedUserIds = [101]) {
  return { defaultPersona: "phantom", personasDir: join(root, "personas"), memoryDbPath: ":memory:",
    configPath: join(root, "config.toml"), harnessIdleTimeoutMs: 5000,
    harnessHardTimeoutMs: 5000, harnessStartupTimeoutMs: 5000,
    harnesses: { chain: ["claude"], claude: { bin: "unused", model: "unused" },
      pi: { bin: "unused", maxPayloadBytes: 100000 } },
    channels: { telegram: { token: "synthetic", allowedUserIds, pollTimeoutS: 1 } },
    embeddings: { provider: "none" }, voice: { provider: "none" } } as never;
}
function harness() {
  const state = { calls: 0, id: "synthetic", available: async () => true,
    async *invoke() { state.calls++; yield { type: "text", text: "ordinary reply" };
      yield { type: "done", finalText: "ordinary reply", harness: "synthetic" }; } };
  return state;
}

test("every command in the real native dispatcher is protected from replacement", async () => {
  let calls = 0;
  const router = new AuthenticatedCommand(options(async () => { calls++; }));
  for (const { command } of TELEGRAM_BOT_COMMANDS) {
    const text = "/" + command;
    expect(() => new AuthenticatedCommand({ ...options(async () => {}), command: text }))
      .toThrow("cannot replace native control commands");
    for (const channel of ["telegram", "phantomchat"] as const)
      expect(await router.consume(channel, message({ text }), true)).toBe(false);
  }
  expect(calls).toBe(0);
});

describe("actual Telegram server dispatch", () => {
  test("a mismatched persona fails before starting the poller", async () => {
    let polled = false;
    await expect(runTelegramServer({ config: config(), memory, agentDir, persona: "other",
      harnesses: [], transport: { async getUpdates() { polled = true; } } as never,
      authenticatedCommand: new AuthenticatedCommand(options(async () => {})) })).rejects.toThrow();
    expect(polled).toBe(false);
  });
  async function run(extra = {}, allowed = [101], fails = false, enabled = true) {
    const calls: AuthenticatedCommandContext[] = [], h = harness();
    const transport = { sent: [] as string[], async getUpdates() {
      return { updates: [message(extra)], reactions: [], nextOffset: 901 };
    }, async sendMessage(_id: string, text: string) { this.sent.push(text); }, async sendTyping() {} };
    const router = new AuthenticatedCommand(options(async context => {
      calls.push(context); if (fails) throw Error("synthetic private error");
    }));
    await runTelegramServer({ config: config(allowed), memory, agentDir, persona: "phantom",
      harnesses: [h as never], transport: transport as never, oneShot: true,
      authenticatedCommand: enabled ? router : undefined });
    return { calls, h, transport };
  }
  test("principal DM reaches the host before any model turn", async () => {
    const result = await run();
    expect(result.calls).toHaveLength(1);
    expect(result.calls[0].channel).toBe("telegram");
    expect(result.calls[0].messageId).toBe("42");
    expect(result.h.calls).toBe(0);
    expect(result.transport.sent).toHaveLength(0);
  });
  test("groups, open bots and callback failures never enter the model", async () => {
    for (const [extra, allowed, fails] of [[{ chatType: "group" }, [101], false], [{}, [], false],
      [{}, [101], true], [{ sourceMessage: undefined }, [101], false]] as const) {
      const result = await run(extra, [...allowed], fails);
      expect(result.h.calls).toBe(0);
      expect(result.calls.length).toBe(fails ? 1 : 0);
    }
  });
  test("disabled binding and ordinary text preserve the ordinary model path", async () => {
    const disabled = await run({}, [101], false, false);
    const ordinary = await run({ text: "ordinary text" });
    expect(disabled.h.calls).toBeGreaterThan(0);
    expect(ordinary.h.calls).toBeGreaterThan(0);
    expect(ordinary.calls).toHaveLength(0);
  });
});

class Pool {
  onevent?: (event: NTNostrEvent) => void;
  subscribeMany(_relays: unknown, _filter: unknown, params: {
    onevent: (event: NTNostrEvent) => void; oneose?: () => void;
  }) { this.onevent = params.onevent; params.oneose?.(); return { close: () => { this.onevent = undefined; } }; }
  publish() { return [Promise.resolve("synthetic acceptance")]; }
  listConnectionStatus() { return new Map([["wss://relay.example", true]]); }
  close() {}
}

describe("actual PhantomChat server dispatch", () => {
  test("verified gift-wrap principal DM becomes verified native hex/source context before the model", async () => {
    const own = generateSecretKey(), peer = generateSecretKey(), ownHex = getPublicKey(own), peerHex = getPublicKey(peer);
    const pool = new Pool(), controller = new AbortController(), calls: AuthenticatedCommandContext[] = [], h = harness();
    const transport = new SimplePoolPhantomchatTransport(own, ["wss://relay.example"], pool as never);
    const channel = createPhantomchatChannel({ secretKey: own, publicKeyHex: ownHex, transport });
    const router = new AuthenticatedCommand(options(async context => { calls.push(context); controller.abort(); }));
    const task = runPhantomchatServer({ config: config(), memory, agentDir, persona: "phantom",
      harnesses: [h as never], channel, secretKey: own, allowedHex: [peerHex], authenticatedCommand: router,
      signal: controller.signal, fetchProfiles: async () => new Map() });
    const timer = setTimeout(() => controller.abort(), 2000);
    try {
      for (let index = 0; !pool.onevent && index < 50; index++) await Bun.sleep(5);
      expect(pool.onevent).toBeDefined();
      const wrap = wrapNip17Message(peer, ownHex, JSON.stringify({ type: "text", id: "claimed",
        from: "spoofed", timestamp: 1, content: "/phantomview" })).wraps[0] as unknown as NTNostrEvent;
      const rumor = unwrapNip17Message(wrap, own);
      pool.onevent!(wrap);
      await task;
      expect(calls).toHaveLength(1);
      expect(calls[0].sender).toBe(peerHex);
      expect(calls[0].messageId).toBe(rumor.id);
      expect(calls[0].sentAt).toBe(rumor.created_at);
      expect(calls[0].persona).toBe("phantom");
      expect(h.calls).toBe(0);
    } finally { clearTimeout(timer); controller.abort(); await task; }
  });

  test("relay, open, TOFU and group commands are consumed without host/model execution", async () => {
    for (const mode of ["relay", "open", "tofu", "group"]) {
      const own = generateSecretKey(), peerHex = getPublicKey(generateSecretKey()), h = harness();
      let calls = 0, claims = 0;
      const msg = { conversationId: peerHex, senderId: peerHex, text: "/phantomview",
        sourceMessage: { id: "a".repeat(64), sentAt: Math.floor(Date.now() / 1000) },
        ...(mode === "group" ? { groupId: "room", conversationId: "group:room" } : {}) };
      const channel = { transport: { async sendMessage() {}, async sendTyping() {} },
        capabilities: { voice: false, typing: false, encryption: true, attachments: false },
        async *listen() { yield msg; } };
      await runPhantomchatServer({ config: config(), memory, agentDir, persona: "phantom",
        harnesses: [h as never], channel: channel as never, secretKey: own,
        allowedHex: ["relay", "group"].includes(mode) ? [peerHex] : [],
        relayHex: mode === "relay" ? [peerHex] : [], tofu: mode === "tofu",
        persistTrust: async () => { claims++; }, fetchProfiles: async () => new Map(),
        authenticatedCommand: new AuthenticatedCommand(options(async () => { calls++; })) });
      expect(calls).toBe(0); expect(h.calls).toBe(0); expect(claims).toBe(0);
    }
  });
});
