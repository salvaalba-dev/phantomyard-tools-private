/** Fixed native startup registration, never a browser or model configuration API. */
import { AuthenticatedCommand, type AuthenticatedCommandOptions } from "./authenticated_command.ts";
import type { AccessEventTemplate } from "./native_link_signer.ts";
import type { PrivateControlTransport } from "./private_control.ts";

export interface AuthenticatedCommandRegistration extends AuthenticatedCommandOptions {
  readonly channel: "telegram" | "phantomchat";
}

/** Capabilities from one actual native listener; no secret material is exposed. */
export interface NativeCommandRuntime {
  readonly transport: PrivateControlTransport;
  readonly publicKey?: string;
  readonly signEvent?: (event: AccessEventTemplate, signal: AbortSignal) => Promise<unknown>;
}

export interface RuntimeCommandRegistration {
  readonly persona: string;
  readonly channel: "telegram" | "phantomchat";
  readonly command: string;
  readonly bind: (runtime: Readonly<NativeCommandRuntime>) => AuthenticatedCommandOptions["handle"];
}

export class AuthenticatedCommandRegistry {
  readonly #routes = new Map<string, AuthenticatedCommand>();
  readonly #factories = new Map<string, Readonly<RuntimeCommandRegistration>>();
  readonly #bound = new Set<string>();

  constructor(registrations: readonly AuthenticatedCommandRegistration[],
    runtimeRegistrations: readonly RuntimeCommandRegistration[] = []) {
    if (!Array.isArray(registrations) || !Array.isArray(runtimeRegistrations)
      || registrations.length + runtimeRegistrations.length > 64)
      throw new Error("A bounded native command registration list is required");
    for (const registration of registrations) {
      if (!registration || !["telegram", "phantomchat"].includes(registration.channel))
        throw new Error("A native command channel is required");
      const route = new AuthenticatedCommand(registration);
      const key = registration.channel + ":" + registration.persona;
      if (this.#routes.has(key)) throw new Error("Duplicate native command route");
      this.#routes.set(key, route);
    }
    for (const registration of runtimeRegistrations) {
      if (!registration || !["telegram", "phantomchat"].includes(registration.channel)
        || typeof registration.bind !== "function") throw new Error("Fixed native runtime binding required");
      // Apply the same persona/command validation and native-control exclusions.
      new AuthenticatedCommand({ ...registration, handle: async () => {} });
      const key = registration.channel + ":" + registration.persona;
      if (this.#routes.has(key) || this.#factories.has(key))
        throw new Error("Duplicate native command route");
      this.#factories.set(key, Object.freeze({ ...registration }));
    }
    Object.freeze(this);
  }

  resolve(channel: "telegram" | "phantomchat", persona: string): AuthenticatedCommand | undefined {
    if (!["telegram", "phantomchat"].includes(channel)
      || typeof persona !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(persona))
      throw new Error("A fixed native listener route is required");
    return this.#routes.get(channel + ":" + persona);
  }

  /** Called once by native startup after constructing the actual channel transport. */
  bind(channel: "telegram" | "phantomchat", persona: string,
    runtime: () => NativeCommandRuntime): AuthenticatedCommand | undefined {
    const existing = this.resolve(channel, persona);
    const key = channel + ":" + persona, registration = this.#factories.get(key);
    if (!registration) return existing;
    if (this.#bound.has(key)) throw new Error("Native runtime route already bound");
    // Consume the binding even on failure; no retry with another persona's capabilities.
    this.#bound.add(key);
    const supplied = runtime();
    const context = Object.freeze({ transport: supplied.transport,
      publicKey: supplied.publicKey, signEvent: supplied.signEvent });
    const handle = registration.bind(context);
    const route = new AuthenticatedCommand({ persona, command: registration.command, handle });
    this.#routes.set(key, route);
    return route;
  }
}

export function verifyAuthenticatedCommandRegistry(registry: AuthenticatedCommandRegistry | undefined): void {
  if (registry !== undefined && !(registry instanceof AuthenticatedCommandRegistry))
    throw new Error("A native command registry instance is required");
}
