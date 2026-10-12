'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function context(initial={}){
 const store=new Map(Object.entries(initial)),events={},selector={value:''},calls=[];
 const sandbox={localStorage:{getItem:key=>store.get(key)||null,setItem:(key,value)=>store.set(key,value)},
  document:{documentElement:{lang:''},querySelectorAll:()=>[],querySelector:selectorName=>selectorName==='#global-language'?selector:{open:false,dataset:{}},addEventListener:(name,handler)=>events[name]=handler},
  state:null,drawNav:()=>calls.push('nav'),accessScreen:()=>calls.push('access'),fillFilters:()=>calls.push('filters'),render:()=>calls.push('render')};
 vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(__dirname,'i18n.js'),'utf8'),sandbox);
 return {sandbox,store,events,selector,calls};
}
let fixture=context();
assert.equal(vm.runInContext('uiText("People")',fixture.sandbox),'Personas');
fixture.events.change({target:{id:'global-language',value:'en'}});
assert.equal(vm.runInContext('uiText("People")',fixture.sandbox),'People');
assert.equal(fixture.store.get('phantomview-language'),'en');
assert.equal(fixture.sandbox.document.documentElement.lang,'en');
assert.equal(vm.runInContext('uiMessage("Autenticación necesaria")',fixture.sandbox),'Authentication necessary');
assert.equal(vm.runInContext('uiMessage("Ruta circular posible de escalado: revisar condiciones y límite de saltos")',fixture.sandbox),'Possible circular escalation route: review conditions and hop limit');
assert.equal(vm.runInContext('uiMessage("My original KB document text")',fixture.sandbox),'My original KB document text');
fixture.sandbox.state={snapshot:{}};
fixture.events.change({target:{id:'global-language',value:'es'}});
assert.ok(fixture.calls.includes('filters')&&fixture.calls.includes('render'));
assert.equal(vm.runInContext('uiText("Tools")',fixture.sandbox),'Herramientas');
vm.runInContext('setUiLanguage("unsupported")',fixture.sandbox);
assert.equal(fixture.store.get('phantomview-language'),'es');
fixture=context({'phantomview-language':'en'});
assert.equal(vm.runInContext('uiText("Documents")',fixture.sandbox),'Documents');
fixture=context({'phantomview-installation-language':'en'});
assert.equal(vm.runInContext('uiText("Organization")',fixture.sandbox),'Organization');
const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
assert.equal((html.match(/id="global-language"/g)||[]).length,1);
assert.ok(!fs.readFileSync(path.join(__dirname,'installation.js'),'utf8').includes('id="installation-language"'));
console.log('Global language checks passed: shared selector, persistence, migration, access messages, data preservation and invalid-locale rejection.');

// Exercise rendered filter options, not just catalog lookups.
fixture=context({'phantomview-language':'en'});
const filterNodes={'#org-filter':{innerHTML:'',value:''},'#dept-filter':{innerHTML:'',value:''}};
Object.assign(fixture.sandbox,{$:key=>filterNodes[key],esc:value=>value,selectedOrg:'',selectedDept:'',orgMatch:()=>true,state:{snapshot:{organizations:[{id:'au',name:'Aquaponics United'}],departments:[{id:'direction',name:'Dirección'}]}}});
const app=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
vm.runInContext(app.slice(app.indexOf('function fillFilters()'),app.indexOf('function stat(')),fixture.sandbox);
vm.runInContext('fillFilters()',fixture.sandbox);
assert.ok(filterNodes['#org-filter'].innerHTML.includes('All organizations'));
assert.ok(!filterNodes['#org-filter'].innerHTML.includes('${uiText'));
vm.runInContext("uiLanguage='es';fillFilters()",fixture.sandbox);
assert.ok(filterNodes['#dept-filter'].innerHTML.includes('Todos los departamentos'));
console.log('Localized filter option rendering passed.');
