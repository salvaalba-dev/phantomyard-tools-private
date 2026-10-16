/** Pinned native model/SQLite/screen path, with synthetic providers only. */
import { afterEach, beforeEach, expect, spyOn, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseConversation, runConversation } from "../src/lib/phantomviewConversation.ts";
import type { Config } from "../src/config.ts";
import type { Harness, HarnessChunk, HarnessRequest } from "../src/harnesses/types.ts";

let root: string, config: Config, calls: HarnessRequest[], output: string, errors: string;
const originalFetch = globalThis.fetch;
const oldPersona = process.env.PHANTOMVIEW_WORKER_PERSONA;
const oldUid = process.env.PHANTOMVIEW_WORKER_UID;
const sentinel = "AUTHORIZED_PERSONA_MEMORY_FIXTURE";

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "native-conversation-test-"));
  const agent = join(root, "personas", "guide");
  await mkdir(agent, { recursive: true });
  await writeFile(join(agent, "BOOT.md"), sentinel);
  config = { defaultPersona: "guide", personasDir: join(root, "personas"),
    memoryDbPath: join(root, "memory.sqlite"), configPath: join(root, "config.toml"),
    harnessIdleTimeoutMs: 5000, harnessHardTimeoutMs: 5000,
    harnesses: { chain: ["native"], pi: { bin: "pi", maxPayloadBytes: 20000 } },
    channels: {}, embeddings: { provider: "none" }, voice: { provider: "none" },
  } as unknown as Config;
  process.env.PHANTOMVIEW_WORKER_PERSONA = "guide";
  process.env.PHANTOMVIEW_WORKER_UID = String(process.getuid!());
  calls = []; output = ""; errors = "";
});

afterEach(async () => {
  globalThis.fetch = originalFetch;
  if (oldPersona === undefined) delete process.env.PHANTOMVIEW_WORKER_PERSONA;
  else process.env.PHANTOMVIEW_WORKER_PERSONA = oldPersona;
  if (oldUid === undefined) delete process.env.PHANTOMVIEW_WORKER_UID;
  else process.env.PHANTOMVIEW_WORKER_UID = oldUid;
  await rm(root, { recursive: true, force: true });
});

function document(changes: Record<string, unknown> = {}) {
  return { schema_version: 1, kind: "ordinary-turn", job_id: "a".repeat(32), persona: "guide",
    channel: "telegram", sender: "101", conversation: "101", tier: "principal", audience: "private",
    text: "Explain the project", ...changes };
}

function harness(score = 0, decisionModel = false): Harness {
  return { id: "native", available: async () => true,
    async *invoke(req: HarnessRequest): AsyncGenerator<HarnessChunk> {
      calls.push(req);
      yield { type: "done", finalText: !decisionModel && calls.length % 2 === 1
        ? JSON.stringify({ score, reason: "fixture", question: "" }) : "Native project answer" };
    } };
}

function ask(doc = document(), h = harness()) {
  return runConversation(JSON.stringify(doc), { config, harnesses: [h],
    out: { write(text) { output += text; return true; } },
    err: { write(text) { errors += text; return true; } } });
}

test("principal labels retain native screening, persona material and tool-less execution", async () => {
  expect(await ask()).toBe(0);
  expect(calls).toHaveLength(2);
  expect(output).toContain("Native project answer");
  expect(JSON.stringify(calls)).toContain(sentinel);
  expect(calls[1].userMessage).toBe("Explain the project");
  for (const req of calls) expect(req.toolsMode).toBe("none");
});

test("actual persona SQLite history survives separate native invocations", async () => {
  const h = harness();
  expect(await ask(document(), h)).toBe(0);
  expect(await ask(document({ job_id: "b".repeat(32), text: "Continue the explanation" }), h)).toBe(0);
  expect(calls).toHaveLength(4);
  expect(JSON.stringify(calls[3].history)).toContain("Explain the project");
  expect(JSON.stringify(calls[3].history)).toContain("Native project answer");
});

test("cross-persona, shared, relay, open and access-command contexts never invoke a model", async () => {
  for (const changes of [{ persona: "other" }, { tier: "relay", audience: "shared" },
    { tier: "open", audience: "shared" }, { audience: "shared" }, { text: "/phantomview" },
    { sender: "202" }, { kind: "issue-access" }, { authorization: "forbidden" }]) {
    expect(await ask(document(changes))).toBe(2);
  }
  expect(calls).toHaveLength(0);
  expect(output).toBe("");
});

test("canonical bounded JSON rejects duplicates and forged UID binding", async () => {
  const raw = JSON.stringify(document());
  expect(() => parseConversation(raw.replace('"tier":"principal"', '"tier":"principal","tier":"principal"'), "guide")).toThrow();
  expect(() => parseConversation(JSON.stringify(document({ text: "x".repeat(32769) })), "guide")).toThrow();
  const uid = spyOn(process, "getuid").mockReturnValue(0);
  try { expect(await ask()).toBe(2); } finally { uid.mockRestore(); }
  expect(calls).toHaveLength(0);
});

test("native fallback judge hold never reaches the answer model", async () => {
  expect(await ask(document(), harness(95))).toBe(0);
  expect(calls).toHaveLength(1);
  expect(output).not.toContain("Native project answer");
  expect(errors).toContain("\nPHANTOMVIEW_HELD\n");
});

test("configured native JEV hold remains active for a principal", async () => {
  config.jev = { provider: "openrouter", model: "typesafe/jev-1.13", baseUrl: "https://fixture.invalid/v1",
    keyEnv: "FIXTURE_KEY", apiKey: "fixture", judge: { enabled: true, threshold: 70, timeoutMs: 1000 },
    router: { enabled: false, timeoutMs: 300 } };
  let requests = 0;
  globalThis.fetch = (async () => {
    requests++;
    const score = { type: "score", score: 9, legend: {}, probabilities: {}, confidence: .9 };
    return new Response(JSON.stringify({ answers: { score, score_attacker: score,
      verdict: { type: "choice", choice: "hold", probabilities: {}, confidence: .9 } } }),
      { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  expect(await ask(document(), harness(0, true))).toBe(0);
  expect(requests).toBeGreaterThan(0);
  expect(calls).toHaveLength(0);
  expect(errors).toContain("\nPHANTOMVIEW_HELD\n");
});

test("canonical PhantomChat direct identity is accepted without an envelope identity override", () => {
  const hex = "a".repeat(64);
  expect(parseConversation(JSON.stringify(document({ channel: "phantomchat", sender: hex, conversation: hex })), "guide").sender).toBe(hex);
});
