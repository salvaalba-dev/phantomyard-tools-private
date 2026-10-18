/** Real one-shot process lifecycle with a synthetic reader-client response. */
import { afterEach, beforeEach, expect, mock, test } from "bun:test";
import { mkdtemp, readFile, rm, writeFile, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { nativeLinkCallback, type NativeLinkOptions } from "../../phantomview/native_link_callback.ts";
import { npubEncode } from "../src/lib/nostrIdentity.ts";

let root: string, script: string, capture: string;
const origin = "https://view.example:8790", link = origin + "/#c=" + "a".repeat(43);
beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "phantomview-native-link-"));
  script = join(root, "client.py"); capture = join(root, "frame.json");
  await helper();
});
afterEach(async () => { await rm(root, { recursive: true, force: true }); });
async function helper(response: unknown = { schema_version: 1, link }, delay = 0) {
  await writeFile(script, `import json,sys,time
raw=json.load(sys.stdin)
with open(${JSON.stringify(capture)},'w') as stream: json.dump({'frame':raw,'argv':sys.argv[1:]},stream)
time.sleep(${delay})
print(${JSON.stringify(JSON.stringify(response))})
`);
}
function options(changes: Partial<NativeLinkOptions> = {}): NativeLinkOptions {
  const uid = process.getuid!();
  return { persona: "coordinator", channel: "telegram", scopeId: "river-project", origin,
    issuerUid: uid, readerUid: uid + 10000, modelUids: [uid + 10001],
    python: Bun.which("python3")!, clientScript: script, socketPath: join(root, "unused.sock"),
    signAuthorization: async () => "Nostr synthetic-event", encodeNpub: npubEncode,
    deliverDirect: async () => true, ...changes };
}
function context(changes = {}) {
  return { channel: "telegram" as const, persona: "coordinator", sender: "101",
    messageId: "42", sentAt: Math.floor(Date.now() / 1000), command: "/phantomview", ...changes };
}
const signal = () => new AbortController().signal;

test("one-shot framing keeps authorization and human identity out of argv and returns no link", async () => {
  const delivery = mock(async () => true), callback = nativeLinkCallback(options({ deliverDirect: delivery }));
  expect(await callback(context(), signal())).toBeUndefined();
  expect(delivery.mock.calls[0]).toEqual(["telegram", "101", link, expect.any(AbortSignal)]);
  const captured = JSON.parse(await readFile(capture, "utf8"));
  expect(captured.frame).toEqual({ schema_version: 1, authorization: "Nostr synthetic-event",
    channel: "telegram", sender: "101", direct: true, principal_authenticated: true, scope_id: "river-project" });
  expect(captured.argv).not.toContain("101");expect(captured.argv).not.toContain("Nostr synthetic-event");
});

test("whole-daemon trust is explicit and does not claim isolated model accounts", async () => {
  expect(() => nativeLinkCallback(options({ modelUids: [] }))).toThrow();
  expect(() => nativeLinkCallback(options({ trustBoundary: "daemon" }))).toThrow();
  const delivery = mock(async () => true);
  await nativeLinkCallback(options({ trustBoundary: "daemon", modelUids: [], deliverDirect: delivery }))
    (context(), signal());
  const captured = JSON.parse(await readFile(capture, "utf8"));
  const at = captured.argv.indexOf("--trust-boundary");
  expect(captured.argv[at + 1]).toBe("daemon");
  expect(captured.argv).not.toContain("--model-uid");
  expect(delivery.mock.calls).toHaveLength(1);
});

test("PhantomChat uses the existing native npub encoder for policy but native hex for direct delivery", async () => {
  const sender = "a".repeat(64), delivery = mock(async () => true);
  const callback = nativeLinkCallback(options({ channel: "phantomchat", deliverDirect: delivery }));
  await callback(context({ channel: "phantomchat", sender, messageId: "b".repeat(64) }), signal());
  expect(JSON.parse(await readFile(capture, "utf8")).frame.sender).toBe(npubEncode(sender));
  expect(delivery.mock.calls[0][1]).toBe(sender);
});

test("context mutation during signing cannot change the delivery recipient", async () => {
  let finish!: (value: string) => void;
  const signed = new Promise<string>(resolve => { finish = resolve; });
  const delivery = mock(async () => true), input = context();
  const callback = nativeLinkCallback(options({ signAuthorization: () => signed, deliverDirect: delivery }));
  const pending = callback(input, signal());input.sender = "102";input.persona = "other";
  finish("Nostr synthetic-event");await pending;
  expect(JSON.parse(await readFile(capture, "utf8")).frame.sender).toBe("101");
  expect(delivery.mock.calls[0][1]).toBe("101");
});

test("wrong context, stale source and pre-cancellation never reach signing", async () => {
  const sign = mock(async () => "Nostr synthetic-event"), callback = nativeLinkCallback(options({ signAuthorization: sign }));
  for (const changes of [{ persona: "other" }, { command: "/other" }, { channel: "phantomchat" },
    { sender: "00101" }, { messageId: "0" }, { sentAt: 1 }])
    await expect(callback(context(changes), signal())).rejects.toThrow("Native link handoff unavailable");
  const controller = new AbortController();controller.abort();
  await expect(callback(context(), controller.signal)).rejects.toThrow();expect(sign).not.toHaveBeenCalled();
});

test("cancelled process cannot deliver a late link", async () => {
  await helper({ schema_version: 1, link }, 4);
  const delivery = mock(async () => true), controller = new AbortController();
  const pending = nativeLinkCallback(options({ deliverDirect: delivery }))(context(), controller.signal);
  const rejected = expect(pending).rejects.toThrow("Native link handoff unavailable");
  for (let i = 0; i < 100; i++) {
    try { await access(capture);break; } catch { await Bun.sleep(5); }
  }
  controller.abort();await rejected;expect(delivery).not.toHaveBeenCalled();
});

test("wrong origins, query credentials, extra fields and failed acknowledgement never deliver success", async () => {
  const delivery = mock(async () => true), callback = nativeLinkCallback(options({ deliverDirect: delivery }));
  for (const response of [{ schema_version: 1, link: "https://other.example/#c=" + "a".repeat(43) },
    { schema_version: 1, link: origin + "/?c=" + "a".repeat(43) },
    { schema_version: 1, link, human: "owner" }, { schema_version: true, link }]) {
    await helper(response);await expect(callback(context(), signal())).rejects.toThrow();
  }
  expect(delivery).not.toHaveBeenCalled();await helper();
  await expect(nativeLinkCallback(options({ deliverDirect: async () => false }))(context(), signal())).rejects.toThrow();
  await expect(nativeLinkCallback(options({ signAuthorization: async () => { throw Error("PRIVATE_SENTINEL"); } }))
    (context(), signal())).rejects.toThrow("Native link handoff unavailable");
});

test("shared accounts and unbound or insecure configuration are refused", () => {
  for (const changes of [{ readerUid: process.getuid!() }, { modelUids: [process.getuid!()] },
    { modelUids: [] }, { origin: "http://view.example" }, { scopeId: "" }, { python: "python3" }])
    expect(() => nativeLinkCallback(options(changes))).toThrow();
});
