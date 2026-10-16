/** Dedicated private text-worker entry. No trusted-input flag or channel transport. */
import { runAsk, type RunAskInput } from "../cli/ask.ts";

const unavailable = "Native conversation unavailable\n";
const held = "\nPHANTOMVIEW_HELD\n";
export interface ConversationJob {
  schema_version: 1; kind: "ordinary-turn"; job_id: string; persona: string;
  channel: "telegram" | "phantomchat"; sender: string; conversation: string;
  tier: "principal"; audience: "private"; text: string;
}

function binding(): string {
  const persona = process.env.PHANTOMVIEW_WORKER_PERSONA;
  const uid = process.env.PHANTOMVIEW_WORKER_UID;
  if (process.platform !== "linux" || !persona || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(persona)
    || !uid || !/^[1-9][0-9]*$/.test(uid) || !Number.isSafeInteger(Number(uid))
    || process.getuid?.() !== Number(uid)) throw new Error(unavailable);
  return persona;
}

export function parseConversation(raw: string, persona: string): ConversationJob {
  if (typeof raw !== "string" || Buffer.byteLength(raw, "utf8") > 65536) throw new Error(unavailable);
  const doc = JSON.parse(raw);
  const fields = ["schema_version", "kind", "job_id", "persona", "channel", "sender",
    "conversation", "tier", "audience", "text"];
  // The protected Python writer supplies compact UTF-8 JSON. An exact round trip
  // rejects duplicate fields and alternate spellings without a permissive parser.
  if (!doc || typeof doc !== "object" || Array.isArray(doc) || JSON.stringify(doc) !== raw
    || Object.keys(doc).length !== fields.length || fields.some(key => !Object.hasOwn(doc, key))
    || doc.schema_version !== 1 || doc.kind !== "ordinary-turn" || doc.persona !== persona
    || typeof doc.job_id !== "string" || !/^[a-f0-9]{32}$/.test(doc.job_id)
    || !["telegram", "phantomchat"].includes(doc.channel) || typeof doc.sender !== "string"
    || doc.conversation !== doc.sender || doc.tier !== "principal" || doc.audience !== "private"
    || typeof doc.text !== "string" || !doc.text.trim() || Buffer.byteLength(doc.text, "utf8") > 32768
    || /^\s*\/phantomview(?:\s|@|$)/i.test(doc.text)) throw new Error(unavailable);
  if (doc.channel === "telegram"
    ? !/^[1-9][0-9]{0,15}$/.test(doc.sender) || !Number.isSafeInteger(Number(doc.sender))
    : !/^[a-f0-9]{64}$/.test(doc.sender)) throw new Error(unavailable);
  return Object.freeze(doc);
}

/** Test seams are not CLI options; neither screening nor trust is injectable here. */
export async function runConversation(raw: string,
  input: Pick<RunAskInput, "config" | "harnesses" | "out" | "err" | "signal"> = {}): Promise<number> {
  const err = input.err ?? process.stderr;
  try {
    const persona = binding();
    const job = parseConversation(raw, persona);
    const result = await runAsk({ config: input.config, harnesses: input.harnesses,
      out: input.out, signal: input.signal, persona, prompt: job.text,
      conversation: `${job.channel}:${job.conversation}`, history: true, stream: false,
      // A principal metadata label never disables the native untrusted-input screen.
      // Preserve only the trusted native hold marker; discard diagnostic contents.
      err: { write(text) { if (String(text).includes(held)) err.write(held); return true; } } });
    if (result !== 0) err.write(unavailable);
    return result;
  } catch {
    err.write(unavailable);
    return 2;
  }
}

export async function runConversationStdin(): Promise<number> {
  try {
    binding(); // Refuse before reading stdin or resolving persona configuration.
    if (process.argv.length !== 3 || process.stdin.isTTY) throw new Error(unavailable);
    let bytes = 0;
    const chunks: Buffer[] = [];
    for await (const chunk of process.stdin) {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      bytes += buffer.length;
      if (bytes > 65536) throw new Error(unavailable);
      chunks.push(buffer);
    }
    const raw = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks));
    return await runConversation(raw);
  } catch {
    process.stderr.write(unavailable);
    return 2;
  }
}
