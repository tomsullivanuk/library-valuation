'use strict';
let me, busy=false, key=null, mode='browse', messageDraft='';
const cards=[...document.querySelectorAll('article')],panel=document.querySelector('#panel'),status=document.querySelector('#saved'),search=document.querySelector('#search');
let selectedTopic='',topicData=null;
let searchHits=null,searchVersion=0,searchTimer,requestSort='submitted',requestDirection=-1,polling=false;
const feedback=document.createElement('p');feedback.id='search-feedback';feedback.setAttribute('role','status');search.parentElement.append(feedback);
const titles=new Map(cards.map(c=>[c.dataset.ref,c.querySelector('h2').textContent]));
const normalize=s=>String(s||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[’']/g,'').replace(/[^\p{L}\p{N}]+/gu,' ').trim();
const indexes=new Map(cards.map(c=>[c,normalize(c.textContent)]));
function matches(card){const q=normalize(search.value);if(!q)return true;const hay=indexes.get(card);return q.split(/\s+/).every(word=>hay.includes(word))||hay.replace(/\s/g,'').includes(q.replace(/\s/g,''))}
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json','X-Family-Request':'1'}:{},body:data?JSON.stringify(data):undefined});const value=await r.json();if(!r.ok)throw Error(value.error||'Request failed');return value}
function el(tag,text,parent){const e=document.createElement(tag);e.textContent=text;if(parent)parent.append(e);return e}
function button(text,fn,parent){const b=el('button',text,parent);b.type='button';b.onclick=fn;return b}
function when(value){const d=new Date(value);return isNaN(d)?value:d.toLocaleString()}
function update(){feedback.hidden=mode!=='browse';for(const c of cards){const selected=me.draft.books.includes(c.dataset.ref);c.querySelector('.choose').textContent=selected?'Remove from My List':'Add to My List';c.querySelector('.choose').disabled=busy;c.hidden=mode!=='browse'||(selectedTopic&&!topicData?.books[c.dataset.ref]?.includes(selectedTopic))||(searchHits? !searchHits.some(r=>r.reference===c.dataset.ref):!matches(c))}document.querySelector('#count').textContent=mode==='browse'?cards.filter(c=>!c.hidden).length+(search.value.trim()?' search results':' catalog records'):me.draft.books.length+' books awaiting submission';document.querySelector('#empty').hidden=mode!=='browse'||cards.some(c=>!c.hidden);document.querySelector('#mine').textContent='My List ('+me.draft.books.length+')';document.querySelector('#browse').setAttribute('aria-pressed',String(mode==='browse'));document.querySelector('#mine').setAttribute('aria-pressed',String(mode==='mine'));document.querySelector('#search-tools').hidden=mode!=='browse';const topicPanel=document.querySelector('#browse-topics');if(topicPanel)topicPanel.hidden=mode!=='browse';document.querySelector('#browse-intro').hidden=mode==='mine';document.querySelector('.updated').hidden=mode==='mine';status.hidden=mode==='mine'&&!status.dataset.notice}
async function runSearch(version,query){
try{const result=await api('/api/search',{query});if(version!==searchVersion||query!==search.value.trim())return;searchHits=result.results;const main=cards[0]?.parentElement;if(main){for(const r of result.results){const card=cards.find(c=>c.dataset.ref===r.reference);if(!card)continue;let hint=card.querySelector('.search-match');if(!hint){hint=document.createElement('p');hint.className='muted search-match';card.append(hint)}hint.textContent=r.reason+(r.excerpt?' · '+r.excerpt:'');main.append(card)}}feedback.textContent=result.notice||(result.engine==='hybrid'?'Results ranked by keywords and related topics.':'Results ranked by keywords.');update()}catch(e){if(version!==searchVersion)return;searchHits=null;feedback.textContent='Enhanced search is unavailable. Showing basic keyword matches.';update()}}
function searchChanged(){clearTimeout(searchTimer);const version=++searchVersion,query=search.value.trim();searchHits=null;for(const card of cards){const hint=card.querySelector('.search-match');if(hint)hint.remove()}if(!query){feedback.textContent='';const main=cards[0]?.parentElement;if(main)for(const card of cards)main.append(card);update();return}feedback.textContent='Searching…';update();searchTimer=setTimeout(()=>runSearch(version,query),300)}
async function change(books,message){if(busy)return;busy=true;update();delete status.dataset.notice;status.textContent='Saving…';try{me.draft=await api('/api/list',{version:me.draft.version,books,message});key=null;status.textContent='List saved.'}catch(e){status.dataset.notice='true';status.textContent='Not saved: '+e.message}finally{busy=false;if(mode==='mine')showMine();else update()}}
function bookInfo(ref){const saved=me.draft_books?.[ref];if(saved)return {...saved,publication:[saved.publisher,saved.year].filter(Boolean).join(' · ')};const c=cards.find(c=>c.dataset.ref===ref);if(c){const ps=[...c.querySelectorAll(':scope > p')];return {title:titles.get(ref),author:ps[0]?.textContent||'',publication:ps[1]?.textContent||'',isbn:ps.find(p=>p.textContent.startsWith('ISBN '))?.textContent||'',available:true}}
for(const r of me.submissions){const b=r.payload.books.find(b=>b.reference===ref);if(b)return {...b,available:false}}
return {title:'Book no longer available',author:'',available:false}}
function table(parent,headers){const wrap=el('div','',parent);wrap.className='table-scroll';const t=el('table','',wrap);t.className='family-table';const hr=el('tr','',el('thead','',t));for(const h of headers){const th=el('th',h,hr);th.scope='col'}return el('tbody','',t)}
function showMine(){mode='mine';panel.hidden=false;panel.replaceChildren();el('h2','My List',panel);
if(!me.draft.books.length)el('p','Your list is empty. Choose Browse to find books.',panel);
else{const body=table(panel,['Book','Author','Publication / ISBN','Action']);for(const ref of me.draft.books){const b=bookInfo(ref),tr=el('tr','',body);const title=el('td',b.title,tr);if(!b.available){const warning=el('small','No longer available',title);warning.className='availability-warning'}el('td',b.author,tr);const pub=el('td',b.publication||'',tr);if(b.isbn)el('small',b.isbn,pub);button('Remove',()=>change(me.draft.books.filter(x=>x!==ref),messageDraft),el('td','',tr))}}
const unavailable=me.draft.books.filter(ref=>!bookInfo(ref).available);if(unavailable.length)el('p','Remove the unavailable '+(unavailable.length===1?'book':'books')+' above, then submit your remaining selections.',panel).className='availability-warning';
const label=el('label','',panel);const notes=el('textarea','',label);notes.placeholder='Optional Message to Pops';notes.setAttribute('aria-label','Optional Message to Pops');notes.value=messageDraft;notes.maxLength=2000;notes.oninput=()=>{messageDraft=notes.value};const actions=el('div','',panel);actions.className='form-actions';const submit=button('Submit request',()=>submitRequest(notes.value,submit),actions);submit.disabled=busy||!me.draft.books.length||!!unavailable.length;button('Continue browsing',showBrowse,actions);el('h3','Submitted requests',panel);const submitted=el('div','',panel);submitted.id='submitted-requests';submissionsTable(me.submissions,submitted);update()}
function submissionsTable(rows,parent){
parent.replaceChildren();if(!rows.length){el('p','No requests submitted yet.',parent);return}
const entries=rows.flatMap(r=>r.payload.books.map(b=>({r,b}))),value=e=>({submitted:e.r.created,book:e.b.title,author:e.b.author,status:e.b.request_status||'pending',message:Number(!!e.r.payload.message||!!e.b.owner_messages?.length)})[requestSort];
entries.sort((a,b)=>requestDirection*String(value(a)).localeCompare(String(value(b)),undefined,{numeric:true,sensitivity:'base'})||a.r.id.localeCompare(b.r.id)||a.b.reference.localeCompare(b.b.reference));
const body=table(parent,['Submitted','Book','Author','Status','Message']);const keys=['submitted','book','author','status','message'];
[...body.parentElement.querySelectorAll('th')].forEach((th,i)=>{th.textContent='';const key=keys[i];th.setAttribute('aria-sort',requestSort===key?(requestDirection===1?'ascending':'descending'):'none');button(['Submitted','Book','Author','Status','Message'][i]+(requestSort===key?(requestDirection===1?' ↑':' ↓'):''),()=>{requestDirection=requestSort===key?-requestDirection:key==='submitted'?-1:1;requestSort=key;submissionsTable(me.submissions,parent)},th)});
let index=0;for(const {r,b} of entries){const tr=el('tr','',body);el('td',when(r.created),tr);el('td',b.title,tr);el('td',b.author,tr);el('td',b.request_status==='collected'?'Transferred':(b.request_status||'pending').replace(/^./,c=>c.toUpperCase()),tr);const cell=el('td','',tr);
if(r.payload.message||b.owner_messages?.length){const detail=el('tr','',body);detail.className='message-details';detail.hidden=true;detail.id='submission-message-'+index++;const content=el('td','',detail);content.colSpan=5;if(r.payload.message)el('p','Your message: '+r.payload.message,content);for(const m of b.owner_messages||[])el('p',when(m.created)+' · Pops Sullivan: '+m.message,content);const link=el('a','Message details',cell);link.href='#'+detail.id;link.setAttribute('aria-expanded','false');link.onclick=e=>{e.preventDefault();detail.hidden=!detail.hidden;link.setAttribute('aria-expanded',String(!detail.hidden))}}else el('span','No message',cell)}
}
async function refreshRequests(){if(!me||busy||polling||document.hidden)return;polling=true;const version=me.draft.version;try{const fresh=await api('/api/me');if(busy||version!==me.draft.version)return;if(fresh.draft.version===me.draft.version&&JSON.stringify(fresh.draft_books)!==JSON.stringify(me.draft_books)){me.draft_books=fresh.draft_books;if(mode==='mine')showMine();}if(JSON.stringify(fresh.submissions)!==JSON.stringify(me.submissions)){me.submissions=fresh.submissions;const target=document.querySelector('#submitted-requests');if(target)submissionsTable(me.submissions,target)}}catch(e){}finally{polling=false}}
setInterval(refreshRequests,15000);window.addEventListener('focus',refreshRequests);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshRequests()});
function showBrowse(){mode='browse';panel.hidden=true;update()}
async function submitRequest(message,send){if(busy)return;if(!me.draft.books.length){status.textContent='Add at least one book first.';return}busy=true;send.disabled=true;update();status.dataset.notice='true';status.textContent='Submitting…';try{if(message!==me.draft.message){me.draft=await api('/api/list',{version:me.draft.version,books:me.draft.books,message});key=null}key=key||crypto.randomUUID();await api('/api/submit',{version:me.draft.version,key});me=await api('/api/me');messageDraft='';key=null;showMine();status.textContent='Request submitted to Pops Sullivan. See Submitted requests below.'}catch(e){status.textContent='Submission not confirmed: '+e.message;try{const fresh=await api('/api/me');me.draft_books=fresh.draft_books;}catch(refreshError){}}finally{busy=false;showMine();update();}}

