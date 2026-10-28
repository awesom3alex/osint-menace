/* Case-local graph editor. Cytoscape.js is vendored under its MIT license. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const graphs = JSON.parse($('graph-data').textContent);
  const config = JSON.parse($('graph-config').textContent);
  const clone = value => JSON.parse(JSON.stringify(value));
  const id = () => crypto.randomUUID().replaceAll('-', '');
  const fieldTypes = ['text', 'textarea', 'number', 'date', 'select', 'checkbox', 'url'];
  const tools = window.MenaceGraph;
  let graph, cy, selected = null, dirty = false, undo = [], redo = [], saving = false;
  let autosaveTimer, saveBlocked = false, recovery = null, connectionStart = null, mapProjection;
  let previewRequest = 0;
  const filters = {query:'', type:'', status:'',from:'',to:'',includeUndated:true};
  let editorId;
  try {editorId=sessionStorage.getItem('menace-graph-editor');if(!editorId){editorId=id();sessionStorage.setItem('menace-graph-editor',editorId);}}
  catch {editorId=id();}
  const draftPrefix = () => `menace-graph-draft:${config.caseId}:${graph.id}:`;
  const draftKey = () => draftPrefix()+editorId;

  const status = message => { $('graph-status').textContent = message; };
  function history() {
    undo.push(JSON.stringify(graph));
    if (undo.length > 12) undo.shift();
    redo = [];
  }
  function changed(message = 'Unsaved changes') {
    if(saveBlocked==='validation')saveBlocked=false;
    dirty = true; status(message); $('undo').disabled = !undo.length; $('redo').disabled = !redo.length;
    persistDraft();clearTimeout(autosaveTimer);
    if(!saveBlocked && !recovery)autosaveTimer=setTimeout(()=>saveGraph(false),1500);
  }
  function mutate(action, redraw = true) {
    const before=JSON.stringify(graph);history();
    try {action();} catch(error) {Object.assign(graph,JSON.parse(before));undo.pop();status(error.message);return;}
    changed(); renderCanvas(redraw); if (redraw) renderDetails(); else {const node=graph.nodes.find(n=>n.id===selected);if(node)renderDuplicates(node);}
  }
  function el(tag, text, parent) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (parent) parent.append(e);
    return e;
  }
  function button(parent, text, action) {
    const b = el('button', text, parent); b.type = 'button'; b.addEventListener('click', action); return b;
  }
  function input(parent, label, value, action, type = 'text', options = []) {
    const wrapper = el('label', label, parent);
    const control = el(type === 'textarea' ? 'textarea' : type === 'select' ? 'select' : 'input', undefined, wrapper);
    if (control.tagName === 'INPUT') control.type = type;
    if (type === 'select') for (const option of options) {
      const item = el('option', option, control); item.value = option;
    }
    if (type === 'checkbox') control.checked = value === true || value === 'true';
    else control.value = value ?? '';
    if (!['checkbox', 'file', 'color', 'select'].includes(type)) control.maxLength = ({Label:500,'Field name':100,'Group name':200,'Legend description':1000})[label] || (label==='Value'||type==='textarea'?20000:2000);
    let lastValue=type==='checkbox'?control.checked:control.value;
    const commit=()=>{
      if(!control.checkValidity())return;
      const value=type==='checkbox'?control.checked:control.value;
      if(value===lastValue)return;lastValue=value;action(value,control);
    };
    control.addEventListener('change',commit);
    if(['Label','Field name','Value','Tags (comma separated)','Supporting evidence / notes','Relationship date','Group name','Legend description'].includes(label)
       && ['text','textarea','url','number','date'].includes(type))control.addEventListener('input',commit);
    return control;
  }
  function renderCanvas(refreshControls = true) {
    const existing = cy ? {zoom:cy.zoom(), pan:cy.pan()} : null;
    const previousSelection=cy ? cy.nodes(':selected').map(n=>n.id()) : [];
    if (cy) cy.destroy();
    hideContext();
    const colors = Object.fromEntries(graph.legend.map(t => [t.type, t.color]));
    cy = cytoscape({container:$('graph-canvas'), layout:{name:'preset'}, boxSelectionEnabled:true,
      selectionType:'additive', minZoom:0.1, maxZoom:3,
      elements:[...(graph.groups||[]).map(g=>({data:{id:g.id,label:g.label,display:g.label,groupNode:true}})),
        ...graph.nodes.map(n => ({data:{...n, parent:n.group||undefined, color:colors[n.type], display:[n.label,
        ...n.fields.filter(f => f.visible).map(f => `${f.name}: ${f.value}`)].join('\n')},
        position:n.position, locked:n.pinned})), ...graph.edges.map(e => ({data:e}))],
      style:[{selector:'node',style:{'label':'data(display)','background-color':'data(color)',
        'color':'#edf5ff','font-size':12,'text-wrap':'wrap','text-max-width':150,'text-valign':'bottom',
        'text-margin-y':9,'width':64,'height':64,'border-width':2,'border-color':'#e4edf7'}},
        {selector:'node[groupNode]',style:{'label':'data(display)','shape':'roundrectangle','background-color':'#62758a','background-opacity':0.15,'border-color':'#9bacbf','border-width':2,'padding':30,'text-valign':'top','text-margin-y':-8,'width':100,'height':70}},
        {selector:'node[?annotation]',style:{'shape':'roundrectangle','width':170,'height':70,'background-color':'#ffed9b','color':'#101923','text-valign':'center','text-margin-y':0,'font-size':12,'text-max-width':150}},
        {selector:'.filtered',style:{'display':'none'}},
        {selector:'node[photo][photo != ""]',style:{'background-image':'data(photo)','background-fit':'cover'}},
        {selector:'edge',style:{'label':'data(label)','color':'#e1eaf5','font-size':11,'text-wrap':'wrap',
          'text-max-width':130,'text-background-color':'#101923','text-background-opacity':0.9,
          'curve-style':'bezier','target-arrow-shape':'triangle','line-color':'#9bacbf','target-arrow-color':'#9bacbf','width':2}},
        {selector:'edge[status = "hypothesis"]',style:{'line-style':'dashed'}},
        {selector:':selected',style:{'border-color':'#ffffff','border-width':5,'line-color':'#ffffff','target-arrow-color':'#ffffff'}}]});
    if (existing) {cy.zoom(existing.zoom); cy.pan(existing.pan);}
    for(const nid of previousSelection)cy.getElementById(nid).select();
    if (selected && cy.getElementById(selected).length) cy.getElementById(selected).select();
    cy.on('tap', 'node, edge', event => {
      if(event.target.data('groupNode')){toggleGroup(event.target.id());return;}
      if(connectionStart && event.target.isNode()) {finishConnection(connectionStart,event.target.id());return;}
      selected = event.target.id(); renderDetails();updateHandle();
    });
    cy.on('tap',event=>{if(event.target===cy){hideContext();connectionStart=null;}});
    cy.on('cxttap','node, edge',event=>showContext(event));
    cy.on('pan zoom render resize',()=>{drawMap();updateHandle();});
    cy.on('grab','node', () => history());
    cy.on('dragfree','node', event => {
      cy.nodes().filter(n=>!n.data('groupNode')).forEach(n=>{
        const model=graph.nodes.find(item=>item.id===n.id());if(model)model.position={...n.position()};
      });changed();drawMap();
    });
    renderLegend(refreshControls); renderElementChoice();if(refreshControls)renderGroups();renderMilestones();applyFilters();updateHandle();
  }
  function renderElementChoice() {
    const list = $('element-choice'); list.replaceChildren();
    const blank = el('option','Select an object or connection',list); blank.value='';
    for (const item of [...graph.nodes,...graph.edges]) {
      const opt = el('option',`${graph.nodes.includes(item) ? 'Object' : 'Connection'}: ${item.label || '(unnamed)'}`,list); opt.value=item.id;
    }
    list.value = selected || '';
  }
  function renderLegend(refreshControls = true) {
    const oldType=$('object-type').value;
    $('object-type').replaceChildren(); $('graph-legend').replaceChildren(); if(refreshControls)$('legend-editor').replaceChildren();
    for (const item of graph.legend) {
      const option = el('option',item.type,$('object-type')); option.value=item.type;
      const entry = el('span',undefined,$('graph-legend'));
      const swatch = el('span',undefined,entry); swatch.className='legend-swatch'; swatch.style.backgroundColor=item.color;
      el('span',`${item.type}: ${item.description}`,entry);
      if(!refreshControls)continue;
      const editor = el('div',undefined,$('legend-editor')); editor.className='graph-field';
      el('strong',item.type,editor);
      input(editor,'Color',item.color,v => mutate(() => item.color=v),'color');
      input(editor,'Legend description',item.description,v => mutate(() => item.description=v,false));
    }
    if(graph.legend.some(t=>t.type===oldType))$('object-type').value=oldType;
  }
  function renderDuplicates(node){
    const container=$('duplicate-warning');if(!container)return;container.replaceChildren();
    const matches=tools.duplicates(graph,node);
      if(matches.length){
        const warning=el('div',undefined,container);warning.className='duplicate-warning';
        el('strong','Possible duplicate — review before merging',warning);
        for(const match of matches)button(warning,`Merge into ${match.label}`,async()=>{
          if(!await confirmAction('Merge fields, source references, and connections into this object? Conflicting fields are retained separately. Undo can restore the separate objects.'))return;
          mutate(()=>{tools.merge(graph,node.id,match.id);selected=match.id;});
        });
        el('p','Keep both objects by leaving them separate. A match is a suggestion, not an identity determination.',warning);
      }
  }
  function renderDetails() {
    renderElementChoice(); const panel = $('details'); panel.replaceChildren();
    const node = graph.nodes.find(n => n.id===selected);
    const edge = graph.edges.find(e => e.id===selected);
    const item = node || edge;
    if (!item) {el('p','Select an object or connection to edit it.',panel); return;}
    input(panel,'Label',item.label,v => mutate(() => item.label=v, false));
    if (edge) {
      for (const endpoint of ['source','target']) {
        const select = input(panel,endpoint === 'source' ? 'From' : 'To',edge[endpoint],v => mutate(() => edge[endpoint]=v),'select',graph.nodes.map(n=>n.id));
        Array.from(select.options).forEach(o=>o.textContent=graph.nodes.find(n=>n.id===o.value).label);
      }
      input(panel,'Relationship status',edge.status,v => mutate(() => edge.status=v),'select',['hypothesis','supported']);
      input(panel,'Supporting evidence / notes',edge.notes,v => mutate(() => edge.notes=v,false),'textarea');
      input(panel,'Relationship date',edge.date||'',v=>mutate(()=>edge.date=v,false),'date');
      evidenceControls(panel,edge,true);
    } else {
      const profileLink=el('a','Open entity profile',panel);profileLink.href=config.caseUrl+'/entities/'+encodeURIComponent(graph.id)+'/'+encodeURIComponent(node.id);
      input(panel,'Object type',node.type,v => mutate(() => node.type=v),'select',graph.legend.map(t=>t.type));
      const objectOptions=el('details',undefined,panel);el('summary','Object options',objectOptions);
      input(objectOptions,'Pin position',node.pinned,v => mutate(() => node.pinned=v),'checkbox');
      input(objectOptions,'Tags (comma separated)',(node.tags||[]).join(', '),v=>mutate(()=>node.tags=v.split(',').map(t=>t.trim()).filter(Boolean),false));
      const groups=input(objectOptions,'Group',node.group||'',v=>mutate(()=>node.group=v),'select',['',...(graph.groups||[]).map(g=>g.id)]);
      Array.from(groups.options).forEach(o=>o.textContent=o.value ? graph.groups.find(g=>g.id===o.value).label : 'No group');
      button(objectOptions,(graph.collapsed||[]).includes(node.id)?'Expand branch':'Collapse outgoing branch',()=>toggleBranch(node.id));
      button(objectOptions,'Duplicate object',()=>duplicateNode(node));
      el('div',undefined,panel).id='duplicate-warning';renderDuplicates(node);
      evidenceControls(panel,node,false);
      const photoOptions=el('details',undefined,panel);el('summary','Photo',photoOptions);
      if (node.photo) {const img=el('img',undefined,panel);img.src=node.photo;img.alt=node.label; button(photoOptions,'Remove photo',()=>mutate(()=>node.photo=''));}
      const uploadLabel=el('label','Upload photo',photoOptions);
      const upload=el('input',undefined,uploadLabel);upload.type='file';upload.accept='image/png,image/jpeg,image/webp';
      upload.addEventListener('change',async()=>{
        const file=upload.files[0];if(!file)return;
        if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>10000000){status('Choose a PNG, JPEG, or WebP photo under 10 MB.');return;}
        const targetGraph=graph;
        try {
          const bitmap=await createImageBitmap(file);const scale=Math.min(1,512/Math.max(bitmap.width,bitmap.height));
          const canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
          canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
          if(graph!==targetGraph||!graph.nodes.includes(node))return;
          mutate(()=>node.photo=canvas.toDataURL('image/png'));
        } catch {status('The photo could not be read.');}
      });
      if (graph.nodes.length > 1) {
        const connectionOptions=el('details',undefined,panel);el('summary','Connections',connectionOptions);
        const linkLabel = el('label','Connect to object',connectionOptions);
        const targetChoice = el('select',undefined,linkLabel);
        for (const other of graph.nodes.filter(n => n.id !== node.id)) {
          const option = el('option',other.label,targetChoice); option.value=other.id;
        }
        button(connectionOptions,'Create connection',()=>mutate(()=>{
          const edge={id:id(),source:node.id,target:targetChoice.value,label:'Related to',notes:'',status:'hypothesis'};
          graph.edges.push(edge);selected=edge.id;
        }));
      }
      el('h3','Fields',panel);
      for (const [index,f] of node.fields.entries()) {
        const group=el('div',undefined,panel);group.className='graph-field';
        el('h4',f.name,group);
        const fieldSettings=el('details',undefined,group);el('summary','Field settings',fieldSettings);
        input(fieldSettings,'Field name',f.name,v=>mutate(()=>{f.name=v;group.querySelector('h4').textContent=v;group.querySelector('[aria-label]')?.setAttribute('aria-label',v);}, false));
        input(fieldSettings,'Field type',f.type,v=>mutate(()=>{f.type=v;f.value='';}),'select',fieldTypes);
        if(f.type==='select') input(fieldSettings,'Choices (separate with |)',f.options,v=>mutate(()=>{f.options=v;f.value='';}));
        const valueControl=input(group,'Value',f.value,v=>mutate(()=>f.value=typeof v==='boolean'?String(v):v, false),f.type,f.type==='select'?['',...f.options.split('|')]:[]);
        valueControl.setAttribute('aria-label',f.name);valueControl.parentElement.firstChild.textContent='';
        group.insertBefore(valueControl.parentElement,fieldSettings);
        input(fieldSettings,'Show on graph',f.visible,v=>mutate(()=>f.visible=v, false),'checkbox');
        if(index>0)button(fieldSettings,'Move field up',()=>mutate(()=>{[node.fields[index-1],node.fields[index]]=[node.fields[index],node.fields[index-1]];}));
        button(fieldSettings,'Remove field',()=>mutate(()=>node.fields.splice(index,1)));
      }
      button(panel,'Add custom field',()=>mutate(()=>{
        let name='Custom field';let i=2;while(node.fields.some(f=>f.name===name))name=`Custom field ${i++}`;
        node.fields.push({name,type:'text',value:'',options:'',visible:false});
      }));
      const templateOptions=el('details',undefined,panel);el('summary','Field templates',templateOptions);
      button(templateOptions,`Save fields as ${node.type} template`,()=>mutate(()=>{
        graph.templates[node.type]=node.fields.map(f=>({...f,value:''}));
      }));
      el('p','Use these fields for new objects of this type in this graph.',templateOptions);
    }
    const removal=el('details',undefined,panel);el('summary','Remove from graph',removal);
    button(removal,node?'Delete object and its connections':'Delete connection',()=>deleteItem(item.id)).className='danger';
  }
  function openGraph(gid) {
    graph=graphs.find(g=>g.id===gid);if(!graph){$('graph-workspace').hidden=true;return;}
    clearTimeout(autosaveTimer);saveBlocked=false;recovery=null;
    graph.groups ||= [];graph.collapsed ||= [];graph.views ||= [];graph.snapshots ||= [];graph.report ||= {include:false,viewId:''};
    $('graph-workspace').hidden=false;selected=null;undo=[];redo=[];dirty=false;
    resetFilters();
    $('evidence-preview').replaceChildren();el('h3','Evidence preview',$('evidence-preview'));
    previewRequest++;connectionStart=null;
    $('graph-name').value=graph.name;
    if(cy){cy.destroy();cy=null;}
    renderCanvas();renderDetails();if(graph.nodes.length)cy.fit(undefined,60);
    status('Autosave on');checkRecovery();
    $('undo').disabled=true;$('redo').disabled=true;
    const url=new URL(location.href);url.searchParams.set('graph',gid);window.history.replaceState(null,'',url);
  }
  $('graph-choice').addEventListener('change',async()=>{
    if(saving || (dirty&&!await confirmAction('Discard unsaved changes and open another graph?'))){$('graph-choice').value=graph?.id||'';return;}
    if(dirty) location.assign(config.base+'?graph='+encodeURIComponent($('graph-choice').value));
    else openGraph($('graph-choice').value);
  });
  $('graph-name').addEventListener('input',()=>mutate(()=>graph.name=$('graph-name').value,false));
  $('element-choice').addEventListener('change',()=>{selected=$('element-choice').value;cy.elements().unselect();cy.getElementById(selected).select();renderDetails();updateHandle();});
  $('add-object').addEventListener('click',()=>{const type=$('object-type').value;mutate(()=>{
    const extent=cy.extent();const node={id:id(),label:`New ${type}`,type,photo:'',source:'',pinned:false,
      annotation:type==='Annotation',fields:clone(graph.templates[type]||[]),position:{x:(extent.x1+extent.x2)/2+(graph.nodes.length%5)*35,y:(extent.y1+extent.y2)/2+(graph.nodes.length%5)*35}};
    graph.nodes.push(node);selected=node.id;
  });});
  $('connect').addEventListener('click',()=>{
    const nodes=cy.nodes(':selected');if(nodes.length!==2){status('Select exactly two objects, then connect. Use Shift-click or drag a selection box.');return;}
    mutate(()=>{const edge={id:id(),source:nodes[0].id(),target:nodes[1].id(),label:'Related to',notes:'',status:'hypothesis'};graph.edges.push(edge);selected=edge.id;});
  });
  $('add-type').addEventListener('click',()=>{
    const type=$('new-type').value.trim();if(!type||['__proto__','constructor','prototype'].includes(type)||graph.legend.some(t=>t.type===type)){status('Choose a unique object type name.');return;}
    mutate(()=>{graph.legend.push({type,color:'#80cbc4',description:type});graph.templates[type]=[{name:'Notes',type:'textarea',value:'',options:'',visible:false}];});$('new-type').value='';
  });
  $('fit').addEventListener('click',()=>cy.fit(undefined,60));
  $('layout').addEventListener('click',async()=>{
    if(!await confirmAction('Automatically arrange unpinned objects? You can undo this.'))return;
    history();cy.layout({name:'cose',animate:false,randomize:false}).run();
    cy.nodes().forEach(n=>graph.nodes.find(item=>item.id===n.id()).position={...n.position()});changed();
  });
  function restore(from,to){if(!from.length)return;to.push(JSON.stringify(graph));const revision=graph.revision;
    Object.assign(graph,JSON.parse(from.pop()),{revision});selected=null;$('graph-name').value=graph.name;renderCanvas();renderDetails();changed();}
  $('undo').addEventListener('click',()=>restore(undo,redo));$('redo').addEventListener('click',()=>restore(redo,undo));
  $('save-graph').addEventListener('click',()=>saveGraph(true));
  $('reload-graph').addEventListener('click',async()=>{
    if(saving){status('Wait for the current save to finish before reloading.');return;}
    if(dirty && !await confirmAction('Reload the saved graph and discard current edits? Export JSON first if you want to keep these changes.'))return;
    clearTimeout(autosaveTimer);try{localStorage.removeItem(draftKey());}catch{/* Storage may be unavailable. */}
    dirty=false;location.reload();
  });
  function download(blob,name){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('export-json').addEventListener('click',()=>download(new Blob([JSON.stringify(graph,null,2)],{type:'application/json'}),'case-graph.json'));
  $('export-png').addEventListener('click',async()=>{
    try {
      const image=new Image();image.src=cy.png({full:true,bg:'#101923',maxWidth:3000,maxHeight:3000});await image.decode();
      const canvas=document.createElement('canvas');canvas.width=Math.max(image.width,800);canvas.height=image.height+110+graph.legend.length*26;
      const ctx=canvas.getContext('2d');ctx.fillStyle='#101923';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0);
      ctx.fillStyle='#edf5ff';ctx.font='bold 20px sans-serif';ctx.fillText(graph.name,20,image.height+30);
      ctx.font='14px sans-serif';graph.legend.forEach((t,i)=>{const y=image.height+60+i*26;ctx.fillStyle=t.color;ctx.fillRect(20,y-12,14,14);ctx.fillStyle='#edf5ff';ctx.fillText(`${t.type}: ${t.description}`,44,y);});
      ctx.fillText('Solid arrow: supported connection · Dashed arrow: hypothesis',20,canvas.height-20);
      canvas.toBlob(blob=>{if(blob)download(blob,'case-graph.png');});
    }catch{status('Image export failed. Try exporting JSON instead.');}
  });
  window.addEventListener('beforeunload',event=>{if(dirty||saving){event.preventDefault();event.returnValue='';}});
  function confirmAction(message) {
    const dialog=$('graph-confirm');if(dialog.open)return Promise.resolve(false);
    $('graph-confirm-message').textContent=message;dialog.returnValue='cancel';
    return new Promise(resolve=>{
      const onClose=()=>{dialog.removeEventListener('close',onClose);resolve(dialog.returnValue==='confirm');};
      dialog.addEventListener('close',onClose);dialog.showModal();
    });
  }
  function persistDraft() {
    try {
      localStorage.setItem(draftKey(),JSON.stringify({graph,at:Date.now(),editorId}));
      if(!recovery)$('recovery-status').textContent='';
    } catch { $('recovery-status').textContent='Browser recovery storage is full or unavailable. Server autosave remains available; export JSON for an extra copy.'; }
  }
  function checkRecovery() {
    $('recover-draft').hidden=true;$('discard-draft').hidden=true;$('recovery-status').textContent='';
    try {
      const candidates=[];
      for(let i=0;i<localStorage.length;i++){
        const key=localStorage.key(i);if(!key.startsWith(draftPrefix()))continue;
        try {const draft=JSON.parse(localStorage.getItem(key));
          if(draft.graph?.id===graph.id && Array.isArray(draft.graph.nodes) && Array.isArray(draft.graph.edges))candidates.push({...draft,key});
        }catch{/* Ignore malformed local drafts. */}
      }
      candidates.sort((a,b)=>b.at-a.at);
      recovery=candidates.find(d=>!tools.equivalent({...d.graph,revision:graph.revision,groups:d.graph.groups||[],collapsed:d.graph.collapsed||[]},graph))||null;
      if(recovery){
        $('recovery-status').textContent=`An unfinished browser draft from ${new Date(recovery.at).toLocaleString()} is available. Recover to review it before saving${recovery.graph.revision!==graph.revision ? '; the server graph has changed since this draft' : ''}.`;
        $('recover-draft').hidden=false;$('discard-draft').hidden=false;
      }
    }catch{$('recovery-status').textContent='Browser recovery storage is unavailable.';}
  }
  async function saveGraph(manual) {
    clearTimeout(autosaveTimer);
    if(saving || (!manual && (saveBlocked || recovery || !dirty)))return;
    if(manual && recovery){status('Recover or discard the available draft before saving.');return;}
    if(manual&&!dirty){status('No unsaved changes. Autosave is on.');return;}
    const snapshot=JSON.stringify(graph), current=graph, key=draftKey();
    saving=true;$('save-graph').disabled=true;status(manual?'Saving…':'Autosaving…');
    try {
      const response=await fetch(config.base+'/'+current.id,{method:'PUT',headers:{'Content-Type':'application/json'},body:snapshot});
      const result=await response.json().catch(()=>({error:'Save failed. Check graph size and field values.'}));
      if(!response.ok){saveBlocked=response.status===409?'conflict':'validation';throw new Error(result.error||'Save failed.');}
      const unchanged=JSON.stringify(current)===snapshot;current.revision=result.revision;dirty=!unchanged;saveBlocked=false;
      try {if(unchanged)localStorage.removeItem(key);else persistDraft();}catch{/* Storage can be disabled. */}
      const option=Array.from($('graph-choice').options).find(o=>o.value===current.id);if(option)option.textContent=current.name;
      status(unchanged?`Saved at ${new Date().toLocaleTimeString()}`:'Earlier changes saved; saving latest edits next.');
      if(unchanged)$('recovery-status').textContent='';
    }catch(error){status(error.message+' Your unsaved work remains in this editor.');persistDraft();
      if(!saveBlocked)autosaveTimer=setTimeout(()=>saveGraph(false),10000);
    }finally{saving=false;$('save-graph').disabled=false;
      if(dirty&&!saveBlocked&&!recovery)autosaveTimer=setTimeout(()=>saveGraph(false),2000);
    }
  }
  $('recover-draft').addEventListener('click',()=>{
    if(!recovery)return;
    const recovered=clone(recovery.graph), oldKey=recovery.key, revision=graph.revision, milestones=graph.snapshots||[];
    recovered.groups ||= [];recovered.collapsed ||= [];
    mutate(()=>{Object.keys(graph).forEach(k=>delete graph[k]);Object.assign(graph,recovered,{revision,snapshots:milestones});selected=null;});
    clearTimeout(autosaveTimer);saveBlocked=true;recovery=null;
    try{localStorage.removeItem(oldKey);}catch{/* Keep draft if removal fails. */}persistDraft();
    $('recover-draft').hidden=true;$('discard-draft').hidden=true;$('graph-name').value=graph.name;
    status('Draft recovered. Review it, then choose Save graph to resume autosave.');
  });
  $('discard-draft').addEventListener('click',()=>{
    if(!recovery)return;
    try{localStorage.removeItem(recovery.key);}catch{status('Could not discard the recovery draft.');return;}
    recovery=null;checkRecovery();if(!recovery&&dirty)saveGraph(false);
  });
  window.addEventListener('pagehide',()=>{if(dirty)persistDraft();});
  function applyFilters() {
    const typeChoice=$('filter-type'), old=filters.type;
    typeChoice.replaceChildren();const all=el('option','All types',typeChoice);all.value='';
    for(const type of graph.legend){const o=el('option',type.type,typeChoice);o.value=type.type;}
    typeChoice.value=old;
    const visible=tools.visibility(graph,filters);
    cy.batch(()=>{
      cy.nodes().filter(n=>!n.data('groupNode')).forEach(n=>n.toggleClass('filtered',!visible.nodes.has(n.id())));
      cy.edges().forEach(e=>e.toggleClass('filtered',!visible.edges.has(e.id())));
    });
    const count=[filters.query,filters.type,filters.status,filters.from,filters.to].filter(Boolean).length;
    $('active-filters').hidden=!count;$('active-filters').textContent=count?String(count):'';
    $('filter-summary').textContent=visible.nodes.size===graph.nodes.length&&visible.edges.size===graph.edges.length
      ? `${graph.nodes.length} objects · ${graph.edges.length} connections`
      : `${visible.nodes.size}/${graph.nodes.length} objects · ${visible.edges.size}/${graph.edges.length} connections`;
    const results=$('search-results');results.replaceChildren();
    if(filters.query) {
      graph.nodes.filter(n=>visible.nodes.has(n.id)).slice(0,30).forEach(n=>button(results,n.label,()=>focusNode(n.id)));
      if(visible.nodes.size>30)el('span','First 30 results shown. Refine your search.',results);
    }
    drawMap();updateHandle();
  }
  function focusNode(nid) {
    const node=cy.getElementById(nid);if(!node.length)return;
    selected=nid;cy.elements().unselect();node.select();cy.center(node);renderDetails();updateHandle();
  }
  $('graph-search').addEventListener('input',()=>{filters.query=$('graph-search').value;applyFilters();});
  $('filter-type').addEventListener('change',()=>{filters.type=$('filter-type').value;applyFilters();});
  $('filter-status').addEventListener('change',()=>{filters.status=$('filter-status').value;applyFilters();});
  $('clear-filters').addEventListener('click',()=>{resetFilters();applyFilters();});
  function toggleBranch(nid){mutate(()=>{graph.collapsed ||= [];graph.collapsed=graph.collapsed.includes(nid)?graph.collapsed.filter(n=>n!==nid):[...graph.collapsed,nid];});}
  $('show-branches').addEventListener('click',()=>mutate(()=>{graph.collapsed=[];(graph.groups||[]).forEach(g=>g.collapsed=false);}));
  function toggleGroup(gid){mutate(()=>{const group=graph.groups.find(g=>g.id===gid);group.collapsed=!group.collapsed;});}
  function renderGroups() {
    const panel=$('group-editor');panel.replaceChildren();
    if(!graph.groups.length)el('p','Select multiple objects and choose Group selected objects.',panel);
    for(const group of graph.groups){const box=el('div',undefined,panel);box.className='graph-field';
      input(box,'Group name',group.label,v=>mutate(()=>group.label=v,false));
      button(box,group.collapsed?'Expand group':'Collapse group',()=>toggleGroup(group.id));
      button(box,'Ungroup objects',()=>mutate(()=>{graph.nodes.forEach(n=>{if(n.group===group.id)n.group='';});graph.groups=graph.groups.filter(g=>g!==group);}));
    }
  }
  $('group-selected').addEventListener('click',()=>{
    const nodes=cy.nodes(':selected').filter(n=>!n.data('groupNode'));
    if(!nodes.length){status('Select objects on the canvas to group them.');return;}
    mutate(()=>{const group={id:'group_'+id(),label:'New group',collapsed:false};graph.groups.push(group);nodes.forEach(n=>graph.nodes.find(m=>m.id===n.id()).group=group.id);});
  });
  $('add-annotation').addEventListener('click',()=>mutate(()=>{
    const type='Annotation';if(!graph.legend.some(t=>t.type===type)){graph.legend.push({type,color:'#ffed9b',description:'Analyst notes on the graph'});graph.templates[type]=[{name:'Note',type:'textarea',value:'',options:'',visible:true}];}
    const extent=cy.extent();const note={id:id(),type,label:'Analyst annotation',annotation:true,photo:'',source:'',pinned:false,tags:[],group:'',
      position:{x:(extent.x1+extent.x2)/2,y:(extent.y1+extent.y2)/2},fields:[{name:'Note',type:'textarea',value:'Add context here',options:'',visible:true}]};
    graph.nodes.push(note);selected=note.id;
  }));
  function duplicateNode(node){mutate(()=>{const duplicate=clone(node);duplicate.id=id();duplicate.label=node.label+' (copy)';duplicate.position={x:node.position.x+100,y:node.position.y+100};duplicate.pinned=false;graph.nodes.push(duplicate);selected=duplicate.id;});}
  async function deleteItem(itemId){
    const node=graph.nodes.find(n=>n.id===itemId);
    if(!await confirmAction(node?'Remove this object and its connections? Undo can restore them.':'Remove this connection? Undo can restore it.'))return;
    mutate(()=>{graph.nodes=graph.nodes.filter(n=>n.id!==itemId);graph.edges=graph.edges.filter(e=>e.id!==itemId&&e.source!==itemId&&e.target!==itemId);graph.collapsed=graph.collapsed.filter(n=>n!==itemId);selected=null;});
  }
  function hideContext(){$('graph-context').hidden=true;}
  function showContext(event){
    const item=event.target, menu=$('graph-context');menu.replaceChildren();selected=item.id();renderDetails();
    const add=(label,action)=>{const b=button(menu,label,()=>{hideContext();action();});b.setAttribute('role','menuitem');};
    if(item.data('groupNode')){add('Expand / collapse group',()=>toggleGroup(item.id()));}
    else{
      add('Edit details',()=>{renderDetails();$('element-choice').focus();});
      if(item.isNode()){
        const node=graph.nodes.find(n=>n.id===item.id());
        add('Connect to another object',()=>{connectionStart=node.id;status('Choose the destination object on the canvas.');});
        add('Duplicate object',()=>duplicateNode(node));
        add(node.pinned?'Unpin object':'Pin object',()=>mutate(()=>node.pinned=!node.pinned));
        add(graph.collapsed.includes(node.id)?'Expand branch':'Collapse branch',()=>toggleBranch(node.id));
      }
      add('Remove from graph',()=>deleteItem(item.id()));
    }
    const rect=$('graph-canvas').getBoundingClientRect(),position=event.renderedPosition;
    menu.hidden=false;menu.style.left=Math.min(window.innerWidth-250,Math.max(0,rect.left+position.x))+'px';
    menu.style.top=Math.max(0,Math.min(window.innerHeight-menu.offsetHeight,rect.top+position.y))+'px';
    menu.querySelector('button')?.focus();
  }
  $('graph-canvas').addEventListener('contextmenu',event=>event.preventDefault());
  $('graph-context').addEventListener('keydown',event=>{
    const items=[...$('graph-context').querySelectorAll('button')],index=items.indexOf(document.activeElement);
    if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
      event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next]?.focus();
    }
  });
  document.addEventListener('pointerdown',event=>{if(!$('graph-context').contains(event.target))hideContext();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){hideContext();connectionStart=null;$('connection-line').style.visibility='hidden';}});
  function updateHandle(){
    const handle=$('connection-handle');
    if(!cy){handle.hidden=true;return;}
    const node=cy.getElementById(selected||'');
    handle.hidden=!node.length||!node.isNode()||node.data('groupNode')||!node.visible();
    if(handle.hidden)return;
    const p=node.renderedPosition();handle.style.left=(p.x+22*cy.zoom())+'px';handle.style.top=(p.y-22*cy.zoom()-16)+'px';
  }
  function finishConnection(source,target){connectionStart=null;if(source===target){status('Choose a different destination object.');return;}
    mutate(()=>{const edge={id:id(),source,target,label:'Related to',notes:'',status:'hypothesis',evidenceRefs:[],date:''};graph.edges.push(edge);selected=edge.id;});
  }
  const handle=$('connection-handle');
  handle.addEventListener('pointerdown',event=>{
    event.preventDefault();event.stopPropagation();const source=selected,node=cy.getElementById(source),rect=$('graph-canvas').getBoundingClientRect();
    if(!node.length)return;
    const start=node.renderedPosition(),line=$('connection-line').querySelector('line');let moved=false;
    $('connection-line').style.visibility='visible';line.setAttribute('x1',start.x);line.setAttribute('y1',start.y);line.setAttribute('x2',start.x);line.setAttribute('y2',start.y);
    handle.setPointerCapture(event.pointerId);
    const move=e=>{if(Math.hypot(e.clientX-event.clientX,e.clientY-event.clientY)>4)moved=true;line.setAttribute('x2',e.clientX-rect.left);line.setAttribute('y2',e.clientY-rect.top);};
    const end=e=>{
      handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',cancel);$('connection-line').style.visibility='hidden';
      if(!moved){connectionStart=source;status('Choose the destination object on the canvas.');return;}
      const x=e.clientX-rect.left,y=e.clientY-rect.top;
      const target=cy.nodes().filter(n=>n.id()!==source&&!n.data('groupNode')&&n.visible()).toArray().find(n=>{const p=n.renderedPosition();return Math.hypot(p.x-x,p.y-y)<=Math.max(24,n.renderedWidth()/2);});
      if(target)finishConnection(source,target.id());else status('Drop the connection handle onto another object.');
    };
    const cancel=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',cancel);$('connection-line').style.visibility='hidden';connectionStart=null;};
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',cancel);
  });
  handle.addEventListener('click',event=>event.preventDefault());
  function drawMap(){
    if(!cy||!graph)return;
    const canvas=$('mini-map'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
    const nodes=graph.nodes.filter(n=>cy.getElementById(n.id).visible());const byId=new Map(nodes.map(n=>[n.id,n]));mapProjection=tools.projection(nodes,canvas.width,canvas.height);
    const {scale,x,y}=mapProjection,pos=n=>({x:(n.position.x-x)*scale,y:(n.position.y-y)*scale});
    ctx.strokeStyle='#62758a';
    graph.edges.filter(e=>cy.getElementById(e.id).visible()).forEach(e=>{const a=byId.get(e.source),b=byId.get(e.target);if(!a||!b)return;const p=pos(a),q=pos(b);ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();});
    for(const node of nodes){const p=pos(node);ctx.fillStyle=graph.legend.find(t=>t.type===node.type)?.color||'#fff';ctx.beginPath();ctx.arc(p.x,p.y,3,0,2*Math.PI);ctx.fill();}
    const extent=cy.extent();ctx.strokeStyle='#ffffff';ctx.lineWidth=1;ctx.strokeRect((extent.x1-x)*scale,(extent.y1-y)*scale,extent.w*scale,extent.h*scale);
  }
  $('mini-map').addEventListener('click',event=>{
    if(!mapProjection)return;const canvas=$('mini-map'),rect=canvas.getBoundingClientRect(),{scale,x,y}=mapProjection;
    const px=(event.clientX-rect.left)*canvas.width/rect.width/scale+x,py=(event.clientY-rect.top)*canvas.height/rect.height/scale+y;
    cy.pan({x:cy.width()/2-px*cy.zoom(),y:cy.height()/2-py*cy.zoom()});
  });
  function evidenceControls(panel,item,isEdge){
    const refs=isEdge?(item.evidenceRefs||[]):[...new Set([item.source,...(item.sourceRefs||[])].filter(Boolean))];
    if(!isEdge&&!refs.length)return;
    el('h3',isEdge?'Supporting case findings':'Linked case findings',panel);
    refs.forEach(ref=>{const row=el('div',undefined,panel);row.className='evidence-ref';
      button(row,config.findings.find(f=>f.ref===ref)?.label||'Unavailable case finding',()=>previewEvidence(ref));
      if(isEdge)button(row,'Unlink finding',()=>mutate(()=>item.evidenceRefs=item.evidenceRefs.filter(r=>r!==ref)));
    });
    if(isEdge){
      if(!config.findings.length){el('p','Save findings to this case to attach supporting evidence.',panel);return;}
      const choice=input(panel,'Attach case finding','',()=>{},'select',['',...config.findings.filter(f=>!refs.includes(f.ref)).map(f=>f.ref)]);
      Array.from(choice.options).forEach(o=>o.textContent=o.value?config.findings.find(f=>f.ref===o.value).label:'Choose a finding');
      button(panel,'Attach evidence',()=>{if(choice.value)mutate(()=>{item.evidenceRefs=[...refs,choice.value];});});
    }
  }
  async function previewEvidence(ref){
    $('evidence-disclosure').open=true;
    const sequence=++previewRequest, panel=$('evidence-preview');panel.replaceChildren();el('h3','Evidence preview',panel);el('p','Loading…',panel);
    try{
      const response=await fetch(config.base+'/evidence?ref='+encodeURIComponent(ref),{cache:'no-store'});
      if(!response.ok)throw new Error(response.status===404?'This finding is no longer available in the case.':'Could not load this case finding.');
      const data=await response.json();if(sequence!==previewRequest)return;panel.replaceChildren();el('h3',data.label,panel);
      el('p',`Source: ${data.source||'Not recorded'} · Status: ${data.status}`,panel);
      el('pre',typeof data.value==='string'?data.value:JSON.stringify(data.value,null,2),panel);
      if(data.notes)el('p',data.notes,panel);
      for(const attachment of data.evidence){const link=el('a',undefined,panel);link.href=attachment.url;link.target='_blank';link.rel='noopener';const img=el('img',undefined,link);img.src=attachment.url;img.alt=attachment.caption||'Attached evidence';el('p',attachment.caption,panel);}
      const link=el('a','Open original case finding',panel);link.href=config.caseUrl+'#finding-'+ref;
    }catch(error){if(sequence===previewRequest){panel.replaceChildren();el('h3','Evidence preview',panel);el('p',error.message,panel);}}
  }
  function resetFilters(){
    Object.assign(filters,{query:'',type:'',status:'',from:'',to:'',includeUndated:true});syncFilters();
  }
  function syncFilters(){
    $('graph-search').value=filters.query||'';$('filter-status').value=filters.status||'';
    $('timeline-from').value=filters.from||'';$('timeline-to').value=filters.to||'';
    $('timeline-undated').checked=filters.includeUndated!==false;
  }
  for(const control of ['timeline-from','timeline-to','timeline-undated'])$(control).addEventListener('change',()=>{
    const from=$('timeline-from').value,to=$('timeline-to').value;
    if(from&&to&&from>to){status('Start date must be before the end date.');return;}
    Object.assign(filters,{from,to,includeUndated:$('timeline-undated').checked});applyFilters();
  });
  function renderMilestones(){
    const views=graph.views||[],saved=$('saved-view'),current=saved.value;
    saved.replaceChildren();let option=el('option','Choose a view',saved);option.value='';
    const report=$('report-view');report.replaceChildren();option=el('option','Full graph',report);option.value='';
    for(const view of views){for(const list of [saved,report]){option=el('option',view.name,list);option.value=view.id;}}
    saved.value=views.some(v=>v.id===current)?current:'';report.value=graph.report?.viewId||'';
    $('include-graph-report').checked=!!graph.report?.include;
    const snapshots=$('snapshot-choice'),previous=snapshots.value;snapshots.replaceChildren();
    option=el('option','Choose a snapshot',snapshots);option.value='';
    for(const snapshot of graph.snapshots||[]){option=el('option',`${snapshot.name} · ${new Date(snapshot.created_at).toLocaleString()}`,snapshots);option.value=snapshot.id;}
    snapshots.value=(graph.snapshots||[]).some(s=>s.id===previous)?previous:'';
  }
  function captureView(name,viewId=id()){
    return {id:viewId,name,filters:clone(filters),zoom:cy.zoom(),pan:{...cy.pan()},
      positions:Object.fromEntries(graph.nodes.map(n=>[n.id,{...n.position}])),collapsed:[...graph.collapsed],
      groupStates:Object.fromEntries(graph.groups.map(g=>[g.id,g.collapsed]))};
  }
  $('save-view').addEventListener('click',()=>{
    const name=$('view-name').value.trim();if(!name){status('Enter a view name.');return;}
    if(graph.views.length>=30){status('Maximum 30 views. Remove one before adding another.');return;}
    const view=captureView(name);mutate(()=>graph.views.push(view));$('saved-view').value=view.id;$('view-name').value='';
  });
  $('update-view').addEventListener('click',()=>{
    const view=graph.views.find(v=>v.id===$('saved-view').value);if(!view){status('Choose a saved view to update.');return;}
    const updated=captureView(view.name,view.id);mutate(()=>Object.assign(view,updated));
  });
  $('apply-view').addEventListener('click',()=>{
    const view=graph.views.find(v=>v.id===$('saved-view').value);if(!view){status('Choose a saved view.');return;}
    mutate(()=>{
      for(const node of graph.nodes)if(view.positions[node.id])node.position={...view.positions[node.id]};
      graph.collapsed=(view.collapsed||[]).filter(n=>graph.nodes.some(node=>node.id===n));
      for(const group of graph.groups)group.collapsed=!!view.groupStates[group.id];
      Object.assign(filters,{query:'',type:'',status:'',from:'',to:'',includeUndated:true},view.filters);syncFilters();selected=null;
    });
    cy.zoom(view.zoom);cy.pan(view.pan);drawMap();status(`View applied: ${view.name}`);
  });
  $('remove-view').addEventListener('click',async()=>{
    const key=$('saved-view').value;if(!key)return;
    if(!await confirmAction('Remove this saved view? The graph content stays available, and Undo can restore the view.'))return;
    mutate(()=>{graph.views=graph.views.filter(v=>v.id!==key);if(graph.report.viewId===key)graph.report.viewId='';});
  });
  async function ensureSaved(){
    if(saving){status('Wait for the current save, then try again.');return false;}
    if(recovery){status('Recover or discard the browser draft first.');return false;}
    if(dirty)await saveGraph(true);
    return !dirty&&!saving;
  }
  async function snapshotAction(action){
    if(!await ensureSaved())return;
    const key=$('snapshot-choice').value,name=$('snapshot-name').value.trim();
    if(action==='create'&&!name){status('Enter a snapshot name.');return;}
    if(action!=='create'&&!key){status('Choose a snapshot.');return;}
    if(action==='restore'&&!await confirmAction('Restore this milestone? A snapshot of the current saved graph will be kept automatically.'))return;
    if(action==='remove'&&!await confirmAction('Remove this saved milestone? Other milestones and the current graph will stay available.'))return;
    if(!await ensureSaved())return;
    clearTimeout(autosaveTimer);saving=true;$('graph-workspace').inert=true;
    const route=config.base+'/'+graph.id+'/snapshots'+(action==='create'?'':'/'+key+(action==='restore'?'/restore':''));
    status(action==='restore'?'Restoring milestone…':'Saving milestone changes…');
    try{
      const response=await fetch(route,{method:action==='remove'?'DELETE':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:graph.revision,name})});
      const result=await response.json();if(!response.ok)throw new Error(result.error||'Snapshot action failed.');
      Object.keys(graph).forEach(k=>delete graph[k]);Object.assign(graph,result.graph);
      graph.groups ||= [];graph.collapsed ||= [];graph.views ||= [];graph.report ||= {include:false,viewId:''};
      undo=[];redo=[];dirty=false;selected=null;
      if(action==='restore')resetFilters();$('graph-name').value=graph.name;
      renderCanvas();renderDetails();$('snapshot-name').value='';$('undo').disabled=true;$('redo').disabled=true;
      try{localStorage.removeItem(draftKey());}catch{/* Browser storage is optional. */}
      status(action==='restore'?'Milestone restored. The previous graph is saved as a snapshot.':'Milestone changes saved.');
    }catch(error){status(error.message);}finally{saving=false;$('graph-workspace').inert=false;}
  }
  $('create-snapshot').addEventListener('click',()=>snapshotAction('create'));
  $('restore-snapshot').addEventListener('click',()=>snapshotAction('restore'));
  $('remove-snapshot').addEventListener('click',()=>snapshotAction('remove'));
  $('open-report-options').addEventListener('click',()=>{$('report-panel').open=true;$('include-graph-report').focus();});
  $('include-graph-report').addEventListener('change',()=>mutate(()=>graph.report.include=$('include-graph-report').checked,false));
  $('report-view').addEventListener('change',()=>mutate(()=>graph.report.viewId=$('report-view').value,false));
  for(const [control,extension] of [['download-graph-pdf','pdf'],['download-graph-word','docx']])$(control).addEventListener('click',async()=>{
    if(!graph.report.include){status('Enable inclusion for this graph before downloading its case report.');return;}
    if(await ensureSaved())location.assign(config.caseUrl+'/report.'+extension);
  });
  const initial=new URLSearchParams(location.search).get('graph')||graphs[0]?.id;
  if(initial){$('graph-choice').value=initial;openGraph(initial);
    const focus=new URLSearchParams(location.search).get('focus');
    if(focus&&cy&&cy.getElementById(focus).length){selected=focus;cy.elements().unselect();const element=cy.getElementById(focus);element.select();cy.center(element);renderDetails();updateHandle();}
  }
})();
