/** Optional native command seam; authentication belongs to the calling channel loop.
 * No organization policy, signing, IPC, model tool or service is installed here.
 */
export interface AuthenticatedCommandContext {
  readonly channel: "telegram" | "phantomchat";
  readonly persona: string;
  /** Native channel identity: decimal Telegram user ID or verified Nostr hex key. */
  readonly sender: string;
  readonly messageId: string;
  readonly sentAt: number;
  readonly command: string;
}

export interface CommandMessage {
  senderId: string;
  conversationId: string;
  text?: string;
  chatType?: string;
  groupId?: string;
  media?: unknown;
  voice?: unknown;
  attachment?: unknown;
  reaction?: unknown;
  sourceMessage?: { id: string; sentAt: number };
}

export interface AuthenticatedCommandOptions {
  readonly persona: string;
  readonly command: string;
  /** Trusted embedding only. Never construct from model output or HTTP input. */
  readonly handle: (context: AuthenticatedCommandContext, signal: AbortSignal) => Promise<void>;
}

export class AuthenticatedCommand {
  private readonly options: AuthenticatedCommandOptions;
  private readonly seen = new Map<string, number>();
  private attempts: Array<{ at: number; sender: string }> = [];

  constructor(options: AuthenticatedCommandOptions) {
    if (!options || typeof options.persona !== "string"
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(options.persona)
      || typeof options.command !== "string" || !/^\/[a-z][a-z0-9_]{0,31}$/.test(options.command)
      || typeof options.handle !== "function") throw new Error("Fixed native command binding required");
    this.options = Object.freeze({ ...options });
  }

  assertPersona(persona: string): void {
    if (persona !== this.options.persona) throw new Error("Native command persona mismatch");
  }

  async consume(channel: "telegram" | "phantomchat", message: CommandMessage,
    principal: boolean, signal?: AbortSignal): Promise<boolean> {
    // Only false may reach ordinary dispatch. Reserved variants never reach a model.
    if (typeof message.text !== "string") return false;
    const command = this.options.command;
    const token = message.text.trimStart().split(/[\s@]/, 1)[0].toLowerCase();
    if (token !== command) return false;
    if (message.text.trim() !== command || principal !== true || signal?.aborted
      || message.groupId || message.media || message.voice || message.attachment || message.reaction
      || message.conversationId !== message.senderId) return true;
    const source = message.sourceMessage;
    if (!source || typeof source.id !== "string" || typeof message.senderId !== "string"
      || typeof message.conversationId !== "string" || !Number.isSafeInteger(source.sentAt) || source.sentAt <= 0
      || Math.abs(Date.now() / 1000 - source.sentAt) > 60) return true;
    if (channel === "telegram") {
      if (message.chatType !== "private" || !/^[1-9][0-9]{0,15}$/.test(message.senderId)
        || Number(message.senderId) > Number.MAX_SAFE_INTEGER || !/^[1-9][0-9]{0,15}$/.test(source.id)
        || Number(source.id) > Number.MAX_SAFE_INTEGER) return true;
    } else if (channel === "phantomchat") {
      if (!/^[a-f0-9]{64}$/.test(message.senderId) || !/^[a-f0-9]{64}$/.test(source.id)) return true;
    } else return true;
    const now = performance.now(), sender = channel + ":" + message.senderId;
    for (const [key, expiry] of this.seen) if (expiry <= now) this.seen.delete(key);
    this.attempts = this.attempts.filter(attempt => now - attempt.at < 60_000);
    const key = sender + ":" + source.id;
    if (this.seen.has(key) || this.seen.size >= 256 || this.attempts.length >= 16
      || this.attempts.filter(attempt => attempt.sender === sender).length >= 3) return true;
    this.seen.set(key, now + 120_000);
    this.attempts.push({ at: now, sender });
    const context = Object.freeze({ channel, persona: this.options.persona,
      sender: message.senderId, messageId: source.id, sentAt: source.sentAt, command });
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(abort, 5000);
    let stop: (() => void) | undefined;
    const cancelled = new Promise<void>((_, reject) => {
      stop = () => reject(new Error("Native command cancelled"));
      controller.signal.addEventListener("abort", stop, { once: true });
    });
    try {
      if (signal?.aborted) abort();
      await Promise.race([Promise.resolve().then(() => {
        if (!controller.signal.aborted) return this.options.handle(context, controller.signal);
      }), cancelled]);
    } catch {
      // A callback failure never leaks text or falls through to inference.
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      if (stop) controller.signal.removeEventListener("abort", stop);
    }
    return true;
  }
}

export function verifyAuthenticatedCommand(command: AuthenticatedCommand | undefined, persona: string): void {
  if (command === undefined) return;
  if (!(command instanceof AuthenticatedCommand)) throw new Error("Native command instance required");
  command.assertPersona(persona);
}
