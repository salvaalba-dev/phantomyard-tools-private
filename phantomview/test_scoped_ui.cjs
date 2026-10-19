/* Visible-only workspace models and directed graph behavior. */
'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const {ScopedModel}=require('./scoped-ui.js');
const a='a'.repeat(64),b='b'.repeat(64),c='c'.repeat(64),e='e'.repeat(64);
function organizationFixture(){
  let serial=0;const resources=[],relations=[],node=(kind,title)=>{const row={id:(++serial).toString(16).padStart(64,'0'),kind,data:{title}};resources.push(row);return row;};
  const org=node('organization','Example Foundation'),chief=node('role','Executive'),manager=node('role','Operations'),staff=node('role','Field coordinator');
  const persona=node('persona','Field persona'),human=node('human','Project counterpart'),department=node('department','Field operations');
  const edge=(source,target,type)=>relations.push({id:(++serial).toString(16).padStart(64,'0'),kind:'relationship',data:{source:source.id,target:target.id,type}});
  edge(staff,manager,'reports');edge(manager,chief,'reports');edge(staff,persona,'assignment');edge(human,persona,'counterpart');edge(staff,department,'membership');
  const view={...fixture(),resources,relations};return {view,org,chief,manager,staff,persona,human,department,edge};
}
test('organization levels follow reporting links and cards join only visible explicit assignments',()=>{
  const f=organizationFixture();f.edge(f.chief,f.staff,'escalation');const tree=new ScopedModel(f.view).organizationTree();
  assert.equal(tree.positions.get(f.org.id).y,tree.positions.get(f.chief.id).y);
  assert.ok(tree.positions.get(f.org.id).x+240<tree.positions.get(f.chief.id).x);
  assert.ok(tree.positions.get(f.chief.id).y<tree.positions.get(f.manager.id).y);
  assert.ok(tree.positions.get(f.manager.id).y<tree.positions.get(f.staff.id).y);
  const card=tree.nodes.find(row=>row.id===f.staff.id);assert.equal(card.personas[0].id,f.persona.id);
  assert.equal(card.humans[0].id,f.human.id);assert.equal(card.departments[0].id,f.department.id);
  assert.equal(tree.edges.filter(row=>row.type==='escalation').length,1);assert.equal(tree.unlinked,0);
});
test('missing assignments never infer placement or counterparts from names or raw identifiers',()=>{
  const f=organizationFixture();f.persona.data.role=f.staff.id;f.view.relations=f.view.relations.filter(row=>!['assignment','counterpart','membership'].includes(row.data.type));
  const tree=new ScopedModel(f.view).organizationTree(),card=tree.nodes.find(row=>row.id===f.persona.id);
  assert.equal(tree.unlinked,1);assert.equal(card.humans.length,0);assert.equal(card.departments.length,0);
  assert.ok(card.issue.includes('not published'));assert.ok(!tree.edges.some(row=>row.source===f.persona.id||row.target===f.persona.id));
});

test('organization tree preserves context links and uses bounded orthogonal connector paths',()=>{
  const f=organizationFixture();f.edge(f.chief,f.staff,'escalation');f.edge(f.staff,f.manager,'escalation');
  const tree=new ScopedModel(f.view).organizationTree();
  assert.ok(tree.edges.some(edge=>edge.type==='context'&&edge.source===f.chief.id&&edge.target===f.org.id));
  for(const edge of tree.edges){
    const path=ScopedModel.treePath(tree,edge);assert.match(path,/^M [\d.]+ [\d.]+ [HV]/);assert.doesNotMatch(path,/[CQLASTZ]/i);
    const values=path.match(/\d+(?:\.\d+)?/g).map(Number);assert.ok(values.every(Number.isFinite));
    assert.ok(!path.includes('-'));assert.ok(Math.max(...values)<=Math.max(tree.width,tree.height));
    assert.equal(tree.routing.get(edge.id).overlap,0);
  }
});

