'use strict';
const $=id=>document.getElementById(id);
async function refresh(){const r=await fetch('/api/students');const data=await r.json();if(!r.ok)throw Error(data.error);$('students').replaceChildren();for(const s of data.students){const li=document.createElement('li');li.textContent=s.name;$('students').append(li);}}
$('student-form').onsubmit=async e=>{e.preventDefault();try{const r=await fetch('/api/students',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('student-name').value,password:$('student-password').value,reset:$('reset-password').checked})});const data=await r.json();if(!r.ok)throw Error(data.error);$('student-password').value='';$('result').textContent='Account updated.';await refresh();}catch(e){$('result').textContent=e.message;}};
refresh().catch(e=>$('result').textContent=e.message);
