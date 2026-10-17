/* Visible-only workspace models and directed graph behavior. */
'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const {ScopedModel}=require('./scoped-ui.js');
const a='a'.repeat(64),b='b'.repeat(64),c='c'.repeat(64),e='e'.repeat(64);
function fixture(){return {schema_version:1,complete_corpus:false,organization:'example',scope_id:'river-project',
  policy_revision:'1'.repeat(64),view_revision:'2'.repeat(64),counts:{human:9000},
  resources:[{id:a,kind:'partner',data:{title:'River partner'}},{id:b,kind:'task',data:{title:'Field review'}},
    {id:c,kind:'objective',data:{title:'Improve monitoring'}}],
  relations:[{id:e,kind:'relationship',data:{source:a,target:b,label:'Assigned work',type:'assignment'}}]};}
test('project menus contain only visible kinds and visible counts ignore global claims',()=>{
  const model=new ScopedModel(fixture());assert.deepEqual(model.sections().map(row=>row.kind),['objective','partner','task']);
  assert.deepEqual(model.counts(),{partner:1,task:1,objective:1});assert.equal(model.organization(),'example');
});

function navigation(data){return {schema_version:1,api_version:1,organization:data.organization,scope_id:data.scope_id,
  policy_revision:data.policy_revision,view_revision:data.view_revision,
  assistant:{persona:null,eligible:false,source:'session-issuer'},
  core:[{id:'core:partner',kind:'partner',label:'Partners',view:'table',count:1}],
  modules:[{id:'project-management',label:'Project management',assistant:{persona:'project-guide',eligible:true,source:'module'},
    sections:[{id:'project-management:partners',kind:'partner',label:'Project partners',view:'cards',count:1}]}]};}

test('server navigation preserves core and module sections with distinct local assistant routes',()=>{
  const data=fixture();data.navigation=navigation(data);const model=new ScopedModel(data);
  assert.deepEqual(model.sections().map(row=>row.id),['core:partner','project-management:partners']);
  assert.equal(model.selection('project-management:partners').view,'cards');
  assert.equal(model.assistant('project-management:partners').persona,'project-guide');
  assert.equal(model.assistant('core:partner').eligible,false);
  data.navigation.modules[0].label='Changed';assert.equal(model.sections()[1].module,'Project management');
});

test('issuer navigation accepts only its matching operational transport',()=>{
  const data=fixture();data.navigation=navigation(data);
  data.navigation.assistant={persona:'coordinator',eligible:true,source:'session-issuer'};
  const model=new ScopedModel(data),info={available:true,persona:'coordinator',scope_id:data.scope_id};
  assert.equal(model.assistant('core:partner').source,'session-issuer');
  assert.equal(model.acceptsAssistant(info,'core:partner'),true);
  assert.equal(model.acceptsAssistant({...info,persona:'administrator'},'core:partner'),false);
  assert.equal(model.acceptsAssistant({...info,available:false},'core:partner'),false);
});

test('stale, hidden-kind, duplicate and executable navigation cannot be rendered',()=>{
  for(const mutate of [nav=>nav.view_revision='f'.repeat(64),nav=>nav.core[0].kind='human',
    nav=>nav.core[0].count=9000,nav=>nav.modules.push(nav.modules[0]),nav=>nav.core[0].view='script',
    nav=>nav.core[0].label='<script>',nav=>nav.modules[0].assistant.eligible='true']){
    const data=fixture();data.navigation=navigation(data);mutate(data.navigation);assert.throws(()=>new ScopedModel(data));
  }
});

test('module graph impact does not traverse records outside the selected section',()=>{
  const model=new ScopedModel(fixture());assert.deepEqual([...model.impact(a,60,'partner').nodes],[a]);
  assert.equal(model.impact(a,60,'partner').edges.size,0);
});

test('eligible module metadata never enables the wrong persona transport',()=>{
  const data=fixture();data.navigation=navigation(data);const model=new ScopedModel(data);
  const info={available:true,persona:'project-guide',scope_id:data.scope_id};
  assert.equal(model.acceptsAssistant(info,'project-management:partners'),true);
  assert.equal(model.acceptsAssistant({...info,persona:'administrator'},'project-management:partners'),false);
  assert.equal(model.acceptsAssistant({...info,scope_id:'other-project'},'project-management:partners'),false);
  assert.equal(model.acceptsAssistant({...info,available:false},'project-management:partners'),false);
  assert.equal(model.acceptsAssistant(info,'core:partner'),false);
});
test('legacy snapshot envelopes and malformed endpoint projections fail closed',()=>{
  assert.throws(()=>new ScopedModel({snapshot:fixture()}));const data=fixture();data.relations[0].data.target='f'.repeat(64);
  assert.throws(()=>new ScopedModel(data));data.relations=[];data.resources.push(data.resources[0]);assert.throws(()=>new ScopedModel(data));
});
test('graph impact follows outgoing flows and handles cycles without touching unrelated nodes',()=>{
  const data=fixture();data.relations.push({id:'d'.repeat(64),kind:'relationship',data:{source:b,target:a}});
  const impact=new ScopedModel(data).impact(a);assert.deepEqual([...impact.nodes],[a,b]);assert.equal(impact.edges.size,2);
  assert.equal(impact.nodes.has(c),false);assert.equal(new ScopedModel(data).impact('f'.repeat(64)).nodes.size,0);
});
test('search preserves relationship-only matches without requiring unrelated endpoint cards',()=>{
  const data=fixture(),result={...data,results:data.relations,partial:false};const model=ScopedModel.search(result);
  assert.equal(model.resources[0].kind,'relationship');assert.equal(model.title(model.resources[0]),'Assigned work');
  assert.deepEqual(model.counts(),{relationship:1});
  delete result.scope_id;assert.throws(()=>ScopedModel.search(result));
});
test('projection bodies are detached and graph limits exclude out-of-view endpoints',()=>{
  const data=fixture(),model=new ScopedModel(data);data.resources[0].data.title='Changed elsewhere';
  assert.equal(model.resources[0].data.title,'River partner');assert.deepEqual([...model.impact(a,1).nodes],[a]);
  assert.equal(model.impact(a,1).edges.size,0);
});
