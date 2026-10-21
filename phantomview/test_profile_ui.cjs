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
  const document=nodes.find(n=>n.className==='profile-link profile-document');assert.ok(document);
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
    const doc={id:String(index+4).repeat(64),kind:'document',data:{title:index?'Persona profile':'Identity',filename,format:'markdown',content:'# '+filename}};
    view.resources.push(doc);view.relations.push({id:String(index+6).repeat(64),kind:'relationship',data:{source:id,target:doc.id,type:'profile'}});
  }
  return view;
}

test('persona profile labels open adjacent readers and collapse without another dialog',async()=>{
  const view=profileFiles(),f=setup(async path=>path==='/api/state'?view:view.resources.find(row=>path.endsWith(row.id)));
  await f.ui.showDetails(view.resources[0]);
  assert.equal(f.$('detail').attrs['data-kind'],'persona');
  const rows=flatten(f.$('detail-content')).filter(node=>node.className==='profile-document-row');
  assert.deepEqual(rows.map(row=>row.children[0].textContent),['IDENTITY','SOUL']);
  const [identity,soul]=rows.map(row=>row.children[0]);
  await soul.events.click();assert.equal(soul.attrs['aria-expanded'],'true');
  assert.equal(rows[1].children[1].hidden,false);
  assert.ok(flatten(rows[1]).some(node=>node.tag==='pre'&&node.textContent==='# SOUL.md'));
  assert.equal(rows[0].children[1].hidden,true);
  await identity.events.click();assert.equal(rows[1].children[1].hidden,true);
  assert.equal(soul.attrs['aria-expanded'],'false');
  assert.ok(flatten(rows[0]).some(node=>node.tag==='pre'&&node.textContent==='# IDENTITY.md'));
  await identity.events.click();assert.equal(rows[0].children[1].hidden,true);
  assert.equal(f.$('detail').open,true);assert.deepEqual(f.failures,[]);
});

test('switching profile labels discards the earlier document response',async()=>{
  const view=profileFiles();let release;
  const delayed=new Promise(resolve=>release=resolve);
  const f=setup(async path=>path==='/api/state'?view:path.endsWith(view.resources[1].id)?delayed:view.resources.find(row=>path.endsWith(row.id)));
  await f.ui.showDetails(view.resources[0]);
  const rows=flatten(f.$('detail-content')).filter(node=>node.className==='profile-document-row');
  const pending=rows[0].children[0].events.click();
  await rows[1].children[0].events.click();release(view.resources[1]);await pending;
  assert.equal(rows[0].children[1].hidden,true);
  assert.ok(!flatten(rows[0]).some(node=>node.tag==='pre'));
  assert.ok(flatten(rows[1]).some(node=>node.tag==='pre'&&node.textContent==='# SOUL.md'));
  assert.deepEqual(f.failures,[]);
});
