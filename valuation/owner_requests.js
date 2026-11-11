'use strict';
(()=>{
const base=location.pathname.startsWith('/owner')?'/owner':'';
const main=document.querySelector('#main-content');
let status='pending',person='',query='',generation=0,sortKey='submitted',sortDirection=-1,editing=false,lastRows='',polling=false;
function text(tag,value,parent){const x=document.createElement(tag);x.textContent=value;parent.append(x);return x}
async function request(path,data){const headers={'Content-Type':'application/json'};if(data){const state=await (await fetch(base+'/api/state',{cache:'no-store'})).json();headers['X-Workspace-Token']=state.token}const r=await fetch(base+path,{method:data?'POST':'GET',headers,body:data?JSON.stringify(data):undefined,cache:'no-store'});const body=await r.json();if(!r.ok)throw Error(body.error||'Unable to save decision');return body}
function button(label,handler,parent){const b=text('button',label,parent);b.type='button';b.onclick=async()=>{b.disabled=true;try{await handler()}catch(e){const p=text('p',e.message,parent);p.setAttribute('role','alert')}finally{b.disabled=false}};return b}
function displayState(value){return value==='collected'?'transferred':value}
function date(value){const d=new Date(value);return Number.isNaN(d.valueOf())?value:d.toLocaleString()}
async function render(){
if(location.hash!=='#requests'||editing)return;
const current=++generation;
main.replaceChildren();
const style=text('style',`#main-content .request-heading{font-size:1.8rem;margin-bottom:.5rem} .request-tools{display:flex;gap:.75rem;align-items:end;flex-wrap:wrap;margin:1rem 0}.request-tools [hidden]{display:none}.request-tools label{display:flex;flex-direction:column;gap:.25rem}.request-tools input{width:18rem}.request-tools button{height:2rem;min-height:2rem;padding:0 .6rem}.request-tools select,.request-tools input{box-sizing:border-box;height:2rem;min-height:2rem;padding:0 .4rem;font:inherit;line-height:normal}.request-scroll{overflow-x:auto}.request-table{width:100%;border-collapse:collapse;font-size:.95rem}.request-table th,.request-table td{text-align:left;padding:.8rem .6rem;vertical-align:top;border-bottom:1px solid #dce4df}.request-table th{white-space:nowrap}.request-table td:first-child{overflow-wrap:anywhere;max-width:13rem}.request-table .request-book{min-width:13rem}.request-table small{display:block;color:#64716b;margin-top:.25rem}.request-table button{padding:.35rem .55rem;font-size:.88rem;min-height:2rem;margin:0 .25rem .3rem 0}.request-table th button{border:0;background:transparent;padding:0;text-align:left;font:inherit;font-weight:700;white-space:nowrap}.request-table select{box-sizing:border-box;width:12rem;max-width:100%;height:2rem;min-height:2rem;margin:0;padding:0 .4rem;font:inherit;vertical-align:top}.request-status{text-transform:capitalize;font-weight:600}.request-overlap{color:#895c13!important}.request-detail td{background:#f7f9f7}.request-detail[hidden]{display:none}.request-detail textarea{display:block;box-sizing:border-box;margin:.4rem 0 .85rem}.request-detail form>button{margin-right:.6rem;margin-bottom:.25rem}.request-table .request-history{display:inline-block;margin-top:0;line-height:2rem;color:#245e4c;text-decoration:underline;white-space:nowrap}.request-actions{min-width:10rem}.request-actions select{width:10rem}.request-tools select,.request-table select{appearance:none;-webkit-appearance:none;padding-right:2rem;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' fill='none' stroke='%2344554c' stroke-width='1.5'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right .65rem center;background-size:.75rem .5rem}@media(forced-colors:active){.request-tools select,.request-table select{appearance:auto;-webkit-appearance:auto;background-image:none}}`,main);
text('h1','Book requests',main).className='request-heading';
text('p','Choose an action, assign a copy when approving, and save your decision with an optional message.',main);
try{
const rows=await request('/api/family-requests');lastRows=JSON.stringify(rows);if(location.hash!=='#requests'||current!==generation)return;
const tools=text('div','',main);tools.className='request-tools';
const stateLabel=text('label','Status',tools),states=text('select','',stateLabel);
for(const s of ['pending','approved','transferred','declined','all']){const o=text('option',s[0].toUpperCase()+s.slice(1),states);o.value=s}states.value=status;
const whoLabel=text('label','Requested by',tools),who=text('select','',whoLabel);text('option','Everyone',who).value='';for(const email of [...new Set(rows.map(r=>r.email))].sort())text('option',email,who).value=email;who.value=person;
const searchLabel=text('label','Search books or messages',tools),search=text('input','',searchLabel);search.type='search';search.value=query;search.placeholder='Title, author or message';
button('Refresh',render,tools);
const count=text('p','',main);count.setAttribute('aria-live','polite');const wrap=text('div','',main);wrap.className='request-scroll';
function draw(){
wrap.replaceChildren();const entries=rows.flatMap(row=>row.items.map(item=>({row,item}))).filter(({row,item})=>(status==='all'||displayState(item.decision.state)===status)&&(!person||row.email===person)&&[item.title,item.author,row.payload.message||''].join(' ').toLowerCase().includes(query.toLowerCase()));
count.textContent=entries.length+' requested '+(entries.length===1?'book':'books');if(!entries.length){text('p',rows.length?'No requests match these filters.':'No requests submitted yet.',wrap);return}
const sortValue=e=>({submitted:e.row.created,person:e.row.email,book:e.item.title,estimate:e.item.value,location:e.item.location,status:displayState(e.item.decision.state)})[sortKey];
entries.sort((a,b)=>{let av=sortValue(a),bv=sortValue(b);if(sortKey==='estimate'){const n=v=>{const m=String(v).match(/(?:\$|USD\s*)([\d,]+(?:\.\d+)?)/);return m?Number(m[1].replaceAll(',','')):null};av=n(av);bv=n(bv);if(av===null||bv===null)return av===bv?0:av===null?1:-1;return sortDirection*(av-bv)}return sortDirection*String(av||'').localeCompare(String(bv||''),undefined,{numeric:true,sensitivity:'base'})||a.row.id.localeCompare(b.row.id)||a.item.reference.localeCompare(b.item.reference)});
const table=text('table','',wrap);table.className='request-table';const head=text('tr','',text('thead','',table));for(const [label,key] of [['Submitted','submitted'],['Requested by','person'],['Book','book'],['Estimate','estimate'],['Location','location'],['Status','status'],['Action',''],['Assigned copy',''],['','']]){const th=text('th','',head);th.scope='col';if(key){th.setAttribute('aria-sort',key===sortKey?(sortDirection===1?'ascending':'descending'):'none');button(label+(sortKey===key?(sortDirection===1?' ↑':' ↓'):''),()=>{if(editing)return;sortDirection=sortKey===key?-sortDirection:key==='submitted'?-1:1;sortKey=key;draw()},th)}else th.textContent=label}const body=text('tbody','',table);
for(const {row,item} of entries){
const tr=text('tr','',body);text('td',date(row.created),tr);text('td',row.email,tr);
const book=text('td','',tr);book.className='request-book';const a=text('a',item.title,book);a.href='#book/'+encodeURIComponent(item.catalog_item_id||'');text('small',item.author,book);if(item.other_requesters.length)text('small','Also requested by '+item.other_requesters.join(', '),book).className='request-overlap';
text('td',item.value,tr);text('td',item.location||'Not recorded',tr);text('td',displayState(item.decision.state),tr).className='request-status';
const actions=text('td','',tr);actions.className='request-actions';
const copy=text('td','',tr),select=text('select','',copy);select.setAttribute('aria-label','Assigned copy for '+item.title);text('option','Choose copy',select).value='';
for(const c of item.copies){const opt=text('option',c.label+(c.assignment?' · '+displayState(c.assignment.state):''),select);opt.value=c.id;opt.disabled=!!c.assignment&&!(c.assignment.submission===row.id&&c.assignment.reference===item.reference);if(item.decision.slot===c.id)opt.selected=true}
const historyCell=text('td','',tr);
const change=async(state,extra={})=>{if(state==='transferred'&&!confirm('Confirm that this assigned copy has permanently left your library as a '+extra.transfer_kind+'?'))return;await request('/api/family-requests',{submission:row.id,reference:item.reference,state,version:item.decision.version,slot:select.value,...extra});editing=false;if(state==='transferred'||extra.correct_transfer){location.reload();return}await render()};
if(['collected','transferred'].includes(item.decision.state)){select.disabled=true;text('small','Transferred'+(item.decision.transfer?' · '+item.decision.transfer.kind:''),actions);button('Correct transfer',showCorrection,actions)}else{
const menu=text('select','',actions);menu.setAttribute('aria-label','Action for '+item.title);text('option','Choose action',menu).value='';
select.disabled=true;
if(item.decision.state!=='approved')text('option','Approve',menu).value='approved';
const hint=text('small','',copy);hint.setAttribute('aria-live','polite');
select.onchange=()=>{hint.textContent=select.value?'Copy selected. Save decision to confirm.':'Choose a copy before saving.'};
if(item.decision.state!=='pending')text('option','Return to pending',menu).value='pending';
if(item.decision.state!=='declined')text('option','Decline',menu).value='declined';
if(item.decision.state==='approved'){select.disabled=true;text('option','Mark transferred',menu).value='transferred'}
text('option','Add message',menu).value='message';
menu.onchange=()=>{const state=menu.value;select.disabled=state!=='approved';hint.textContent=state==='approved'?'Choose a copy, then Save decision.':'';if(!state){editing=false;transferRow.hidden=true;return}editing=true;if(state==='transferred'){showTransfer();return}showDecision(state==='message'?item.decision.state:state)};
}
const transferRow=text('tr','',body);transferRow.className='request-detail';transferRow.hidden=true;
function showDecision(state){
transferRow.hidden=false;transferRow.replaceChildren();const td=text('td','',transferRow);td.colSpan=9;const form=text('form','',td);
text('p',state==='approved'?'Approve and reserve the selected copy.':'Save as '+displayState(state)+'.',form);
const notes=text('textarea','',text('label','Message to requester (optional)',form));notes.maxLength=2000;notes.setAttribute('aria-label','Message to requester');notes.placeholder='For example: I can bring this book next weekend.';
const save=text('button','Save decision',form);save.type='submit';button('Cancel',()=>{editing=false;draw()},form);
form.onsubmit=async(e)=>{e.preventDefault();if(state==='approved'&&!select.value){text('p','Choose a physical copy before saving.',td).setAttribute('role','alert');return}save.disabled=true;try{await change(state,{message:notes.value})}catch(err){text('p',err.message,td).setAttribute('role','alert')}finally{save.disabled=false}};
}
function showCorrection(){
editing=true;
transferRow.hidden=false;transferRow.replaceChildren();const td=text('td','',transferRow);td.colSpan=9;
text('p','Correct a transfer recorded by mistake. This restores the copy to the library and returns the request to Pending. The original transfer remains in history. If Libib was already changed, restore that copy there separately.',td);
const form=text('form','',td),label=text('label','Correction reason',form),reason=text('input','',label);reason.required=true;reason.maxLength=1000;reason.placeholder='For example: Test transfer; book is still here';
const save=text('button','Restore copy and return to Pending',form);save.type='submit';button('Cancel',()=>{editing=false;transferRow.hidden=true;draw()},form);
form.onsubmit=async(e)=>{e.preventDefault();if(!form.reportValidity())return;save.disabled=true;try{await change('pending',{correct_transfer:true,correction_reason:reason.value})}catch(err){text('p',err.message,td).setAttribute('role','alert')}finally{save.disabled=false}};reason.focus();
}
function showTransfer(){
transferRow.hidden=false;transferRow.replaceChildren();const td=text('td','',transferRow);td.colSpan=9;
text('p','Record permanent handover of the assigned copy. This removes it from the active collection and preserves its history.',td);
const form=text('form','',td);form.className='request-tools';
const label=text('label','Transfer type',form),kind=text('select','',label);kind.required=true;kind.setAttribute('aria-label','Transfer type');text('option','Choose Gift or Sale',kind).value='';text('option','Gift',kind).value='gift';text('option','Sale',kind).value='sale';
const amountLabel=text('label','Amount received ($, optional)',form),amount=text('input','',amountLabel);amount.type='number';amount.min='0';amount.max='999999999.99';amount.step='.01';amountLabel.hidden=true;amount.disabled=true;
kind.onchange=()=>{amountLabel.hidden=kind.value!=='sale';amount.disabled=kind.value!=='sale';if(kind.value!=='sale')amount.value=''};
const notes=text('textarea','',text('label','Message to requester (optional)',form));notes.maxLength=2000;notes.setAttribute('aria-label','Message to requester');
const save=text('button','Save transfer',form);save.type='submit';
button('Cancel',()=>{editing=false;transferRow.hidden=true;draw()},form);
form.onsubmit=async(e)=>{e.preventDefault();if(!form.reportValidity())return;save.disabled=true;try{await change('transferred',{transfer_kind:kind.value,sale_amount:amount.value,message:notes.value})}catch(err){text('p',err.message,td).setAttribute('role','alert')}finally{save.disabled=false}};
kind.focus();
}
const detailRow=text('tr','',body);detailRow.className='request-detail';detailRow.hidden=true;detailRow.id='request-history-'+row.id+'-'+item.reference;
const history=text('a','Message history',historyCell);history.className='request-history';history.href='#'+detailRow.id;history.setAttribute('aria-expanded','false');history.setAttribute('aria-controls',detailRow.id);history.onclick=(e)=>{e.preventDefault();detailRow.hidden=!detailRow.hidden;history.setAttribute('aria-expanded',String(!detailRow.hidden))};
const cell=text('td','',detailRow);cell.colSpan=9;text('p','Submitted '+date(row.created),cell);text('p',row.payload.message||'No message included.',cell);
if(['collected','transferred'].includes(item.decision.state))text('p','Libib update required: remove only this transferred copy from its original collection. Libib has not been updated automatically.',cell);
if(item.history&&item.history.length){for(const event of item.history)text('p',date(event.created)+' · '+displayState(event.state)+' · '+event.actor+(event.message?' · Message: '+event.message:'')+(event.correction_reason?' · Transfer corrected: '+event.correction_reason:'')+(event.transfer?' · '+event.transfer.kind+(event.transfer.amount!==null?' · $'+event.transfer.amount:''):''),cell)}else text('p','No decisions recorded yet.',cell);
}
}
states.onchange=()=>{if(editing){states.value=status;return}status=states.value;draw()};who.onchange=()=>{if(editing){who.value=person;return}person=who.value;draw()};search.oninput=()=>{if(editing){search.value=query;return}query=search.value;draw()};draw();
}catch(e){text('p','Unable to load requests: '+e.message,main).setAttribute('role','alert')}
}
async function refreshRequests(){if(location.hash!=='#requests'||editing||polling||document.hidden||(main.contains(document.activeElement)&&document.activeElement.matches('input,textarea,select')))return;polling=true;try{const rows=await request('/api/family-requests');if(!editing&&JSON.stringify(rows)!==lastRows)await render()}catch(e){}finally{polling=false}}
setInterval(refreshRequests,15000);window.addEventListener('focus',refreshRequests);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshRequests()});
window.addEventListener('hashchange',()=>{if(location.hash!=='#requests')editing=false});
window.addEventListener('owner-requests',render);if(location.hash==='#requests')render();
})();
