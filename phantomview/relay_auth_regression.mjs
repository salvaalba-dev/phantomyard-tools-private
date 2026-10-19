// No real relay, identity, persona state or credentials are used.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve(process.env.PHANTOMVIEW_NATIVE_SOURCE || 'native-source');
const dependency = root + '/node_modules/nostr-tools/lib/esm/';
const { AbstractRelay } = await import(pathToFileURL(dependency + 'abstract-relay.js'));
const { SimplePool, useWebSocketImplementation } = await import(pathToFileURL(dependency + 'pool.js'));
const turn = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
class FakeWebSocket {
  static OPEN = 1;
  static latest;
  readyState = 0;
  sent = [];
  constructor() {
    FakeWebSocket.latest = this;
    queueMicrotask(() => { this.readyState = 1; this.onopen(); });
  }
  send(frame) {
    if (this.sendFailure) throw this.sendFailure;
    assert.equal(this.readyState, 1);
    this.sent.push(JSON.parse(frame));
  }
  receive(frame) { this.onmessage({ data: JSON.stringify(frame) }); }
  close() { this.readyState = 3; this.onclose({ message: 'test connection closed' }); }
}
const event = { id: 'a'.repeat(64), pubkey: 'b'.repeat(64), sig: 'c'.repeat(128),
  kind: 22242, created_at: 1, tags: [], content: '' };
useWebSocketImplementation(FakeWebSocket);

for (const entry of ['abstract-relay', 'pool']) {
  async function connect() {
    let relay;
    if (entry === 'pool') {
      relay = await new SimplePool({ enableReconnect: false }).ensureRelay('wss://test.invalid/');
    } else {
      relay = new AbstractRelay('wss://test.invalid/', {
        verifyEvent: () => true, websocketImplementation: FakeWebSocket,
      });
      await relay.connect();
    }
    relay.publishTimeout = 30;
    const socket = FakeWebSocket.latest;
    socket.receive(['AUTH', 'synthetic-challenge']);
    return { relay, socket };
  }

  test(`${entry}: disconnect while signing rejects AUTH without an orphan`, async () => {
    const { relay, socket } = await connect();
    const signing = deferred(), entered = deferred();
    const pending = relay.auth(async () => { entered.resolve(); return signing.promise; });
    const rejected = assert.rejects(pending, /closed connection/);
    await entered.promise;
    socket.close();
    signing.resolve(event);
    await rejected;
    assert.equal(relay.openEventPublishes.size, 0);
    await turn(); // An unhandled send() rejection fails the node:test runner.
  });

  test(`${entry}: signing failure reaches the caller immediately`, async () => {
    const { relay } = await connect();
    try {
      await assert.rejects(relay.auth(async () => { throw Error('signing refused'); }), /signing refused/);
      assert.equal(relay.openEventPublishes.size, 0);
    } finally { relay.close(); }
  });

  test(`${entry}: websocket send failure rejects AUTH and clears pending state`, async () => {
    const { relay, socket } = await connect();
    try {
      socket.sendFailure = Error('synthetic websocket write failure');
      await assert.rejects(relay.auth(async () => event), /synthetic websocket write failure/);
      assert.equal(relay.openEventPublishes.size, 0);
      await turn();
    } finally { relay.close(); }
  });

  test(`${entry}: successful AUTH still waits for OK`, async () => {
    const { relay, socket } = await connect();
    try {
      let settled = false;
      const pending = relay.auth(async () => event);
      pending.then(() => { settled = true; });
      await turn();
      assert.equal(settled, false);
      assert.equal(socket.sent[0][0], 'AUTH');
      socket.receive(['OK', event.id, true, 'accepted']);
      assert.equal(await pending, 'accepted');
      assert.equal(relay.openEventPublishes.size, 0);
    } finally { relay.close(); }
  });

  test(`${entry}: negative OK and timeout still reject`, async () => {
    for (const negative of [true, false]) {
      const { relay, socket } = await connect();
      try {
        const pending = relay.auth(async () => event);
        const rejected = assert.rejects(pending, negative ? /denied/ : /auth timed out/);
        await turn();
        if (negative) socket.receive(['OK', event.id, false, 'denied']);
        await rejected;
        assert.equal(relay.openEventPublishes.size, 0);
      } finally { relay.close(); }
    }
  });

  test(`${entry}: existing fire-and-forget guard observes the send rejection`, async () => {
    const { relay, socket } = await connect();
    const signing = deferred(), entered = deferred(), observed = deferred();
    // Same observation boundary as the pinned guardRelayAuthRejection().
    const original = relay.auth.bind(relay);
    relay.auth = signer => {
      const pending = original(signer);
      pending.catch(observed.resolve);
      return pending;
    };
    relay.onauth = async () => { entered.resolve(); return signing.promise; };
    socket.receive(['AUTH', 'second-challenge']);
    await entered.promise;
    socket.close();
    signing.resolve(event);
    assert.match((await observed.promise).message, /closed connection/);
    assert.equal(relay.openEventPublishes.size, 0);
    await turn();
  });
}
