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
    relay.publishTimeout = 250;
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

  test(`${entry}: synthetic fire-and-forget observer sees the send rejection`, async () => {
    const { relay, socket } = await connect();
    const signing = deferred(), entered = deferred(), observed = deferred();
    // Unit-test observer only. The separate Bun integration imports the real guard.
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

  test(`${entry}: transient signing failure allows retry on the same connection`, async () => {
    const { relay, socket } = await connect();
    try {
      await assert.rejects(relay.auth(async () => { throw Error('transient signer'); }), /transient signer/);
      const pending = relay.auth(async () => event);
      await turn();
      assert.equal(socket.sent.length, 1);
      socket.receive(['OK', event.id, true, 'retry accepted']);
      assert.equal(await pending, 'retry accepted');
    } finally { relay.close(); }
  });

  test(`${entry}: concurrent AUTH shares signing and a late old failure preserves the new AUTH`, async () => {
    const { relay, socket } = await connect();
    const oldSigning = deferred();
    try {
      let calls = 0;
      const signer = async () => { calls++; return oldSigning.promise; };
      const first = relay.auth(signer), same = relay.auth(signer);
      const rejected = Promise.all([assert.rejects(first, /closed connection/), assert.rejects(same, /closed connection/)]);
      assert.equal(calls, 1);
      socket.close();
      await relay.connect();
      const nextSocket = FakeWebSocket.latest;
      nextSocket.receive(['AUTH', 'new challenge']);
      const next = relay.auth(async () => event);
      const nextMemo = relay.authPromise;
      oldSigning.resolve(event);
      await rejected;
      assert.equal(relay.authPromise, nextMemo);
      await turn();
      assert.equal(nextSocket.sent.length, 1);
      assert.equal(nextSocket.sent[0][0], 'AUTH');
      nextSocket.receive(['OK', event.id, true, 'new connection accepted']);
      assert.equal(await next, 'new connection accepted');
    } finally { relay.close(); }
  });

  for (const mode of ['disconnected', 'missing websocket', 'closed websocket', 'write failure']) {
    test(`${entry}: ${mode} rejects publish/count and cleans their pending entries`, async () => {
      const { relay, socket } = await connect();
      try {
        if (mode === 'disconnected') socket.close();
        if (mode === 'missing websocket') relay.ws = undefined;
        if (mode === 'closed websocket') socket.readyState = 3;
        if (mode === 'write failure') socket.sendFailure = Error('synthetic write failure');
        const expected = mode === 'write failure' ? /synthetic write failure/ : /closed connection/;
        await Promise.all([
          assert.rejects(relay.auth(async () => ({ ...event, id: 'd'.repeat(64) })), expected),
          assert.rejects(relay.publish(event), expected),
          assert.rejects(relay.count([{}], { id: 'count-fail' }), expected),
        ]);
        assert.equal(relay.openEventPublishes.size, 0);
        assert.equal(relay.openCountRequests.size, 0);
        await turn();
      } finally { relay.close(); }
    });
  }

  test(`${entry}: successful publish/count preserve their response contract`, async () => {
    const { relay, socket } = await connect();
    try {
      const published = relay.publish(event), counted = relay.count([{}], { id: 'count-ok' });
      await turn();
      assert.deepEqual(socket.sent.map(frame => frame[0]), ['EVENT', 'COUNT']);
      socket.receive(['OK', event.id, true, 'stored']);
      socket.receive(['COUNT', 'count-ok', { count: 7 }]);
      assert.equal(await published, 'stored');
      assert.equal(await counted, 7);
      assert.equal(relay.openEventPublishes.size, 0);
      assert.equal(relay.openCountRequests.size, 0);
    } finally { relay.close(); }
  });

  test(`${entry}: failed REQ closes once and cancels EOSE without orphaning CLOSE`, async () => {
    const { relay, socket } = await connect();
    let closed = 0, eosed = 0;
    try {
      socket.sendFailure = Error('synthetic REQ failure');
      const sub = relay.subscribe([{}], {
        id: 'failed-sub', eoseTimeout: 20,
        onclose: reason => { closed++; assert.match(reason, /synthetic REQ failure/); },
        oneose: () => eosed++,
      });
      await turn();
      sub.close();
      await new Promise(resolve => setTimeout(resolve, 40));
      assert.equal(sub.closed, true);
      assert.equal(relay.openSubs.size, 0);
      assert.equal(relay.ongoingOperations, 0);
      assert.equal(closed, 1);
      assert.equal(eosed, 0);
    } finally { relay.close(); }
  });

  test(`${entry}: relay CLOSED tears down once without echoing CLOSE`, async () => {
    const { relay, socket } = await connect();
    let closed = 0;
    try {
      const sub = relay.subscribe([{}], { id: 'remote-closed', onclose: () => closed++ });
      await turn();
      socket.receive(['CLOSED', sub.id, 'remote rejection']);
      sub.close();
      assert.equal(closed, 1);
      assert.equal(relay.openSubs.size, 0);
      assert.equal(relay.ongoingOperations, 0);
      assert.deepEqual(socket.sent.map(frame => frame[0]), ['REQ']);
    } finally { relay.close(); }
  });
}
