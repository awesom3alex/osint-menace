// Cancelling changes only the job; polling updates results without navigating away.
document.addEventListener('submit',async event=>{
 const form=event.target;if(!form.matches('.cancel-search-form'))return;
 event.preventDefault();const button=form.querySelector('button');if(button.disabled)return;
 button.disabled=true;button.textContent='Cancelling…';
 try {const response=await fetch(form.action,{method:'POST'});const data=await response.json();if(!response.ok)throw Error(data.error||'Could not cancel search.');button.textContent=data.message;}
 catch(error){button.disabled=false;button.textContent='Retry cancellation';const message=document.createElement('p');message.setAttribute('role','alert');message.textContent=error.message;form.append(message);}
});
