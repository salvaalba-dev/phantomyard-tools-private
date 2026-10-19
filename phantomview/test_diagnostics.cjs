'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
const scope={Date};vm.createContext(scope);
vm.runInContext(source.slice(source.indexOf('function operationSummary('),source.indexOf('function operationBadge(')),scope);
vm.runInContext(source.slice(source.indexOf('function operationState('),source.indexOf('function operationBadge(')),scope);
const summary=scope.operationSummary,status=scope.operationState,clock=Date.now();
const actor={diagnostics:{checked_at:new Date(clock).toISOString(),stale_after_seconds:900,checks:[{id:'service',status:'ok'},{id:'telegram',status:'not-configured'}]}};
assert.equal(summary(actor,clock).label,'Local checks OK');
assert.equal(status(actor,clock).label,'Alive');
assert.equal(summary(actor,clock+901000).label,'Check expired');
assert.equal(status(actor,clock+901000).label,'Check expired');
assert.equal(summary(actor,clock-61000).label,'Check expired');
actor.diagnostics.checks.push({id:'heartbeat',status:'attention'});
assert.equal(summary(actor,clock).label,'Needs attention');
assert.equal(status(actor,clock).label,'Alive · review');
actor.diagnostics.checks.pop();actor.diagnostics.doctor_error='timeout';
assert.equal(summary(actor,clock).label,'Partial checks');
assert.equal(status(actor,clock).label,'Alive · partial');
actor.diagnostics.checks[0].status='attention';
assert.equal(status(actor,clock).label,'Not running');
actor.diagnostics.checks[0].status='unknown';
assert.equal(status(actor,clock).label,'Unverified');
actor.diagnostics.checks[0].status='ok';
assert.equal(status({...actor,profile_remote:true},clock).label,'Unverified');
assert.equal(summary({runtime:'unknown'},clock).label,'Unverified');
assert.equal(summary({runtime:'reported'},clock).label,'Report available');
console.log('Diagnostic UI checks passed: freshness, partial evidence, attention, optional channels and unverified runtime.');

// Render real persona cards to prevent operational flags disappearing from this view.
const cardScope={actors:()=>[{id:'atlas',key:'example:atlas',tools:[],description:'',role:'staff'}],
 esc:String,uiText:key=>key,roleFor:()=>({name:'Staff'}),departmentName:()=>'',
 badge:label=>label,installation:()=>'',installationEvidenceLabel:()=>'',tags:()=>'',operationBadge:()=>'<span>● Alive</span>'};
vm.createContext(cardScope);
vm.runInContext(source.slice(source.indexOf('function personas(){'),source.indexOf('function tools(){')),cardScope);
assert.match(cardScope.personas(),/persona-operation[^]*● Alive/);
console.log('Persona card rendering includes the operational status flag.');
