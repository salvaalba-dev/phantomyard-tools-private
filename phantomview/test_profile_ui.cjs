/* Exercise the actual profile dialog functions with inert DOM and HTTP fixtures. */
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {ScopedModel}=require('./scoped-ui.js');
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.events={};this.attrs={};this.open=false;this.hidden=false;this.textContent='';}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[];this.textContent='';this.append(...children);}
  addEventListener(name,fn){this.events[name]=fn;}
  showModal(){this.open=true;}
  setAttribute(name,value){this.attrs[name]=value;}
}
const id='a'.repeat(64),noteId='b'.repeat(64),hash='c'.repeat(64);
function fixture(){return {schema_version:1,complete_corpus:false,organization:'example',scope_id:'example',
  policy_revision:'1'.repeat(64),view_revision:'2'.repeat(64),
  resources:[{id,kind:'persona',data:{id:'coordinator',title:'Coordinator',description:'<img src=x onerror=alert(1)>'}},
    {id:noteId,kind:'knowledge',data:{title:'Role profile',actor:'coordinator',source:'reviewed-knowledge',payload_sha256:hash}}],relations:[]};}
function setup(request){
  const source=fs.readFileSync(require.resolve('./scoped-ui.js'),'utf8'),begin=source.indexOf('  function renderProfile('),end=source.indexOf('  function renderOrganizationTree(');
  assert.ok(begin>0&&end>begin);
  const elements=new Map(),failures=[],$=key=>{if(!elements.has(key))elements.set(key,new Element('div'));return elements.get(key);};
  const text=(tag,value,cls)=>{const e=new Element(tag);e.textContent=value;e.className=cls;return e;};
  const make=new Function('ScopedModel','text','$','api','failure',`let epoch=0,detailEpoch=0,profileReadEpoch=0,detailFocus=null;
    const controller={signal:null},chat={view:true};${source.slice(begin,end)}
    return {showDetails,close:()=>{detailEpoch++;profileReadEpoch++;$('detail').open=false;$('detail-content').replaceChildren();}};`);
  const ui=make(ScopedModel,text,$,request,error=>failures.push(error.message));return {ui,$,failures};
}
function flatten(node){return [node,...node.children.flatMap(flatten)];}
test('profile dialog renders plain text, preserves one dialog and reads documents in place',async()=>{
  const view=fixture(),calls=[],f=setup(async path=>{calls.push(path);if(path==='/api/state')return view;
    if(path==='/api/resource/'+id)return view.resources[0];
    return {id:noteId,title:'Role profile',actor:'coordinator',payload_sha256:hash,trust:'untrusted',format:'markdown',excerpt_only:false,content:'<script>doNotExecute()</script>'};});
  await f.ui.showDetails(view.resources[0]);assert.equal(f.$('detail').open,true);assert.deepEqual(f.failures,[]);
  const nodes=flatten(f.$('detail-content'));assert.ok(nodes.some(n=>n.textContent==='<img src=x onerror=alert(1)>'));
  assert.ok(!nodes.some(n=>n.tag==='img'||n.tag==='script'));
  label(f,'Documents').events.click();
  const document=flatten(f.$('detail-content')).find(n=>n.className==='profile-link profile-document');assert.ok(document);
  await document.events.click();const after=flatten(f.$('detail-content'));
  assert.ok(after.some(n=>n.tag==='pre'&&n.textContent==='<script>doNotExecute()</script>'));
  assert.equal(f.$('detail').open,true);assert.ok(calls.includes('/api/reviewed-knowledge/'+noteId));
});
test('a changed authorized view prevents rendering and stale requests cannot repopulate a closed dialog',async()=>{
  const view=fixture();let states=0;
  const f=setup(async path=>path==='/api/state'?{...view,view_revision:++states===1?view.view_revision:'3'.repeat(64)}:view.resources[0]);
  await f.ui.showDetails(view.resources[0]);assert.deepEqual(f.failures,['Record information changed']);
  assert.equal(f.$('detail-content').children.length,0);
  let resolve;const pending=new Promise(done=>resolve=done),g=setup(()=>pending);
  const read=g.ui.showDetails(view.resources[0]);g.ui.close();resolve(view);await read;
  assert.equal(g.$('detail').open,false);assert.equal(g.$('detail-content').children.length,0);assert.deepEqual(g.failures,[]);
});


test('Documents cards open their own published text instead of an empty entity profile',async()=>{
  const view=fixture(),body='# Identity\n<script>doNotExecute()</script>';
  const row={id:noteId,kind:'document',data:{title:'Identity',filename:'IDENTITY.md',source:'reviewed-profile',format:'markdown',content:body}};
  view.resources=[row];
  const calls=[],f=setup(async path=>{calls.push(path);return path==='/api/state'?view:row;});
  await f.ui.showDetails(row);
  assert.deepEqual(f.failures,[]);assert.equal(f.$('detail-title').textContent,'Identity');
  const nodes=flatten(f.$('detail-content'));
  assert.ok(nodes.some(n=>n.tag==='pre'&&n.textContent===body));
  assert.ok(!nodes.some(n=>n.tag==='script'||n.textContent==='Identity & contact'));
  assert.deepEqual(calls,['/api/state','/api/resource/'+noteId,'/api/state']);
});

