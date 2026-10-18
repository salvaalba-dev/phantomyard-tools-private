/** Actual transports with mocked HTTP/relay IO; no production messages or keys. */
import { expect, test } from "bun:test";
import { generateSecretKey, getPublicKey } from "nostr-tools/pure";
import { HttpTelegramTransport } from "../src/channels/telegram/transport.ts";
import { SimplePoolPhantomchatTransport } from "../src/channels/phantomchat/transport.ts";
import { unwrapV2, type NTNostrEvent } from "../src/lib/nostrCrypto.ts";
import { privateControlDelivery } from "../src/channels/core/privateControl.ts";

const origin = "https://view.example:8790", link = origin + "/#c=" + "a".repeat(43);

test("Telegram requires API acceptance and never records or retries a control link", async () => {
  const originalFetch = globalThis.fetch;
  const transport = new HttpTelegramTransport("synthetic-token");
  let recorded = 0, calls = 0, body: any;
  transport.setOutboundRecorder(() => { recorded++; });
  try {
    globalThis.fetch = (async (_url: unknown, init: RequestInit) => {
      calls++; body = JSON.parse(init.body as string);
      return Response.json({ ok: true, result: { message_id: 42, chat: { id: 101, type: "private" } } });
    }) as typeof fetch;
    const deliver = privateControlDelivery("telegram", origin, transport);
    expect(await deliver("telegram", "101", link, new AbortController().signal)).toBe(true);
    expect(recorded).toBe(0); expect(calls).toBe(1);
    expect(body).toEqual({ chat_id: 101, text: link, protect_content: true,
      link_preview_options: { is_disabled: true } });
    for (const response of [new Response("denied", { status: 400 }), Response.json({ ok: false }),
      Response.json({ ok: true, result: { message_id: 42, chat: { id: 102, type: "private" } } }),
      new Response("x".repeat(8193))]) {
      const before = calls;
      globalThis.fetch = (async () => { calls++; return response; }) as typeof fetch;
      expect(await deliver("telegram", "101", link, new AbortController().signal)).toBe(false);
      expect(calls).toBe(before + 1); expect(recorded).toBe(0);
    }
    const controller = new AbortController(); controller.abort(); const before = calls;
    expect(await deliver("telegram", "101", link, controller.signal)).toBe(false);
    expect(calls).toBe(before);
  } finally { globalThis.fetch = originalFetch; }
});

test("PhantomChat encrypts to the exact peer without recording, read-back or rewrap retries", async () => {
  const own = generateSecretKey(), peer = generateSecretKey(), hex = getPublicKey(peer);
  const wraps: NTNostrEvent[] = []; let recorded = 0, reads = 0, reject = false;
  const pool = {
    publish(_relays: string[], event: NTNostrEvent) {
      wraps.push(event); return [reject ? Promise.reject(Error("synthetic denial")) : Promise.resolve("accepted")];
    },
    subscribeMany() { reads++; throw Error("Unexpected read-back"); },
    listConnectionStatus() { return new Map(); }, close() {},
  };
  const transport = new SimplePoolPhantomchatTransport(own, ["wss://relay.example"], pool as never);
  transport.setOutboundRecorder(() => { recorded++; });
  try {
    const deliver = privateControlDelivery("phantomchat", origin, transport);
    expect(await deliver("phantomchat", hex, link, new AbortController().signal)).toBe(true);
    expect(wraps).toHaveLength(1); expect(recorded).toBe(0); expect(reads).toBe(0);
    expect((await unwrapV2(wraps[0], peer)).content).toBe(link);
    expect(JSON.stringify(wraps[0])).not.toContain(link);
    reject = true;
    expect(await deliver("phantomchat", hex, link, new AbortController().signal)).toBe(false);
    expect(wraps).toHaveLength(2); expect(recorded).toBe(0); expect(reads).toBe(0);
    const controller = new AbortController(); controller.abort();
    expect(await deliver("phantomchat", hex, link, controller.signal)).toBe(false);
    expect(wraps).toHaveLength(2);
  } finally { transport.close(); }
});
