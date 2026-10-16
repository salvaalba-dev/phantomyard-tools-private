/** Run only in the disposable patched native checkout; no real channels. */
import { describe, expect, test } from "bun:test";
import { generateSecretKey, getPublicKey } from "nostr-tools/pure";
import { parseGetUpdatesResult } from "../src/channels/telegram/parse.ts";
import { telegramSourceMessage, nostrSourceMessage } from "../src/channels/core/sourceMessage.ts";
import { createPhantomchatChannel } from "../src/channels/phantomchat/channel.ts";
import { SimplePoolPhantomchatTransport } from "../src/channels/phantomchat/transport.ts";
import type { ChannelMessage } from "../src/channels/core/types.ts";
import { wrapNip17Message, unwrapNip17Message, type NTNostrEvent } from "../src/lib/nostrCrypto.ts";

describe("private source-message provenance", () => {
  test("Telegram keeps API provenance distinct from update IDs and supplied content", () => {
    const message = { message_id: 42, date: 1000, chat: { id: 101, type: "private" },
      from: { id: 101 }, text: "/phantomview", sourceMessage: { id: "spoofed", sentAt: 9999 } };
    const parsed = parseGetUpdatesResult({ ok: true, result: [{ update_id: 900, message }] });
    expect(parsed.updates[0].sourceMessage).toEqual({ id: "42", sentAt: 1000 });
    expect(parsed.updates[0].updateId).toBe(900);
    expect(parsed.updates[0].text).toBe("/phantomview");
    expect(parsed.updates[0].senderId).toBe("101");
    expect(Object.isFrozen(parsed.updates[0].sourceMessage)).toBe(true);
  });

  test("missing or invalid API provenance never becomes receipt time", () => {
    for (const fields of [{}, { message_id: 42 }, { date: 1000 }, { message_id: 0, date: 1000 },
      { message_id: 42, date: 1.5 }, { message_id: 42, date: "1000" }]) {
      const message = { chat: { id: 101 }, from: { id: 101 }, text: "ordinary text", ...fields };
      const parsed = parseGetUpdatesResult({ ok: true, result: [{ update_id: 1, message }] } as never);
      expect(parsed.updates[0].sourceMessage).toBeUndefined();
      expect(parsed.updates[0].text).toBe("ordinary text");
    }
  });

  test("media and group provenance remains metadata, without turning a group into a DM", () => {
    for (const content of [{ text: "/phantomview" }, { voice: { file_id: "voice" } },
      { document: { file_id: "doc", file_name: "data.txt" } }]) {
      const parsed = parseGetUpdatesResult({ ok: true, result: [{ update_id: 1, message: {
        message_id: 42, date: 1000, chat: { id: -101, type: "supergroup" }, from: { id: 101 }, ...content,
      } }] });
      expect(parsed.updates[0].sourceMessage).toEqual({ id: "42", sentAt: 1000 });
      expect(parsed.updates[0].chatType).toBe("supergroup");
      expect(parsed.updates[0].conversationId).toBe("-101");
    }
  });

  test("helpers refuse coercions, unsafe numbers and incomplete Nostr provenance", () => {
    for (const value of [undefined, null, true, "1000", 0, -1, 1.5, NaN, Infinity, 2 ** 53]) {
      expect(telegramSourceMessage(value, 1000)).toBeUndefined();
      expect(telegramSourceMessage(42, value)).toBeUndefined();
      expect(nostrSourceMessage("a".repeat(64), value)).toBeUndefined();
    }
    for (const id of ["", "claimed-id", "A".repeat(64), "a".repeat(63)]) {
      expect(nostrSourceMessage(id, 1000)).toBeUndefined();
    }
    expect(Object.isFrozen(nostrSourceMessage("a".repeat(64), 1000))).toBe(true);
  });
});

class Pool {
  onevent?: (event: NTNostrEvent) => void;
  subscribeMany(_relays: unknown, _filter: unknown, params: {
    onevent: (event: NTNostrEvent) => void; oneose?: () => void;
  }) {
    this.onevent = params.onevent;
    params.oneose?.();
    return { close: () => { this.onevent = undefined; } };
  }
  publish() { return [Promise.resolve("synthetic acceptance")]; }
  listConnectionStatus() { return new Map([["wss://relay.example", true]]); }
  close() {}
}

async function receive(content: string, mutate?: (event: NTNostrEvent) => NTNostrEvent) {
  const recipient = generateSecretKey(), sender = generateSecretKey(), pool = new Pool();
  const ownHex = getPublicKey(recipient), senderHex = getPublicKey(sender);
  const transport = new SimplePoolPhantomchatTransport(recipient, ["wss://relay.example"], pool as never);
  const channel = createPhantomchatChannel({ secretKey: recipient, publicKeyHex: ownHex, transport });
  const controller = new AbortController(), messages: ChannelMessage[] = [];
  const pump = (async () => {
    for await (const message of channel.listen!(controller.signal)) {
      messages.push(message);
      controller.abort();
    }
  })();
  const timer = setTimeout(() => controller.abort(), 1000);
  try {
    for (let index = 0; !pool.onevent && index < 50; index++) await Bun.sleep(5);
    expect(pool.onevent).toBeDefined();
    const wrap = wrapNip17Message(sender, ownHex, content).wraps[0] as unknown as NTNostrEvent;
    const rumor = unwrapNip17Message(wrap, recipient);
    pool.onevent!(mutate ? mutate(wrap) : wrap);
    await pump;
    return { messages, rumor, senderHex };
  } finally {
    clearTimeout(timer);
    controller.abort();
    await pump;
  }
}

describe("actual verifying PhantomChat adapter", () => {
  test("legacy app IDs/times and claimed sender never replace inner rumor provenance", async () => {
    const { messages, rumor, senderHex } = await receive(JSON.stringify({ type: "text",
      id: "claimed-delivery-id", timestamp: 1, from: "spoofed", content: "/phantomview" }));
    expect(messages).toHaveLength(1);
    expect(messages[0].sourceMessage).toEqual({ id: rumor.id, sentAt: rumor.created_at });
    expect(messages[0].messageId).toBe("claimed-delivery-id");
    expect(messages[0].senderId).toBe(senderHex);
    expect(Object.isFrozen(messages[0].sourceMessage)).toBe(true);
  });

  test("plain NIP-17 DMs retain canonical inner ID/time", async () => {
    const { messages, rumor } = await receive("/phantomview");
    expect(messages).toHaveLength(1);
    expect(messages[0].sourceMessage).toEqual({ id: rumor.id, sentAt: rumor.created_at });
    expect(messages[0].messageId).toBe(rumor.id);
  });

  test("a tampered wrap produces neither a message nor provenance", async () => {
    const { messages } = await receive("/phantomview", event => JSON.parse(JSON.stringify({ ...event,
      sig: (event.sig[0] === "0" ? "1" : "0") + event.sig.slice(1) })));
    expect(messages).toHaveLength(0);
  });
});
