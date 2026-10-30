/* Pure graph operations shared by the editor and regression tests. */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MenaceGraph = factory();
})(typeof window !== 'undefined' ? window : this, function() {
  'use strict';
  function normalize(value) {return String(value ?? '').trim().toLowerCase().replace(/^@/, '').replace(/\/$/, '');}
  function keys(node) {
    const result = new Set();
    if (node.label && !/^new\b/i.test(node.label)) result.add('label:'+node.type+':'+normalize(node.label));
    for (const field of node.fields) {
      const name=normalize(field.name), value=normalize(field.value);
      if (!value || !/email|username|domain|profile url|website|original finding/.test(name)) continue;
      const kind=/email/.test(name)?'email':/username/.test(name)?'username':/domain/.test(name)?'domain':/original finding/.test(name)?'finding':'url';
      result.add(kind+':'+value);
    }
    return result;
  }
  function duplicates(graph, node) {
    const own=keys(node);
    return graph.nodes.filter(other=>other.id!==node.id && !other.annotation &&
      [...keys(other)].some(key=>own.has(key)));
  }
  function hiddenNodes(graph) {
    const hidden=new Set();
    for (const group of graph.groups || []) if(group.collapsed)
      graph.nodes.filter(n=>n.group===group.id).forEach(n=>hidden.add(n.id));
    const roots=new Set(graph.collapsed || []);
    for (const root of roots) {
      const visited=new Set([root]), queue=[root];
      while(queue.length) {
        const current=queue.pop();
        for(const edge of graph.edges.filter(e=>e.source===current)) {
          if(visited.has(edge.target))continue;
          visited.add(edge.target);queue.push(edge.target);
          if(!roots.has(edge.target))hidden.add(edge.target);
        }
      }
    }
    return hidden;
  }
  function visibility(graph, filters) {
    const hidden=hiddenNodes(graph), query=normalize(filters.query);
    const matching=new Set(graph.nodes.filter(n=>!hidden.has(n.id) &&
      (!filters.type||n.type===filters.type) && (!query || normalize([
        n.label,n.type,...(n.tags||[]),...n.fields.flatMap(f=>[f.name,f.value])
      ].join(' ')).includes(query))).map(n=>n.id));
    const dated=!!(filters.from||filters.to);
    const edges=graph.edges.filter(e=>(!filters.status||e.status===filters.status) &&
      (!dated || (!e.date ? filters.includeUndated!==false : ((!filters.from||e.date>=filters.from)&&(!filters.to||e.date<=filters.to)))) &&
      matching.has(e.source)&&matching.has(e.target));
    const nodes=(filters.status||dated) ? new Set(edges.flatMap(e=>[e.source,e.target])) : matching;
    return {nodes,edges:new Set(edges.map(e=>e.id))};
  }
  function merge(graph, sourceId, targetId) {
    const source=graph.nodes.find(n=>n.id===sourceId), target=graph.nodes.find(n=>n.id===targetId);
    if(!source || !target || source===target)throw new Error('Choose two different objects.');
    if(source.photo && target.photo && target.photo!==source.photo)throw new Error('Both objects have different photos. Export or remove one photo before merging.');
    for(const field of source.fields) {
      if(target.fields.some(f=>f.name===field.name && f.value===field.value && f.type===field.type))continue;
      let name=field.name, suffix=2;
      while(target.fields.some(f=>normalize(f.name)===normalize(name)))name=`${field.name} (${suffix++})`;
      target.fields.push({...field,name});
    }
    if(source.photo && !target.photo)target.photo=source.photo;
    target.tags=[...new Set([...(target.tags||[]),...(source.tags||[])])];
    target.sourceRefs=[...new Set([target.source,source.source,...(target.sourceRefs||[]),...(source.sourceRefs||[])].filter(Boolean))];
    graph.edges.forEach(e=>{if(e.source===sourceId)e.source=targetId;if(e.target===sourceId)e.target=targetId;});
    graph.nodes=graph.nodes.filter(n=>n.id!==sourceId);
    graph.collapsed=(graph.collapsed||[]).filter(n=>n!==sourceId);
    return target;
  }
  function projection(nodes,width,height) {
    if(!nodes.length)return {scale:1,x:0,y:0};
    const xs=nodes.map(n=>n.position.x),ys=nodes.map(n=>n.position.y);
    const x=Math.min(...xs)-50,y=Math.min(...ys)-50;
    return {scale:Math.min(width/(Math.max(...xs)-x+50),height/(Math.max(...ys)-y+50)),x,y};
  }
  function equivalent(a,b) {
    const stable=value=>JSON.stringify(value,(_key,item)=>item && typeof item==='object' && !Array.isArray(item)
      ? Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b))) : item);
    return stable(a)===stable(b);
  }
  return {normalize,duplicates,hiddenNodes,visibility,merge,projection,equivalent};
});
