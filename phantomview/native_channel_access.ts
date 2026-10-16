/** Opt-in pre-model adapter. This class neither authenticates transports nor isolates a host. */
import { npubEncode } from "../../lib/nostrIdentity.ts";
import type { ChannelMessage } from "./types.ts";

export interface NativeAccessContext {
  readonly channel: "telegram" | "phantomchat";
  readonly sender: string;
  readonly message_id: string;
  readonly sent_at: number;
  readonly text: "/phantomview";
  readonly direct: true;
  readonly principal_authenticated: true;
  readonly scope_id: string;
}

export interface NativeAccessOptions {
  readonly persona: string;
  readonly scopeId: string;
  readonly issuerUid: number;
  readonly readerUid: number;
  readonly modelUids: readonly number[];
  /** Protected host callback: fixed signer/IPC/direct delivery; never a model tool. */
  readonly request: (context: NativeAccessContext, signal: AbortSignal) => Promise<void>;
}

export class NativeAccessRouter {
  private readonly options: NativeAccessOptions;
  private readonly seen = new Map<string, number>();
  private attempts: Array<{ at: number; sender: string }> = [];

  constructor(options: NativeAccessOptions) {
    this.options = Object.freeze({ ...options, modelUids: Object.freeze([...options.modelUids]) });
    this.assertPersona(options.persona);
  }

  assertPersona(persona: string): void {
    const o = this.options;
    const uid = process.getuid?.();
    const positive = (value: unknown): value is number =>
      typeof value === "number" && Number.isSafeInteger(value) && value > 0;
    if (process.platform !== "linux" || !positive(uid) || uid !== o.issuerUid
      || !positive(o.readerUid) || o.readerUid === uid || !o.modelUids.length
      || o.modelUids.some(value => !positive(value) || value === uid || value === o.readerUid)
      || typeof o.persona !== "string" || !o.persona || o.persona !== persona
      || typeof o.scopeId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(o.scopeId)
      || typeof o.request !== "function") {
      throw new Error("Native access requires fixed persona/scope and isolated channel, reader and model accounts");
    }
  }

  async consume(channel: "telegram" | "phantomchat", message: ChannelMessage & {
    chatType?: string; voice?: unknown; attachment?: unknown;
  }, principal: boolean, signal?: AbortSignal): Promise<boolean> {
    // False is the only model fallthrough; all reserved variants are consumed.
    if (typeof message.text !== "string" || !/^\s*\/phantomview(?:\s|@|$)/i.test(message.text)) return false;
    try { this.assertPersona(this.options.persona); } catch { return true; }
    if (message.text.trim() !== "/phantomview" || principal !== true || signal?.aborted
      || message.media || message.voice || message.attachment || message.reaction || message.groupId
      || message.conversationId !== message.senderId) return true;
    const source = message.sourceMessage;
    if (!source || !Number.isSafeInteger(source.sentAt) || source.sentAt <= 0
      || Math.abs(Date.now() / 1000 - source.sentAt) > 60) return true;
    let sender: string;
    if (channel === "telegram") {
      if (message.chatType !== "private" || !/^[1-9][0-9]{0,15}$/.test(message.senderId)
        || Number(message.senderId) > Number.MAX_SAFE_INTEGER || !/^[1-9][0-9]{0,15}$/.test(source.id)
        || Number(source.id) > Number.MAX_SAFE_INTEGER) return true;
      sender = message.senderId;
    } else if (channel === "phantomchat") {
      if (!/^[a-f0-9]{64}$/.test(message.senderId) || !/^[a-f0-9]{64}$/.test(source.id)) return true;
      sender = npubEncode(message.senderId);
    } else return true;
    const now = performance.now(), budgetKey = channel + ":" + sender;
    for (const [key, expiry] of this.seen) if (expiry <= now) this.seen.delete(key);
    this.attempts = this.attempts.filter(attempt => now - attempt.at < 60_000);
    const key = budgetKey + ":" + source.id;
    if (this.seen.has(key) || this.seen.size >= 256 || this.attempts.length >= 16
      || this.attempts.filter(attempt => attempt.sender === budgetKey).length >= 3) return true;
    this.seen.set(key, now + 120_000);
    this.attempts.push({ at: now, sender: budgetKey });
    const context: NativeAccessContext = Object.freeze({ channel, sender, message_id: source.id,
      sent_at: source.sentAt, text: "/phantomview", direct: true,
      principal_authenticated: true, scope_id: this.options.scopeId });
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(abort, 5000);
    let stop: (() => void) | undefined;
    const cancelled = new Promise<void>((_, reject) => {
      stop = () => reject(new Error("Native access cancelled"));
      controller.signal.addEventListener("abort", stop, { once: true });
    });
    try {
      // Observe a concurrent shutdown before starting protected host work.
      if (signal?.aborted) abort();
      await Promise.race([Promise.resolve().then(() => {
        if (!controller.signal.aborted) return this.options.request(context, controller.signal);
      }), cancelled]);
    } catch {
      // No error text, credential, signed event or link reaches logging/model fallback.
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      if (stop) controller.signal.removeEventListener("abort", stop);
    }
    return true;
  }
}

export function verifyNativeAccess(router: NativeAccessRouter | undefined, persona: string): void {
  if (router === undefined) return;
  if (!(router instanceof NativeAccessRouter)) throw new Error("A native access router is required");
  router.assertPersona(persona);
}
