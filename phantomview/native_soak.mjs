// Compiled-daemon staging only. Run inside a fresh Linux PID/network namespace.
// Synthetic identity and model output; never read an operator HOME or credentials.
import assert from 'node:assert/strict';
import { mkdir, writeFile, readFile, readdir, lstat, unlink, chmod } from 'node:fs/promises';
import { resolve } from 'node:path';
import { connect } from 'node:net';
import { pathToFileURL } from 'node:url';

const [binaryArg, sourceArg, evidenceArg, durationArg = '910'] = process.argv.slice(2);
const binary = resolve(binaryArg), source = resolve(sourceArg), evidence = resolve(evidenceArg);
const seconds = Number(durationArg);
assert.ok(Number.isFinite(seconds) && seconds >= 910, 'Acceptance requires over 15 minutes');
assert.equal(process.platform, 'linux');
assert.equal(process.getuid(), 1001, 'Compile-time staging account must match');
const interfaces = (await readFile('/proc/net/route', 'utf8')).trim().split('\n');
assert.equal(interfaces.length, 1, 'Refusing a namespace with an external route');
assert.equal(process.env.PHANTOMVIEW_SOAK_NAMESPACE, 'isolated');
const root = '/tmp/phantomview-soak', socketPath = root + '/native/persona.sock';
const persona = root + '/personas/soak';
const { nsecEncode, npubEncode } = await import(pathToFileURL(source + '/node_modules/nostr-tools/lib/esm/nip19.js'));
const { getPublicKey } = await import(pathToFileURL(source + '/node_modules/nostr-tools/lib/esm/pure.js'));
const key = new Uint8Array(32).fill(1), owner = npubEncode(getPublicKey(new Uint8Array(32).fill(2)));
await mkdir(evidence, { recursive: true });
for (const name of ['native', 'home', 'config', 'data', 'state', 'personas/soak/memory']) {
  await mkdir(root + '/' + name, { recursive: true, mode: 0o750 });
}
await chmod(root + '/native', 0o750);
const env = { PATH: process.env.PATH, HOME: root + '/home',
  XDG_CONFIG_HOME: root + '/config', XDG_DATA_HOME: root + '/data', XDG_STATE_HOME: root + '/state',
  PHANTOMBOT_CONFIG: root + '/config.toml', PHANTOMBOT_PERSONAS_DIR: root + '/personas',
  PHANTOMBOT_DEFAULT_PERSONA: 'soak', PHANTOMCHAT_RELAYS_URL: 'http://127.0.0.1:18765/relays.json',
  NO_COLOR: '1', TERM: 'dumb' };
await writeFile(root + '/config.toml', `default_persona = "soak"
personas_dir = "${root}/personas"
autostart_personas = []
harness_idle_timeout_s = 10
harness_hard_timeout_s = 30
[harnesses]
chain = ["claude"]
[harnesses.claude]
bin = "${root}/fake-claude"
model = "synthetic"
[p2p]
enabled = false
`, { mode: 0o600 });
await writeFile(persona + '/SOUL.md', '# Synthetic staging persona\nAnswer the synthetic test request.\n');
await writeFile(persona + '/phantomchat.json', JSON.stringify({ nsec: nsecEncode(key),
  relays: ['ws://127.0.0.1:18765/relay'], allowed_npubs: [owner], greeted: [owner] }), { mode: 0o600 });
// The real Claude adapter spawns this child. The same valid JSON can be consumed
// by the tool-less judge and asserted in a completed conversation turn.
await writeFile(root + '/fake-claude', `#!/usr/bin/python3
import json,sys,time
if '--version' in sys.argv:
    print('synthetic-claude 1.0');sys.exit(0)
sys.stdin.read()
time.sleep(0.05)
text=json.dumps({'score':0,'reason':'synthetic fixture','question':'','reply':'SOAK_REPLY'})
print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':text}]}}))
print(json.dumps({'type':'result'}))
`, { mode: 0o700 });

const metrics = { schema_version: 1, synthetic: true, production_activation: false,
  duration_seconds: 0, turns: 0, nightly_runs: 0, relay_connections: 0,
  auth_frames: 0, rejected_auth: 0, forced_disconnects: 0, max_rss_kb: 0,
  max_runtime_processes: 0, socket_checks: [], binary_sha256: new Bun.CryptoHasher('sha256').update(await readFile(binary)).digest('hex') };
