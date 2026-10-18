'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {AuthenticatedCommandRegistry,verifyAuthenticatedCommandRegistry}=require('./authenticated_command_registry.ts');

const registration=(channel,persona,handle=async()=>{})=>({channel,persona,command:'/phantomview',handle});
const message=id=>({senderId:'101',conversationId:'101',chatType:'private',text:'/phantomview',
  sourceMessage:{id,sentAt:Math.floor(Date.now()/1000)}});

test('exact channel and persona registration has no default fallback',()=>{
  const registry=new AuthenticatedCommandRegistry([
    registration('telegram','coordinator'),registration('phantomchat','coordinator'),
    registration('telegram','administrator')]);
  assert.ok(registry.resolve('telegram','coordinator'));
  assert.notEqual(registry.resolve('telegram','coordinator'),registry.resolve('phantomchat','coordinator'));
  assert.equal(registry.resolve('phantomchat','administrator'),undefined);
  assert.equal(registry.resolve('telegram','unregistered'),undefined);
  verifyAuthenticatedCommandRegistry(registry);verifyAuthenticatedCommandRegistry(undefined);
  assert.throws(()=>verifyAuthenticatedCommandRegistry({resolve(){}}));
  assert.throws(()=>registry.resolve('email','coordinator'));
  assert.throws(()=>registry.resolve('telegram','../coordinator'));
});

test('invalid, duplicate and native-control bindings fail at construction',()=>{
  const row=registration('telegram','coordinator');
  for(const rows of [null,{},[row,row],[{...row,channel:'email'}],
    [{...row,command:'/stop'}],Array(65).fill(row)])
    assert.throws(()=>new AuthenticatedCommandRegistry(rows));
  assert.equal(new AuthenticatedCommandRegistry([]).resolve('telegram','coordinator'),undefined);
});

test('startup registrations are copied and each persona retains its own callback and attempt state',async()=>{
  const calls=[],row=registration('telegram','coordinator',async context=>calls.push(context.persona));
  const rows=[row,registration('telegram','administrator',async context=>calls.push(context.persona))];
  const registry=new AuthenticatedCommandRegistry(rows);
  row.persona='other';row.handle=async()=>{throw Error('mutated handler');};rows.length=0;
  assert.equal(Object.isFrozen(registry),true);
  const first=registry.resolve('telegram','coordinator'),second=registry.resolve('telegram','administrator');
  await first.consume('telegram',message('1'),true);
  await first.consume('telegram',message('1'),true);
  await second.consume('telegram',message('1'),true);
  assert.deepEqual(calls,['coordinator','administrator']);
});

test('runtime capabilities bind only the exact registered route once and remain outside message input',async()=>{
  const seen=[],transport={sendPrivateControlMessage:async()=>true};
  const definition={channel:'telegram',persona:'administrator',command:'/phantomview',
    bind:runtime=>{assert.equal(Object.isFrozen(runtime),true);assert.equal(runtime.transport,transport);
      assert.equal('secretKey' in runtime,false);return async context=>seen.push(context.persona);}};
  const registry=new AuthenticatedCommandRegistry([], [definition]);
  definition.bind=()=>{throw Error('mutated factory');};
  let calls=0;
  const runtime=()=>{calls++;return {transport,publicKey:'a'.repeat(64),secretKey:'not-forwarded'};};
  assert.equal(registry.bind('telegram','coordinator',runtime),undefined);
  assert.equal(registry.bind('phantomchat','administrator',runtime),undefined);
  assert.equal(calls,0);
  const route=registry.bind('telegram','administrator',runtime);
  await route.consume('telegram',message('51'),true);
  assert.deepEqual(seen,['administrator']);assert.equal(calls,1);
  assert.throws(()=>registry.bind('telegram','administrator',runtime),/already bound/);
  assert.equal(registry.resolve('telegram','administrator'),route);
});

test('runtime registration conflicts and failed binding cannot fall back or retry',()=>{
  const row={channel:'telegram',persona:'coordinator',command:'/phantomview',bind:()=>{throw Error('unavailable');}};
  assert.throws(()=>new AuthenticatedCommandRegistry([registration('telegram','coordinator')],[row]));
  assert.throws(()=>new AuthenticatedCommandRegistry([],[row,row]));
  assert.throws(()=>new AuthenticatedCommandRegistry([],[{...row,command:'/update'}]));
  const registry=new AuthenticatedCommandRegistry([],[row]);
  assert.throws(()=>registry.bind('telegram','coordinator',()=>({transport:{}})),/unavailable/);
  assert.equal(registry.resolve('telegram','coordinator'),undefined);
  assert.throws(()=>registry.bind('telegram','coordinator',()=>({transport:{}})),/already bound/);
});
