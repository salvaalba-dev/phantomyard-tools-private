/** Private control delivery: no reaction/history recorder and no automatic retry. */
export function validPrivateControl(channel: string, recipient: string, text: string): boolean {
  if (typeof recipient !== "string" || typeof text !== "string" || !text.length
    || Buffer.byteLength(text) > 2048) return false;
  if (channel === "telegram") return /^[1-9][0-9]{0,15}$/.test(recipient)
    && Number(recipient) <= Number.MAX_SAFE_INTEGER;
  return channel === "phantomchat" && /^[a-f0-9]{64}$/.test(recipient);
}

export async function privateControlSend(signal: AbortSignal,
  send: (signal: AbortSignal) => Promise<boolean>): Promise<boolean> {
  if (signal.aborted) return false;
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, 3000);
  let stop!: () => void;
  const cancelled = new Promise<boolean>(resolve => {
    stop = () => resolve(false);
    controller.signal.addEventListener("abort", stop, { once: true });
  });
  try {
    if (signal.aborted) abort();
    if (controller.signal.aborted) return false;
    const result = await Promise.race([send(controller.signal), cancelled]);
    return result === true && !controller.signal.aborted;
  } catch { return false; }
  finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", abort);
    controller.signal.removeEventListener("abort", stop);
  }
}

export async function privateControlResponse(response: Response): Promise<unknown> {
  if (!response.body) throw new Error("Control acknowledgement unavailable");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > 8192) throw new Error("Control acknowledgement unavailable");
      chunks.push(value);
    }
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

export interface PrivateControlTransport {
  sendPrivateControlMessage?(recipient: string, text: string, signal: AbortSignal): Promise<boolean>;
}

/** Fixed trusted host binding; never adapt ordinary sendMessage as a fallback. */
export function privateControlDelivery(channel: "telegram" | "phantomchat", origin: string,
  transport: PrivateControlTransport) {
  const url = new URL(origin);
  if (!["telegram", "phantomchat"].includes(channel) || url.protocol !== "https:"
    || url.origin !== origin || typeof transport?.sendPrivateControlMessage !== "function")
    throw new Error("Private control transport and canonical origin required");
  const send = transport.sendPrivateControlMessage.bind(transport);
  return async (requestedChannel: string, sender: string, link: string, signal: AbortSignal): Promise<boolean> => {
    if (requestedChannel !== channel || !validPrivateControl(channel, sender, link)
      || !link.startsWith(origin + "/#c=")
      || !/^[A-Za-z0-9_-]{43}$/.test(link.slice((origin + "/#c=").length))) return false;
    return privateControlSend(signal, inner => send(sender, link, inner));
  };
}
