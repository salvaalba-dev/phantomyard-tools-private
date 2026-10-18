/* Consultation lifecycle races, scope binding and exact-request retries. */
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {ScopedChat}=require('./scoped-chat.js');
const id='12345678-1234-1234-1234-123456789abc',requestId='12345678-1234-1234-1234-123456789def';
const view={scope_id:'river-project',view_revision:'a'.repeat(64)};
const pending=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};};
function fixture(request){const frames=[],calls=[],invalid=[];const chat=new ScopedChat({request:async(...args)=>{calls.push(args);return request(...args);},
  render:state=>frames.push(state),onInvalid:()=>invalid.push(true),delay:async()=>{},uuid:()=>requestId});
  chat.enable({available:true,persona:'project-guide',scope_id:'river-project'},view);return{chat,frames,calls,invalid};}
function complete(text='Scoped answer',overrides={}){return{id,status:'complete',result:{status:'complete',request_id:requestId,complete_corpus:false,
  persona:'project-guide',scope_id:view.scope_id,view_revision:view.view_revision,text,...overrides}};}

test('submit and poll return only a matching scoped response',async()=>{
  let posted=false;const f=fixture(async method=>method==='DELETE'?{}:!posted?(posted=true,{id,status:'queued',result:null}):complete());
  await f.chat.send('Explain the project');assert.equal(f.chat.state.text,'Scoped answer');
  assert.deepEqual(f.calls[0],['POST','/api/scoped-assistant/jobs',{request_id:requestId,question:'Explain the project',resource_ids:[]}]);
  assert.equal(f.calls.filter(row=>row[0]==='POST').length,1);
});
test('late submission after cancel is discarded and its server job is cancelled',async()=>{
  const late=pending(),f=fixture(async method=>method==='POST'?late.promise:{});const running=f.chat.send('Explain');f.chat.cancel();
  late.resolve(complete('Late private answer'));await running;
  assert.equal(f.chat.state.text,'');assert.equal(f.chat.state.status,'cancelled');assert.ok(f.calls.some(row=>row[0]==='DELETE'&&row[1].endsWith(id)));
});
test('reset during a pending poll clears data and suppresses late output',async()=>{
  const late=pending();const f=fixture(async method=>method==='POST'?{id,status:'running'}:method==='GET'?late.promise:{});
  const running=f.chat.send('Explain');await new Promise(resolve=>setImmediate(resolve));f.chat.reset();late.resolve(complete('Stale answer'));await running;
  assert.equal(f.chat.state.status,'unavailable');assert.equal(f.chat.state.text,'');assert.equal(f.chat.view,null);
});
test('ambiguous network failure retries exactly the same request UUID and focus',async()=>{
  let count=0;const f=fixture(async method=>{if(method==='POST'&&count++===0)throw Error('Connection lost');return complete();});
  f.chat.setFocus({id:'b'.repeat(64),title:'Visible task'});await f.chat.send('Explain');assert.ok(f.chat.retryBody);
  await f.chat.send('Explain',true);const posts=f.calls.filter(row=>row[0]==='POST');assert.deepEqual(posts[0][2],posts[1][2]);
  assert.equal(f.chat.state.text,'Scoped answer');
});
test('JEV holds and failures never display supplied response text',async()=>{
  for(const status of ['held','failed','cancelled']){const f=fixture(async()=>({...complete('Do not display'),status}));await f.chat.send('Explain');
    assert.equal(f.chat.state.status,status);assert.equal(f.chat.state.text,'');}
});
test('changed scope, persona, request, view or corpus claims clear the client',async()=>{
  for(const change of [{scope_id:'other'},{persona:'other'},{request_id:id},{view_revision:'c'.repeat(64)},{complete_corpus:true}]){
    const f=fixture(async()=>complete('Wrong context',change));await f.chat.send('Explain');assert.equal(f.chat.view,null);assert.equal(f.invalid.length,1);
  }
});
test('authorization errors clear response state without a legacy fallback',async()=>{
  for(const status of [401,403,404,409]){const f=fixture(async()=>{throw Object.assign(Error('Denied'),{status});});await f.chat.send('Explain');
    assert.equal(f.chat.state.text,'');assert.equal(f.invalid.length,1);assert.equal(f.calls.length,1);}
});
test('rate limits require an explicit retry and never auto-submit again',async()=>{
  const f=fixture(async()=>{throw Object.assign(Error('Limit'),{status:429});});await f.chat.send('Explain');
  assert.equal(f.chat.state.status,'limited');assert.equal(f.calls.length,1);assert.ok(f.chat.retryBody);
  await f.chat.send('Another question');assert.equal(f.calls.length,1);
});
test('model HTML remains plain response text and is never interpreted by the client model',async()=>{
  const text='<img src=x onerror=alert(1)>';const f=fixture(async()=>complete(text));await f.chat.send('Explain');assert.equal(f.chat.state.text,text);
});
test('unconfigured or mismatched capabilities cannot enable a consultation',async()=>{
  const f=fixture(async()=>complete());f.chat.enable({available:true,persona:'guide',scope_id:'other'},view);await f.chat.send('Explain');assert.equal(f.calls.length,0);
});

test('existing-persona mode requires its own response provenance',async()=>{
  const f=fixture(async()=>complete('Native answer',{mode:'persona-conversation',native_context:'existing-persona'}));
  f.chat.enable({available:true,persona:'project-guide',scope_id:view.scope_id,mode:'persona-conversation'},view);
  await f.chat.send('Explain the institution');assert.equal(f.chat.state.text,'Native answer');
  assert.equal(f.frames.at(-1).mode,'persona-conversation');
  const wrong=fixture(async()=>complete('Wrong provenance'));
  wrong.chat.enable({available:true,persona:'project-guide',scope_id:view.scope_id,mode:'persona-conversation'},view);
  await wrong.chat.send('Explain');assert.equal(wrong.invalid.length,1);assert.equal(wrong.chat.state.text,'');
});
