/* Human-operated updates. The reader never receives install privileges. */
'use strict';
let botVersionState=null,botVersionBusy=false;
const botVersionWords={
 'PhantomBot update':'Actualizar PhantomBot','Installed binary':'Binario instalado','Available stable release':'Versión estable disponible',
 'Check versions':'Comprobar versiones','Up to date':'Actualizado','Version not verified':'Versión sin verificar','Copy update command':'Copiar comando de actualización',
 'Copied':'Copiado','Close':'Cerrar','Release notes':'Notas de la versión','Open VPS terminal':'Abrir terminal del VPS',
 'Run this command as the installation administrator. The official updater asks for confirmation.':'Ejecuta este comando como administrador de la instalación. El actualizador oficial pide confirmación.',
 'This binary is shared by multiple personas/setups on this host. Review the release and plan their service restarts.':'Este binario lo comparten varias personas o instalaciones del servidor. Revisa la versión y planifica el reinicio de sus servicios.',
 'The badge observes the installed binary, not the version loaded by each running service. The isolated analysis runtime is versioned separately.':'La etiqueta observa el binario instalado, no la versión cargada por cada servicio en ejecución. El motor aislado de análisis mantiene su propia versión.',
 'No installation runs from this dashboard. The version refreshes automatically after a terminal or scheduled update.':'La instalación se ejecuta desde la terminal. La versión se refresca automáticamente tras una actualización manual o programada.',
 'Checking…':'Comprobando…','Last release check':'Última comprobación de versión','Copy failed; select the command':'No se pudo copiar; selecciona el comando'
};
function botText(value){return uiLanguage==='es'?(botVersionWords[value]||value):value;}
function renderBotVersion(){
 const button=$('#mode');if(!button)return;
 button.type='button';button.className='badge bot-version '+(botVersionState?.status==='available'?'amber':'gray');
 const v=botVersionState;button.textContent='PhantomBot '+(v?.installed||'?')+' / '+(v?.status==='unknown'?'?':v?.available||'?');
 button.title=botText(v?.status==='current'?'Up to date':v?.status==='available'?'PhantomBot update':'Version not verified');
 button.setAttribute('aria-label',button.textContent+' · '+button.title);
 if($('#bot-version-dialog')?.open)renderBotDialog();
}
async function readBotVersion(force=false){if(botVersionBusy||!state)return;botVersionBusy=true;try{botVersionState=await api(force?'/api/phantombot/check':'/api/phantombot/status',force?{}:undefined);}catch{botVersionState=null;}finally{botVersionBusy=false;renderBotVersion();}}
function renderBotDialog(){const v=botVersionState;$('#bot-version-dialog .close').setAttribute('aria-label',botText('Close'));$('#bot-version-body').innerHTML=`<h2>${esc(botText('PhantomBot update'))}</h2><div class="detail-grid"><div><span>${esc(botText('Installed binary'))}</span>${esc(v?.installed||'?')}</div><div><span>${esc(botText('Available stable release'))}</span>${esc(v?.status==='unknown'?'?':v?.available||'?')}</div></div><p>${esc(botText(v?.status==='current'?'Up to date':!v||v.status==='unknown'?'Version not verified':'PhantomBot update'))}</p><p class="hint">${esc(botText('Last release check'))}: ${esc(v?.checked_at?time(v.checked_at):'?')}</p>${v?.scope==='shared'?`<div class="notice">${esc(botText('This binary is shared by multiple personas/setups on this host. Review the release and plan their service restarts.'))}</div>`:''}<p>${esc(botText('Run this command as the installation administrator. The official updater asks for confirmation.'))}</p><pre class="kb-content bot-command">${esc(v?.command||'')}</pre><div class="assistant-actions"><button class="button" id="bot-copy" ${!v?.command?'disabled':''}>${esc(botText('Copy update command'))}</button><button class="button" id="bot-check">${esc(botText('Check versions'))}</button><a class="button" href="${esc(v?.release_url||'https://github.com/phantomyard/phantombot/releases')}" target="_blank" rel="noreferrer">${esc(botText('Release notes'))} ↗</a>${v?.terminal_url?`<a class="button" href="${esc(v.terminal_url)}" target="_blank" rel="noreferrer">${esc(botText('Open VPS terminal'))} ↗</a>`:''}</div><p class="hint">${esc(botText('No installation runs from this dashboard. The version refreshes automatically after a terminal or scheduled update.'))}</p><p class="hint">${esc(botText('The badge observes the installed binary, not the version loaded by each running service. The isolated analysis runtime is versioned separately.'))}</p><p id="bot-copy-status" role="status"></p>`;}
const botDialog=document.createElement('dialog');botDialog.id='bot-version-dialog';botDialog.innerHTML='<button class="close" aria-label="Close">×</button><div id="bot-version-body"></div>';document.body.append(botDialog);
$('#mode').addEventListener('click',()=>{renderBotDialog();botDialog.showModal();readBotVersion();});
document.addEventListener('click',async event=>{if(event.target.id==='bot-check'){event.target.disabled=true;event.target.textContent=botText('Checking…');await readBotVersion(true);}if(event.target.id==='bot-copy'){try{await navigator.clipboard.writeText(botVersionState.command);$('#bot-copy-status').textContent=botText('Copied');}catch{$('#bot-copy-status').textContent=botText('Copy failed; select the command');}}});
const beforeBotRender=render;render=function(){beforeBotRender();renderBotVersion();if(!botVersionState&&!botVersionBusy)readBotVersion();};
const beforeBotAccess=accessScreen;accessScreen=function(...args){resetGlobalSearch();botVersionState=null;botDialog.close();beforeBotAccess(...args);};
setInterval(()=>readBotVersion(),30000);
