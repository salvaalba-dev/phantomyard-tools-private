/** Native startup capability view over an already loaded persona identity. */
import { finalizeEvent } from "nostr-tools/pure";
import type { NostrIdentity } from "../../lib/nostrIdentity.ts";
import type { NativeCommandRuntime } from "./authenticatedCommandRegistry.ts";
import type { PrivateControlTransport } from "./privateControl.ts";
import type { AccessEventTemplate } from "./nativeLinkSigner.ts";

export function nativeListenerRuntime(transport: PrivateControlTransport,
  identity?: NostrIdentity): Readonly<NativeCommandRuntime> {
  const send = transport.sendPrivateControlMessage?.bind(transport);
  // Expose only a bound operation, not the transport object's credential fields.
  const privateTransport = Object.freeze({ sendPrivateControlMessage: send });
  return Object.freeze({ transport: privateTransport, publicKey: identity?.publicKeyHex,
    signEvent: identity ? async (event: AccessEventTemplate, signal: AbortSignal) => {
      if (signal.aborted) throw new Error("Native signing cancelled");
      return finalizeEvent(event, identity.secretKey);
    } : undefined,
  });
}
