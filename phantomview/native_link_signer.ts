/** NIP-98 formatting over a trusted native signer; no key or credential loading. */
import { createHash, randomBytes } from "node:crypto";
import { getEventHash, verifyEvent } from "nostr-tools/pure";

export interface AccessEventTemplate {
  kind: number;
  created_at: number;
  tags: string[][];
  content: string;
}

export interface NativeAccessSignerOptions {
  readonly origin: string;
  readonly publicKey: string;
  /** Fixed host closure using the already loaded native identity. Not a model tool. */
  readonly signEvent: (event: AccessEventTemplate, signal: AbortSignal) => Promise<unknown>;
}

export function nativeAccessAuthorization(options: NativeAccessSignerOptions) {
  const { origin, publicKey, signEvent } = options;
  const parsed = new URL(origin);
  if (parsed.protocol !== "https:" || parsed.origin !== origin
    || !/^[a-f0-9]{64}$/.test(publicKey) || typeof signEvent !== "function")
    throw new Error("Fixed native signing identity and canonical HTTPS origin required");
  const deny = () => new Error("Native access authorization unavailable");
  return async (signal: AbortSignal): Promise<string> => {
    if (signal.aborted) throw deny();
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(abort, 2000);
    let stopped!: () => void;
    const cancelled = new Promise<never>((_, reject) => {
      stopped = () => reject(deny());
      controller.signal.addEventListener("abort", stopped, { once: true });
    });
    try {
      if (signal.aborted) abort();
      if (controller.signal.aborted) throw deny();
      const event: AccessEventTemplate = { kind: 27235, created_at: Math.floor(Date.now() / 1000),
        tags: [["u", origin + "/api/access-link"], ["method", "POST"],
          ["payload", createHash("sha256").update("{}").digest("hex")],
          ["nonce", randomBytes(16).toString("hex")]], content: "" };
      const expected = JSON.stringify(event);
      // A native finalizer may mutate its template. Retain an independent expected value.
      const result = await Promise.race([
        Promise.resolve().then(() => {
          if (controller.signal.aborted) throw deny();
          return signEvent(JSON.parse(expected), controller.signal);
        }), cancelled,
      ]);
      if (controller.signal.aborted) throw deny();
      const raw = JSON.stringify(result);
      if (typeof raw !== "string" || Buffer.byteLength(raw) > 6000) throw deny();
      // Strip symbols/prototypes, including any cached verification marker from the provider.
      const signed = JSON.parse(raw);
      if (!signed || Object.keys(signed).sort().join(",") !== "content,created_at,id,kind,pubkey,sig,tags"
        || signed.pubkey !== publicKey || signed.kind !== event.kind || signed.content !== ""
        || signed.created_at !== event.created_at || Math.abs(Date.now() / 1000 - signed.created_at) > 60
        || JSON.stringify(signed.tags) !== JSON.stringify(event.tags)
        || !/^[a-f0-9]{64}$/.test(signed.id) || !/^[a-f0-9]{128}$/.test(signed.sig)
        || getEventHash(signed) !== signed.id || !verifyEvent(signed)) throw deny();
      const authorization = "Nostr " + Buffer.from(raw).toString("base64");
      if (authorization.length > 8192 || controller.signal.aborted) throw deny();
      return authorization;
    } catch { throw deny(); }
    finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      controller.signal.removeEventListener("abort", stopped);
    }
  };
}
