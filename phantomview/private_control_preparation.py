"""Prepare additive native control methods; ordinary delivery stays unchanged."""
from native_ingress_patch import replace_exact

INPUTS = {
    'src/channels/telegram/transport.ts': '02df82519e6904eafe489f4776bf88cede50f531c5fff7bcfdac272735d68695',
    'src/channels/phantomchat/transport.ts': '7cb27573aec440d3dba3d25f664358e00e60f1e7e685208d9a4079fe5058a764',
}
HELPER = 'src/channels/core/privateControl.ts'

TELEGRAM = '''  /** One private control send; success means Telegram accepted it, not that it was read. */
  async sendPrivateControlMessage(recipient: string, text: string, signal: AbortSignal): Promise<boolean> {
    if (!validPrivateControl("telegram", recipient, text)) return false;
    return privateControlSend(signal, async active => {
      const response = await fetch(`https://api.telegram.org/bot${this.token}/sendMessage`, {
        method: "POST", headers: { "content-type": "application/json" }, signal: active,
        body: JSON.stringify({ chat_id: Number(recipient), text, protect_content: true,
          link_preview_options: { is_disabled: true } }),
      });
      if (!response.ok) { await response.body?.cancel(); return false; }
      const body = await privateControlResponse(response) as {
        ok?: boolean; result?: { message_id?: number; chat?: { id?: number; type?: string } };
      };
      return body?.ok === true && Number.isSafeInteger(body.result?.message_id)
        && body.result!.message_id! > 0 && body.result?.chat?.type === "private"
        && String(body.result.chat.id) === recipient;
    });
  }

'''

PHANTOMCHAT = '''  /** One existing native encrypted wrap, without history correlation or rewrap retry. */
  async sendPrivateControlMessage(recipient: string, text: string, signal: AbortSignal): Promise<boolean> {
    if (this.closed || !validPrivateControl("phantomchat", recipient, text)) return false;
    return privateControlSend(signal, async active => {
      const { event } = await wrapV2(this.ourSecretKey, recipient, text);
      if (active.aborted || this.closed) return false;
      const outcomes = this.publishToTargets(event as unknown as NTNostrEvent,
        this.relayHealth.publishTargets());
      if (!outcomes.length) return false;
      return Promise.any(outcomes.map(async result => {
        if (await result) return true;
        throw new Error("Control publication unavailable");
      })).catch(() => false);
    });
  }

'''


def prepare(sources):
    result = {}
    for name in INPUTS:
        telegram = '/telegram/' in name
        source = sources[name]
        interface = 'TelegramTransport' if telegram else 'PhantomchatTransport'
        source = replace_exact(source, f'export interface {interface} extends ChannelTransport {{',
            f'export interface {interface} extends ChannelTransport {{\n'
            '  /** Optional non-recording control send, with explicit transport acceptance. */\n'
            '  sendPrivateControlMessage?(recipient: string, text: string, signal: AbortSignal): Promise<boolean>;')
        source = replace_exact(source,
            '  async sendMessage(conversationId: string, text: string): Promise<void> {',
            (TELEGRAM if telegram else PHANTOMCHAT)
            + '  async sendMessage(conversationId: string, text: string): Promise<void> {')
        names = 'validPrivateControl, privateControlSend' + (', privateControlResponse' if telegram else '')
        result[name] = f'import {{ {names} }} from "../core/privateControl.ts";\n' + source
    return result
