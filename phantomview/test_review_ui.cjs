/* Behavioral tests for offline review decisions; no browser or external package. */
'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {ReviewModel} = require('./review_ui.js');
const a = 'a'.repeat(64), b = 'b'.repeat(64), c = 'c'.repeat(64);
function fixture() {
  return {draft_revision:'d'.repeat(64), organization_revision:'e'.repeat(64),
    categories:[{id:'category-1'}, {id:'category-3'}, {id:'category-4.2'}],
    scopes:[{id:'example',kind:'organization'}, {id:'river-project',kind:'project'}],
    resources:[
      {id:a,kind:'persona',payload_sha256:'1'.repeat(64),provenance:{identity:'lead'},data:{title:'Project lead'}},
      {id:b,kind:'finding',payload_sha256:'2'.repeat(64),requires:[a],provenance:{identity:'finding'},data:{title:'Profile warning'}},
      {id:c,kind:'relationship',payload_sha256:'3'.repeat(64),endpoints:[a,b],provenance:{identity:'edge'},data:{title:'Link'}}]};
}
const grant = {category:'category-1',scope:'example',secret:false};
test('export requires explicit classification and complete source dependencies', () => {
  const model = new ReviewModel(fixture());
  assert.throws(() => model.export()); model.select(b,true);
  assert.throws(() => model.apply(grant,false)); model.apply(grant,true);
  assert.throws(() => model.export()); model.includeDependencies();
  assert.equal(model.issues().unreviewed,1); model.apply(grant,true);
  const decisions = model.export(); assert.equal(decisions.resources.length,2);
  assert.equal(decisions.resources[0].project,null);
  assert.equal(decisions.draft_revision,'d'.repeat(64));
});
test('recursive dependencies and relationship endpoints are included only by explicit action', () => {
  const model = new ReviewModel(fixture()); model.select(c,true);
  assert.equal(model.selected.size,1); model.includeDependencies();
  assert.equal(model.selected.size,3); model.apply(grant,true);
  assert.equal(model.export().resources.length,3);
  model.select(a,false); assert.throws(() => model.export());
});
test('unknown scopes, categories, category zero and missing secret review fail', () => {
  const model = new ReviewModel(fixture()); model.select(a,true);
  for (const invalid of [{category:'category-0'},{category:'category-999'},{scope:'unknown'},{secret:null}]) {
    assert.throws(() => model.apply({...grant,...invalid},true));
  }
  assert.throws(() => model.select('unknown',true));
});
test('project category needs project scope and exact project binding', () => {
  const model = new ReviewModel(fixture()); model.select(a,true);
  assert.throws(() => model.apply({...grant,category:'category-4.2'},true));
  model.apply({...grant,category:'category-4.2',scope:'river-project'},true);
  assert.equal(model.export().resources[0].project,'river-project');
});
test('filtering never changes selection, decisions or export scope', () => {
  const model = new ReviewModel(fixture()); model.select(a,true); model.apply(grant,true);
  assert.equal(model.filter('warning','finding').length,1);
  assert.equal(model.export().resources[0].id,a);
  const exported = model.export(); exported.resources[0].scope.id='tampered';
  assert.equal(model.export().resources[0].scope.id,'example');
});
test('new selection never inherits classifications from other records', () => {
  const model = new ReviewModel(fixture()); model.select(a,true); model.apply(grant,true);
  model.select(b,true); assert.equal(model.issues().unreviewed,1); assert.throws(() => model.export());
});
