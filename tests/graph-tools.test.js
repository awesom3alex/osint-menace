const test = require('node:test');
const assert = require('node:assert/strict');
const tools = require('../static/graph-tools.js');
const node = (id,label,fields=[]) => ({id,label,type:'Account',fields,position:{x:0,y:0},source:'',photo:''});
const field = (name,value) => ({name,value,type:'text',options:'',visible:false});
const fixture = () => ({nodes:[node('a','Alice',[field('Username','@alice')]),node('b','Bob'),node('c','Carol')],
  edges:[{id:'ab',source:'a',target:'b',status:'hypothesis'}, {id:'bc',source:'b',target:'c',status:'supported'},
         {id:'ca',source:'c',target:'a',status:'supported'}],groups:[],collapsed:[]});
test('search matches field values and tags while relationship filters retain endpoints',()=>{
  const g=fixture();g.nodes[0].tags=['priority'];
  assert.deepEqual([...tools.visibility(g,{query:'PRIORITY'}).nodes],['a']);
  assert.deepEqual([...tools.visibility(g,{query:'@alice'}).nodes],['a']);
  assert.deepEqual([...tools.visibility(g,{type:'Person'}).nodes],[]);
  const view=tools.visibility(g,{status:'hypothesis'});
  assert.deepEqual([...view.nodes],['a','b']);assert.deepEqual([...view.edges],['ab']);
});
test('branch collapse handles cycles without hiding the root or deleting objects',()=>{
  const g=fixture();g.collapsed=['a'];
  assert.deepEqual([...tools.hiddenNodes(g)].sort(),['b','c']);
  assert.equal(g.nodes.length,3);assert.equal(g.edges.length,3);
  g.collapsed=[];assert.equal(tools.hiddenNodes(g).size,0);
});
test('collapsed groups are reversible and compose with filters',()=>{
  const g=fixture();g.groups=[{id:'group',collapsed:true}];g.nodes[1].group='group';
  assert.deepEqual([...tools.visibility(g,{}).nodes],['a','c']);
  g.groups[0].collapsed=false;assert.equal(tools.visibility(g,{}).nodes.size,3);
});
test('duplicate suggestions normalize email and username without treating notes as identities',()=>{
  const g=fixture();const copy=node('d','Different label',[field('Username','alice')]);g.nodes.push(copy);
  assert.deepEqual(tools.duplicates(g,copy).map(n=>n.id),['a']);
  g.nodes[0].fields=[field('Email',' USER@example.com ')];copy.fields=[field('Email address','user@EXAMPLE.com')];
  assert.equal(tools.duplicates(g,copy)[0].id,'a');
  copy.fields=[field('Notes','user@example.com')];assert.equal(tools.duplicates(g,copy).length,0);
});
test('merge retains conflicting fields, evidence provenance, and relationships',()=>{
  const g=fixture();g.nodes[0].source='source-a';g.nodes[1].source='source-b';
  g.nodes[0].fields=[field('Email','first@example.com')];g.nodes[1].fields=[field('Email','second@example.com')];
  const target=tools.merge(g,'a','b');
  assert.deepEqual(target.fields.map(f=>f.value),['second@example.com','first@example.com']);
  assert.equal(target.fields[1].name,'Email (2)');
  assert.deepEqual(target.sourceRefs,['source-b','source-a']);
  assert.equal(g.nodes.length,2);assert.equal(g.edges[0].source,'b');assert.equal(g.edges[2].target,'b');
});
test('different photos require review before merging and do not mutate the graph',()=>{
  const g=fixture();g.nodes[0].photo='one';g.nodes[1].photo='two';const before=JSON.stringify(g);
  assert.throws(()=>tools.merge(g,'a','b'),/different photos/);assert.equal(JSON.stringify(g),before);
});
test('minimap projection handles empty and coincident positions',()=>{
  assert.deepEqual(tools.projection([],240,150),{scale:1,x:0,y:0});
  const p=tools.projection(fixture().nodes,240,150);assert.ok(Number.isFinite(p.scale)&&p.scale>0);
  assert.ok((0-p.x)*p.scale>=0 && (0-p.x)*p.scale<=240);
});
test('recovery comparison ignores JSON key order but detects changed graph content',()=>{
  assert.ok(tools.equivalent({id:'a',nodes:[{label:'A',id:'n'}]},{nodes:[{id:'n',label:'A'}],id:'a'}));
  assert.ok(!tools.equivalent({nodes:[{label:'A'}]},{nodes:[{label:'B'}]}));
});
test('timeline uses inclusive date bounds and explicitly handles undated relationships',()=>{
  const g=fixture();g.edges[0].date='2026-10-10';g.edges[1].date='2026-10-27';
  assert.deepEqual([...tools.visibility(g,{from:'2026-10-27',to:'2026-10-27',includeUndated:false}).edges],['bc']);
  assert.deepEqual([...tools.visibility(g,{from:'2026-10-27',includeUndated:true}).edges],['bc','ca']);
  assert.equal(g.edges.length,3);
});
