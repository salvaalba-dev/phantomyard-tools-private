/** Compose native listener capabilities with the existing trusted-daemon handoff. */
import { AuthenticatedCommandRegistry, type NativeCommandRuntime } from "./authenticated_command_registry.ts";
import { nativeAccessAuthorization } from "./native_link_signer.ts";
import { nativeLinkCallback } from "./native_link_callback.ts";
import { privateControlDelivery } from "./private_control.ts";
import { npubEncode } from "nostr-tools/nip19";

export interface PhantomViewStartupRoute {
  readonly persona: string;
  readonly channel: "telegram" | "phantomchat";
  readonly scopeId: string;
  readonly origin: string;
  readonly issuerUid: number;
  readonly readerUid: number;
  readonly python: string;
  readonly clientScript: string;
  readonly socketPath: string;
}

/** Trusted host input only: no CLI discovery, environment loader or model configuration. */
export function phantomViewStartupCommands(routes: readonly PhantomViewStartupRoute[]) {
  if (!Array.isArray(routes) || routes.length > 64)
    throw new Error("A bounded fixed PhantomView startup route list is required");
  return new AuthenticatedCommandRegistry([], routes.map(value => {
    const route = Object.freeze({ ...value });
    return { persona: route.persona, channel: route.channel, command: "/phantomview",
      bind: (runtime: Readonly<NativeCommandRuntime>) => {
        if (!runtime.publicKey || typeof runtime.signEvent !== "function")
          throw new Error("The receiving persona requires its existing native signing identity");
        return nativeLinkCallback({ ...route, trustBoundary: "daemon", modelUids: [],
          signAuthorization: nativeAccessAuthorization({ origin: route.origin,
            publicKey: runtime.publicKey, signEvent: runtime.signEvent }),
          encodeNpub: npubEncode,
          deliverDirect: privateControlDelivery(route.channel, route.origin, runtime.transport),
        });
      },
    };
  }));
}
