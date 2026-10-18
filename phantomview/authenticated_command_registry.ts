/** Fixed native startup registration, never a browser or model configuration API. */
import { AuthenticatedCommand, type AuthenticatedCommandOptions } from "./authenticated_command.ts";

export interface AuthenticatedCommandRegistration extends AuthenticatedCommandOptions {
  readonly channel: "telegram" | "phantomchat";
}

export class AuthenticatedCommandRegistry {
  readonly #routes = new Map<string, AuthenticatedCommand>();

  constructor(registrations: readonly AuthenticatedCommandRegistration[]) {
    if (!Array.isArray(registrations) || registrations.length > 64)
      throw new Error("A bounded native command registration list is required");
    for (const registration of registrations) {
      if (!registration || !["telegram", "phantomchat"].includes(registration.channel))
        throw new Error("A native command channel is required");
      const route = new AuthenticatedCommand(registration);
      const key = registration.channel + ":" + registration.persona;
      if (this.#routes.has(key)) throw new Error("Duplicate native command route");
      this.#routes.set(key, route);
    }
    Object.freeze(this);
  }

  resolve(channel: "telegram" | "phantomchat", persona: string): AuthenticatedCommand | undefined {
    if (!["telegram", "phantomchat"].includes(channel)
      || typeof persona !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(persona))
      throw new Error("A fixed native listener route is required");
    return this.#routes.get(channel + ":" + persona);
  }
}

export function verifyAuthenticatedCommandRegistry(registry: AuthenticatedCommandRegistry | undefined): void {
  if (registry !== undefined && !(registry instanceof AuthenticatedCommandRegistry))
    throw new Error("A native command registry instance is required");
}