const clients = new Set();
const server = Bun.serve({ hostname: '127.0.0.1', port: 18765,
  fetch(req, server) {
    if (new URL(req.url).pathname === '/relays.json') return Response.json({ relays: ['ws://127.0.0.1:18765/relay'] });
    if (server.upgrade(req)) return;
    return new Response('synthetic staging', { status: 404 });
  }, websocket: {
    open(ws) {
      clients.add(ws); metrics.relay_connections++;
      ws.send(JSON.stringify(['AUTH', 'synthetic-' + metrics.relay_connections]));
      if (metrics.relay_connections % 3 === 0) { metrics.forced_disconnects++; ws.close(1012, 'synthetic connect race'); }
    },
    message(ws, raw) {
      const frame = JSON.parse(String(raw));
      if (frame[0] === 'AUTH') {
        metrics.auth_frames++;
        const accepted = metrics.auth_frames % 3 !== 0;
        if (!accepted) metrics.rejected_auth++;
        ws.send(JSON.stringify(['OK', frame[1].id, accepted, accepted ? 'accepted' : 'synthetic AUTH rejection']));
      }
      if (frame[0] === 'EVENT') ws.send(JSON.stringify(['OK', frame[1].id, true, 'stored']));
      if (frame[0] === 'REQ') ws.send(JSON.stringify(['EOSE', frame[1]]));
    }, close(ws) { clients.delete(ws); },
  },
});
let daemon;
const sleepers = ms => new Promise(resolve => setTimeout(resolve, ms));
const logFile = Bun.file(evidence + '/daemon.log').writer();
function launch(args) {
  return Bun.spawn([binary, ...args], { env, cwd: root, stdin: 'ignore', stdout: 'pipe', stderr: 'pipe' });
}
async function drain(stream, prefix) {
  for await (const chunk of stream) logFile.write(prefix + Buffer.from(chunk).toString());
}
async function inventory() {
  const processes = [];
  for (const pid of await readdir('/proc')) {
    if (!/^\d+$/.test(pid)) continue;
    try {
      const cmd = (await readFile('/proc/' + pid + '/cmdline', 'utf8')).replaceAll('\0', ' ');
      if (cmd.startsWith(binary + ' ') || cmd.includes(root + '/fake-claude')) processes.push({ pid: Number(pid), cmd });
    } catch {}
  }
  return processes;
}
async function assertRunning() {
  assert.equal(daemon.exitCode, null, 'Compiled daemon exited during staging');
  const status = await readFile('/proc/' + daemon.pid + '/status', 'utf8');
  const rss = Number(status.match(/^VmRSS:\s+(\d+)/m)?.[1] || 0);
  metrics.max_rss_kb = Math.max(metrics.max_rss_kb, rss);
  const children = await inventory();
  metrics.max_runtime_processes = Math.max(metrics.max_runtime_processes, children.length);
  assert.ok(children.length <= 8, 'Runtime children are accumulating');
}
async function turn(index) {
  const question = { schema_version: 1, request_id: crypto.randomUUID(),
    conversation: 'phantomview:' + 'a'.repeat(64), question: 'Synthetic health turn ' + index, evidence: [] };
  const answer = await new Promise((resolve, reject) => {
    const client = connect(socketPath), chunks = [];
    client.setTimeout(45000, () => { client.destroy(); reject(Error('Conversation timed out')); });
    client.on('error', reject);
    client.on('data', chunk => chunks.push(chunk));
    client.on('end', () => {
      try { const raw = Buffer.concat(chunks); resolve(JSON.parse(raw.subarray(4, 4 + raw.readUInt32BE(0)).toString())); }
      catch (error) { reject(error); }
    });
    client.on('connect', () => { const raw = Buffer.from(JSON.stringify(question)), header = Buffer.alloc(4);
      header.writeUInt32BE(raw.length); client.write(Buffer.concat([header, raw])); });
  });
  assert.equal(answer.status, 'complete');
  assert.ok(answer.text.includes('SOAK_REPLY'), 'A model turn must complete, not only a held request');
  metrics.turns++;
  console.log(JSON.stringify({ event: 'turn', turns: metrics.turns }));
}
async function nightly() {
  const child = launch(['nightly', '--persona', 'soak']);
  const timer = setTimeout(() => child.kill(), 30000);
  try {
    const [code, out, err] = await Promise.all([child.exited, new Response(child.stdout).text(), new Response(child.stderr).text()]);
    await writeFile(evidence + '/nightly-' + metrics.nightly_runs + '.log', out + err);
    assert.equal(code, 0, 'The compiled nightly child must finish successfully');
    metrics.nightly_runs++;
    await assertRunning();
  } finally { clearTimeout(timer); }
}
async function refusal(label, setup) {
  const cleanup = await setup();
  const before = await lstat(socketPath);
  const child = launch(['run']);
  const timer = setTimeout(() => child.kill(), 20000);
  try {
    const [code, out, err] = await Promise.all([child.exited, new Response(child.stdout).text(), new Response(child.stderr).text()]);
    await writeFile(evidence + '/socket-' + label + '.log', out + err);
    assert.equal(code, 1);
    assert.match(out + err, /Existing socket path requires operator inspection/);
    const after = await lstat(socketPath);
    assert.equal(after.ino, before.ino); assert.equal(after.uid, before.uid);
    metrics.socket_checks.push(label);
  } finally {
    clearTimeout(timer); await cleanup();
    try { await unlink(socketPath); } catch (err) { if (err.code !== 'ENOENT') throw err; }
  }
}

