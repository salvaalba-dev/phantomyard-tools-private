/** Real native dispatch loops, synthetic transports and no external model calls. */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { generateSecretKey, getPublicKey } from "nostr-tools/pure";
import { NativeAccessRouter, verifyNativeAccess, type NativeAccessContext } from "../src/channels/core/nativeAccess.ts";
import { runTelegramServer } from "../src/channels/core/engine.ts";
import { runPhantomchatServer } from "../src/channels/phantomchat/server.ts";
import { createPhantomchatChannel } from "../src/channels/phantomchat/channel.ts";
import { SimplePoolPhantomchatTransport } from "../src/channels/phantomchat/transport.ts";
import { wrapNip17Message, unwrapNip17Message, type NTNostrEvent } from "../src/lib/nostrCrypto.ts";
import { npubEncode } from "../src/lib/nostrIdentity.ts";
import { openMemoryStore } from "../src/memory/store.ts";

let root: string, agentDir: string, memory: Awaited<ReturnType<typeof openMemoryStore>>;
beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "phantomview-native-channel-"));
  agentDir = join(root, "personas", "phantom");
  await mkdir(agentDir, { recursive: true });
  await writeFile(join(agentDir, "BOOT.md"), "Synthetic persona");
  memory = await openMemoryStore(":memory:");
});
afterEach(async () => { await memory.close(); await rm(root, { recursive: true, force: true }); });

function options(request: (context: NativeAccessContext, signal: AbortSignal) => Promise<void>) {
  const uid = process.getuid!();
  return { persona: "phantom", scopeId: "river-project", issuerUid: uid,
    readerUid: uid + 10000, modelUids: [uid + 10001], request };
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

describe("protected native adapter", () => {
  test("startup rejects shared accounts, persona mismatch and plain callback objects", () => {
    const o = options(async () => {});
    for (const patch of [{ issuerUid: 0 }, { readerUid: o.issuerUid }, { modelUids: [o.issuerUid] },
      { modelUids: [o.readerUid] }, { modelUids: [] }, { modelUids: [0] }, { scopeId: "" }]) {
      expect(() => new NativeAccessRouter({ ...o, ...patch })).toThrow();
    }
    expect(() => verifyNativeAccess(new NativeAccessRouter(o), "other")).toThrow();
    expect(() => verifyNativeAccess({} as never, "phantom")).toThrow();
  });

  test("fixed source context, concurrent duplicate claim and explicit cancellation", async () => {
    const calls: NativeAccessContext[] = [];
    let started!: () => void;
    const began = new Promise<void>(resolve => { started = resolve; });
    const controller = new AbortController();
    const router = new NativeAccessRouter(options(async (context, signal) => {
      calls.push(context); started();
      await new Promise<void>(resolve => signal.addEventListener("abort", () => resolve(), { once: true }));
    }));
    const first = router.consume("telegram", message(), true, controller.signal);
    await began;
    expect(await router.consume("telegram", message(), true)).toBe(true);
    controller.abort();
    expect(await first).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual({ channel: "telegram", sender: "101", message_id: "42",
      sent_at: calls[0].sent_at, text: "/phantomview", direct: true,
      principal_authenticated: true, scope_id: "river-project" });
    expect(Object.isFrozen(calls[0])).toBe(true);
  });

  test("source, authority and command failures are consumed without host work", async () => {
    let calls = 0;
    const router = new NativeAccessRouter(options(async () => { calls++; }));
    for (const extra of [{ chatType: undefined }, { chatType: "group" }, { groupId: "room" },
      { conversationId: "other" }, { sourceMessage: undefined },
      { sourceMessage: { id: "42", sentAt: 1 } }, { voice: {} }, { media: {} },
      { text: "/phantomview other-scope" }, { text: "/phantomview@otherbot" }]) {
      expect(await router.consume("telegram", message(extra), true)).toBe(true);
    }
    expect(await router.consume("telegram", message(), false)).toBe(true);
    expect(await router.consume("telegram", message({ text: "ordinary text" }), true)).toBe(false);
    expect(calls).toBe(0);
  });

  test("callback exceptions never fall through and new attempts remain bounded", async () => {
    let calls = 0;
    const router = new NativeAccessRouter(options(async () => { calls++; throw Error("private synthetic grant"); }));
    for (let index = 0; index < 5; index++) {
      expect(await router.consume("telegram", message({ sourceMessage: {
        id: String(index + 1), sentAt: Math.floor(Date.now() / 1000) } }), true)).toBe(true);
    }
    expect(calls).toBe(3);
  });

  test("different senders cannot bypass the per-router budget", async () => {
    let calls = 0;
    const router = new NativeAccessRouter(options(async () => { calls++; }));
    for (let index = 0; index < 17; index++) {
      const sender = String(101 + index);
      expect(await router.consume("telegram", message({ senderId: sender, conversationId: sender }), true)).toBe(true);
    }
    expect(calls).toBe(16);
  });
});

describe("actual Telegram server dispatch", () => {
  test("a mismatched persona fails before starting the poller", async () => {
    let polled = false;
    await expect(runTelegramServer({ config: config(), memory, agentDir, persona: "other",
      harnesses: [], transport: { async getUpdates() { polled = true; } } as never,
      nativeAccess: new NativeAccessRouter(options(async () => {})) })).rejects.toThrow();
    expect(polled).toBe(false);
  });
  async function run(extra = {}, allowed = [101], fails = false, enabled = true) {
    const calls: NativeAccessContext[] = [], h = harness();
    const transport = { sent: [] as string[], async getUpdates() {
      return { updates: [message(extra)], reactions: [], nextOffset: 901 };
    }, async sendMessage(_id: string, text: string) { this.sent.push(text); }, async sendTyping() {} };
    const router = new NativeAccessRouter(options(async context => {
      calls.push(context); if (fails) throw Error("synthetic private error");
    }));
    await runTelegramServer({ config: config(allowed), memory, agentDir, persona: "phantom",
      harnesses: [h as never], transport: transport as never, oneShot: true,
      nativeAccess: enabled ? router : undefined });
    return { calls, h, transport };
  }
  test("principal DM reaches the host before any model turn", async () => {
    const result = await run();
    expect(result.calls).toHaveLength(1);
    expect(result.calls[0].channel).toBe("telegram");
    expect(result.calls[0].message_id).toBe("42");
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
  test("verified gift-wrap principal DM becomes canonical npub/source context before the model", async () => {
    const own = generateSecretKey(), peer = generateSecretKey(), ownHex = getPublicKey(own), peerHex = getPublicKey(peer);
    const pool = new Pool(), controller = new AbortController(), calls: NativeAccessContext[] = [], h = harness();
    const transport = new SimplePoolPhantomchatTransport(own, ["wss://relay.example"], pool as never);
    const channel = createPhantomchatChannel({ secretKey: own, publicKeyHex: ownHex, transport });
    const router = new NativeAccessRouter(options(async context => { calls.push(context); controller.abort(); }));
    const task = runPhantomchatServer({ config: config(), memory, agentDir, persona: "phantom",
      harnesses: [h as never], channel, secretKey: own, allowedHex: [peerHex], nativeAccess: router,
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
      expect(calls[0].sender).toBe(npubEncode(peerHex));
      expect(calls[0].message_id).toBe(rumor.id);
      expect(calls[0].sent_at).toBe(rumor.created_at);
      expect(calls[0].scope_id).toBe("river-project");
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
        nativeAccess: new NativeAccessRouter(options(async () => { calls++; })) });
      expect(calls).toBe(0); expect(h.calls).toBe(0); expect(claims).toBe(0);
    }
  });
});
