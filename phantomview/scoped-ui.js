/* The server authorizes every resource. This client never infers ACL grants. */
'use strict';
const SCOPED_KINDS = {organization:'Organization',department:'Departments',role:'Roles',persona:'Personas',human:'Humans',
  project:'Projects',partner:'Partners',objective:'Objectives',task:'Tasks',document:'Documents',knowledge:'Knowledge',
  procedure:'Procedures',finding:'Findings',component:'Components',relationship:'Relationships'};
const scopedHex = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
function scopedRecord(row) {
  if (!row || !scopedHex(row.id) || !Object.hasOwn(SCOPED_KINDS,row.kind)
      || !row.data || typeof row.data !== 'object' || Array.isArray(row.data)) throw Error('Invalid scoped record');
  return row;
}
class ScopedModel {
  constructor(view) {
    if (!view || view.schema_version !== 1 || view.complete_corpus !== false
        || typeof view.organization !== 'string' || !view.organization || typeof view.scope_id !== 'string'
        || !scopedHex(view.policy_revision) || !scopedHex(view.view_revision)
        || !Array.isArray(view.resources) || !Array.isArray(view.relations)
        || view.resources.length + view.relations.length > 2000) throw Error('Current scoped data required');
    this.view = structuredClone(view);
    this.resources = this.view.resources.map(scopedRecord); this.relations = this.view.relations.map(scopedRecord);
    this.byId = new Map();
    for (const row of [...this.resources,...this.relations]) {
      if (this.byId.has(row.id)) throw Error('Ambiguous scoped record');
      this.byId.set(row.id,row);
    }
    if (this.resources.some(row => row.kind === 'relationship') || this.relations.some(row => row.kind !== 'relationship'
        || !this.resources.some(node => node.id === row.data.source) || !this.resources.some(node => node.id === row.data.target))) {
      throw Error('Relationship endpoints must belong to this visible projection');
    }
    this.navigation = this.view.navigation ? this.validateNavigation(this.view.navigation) : null;
  }
  validateNavigation(nav) {
    if(nav.schema_version!==1||nav.api_version!==1||nav.organization!==this.view.organization
        ||nav.scope_id!==this.view.scope_id||nav.policy_revision!==this.view.policy_revision
        ||nav.view_revision!==this.view.view_revision||!Array.isArray(nav.core)||!Array.isArray(nav.modules)
        ||nav.modules.length>24)throw Error('Current navigation required');
    const route=value=>{
      if(!value||typeof value.eligible!=='boolean'||!['session-issuer','runtime-default','module'].includes(value.source)
          ||(value.eligible?(typeof value.persona!=='string'||!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/.test(value.persona)):value.persona!==null))
        throw Error('Invalid assistant route');
    };
    route(nav.assistant);
    const ids=new Set(),counts=this.counts(),label=value=>typeof value==='string'&&value.trim()&&value.length<=80&&!/[<>\x00-\x1f]/.test(value);
    const sections=(rows,prefix)=>{
      if(!Array.isArray(rows)||rows.length>14)throw Error('Invalid navigation sections');
      for(const row of rows){if(!row||typeof row.id!=='string'||!row.id.startsWith(prefix+':')
          ||!/^[a-z][a-z0-9-]{0,47}$/.test(row.id.slice(prefix.length+1))||ids.has(row.id)
          ||!label(row.label)||!Object.hasOwn(SCOPED_KINDS,row.kind)||row.kind==='relationship'
          ||!['table','cards','graph','document'].includes(row.view)||!counts[row.kind]||row.count!==counts[row.kind])
        throw Error('Invalid visible section');ids.add(row.id);}
    };
    sections(nav.core,'core');const modules=new Set();
    for(const item of nav.modules){if(!item||typeof item.id!=='string'||!/^[a-z][a-z0-9-]{0,47}$/.test(item.id)
        ||item.id==='core'||modules.has(item.id)||!label(item.label))throw Error('Invalid module');
      modules.add(item.id);sections(item.sections,item.id);route(item.assistant);}
    return nav;
  }
  sections() {
    if(this.navigation)return [...this.navigation.core,...this.navigation.modules.flatMap(item=>item.sections.map(row=>({...row,module:item.label,assistant:item.assistant})))];
    return [...new Set(this.resources.map(row => row.kind))].sort().map(kind => ({id:kind,kind,label:SCOPED_KINDS[kind],view:'cards'}));
  }
  selection(id) { return this.sections().find(row=>row.id===id); }
  assistant(id) { return this.selection(id)?.assistant||this.navigation?.assistant||null; }
  acceptsAssistant(info,id) {
    const route=this.assistant(id);
    return info?.available===true&&info.scope_id===this.view.scope_id
      &&(!route||(route.eligible&&route.persona===info.persona));
  }
  counts() {
    const counts = {};
    for (const row of this.resources) counts[row.kind] = (counts[row.kind] || 0) + 1;
    return counts;
  }
  static search(result) {
    if (!result || result.complete_corpus !== false || typeof result.partial !== 'boolean'
        || !Array.isArray(result.results) || result.results.length > 100) throw Error('Invalid scoped search');
    const model=new ScopedModel({schema_version:1,complete_corpus:false,organization:result.organization,
      scope_id:result.scope_id,policy_revision:result.policy_revision,view_revision:result.view_revision,resources:[],relations:[]});
    model.resources=structuredClone(result.results).map(scopedRecord);
    if(new Set(model.resources.map(row=>row.id)).size!==model.resources.length)throw Error('Ambiguous search result');
    model.byId=new Map(model.resources.map(row=>[row.id,row]));return model;
  }
  title(row) { return String(row.data.title || row.data.display_name || row.data.name || row.data.label || row.data.id || SCOPED_KINDS[row.kind]); }
  static isReviewedNote(row) {return row.kind==='knowledge'&&row.data.source==='reviewed-knowledge';}
  static detailPath(row) {
    scopedRecord(row);
    return (ScopedModel.isReviewedNote(row)?'/api/reviewed-knowledge/':'/api/resource/')+row.id;
  }
  static detailText(row,current) {
    if(ScopedModel.isReviewedNote(row)) {
      if(!current||current.id!==row.id||current.actor!==row.data.actor||current.title!==row.data.title
          ||current.payload_sha256!==row.data.payload_sha256||!scopedHex(current.payload_sha256)
          ||current.trust!=='untrusted'||current.format!=='markdown'||current.excerpt_only!==false
          ||typeof current.content!=='string'||current.content.length>262144)throw Error('Current reviewed note required');
      return current.content;
    }
    scopedRecord(current);
    if(current.id!==row.id||current.kind!==row.kind)throw Error('Record identity changed');
    return JSON.stringify(current.data,null,2);
  }
  organization() {
    const row = this.resources.find(row => row.kind === 'organization');
    return row ? this.title(row) : this.view.organization;
  }
  impact(id, limit=60, kind=null) {
    const allowed = new Set(this.resources.filter(row=>!kind||row.kind===kind).slice(0,limit).map(row => row.id));
    const nodes = new Set(allowed.has(id) ? [id] : []), edges = new Set(), pending = [...nodes];
    for (let index=0;index<pending.length;index++) for (const edge of this.relations) {
      if (edge.data.source === pending[index] && allowed.has(edge.data.target)) {
        edges.add(edge.id);
        if (!nodes.has(edge.data.target)) {nodes.add(edge.data.target);pending.push(edge.data.target);}
      }
    }
    return {nodes,edges};
  }
}

