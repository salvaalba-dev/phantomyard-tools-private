/** Existing-daemon conversation framing, native completion and real reader client. */
import { expect, test } from "bun:test";
import { connect } from "node:net";
import { chmod, lstat, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { startPersonaConversations } from "../src/lib/phantomViewPersonaConversation.ts";
import { runAsk } from "../src/cli/ask.ts";
import { openMemoryStore } from "../src/memory/store.ts";
import type { Config } from "../src/config.ts";

const request = { schema_version: 1, request_id: "12345678-1234-1234-1234-123456789abc",
  conversation: "phantomview:" + "a".repeat(64), question: "Explain the organization", evidence: [] };
async function wire(path: string, value: unknown): Promise<any> {
  return await new Promise((resolve, reject) => {
    const socket = connect(path), chunks: Buffer[] = [];
    socket.on("error", reject);
    socket.on("data", part => chunks.push(part));
    socket.on("end", () => {
      try { const raw = Buffer.concat(chunks); resolve(JSON.parse(raw.subarray(4, 4 + raw.readUInt32BE(0)).toString())); }
      catch (error) { reject(error); }
    });
    socket.on("connect", () => { const raw = Buffer.from(JSON.stringify(value)); const head = Buffer.alloc(4);
      head.writeUInt32BE(raw.length); socket.write(Buffer.concat([head, raw])); });
    socket.setTimeout(4000, () => { socket.destroy(); reject(Error("Fixture timed out")); });
  });
}

test("fixed native persona, history and completion metadata survive the real socket", async () => {
  const root = await mkdtemp(join(tmpdir(), "pv-persona-"));
  const path = join(root, "persona.sock"), calls: any[] = [];
  const runtime = await startPersonaConversations([{ persona: "coordinator", socketPath: path,
    issuerUid: process.getuid!(), groupId: process.getgid!() }], async input => {
      calls.push(input); input.onCompletion?.({ screenedHold: input.prompt === "Hold this request" });
      input.out!.write("PHANTOMVIEW_HELD is ordinary generated text"); return 0;
    });
  try {
    expect((await lstat(path)).mode & 0o777).toBe(0o660);
    const answer = await wire(path, request);
    expect(answer.status).toBe("complete");
    expect(answer.persona).toBe("coordinator");
    expect(answer.text).toContain("PHANTOMVIEW_HELD");
    expect(calls[0].persona).toBe("coordinator");
    expect(calls[0].history).toBe(true);
    expect(calls[0].conversation).toBe(request.conversation);
    expect(calls[0].trusted).toBeUndefined();
    expect(calls[0].toolsMode).toBeUndefined();
    const held = await wire(path, { ...request, question: "Hold this request" });
    expect(held.status).toBe("held"); expect(held.text).toBe("");
    await expect(wire(path, { ...request, persona: "other" })).rejects.toThrow();
    expect(calls).toHaveLength(2);
  } finally { await runtime.close(); await rm(root, { recursive: true, force: true }); }
});

test("disconnect cancels native work and cleanup removes the owned socket", async () => {
  const root = await mkdtemp(join(tmpdir(), "pv-cancel-")), path = join(root, "persona.sock");
  let started!: () => void, stopped!: () => void;
  const ready = new Promise<void>(resolve => { started = resolve; });
  const done = new Promise<void>(resolve => { stopped = resolve; });
  const runtime = await startPersonaConversations([{ persona: "coordinator", socketPath: path,
    issuerUid: process.getuid!(), groupId: process.getgid!() }], async input => {
      started(); await new Promise<void>(resolve => input.signal!.addEventListener("abort", () => resolve(), { once: true }));
      stopped(); return 1;
    });
  try {
    const socket = connect(path), raw = Buffer.from(JSON.stringify(request)), head = Buffer.alloc(4);
    head.writeUInt32BE(raw.length); socket.write(Buffer.concat([head, raw])); await ready;
    socket.destroy(); await done;
    await runtime.close(); await expect(lstat(path)).rejects.toThrow();
  } finally { await runtime.close(); await rm(root, { recursive: true, force: true }); }
});

test("startup refuses a pre-existing operator file without replacing it", async () => {
  const root = await mkdtemp(join(tmpdir(), "pv-existing-")), path = join(root, "persona.sock");
  try {
    await writeFile(path, "Operator content");
    await expect(startPersonaConversations([{ persona: "coordinator", socketPath: path,
      issuerUid: process.getuid!(), groupId: process.getgid!() }])).rejects.toThrow();
    expect(await readFile(path, "utf8")).toBe("Operator content");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("runAsk exposes a native hold independently of generated text", async () => {
  const root = await mkdtemp(join(tmpdir(), "pv-ask-meta-"));
  const memory = await openMemoryStore(join(root, "memory.sqlite"));
  try {
    await mkdir(join(root, "personas", "coordinator"), { recursive: true });
    await writeFile(join(root, "personas", "coordinator", "BOOT.md"), "Synthetic persona");
    const config = { defaultPersona: "coordinator", personasDir: join(root, "personas"),
      configPath: join(root, "config.toml"), memoryDbPath: join(root, "memory.sqlite"),
      harnessIdleTimeoutMs: 5000, harnessHardTimeoutMs: 5000, harnessStartupTimeoutMs: 5000,
      harnesses: { chain: ["claude"], claude: { bin: "unused", model: "unused" }, pi: { bin: "unused", maxPayloadBytes: 1 } },
      channels: {}, embeddings: { provider: "none" }, voice: { provider: "none" } } as Config;
    const observed: boolean[] = [];
    const code = await runAsk({ config, memory, persona: "coordinator", prompt: "Synthetic held request",
      harnesses: [{ id: "fixture", available: async () => true,
        async *invoke() { throw Error("A held request must not invoke the turn harness"); } }],
      screen: async () => ({ action: "hold", score: 100, reason: "Synthetic hold", heldMessage: "Held" }),
      onCompletion: meta => observed.push(meta.screenedHold), out: { write: () => true }, err: { write: () => true } });
    expect(code).toBe(0); expect(observed).toEqual([true]);
  } finally { await memory.close(); await rm(root, { recursive: true, force: true }); }
});

test("the production Python client verifies the native account before sending", async () => {
  const root = await mkdtemp(join(tmpdir(), "pv-python-")), path = join(root, "persona.sock");
  await chmod(root, 0o750);
  const runtime = await startPersonaConversations([{ persona: "coordinator", socketPath: path,
    issuerUid: process.getuid!(), groupId: process.getgid!() }], async input => {
      input.onCompletion?.({ screenedHold: false }); input.out!.write("Native persona answer"); return 0;
    });
  try {
    const python = process.env.PHANTOMVIEW_SIGNER_PYTHON!, source = process.env.PHANTOMVIEW_SOURCE!;
    expect(python).toBeTruthy(); expect(source).toBeTruthy();
    const probe = `import json,os,sys,threading
sys.path.insert(0,${JSON.stringify(source)})
from persona_conversation import NativePersonaClient
os.setgroups([]);os.setgid(${process.getgid!()});os.setuid(29001)
client=NativePersonaClient(${JSON.stringify(path)},${process.getuid!()},'coordinator')
print(json.dumps(client.run(json.load(sys.stdin),cancelled=threading.Event())))
`;
    const child = Bun.spawn(["sudo", "-n", "--", python, "-c", probe], { stdin: "pipe", stdout: "pipe", stderr: "pipe" });
    child.stdin.write(JSON.stringify(request)); child.stdin.end();
    const [stdout, stderr, code] = await Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited]);
    expect(stderr).toBe(""); expect(code).toBe(0);
    expect(JSON.parse(stdout)).toEqual({ schema_version: 1, request_id: request.request_id,
      persona: "coordinator", status: "complete", text: "Native persona answer" });
  } finally { await runtime.close(); await rm(root, { recursive: true, force: true }); }
}, 15000);