test('same-level workflow connectors use clear facing sides without a perimeter detour',()=>{
  const f=organizationFixture();f.view.relations.splice(0,f.view.relations.length,...f.view.relations.filter(edge=>edge.data.type!=='reports'));f.edge(f.manager,f.staff,'escalation');
  const tree=new ScopedModel(f.view).organizationTree(),edge=tree.edges.find(edge=>edge.type==='escalation');
  const a=tree.positions.get(edge.source),b=tree.positions.get(edge.target);assert.equal(a.y,b.y);
  const path=ScopedModel.treePath(tree,edge),route=tree.routing.get(edge.id);
  assert.ok(!path.includes(' C '));assert.equal(route.overlap,0);
  assert.ok(['left','right'].includes(route.targetSide));assert.ok(route.points.length<=4);
});

function routingFixture(){
  const positions=new Map([['org',{x:16,y:64}],['chief',{x:970,y:64}],['finance',{x:295,y:294}],['operations',{x:835,y:294}],
    ['alliances',{x:1375,y:294}],['marketing',{x:1645,y:294}],['project',{x:565,y:524}],['volunteers',{x:835,y:524}],['training',{x:1105,y:524}]]);
  const nodes=[...positions.keys()].map(id=>({id,record:{kind:id==='org'?'organization':'role'}}));let id=0;
  const edges=[],add=(source,target,type)=>edges.push({id:String(++id),source,target,type});
  for(const actor of ['finance','operations','alliances','marketing'])add(actor,'chief','reports');
  for(const actor of ['project','volunteers','training'])add(actor,'operations','reports');add('chief','org','context');
  for(const [source,target]of [['volunteers','operations'],['alliances','operations'],['operations','finance'],['operations','alliances'],
    ['project','operations'],['finance','operations'],['chief','project'],['marketing','chief'],['training','operations'],['operations','chief'],['finance','chief']])add(source,target,'escalation');
  return {positions,nodes,edges,width:2072,height:754};
}

test('dense reporting layout takes the clear right-hand entry for marketing escalation',()=>{
  const tree=routingFixture(),routes=ScopedModel.treeRoutes(tree),edge=tree.edges.find(e=>e.source==='marketing'&&e.type==='escalation');
  const route=routes.get(edge.id);assert.equal(route.targetSide,'right');assert.ok(route.points.length<=4);
  assert.ok(Math.max(...route.points.map(p=>p.x))<=1885);assert.ok(Math.min(...route.points.map(p=>p.y))>=64);
  for(const route of routes.values()){assert.ok(!route.unrouted);assert.equal(route.overlap,0);}
});

test('routing is deterministic, avoids card interiors and separates shared connector segments',()=>{
  const tree=routingFixture(),routes=ScopedModel.treeRoutes(tree);assert.deepEqual(routes,ScopedModel.treeRoutes(tree));
  const segments=[];
  for(const [id,route]of routes){const edge=tree.edges.find(e=>e.id===id);
    for(let i=1;i<route.points.length;i++){const a=route.points[i-1],b=route.points[i];assert.ok(a.x===b.x||a.y===b.y);
      for(const previous of segments){const c=previous.a,d=previous.b;if(previous.id===id)continue;
        const shared=a.x===b.x&&c.x===d.x&&a.x===c.x?Math.max(Math.min(a.y,b.y),Math.min(c.y,d.y))<Math.min(Math.max(a.y,b.y),Math.max(c.y,d.y)):
          a.y===b.y&&c.y===d.y&&a.y===c.y&&Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x))<Math.min(Math.max(a.x,b.x),Math.max(c.x,d.x));
        assert.equal(!!shared,false,'Shared segment between '+id+' and '+previous.id);
      }
      segments.push({id,a,b});
      for(const node of tree.nodes){const box={...tree.positions.get(node.id),w:240,h:node.record.kind==='organization'?104:160};
        const inside=a.x===b.x?a.x>box.x&&a.x<box.x+box.w&&Math.max(Math.min(a.y,b.y),box.y)<Math.min(Math.max(a.y,b.y),box.y+box.h):
          a.y>box.y&&a.y<box.y+box.h&&Math.max(Math.min(a.x,b.x),box.x)<Math.min(Math.max(a.x,b.x),box.x+box.w);
        assert.equal(inside,false,edge.id+' crosses '+node.id);
      }
    }
  }
});
test('reporting cycles and multiple managers stay bounded and are marked for review',()=>{
  const f=organizationFixture();f.edge(f.chief,f.staff,'reports');let tree=new ScopedModel(f.view).organizationTree();
  assert.equal(tree.nodes.filter(row=>row.issue.includes('Circular')).length,3);assert.ok(Number.isFinite(tree.height));
  const g=organizationFixture();g.edge(g.staff,g.chief,'reports');tree=new ScopedModel(g.view).organizationTree();
  assert.ok(tree.nodes.find(row=>row.id===g.staff.id).issue.includes('Multiple'));assert.ok(Number.isFinite(tree.width));
});
test('organization tree is bounded and project-only workspaces retain their relationship graph',()=>{
  assert.equal(new ScopedModel(fixture()).organizationTree(),null);const f=organizationFixture();
  for(let i=0;i<80;i++)f.view.resources.push({id:(100+i).toString(16).padStart(64,'0'),kind:'role',data:{title:'Role '+i}});
  const tree=new ScopedModel(f.view).organizationTree();assert.ok(tree.nodes.length<=60);assert.equal(tree.truncated,true);
});
function fixture(){return {schema_version:1,complete_corpus:false,organization:'example',scope_id:'river-project',
  policy_revision:'1'.repeat(64),view_revision:'2'.repeat(64),counts:{human:9000},
  resources:[{id:a,kind:'partner',data:{title:'River partner'}},{id:b,kind:'task',data:{title:'Field review'}},
    {id:c,kind:'objective',data:{title:'Improve monitoring'}}],
  relations:[{id:e,kind:'relationship',data:{source:a,target:b,label:'Assigned work',type:'assignment'}}]};}
