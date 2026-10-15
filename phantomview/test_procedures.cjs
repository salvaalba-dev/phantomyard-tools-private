'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const app=fs.readFileSync(__dirname+'/app.js','utf8');
const source=app.slice(app.indexOf('function procedures(){'),app.indexOf('function changes(){'));
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const context={document:{querySelectorAll:()=>[]},esc,uiText:x=>x,badge:x=>`<span>${esc(x)}</span>`,time:x=>x,
 selectedOrg:'example',selectedDept:'',searchMatch:()=>true,orgMatch:a=>a.org==='example',empty:(a,b)=>a+b,
 state:{snapshot:{actors:[{id:'staff',org:'example',department:'operations',role:'staff'}],
 procedure_discovery:{automatic:true,partial:false},procedures:[
 {id:'rule',org:'example',title:'Escalation',kind:'rules',origin:'organization',steps:[{from:'staff',to:'lead',action:'If blocked'}]},
 {id:'note',org:'example',title:'<script>bad()</script>',kind:'ordered',origin:'knowledge',source_owner:'staff',source_note:'a'.repeat(64),steps:[{actor:'',action:'Read <img onerror="bad()">'}]},
 {id:'other',org:'other',title:'Foreign procedure',steps:[]}]}}};
vm.createContext(context);vm.runInContext(source,context);
let html=vm.runInContext('procedures()',context);
assert.ok(html.includes('staff → lead'));
assert.ok(html.includes('Conditional rules'));
assert.ok(html.includes('Step owner not specified'));
assert.ok(html.includes('data-note="'+'a'.repeat(64)+'"'));
assert.ok(!html.includes('<script>')&&!html.includes('<img onerror'));
assert.ok(!html.includes('Foreign procedure'));
context.selectedDept='operations';
html=vm.runInContext('procedures()',context);
assert.ok(html.includes('Escalation')&&html.includes('data-procedure="note"'));
context.document.querySelectorAll=()=>[{dataset:{procedure:'note'}}];
assert.ok(vm.runInContext('procedures()',context).includes('data-procedure="note" open'));
console.log('Procedure rendering passed: source links, conditional flows, scope, escaping, missing owners and expanded-state preservation.');
