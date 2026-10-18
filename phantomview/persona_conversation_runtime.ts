/** Optional local conversation listener inside the existing native daemon. */
import { createServer, type Socket } from "node:net";
import { chmod, chown, lstat, unlink } from "node:fs/promises";
import { dirname, isAbsolute, resolve } from "node:path";
import { runAsk } from "../cli/ask.ts";

export interface PersonaConversationRoute {
  readonly persona: string;
  readonly socketPath: string;
  readonly groupId: number;
  readonly issuerUid: number;
}
const MAX_REQUEST = 16384, MAX_RESPONSE = 64000;

function parse(raw: Buffer) {
  const text = new TextDecoder("utf-8", { fatal: true }).decode(raw);
  const value = JSON.parse(text);
  if (!value || JSON.stringify(value) !== text || Object.keys(value).sort().join(",") !==
      "conversation,evidence,question,request_id,schema_version" || value.schema_version !== 1
    || typeof value.request_id !== "string" || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value.request_id)
    || typeof value.conversation !== "string" || !/^phantomview:[a-f0-9]{64}$/.test(value.conversation)
    || typeof value.question !== "string" || !value.question.trim() || [...value.question].length > 1800
    || !Array.isArray(value.evidence) || value.evidence.length > 8) throw Error("Invalid conversation request");
  for (const row of value.evidence) {
    if (!row || Object.keys(row).sort().join(",") !== "excerpt,id,kind,trust"
      || row.trust !== "untrusted" || typeof row.id !== "string" || !/^[a-f0-9]{64}$/.test(row.id)
      || typeof row.kind !== "string" || !/^[a-z-]{1,32}$/.test(row.kind)
      || typeof row.excerpt !== "string" || [...row.excerpt].length > 1000) throw Error("Invalid viewer evidence");
  }
  return value;
}

async function protectedParent(route: PersonaConversationRoute) {
  if (process.platform !== "linux" || !Number.isSafeInteger(route.issuerUid) || route.issuerUid <= 0
    || process.getuid?.() !== route.issuerUid || !Number.isSafeInteger(route.groupId) || route.groupId <= 0
    || typeof route.persona !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(route.persona)
    || !isAbsolute(route.socketPath) || resolve(route.socketPath) !== route.socketPath
    || Buffer.byteLength(route.socketPath) > 100) throw Error("Fixed native conversation route required");
  for (let path = dirname(route.socketPath); ; path = dirname(path)) {
    const info = await lstat(path);
    if (!info.isDirectory() || info.isSymbolicLink()) throw Error("Linked native socket parent");
    if (path === dirname(route.socketPath) &&
        (![0, route.issuerUid].includes(info.uid) || (info.mode & 0o022)))
      throw Error("Protected native socket parent required");
    if (dirname(path) === path) break;
  }
  try { await lstat(route.socketPath); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return; throw error; }
  throw Error("Existing socket path requires operator inspection");
}

