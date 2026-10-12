'use strict';
// AU widget pattern: text-only bubbles, bounded transcript and asynchronous polling.
const consultationLabels={en:{send:'Send',cancel:'Cancel',clear:'New analysis',expand:'Expand chat',reduce:'Reduce chat',scope:'PhantomView analysis only · no tools',placeholder:'Ask about PhantomView or this finding…',unavailable:'Assistant unavailable',idle:'Uses this dashboard session. No second sign-in.',working:'Analyzing with the default persona…',selected:'Selected finding',overview:'Current view',helper:'Prompt helper',copy:'Copy prompt',download:'Download .txt',copied:'Copied',held:'Held by the safety screen',failed:'Consultation failed; retry later',expired:'Session expired; request a new temporary link',close:'Close',unknown:'Default persona not verified'},es:{send:'Enviar',cancel:'Cancelar',clear:'Nuevo análisis',expand:'Ampliar chat',reduce:'Reducir chat',scope:'Solo análisis de PhantomView · sin herramientas',placeholder:'Pregunta sobre PhantomView o este hallazgo…',unavailable:'Asistente no disponible',idle:'Usa la sesión del dashboard. Sin una segunda identificación.',working:'Analizando con la persona por defecto…',selected:'Hallazgo seleccionado',overview:'Vista actual',helper:'Prompt helper',copy:'Copiar prompt',download:'Descargar .txt',copied:'Copiado',held:'Retenido por el filtro de seguridad',failed:'La consulta falló; inténtalo más tarde',expired:'Sesión caducada; solicita otro enlace temporal',close:'Cerrar',unknown:'Persona por defecto sin verificar'}};
const consultationText=k=>consultationLabels[typeof uiLanguage==='undefined'?'es':uiLanguage][k]||k;
let consultationJob=null,consultationBusy=false,consultationGeneration=0,consultationTurns=[],consultationScope='',consultationResult='',consultationReady=null;
function currentAssistantFinding(){return selectedReviewFinding?findings().find(f=>findingId(f)===selectedReviewFinding):null;}
function renderAssistant(){
 document.querySelector('.assistant-heading b').textContent='PhantomView · '+(uiLanguage==='es'?'Asistente':'Assistant');
 const persona=assistantSelection(state?.snapshot||{},selectedOrg),finding=state?currentAssistantFinding():null;
 const scope=JSON.stringify([selectedOrg,current,finding?findingId(finding):'']);
 if(consultationScope!==scope||!state){
  const old=consultationJob;consultationGeneration++;consultationBusy=false;consultationJob=null;
  if(old)consultationFetch('/jobs/'+old+'/cancel','POST',{}).catch(()=>{});
  consultationScope=scope;consultationTurns=[];consultationResult='';
  document.querySelector('#assistant-messages').replaceChildren();
  document.querySelector('#prompt-result')?.close();
 }
 document.querySelector('#assistant-context').textContent=persona.status==='ready'?`${uiText('Default persona')} · ${persona.persona}`:consultationText('unknown');
 document.querySelector('#assistant-scope').textContent=finding?consultationText('selected')+': '+uiMessage(finding.title):consultationText('overview')+': '+uiText(sections.find(s=>s[0]===current)?.[2]||current);
 document.querySelector('#assistant-question').placeholder=consultationText('placeholder');
 document.querySelector('#assistant-question').setAttribute('aria-label',consultationText('placeholder'));
 document.querySelector('#assistant-send').textContent=consultationText('send');
 document.querySelector('#assistant-send').disabled=consultationBusy||persona.status!=='ready'||consultationReady===false;
 document.querySelector('#assistant-clear').textContent=consultationText('clear');
 document.querySelector('#assistant-cancel').textContent=consultationText('cancel');
 document.querySelector('#assistant-cancel').hidden=!consultationBusy;
 document.querySelector('#assistant-expand').textContent=consultationText(document.querySelector('#assistant-panel').classList.contains('expanded')?'reduce':'expand');
 document.querySelector('#assistant-status').textContent=consultationBusy?consultationText('working'):consultationReady===false?consultationText('unavailable'):consultationText('scope')+'. '+consultationText('idle');
 document.querySelectorAll('[data-prompt-helper]').forEach(b=>{b.textContent=consultationText('helper');b.disabled=consultationBusy||persona.status!=='ready'||consultationReady===false;});
}
async function consultationFetch(path,method='GET',body){
 const response=await fetch('/api/assistant'+path,{method,credentials:'same-origin',headers:method==='POST'?{'Content-Type':'application/json'}:{},body:body===undefined?undefined:JSON.stringify(body)});
 if(response.status===401)throw Error(consultationText('expired'));
 const data=await response.json();if(!response.ok)throw Error(data.error||consultationText('failed'));return data;
}
function consultationMessage(role,text){
 const row=document.createElement('div');row.className='assistant-message '+role;
 const label=document.createElement('b');label.textContent=role==='human'?(uiLanguage==='es'?'Tú':'You'):(state?.snapshot?.assistant?.persona||'Assistant');
 const content=document.createElement('p');content.textContent=text;row.append(label,content);
 const log=document.querySelector('#assistant-messages');log.append(row);while(log.children.length>12)log.firstChild.remove();log.scrollTop=log.scrollHeight;
}
function showPromptResult(text){
 consultationResult=text;let dialog=document.querySelector('#prompt-result');
 if(!dialog){dialog=document.createElement('dialog');dialog.id='prompt-result';dialog.innerHTML='<h2>Prompt helper</h2><textarea readonly rows="18" aria-label="Generated investigation prompt"></textarea><div class="assistant-actions"><button class="button" data-copy-prompt></button><button class="button" data-download-prompt></button><button class="button" data-close-prompt></button></div><p role="status"></p>';document.body.append(dialog);}
 dialog.querySelector('textarea').value=text;
 for(const [attr,key] of [['copy-prompt','copy'],['download-prompt','download'],['close-prompt','close']])dialog.querySelector('[data-'+attr+']').textContent=consultationText(key);
 dialog.querySelector('p').textContent=consultationText('scope');dialog.showModal();
}
async function submitConsultation(kind,question=''){
 if(consultationBusy||!state)return;
 const finding=currentAssistantFinding(),generation=++consultationGeneration,scope=consultationScope;
 consultationBusy=true;renderAssistant();if(kind==='question')consultationMessage('human',question);
 try{
  let job=await consultationFetch('/jobs','POST',{kind,org:selectedOrg||state.snapshot.assistant.org,view:current,finding:finding?[finding.entity,finding.title,finding.source]:null,question,locale:uiLanguage,request_id:crypto.randomUUID(),turns:kind==='question'?consultationTurns.slice(-4):[]});
  if(generation!==consultationGeneration){await consultationFetch('/jobs/'+job.id+'/cancel','POST',{});return;}
  consultationJob=job.id;
  while(['queued','running'].includes(job.status)){
   await new Promise(resolve=>setTimeout(resolve,1000));if(generation!==consultationGeneration)return;
   job=await consultationFetch('/jobs/'+consultationJob);
  }
  if(generation!==consultationGeneration)return;
  if(job.status==='complete'){
   if(kind==='prompt-helper')showPromptResult(job.text);
   else{consultationMessage('assistant',job.text);if(scope===consultationScope)consultationTurns=[...consultationTurns,{role:'human',text:question.slice(0,800)},{role:'assistant',text:job.text.slice(0,800)}].slice(-4);}
  }else throw Error(consultationText(job.status==='held'?'held':'failed'));
 }catch(error){if(generation===consultationGeneration)consultationMessage('assistant',error.message);}
 finally{if(generation===consultationGeneration){consultationJob=null;consultationBusy=false;renderAssistant();}}
}
async function cancelConsultation(){const id=consultationJob;consultationGeneration++;consultationBusy=false;consultationJob=null;if(id)try{await consultationFetch('/jobs/'+id+'/cancel','POST',{});}catch{}renderAssistant();}
document.querySelector('#assistant-form').addEventListener('submit',event=>{event.preventDefault();const input=document.querySelector('#assistant-question'),q=input.value.trim();if(q){input.value='';submitConsultation('question',q);}});
document.querySelector('#assistant-cancel').addEventListener('click',cancelConsultation);
document.querySelector('#assistant-clear').addEventListener('click',async()=>{await cancelConsultation();consultationTurns=[];document.querySelector('#assistant-messages').replaceChildren();});
document.querySelector('#assistant-expand').addEventListener('click',()=>{const panel=document.querySelector('#assistant-panel');const expanded=panel.classList.toggle('expanded');document.querySelector('#assistant-expand').setAttribute('aria-expanded',String(expanded));renderAssistant();});
document.addEventListener('click',async event=>{
 if(event.target.closest('[data-prompt-helper]'))submitConsultation('prompt-helper');
 if(event.target.closest('[data-close-prompt]'))document.querySelector('#prompt-result').close();
 if(event.target.closest('[data-copy-prompt]'))try{await navigator.clipboard.writeText(consultationResult);document.querySelector('#prompt-result p').textContent=consultationText('copied');}catch{document.querySelector('#prompt-result textarea').select();}
 if(event.target.closest('[data-download-prompt]')){const url=URL.createObjectURL(new Blob([consultationResult],{type:'text/plain;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download='phantomview-investigation.txt';link.click();URL.revokeObjectURL(url);}
});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.querySelector('#assistant-panel').classList.contains('expanded')){document.querySelector('#assistant-panel').classList.remove('expanded');renderAssistant();}});
setInterval(async()=>{if(!state)return;try{const status=await consultationFetch('/status');consultationReady=status.ready===true;}catch{consultationReady=false;}renderAssistant();},15000);
