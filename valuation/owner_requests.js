'use strict';
(()=>{
const base=location.pathname.startsWith('/owner')?'/owner':'';
const main=document.querySelector('#main-content');
let status='pending',person='',query='',generation=0;
function text(tag,value,parent){const x=document.createElement(tag);x.textContent=value;parent.append(x);return x}
async function request(path,data){const headers={'Content-Type':'application/json'};if(data){const state=await (await fetch(base+'/api/state',{cache:'no-store'})).json();headers['X-Workspace-Token']=state.token}const r=await fetch(base+path,{method:data?'POST':'GET',headers,body:data?JSON.stringify(data):undefined,cache:'no-store'});const body=await r.json();if(!r.ok)throw Error(body.error||'Unable to save decision');return body}
function button(label,handler,parent){const b=text('button',label,parent);b.type='button';b.onclick=async()=>{b.disabled=true;try{await handler()}catch(e){const p=text('p',e.message,parent);p.setAttribute('role','alert')}finally{b.disabled=false}};return b}
function date(value){const d=new Date(value);return Number.isNaN(d.valueOf())?value:d.toLocaleString()}
async function render(){
if(location.hash!=='#requests')return;
const current=++generation;
main.replaceChildren();
const style=text('style',`#main-content .request-heading{font-size:1.8rem;margin-bottom:.5rem} .request-tools{display:flex;gap:.75rem;align-items:end;flex-wrap:wrap;margin:1rem 0}.request-tools label{display:flex;flex-direction:column;gap:.25rem}.request-tools input{width:18rem}.request-tools select,.request-tools input{box-sizing:border-box;height:2rem;min-height:2rem;padding:0 .4rem;font:inherit;line-height:normal}.request-scroll{overflow-x:auto}.request-table{width:100%;border-collapse:collapse;font-size:.95rem}.request-table th,.request-table td{text-align:left;padding:.8rem .6rem;vertical-align:top;border-bottom:1px solid #dce4df}.request-table th{white-space:nowrap}.request-table td:first-child{overflow-wrap:anywhere;max-width:13rem}.request-table .request-book{min-width:13rem}.request-table small{display:block;color:#64716b;margin-top:.25rem}.request-table button{padding:.35rem .55rem;font-size:.88rem;min-height:2rem;margin:0 .25rem .3rem 0}.request-table select{width:12rem;max-width:100%;min-height:2rem}.request-status{text-transform:capitalize;font-weight:600}.request-overlap{color:#895c13!important}.request-detail td{background:#f7f9f7}.request-detail[hidden]{display:none}.request-table .request-history{display:inline-block;margin-top:.4rem;color:#245e4c;text-decoration:underline;white-space:nowrap}.request-actions{min-width:10rem}.request-actions select{width:10rem}`,main);
text('h1','Book requests',main).className='request-heading';
text('p','Approval reserves a copy. Mark collected only after the book has left the library.',main);
try{
const rows=await request('/api/family-requests');if(location.hash!=='#requests'||current!==generation)return;
const tools=text('div','',main);tools.className='request-tools';
const stateLabel=text('label','Status',tools),states=text('select','',stateLabel);
for(const s of ['pending','approved','collected','declined','all']){const o=text('option',s[0].toUpperCase()+s.slice(1),states);o.value=s}states.value=status;
const whoLabel=text('label','Requested by',tools),who=text('select','',whoLabel);text('option','Everyone',who).value='';for(const email of [...new Set(rows.map(r=>r.email))].sort())text('option',email,who).value=email;who.value=person;
const searchLabel=text('label','Search books or messages',tools),search=text('input','',searchLabel);search.type='search';search.value=query;search.placeholder='Title, author or message';
button('Refresh',render,tools);
const count=text('p','',main);count.setAttribute('aria-live','polite');const wrap=text('div','',main);wrap.className='request-scroll';
function draw(){
wrap.replaceChildren();const entries=rows.flatMap(row=>row.items.map(item=>({row,item}))).filter(({row,item})=>(status==='all'||item.decision.state===status)&&(!person||row.email===person)&&[item.title,item.author,row.payload.message||''].join(' ').toLowerCase().includes(query.toLowerCase()));
count.textContent=entries.length+' requested '+(entries.length===1?'book':'books');if(!entries.length){text('p',rows.length?'No requests match these filters.':'No requests submitted yet.',wrap);return}
const table=text('table','',wrap);table.className='request-table';const head=text('tr','',text('thead','',table));for(const label of ['Requested by','Book','Estimate','Location','Status','Assigned copy','Actions']){const th=text('th',label,head);th.scope='col'}const body=text('tbody','',table);
for(const {row,item} of entries){
const tr=text('tr','',body);text('td',row.email,tr);
const book=text('td','',tr);book.className='request-book';const a=text('a',item.title,book);a.href='#book/'+encodeURIComponent(item.catalog_item_id||'');text('small',item.author,book);if(item.other_requesters.length)text('small','Also requested by '+item.other_requesters.join(', '),book).className='request-overlap';
text('td',item.value,tr);text('td',item.location||'Not recorded',tr);text('td',item.decision.state,tr).className='request-status';
const copy=text('td','',tr),select=text('select','',copy);select.setAttribute('aria-label','Assigned copy for '+item.title);text('option','Choose copy',select).value='';
for(const c of item.copies){const opt=text('option',c.label+(c.assignment?' · '+c.assignment.state:''),select);opt.value=c.id;opt.disabled=!!c.assignment&&!(c.assignment.submission===row.id&&c.assignment.reference===item.reference);if(item.decision.slot===c.id)opt.selected=true}
const actions=text('td','',tr);actions.className='request-actions';
const change=async(state)=>{if(state==='collected'&&!confirm('Confirm that this assigned physical book has actually been collected and has left your library?'))return;await request('/api/family-requests',{submission:row.id,reference:item.reference,state,version:item.decision.version,slot:select.value});if(state==='collected'){location.reload();return}await render()};
if(item.decision.state==='collected'){select.disabled=true;text('small','Collection recorded',actions)}else{
const menu=text('select','',actions);menu.setAttribute('aria-label','Action for '+item.title);text('option','Choose action',menu).value='';
let approve;
if(item.decision.state!=='approved'){approve=text('option','Approve',menu);approve.value='approved';approve.disabled=!select.value;select.onchange=()=>{approve.disabled=!select.value}}
if(item.decision.state!=='pending')text('option','Return to pending',menu).value='pending';
if(item.decision.state!=='declined')text('option','Decline',menu).value='declined';
if(item.decision.state==='approved'){select.disabled=true;text('option','Mark collected',menu).value='collected'}
menu.onchange=async()=>{const state=menu.value;if(!state)return;menu.disabled=true;try{await change(state)}catch(e){text('p',e.message,actions).setAttribute('role','alert')}finally{menu.value='';menu.disabled=false}};
}
const detailRow=text('tr','',body);detailRow.className='request-detail';detailRow.hidden=true;detailRow.id='request-history-'+row.id+'-'+item.reference;
const history=text('a','Message history',actions);history.className='request-history';history.href='#'+detailRow.id;history.setAttribute('aria-expanded','false');history.setAttribute('aria-controls',detailRow.id);history.onclick=(e)=>{e.preventDefault();detailRow.hidden=!detailRow.hidden;history.setAttribute('aria-expanded',String(!detailRow.hidden))};
const cell=text('td','',detailRow);cell.colSpan=7;text('p','Submitted '+date(row.created),cell);text('p',row.payload.message||'No message included.',cell);
if(item.history&&item.history.length){for(const event of item.history)text('p',date(event.created)+' · '+event.state+' · '+event.actor,cell)}else text('p','No decisions recorded yet.',cell);
}
}
states.onchange=()=>{status=states.value;draw()};who.onchange=()=>{person=who.value;draw()};search.oninput=()=>{query=search.value;draw()};draw();
}catch(e){text('p','Unable to load requests: '+e.message,main).setAttribute('role','alert')}
}
window.addEventListener('owner-requests',render);if(location.hash==='#requests')render();
})();