(async()=>{try{me=await api('/api/me');messageDraft=me.draft.message||'';if(me.owner&&!['/browse','/browse/'].includes(location.pathname)){location.replace('/owner/');return}document.querySelector('#signed-in').textContent='Signed in as '+me.email;status.textContent='Your list is saved automatically as you add or remove books.';document.querySelector('#inbox').hidden=true;for(const c of cards)c.querySelector('.choose').onclick=()=>{const ref=c.dataset.ref;change(me.draft.books.includes(ref)?me.draft.books.filter(x=>x!==ref):[...me.draft.books,ref],me.draft.message)};document.querySelector('#browse').onclick=showBrowse;document.querySelector('#mine').onclick=showMine;search.oninput=searchChanged;search.maxLength=500;update()}catch(e){status.textContent='Unable to load your list. Refresh to sign in again.';document.querySelector('#signed-in').textContent='Sign-in could not be verified.';for(const b of document.querySelectorAll('button'))b.disabled=true}})();

async function loadTopics(){
  const section=document.createElement('section');section.id='browse-topics';document.querySelector('#search-tools').before(section);
  el('style',`#browse-topics .topic-grid{display:flex;gap:.5rem;flex-wrap:wrap;margin:.6rem 0 1rem}#browse-topics .topic-grid button{font-weight:600}#browse-topics .subtopic-panel{margin:1rem 0;padding:1rem 1.2rem;background:#edf3ee;border-left:4px solid #245d49;border-radius:0 8px 8px 0}#browse-topics .subtopic-panel h3{font:600 1rem system-ui;margin:0 0 .4rem}#browse-topics .subtopic-grid{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.75rem}#browse-topics .subtopic-grid button{font-size:.92rem;border-radius:999px;padding:.3rem .75rem}#browse-topics .topic-path{font-size:.9rem;color:#4e6256;margin:.6rem 0}#browse-topics .topic-level{font-weight:600;margin-top:.7rem}`,section);
  el('h2','Browse by topic',section);
  el('p','Books may appear in more than one topic. Counts show catalog records currently available to request.',section).className='muted';
  el('p','1. Choose a topic',section).className='topic-level';
  const content=el('div','',section);content.className='topic-grid';content.setAttribute('role','group');content.setAttribute('aria-label','Broad topics');
  const detail=el('section','',section);detail.className='subtopic-panel';detail.setAttribute('aria-label','Narrower subjects');detail.hidden=true;
  const path=el('p','',section);path.className='topic-path';path.setAttribute('role','status');
  try{
    topicData=await api('/api/topics');
    function draw(){
      content.replaceChildren();detail.replaceChildren();detail.hidden=true;
      const choose=id=>{selectedTopic=id;draw();if(me)update()};
      const all=button('All topics',()=>choose(''),content);all.setAttribute('aria-pressed',String(!selectedTopic));
      let active=null;
      for(const topic of topicData.topics.filter(t=>t.count)){
        const isActive=selectedTopic===topic.id||topic.subtopics.some(s=>s.id===selectedTopic);
        const b=button(topic.title+' ('+topic.count+')',()=>choose(topic.id),content);b.title=topic.description;b.setAttribute('aria-pressed',String(isActive));if(isActive)active=topic;
      }
      if(active){
        const child=active.subtopics.find(s=>s.id===selectedTopic);
        path.textContent='Browsing: All topics › '+active.title+(child?' › '+child.title:'');
        const children=active.subtopics.filter(s=>s.count);
        if(children.length){
          detail.hidden=false;el('h3','2. Narrow '+active.title,detail);el('p',active.description,detail).className='muted';
          const sub=el('div','',detail);sub.className='subtopic-grid';sub.setAttribute('role','group');sub.setAttribute('aria-label','Subtopics within '+active.title);
          const any=button('All '+active.title+' ('+active.count+')',()=>choose(active.id),sub);any.setAttribute('aria-pressed',String(selectedTopic===active.id));
          for(const subject of children){const b=button(subject.title+' ('+subject.count+')',()=>choose(subject.id),sub);b.setAttribute('aria-pressed',String(selectedTopic===subject.id))}
        }
      }else path.textContent='Browsing: All topics';
    }
    draw();if(me)update();
  }catch(e){content.textContent='Topic browsing is temporarily unavailable. You can still search the library.'}
}
loadTopics();
