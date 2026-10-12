'use strict';
const assert=require('node:assert/strict');
const {reviewRoutes}=require('./review.js');
const roles=['ceo','project','staff'].map(id=>({id,key:`au:roles:${id}`,org:'au'}));
const relation=(from,to,label)=>({from:`au:roles:${from}`,to:`au:roles:${to}`,type:'escalation',label});
const snapshot={roles,edges:[relation('ceo','project','Decision returned to the project'),relation('project','ceo','Request CEO approval')]};
let model=reviewRoutes(snapshot,'au:roles:ceo');
assert.equal(model.routes[0].length,2);
assert.equal(model.routes[0][0].label,'Decision returned to the project');
assert.equal(model.routes[0].at(-1).to,'au:roles:ceo');
model=reviewRoutes({roles,edges:[relation('ceo','project','Response'),relation('*','ceo','Exception approval')]},'au:roles:ceo');
assert.equal(model.routes[0].length,2);
assert.equal(model.routes[0][1].inherited,true);
assert.ok(!model.edges.some(e=>e.from==='au:roles:ceo'&&e.to==='au:roles:ceo'));
assert.equal(reviewRoutes(snapshot,'foreign:roles:ceo').routes.length,0);
assert.equal(reviewRoutes({roles,edges:[relation('project','ceo','Escalate')]},'au:roles:project').routes.length,0);
const denseRoles=['ceo','project','staff','finance','partners','training'].map(id=>({id,key:`au:roles:${id}`,org:'au'}));
const dense={roles:denseRoles,edges:denseRoles.flatMap(a=>denseRoles.filter(b=>a!==b).map(b=>relation(a.id,b.id,'Conditional')))};
model=reviewRoutes(dense,'au:roles:ceo');
assert.equal(model.routes[0].length,2);
assert.ok(model.routes.length<=3&&model.routes.every(route=>route.length<=6));
console.log('Review route checks passed: closed route, source conditions, wildcard provenance, setup isolation and bounded search.');

// Classic browser scripts share one lexical scope; reject cross-file name collisions.
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
new vm.Script(['i18n.js','installation.js','review.js','assistant.js','app.js'].map(file=>fs.readFileSync(path.join(__dirname,file),'utf8')).join('\n'));
console.log('Combined browser script scope check passed.');
