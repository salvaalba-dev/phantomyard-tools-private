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
    if(row.kind==='document')return typeof current.data.content==='string'&&['markdown','text/plain'].includes(current.data.format)
      ?current.data.content:'Document information is available, but its text has not been published for this session.';
    return JSON.stringify(current.data,null,2);
  }
  organization() {
    const row = this.resources.find(row => row.kind === 'organization');
    return row ? this.title(row) : this.view.organization;
  }
  personaRows() {
    const unique=rows=>[...new Map(rows.map(row=>[row.id,row])).values()];
    const linked=(persona,type,kind)=>unique(this.relations.filter(edge=>edge.data.type===type&&edge.data.target===persona.id)
      .map(edge=>this.byId.get(edge.data.source)).filter(row=>row?.kind===kind));
    const personas=this.resources.filter(row=>row.kind==='persona').sort((a,b)=>this.title(a).localeCompare(this.title(b)));
    const rows=personas.map(persona=>({persona,humans:linked(persona,'counterpart','human'),roles:linked(persona,'assignment','role')}));
    const shown=new Set(rows.flatMap(row=>[...row.humans,...row.roles].map(record=>record.id)));
    // Preserve visible, unassigned records without inventing an association.
    for(const record of this.resources.filter(row=>['human','role'].includes(row.kind)&&!shown.has(row.id))
      .sort((a,b)=>this.title(a).localeCompare(this.title(b)))) {
      rows.push({persona:null,humans:record.kind==='human'?[record]:[],roles:record.kind==='role'?[record]:[]});
    }
    return rows;
  }
  static contactLink(kind, value) {
    if(typeof value!=='string'||value.length>600||/[\s\x00-\x1f\x7f]/.test(value))return null;
    if(kind==='email')return /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(value)?'mailto:'+encodeURIComponent(value).replace('%40','@'):null;
    if(kind==='npub')return /^npub1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}$/.test(value)?'nostr:'+value:null;
    if(kind==='telegram')return /^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$/.test(value)?'https://t.me/'+value.replace(/^@/,''):null;
    if(kind==='website'){
      try{const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password?url.href:null;}catch{return null;}
    }
    return null;
  }
  profile(row) {
    scopedRecord(row);
    const current=this.byId.get(row.id);
    if(!current||JSON.stringify(current)!==JSON.stringify(row))throw Error('Current visible profile required');
    const data=row.data,scalar=value=>typeof value==='string'&&value.trim()?value.slice(0,4000):null;
    const list=value=>Array.isArray(value)?value.filter(item=>typeof item==='string'&&item.trim()).slice(0,128):[];
    const related=new Map(),documents=new Map(),roles=new Map(),people=new Map(),departments=new Map();
    const add=(target,label)=>{if(!target||target.id===row.id)return;related.set(target.id,{record:target,label});
      if(['document','knowledge','procedure'].includes(target.kind))documents.set(target.id,target);
      if(target.kind==='role')roles.set(target.id,target);
      if(['persona','human'].includes(target.kind))people.set(target.id,target);
      if(target.kind==='department')departments.set(target.id,target);};
    const labels={assignment:'Role / persona',counterpart:'Human counterpart',membership:'Department',reports:'Reporting',
      context:'Organization',department:'Department hierarchy',escalation:'Workflow',document:'Document',documentation:'Document',
      profile:'Profile document',knowledge:'Knowledge',reference:'Reference'};
    const neighbors=id=>this.relations.filter(edge=>edge.data.source===id||edge.data.target===id);
    for(const edge of neighbors(row.id))add(this.byId.get(edge.data.source===row.id?edge.data.target:edge.data.source),labels[edge.data.type]||'Related record');
    if(row.kind==='persona')for(const role of [...roles.values()])for(const edge of neighbors(role.id)){
      if(['membership','reports'].includes(edge.data.type))add(this.byId.get(edge.data.source===role.id?edge.data.target:edge.data.source),labels[edge.data.type]);
    }
    if(row.kind==='human')for(const persona of [...people.values()].filter(item=>item.kind==='persona'))for(const edge of neighbors(persona.id)){
      if(edge.data.type==='assignment')add(this.byId.get(edge.data.source), 'Counterpart role');
    }
    if(row.kind==='organization'){
      for(const target of this.resources.filter(item=>item.kind==='department'))departments.set(target.id,target);
      const roots=this.resources.filter(item=>item.kind==='role'&&!this.relations.some(edge=>edge.data.type==='reports'&&edge.data.source===item.id));
      for(const role of roots){add(role,'Organization lead');for(const edge of neighbors(role.id))if(edge.data.type==='assignment'){
        const persona=this.byId.get(edge.data.target);add(persona,'Organization lead');
        if(persona)for(const binding of neighbors(persona.id))if(binding.data.type==='counterpart')add(this.byId.get(binding.data.source),'Human counterpart');
      }}
    }
    // Reviewed note ownership is an exact collector identity, never a title/path guess.
    if(row.kind==='persona'&&scalar(data.id))for(const note of this.resources.filter(item=>item.kind==='knowledge'&&ScopedModel.isReviewedNote(item))){
      if(note.data.actor===data.id||note.data.actor===this.view.organization+':actors:'+data.id)add(note,'Reviewed knowledge');
    }
    const contacts=data.contacts&&typeof data.contacts==='object'?data.contacts:data.channels&&typeof data.channels==='object'?data.channels:{};
    const contactRows=[['Website','website',contacts.website||data.website],['Email','email',contacts.email||data.email],
      ['Nostr / npub','npub',contacts.npub||data.npub],['Telegram','telegram',contacts.telegram||contacts.telegram_bot||data.telegram_bot]]
      .map(([label,kind,value])=>({label,value:scalar(value),href:ScopedModel.contactLink(kind,value)}));
    const fields=[];for(const [key,label]of [['sector','Sector'],['legal_name','Legal name'],['country','Country'],['scope','Scope'],
      ['languages','Languages'],['default_language','Default language'],['installation_label','Installation'],['runtime','Runtime']]){
      const value=scalar(data[key])||list(data[key]).join(', ');if(value)fields.push({label,value});
    }
    const legal=data.legal&&typeof data.legal==='object'?data.legal:{};
    for(const [key,label]of [['legal_name','Legal name'],['legal_form','Legal form'],['nif','Organization tax ID'],['constitution_date','Founded']]){
      const value=scalar(legal[key]);if(value)fields.push({label,value});
    }
    const assignedRoles=row.kind==='persona'?this.relations.filter(edge=>edge.data.type==='assignment'&&edge.data.target===row.id)
      .map(edge=>this.byId.get(edge.data.source)).filter(role=>role?.kind==='role'):[];
    const functions=[...new Set([...list(data.functions),...assignedRoles.flatMap(role=>list(role.data.functions))])];
    const description=scalar(data.description)||assignedRoles.map(role=>scalar(role.data.description)).find(Boolean)||'';
    return {record:row,title:this.title(row),kind:SCOPED_KINDS[row.kind],description,contacts:contactRows,fields,functions,
      tools:list(data.tools),excluded:list(data.excluded),roles:[...roles.values()],people:[...people.values()],
      departments:[...departments.values()],relations:[...related.values()].filter(item=>!documents.has(item.record.id)),
      documents:[...documents.values()]};
  }
  organizationTree() {
    const organization=this.resources.find(row=>row.kind==='organization');
    if(!organization||!this.resources.some(row=>row.kind==='role'||row.kind==='persona'))return null;
    const roles=this.resources.filter(row=>row.kind==='role').slice(0,59),roleIds=new Set(roles.map(row=>row.id));
    const visible=(id,kind)=>{const row=this.byId.get(id);return row?.kind===kind?row:null;};
    const assignments=new Map(roles.map(row=>[row.id,[]])),memberships=new Map(roles.map(row=>[row.id,[]])),counterparts=new Map();
    for(const edge of this.relations){const {source,target,type}=edge.data;
      if(type==='assignment'&&roleIds.has(source)&&visible(target,'persona'))assignments.get(source).push(visible(target,'persona'));
      if(type==='membership'&&roleIds.has(source)&&visible(target,'department'))memberships.get(source).push(visible(target,'department'));
      if(type==='counterpart'&&visible(source,'human')&&visible(target,'persona')){
        if(!counterparts.has(target))counterparts.set(target,[]);counterparts.get(target).push(visible(source,'human'));
      }
    }
    const unique=rows=>[...new Map(rows.map(row=>[row.id,row])).values()];
    const card=(record,personas=[])=>({id:record.id,record,personas:unique(personas),
      humans:unique(personas.flatMap(row=>counterparts.get(row.id)||[])),departments:unique(memberships.get(record.id)||[]),issue:''});
    const nodes=[card(organization),...roles.map(row=>card(row,assignments.get(row.id)))],byId=new Map(nodes.map(row=>[row.id,row]));
    const parents=new Map(),reporting=[];
    for(const edge of this.relations.filter(row=>row.data.type==='reports'&&roleIds.has(row.data.source))){
      if(!roleIds.has(edge.data.target)){byId.get(edge.data.source).issue='Manager outside this diagram';continue;}
      reporting.push(edge);if(!parents.has(edge.data.source))parents.set(edge.data.source,new Set());parents.get(edge.data.source).add(edge.data.target);
    }
    const parent=new Map();
    for(const row of roles){const choices=parents.get(row.id)||new Set();
      if(choices.size>1)byId.get(row.id).issue='Multiple reporting parents';
      parent.set(row.id,choices.size===1?[...choices][0]:null);
    }
    const cycles=new Set();
    for(const row of roles){const path=[],seen=new Map();let id=row.id;
      while(id){if(seen.has(id)){for(const key of path.slice(seen.get(id)))cycles.add(key);break;}
        seen.set(id,path.length);path.push(id);id=parent.get(id);}
    }
    for(const id of cycles){parent.set(id,null);byId.get(id).issue='Circular reporting: review required';}
    const children=new Map(nodes.map(row=>[row.id,[]]));
    for(const row of roles)children.get(parent.get(row.id)||organization.id).push(row.id);
    const ordered=ids=>ids.sort((a,b)=>this.title(byId.get(a).record).localeCompare(this.title(byId.get(b).record)));
    for(const ids of children.values())ordered(ids);
    const units=id=>Math.max(1,children.get(id).reduce((sum,key)=>sum+units(key),0));
    const forestWidth=Math.max(780,units(organization.id)*270),positions=new Map();let depth=0;
    const place=(id,left,span,level)=>{positions.set(id,{x:left+span/2-120,y:64+level*230});depth=Math.max(depth,level);
      let offset=left;for(const child of children.get(id)){const size=span*units(child)/units(id);place(child,offset,size,level+1);offset+=size;}};
    positions.set(organization.id,{x:16,y:64});
    let offset=280;for(const child of children.get(organization.id)){const span=forestWidth*units(child)/units(organization.id);place(child,offset,span,0);offset+=span;}
    const assigned=new Set(nodes.flatMap(row=>row.personas.map(persona=>persona.id)));
    const unlinked=this.resources.filter(row=>row.kind==='persona'&&!assigned.has(row.id));
    const available=Math.max(0,60-nodes.length),unlinkedShown=unlinked.slice(0,available),unlinkedY=64+(depth+1)*230;
    unlinkedShown.forEach((row,index)=>{const node=card(row,[row]);node.issue='Role assignment not published';nodes.push(node);
      positions.set(row.id,{x:280+Math.floor(index%Math.max(1,Math.floor(forestWidth/270)))*270+15,y:unlinkedY+Math.floor(index/Math.max(1,Math.floor(forestWidth/270)))*230});});
    const edges=roles.map(row=>{const boss=parent.get(row.id);const source=reporting.find(edge=>edge.data.source===row.id&&edge.data.target===boss);
      return {id:source?.id||'context:'+row.id,source:row.id,target:boss||organization.id,type:boss?'reports':'context',label:boss?'Reports to':'Organization context; no visible reporting parent'};});
    for(const edge of this.relations)if(edge.data.type==='escalation'&&roleIds.has(edge.data.source)&&roleIds.has(edge.data.target))edges.push({id:edge.id,...edge.data});
    const workflowCount=edges.filter(edge=>edge.type==='escalation').length,width=forestWidth+280+40+workflowCount*12;
    const bottom=Math.max(...[...positions.values()].map(point=>point.y))+190;
    return {nodes,edges,positions,width,height:bottom+40,unlinked:unlinked.length,
      truncated:this.resources.filter(row=>row.kind==='role').length>roles.length||unlinked.length>unlinkedShown.length,
      incomplete:nodes.some(row=>row.issue)||nodes.some(row=>row.record.kind==='role'&&!row.personas.length)};
  }
  static fitTree(tree, availableWidth) {
    if(!Number.isFinite(availableWidth)||availableWidth<240)throw Error('Diagram width required');
    const width=Math.floor(availableWidth),compact=width<580,gap=compact?14:20,columns=4;
    const cardWidth=(width-32-gap*(columns-1))/columns,cardHeight=compact?82:120,rowGap=compact?82:80;
    const organization=tree.nodes.find(node=>node.record.kind==='organization'),levels=new Map();
    for(const node of tree.nodes.filter(node=>node!==organization)){
      const level=tree.positions.get(node.id).y;if(!levels.has(level))levels.set(level,[]);levels.get(level).push(node);
    }
    const positions=new Map(),sizes=new Map();let y=32;
    positions.set(organization.id,{x:16,y});sizes.set(organization.id,{w:Math.min(168,width*.27),h:compact?82:104});
    for(const [,nodes]of [...levels].sort((a,b)=>a[0]-b[0])){
      nodes.sort((a,b)=>tree.positions.get(a.id).x-tree.positions.get(b.id).x);
      // Wrap peers before adding another reporting level; never scale text or overflow horizontally.
      for(let start=0;start<nodes.length;start+=columns){const row=nodes.slice(start,start+columns);
        if(start===0&&positions.size===1&&row.length>1)y+=cardHeight+rowGap;
        for(const [i,node]of row.entries()){
          const x=row.length===1?(width-cardWidth)/2:16+i*(cardWidth+gap);
          positions.set(node.id,{x,y});sizes.set(node.id,{w:cardWidth,h:cardHeight});
        }
        y+=cardHeight+rowGap;
      }
    }
    return {...tree,positions,sizes,width,height:y-rowGap+24,compact,fit:true,routing:null,junctions:[]};
  }
  static treePath(tree,edge) {
    tree.routing ||= ScopedModel.treeRoutes(tree);
    return tree.routing.get(edge.id).path;
  }
  static treeRoutes(tree) {
    const boxes=new Map(tree.nodes.map(node=>[node.id,{...tree.positions.get(node.id),...(tree.sizes?.get(node.id)||{w:240,h:node.record.kind==='organization'?104:160})}]));
    const routes=new Map(),used=[],ports=new Map(),directions={top:[0,-1],right:[1,0],bottom:[0,1],left:[-1,0]};
    const compact=points=>{
      const result=[];for(const p of points){if(result.length&&result.at(-1).x===p.x&&result.at(-1).y===p.y)continue;
        if(result.length>1){const a=result.at(-2),b=result.at(-1);if(a.x===b.x&&b.x===p.x||a.y===b.y&&b.y===p.y)result.pop();}result.push(p);}return result;
    };
    const segments=points=>points.slice(1).map((p,i)=>({a:points[i],b:p}));
    const overlaps=(a,b,c,d)=>Math.min(Math.max(a,b),Math.max(c,d))-Math.max(Math.min(a,b),Math.min(c,d))>0.1;
    const hits=(segment,box,pad)=>{
      const {a,b}=segment;
      return a.x===b.x?a.x>box.x-pad&&a.x<box.x+box.w+pad&&overlaps(a.y,b.y,box.y-pad,box.y+box.h+pad):
        a.y>box.y-pad&&a.y<box.y+box.h+pad&&overlaps(a.x,b.x,box.x-pad,box.x+box.w+pad);
    };
    const shared=(a,b)=>a.a.x===a.b.x&&b.a.x===b.b.x?a.a.x===b.a.x&&overlaps(a.a.y,a.b.y,b.a.y,b.b.y):
      a.a.y===a.b.y&&b.a.y===b.b.y&&a.a.y===b.a.y&&overlaps(a.a.x,a.b.x,b.a.x,b.b.x);
    const crosses=(a,b)=>{
      if((a.a.x===a.b.x)===(b.a.x===b.b.x))return false;
      const v=a.a.x===a.b.x?a:b,h=a.a.x===a.b.x?b:a;
      return v.a.x>Math.min(h.a.x,h.b.x)&&v.a.x<Math.max(h.a.x,h.b.x)&&h.a.y>Math.min(v.a.y,v.b.y)&&h.a.y<Math.max(v.a.y,v.b.y);
    };
    const port=(id,side,fraction)=>{
      const box=boxes.get(id),count=ports.get(id+':'+side)||0,extent=['top','bottom'].includes(side)?box.w:box.h;
      const shift=count===0?0:(count%2?1:-1)*Math.ceil(count/2)*(tree.fit?8:12);
      const along=fraction===undefined?Math.max(8,Math.min(extent-8,extent/2+shift)):extent*fraction;
      const p=side==='top'?{x:box.x+along,y:box.y}:side==='bottom'?{x:box.x+along,y:box.y+box.h}:
        side==='left'?{x:box.x,y:box.y+along}:{x:box.x+box.w,y:box.y+along};
      return {p,stub:{x:p.x+directions[side][0]*(tree.fit?8:14),y:p.y+directions[side][1]*(tree.fit?8:14)},side};
    };
    const bounds={left:Math.min(...[...boxes.values()].map(b=>b.x))-12,right:Math.max(...[...boxes.values()].map(b=>b.x+b.w))+16,
      top:16,bottom:Math.max(...[...boxes.values()].map(b=>b.y+b.h))+24};
    const ordered=[...tree.edges].sort((a,b)=>(a.type==='reports'?0:a.type==='context'?1:2)-(b.type==='reports'?0:b.type==='context'?1:2));
    tree.junctions=[];
    for(const edge of ordered){
      const report=edge.type==='reports';
      if(tree.fit&&report){
        const a=boxes.get(edge.source),b=boxes.get(edge.target),peers=tree.edges.filter(row=>row.type==='reports'&&row.target===edge.target&&boxes.get(row.source).y===a.y);
        const lane=(a.y+b.y+b.h)/2,ax=a.x+a.w/2,bx=b.x+b.w/2;
        const points=compact([{x:ax,y:a.y},{x:ax,y:lane},{x:bx,y:lane},{x:bx,y:b.y+b.h}]),lines=segments(points);
        // Only actual siblings share a reporting bus. Other flows keep independent paths.
        if(a.y>b.y+b.h&&!lines.some(line=>used.some(previous=>previous.bus!==edge.target&&shared(line,previous)))&&!lines.some(line=>[...boxes].some(([id,box])=>hits(line,box,id===edge.source||id===edge.target?0:4)))){
          const path='M '+points[0].x+' '+points[0].y+points.slice(1).map((p,i)=>p.x===points[i].x?' V '+p.y:' H '+p.x).join('');
          routes.set(edge.id,{path,points,sourceSide:'top',targetSide:'bottom',overlap:0,bus:edge.target});used.push(...lines.map(line=>({...line,bus:edge.target})));
          if(peers.length>1)for(const x of [ax,bx])if(!tree.junctions.some(j=>j.x===x&&j.y===lane))tree.junctions.push({x,y:lane});
          continue;
        }
      }
      const siblings=tree.edges.filter(row=>row.type==='reports'&&row.target===edge.target).sort((l,r)=>boxes.get(l.source).x-boxes.get(r.source).x);
      const fraction=report?(siblings.findIndex(row=>row.id===edge.id)+1)/(siblings.length+1):undefined;
      const candidates=id=>Object.keys(directions).flatMap(side=>(tree.fit?[undefined,.3,.7]:[undefined]).map(fraction=>port(id,side,fraction)));
      const starts=report?[port(edge.source,'top')]:candidates(edge.source);
      const ends=report?[port(edge.target,'bottom',fraction)]:candidates(edge.target);
      let best=null;
      for(const start of starts)for(const end of ends){
        const s=start.stub,t=end.stub,mx=(s.x+t.x)/2,my=(s.y+t.y)/2;
        const middle=[[{x:s.x,y:t.y}],[{x:t.x,y:s.y}]];
        for(const x of [mx,mx-12,mx+12,s.x-24,s.x+24,t.x-24,t.x+24,bounds.left,bounds.right])middle.push([{x,y:s.y},{x,y:t.y}]);
        for(const y of [my,my-12,my+12,s.y-24,s.y+24,t.y-24,t.y+24,bounds.top,bounds.bottom])middle.push([{x:s.x,y},{x:t.x,y}]);
        for(const turns of middle){
          const points=compact([start.p,s,...turns,t,end.p]);
          if(points.some(p=>p.x<2||p.y<2||p.x>tree.width-2||p.y>tree.height-2))continue;
          const lines=segments(points);if(lines.some(line=>[...boxes].some(([id,box])=>hits(line,box,id===edge.source||id===edge.target?0:(tree.fit?4:8)))))continue;
          const length=lines.reduce((sum,line)=>sum+Math.abs(line.a.x-line.b.x)+Math.abs(line.a.y-line.b.y),0);
          const overlap=lines.reduce((sum,line)=>sum+used.filter(previous=>shared(line,previous)).length,0);
          const intersections=lines.reduce((sum,line)=>sum+used.filter(previous=>crosses(line,previous)).length,0);
          const score=length+(points.length-2)*18+overlap*100000+intersections*(tree.fit?160:80);
          if(!best||score<best.score)best={points,lines,score,start,end,overlap};
        }
      }
      // Retain a visible diagnostic if a dense diagram cannot be routed safely.
      if(!best){routes.set(edge.id,{path:'',unrouted:true});continue;}
      const path='M '+best.points[0].x+' '+best.points[0].y+best.points.slice(1).map((p,i)=>p.x===best.points[i].x?' V '+p.y:' H '+p.x).join('');
      used.push(...best.lines);for(const [id,side]of [[edge.source,best.start.side],[edge.target,best.end.side]])ports.set(id+':'+side,(ports.get(id+':'+side)||0)+1);
      routes.set(edge.id,{path,points:best.points,sourceSide:best.start.side,targetSide:best.end.side,overlap:best.overlap});
    }
    return routes;
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
  let treeObserver=null, profileReadEpoch=0;
  let model=null, section='', epoch=0, controller=null, detailEpoch=0, redemption=null, closing=false, reviewContext=null, proposalId=null, reviewEpoch=0, detailFocus=null;
  const chat=new ScopedChat({
    request:async(method,path,body)=>{
      const response=await fetch(path,{method,credentials:'same-origin',cache:'no-store',keepalive:method!=='GET',
        headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
      if(!response.ok){const error=Error('Consultation unavailable');error.status=response.status;throw error;}return response.json();
    },
    onInvalid:()=>failure(Error('Current scoped session required'),epoch),
    render:state=>{
      const labels={unavailable:'Not configured for this session.',ready:'How can I help with your workspace?',submitting:'Submitting your consultation\u2026',
        queued:'Queued for your persona\u2026',running:'Your persona is reviewing the evidence\u2026',complete:'Answer based on selected authorized evidence.',
        held:'Screening held this request. No answer was released.',failed:'The consultation could not finish.',cancelled:'Cleared. Cancellation requested.',
        limited:'Consultation limit reached. Retry later.',error:'Connection interrupted. Retry the same request or cancel.'};
      if(state.mode==='persona-conversation'){
        labels.ready='Ask your existing persona. Its native knowledge and tools apply.';
        labels.running='Your persona is answering through PhantomBot\u2026';
        labels.complete='Reply from your existing persona; selected viewer context is supplemental.';
      }
      const note=document.querySelector('.session-note');
      if(note)note.textContent=state.mode==='persona-conversation'?'Read-only viewer \u00b7 Native persona permissions apply':'Private \u00b7 Read-only session';
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
    profileReadEpoch++;
    treeObserver?.disconnect();treeObserver=null;
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
  function renderProfile(profile, view, ticket, detailTicket) {
    const host=$('detail-content');host.replaceChildren();
    const persona=profile.record.kind==='persona';
    const section=(title,parent)=>{const box=text('section','', 'profile-section');box.append(text('h3',title));parent.append(box);return box;};
    const value=(parent,label,content)=>{const line=text('div','', 'profile-field');line.append(text('span',label,'profile-label'),text('span',content));parent.append(line);};
    const links=(parent,rows,empty)=>{
      if(!rows.length){parent.append(text('p',empty,'profile-empty'));return;}
      for(const row of rows){const button=text('button',view.title(row),'profile-link');button.type='button';
        button.addEventListener('click',()=>showDetails(row));parent.append(button);}
    };
    host.append(text('p',profile.kind,'profile-kind'));
    if(profile.description)host.append(text('p',profile.description,'profile-description'));
    const grid=text('div','', 'profile-grid');host.append(grid);
    const contact=section('Identity & contact',grid);
    for(const row of profile.contacts){const line=text('div','', 'profile-field');line.append(text('span',row.label,'profile-label'));
      if(row.href){const link=text('a',row.value,'profile-contact');link.href=row.href;link.rel='noopener noreferrer';
        if(row.href.startsWith('https:'))link.target='_blank';line.append(link);}
      else line.append(text('span',row.value||'Not linked in the authorized information',row.value?'':'profile-empty'));
      contact.append(line);}
    const related=section(profile.record.kind==='organization'?'People & structure':'People & responsibilities',grid);
    if(profile.people.length)links(related,profile.people,'');
    if(profile.roles.length)links(related,profile.roles,'');
    if(profile.departments.length){related.append(text('h4','Departments'));links(related,profile.departments,'');}
    if(!profile.people.length&&!profile.roles.length&&!profile.departments.length)related.append(text('p','No published associations for this record.','profile-empty'));
    if(profile.functions.length){const box=section('Responsibilities',host),list=text('ul','', 'profile-functions');
      for(const item of profile.functions)list.append(text('li',item));box.append(list);}
    if(profile.tools.length||profile.excluded.length){const box=section('Declared tools',host);value(box,'Available',profile.tools.join(', ')||'None declared');
      if(profile.excluded.length)value(box,'Excluded',profile.excluded.join(', '));}
    const docs=section('Profiles & working documents',host);
    let activeDocument=null;
    const closeDocument=()=>{profileReadEpoch++;if(activeDocument){activeDocument.reader.replaceChildren();activeDocument.reader.hidden=true;activeDocument.button.setAttribute('aria-expanded','false');activeDocument=null;}};
    if(!profile.documents.length)docs.append(text('p','No document or profile text has been published for this record.','profile-empty'));
    for(const row of profile.documents){
      const filename=row.data.filename, label=persona&&['IDENTITY.md','SOUL.md'].includes(filename)?filename.slice(0,-3):view.title(row);
      const line=text('div','',persona?'profile-document-row':'profile-document-entry'),reader=text('section','', 'profile-reader');reader.hidden=true;
      const button=text('button',label,'profile-link profile-document');button.type='button';
      button.setAttribute('aria-expanded','false');reader.setAttribute('aria-label',filename||view.title(row));
      line.append(button,reader);docs.append(line);
      button.addEventListener('click',async()=>{
        if(activeDocument?.button===button){closeDocument();return;}
        closeDocument();activeDocument={button,reader};button.setAttribute('aria-expanded','true');
        const readTicket=++profileReadEpoch;reader.hidden=false;reader.replaceChildren(text('p','Loading current document...'));
        try{const current=await api(ScopedModel.detailPath(row),undefined,controller?.signal);
          if(ticket!==epoch||detailTicket!==detailEpoch||readTicket!==profileReadEpoch||!$('detail').open)return;
          const content=ScopedModel.detailText(row,current),fresh=new ScopedModel(await api('/api/state',undefined,controller?.signal));
          if(ticket!==epoch||detailTicket!==detailEpoch||readTicket!==profileReadEpoch||!$('detail').open)return;
          if(fresh.view.view_revision!==view.view.view_revision||fresh.view.policy_revision!==view.view.policy_revision||fresh.view.scope_id!==view.view.scope_id)throw Error('Profile information changed');
          const body=ScopedModel.isReviewedNote(row)?content:typeof current.data?.content==='string'&&['markdown','text/plain'].includes(current.data.format)
            ?current.data.content:'Document information is available, but its text has not been published for this session.';
          reader.replaceChildren();const close=text('button','Close document','profile-reader-close');close.type='button';
          close.addEventListener('click',closeDocument);reader.append(close,text('h3',filename||view.title(row)),text('pre',body,'profile-document-body'));
        }catch(error){if(readTicket===profileReadEpoch&&detailTicket===detailEpoch)failure(error,ticket);}
      });}
    if(profile.fields.length){const extra=text('details','', 'profile-extra');extra.append(text('summary','Organization & record details'));
      for(const field of profile.fields)value(extra,field.label,field.value);host.append(extra);}
    const other=profile.relations.filter(item=>!['persona','human','role','department'].includes(item.record.kind));
    if(other.length)links(section('Related information',host),other.map(item=>item.record),'');
    host.append(text('p','Source: current authorized organization records. Documents are shown only when separately available to this session.','profile-source'));
  }
  async function showDetails(row) {
    const ticket=epoch, detailTicket=++detailEpoch;
    // Remove old contents before any new read; never show a cached fallback.
    detailFocus=null;$('assistant-about').hidden=true;
    profileReadEpoch++;
    $('detail').setAttribute('data-kind',row.kind);
    $('detail-content').textContent='Loading current record\u2026';$('detail-title').textContent='Record';if(!$('detail').open)$('detail').showModal();
    try{
      const view=new ScopedModel(await api('/api/state',undefined,controller?.signal));
      if(ticket!==epoch||detailTicket!==detailEpoch||!$('detail').open)return;
      const selected=view.byId.get(row.id);if(!selected||selected.kind!==row.kind)throw Error('Record is no longer visible');
      const current=await api(ScopedModel.detailPath(selected),undefined,controller?.signal);
      if(ticket!==epoch||detailTicket!==detailEpoch||!$('detail').open)return;
      const content=ScopedModel.detailText(selected,current),fresh=new ScopedModel(await api('/api/state',undefined,controller?.signal));
      if(ticket!==epoch||detailTicket!==detailEpoch||!$('detail').open)return;
      if(fresh.view.view_revision!==view.view.view_revision||fresh.view.policy_revision!==view.view.policy_revision||fresh.view.scope_id!==view.view.scope_id)throw Error('Record information changed');
      if(ScopedModel.isReviewedNote(selected)||selected.kind==='document')$('detail-content').replaceChildren(text('pre',content,'profile-document-body'));
      else renderProfile(view.profile(current),view,ticket,detailTicket);
      const title=ScopedModel.isReviewedNote(selected)?current.title:view.title(current);
      $('detail-title').textContent=title;
      detailFocus={id:current.id,title};$('assistant-about').hidden=!chat.view;
    }catch(error){if(detailTicket===detailEpoch)failure(error,ticket);}
  }
  function renderOrganizationTree(sourceTree, observe=true, preferences={}) {
    $('graph-panel').hidden=false;
    const graphWidth=$('graph').clientWidth;if(graphWidth<240)return;
    const tree=ScopedModel.fitTree(sourceTree,graphWidth);
    const graph=$('graph');graph.replaceChildren();$('graph-panel').hidden=false;$('graph-title').textContent='Organization tree';
    $('graph-caption').textContent=`Visible reporting levels \u00b7 ${tree.unlinked} unlinked personas`+(tree.truncated?' \u00b7 diagram limited to 60 cards':'');
    const canvas=text('div','', 'organization-tree'+(tree.compact?' tree-compact':''));canvas.style.width=tree.width+'px';canvas.style.height=tree.height+'px';
    const ns='http://www.w3.org/2000/svg',svg=(tag,attrs)=>{const element=document.createElementNS(ns,tag);for(const[key,value]of Object.entries(attrs))element.setAttribute(key,String(value));return element;};
    const lines=svg('svg',{width:tree.width,height:tree.height,viewBox:`0 0 ${tree.width} ${tree.height}`,'aria-label':'Reporting and workflow connections'});
    const defs=svg('defs',{}),marker=svg('marker',{id:'tree-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});
    marker.append(svg('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'context-stroke'}));defs.append(marker);lines.append(defs);canvas.append(lines);
    const paths=new Map(),cards=new Map();tree.routing ||= ScopedModel.treeRoutes(tree);
    let selected=preferences.selected||[...tree.nodes].filter(node=>node.record.kind!=='organization').sort((a,b)=>tree.positions.get(a.id).y-tree.positions.get(b.id).y)[0]?.id,all=!!preferences.all;
    const controls=text('label','', 'tree-controls'),toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=all;controls.append(toggle,text('span','All workflows'));graph.append(controls);
    const detail=text('div','', 'tree-detail');detail.setAttribute('aria-live','polite');
    for(const edge of tree.edges){const workflow=edge.type==='escalation';
      const path=svg('path',{d:ScopedModel.treePath(tree,edge),
        class:'tree-edge '+(workflow?'workflow':edge.type==='context'?'context':'reporting')});
      if(edge.type!=='context')path.setAttribute('marker-end','url(#tree-arrow)');
      const title=svg('title',{});title.textContent=edge.label||edge.type;path.append(title);lines.append(path);paths.set(edge.id,path);
    }
    for(const point of tree.junctions)lines.append(svg('circle',{cx:point.x,cy:point.y,r:3,class:'tree-junction'}));
    const unrouted=[...tree.routing.values()].filter(route=>route.unrouted).length;
    if(unrouted)$('graph-caption').textContent+=` \u00b7 ${unrouted} connections need more diagram space; inspect role records`;
    const highlight=id=>{
      const nodes=new Set(id?[id]:[]),edges=new Set();
      if(id){let current=id;const seen=new Set();
        while(!seen.has(current)){seen.add(current);const edge=tree.edges.find(row=>row.source===current&&row.type!=='escalation');if(!edge)break;nodes.add(edge.target);edges.add(edge.id);current=edge.target;}
        const pending=[id];for(let i=0;i<pending.length;i++)for(const edge of tree.edges)if(edge.type!=='escalation'&&edge.target===pending[i]){
          edges.add(edge.id);if(!nodes.has(edge.source)){nodes.add(edge.source);pending.push(edge.source);}}
        for(const edge of tree.edges)if(edge.type==='escalation'&&(edge.source===id||edge.target===id)){edges.add(edge.id);nodes.add(edge.source);nodes.add(edge.target);}
      }
      for(const[key,card]of cards){card.classList.toggle('lit',nodes.has(key));card.classList.toggle('dim',!!id&&!nodes.has(key));}
      for(const[key,path]of paths){path.classList.toggle('lit',edges.has(key));path.classList.toggle('dim',!!id&&!edges.has(key));
        path.style.display=!all&&tree.edges.find(edge=>edge.id===key).type==='escalation'&&!edges.has(key)?'none':'';}
      const node=tree.nodes.find(row=>row.id===(id||selected));detail.replaceChildren();
      if(node){for(const row of [...node.personas,...node.humans,...(node.record.kind==='role'?[node.record]:[]),...node.departments])detail.append(link(row,'tree-detail-link'));}
    
    };
    const link=(row,className)=>{const button=text('button',model.title(row),className);button.type='button';button.title=model.title(row);button.addEventListener('click',()=>showDetails(row));return button;};
    for(const node of tree.nodes){const point=tree.positions.get(node.id),card=text('article','', 'tree-card'+(node.record.kind==='organization'?' tree-root':''));
      card.style.left=point.x+'px';card.style.top=point.y+'px';card.style.width=tree.sizes.get(node.id).w+'px';card.style.height=tree.sizes.get(node.id).h+'px';
      card.append(link(node.personas.length===1?node.personas[0]:node.record,'tree-primary'));
      if(node.record.kind==='organization'){card.append(text('p','Organization','tree-role'));}
      else{
        if(node.record.kind==='role')card.append(link(node.record,'tree-role'));
        if(node.personas.length>1){const names=text('div','', 'tree-personas');for(const persona of node.personas.slice(0,3))names.append(link(persona,'tree-persona'));card.append(names);}
        const humans=text('div','', 'tree-humans');humans.append(text('span','Human: '));
        if(node.humans.length)for(const human of node.humans.slice(0,3))humans.append(link(human,'tree-human'));else humans.append(text('span','No visible counterpart','tree-muted'));card.append(humans);
        const departments=text('div','', 'tree-departments');for(const department of node.departments.slice(0,2))departments.append(link(department,'tree-department'));
        if(!node.departments.length)departments.append(text('span','No visible department','tree-muted'));card.append(departments);
        if(node.issue)card.append(text('p',node.issue,'tree-warning'));else if(!node.personas.length)card.append(text('p','Persona assignment not published','tree-warning'));
      }
      card.addEventListener('mouseenter',()=>highlight(node.id));card.addEventListener('mouseleave',()=>highlight(selected));
      card.addEventListener('focusin',()=>highlight(node.id));card.addEventListener('focusout',event=>{if(!card.contains(event.relatedTarget))highlight(selected);});
      card.addEventListener('click',()=>{selected=node.id;preferences.selected=selected;highlight(selected);});
      cards.set(node.id,card);canvas.append(card);
    }
    graph.append(canvas,detail);toggle.addEventListener('change',()=>{all=toggle.checked;preferences.all=all;highlight(selected);});highlight(selected);
    const legend=text('div','', 'tree-legend');legend.setAttribute('aria-label','Connection legend');
    for(const [style,label]of [['reporting','Reports to \u00b7 solid green arrow points to the manager'],['workflow','Workflow / escalation \u00b7 dashed amber arrow points to the destination'],['context','Organization context \u00b7 dotted line connects the role to its organization']]){
      const item=text('span','', 'tree-key'),sample=svg('svg',{width:44,height:14,'aria-hidden':'true'});
      const path=svg('path',{d:'M 0 7 H 40',class:'tree-edge '+style});if(style!=='context')path.setAttribute('marker-end','url(#tree-arrow)');sample.append(path);item.append(sample,text('span',label));legend.append(item);
    }
    legend.append(text('span','A dot is a shared reporting junction. Crossings without a dot are separate. Hover or focus a persona for its workflows and linked details.','tree-legend-note'));
    graph.append(legend);
    if(observe){let width=graphWidth;treeObserver=new ResizeObserver(()=>{if(!graph.querySelector('.organization-tree')||!model){treeObserver?.disconnect();return;}
      if(Math.abs(graph.clientWidth-width)>1){width=graph.clientWidth;renderOrganizationTree(sourceTree,false,preferences);}});treeObserver.observe(graph);}

  }
  function renderGraph() {
    treeObserver?.disconnect();treeObserver=null;
    if(!section){const tree=model.organizationTree();if(tree){renderOrganizationTree(tree);return;}}
    $('graph-title').textContent='Relationships';
    const graph=$('graph');graph.replaceChildren();
    const selected=model.selection(section);
    const nodes=model.resources.filter(row=>!selected||row.kind===selected.kind).slice(0,60), ids=new Set(nodes.map(row=>row.id));
    const edges=model.relations.filter(row=>ids.has(row.data.source)&&ids.has(row.data.target));
    $('graph-panel').hidden=!nodes.length;
    $('graph-caption').textContent=`${nodes.length} visible records \u00b7 ${edges.length} connections`+(model.resources.length>60?' \u00b7 graph limited to 60 records':'');
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
  function renderOverviewRecords(records) {
    const rows=model.personaRows();
    if(rows.length){
      const wrapper=text('div','', 'persona-directory'),table=text('table','', 'persona-records');
      table.setAttribute('aria-label','Persona, human and role associations');
      const head=text('thead',''),header=text('tr','');
      for(const label of ['Persona','Human','Role']){const cell=text('th',label);cell.scope='col';header.append(cell);}head.append(header);table.append(head);
      const body=text('tbody','');
      for(const row of rows){const line=text('tr','');
        for(const [items,empty]of [[[row.persona].filter(Boolean),'No linked persona'],[row.humans,'No visible counterpart'],[row.roles,'No visible role']]){
          const cell=text('td','');
          for(const record of items){const button=text('button',model.title(record),'record-link');button.type='button';
            button.addEventListener('click',()=>showDetails(record));cell.append(button);}
          if(!items.length)cell.append(text('span',empty,'muted'));line.append(cell);
        }
        body.append(line);
      }
      table.append(body);wrapper.append(table);records.append(wrapper);
    }
    for(const kind of [...new Set(model.resources.map(row=>row.kind))].filter(kind=>!['persona','human','role'].includes(kind))){
      const group=text('section','', 'record-group'),heading=text('h3',SCOPED_KINDS[kind]),cards=text('div','', 'cards');group.append(heading,cards);
      for(const row of model.resources.filter(row=>row.kind===kind)){
        const button=text('button',model.title(row),'card');button.type='button';button.addEventListener('click',()=>showDetails(row));cards.append(button);
      }
      records.append(group);
    }
  }
  function render(search=false) {
    const selected=model.selection(section);
    const selectSection=id=>{section=id;chat.reset();render(search);loadAssistant(epoch);};
    $('organization').textContent=model.organization();$('scope-label').textContent=model.view.scope_id;
    $('page-title').textContent=search?'Search your workspace':selected?selected.label:'Your information, connected.';
    const nav=$('navigation');nav.replaceChildren();
    let group='';
    for(const item of [{id:'',label:search?'All results':'Overview'},...model.sections()]) {
      if(item.module&&item.module!==group){group=item.module;nav.append(text('span',group,'module-label'));}
      const button=text('button',item.label);button.type='button';button.className=section===item.id?'active':'';
      button.setAttribute('aria-current',section===item.id?'page':'false');button.addEventListener('click',()=>selectSection(item.id));nav.append(button);
    }
    const stats=$('stats');stats.replaceChildren();
    for(const[kind,count]of Object.entries(model.counts())){
      const target=model.sections().find(item=>item.kind===kind),tile=text('button','', 'stat');tile.type='button';
      tile.append(text('span',SCOPED_KINDS[kind]),text('strong',count));tile.disabled=!target;
      tile.setAttribute('aria-label',`Show ${SCOPED_KINDS[kind]} (${count})`);
      tile.setAttribute('aria-current',target&&section===target.id?'page':'false');
      tile.classList.toggle('active',!!target&&section===target.id);
      if(target)tile.addEventListener('click',()=>selectSection(target.id));stats.append(tile);
    }
    const records=$('records');records.replaceChildren();
    const overview=!search&&!selected;
    records.className=overview?'overview-records':selected?.view==='table'?'record-table':'cards';
    if(overview)renderOverviewRecords(records);
    else for(const row of model.resources.filter(row=>!selected||row.kind===selected.kind)) {
      const card=text('button','', 'card');card.type='button';card.append(text('small',SCOPED_KINDS[row.kind]),text('h3',model.title(row)));
      const summary=row.data.description||row.data.severity||row.data.kind;
      if(typeof summary==='string')card.append(text('p',summary.slice(0,180)));card.addEventListener('click',()=>showDetails(row));records.append(card);
      if(selected?.view==='document')card.append(text('pre',JSON.stringify(row.data,null,2),'record-preview'));
    }
    if(!records.childElementCount)records.append(text('p','No records are available in this view.','muted'));
    if(search){treeObserver?.disconnect();treeObserver=null;$('graph-panel').hidden=true;$('graph').replaceChildren();}else renderGraph();
    $('status').textContent=search?'Results cover all information available to this session.':'Showing only information available to this session.';
    $('records-title').textContent=search?'Search results':selected?selected.label:'Available records';
  }
  async function load() {
    if(closing)return;
    const ticket=operation();$('status').textContent='Refreshing your workspace\u2026';$('query').value='';
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
  $('logout').addEventListener('click',async()=>{if(closing)return;closing=true;const ticket=operation();$('query').value='';$('status').textContent='Closing your session\u2026';
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
    $('review-current').textContent=`Current: ${row.category} \u00b7 ${row.scope.id}`;
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
    const ticket=operation();$('status').textContent='Searching all authorized information\u2026';
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