test('record rows align personas with explicit visible counterparts and roles only',()=>{
  const f=organizationFixture();f.edge(f.human,f.persona,'counterpart');f.edge(f.department,f.persona,'assignment');
  f.persona.data.human='Unpublished human';const rows=new ScopedModel(f.view).personaRows(),row=rows.find(row=>row.persona?.id===f.persona.id);
  assert.deepEqual(row.humans.map(record=>record.id),[f.human.id]);
  assert.deepEqual(row.roles.map(record=>record.id),[f.staff.id]);
  assert.ok(!rows.flatMap(row=>row.humans).some(record=>record.data.title==='Unpublished human'));
  assert.ok(!row.roles.some(record=>record.kind==='department'));
});

test('unassigned humans and roles remain visible without fabricated persona joins',()=>{
  const f=organizationFixture();f.view.relations=[];const rows=new ScopedModel(f.view).personaRows();
  const row=rows.find(row=>row.persona?.id===f.persona.id);assert.deepEqual(row.humans,[]);assert.deepEqual(row.roles,[]);
  for(const record of f.view.resources.filter(row=>['human','role'].includes(row.kind))){
    const orphan=rows.find(row=>[...row.humans,...row.roles].some(item=>item.id===record.id));assert.equal(orphan.persona,null);
  }
  assert.deepEqual(new ScopedModel(fixture()).personaRows(),[]);
});

test('project menus contain only visible kinds and visible counts ignore global claims',()=>{
  const model=new ScopedModel(fixture());assert.deepEqual(model.sections().map(row=>row.kind),['objective','partner','task']);
  assert.deepEqual(model.counts(),{partner:1,task:1,objective:1});assert.equal(model.organization(),'example');
});

function navigation(data){return {schema_version:1,api_version:1,organization:data.organization,scope_id:data.scope_id,
  policy_revision:data.policy_revision,view_revision:data.view_revision,
  assistant:{persona:null,eligible:false,source:'session-issuer'},
  core:[{id:'core:partner',kind:'partner',label:'Partners',view:'table',count:1}],
  modules:[{id:'project-management',label:'Project management',assistant:{persona:'project-guide',eligible:true,source:'module'},
    sections:[{id:'project-management:partners',kind:'partner',label:'Project partners',view:'cards',count:1}]}]};}

test('server navigation preserves core and module sections with distinct local assistant routes',()=>{
  const data=fixture();data.navigation=navigation(data);const model=new ScopedModel(data);
  assert.deepEqual(model.sections().map(row=>row.id),['core:partner','project-management:partners']);
  assert.equal(model.selection('project-management:partners').view,'cards');
  assert.equal(model.assistant('project-management:partners').persona,'project-guide');
  assert.equal(model.assistant('core:partner').eligible,false);
  data.navigation.modules[0].label='Changed';assert.equal(model.sections()[1].module,'Project management');
});

