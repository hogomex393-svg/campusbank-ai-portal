// Group review UI regressions. Mock HTTP data is fictional and contains no credentials.
import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';import crypto from 'node:crypto';import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {JSDOM}=await import(pathToFileURL(path.join(root,'.build_frontend/node_modules/jsdom/lib/api.js')).href);
const catalog=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/portal_catalog.json'),'utf8'));
const dom=new JSDOM(await fs.readFile(path.join(root,'web/index.html'),'utf8'),{url:'http://localhost/',runScripts:'outside-only',pretendToBeVisual:true});const w=dom.window;
Object.defineProperty(w,'crypto',{value:{randomUUID:crypto.randomUUID}});w.setInterval=()=>0;w.confirm=()=>true;
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
const chats=[{id:'c1',title:'Synthetic transfer',archived:0,bank_mode:'general',ticket:null,messages:[{id:1,role:'user',content:'Transfer help',metadata:{}},{id:2,role:'assistant',content:'Fictional transfer review.',metadata:{mode:'agent',sources:[{id:'DEMO_TRANSFER_QUOTE',title:'演示转账计算','title_en':'Demo transfer quote',version:'abc123456789'}]}}]}];
const requests=[{id:'CB-REVIEW-ONE',service_id:'branch_appointment',title:'网点服务预约',status:'needs_info',archived:0,staff_note:'Please supplement the demo purpose.',payload:{city:'London',date:'2030-11-02',purpose:'Original demo purpose'}}];
let creates=0;const routes=[];
w.fetch=async(url,options={})=>{
 const body=options.body?JSON.parse(options.body):null;routes.push({url,method:options.method,body});let data;
 if(url==='/api/bootstrap')data={...catalog,user:{id:'u1',display_name:'Demo'},portal_role:'customer',csrf:'mock',api_available:false};
 else if(url.startsWith('/api/chats')&&!url.includes('/archive')&&!url.includes('/feedback'))data=url==='/api/chats'?chats.filter(c=>!c.archived):url==='/api/chats?archived=true'?chats.filter(c=>c.archived):chats.find(c=>c.id===url.split('/')[3]);
 else if(url.includes('/messages/2/feedback')){data={message_id:2,...body};chats[0].messages[1].feedback=data;}
 else if(url.startsWith('/api/chats/')&&url.endsWith('/archive')){chats[0].archived=+body.archived;data={id:'c1',archived:body.archived};}
 else if(url==='/api/requests'&&options.method==='POST'){creates++;throw Error('Supplement must not create a new request');}
 else if(url==='/api/requests')data=requests.filter(r=>!r.archived);
 else if(url==='/api/requests?archived=true')data=requests.filter(r=>r.archived);
 else if(url==='/api/requests/CB-REVIEW-ONE/action'){
   if(body.action==='supplement'){requests[0].payload=body.payload;requests[0].status='pending';}
   else requests[0].status='cancelled';data=requests[0];
 }else if(url==='/api/requests/CB-REVIEW-ONE/archive'){requests[0].archived=+body.archived;data={id:requests[0].id,archived:body.archived};}
 else if(url==='/api/requests/CB-REVIEW-ONE')data={...requests[0],events:[{created_at:'2026-10-25T08:00:00Z',status:'needs_info',note:'Demo review note'}]};
 else throw Error('Unexpected mocked route '+url);
 return {ok:true,json:async()=>structuredClone(data)};
};
w.eval(await fs.readFile(path.join(root,'web/app.js'),'utf8')+'\nwindow.__review={S,selectChat,showRequests,renderChat};');const ui=w.__review;
const pause=ms=>new Promise(r=>setTimeout(r,ms));async function until(fn){const end=Date.now()+5000;while(!fn()){assert(Date.now()<end,'Review UI timed out');await pause(15);}}
await until(()=>ui.S.boot);
for(const close of ['sidebarClose','sidebarBackdrop']){w.document.getElementById('menuToggle').click();assert(!w.document.getElementById('sidebarBackdrop').hidden);w.document.getElementById(close).click();assert(!w.document.getElementById('sidebar').classList.contains('open'));}
w.document.getElementById('menuToggle').click();w.document.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert(!w.document.getElementById('sidebar').classList.contains('open'));assert.equal(w.document.activeElement.id,'menuToggle');
await ui.selectChat('c1');ui.S.debug=true;ui.renderChat(false);assert(w.document.querySelector('.public-source-list').textContent.includes('abc123456789'));
[...w.document.querySelectorAll('.feedback-button')].find(b=>b.textContent==='没帮助').click();const feedback=w.document.querySelector('.feedback-form');feedback.querySelector('select').value='misunderstood';feedback.querySelector('input').value='Synthetic reason';feedback.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await until(()=>chats[0].messages[1].feedback);assert.equal(chats[0].messages[1].feedback.reason,'misunderstood');
w.document.querySelector('.archive-chat').click();await until(()=>chats[0].archived===1);await pause(30);assert.equal(w.document.querySelectorAll('.history-entry').length,0);
w.document.getElementById('archiveHistoryToggle').click();await until(()=>w.document.querySelector('.archive-chat'));w.document.querySelector('.archive-chat').click();await until(()=>chats[0].archived===0);
await ui.showRequests();[...w.document.querySelectorAll('.request-customer-actions button')].find(b=>b.textContent==='补充原申请资料').click();let form=w.document.getElementById('serviceForm');assert.equal(form.elements.purpose.value,'Original demo purpose');form.elements.purpose.value='Updated demo purpose';form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await until(()=>!w.document.getElementById('serviceForm'));
[...w.document.querySelectorAll('#serviceBody button')].find(b=>b.textContent==='确认提交演示请求').click();await until(()=>w.document.querySelector('.reference-number'));assert.equal(w.document.querySelector('.reference-number').textContent,'CB-REVIEW-ONE');assert.equal(creates,0);assert.equal(requests.length,1);assert.equal(requests[0].payload.purpose,'Updated demo purpose');
w.document.getElementById('serviceDialog').close();await ui.showRequests();[...w.document.querySelectorAll('.request-customer-actions button')].find(b=>b.textContent==='撤回演示申请').click();await until(()=>requests[0].status==='cancelled');await pause(40);
[...w.document.querySelectorAll('.request-customer-actions button')].find(b=>b.textContent==='归档记录').click();await until(()=>requests[0].archived===1);
console.log(JSON.stringify({close_button_overlay_escape:true,focus_returns_to_menu:true,readable_source_titles_and_versions:true,answer_feedback_sent:true,archive_restore_preserves_chat:true,supplement_updates_original_request:true,withdraw_then_archive:true}));dom.window.close();
