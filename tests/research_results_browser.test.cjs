// Three browser-behaviour tests; no network or case files are used.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('osint/static/research-results.js','utf8');
function fixture(reply){
 const handlers={},previewHandlers={},checks=[{value:'a',checked:true},{value:'b',checked:true}],singles=[{name:'single_entry',value:'a'},{name:'single_entry',value:'b'}],batch={name:'action',value:'case'},destination={value:'case-1',options:[{value:'case-1'}],selectedOptions:[{textContent:'Test'}],addEventListener(){},removeAttribute(){},setAttribute(){},focus(){}},status={textContent:''},all={addEventListener(){}};
 checks.forEach(input=>input.addEventListener=()=>{});
 const form={action:{toString(){return '[object RadioNodeList]';}},dataset:{savedUrl:'/research/results/fixture/saved'},getAttribute(name){assert.equal(name,'action');return '/research/results/fixture/action';},addEventListener(type,callback){handlers[type]=callback;},querySelectorAll(selector){return selector==='input[name="selected"]'?checks:selector==='[data-requires-selection]'?[batch]:singles;}};
 const editors={children:[],replaceChildren(){this.children=[];},append(fragment){this.children.push(fragment.querySelector('fieldset'));},querySelectorAll(){return this.children;}};
 const dialog={showModal(){this.open=true;},close(){this.open=false;},addEventListener(){}};
 const template={content:{cloneNode(){const fields={legend:{textContent:''},'.research-preview-source':{},'.research-preview-original':{},'[name="review_title"]':{value:''},'[name="review_type"]':{value:'Other'},'[name="review_tags"]':{value:''},'[name="review_notes"]':{value:''}};const fieldset={dataset:{},querySelector:selector=>fields[selector]};return {querySelector:()=>fieldset};}}};
 const nodes={'research-results-form':form,'select-visible-results':all,'add-selected-to-case':batch,'research-destination-case':destination,'research-action-status':status,'research-save-preview':dialog,'research-preview-form':{addEventListener(type,callback){previewHandlers[type]=callback;}},'research-preview-editors':editors,'research-preview-status':{},'research-preview-confirm':{},'research-preview-cancel':{addEventListener(){}},'research-preview-data':{textContent:JSON.stringify({a:{title:'A',summary:'Original A'},b:{title:'B',summary:'Original B'}})},'research-preview-destination':{},'research-preview-editor':template};
 const calls=[];
 class FormData {constructor(){this.fields=[];}append(name,value){this.fields.push([name,value]);}set(name,value){this.fields=this.fields.filter(row=>row[0]!==name);this.append(name,value);}}
 vm.runInNewContext(source,{document:{getElementById:id=>nodes[id]},sessionStorage:{getItem(){return null;},setItem(){}},location:{href:'http://localhost/research/results/fixture'},URL,FormData,fetch:async(url,options)=>{if(options.method!=='POST')return response(true,{saved_ids:[]});calls.push({url,options});return reply;},Map,Set,Error,Boolean});
 return {checks,singles,batch,destination,status,calls,submit:async(button)=>{await new Promise(setImmediate);let prevented=false;await handlers.submit({submitter:button,preventDefault(){prevented=true;}});assert.ok(prevented);assert.equal(dialog.open,true);await previewHandlers.submit({preventDefault(){}});}};
}

function response(ok,data){return {ok,headers:{get(){return 'application/json';}},json:async()=>data};}

test('single Add To Case uses the real form URL despite named action buttons and stays in place',async()=>{
 const f=fixture(response(true,{selected_ids:['a'],message:'Added 1 result to Test.'}));
 await f.submit(f.singles[0]);
 assert.equal(f.calls[0].url,'/research/results/fixture/action');
 assert.equal(f.calls[0].options.headers.Accept,'application/json');
 assert.deepEqual(f.calls[0].options.body.fields.filter(row=>row[0]!=='review_edits'),[['single_entry','a']]);
 assert.equal(f.status.textContent,'Added 1 result to Test.');
 assert.equal(f.singles[0].textContent,'Added To Case');
 assert.equal(f.singles[0].disabled,true);
 assert.equal(f.checks[1].checked,true);
 assert.equal(f.destination.disabled,false);
});

test('batch Add To Case clears saved selections and restores controls without navigation',async()=>{
 const f=fixture(response(true,{selected_ids:['a','b'],message:'Added 2 results to Test.'}));
 await f.submit(f.batch);
 assert.equal(f.calls[0].url,'/research/results/fixture/action');
 assert.deepEqual(f.calls[0].options.body.fields.filter(row=>row[0]!=='review_edits'),[['action','case']]);
 assert.ok(f.checks.every(input=>!input.checked&&!input.disabled));
 assert.ok(f.singles.every(button=>button.textContent==='Added To Case'));
 assert.equal(f.batch.textContent,'Add Selected To Case (0)');
 assert.equal(f.status.textContent,'Added 2 results to Test.');
});

test('failed saves show the server error, preserve selections, and allow a retry',async()=>{
 const f=fixture(response(false,{error:'These results have already been saved to this case.'}));
 await f.submit(f.batch);
 assert.equal(f.status.textContent,'These results have already been saved to this case.');
 assert.ok(f.checks.every(input=>input.checked&&!input.disabled));
 assert.ok(f.singles.every(button=>!button.disabled));
 assert.equal(f.batch.disabled,false);
 assert.equal(f.destination.disabled,false);
});