test('issuer navigation accepts only its matching operational transport',()=>{
  const data=fixture();data.navigation=navigation(data);
  data.navigation.assistant={persona:'coordinator',eligible:true,source:'session-issuer'};
  const model=new ScopedModel(data),info={available:true,persona:'coordinator',scope_id:data.scope_id};
  assert.equal(model.assistant('core:partner').source,'session-issuer');
  assert.equal(model.acceptsAssistant(info,'core:partner'),true);
  assert.equal(model.acceptsAssistant({...info,persona:'administrator'},'core:partner'),false);
  assert.equal(model.acceptsAssistant({...info,available:false},'core:partner'),false);
});

test('stale, hidden-kind, duplicate and executable navigation cannot be rendered',()=>{
  for(const mutate of [nav=>nav.view_revision='f'.repeat(64),nav=>nav.core[0].kind='human',
    nav=>nav.core[0].count=9000,nav=>nav.modules.push(nav.modules[0]),nav=>nav.core[0].view='script',
    nav=>nav.core[0].label='<script>',nav=>nav.modules[0].assistant.eligible='true']){
    const data=fixture();data.navigation=navigation(data);mutate(data.navigation);assert.throws(()=>new ScopedModel(data));
  }
});

test('module graph impact does not traverse records outside the selected section',()=>{
  const model=new ScopedModel(fixture());assert.deepEqual([...model.impact(a,60,'partner').nodes],[a]);
  assert.equal(model.impact(a,60,'partner').edges.size,0);
});

test('eligible module metadata never enables the wrong persona transport',()=>{
  const data=fixture();data.navigation=navigation(data);const model=new ScopedModel(data);
  const info={available:true,persona:'project-guide',scope_id:data.scope_id};
  assert.equal(model.acceptsAssistant(info,'project-management:partners'),true);
  assert.equal(model.acceptsAssistant({...info,persona:'administrator'},'project-management:partners'),false);
  assert.equal(model.acceptsAssistant({...info,scope_id:'other-project'},'project-management:partners'),false);
  assert.equal(model.acceptsAssistant({...info,available:false},'project-management:partners'),false);
  assert.equal(model.acceptsAssistant(info,'core:partner'),false);
});
test('legacy snapshot envelopes and malformed endpoint projections fail closed',()=>{
  assert.throws(()=>new ScopedModel({snapshot:fixture()}));const data=fixture();data.relations[0].data.target='f'.repeat(64);
  assert.throws(()=>new ScopedModel(data));data.relations=[];data.resources.push(data.resources[0]);assert.throws(()=>new ScopedModel(data));
});
test('graph impact follows outgoing flows and handles cycles without touching unrelated nodes',()=>{
  const data=fixture();data.relations.push({id:'d'.repeat(64),kind:'relationship',data:{source:b,target:a}});
  const impact=new ScopedModel(data).impact(a);assert.deepEqual([...impact.nodes],[a,b]);assert.equal(impact.edges.size,2);
  assert.equal(impact.nodes.has(c),false);assert.equal(new ScopedModel(data).impact('f'.repeat(64)).nodes.size,0);
});
test('search preserves relationship-only matches without requiring unrelated endpoint cards',()=>{
  const data=fixture(),result={...data,results:data.relations,partial:false};const model=ScopedModel.search(result);
  assert.equal(model.resources[0].kind,'relationship');assert.equal(model.title(model.resources[0]),'Assigned work');
  assert.deepEqual(model.counts(),{relationship:1});
  delete result.scope_id;assert.throws(()=>ScopedModel.search(result));
});
test('projection bodies are detached and graph limits exclude out-of-view endpoints',()=>{
  const data=fixture(),model=new ScopedModel(data);data.resources[0].data.title='Changed elsewhere';
  assert.equal(model.resources[0].data.title,'River partner');assert.deepEqual([...model.impact(a,1).nodes],[a]);
  assert.equal(model.impact(a,1).edges.size,0);
});

