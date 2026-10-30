(() => {
 document.querySelectorAll('.github-run').forEach(form => form.addEventListener('submit',async event => {
  event.preventDefault();const button=form.querySelector('button'),message=form.querySelector('[role="status"]');button.disabled=true;
  message.textContent='Starting selected tool…';
  try {
   const tool=form.dataset.tool,target=form.elements.target.value.trim(),kind=tool==='unfurl'?'url':'domain';
   const response=await fetch('/api/github-tools/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool,target,kind,case_id:form.dataset.case})});
   const result=await response.json();if(!response.ok)throw Error(result.error||'Tool could not start.');location.assign(result.url);
  } catch(error) {message.textContent=error.message;button.disabled=false;}
 }));
})();