async function startScopedWorkspace() {
  const $ = id => document.getElementById(id);
  const text = (tag,value,className) => {const node=document.createElement(tag);node.textContent=value;if(className)node.className=className;return node;};
  let model=null, section='', epoch=0, controller=null, detailEpoch=0, redemption=null, closing=false, reviewContext=null, proposalId=null, reviewEpoch=0, detailFocus=null;
  const chat=new ScopedChat({
    request:async(method,path,body)=>{
      const response=await fetch(path,{method,credentials:'same-origin',cache:'no-store',keepalive:method!=='GET',
        headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
      if(!response.ok){const error=Error('Consultation unavailable');error.status=response.status;throw error;}return response.json();
    },
    onInvalid:()=>failure(Error('Current scoped session required'),epoch),
    render:state=>{
      const labels={unavailable:'Not configured for this session.',ready:'How can I help with your workspace?',submitting:'Submitting your consultation…',
        queued:'Queued for your persona…',running:'Your persona is reviewing the evidence…',complete:'Answer based on selected authorized evidence.',
        held:'Screening held this request. No answer was released.',failed:'The consultation could not finish.',cancelled:'Cleared. Cancellation requested.',
        limited:'Consultation limit reached. Retry later.',error:'Connection interrupted. Retry the same request or cancel.'};
      if(state.mode==='persona-conversation'){
        labels.ready='Ask your existing persona. Its native knowledge and tools apply.';
        labels.running='Your persona is answering through PhantomBot…';
        labels.complete='Reply from your existing persona; selected viewer context is supplemental.';
      }
      const note=document.querySelector('.session-note');
      if(note)note.textContent=state.mode==='persona-conversation'?'Read-only viewer · Native persona permissions apply':'Private · Read-only session';
      $('assistant-status').textContent=labels[state.status]||labels.unavailable;
      $('assistant-persona').textContent=state.persona;$('assistant-answer').textContent=state.text;$('assistant-answer').hidden=!state.text;
      $('assistant-question').textContent=state.question;$('assistant-question').hidden=!state.question;
      $('assistant-focus-title').textContent=state.focus;$('assistant-focus').hidden=!state.focus;
      $('assistant-input').disabled=!state.available||state.busy||state.retry;$('assistant-send').disabled=!state.available||state.busy||state.retry;
      $('assistant-cancel').hidden=!state.busy&&!state.retry&&!state.text;$('assistant-retry').hidden=!state.retry;
      $('assistant-cancel').textContent=state.busy||state.retry?'Cancel':'Clear';
      document.querySelector('.assistant-panel').setAttribute('data-state',state.status);
      if(['ready','unavailable','cancelled','submitting'].includes(state.status))$('assistant-input').value='';
    }
  });
  function clearReview(hide=true) {
    reviewEpoch++;reviewContext=null;proposalId=null;if(hide)$('review-open').hidden=true;
    for(const id of ['review-resource','review-category','review-content','review-current','review-status'])$(id).replaceChildren();
    $('review-confirm').checked=false;if($('review-dialog').open)$('review-dialog').close();
  }
  function clear() {
    chat.reset();detailFocus=null;$('assistant-about').hidden=true;
    model=null;section='';detailEpoch++;$('navigation').replaceChildren();$('records').replaceChildren();$('stats').replaceChildren();
    $('graph').replaceChildren();$('graph-panel').hidden=true;$('organization').textContent='';$('scope-label').textContent='Session required';
    $('graph-caption').textContent='';$('records-title').textContent='Records';
    $('detail-content').textContent='';$('detail-title').textContent='Record';if($('detail').open)$('detail').close();
    $('page-title').textContent='Your information, connected.';
    clearReview();
  }
  function operation() {epoch++;if(controller)controller.abort();controller=new AbortController();clear();$('message').hidden=true;return epoch;}
  function failure(error,ticket) {
    if(ticket!==epoch || error.name==='AbortError')return;
    epoch++;if(controller)controller.abort();
    clear();$('status').textContent='Workspace unavailable';$('message').hidden=false;
    $('message').textContent='A current identified session and available scoped data are required. Refresh or request a new temporary link from your persona.';
  }
  async function api(path,body,signal) {
    const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal,
      headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    if(!response.ok){const error=Error('Scoped request unavailable');error.status=response.status;throw error;}return response.json();
  }
  function showDetails(row) {
    const ticket=epoch, detailTicket=++detailEpoch;
    // Remove old contents before any new read; never show a cached fallback.
    detailFocus=null;$('assistant-about').hidden=true;
    $('detail-content').textContent='Loading current record…';$('detail-title').textContent='Record';$('detail').showModal();
    api(ScopedModel.detailPath(row),undefined,controller?.signal).then(current=>{
      if(ticket!==epoch||detailTicket!==detailEpoch||!$('detail').open)return;
      $('detail-content').textContent=ScopedModel.detailText(row,current);
      const title=ScopedModel.isReviewedNote(row)?current.title:model.title(current);
      $('detail-title').textContent=title;
      detailFocus={id:current.id,title};$('assistant-about').hidden=!chat.view;
    }).catch(error=>failure(error,ticket));
  }
  function renderGraph() {
    const graph=$('graph');graph.replaceChildren();
    const selected=model.selection(section);
    const nodes=model.resources.filter(row=>!selected||row.kind===selected.kind).slice(0,60), ids=new Set(nodes.map(row=>row.id));
    const edges=model.relations.filter(row=>ids.has(row.data.source)&&ids.has(row.data.target));
    $('graph-panel').hidden=!nodes.length;
    $('graph-caption').textContent=`${nodes.length} visible records · ${edges.length} connections`+(model.resources.length>60?' · graph limited to 60 records':'');
    if(!nodes.length)return;
    const ns='http://www.w3.org/2000/svg';
    const svg=(tag,attrs)=>{const node=document.createElementNS(ns,tag);for(const[key,value]of Object.entries(attrs))node.setAttribute(key,String(value));return node;};
    const height=Math.ceil(nodes.length/3)*100+40, root=svg('svg',{viewBox:`0 0 900 ${height}`,role:'group','aria-label':'Visible directed relationships'});
    const defs=svg('defs',{}), marker=svg('marker',{id:'flow-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});
    marker.append(svg('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'context-stroke'}));defs.append(marker);root.append(defs);
    const positions=new Map(nodes.map((row,index)=>[row.id,{x:45+(index%3)*300,y:30+Math.floor(index/3)*100}]));
    const paths=new Map(), groups=new Map();
    for(const edge of edges){const a=positions.get(edge.data.source),b=positions.get(edge.data.target);
      const path=svg('path',{d:`M ${a.x+105} ${a.y+50} Q ${(a.x+b.x)/2+105} ${(a.y+b.y)/2+75} ${b.x+105} ${b.y+50}`,class:'edge','marker-end':'url(#flow-arrow)'});
      const title=svg('title',{});title.textContent=String(edge.data.label||edge.data.type||'Connection');path.append(title);root.append(path);paths.set(edge.id,path);
    }
    const highlight=id=>{const impact=id?model.impact(id,60,selected?.kind):null;for(const[key,node]of groups){node.classList.toggle('lit',!!impact?.nodes.has(key));node.classList.toggle('dim',!!impact&&!impact.nodes.has(key));}
      for(const[key,path]of paths){path.classList.toggle('lit',!!impact?.edges.has(key));path.classList.toggle('dim',!!impact&&!impact.edges.has(key));}};
    for(const row of nodes){const p=positions.get(row.id),g=svg('g',{class:'node',transform:`translate(${p.x},${p.y})`,tabindex:0,role:'button','aria-label':'Open '+model.title(row)});
      g.append(svg('rect',{width:210,height:50,rx:9}));const title=svg('text',{x:12,y:22});title.textContent=model.title(row).slice(0,26);g.append(title);
      const kind=svg('text',{x:12,y:39,class:'node-kind'});kind.textContent=SCOPED_KINDS[row.kind];g.append(kind);
      g.addEventListener('mouseenter',()=>highlight(row.id));g.addEventListener('mouseleave',()=>highlight(null));g.addEventListener('focus',()=>highlight(row.id));g.addEventListener('blur',()=>highlight(null));
      g.addEventListener('click',()=>showDetails(row));g.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();showDetails(row);}});
      groups.set(row.id,g);root.append(g);
    }
    graph.append(root);
  }
  function render(search=false) {
    const selected=model.selection(section);
    $('organization').textContent=model.organization();$('scope-label').textContent=model.view.scope_id;
    $('page-title').textContent=search?'Search your workspace':selected?selected.label:'Your information, connected.';
    const nav=$('navigation');nav.replaceChildren();
    let group='';
    for(const item of [{id:'',label:search?'All results':'Overview'},...model.sections()]) {
      if(item.module&&item.module!==group){group=item.module;nav.append(text('span',group,'module-label'));}
      const button=text('button',item.label);button.type='button';button.className=section===item.id?'active':'';
      button.setAttribute('aria-current',section===item.id?'page':'false');button.addEventListener('click',()=>{
        section=item.id;chat.reset();render(search);loadAssistant(epoch);
      });nav.append(button);
    }
    const stats=$('stats');stats.replaceChildren();
    for(const[kind,count]of Object.entries(model.counts())){const tile=text('div','', 'stat');tile.append(text('span',SCOPED_KINDS[kind]),text('strong',count));stats.append(tile);}
    const records=$('records');records.replaceChildren();
    records.className=selected?.view==='table'?'record-table':'cards';
    for(const row of model.resources.filter(row=>!selected||row.kind===selected.kind)) {
      const card=text('button','', 'card');card.type='button';card.append(text('small',SCOPED_KINDS[row.kind]),text('h3',model.title(row)));
      const summary=row.data.description||row.data.severity||row.data.kind;
      if(typeof summary==='string')card.append(text('p',summary.slice(0,180)));card.addEventListener('click',()=>showDetails(row));records.append(card);
      if(selected?.view==='document')card.append(text('pre',JSON.stringify(row.data,null,2),'record-preview'));
    }
    if(!records.childElementCount)records.append(text('p','No records are available in this view.','muted'));
    if(search){$('graph-panel').hidden=true;$('graph').replaceChildren();}else renderGraph();
    $('status').textContent=search?'Results cover all information available to this session.':'Showing only information available to this session.';
    $('records-title').textContent=search?'Search results':selected?selected.label:'Available records';
  }
  async function load() {
    if(closing)return;
    const ticket=operation();$('status').textContent='Refreshing your workspace…';$('query').value='';
    try {const view=await api('/api/state',undefined,controller.signal);if(ticket!==epoch)return;model=new ScopedModel(view);render();await loadAssistant(ticket);
      try{const review=await api('/api/review',undefined,controller.signal);if(ticket===epoch&&review.resources?.length)$('review-open').hidden=false;}
      catch(error){if(error.status===401)failure(error,ticket);/* Read access does not imply review authority. */}}
    catch(error){failure(error,ticket);}
  }
  async function loadAssistant(ticket) {
    const selectedSection=section,route=model?.assistant(section);
    if(route){$('assistant-persona').textContent=route.persona||'';
      $('assistant-status').textContent=route.eligible?'Selected persona is not connected for this view.':'No authorized assistant is available for this view.';}
    if(route&&!route.eligible)return;
    try{const info=await api('/api/scoped-assistant/info',undefined,controller.signal);
      if(ticket===epoch&&model&&section===selectedSection&&model.acceptsAssistant(info,section))chat.enable(info,model.view);}
    catch(error){if(error.status===401)failure(error,ticket);}
  }
  $('assistant-form').addEventListener('submit',event=>{event.preventDefault();chat.send($('assistant-input').value);});
  $('assistant-cancel').addEventListener('click',()=>chat.cancel());
  $('assistant-retry').addEventListener('click',()=>chat.send(chat.retryBody?.question||'',true));
  $('assistant-unfocus').addEventListener('click',()=>chat.setFocus(null));
  $('assistant-about').addEventListener('click',()=>{if(detailFocus&&chat.view){chat.setFocus(detailFocus);$('detail').close();$('assistant-input').focus();}});
  $('refresh').addEventListener('click',load);
  $('logout').addEventListener('click',async()=>{if(closing)return;closing=true;const ticket=operation();$('query').value='';$('status').textContent='Closing your session…';
    // Revocation must finish even if visibility changes or other reads are aborted.
    try{if(redemption)await redemption.catch(()=>{});
      await api('/api/logout',{});if(ticket===epoch)$('status').textContent='Logged out. Request a new temporary link to continue.';}
    catch(error){failure(error,ticket);}finally{closing=false;}});
  $('close-detail').addEventListener('click',()=>{$('detail').close();$('detail-content').textContent='';detailEpoch++;});
  $('detail').addEventListener('close',()=>{$('detail-content').textContent='';detailEpoch++;detailFocus=null;$('assistant-about').hidden=true;});
  function reviewSelection() {
    reviewEpoch++;proposalId=null;$('review-confirm').checked=false;$('review-submit').disabled=false;$('review-status').textContent='';
    const row=reviewContext?.resources.find(value=>value.id===$('review-resource').value);
    $('review-category').replaceChildren(new Option('Choose a category',''));
    if(!row)return;
    for(const category of row.allowed_categories)$('review-category').append(new Option(category,category));
    $('review-current').textContent=`Current: ${row.category} · ${row.scope.id}`;
    $('review-content').textContent=JSON.stringify(row.data,null,2);
  }
  $('review-open').addEventListener('click',async()=>{
    const ticket=epoch,reviewTicket=++reviewEpoch;
    try{const review=await api('/api/review',undefined,controller.signal);if(ticket!==epoch||reviewTicket!==reviewEpoch)return;
      if(!Array.isArray(review.resources)||!review.resources.length)throw Error('Review unavailable');
      reviewContext=review;$('review-resource').replaceChildren();
      for(const row of review.resources)$('review-resource').append(new Option(model.title(row),row.id));
      reviewSelection();$('review-dialog').showModal();
    }catch(error){if(reviewTicket===reviewEpoch)failure(error,ticket);}
  });
  $('review-resource').addEventListener('change',reviewSelection);
  $('review-category').addEventListener('change',()=>{reviewEpoch++;proposalId=null;$('review-confirm').checked=false;$('review-submit').disabled=false;});
  $('review-close').addEventListener('click',()=>clearReview(false));
  $('review-dialog').addEventListener('close',()=>{if(!$('review-dialog').open)clearReview(false);});
  $('review-submit').addEventListener('click',async()=>{
    const ticket=epoch,reviewTicket=reviewEpoch,row=reviewContext?.resources.find(value=>value.id===$('review-resource').value),category=$('review-category').value;
    if(!row||!$('review-confirm').checked||!row.allowed_categories.includes(category)){$('review-status').textContent='Choose an authorized category and confirm your review.';return;}
    $('review-submit').disabled=true;proposalId ||= crypto.randomUUID();
    const body={request_id:proposalId,base_revision:reviewContext.base_revision,view_revision:reviewContext.view_revision,
      changes:[{id:row.id,payload_sha256:row.payload_sha256,category}]};
    try{const result=await api('/api/review',body,controller.signal);if(ticket!==epoch||reviewTicket!==reviewEpoch)return;
      if(result.status!=='pending'||result.published!==false)throw Error('Unexpected proposal response');
      $('review-status').textContent='Proposal recorded. Publication awaits separate approval.';
    }catch(error){if(reviewTicket===reviewEpoch)failure(error,ticket);}
  });
  $('search-form').addEventListener('submit',async event=>{event.preventDefault();if(closing)return;const query=$('query').value.trim();if(!query){await load();return;}
    const ticket=operation();$('status').textContent='Searching all authorized information…';
    try{const result=await api('/api/search',{query},controller.signal);if(ticket!==epoch)return;
      model=ScopedModel.search(result);render(true);await loadAssistant(ticket);
      if(result.partial)$('status').textContent='Showing the first 100 authorized matches. Refine your search for more.';
    }catch(error){failure(error,ticket);}
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden){operation();$('status').textContent='Workspace hidden. Refresh when you return.';}});
  window.addEventListener('pagehide',()=>operation());window.addEventListener('pageshow',event=>{if(event.persisted)load();});
  const fragment=new URLSearchParams(location.hash.slice(1)),code=fragment.get('c');
  if(location.hash)history.replaceState(null,'',location.pathname);
  if(code){const ticket=operation();try{redemption=api('/api/redeem',{code});await redemption;if(ticket!==epoch)return;}
    catch(error){failure(error,ticket);return;}}
  await load();
}
if(typeof module!=='undefined'&&module.exports)module.exports={ScopedModel};else startScopedWorkspace();
