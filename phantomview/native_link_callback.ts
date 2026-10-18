/** Bind a verified native command to the existing one-shot protected IPC client. */
import { spawn } from "node:child_process";
import { isAbsolute } from "node:path";
import type { AuthenticatedCommandContext } from "./authenticated_command.ts";

export interface NativeLinkOptions {
  readonly persona: string;
  readonly channel: "telegram" | "phantomchat";
  readonly scopeId: string;
  readonly origin: string;
  readonly issuerUid: number;
  readonly readerUid: number;
  readonly modelUids: readonly number[];
  /** Explicit daemon trust includes its tools/account. Omission preserves isolated mode. */
  readonly trustBoundary?: "isolated" | "daemon";
  readonly python: string;
  readonly clientScript: string;
  readonly socketPath: string;
  /** Existing native signer. No key, vault or credential-store copy is accepted. */
  readonly signAuthorization: (signal: AbortSignal) => Promise<string>;
  /** Existing native NIP-19 encoder; never supplied by a message or browser. */
  readonly encodeNpub: (hex: string) => string;
  /** Send only to the verified native sender. Require explicit delivery acknowledgement. */
  readonly deliverDirect: (channel: "telegram" | "phantomchat", sender: string,
    link: string, signal: AbortSignal) => Promise<boolean>;
}

export function nativeLinkCallback(options: NativeLinkOptions) {
  const o = Object.freeze({ ...options, modelUids: Object.freeze([...options.modelUids]) });
  const positive = (value: unknown): value is number =>
    typeof value === "number" && Number.isSafeInteger(value) && value > 0;
  const assertAccount = () => {
    const boundary = o.trustBoundary ?? "isolated";
    if (process.platform !== "linux" || !positive(process.getuid?.()) || process.getuid!() !== o.issuerUid
      || !positive(o.readerUid) || o.readerUid === o.issuerUid
      || !["isolated", "daemon"].includes(boundary)
      || (boundary === "daemon" ? o.modelUids.length !== 0 : (!o.modelUids.length
        || o.modelUids.some(uid => !positive(uid) || uid === o.readerUid || uid === o.issuerUid))))
      throw new Error("Configured native trust boundary and separate reader account required");
  };
  assertAccount();
  const origin = new URL(o.origin);
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(o.persona)
    || !["telegram", "phantomchat"].includes(o.channel)
    || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(o.scopeId)
    || origin.protocol !== "https:" || origin.origin !== o.origin
    || ![o.python, o.clientScript, o.socketPath].every(value => typeof value === "string" && isAbsolute(value))
    || ![o.signAuthorization, o.encodeNpub, o.deliverDirect].every(value => typeof value === "function"))
    throw new Error("Fixed native link callback configuration required");
  const argv = ["-I", o.clientScript, "--socket", o.socketPath, "--issuer-uid", String(o.issuerUid),
    "--reader-uid", String(o.readerUid), ...o.modelUids.flatMap(uid => ["--model-uid", String(uid)]),
    "--origin", o.origin, "--channel", o.channel, "--scope-id", o.scopeId];
  if (o.trustBoundary === "daemon") argv.push("--trust-boundary", "daemon");
  const deny = () => new Error("Native link handoff unavailable");

  function request(raw: string, signal: AbortSignal): Promise<string> {
    return new Promise((resolve, reject) => {
      if (signal.aborted) { reject(deny()); return; }
      // No shell, credentials in argv, CWD-derived module or inherited Python options.
      const child = spawn(o.python, argv, { stdio: ["pipe", "pipe", "ignore"],
        env: { PATH: "/usr/bin:/bin", LANG: "C.UTF-8" } });
      let output = Buffer.alloc(0), failed = false, force: ReturnType<typeof setTimeout> | undefined;
      const stop = () => {
        failed = true; child.kill("SIGTERM");
        if (!force) force = setTimeout(() => child.kill("SIGKILL"), 200);
      };
      signal.addEventListener("abort", stop, { once: true });
      const timer = setTimeout(stop, 3500);
      child.on("error", () => { failed = true; });
      child.stdin.on("error", () => { failed = true; });
      child.stdout.on("data", (data: Buffer) => {
        if (output.length + data.length > 2048) stop();
        else output = Buffer.concat([output, data]);
      });
      child.on("close", code => {
        clearTimeout(timer); if (force) clearTimeout(force);
        signal.removeEventListener("abort", stop);
        if (failed || code !== 0 || signal.aborted) { reject(deny()); return; }
        try {
          const result = JSON.parse(output.toString("utf8"));
          if (!result || Object.keys(result).sort().join(",") !== "link,schema_version"
            || result.schema_version !== 1 || typeof result.link !== "string") throw deny();
          const url = new URL(result.link);
          if (url.origin !== o.origin || url.username || url.password || url.pathname !== "/"
            || url.search || !/^#c=[A-Za-z0-9_-]{43}$/.test(url.hash)
            || result.link !== o.origin + "/" + url.hash) throw deny();
          resolve(result.link);
        } catch { reject(deny()); }
      });
      if (signal.aborted) stop();
      child.stdin.end(raw);
    });
  }

  return async (context: AuthenticatedCommandContext, signal: AbortSignal): Promise<void> => {
    try {
    assertAccount();
    context = Object.freeze({ ...context });
    if (signal.aborted || context.persona !== o.persona || context.channel !== o.channel
      || context.command !== "/phantomview" || !Number.isSafeInteger(context.sentAt)
      || context.sentAt <= 0 || Math.abs(Date.now() / 1000 - context.sentAt) > 60)
      throw deny();
    let sender = context.sender;
    if (o.channel === "telegram") {
      if (typeof sender !== "string" || !/^[1-9][0-9]{0,15}$/.test(sender)
        || Number(sender) > Number.MAX_SAFE_INTEGER || typeof context.messageId !== "string"
        || !/^[1-9][0-9]{0,15}$/.test(context.messageId)
        || Number(context.messageId) > Number.MAX_SAFE_INTEGER) throw deny();
    } else {
      if (typeof sender !== "string" || !/^[a-f0-9]{64}$/.test(sender)
        || typeof context.messageId !== "string" || !/^[a-f0-9]{64}$/.test(context.messageId)) throw deny();
      sender = o.encodeNpub(sender);
      if (!/^npub1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}$/.test(sender)) throw deny();
    }
    const authorization = await o.signAuthorization(signal);
    if (signal.aborted || typeof authorization !== "string" || !authorization.startsWith("Nostr ")
      || authorization.length > 12000) throw deny();
    const raw = JSON.stringify({ schema_version: 1, authorization, channel: o.channel, sender,
      direct: true, principal_authenticated: true, scope_id: o.scopeId });
    if (Buffer.byteLength(raw) > 16384) throw deny();
    const link = await request(raw, signal);
    assertAccount();
    if (signal.aborted) throw deny();
    if (await o.deliverDirect(o.channel, context.sender, link, signal) !== true) throw deny();
    // Never return a link, identity or signer output to the caller/model.
    } catch { throw deny(); }
  };
}
