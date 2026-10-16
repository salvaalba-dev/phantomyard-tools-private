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
