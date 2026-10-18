'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const {privateControlDelivery,privateControlSend,validPrivateControl}=require('./private_control.ts');
const origin='https://view.example:8790',link=origin+'/#c='+'a'.repeat(43);

test('private control delivery has exact channel, recipient and origin binding',async()=>{
  const calls=[],transport={async sendPrivateControlMessage(...args){calls.push(args);return true;}};
  const deliver=privateControlDelivery('telegram',origin,transport),signal=new AbortController().signal;
  assert.equal(await deliver('telegram','101',link,signal),true);
  for(const args of [['phantomchat','101',link],['telegram','-101',link],
    ['telegram','101','https://other.example/#c='+'a'.repeat(43)],['telegram','101',link+'&human=owner']])
    assert.equal(await deliver(...args,signal),false);
  assert.equal(calls.length,1);assert.equal(calls[0][0],'101');
  assert.throws(()=>privateControlDelivery('telegram',origin,{sendMessage(){}}));
  assert.throws(()=>privateControlDelivery('telegram',origin+'/path',transport));
  assert.equal(validPrivateControl('phantomchat','a'.repeat(64),'control'),true);
  assert.equal(validPrivateControl('telegram','9007199254740992','control'),false);
  assert.equal(validPrivateControl('telegram','101','a'.repeat(2049)),false);
});

test('only explicit acceptance succeeds; cancellation and errors do not retry',async()=>{
  for(const result of [undefined,false,{},'accepted'])
    assert.equal(await privateControlSend(new AbortController().signal,async()=>result),false);
  assert.equal(await privateControlSend(new AbortController().signal,async()=>{throw Error('private');}),false);
  const controller=new AbortController();controller.abort();let calls=0;
  assert.equal(await privateControlSend(controller.signal,async()=>{calls++;return true;}),false);
  assert.equal(calls,0);
});

test('active cancellation reaches the transport and suppresses a late acknowledgement',async()=>{
  const controller=new AbortController();let finish,seenSignal;
  const pending=privateControlSend(controller.signal,signal=>{
    seenSignal=signal;return new Promise(resolve=>{finish=resolve;});
  });
  controller.abort();assert.equal(await pending,false);assert.equal(seenSignal.aborted,true);
  finish(true);
});