/** The optional ask dependency is trusted test embedding, never a wire option. */
export async function startPersonaConversations(routes: readonly PersonaConversationRoute[], ask = runAsk) {
  const started: Array<{ close(): Promise<void> }> = [];
  const close = async () => { for (const runtime of started.toReversed()) await runtime.close(); };
  const names = new Set<string>(), paths = new Set<string>();
  if (!Array.isArray(routes) || routes.length > 64) throw Error("Bounded native conversation routes required");
  // Validate every descriptor before creating the first listener.
  const fixed = routes.map(route => Object.freeze({ ...route }));
  for (const route of fixed) {
    if (names.has(route.persona) || paths.has(route.socketPath)) throw Error("Duplicate conversation route");
    names.add(route.persona); paths.add(route.socketPath);
    await protectedParent(route);
  }
  try {
    for (const route of fixed) {
      const sockets = new Set<Socket>();
      let busy = false, ready = false, stamp: Awaited<ReturnType<typeof lstat>> | undefined;
      const server = createServer({ allowHalfOpen: true }, socket => {
        if (!ready || sockets.size >= 4) { socket.destroy(); return; }
        sockets.add(socket);
        const abort = new AbortController();
        socket.on("error", () => abort.abort());
        socket.on("end", () => { abort.abort(); socket.destroy(); });
        socket.on("close", () => { abort.abort(); sockets.delete(socket); });
        let frame = Buffer.alloc(0), expected = 0, dispatched = false;
        const timeout = setTimeout(() => socket.destroy(), 3000);
        socket.once("close", () => clearTimeout(timeout));
        const reply = (value: object) => {
          if (socket.destroyed) return;
          const raw = Buffer.from(JSON.stringify(value));
          if (raw.length > MAX_RESPONSE) { socket.destroy(); return; }
          const head = Buffer.alloc(4); head.writeUInt32BE(raw.length);
          socket.end(Buffer.concat([head, raw]));
        };
        socket.on("data", data => {
          if (dispatched || frame.length + data.length > MAX_REQUEST + 4) { socket.destroy(); return; }
          frame = Buffer.concat([frame, data]);
          if (frame.length >= 4 && !expected) {
            expected = frame.readUInt32BE(0);
            if (!expected || expected > MAX_REQUEST) { socket.destroy(); return; }
          }
          if (!expected || frame.length < expected + 4) return;
          dispatched = true; clearTimeout(timeout);
          if (frame.length !== expected + 4 || busy) { socket.destroy(); return; }
          let request: ReturnType<typeof parse>;
          try { request = parse(frame.subarray(4)); }
          catch { socket.destroy(); return; }
          busy = true;
          void (async () => {
            let text = "", done = false, held = false;
            const timer = setTimeout(() => { abort.abort(); socket.destroy(); }, 120000);
            try {
              const prompt = request.evidence.length ? JSON.stringify({ question: request.question,
                viewer_evidence: request.evidence, evidence_trust: "untrusted" }) : request.question;
              const code = await ask({ persona: route.persona, prompt, history: true, stream: false,
                conversation: request.conversation, signal: abort.signal,
                onCompletion: completion => { done = true; held ||= completion.screenedHold; },
                out: { write(value) {
                  text += String(value);
                  if (Buffer.byteLength(text) > 48000) throw Error("Native answer exceeds bound");
                  return true;
                } }, err: { write() { return true; } } });
              if (!abort.signal.aborted) reply({ schema_version: 1, request_id: request.request_id,
                persona: route.persona, status: code === 0 && done ? (held ? "held" : "complete") : "failed",
                text: code === 0 && done && !held ? text : "" });
            } catch {
              if (!abort.signal.aborted) reply({ schema_version: 1, request_id: request.request_id,
                persona: route.persona, status: "failed", text: "" });
            } finally { clearTimeout(timer); busy = false; }
          })();
        });
      });
      const runtime = { async close() {
        ready = false;
        for (const socket of sockets) socket.destroy();
        if (server.listening) await new Promise<void>((resolveClose, rejectClose) =>
          server.close(error => error ? rejectClose(error) : resolveClose()));
        if (stamp) {
          try {
            const current = await lstat(route.socketPath);
            if (current.isSocket() && current.dev === stamp.dev && current.ino === stamp.ino && current.uid === stamp.uid)
              await unlink(route.socketPath);
          } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
        }
      } };
      started.push(runtime);
      await new Promise<void>((resolveListen, rejectListen) => {
        server.once("error", rejectListen);
        server.listen(route.socketPath, () => { server.removeListener("error", rejectListen); resolveListen(); });
      });
      stamp = await lstat(route.socketPath);
      await chown(route.socketPath, -1, route.groupId);
      await chmod(route.socketPath, 0o660);
      ready = true;
      // Operational errors never expose diagnostics or an unauthenticated fallback.
      server.on("error", () => { for (const socket of sockets) socket.destroy(); });
    }
  } catch (error) { await close(); throw error; }
  return Object.freeze({ close });
}