test('Documents without published readable text explain the missing content',async()=>{
  for(const data of [{title:'Minutes'},{title:'Minutes',format:'text/html',content:'<script>doNotExecute()</script>'}]){
    const row={id:noteId,kind:'document',data},view=fixture();view.resources=[row];
    const f=setup(async path=>path==='/api/state'?view:row);await f.ui.showDetails(row);
    const nodes=flatten(f.$('detail-content'));assert.deepEqual(f.failures,[]);
    assert.ok(nodes.some(n=>n.tag==='pre'&&n.textContent.includes('its text has not been published')));
    assert.ok(!nodes.some(n=>n.textContent.includes('<script>')));
  }
});

function profileFiles(){
  const view=fixture();view.resources=view.resources.slice(0,1);
  for(const [index,filename]of ['IDENTITY.md','SOUL.md'].entries()){
    const doc={id:String(index+4).repeat(64),kind:'document',data:{title:index?'Persona profile':'Identity',filename,source:'reviewed-profile',format:'markdown',content:'# '+filename}};
    view.resources.push(doc);view.relations.push({id:String(index+6).repeat(64),kind:'relationship',data:{source:id,target:doc.id,type:'profile'}});
  }
  return view;
}

function label(f,name){const result=flatten(f.$('detail-content')).find(n=>n.className==='persona-label'&&n.attrs['aria-label']===name);assert.ok(result,'Missing label '+name);return result;}
function pane(f){return flatten(f.$('detail-content')).find(n=>n.className==='persona-pane');}

test('persona labels update one lateral pane and close documents back to Contact',async()=>{
  const view=profileFiles(),f=setup(async path=>path==='/api/state'?view:view.resources.find(row=>path.endsWith(row.id)));
  await f.ui.showDetails(view.resources[0]);
  assert.equal(f.$('detail').attrs['data-kind'],'persona');
  const content=pane(f);assert.equal(label(f,'Contact').attrs['aria-pressed'],'true');
  await label(f,'SOUL').events.click();assert.equal(pane(f),content);
  assert.equal(label(f,'SOUL').attrs['aria-pressed'],'true');
  assert.ok(flatten(content).some(n=>n.tag==='pre'&&n.textContent==='# SOUL.md'));
  await label(f,'IDENTITY').events.click();assert.equal(pane(f),content);
  assert.equal(label(f,'SOUL').attrs['aria-pressed'],'false');
  assert.ok(!flatten(content).some(n=>n.textContent==='# SOUL.md'));
  assert.ok(flatten(content).some(n=>n.tag==='pre'&&n.textContent==='# IDENTITY.md'));
  flatten(content).find(n=>n.textContent==='Close document').events.click();
  assert.equal(label(f,'Contact').attrs['aria-pressed'],'true');
  assert.ok(!flatten(content).some(n=>n.tag==='pre'));
  assert.equal(f.$('detail').open,true);assert.deepEqual(f.failures,[]);
});

test('switching lateral labels discards an earlier document response',async()=>{
  const view=profileFiles();let release;
  const delayed=new Promise(resolve=>release=resolve);
  const f=setup(async path=>path==='/api/state'?view:path.endsWith(view.resources[1].id)?delayed:view.resources.find(row=>path.endsWith(row.id)));
  await f.ui.showDetails(view.resources[0]);
  const pending=label(f,'IDENTITY').events.click();
  await label(f,'SOUL').events.click();release(view.resources[1]);await pending;
  assert.ok(!flatten(pane(f)).some(n=>n.textContent==='# IDENTITY.md'));
  assert.ok(flatten(pane(f)).some(n=>n.tag==='pre'&&n.textContent==='# SOUL.md'));
  assert.deepEqual(f.failures,[]);
});

test('Contact keeps published channels in one pane with safe links and plain text',async()=>{
  const view=profileFiles();view.resources[0].data.contacts={email:'team@example.org',telegram:'@example_bot',phone:'+1 555 0100',phantomchat:'npub-public-reference',website:'javascript:alert(1)',signal:'<img src=x>'};
  const f=setup(async path=>path==='/api/state'?view:view.resources[0]);await f.ui.showDetails(view.resources[0]);
  const nodes=flatten(pane(f));
  assert.ok(nodes.some(n=>n.tag==='a'&&n.href==='mailto:team@example.org'));
  assert.ok(nodes.some(n=>n.tag==='a'&&n.href==='https://t.me/example_bot'));
  assert.ok(nodes.some(n=>n.textContent==='+1 555 0100'));
  assert.ok(nodes.some(n=>n.textContent==='npub-public-reference'));
  assert.ok(nodes.some(n=>n.textContent==='<img src=x>'));
  assert.ok(!nodes.some(n=>n.tag==='img'||n.href?.startsWith('javascript:')));
});