try {
  daemon = launch(['run']);
  const drains = [drain(daemon.stdout, '[stdout] '), drain(daemon.stderr, '[stderr] ')];
  for (let attempt = 0; ; attempt++) {
    await assertRunning();
    try { assert.ok((await lstat(socketPath)).isSocket()); break; } catch (err) {
      if (attempt >= 60) throw err; await sleepers(500);
    }
  }
  const started = performance.now();
  let nextTurn = 0, nextNightly = 10000, nextDrop = 15000;
  while (performance.now() - started < seconds * 1000) {
    await assertRunning();
    const elapsed = performance.now() - started;
    if (elapsed >= nextTurn) { await turn(metrics.turns + 1); nextTurn += 60000; }
    if (elapsed >= nextNightly) { await nightly(); nextNightly += 180000; }
    if (elapsed >= nextDrop) {
      for (const ws of clients) {
        ws.send(JSON.stringify(['AUTH', 'synthetic-rotate-' + elapsed]));
        ws.close(1012, 'synthetic periodic disconnect'); metrics.forced_disconnects++;
      }
      nextDrop += 45000;
    }
    await sleepers(1000);
  }
  metrics.duration_seconds = (performance.now() - started) / 1000;
  await turn(metrics.turns + 1); await nightly(); await assertRunning();
  assert.ok(metrics.turns >= 10 && metrics.nightly_runs >= 2);
  assert.ok(metrics.auth_frames >= 3 && metrics.forced_disconnects >= 3 && metrics.rejected_auth >= 1);
  daemon.kill('SIGTERM');
  const stopTimer = setTimeout(() => daemon.kill('SIGKILL'), 12000);
  try { assert.equal(await daemon.exited, 0, 'Graceful shutdown must exit cleanly'); }
  finally { clearTimeout(stopTimer); }
  await Promise.all(drains);
  await assert.rejects(lstat(socketPath), { code: 'ENOENT' });
  await refusal('live', async () => {
    const listener = Bun.listen({ unix: socketPath, socket: { data() {} } });
    return async () => listener.stop(true);
  });
  await refusal('stale', async () => {
    const make = Bun.spawnSync(['python3', '-c', 'import os,socket; s=socket.socket(socket.AF_UNIX); s.bind(' + JSON.stringify(socketPath) + '); os._exit(0)']);
    assert.equal(make.exitCode, 0); return async () => {};
  });
  await refusal('foreign', async () => {
    const make = Bun.spawnSync(['python3', '-c', 'import os,socket; s=socket.socket(socket.AF_UNIX); s.bind(' + JSON.stringify(socketPath) + '); os._exit(0)']);
    assert.equal(make.exitCode, 0);
    assert.equal(Bun.spawnSync(['sudo', '-n', 'chown', '0:0', socketPath]).exitCode, 0);
    assert.equal((await lstat(socketPath)).uid, 0); return async () => {};
  });
  await sleepers(3000);
  assert.deepEqual(await inventory(), [], 'No compiled daemon, nightly or harness child may survive');
  metrics.passed = true;
} catch (error) {
  metrics.passed = false; metrics.error = error.stack || String(error); throw error;
} finally {
  if (daemon?.exitCode === null) { daemon.kill('SIGKILL'); await daemon.exited; }
  server.stop(true); await logFile.end();
  await writeFile(evidence + '/soak-result.json', JSON.stringify(metrics, null, 2) + '\n');
  console.log(JSON.stringify(metrics));
}
