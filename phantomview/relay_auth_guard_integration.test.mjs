// Bun integration: import the actual pinned PhantomBot modules, not a guard copy.
// Only logging and the websocket are replaced; no daemon or persona is started.
import { test, mock } from 'bun:test';
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve(process.env.PHANTOMVIEW_NATIVE_SOURCE || 'native-source');
const warnings = [];
mock.module(root + '/src/lib/logger.ts', () => ({
  log: { warn: (...args) => warnings.push(args), debug: () => {} },
}));
const { AuthGuardedSimplePool, guardRelayAuthRejection } = await import(
  pathToFileURL(root + '/src/channels/phantomchat/authGuardedPool.ts').href
);
const { useWebSocketImplementation } = await import(
  pathToFileURL(root + '/node_modules/nostr-tools/lib/esm/pool.js').href
);
const turn = () => new Promise(resolve => setImmediate(resolve));
class FakeWebSocket {
  static OPEN = 1;
  static latest;
  readyState = 0;
  sent = [];
  constructor() {
    FakeWebSocket.latest = this;
    queueMicrotask(() => { this.readyState = 1; this.onopen(); });
  }
  send(frame) { assert.equal(this.readyState, 1); this.sent.push(JSON.parse(frame)); }
  receive(frame) { this.onmessage({ data: JSON.stringify(frame) }); }
  close() { this.readyState = 3; this.onclose({ message: 'synthetic disconnect' }); }
}
useWebSocketImplementation(FakeWebSocket);
const syntheticKey = new Uint8Array(32).fill(1);
async function connect() {
  const pool = new AuthGuardedSimplePool(syntheticKey, { enableReconnect: false });
  const relay = await pool.ensureRelay('wss://test.invalid/');
  return { relay, socket: FakeWebSocket.latest };
}

test('real pool installs an idempotent guard before AUTH and observes a signing/disconnect race', async () => {
  const { relay, socket } = await connect();
  try {
    const installed = relay.auth;
    guardRelayAuthRejection(relay);
    assert.equal(relay.auth, installed);
    let finish;
    relay.onauth = () => new Promise(resolve => { finish = resolve; });
    const before = warnings.length;
    socket.receive(['AUTH', 'disconnect challenge']); // Real fire-and-forget path.
    assert.equal(typeof finish, 'function');
    socket.close();
    finish({ id: 'a'.repeat(64), kind: 22242, tags: [], content: '' });
    await turn();
    assert.equal(warnings.length, before + 1);
    assert.equal(warnings.at(-1)[0], 'phantomchat: relay AUTH failed');
    assert.match(warnings.at(-1)[1].error, /closed connection/);
    assert.equal(relay.openEventPublishes.size, 0);
  } finally { relay.close(); }
});

test('real pool signer sends a signed AUTH and still awaits relay OK', async () => {
  const { relay, socket } = await connect();
  try {
    socket.receive(['AUTH', 'signed challenge']);
    await turn();
    const frame = socket.sent[0];
    assert.equal(frame[0], 'AUTH');
    assert.equal(frame[1].kind, 22242);
    assert.equal(frame[1].sig.length, 128);
    assert.deepEqual(frame[1].tags, [['relay', 'wss://test.invalid/'], ['challenge', 'signed challenge']]);
    socket.receive(['OK', frame[1].id, true, 'accepted']);
    assert.equal(await relay.auth(relay.onauth), 'accepted');
    assert.equal(relay.openEventPublishes.size, 0);
  } finally { relay.close(); }
});

test('real guard preserves caller rejection and permits a transient signer retry', async () => {
  const { relay, socket } = await connect();
  try {
    relay.challenge = 'retry challenge';
    await assert.rejects(relay.auth(async () => { throw Error('transient signer'); }), /transient signer/);
    const pending = relay.auth(relay.onauth);
    await turn();
    socket.receive(['OK', socket.sent[0][1].id, true, 'retry accepted']);
    assert.equal(await pending, 'retry accepted');
  } finally { relay.close(); }
});