test('reviewed knowledge cards open the bounded note endpoint and retain plain text',()=>{
  const row={id:a,kind:'knowledge',data:{title:'Handbook',actor:'coordinator',source:'reviewed-knowledge',payload_sha256:b}};
  const note={id:a,title:'Handbook',actor:'coordinator',payload_sha256:b,trust:'untrusted',format:'markdown',excerpt_only:false,
    content:'<img src=x onerror=alert(1)>\n# Untrusted Markdown'};
  assert.equal(ScopedModel.detailPath(row),'/api/reviewed-knowledge/'+a);
  assert.equal(ScopedModel.detailText(row,note),note.content);
  assert.equal(ScopedModel.detailPath(fixture().resources[0]),'/api/resource/'+a);
});

test('note details reject stale bytes, wrong identity and incomplete or trusted content',()=>{
  const row={id:a,kind:'knowledge',data:{title:'Handbook',actor:'coordinator',source:'reviewed-knowledge',payload_sha256:b}};
  const note={id:a,title:'Handbook',actor:'coordinator',payload_sha256:b,trust:'untrusted',format:'markdown',excerpt_only:false,content:'Text'};
  for(const change of [{id:c},{actor:'other'},{title:'Other note'},{payload_sha256:c},{trust:'trusted'},
    {format:'html'},{excerpt_only:true},{content:null},{content:'x'.repeat(262145)}])
    assert.throws(()=>ScopedModel.detailText(row,{...note,...change}));
});


test('fitted diagrams keep every card and route within the measured panel at responsive widths',()=>{
  for(const width of [280,320,580,736,1024,1328]){
    const original=routingFixture(),tree=ScopedModel.fitTree(original,width),routes=ScopedModel.treeRoutes(tree);
    assert.equal(tree.width,width);assert.equal(routes.size,19);assert.ok(tree.junctions.length>0);
    for(const node of tree.nodes){const b={...tree.positions.get(node.id),...tree.sizes.get(node.id)};
      assert.ok(b.x>=0&&b.x+b.w<=width);assert.ok(b.y>=0&&b.y+b.h<=tree.height);
      for(const other of tree.nodes.filter(row=>row.id!==node.id)){const c={...tree.positions.get(other.id),...tree.sizes.get(other.id)};
        assert.ok(b.x+b.w<=c.x||c.x+c.w<=b.x||b.y+b.h<=c.y||c.y+c.h<=b.y,'Overlapping cards');}
    }
    for(const [id,route]of routes){assert.ok(!route.unrouted,'Missing route '+id+' at '+width);assert.equal(route.overlap,0);
      for(let i=1;i<route.points.length;i++){const a=route.points[i-1],b=route.points[i];assert.ok(a.x===b.x||a.y===b.y);
        assert.ok(b.x>=0&&b.x<=width&&b.y>=0&&b.y<=tree.height);
        for(const node of tree.nodes){const box={...tree.positions.get(node.id),...tree.sizes.get(node.id)};
          const hit=a.x===b.x?a.x>box.x&&a.x<box.x+box.w&&Math.max(Math.min(a.y,b.y),box.y)<Math.min(Math.max(a.y,b.y),box.y+box.h):
            a.y>box.y&&a.y<box.y+box.h&&Math.max(Math.min(a.x,b.x),box.x)<Math.min(Math.max(a.x,b.x),box.x+box.w);
          assert.equal(hit,false,'Route crosses a card at '+width);}
      }
    }
    assert.deepEqual(original.positions,routingFixture().positions,'Fitting must not mutate the source tree');
  }
});

test('fitted peers wrap into rows and retain bounded cycle diagnostics',()=>{
  const f=organizationFixture();for(let i=0;i<30;i++)f.view.resources.push({id:(100+i).toString(16).padStart(64,'0'),kind:'role',data:{title:'Peer '+i}});
  const source=new ScopedModel(f.view).organizationTree(),tree=ScopedModel.fitTree(source,320);
  assert.equal(tree.nodes.length,source.nodes.length);assert.ok(tree.height>source.height);
  assert.throws(()=>ScopedModel.fitTree(source,NaN));assert.throws(()=>ScopedModel.fitTree(source,0));
});
