'use strict';
function assistantSelection(snapshot, organization, clock=Date.now()){
 const row=snapshot?.assistant;
 if(!row||organization&&row.org!==organization)return {status:'unknown'};
 const checked=Date.parse(row.checked_at),age=clock-checked;
 if(!Number.isFinite(checked)||age>900000||age< -60000)return {status:'expired'};
 return {status:'ready',...row};
}
function renderAssistant(){
 const context=document.querySelector('#assistant-context'),button=document.querySelector('#assistant-contact');
 const assistant=assistantSelection(state?.snapshot||{assistant:accessInfo.assistant},selectedOrg);
 let message=assistant.status==='expired'?'Default observation expired':'Default persona not verified';
 if(assistant.status==='ready'){
  context.innerHTML=`${uiText('Default persona')} · <strong>${esc(assistant.persona)}</strong>`;
  const issuer=state?.access?.actor;
  if(issuer&&issuer!==assistant.persona)context.innerHTML+=`<br>${uiText('Issuer change pending configuration')}`;
 }else context.textContent=uiText(message);
 button.disabled=assistant.status!=='ready'||!assistant.npub;
 button.textContent=uiText(assistant.status==='ready'&&!assistant.npub?'Contact not declared':'Copy contact');
 button.dataset.npub=button.disabled?'':assistant.npub;
 document.querySelector('#assistant-expand').textContent=uiText(document.querySelector('#assistant-panel').classList.contains('expanded')?'Reduce chat':'Expand chat');
}
document.querySelector('#assistant-contact').addEventListener('click',async()=>{
 const button=document.querySelector('#assistant-contact');
 const assistant=assistantSelection(state?.snapshot||{assistant:accessInfo.assistant},selectedOrg);
 if(assistant.status!=='ready'||!assistant.npub)return renderAssistant();
 try{await navigator.clipboard.writeText(assistant.npub);button.textContent=uiText('Contact copied');}
 catch{button.textContent=uiText('Copy failed; use the persona profile');}
});
document.querySelector('#assistant-expand').addEventListener('click',()=>{
 const panel=document.querySelector('#assistant-panel');
 const expanded=panel.classList.toggle('expanded');
 document.querySelector('#assistant-expand').setAttribute('aria-expanded',String(expanded));
 renderAssistant();
});
document.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&document.querySelector('#assistant-panel').classList.contains('expanded')){
  document.querySelector('#assistant-panel').classList.remove('expanded');
  document.querySelector('#assistant-expand').setAttribute('aria-expanded','false');
  renderAssistant();
 }
});