test('relationship labels use explicit counterpart, assignment and organization context only',async()=>{
  const view=profileFiles(),roleId='c'.repeat(64),humanId='d'.repeat(64),orgId='e'.repeat(64),managerId='f'.repeat(64);
  view.resources.push({id:roleId,kind:'role',data:{title:'Coordinator role'}},{id:humanId,kind:'human',data:{name:'Example Human'}},
    {id:orgId,kind:'organization',data:{name:'Example Organization'}},{id:managerId,kind:'role',data:{title:'Manager'}});
  for(const [index,type,source,target]of [[8,'assignment',roleId,id],[9,'counterpart',humanId,id],[10,'context',roleId,orgId],[11,'reports',roleId,managerId]]){
    view.relations.push({id:index.toString(16).padStart(64,'0'),kind:'relationship',data:{type,source,target}});
  }
  const f=setup(async path=>path==='/api/state'?view:view.resources.find(row=>path.endsWith(row.id)));await f.ui.showDetails(view.resources[0]);
  label(f,'Role').events.click();let nodes=flatten(pane(f));
  assert.ok(nodes.some(n=>n.textContent==='Coordinator role'));assert.ok(nodes.some(n=>n.textContent==='Reporting destinations'));
  assert.ok(!flatten(f.$('detail-content')).filter(n=>n.className==='persona-role').some(n=>n.textContent.includes('Manager')));
  label(f,'Human').events.click();assert.ok(flatten(pane(f)).some(n=>n.textContent==='Example Human'));
  label(f,'Organization').events.click();assert.ok(flatten(pane(f)).some(n=>n.textContent==='Example Organization'));
  label(f,'Organization').events.mouseenter();assert.equal(flatten(f.$('detail-content')).find(n=>n.className==='persona-workspace').attrs['data-highlight'],'true');
  assert.deepEqual(f.failures,[]);
});

test('working document tree excludes profiles and never invents source folders',async()=>{
  const view=profileFiles();
  for(const [index,folder]of ['Project/Governance','../private'].entries()){
    const doc={id:String(index+1).repeat(64),kind:'document',data:{title:'Working file '+index,folder,format:'text/plain',content:'Approved text'}};
    view.resources.push(doc);view.relations.push({id:String(index+8).repeat(64),kind:'relationship',data:{source:id,target:doc.id,type:'document'}});
  }
  const f=setup(async path=>path==='/api/state'?view:view.resources[0]);await f.ui.showDetails(view.resources[0]);label(f,'Documents').events.click();
  const nodes=flatten(pane(f));assert.deepEqual(nodes.filter(n=>n.tag==='summary').map(n=>n.textContent),['Project','Governance','Unfiled documents']);
  assert.deepEqual(nodes.filter(n=>n.className==='profile-link profile-document').map(n=>n.textContent),['Working file 0','Working file 1']);
  assert.ok(!nodes.some(n=>n.textContent==='IDENTITY.md'||n.textContent==='SOUL.md'||n.textContent==='private'));
});

test('missing sources stay explicit and choosing a non-document pane cancels a pending read',async()=>{
  const view=fixture();view.resources=view.resources.slice(0,1);
  const f=setup(async path=>path==='/api/state'?view:view.resources[0]);await f.ui.showDetails(view.resources[0]);
  label(f,'SOUL').events.click();assert.ok(flatten(pane(f)).some(n=>n.textContent.includes('has not been published')));
  label(f,'Documents').events.click();assert.ok(flatten(pane(f)).some(n=>n.textContent.startsWith('No working documents')));
  const files=profileFiles();let release;const pending=new Promise(resolve=>release=resolve);
  const g=setup(async path=>path==='/api/state'?files:path.endsWith(id)?files.resources[0]:pending);await g.ui.showDetails(files.resources[0]);
  const read=label(g,'SOUL').events.click();label(g,'Contact').events.click();release(files.resources[2]);await read;
  assert.ok(!flatten(pane(g)).some(n=>n.tag==='pre'));assert.equal(label(g,'Contact').attrs['aria-pressed'],'true');
});

test('lateral document reads still reject policy changes and cannot repopulate a closed card',async()=>{
  const view=profileFiles();let states=0;
  const f=setup(async path=>path==='/api/state'?{...view,policy_revision:++states<3?view.policy_revision:'0'.repeat(64)}:view.resources.find(row=>path.endsWith(row.id)));
  await f.ui.showDetails(view.resources[0]);await label(f,'SOUL').events.click();
  assert.deepEqual(f.failures,['Profile information changed']);assert.ok(!flatten(pane(f)).some(n=>n.tag==='pre'));
  let release;const pending=new Promise(resolve=>release=resolve);
  const g=setup(async path=>path==='/api/state'?view:path.endsWith(id)?view.resources[0]:pending);await g.ui.showDetails(view.resources[0]);
  const read=label(g,'SOUL').events.click();g.ui.close();release(view.resources[2]);await read;
  assert.equal(g.$('detail-content').children.length,0);assert.deepEqual(g.failures,[]);
});
