// Run with node tests/family_app_ui.mjs; only invented records and a fake DOM.
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const nodes=[];
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.value='';this.textContent='';this.dataset={};nodes.push(this)}
 append(e){this.children.push(e)}
 replaceChildren(){this.children=[]}
 setAttribute(k,v){this[k]=v}
 querySelector(selector){return nodes.find(e=>selector==='.form-actions button'&&e.tag==='button'&&e.textContent==='Submit request')}
}
const ids=Object.fromEntries(['panel','saved','search','count','empty','mine','browse','search-tools','browse-intro','signed-in','inbox'].map(k=>[k,new Element('div')]));
let draft={version:1,books:['ref'],message:'OLD MESSAGE'};
let posts=[];
let submissions=[{created:'2026-11-10',payload:{books:[{reference:'ref',title:'Test book',author:'Author',request_status:'pending'}],message:'Historic message'}}];
ids.updated=new Element('p');ids.search.parentElement=new Element('div');
const source=await readFile(new URL('../valuation/family_app.js',import.meta.url),'utf8');
const context=vm.createContext({document:{querySelector:s=>ids[s.slice(1)],querySelectorAll:()=>[],createElement:t=>new Element(t)},Date,Map,String,JSON,Error,crypto:{randomUUID:()=> 'retry-key'},location:{replace(){throw Error('Unexpected owner redirect')}},fetch:async(path,opts)=>({ok:true,json:async()=>{if(opts.method==='POST'){const payload=JSON.parse(opts.body);posts.push({path,payload});if(path==='/api/list'){draft={version:draft.version+1,books:payload.books,message:payload.message};return draft}return {id:'receipt'}}return {email:'guest@example.org',owner:false,draft,submissions}}})});
vm.runInContext(source,context);
await new Promise(r=>setTimeout(r,0));
vm.runInContext('showMine()',context);
assert.equal(ids['search-tools'].hidden,true);
assert.equal(ids.updated.hidden,true);
assert.equal(ids['browse-intro'].hidden,true);
assert.equal(ids.saved.hidden,true);
assert.ok(!nodes.some(e=>e.textContent.startsWith('Your saved choices are below.')));
let notes=nodes.filter(e=>e.tag==='textarea').at(-1);
assert.equal(notes.value,'');
assert.equal(notes.placeholder,'Optional Message to Pops');
const link=nodes.find(e=>e.tag==='a'&&e.textContent==='Message details');
assert.equal(link['aria-expanded'],'false');
link.onclick({preventDefault(){}});
assert.equal(link['aria-expanded'],'true');
link.onclick({preventDefault(){}});
assert.equal(link['aria-expanded'],'false');
nodes.find(e=>e.tag==='button'&&e.textContent==='Continue browsing').onclick();
assert.equal(posts.length,0);
assert.equal(ids['search-tools'].hidden,false);
assert.equal(ids.updated.hidden,false);
assert.equal(ids['browse-intro'].hidden,false);
assert.equal(ids.saved.hidden,false);
vm.runInContext('showMine()',context);
const submit=nodes.filter(e=>e.tag==='button'&&e.textContent==='Submit request').at(-1);
await submit.onclick();
assert.equal(posts.length,2);
assert.equal(posts[0].path,'/api/list');
assert.equal(posts[0].payload.message,'');
assert.equal(posts[1].path,'/api/submit');
assert.equal(posts[1].payload.version,2);
assert.equal(posts[1].payload.key,'retry-key');
assert.equal(ids.saved.textContent,'Request submitted to Pops Sullivan. See Prior submissions below.');
console.log('Family UI checks passed: blank message, hidden search, message toggle, non-destructive browsing and direct submission.');

// Read-only query responses must not overwrite a newer query or alter drafts.
context.testResponse={results:[{reference:'ref',reason:'Related topics',excerpt:'Source text'}],engine:'hybrid',notice:''};
vm.runInContext("api=async()=>testResponse;searchVersion=2;search.value='new topic'",context);
await vm.runInContext("runSearch(1,'old topic')",context);
assert.equal(vm.runInContext('searchHits',context),null);
await vm.runInContext("runSearch(2,'new topic')",context);
assert.equal(vm.runInContext('searchHits.length',context),1);
vm.runInContext("api=async()=>{throw Error('offline')}",context);
await vm.runInContext("runSearch(2,'new topic')",context);
assert.equal(vm.runInContext('searchHits',context),null);
assert.ok(nodes.find(e=>e.id==='search-feedback').textContent.includes('basic keyword'));
assert.equal(posts.length,2);
console.log('Search UI checks passed: latest response wins, offline fallback, no draft writes.');
