/** Native signing with disposable keys and real Python verifier interoperability. */
import { expect, test } from "bun:test";
import { generateSecretKey, getPublicKey, finalizeEvent, verifyEvent } from "nostr-tools/pure";
import { resolve } from "node:path";
import { nativeAccessAuthorization } from "../src/channels/core/nativeLinkSigner.ts";

const origin = "https://view.example:8790";
const signal = () => new AbortController().signal;
function signer(change?: (event: any) => void) {
  const key = generateSecretKey(), publicKey = getPublicKey(key);
  const sign = nativeAccessAuthorization({ origin, publicKey,
    signEvent: async event => { change?.(event); return finalizeEvent(event, key); } });
  return { sign, publicKey, key };
}

test("native finalization preserves exact NIP-98 binding and fresh unique nonces", async () => {
  const { sign, publicKey } = signer();
  const first = await sign(signal()), second = await sign(signal());
  const event = JSON.parse(Buffer.from(first.slice(6), "base64").toString());
  expect(event.pubkey).toBe(publicKey); expect(event.kind).toBe(27235);
  expect(event.content).toBe(""); expect(verifyEvent(event)).toBe(true);
  expect(event.tags.slice(0, 3)).toEqual([["u", origin + "/api/access-link"], ["method", "POST"],
    ["payload", "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"]]);
  expect(event.tags[3][0]).toBe("nonce"); expect(event.tags[3][1]).toMatch(/^[a-f0-9]{32}$/);
  expect(first).not.toBe(second);
  expect(Object.keys(event).sort()).toEqual(["content", "created_at", "id", "kind", "pubkey", "sig", "tags"]);
});

test("even validly signed provider changes cannot replace request bindings", async () => {
  for (const change of [
    (event: any) => { event.kind = 1; }, (event: any) => { event.content = "alternate"; },
    (event: any) => { event.tags[0][1] = "https://other.example/api/access-link"; },
    (event: any) => { event.tags[2][1] = "0".repeat(64); },
    (event: any) => { event.tags.push(["human", "owner"]); },
    (event: any) => { event.created_at -= 1; },
  ]) await expect(signer(change).sign(signal())).rejects.toThrow("Native access authorization unavailable");
  const first = generateSecretKey(), second = generateSecretKey();
  await expect(nativeAccessAuthorization({ origin, publicKey: getPublicKey(first),
    signEvent: async event => finalizeEvent(event, second) })(signal())).rejects.toThrow("unavailable");
  await expect(nativeAccessAuthorization({ origin, publicKey: getPublicKey(first), signEvent: async event => {
    const signed = finalizeEvent(event, first);
    return { ...signed, sig: "0".repeat(128) };
  } })(signal())).rejects.toThrow("unavailable");
});

test("fixed options survive caller mutation and errors never expose provider details", async () => {
  const key = generateSecretKey();
  const options = { origin, publicKey: getPublicKey(key), signEvent: async (event: any) => finalizeEvent(event, key) };
  const sign = nativeAccessAuthorization(options); options.origin = "https://other.example";
  expect((await sign(signal())).startsWith("Nostr ")).toBe(true);
  const failed = nativeAccessAuthorization({ origin, publicKey: getPublicKey(key),
    signEvent: async () => { throw Error("PRIVATE_PROVIDER_SENTINEL"); } });
  try { await failed(signal()); throw Error("Expected refusal"); }
  catch (error) { expect(String(error)).toBe("Error: Native access authorization unavailable"); }
  expect(() => nativeAccessAuthorization({ ...options, origin: origin + "/path" })).toThrow();
});

test("cancellation prevents use of a late signed result", async () => {
  const key = generateSecretKey(), controller = new AbortController();
  let finish!: () => void, began!: () => void;
  const started = new Promise<void>(resolve => { began = resolve; });
  let calls = 0;
  const sign = nativeAccessAuthorization({ origin, publicKey: getPublicKey(key), signEvent: async event => {
    calls++; began(); await new Promise<void>(resolve => { finish = resolve; });
    return finalizeEvent(event, key);
  } });
  const pending = sign(controller.signal); await started; controller.abort();
  await expect(pending).rejects.toThrow("unavailable"); finish();
  await expect(sign(controller.signal)).rejects.toThrow("unavailable"); expect(calls).toBe(1);
});

test("native authorization reaches the real identified reader and retains single-use verification", async () => {
  const python = process.env.PHANTOMVIEW_SIGNER_PYTHON;
  if (!python) throw Error("The real-verifier fixture requires PHANTOMVIEW_SIGNER_PYTHON");
  const { sign, publicKey } = signer();
  const probe = resolve(import.meta.dir, "../../phantomview/native_link_signer_probe.py");
  const child = Bun.spawn([python, "-I", probe], { stdin: "pipe", stdout: "pipe", stderr: "pipe" });
  child.stdin.write(JSON.stringify({ origin, publicKey, authorization: await sign(signal()) }));
  child.stdin.end();
  const output = await new Response(child.stdout).text(), errors = await new Response(child.stderr).text();
  expect(await child.exited, errors).toBe(0);
  expect(JSON.parse(output)).toEqual({ verified: true, replay_denied: true, single_use: true,
    forged_signature_denied: true, recipient_bound: true });
}, 10000);
