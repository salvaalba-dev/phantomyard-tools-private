/** Pinned native source integration; no live provider or channel is contacted. */
import { afterEach, beforeEach, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runAsk } from "../src/cli/ask.ts";
import type { Config } from "../src/config.ts";
import type { Harness, HarnessChunk, HarnessRequest } from "../src/harnesses/types.ts";

let root: string;
let config: Config;
let calls: HarnessRequest[];
let output: string;
let errors: string;
const originalFetch = globalThis.fetch;
const sentinel = "PRIVATE_PERSONA_SENTINEL_MUST_NEVER_REACH_A_MODEL";

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "scoped-native-test-"));
  const agent = join(root, "personas", "example");
  await mkdir(join(agent, "memory"), { recursive: true });
  for (const file of ["BOOT.md", "SOUL.md", "MEMORY.md", "AGENTS.md", "memory/decisions.md", "memory/people.md", "memory/norms.md"])
    await writeFile(join(agent, file), sentinel);
  config = {
    defaultPersona: "example", personasDir: join(root, "personas"),
    memoryDbPath: join(root, "must-not-be-opened.sqlite"), configPath: join(root, "config.toml"),
    harnessIdleTimeoutMs: 5000, harnessHardTimeoutMs: 5000,
    harnesses: { chain: ["native"], pi: { bin: "pi", maxPayloadBytes: 20000 } },
    channels: {}, embeddings: { provider: "none" }, voice: { provider: "none" },
  } as unknown as Config;
  calls = []; output = ""; errors = "";
});

afterEach(async () => {
  globalThis.fetch = originalFetch;
  await rm(root, { recursive: true, force: true });
});

function harness(score = 0, jev = false): Harness {
  return { id: "native", available: async () => true,
    async *invoke(req: HarnessRequest): AsyncGenerator<HarnessChunk> {
      calls.push(req);
      yield { type: "done", finalText: !jev && calls.length === 1
        ? JSON.stringify({ score, reason: "fixture verdict", question: "" }) : "Authorized evidence answer" };
    } };
}

async function ask(h: Harness) {
  return runAsk({ config, persona: "example", conversation: "scoped:test", history: true,
    prompt: JSON.stringify({ kind: "scoped-consultation", question: "Explain the project", evidence: [{ excerpt: "AUTHORIZED_PROJECT_FACT" }] }),
    harnesses: [h], screen: async () => { throw new Error("Injected screen must be ignored"); },
    out: { write(text) { output += text; return true; } },
    err: { write(text) { errors += text; return true; } } });
}

test("native screen and answer see only neutral persona plus supplied evidence", async () => {
  expect(await ask(harness())).toBe(0);
  expect(calls).toHaveLength(2);
  expect(output).toContain("Authorized evidence answer");
  expect(JSON.stringify(calls)).not.toContain(sentinel);
  expect(calls[1].userMessage).toContain("AUTHORIZED_PROJECT_FACT");
  for (const req of calls) {
    expect(req.toolsMode).toBe("none");
    expect(req.history ?? []).toEqual([]);
    expect(req.workingDir).not.toBe(join(root, "personas", "example"));
    expect(existsSync(req.workingDir)).toBe(false);
  }
  expect(existsSync(config.memoryDbPath)).toBe(false);
});

test("a real native screened hold never invokes the answer harness", async () => {
  expect(await ask(harness(95))).toBe(0);
  expect(calls).toHaveLength(1);
  expect(output).not.toContain("Authorized evidence answer");
  expect(errors).toContain("\nPHANTOMVIEW_HELD\n");
  expect(JSON.stringify(calls)).not.toContain(sentinel);
});

function jev(score: number) {
  const bodies: string[] = [];
  config.jev = { provider: "openrouter", model: "typesafe/jev-1.13", baseUrl: "https://fixture.invalid/v1",
    keyEnv: "UNUSED_FIXTURE_KEY", apiKey: "fixture-key", judge: { enabled: true, threshold: 70, timeoutMs: 1000 },
    router: { enabled: false, timeoutMs: 300 } };
  globalThis.fetch = (async (_url, init) => {
    bodies.push(String(init?.body));
    const answer = { type: "score", score, legend: {}, probabilities: {}, confidence: 0.9 };
    return new Response(JSON.stringify({ answers: { score: answer, score_attacker: answer,
      verdict: { type: "choice", choice: score > 7 ? "hold" : "allow", probabilities: {}, confidence: 0.9 } } }),
      { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  return bodies;
}

test("configured JEV sees authorized input with no private persona briefing", async () => {
  const bodies = jev(0);
  expect(await ask(harness(0, true))).toBe(0);
  expect(bodies.length).toBeGreaterThan(0);
  expect(bodies.join("")).toContain("AUTHORIZED_PROJECT_FACT");
  expect(bodies.join("")).not.toContain(sentinel);
  expect(calls).toHaveLength(1);
  expect(output).toContain("Authorized evidence answer");
});

test("configured JEV hold is preserved without running the answering model", async () => {
  const bodies = jev(9);
  expect(await ask(harness(0, true))).toBe(0);
  expect(bodies.length).toBeGreaterThan(0);
  expect(calls).toHaveLength(0);
  expect(output).not.toContain("Authorized evidence answer");
  expect(errors).toContain("\nPHANTOMVIEW_HELD\n");
});

test("malformed JEV plus unreadable native fallback still holds without an answer", async () => {
  jev(10); // Deliberately outside the native decision model's 0-9 score scale.
  expect(await ask(harness(0, true))).toBe(0);
  expect(calls).toHaveLength(2); // Native judge and its format retry, never the answer turn.
  expect(output).not.toContain("Authorized evidence answer");
  expect(errors).toContain("\nPHANTOMVIEW_HELD\n");
});
