/** Real native startup with temporary stores and stubbed channel transports. */
import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runRun } from "../src/cli/run.ts";
import { AuthenticatedCommandRegistry } from "../src/channels/core/authenticatedCommandRegistry.ts";
import type { Config } from "../src/config.ts";
import { generateIdentity } from "../src/lib/nostrIdentity.ts";
import { savePhantomchatPersonaConfig } from "../src/channels/phantomchat/personaStore.ts";
import { nativeAccessAuthorization } from "../src/channels/core/nativeLinkSigner.ts";
import { verifyEvent } from "nostr-tools/pure";

test("a registry-shaped JSON object fails before startup or configuration reads", async () => {
  await expect(runRun({ authenticatedCommands: {} as never })).rejects.toThrow("registry instance");
});

test("runtime startup binds the exact Telegram transport and already loaded persona signer", async () => {
  const folder = await mkdtemp(join(tmpdir(), "phantomview-runtime-startup-"));
  const previousState = process.env.PHANTOMBOT_STATE;
  process.env.PHANTOMBOT_STATE = join(folder, "state.json");
  try {
    for (const persona of ["coordinator", "administrator"]) {
      const dir = join(folder, "personas", persona);
      await mkdir(dir, { recursive: true });
      await writeFile(join(dir, "BOOT.md"), "Synthetic startup fixture");
    }
    const identity = generateIdentity();
    await savePhantomchatPersonaConfig(join(folder, "personas", "administrator"), {
      nsec: identity.nsec, relays: ["wss://relay.example"], allowedNpubs: [],
    });
    const bound: unknown[] = [], signed: string[] = [], listeners: string[] = [];
    const registry = new AuthenticatedCommandRegistry([], [{
      channel: "telegram", persona: "administrator", command: "/phantomview",
      bind: runtime => {
        expect(runtime.publicKey).toBe(identity.publicKeyHex);
        expect(Object.keys(runtime).sort()).toEqual(["publicKey", "signEvent", "transport"]);
        bound.push(runtime.transport);
        const sign = nativeAccessAuthorization({ origin: "https://view.example",
          publicKey: runtime.publicKey!, signEvent: runtime.signEvent! });
        return async (_context, signal) => {
          const auth = await sign(signal);
          const event = JSON.parse(Buffer.from(auth.slice(6), "base64").toString());
          if (verifyEvent(event)) signed.push(event.pubkey);
        };
      },
    }]);
    const config = {
      defaultPersona: "coordinator", autostartPersonas: [], personasDir: join(folder, "personas"),
      memoryDbPath: join(folder, "memory.sqlite"), configPath: join(folder, "config.toml"),
      harnessIdleTimeoutMs: 5000, harnessHardTimeoutMs: 5000, harnessStartupTimeoutMs: 5000,
      harnesses: { chain: ["claude"], claude: { bin: "unused", model: "unused" },
        pi: { bin: "unused", maxPayloadBytes: 100000 } },
      channels: { telegram: { token: "synthetic-one", allowedUserIds: [101], pollTimeoutS: 1 },
        telegramPersonas: { administrator: { token: "synthetic-two", allowedUserIds: [102], pollTimeoutS: 1 } } },
      embeddings: { provider: "none" }, voice: { provider: "none" },
      p2p: { enabled: false, stunServers: [] },
    } as Config;
    const code = await runRun({ config, checkHarnesses: false,
      lockPath: join(folder, "run.lock"), authenticatedCommands: registry,
      loadPersonaConfig: async () => config, fetchCanonicalRelays: async () => null,
      out: { write() { return true; } }, err: { write() { return true; } },
      runPhantomchatServer: async () => { throw Error("Inactive channel must not start"); },
      runTelegramServer: async input => {
        listeners.push(input.persona);
        if (input.persona === "coordinator") expect(input.authenticatedCommand).toBeUndefined();
        else {
          expect(bound).toHaveLength(1);
          expect(bound[0]).not.toBe(input.transport);
          expect(Object.keys(bound[0] as object)).toEqual(["sendPrivateControlMessage"]);
          await input.authenticatedCommand!.consume("telegram", {
            text: "/phantomview", senderId: "102", conversationId: "102", chatType: "private",
            sourceMessage: { id: "72", sentAt: Math.floor(Date.now() / 1000) },
          }, true);
        }
      },
    });
    expect(code).toBe(0);
    expect(listeners.sort()).toEqual(["administrator", "coordinator"]);
    expect(signed).toEqual([identity.publicKeyHex]);
  } finally {
    if (previousState === undefined) delete process.env.PHANTOMBOT_STATE;
    else process.env.PHANTOMBOT_STATE = previousState;
    await rm(folder, { recursive: true, force: true });
  }
});

test("existing startup binds each Telegram listener to its own registered persona", async () => {
  const folder = await mkdtemp(join(tmpdir(), "phantomview-command-startup-"));
  const previousState = process.env.PHANTOMBOT_STATE;
  process.env.PHANTOMBOT_STATE = join(folder, "state.json");
  try {
    for (const persona of ["coordinator", "administrator"]) {
      const dir = join(folder, "personas", persona);
      await mkdir(dir, { recursive: true });
      await writeFile(join(dir, "BOOT.md"), "Synthetic startup fixture");
    }
    const calls: string[] = [], listeners: string[] = [];
    const registry = new AuthenticatedCommandRegistry([{
      channel: "telegram", persona: "administrator", command: "/phantomview",
      handle: async context => { calls.push(context.persona); },
    }]);
    const config = {
      defaultPersona: "coordinator", personasDir: join(folder, "personas"),
      memoryDbPath: join(folder, "memory.sqlite"), configPath: join(folder, "config.toml"),
      harnessIdleTimeoutMs: 5000, harnessHardTimeoutMs: 5000, harnessStartupTimeoutMs: 5000,
      harnesses: { chain: ["claude"], claude: { bin: "unused", model: "unused" },
        pi: { bin: "unused", maxPayloadBytes: 100000 } },
      channels: { telegram: { token: "synthetic-one", allowedUserIds: [101], pollTimeoutS: 1 },
        telegramPersonas: { administrator: { token: "synthetic-two", allowedUserIds: [102], pollTimeoutS: 1 } } },
      embeddings: { provider: "none" }, voice: { provider: "none" },
    } as Config;
    const code = await runRun({ config, checkHarnesses: false,
      lockPath: join(folder, "run.lock"), authenticatedCommands: registry,
      loadPersonaConfig: async () => config,
      out: { write() { return true; } }, err: { write() { return true; } },
      runTelegramServer: async input => {
        listeners.push(input.persona);
        expect(input.authenticatedCommand).toBe(registry.resolve("telegram", input.persona));
        if (input.authenticatedCommand) await input.authenticatedCommand.consume("telegram", {
          text: "/phantomview", senderId: "102", conversationId: "102", chatType: "private",
          sourceMessage: { id: "42", sentAt: Math.floor(Date.now() / 1000) },
        }, true);
      },
    });
    expect(code).toBe(0);
    expect(listeners.sort()).toEqual(["administrator", "coordinator"]);
    expect(calls).toEqual(["administrator"]);
    expect(config.defaultPersona).toBe("coordinator");
  } finally {
    if (previousState === undefined) delete process.env.PHANTOMBOT_STATE;
    else process.env.PHANTOMBOT_STATE = previousState;
    await rm(folder, { recursive: true, force: true });
  }
});
