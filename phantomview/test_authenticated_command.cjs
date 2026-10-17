/* Synthetic adapter tests: no native channel authentication or live signing. */
'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const {AuthenticatedCommand,verifyAuthenticatedCommand}=require('./authenticated_command.ts');
const message=(extra={})=>({senderId:'101',conversationId:'101',chatType:'private',
  text:'/phantomview',sourceMessage:{id:'42',sentAt:Math.floor(Date.now()/1000)},...extra});
const binding=handle=>({persona:'coordinator',command:'/phantomview',handle});

test('explicit binding, immutable options and fixed receiving persona',async()=>{
  const calls=[],options=binding(async context=>calls.push(context));
  const router=new AuthenticatedCommand(options);options.persona='other';
  verifyAuthenticatedCommand(undefined,'coordinator');verifyAuthenticatedCommand(router,'coordinator');
  assert.throws(()=>verifyAuthenticatedCommand({},'coordinator'));
  assert.throws(()=>verifyAuthenticatedCommand(router,'other'));
  await router.consume('telegram',message(),true);
  assert.equal(calls[0].persona,'coordinator');assert.equal(Object.isFrozen(calls[0]),true);
  for(const change of [{persona:'../other'},{command:'/view argument'},{handle:null}])
    assert.throws(()=>new AuthenticatedCommand({...binding(async()=>{}),...change}));
});

test('ordinary text falls through; reserved malformed or unauthorized requests do not',async()=>{
  let calls=0;const router=new AuthenticatedCommand(binding(async()=>{calls++;}));
  assert.equal(await router.consume('telegram',message({text:'ordinary question'}),true),false);
  for(const extra of [{chatType:'group'},{groupId:'room'},{conversationId:'other'},
    {sourceMessage:undefined},{sourceMessage:{id:'42',sentAt:1}},{media:{}},
    {text:'/phantomview@bot'},{text:'/phantomview other'},{text:'/PHANTOMVIEW'}])
    assert.equal(await router.consume('telegram',message(extra),true),true);
  assert.equal(await router.consume('telegram',message(),false),true);assert.equal(calls,0);
});

test('source IDs and native sender encodings are checked for both transports',async()=>{
  const calls=[],router=new AuthenticatedCommand(binding(async context=>calls.push(context)));
  await router.consume('telegram',message({senderId:'9007199254740992',conversationId:'9007199254740992'}),true);
  await router.consume('telegram',message({sourceMessage:{id:'0',sentAt:Math.floor(Date.now()/1000)}}),true);
  const sender='a'.repeat(64),id='b'.repeat(64);
  await router.consume('phantomchat',message({senderId:sender,conversationId:sender,
    sourceMessage:{id,sentAt:Math.floor(Date.now()/1000)}}),false);
  await router.consume('phantomchat',message({senderId:sender,conversationId:sender,
    sourceMessage:{id,sentAt:Math.floor(Date.now()/1000)}}),true);
  assert.equal(calls.length,1);assert.equal(calls[0].sender,sender);assert.equal(calls[0].messageId,id);
  assert.equal(calls[0].channel,'phantomchat');assert.equal(Object.hasOwn(calls[0],'human'),false);
});

test('duplicates are claimed before asynchronous host work and never retried automatically',async()=>{
  let calls=0,release;const done=new Promise(resolve=>{release=resolve;});
  const router=new AuthenticatedCommand(binding(async()=>{calls++;await done;}));
  const first=router.consume('telegram',message(),true);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(await router.consume('telegram',message(),true),true);
  release();await first;assert.equal(calls,1);
});

test('per-sender attempts stay bounded even when the callback fails',async()=>{
  let calls=0;const router=new AuthenticatedCommand(binding(async()=>{calls++;throw Error('PRIVATE_SENTINEL');}));
  for(let id=1;id<=5;id++)assert.equal(await router.consume('telegram',message({
    sourceMessage:{id:String(id),sentAt:Math.floor(Date.now()/1000)}}),true),true);
  assert.equal(calls,3);
});

test('cancellation consumes the reserved command and prevents a second callback',async()=>{
  let started,observed=false;const began=new Promise(resolve=>{started=resolve;});
  const router=new AuthenticatedCommand(binding(async(context,signal)=>{
    started();await new Promise(resolve=>signal.addEventListener('abort',()=>{observed=true;resolve();},{once:true}));
  }));
  const controller=new AbortController(),first=router.consume('telegram',message(),true,controller.signal);
  await began;controller.abort();assert.equal(await first,true);assert.equal(observed,true);
  assert.equal(await router.consume('telegram',message(),true,controller.signal),true);
});
