// Render upstream data as text nodes, never executable HTML.
(() => {
  const label = key => {
    const names = {e164:'International number (E.164)',geo:'Numbering region',region:'Country / region',valid:'Valid number',possible:'Possible number',spam:'Listed as spam',operators_in_country:'Operators in country',formatted:'Number formats',timezones:'Time zones',line_type:'Line type',rfc3966:'Telephone link format',mcc:'MCC',mnc:'MNC'};
    return names[key] || String(key).replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' ').replace(/^./, c => c.toUpperCase());
  };
  const scalar = value => value === null ? 'Not provided' : typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value).replace(/^[A-Z]+(?:_[A-Z]+)+$/, s => s.toLowerCase().replace(/_/g,' ').replace(/^./, c=>c.toUpperCase()));
  const node = (tag, text, className) => {const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if(className) element.className=className; return element;};
  const simple = value => value === null || typeof value !== 'object';
  function render(value, depth=0) {
    if (simple(value)) return node('p', scalar(value));
    if (depth > 12) return node('p', 'Further nested details are available in raw output.');
    if (Array.isArray(value)) {
      if (!value.length) return node('p', 'No results returned.', 'output-empty');
      if (value.every(simple)) {
        const list = node('ul'); value.slice(0,500).forEach(item=>list.append(node('li',scalar(item)))); return list;
      }
      if (value.every(item => item && !Array.isArray(item) && typeof item==='object' && Object.values(item).every(simple))) {
        const columns = [...new Set(value.flatMap(item=>Object.keys(item)))];
        const wrap=node('div',undefined,'output-table-wrap'),table=node('table',undefined,'output-table'),head=node('thead'),row=node('tr');
        columns.forEach(key=>row.append(node('th',label(key))));head.append(row);table.append(head);
        const body=node('tbody');value.slice(0,500).forEach(item=>{const tr=node('tr');columns.forEach(key=>tr.append(node('td',key in item ? scalar(item[key]) : '—')));body.append(tr);});table.append(body);wrap.append(table);return wrap;
      }
      const container=node('div',undefined,'output-records');
      value.slice(0,100).forEach((item,index)=>{const card=node('section',undefined,'output-record');card.append(node('h3',value.length===1?'Summary':`Result ${index+1}`),render(item,depth+1));container.append(card);});return container;
    }
    const container=node('div'), facts=node('dl',undefined,'output-facts');
    Object.entries(value).filter(([,v])=>simple(v)).forEach(([key,item])=>{const pair=node('div');pair.append(node('dt',label(key)),node('dd',scalar(item)));facts.append(pair);});
    if(facts.childElementCount)container.append(facts);
    Object.entries(value).filter(([,v])=>!simple(v)).forEach(([key,item])=>{
      const detail=node('details',undefined,'output-group');detail.open=!Array.isArray(item) || item.length<=5;
      detail.append(node('summary',`${label(key)}${Array.isArray(item)?` (${item.length})`:''}`));
      if(key==='operators_in_country')detail.append(node('p',"Country-wide operator directory. These are not confirmed carriers for this number.",'case-capture-note'));
      detail.append(render(item,depth+1));container.append(detail);
    });return container;
  }
  function parse(text) {
    try {return {ok:true,value:JSON.parse(text)};} catch (_) {}
    const lines=text.trim().split('\n').filter(line=>line.trim());
    if(lines.length>1)try{return {ok:true,value:lines.map(line=>JSON.parse(line))};}catch(_){}
    return {ok:false};
  }
  window.showReadableOutput = text => {
    const destination=document.getElementById('readable-output'),raw=document.getElementById('addon-output'),details=document.getElementById('raw-output');
    destination.replaceChildren();raw.textContent=text || 'Tool returned no output.';
    const parsed=parse(text);
    destination.hidden=!parsed.ok;details.open=!parsed.ok;
    document.getElementById('raw-output-label').textContent=parsed.ok?'View raw output':'Tool output';
    if(parsed.ok){destination.append(render(parsed.value));destination.append(node('p','Large lists show up to 500 rows; up to 100 result groups are displayed. Full captured output is available below.','case-capture-note'));}
  };
})();
