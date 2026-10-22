// Form journey integration in a DOM, using fixed canonical server-preview fixtures.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {JSDOM}=await import(pathToFileURL(path.join(root,'.build_frontend/node_modules/jsdom/lib/api.js')).href);
const catalog=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/portal_catalog.json'),'utf8'));
const scenarios=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/scenarios.json'),'utf8'));
const previews=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/scenario_previews.json'),'utf8'));
for(const s of catalog.services)if(scenarios[s.id])s.scenario=scenarios[s.id];
const dom=new JSDOM(await fs.readFile(path.join(root,'web/index.html'),'utf8'),{url:'http://localhost:8516/',runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window;Object.defineProperty(w,'crypto',{value:{randomUUID:crypto.randomUUID}});
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};w.setInterval=()=>0;
const records=[],chats=[];let previewFailure=false;
w.fetch=async(url,options={})=>{
  const data=options.body?JSON.parse(options.body):null;let value;
  if(url==='/api/bootstrap')value={...catalog,csrf:'test',user:{id:'demo',display_name:'Demo'},api_available:false,portal_role:'customer'};
  else if(url==='/api/chats'){
    if(options.method==='POST'){value={id:crypto.randomUUID(),title:'Demo',bank_mode:data.bank_mode,messages:[],ticket:null};chats.push(value);}else value=chats;
  }else if(url==='/api/requests'&&options.method==='POST'){
    value={id:'CB-FORM-TEST',status:'pending',...data,scenario:previews.international};records.push(value);
  }else if(url==='/api/requests')value=records;
  else if(url.startsWith('/api/chats/'))value=chats.find(c=>c.id===url.split('/')[3]);
  else if(url==='/api/scenarios/preview'){
    if(previewFailure)return {ok:false,status:400,json:async()=>({detail:'收款名称不匹配，请核对演示收款资料。'})};
    value=previews[data.service_id==='open_account'?'student':data.payload.transfer_type==='international'?'international':'domestic'];
  }else throw Error('Unexpected route '+url);
  return {ok:true,json:async()=>structuredClone(value)};
};
w.eval(await fs.readFile(path.join(root,'web/app.js'),'utf8')+'\nwindow.__form={S,newChat,openService,switchBankMode,showRequests};');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn){const end=Date.now()+5000;while(!fn()){assert(Date.now()<end,'Form workflow timed out');await pause(15);}}
await until(()=>w.__form.S.boot);const ui=w.__form;await ui.newChat();assert.equal(w.document.body.dataset.bankMode,'general');
ui.openService('open_account');let form=w.document.getElementById('serviceForm');
assert(form.querySelector('.scenario-section'));assert(w.document.querySelector('.scenario-profile').textContent.includes('example.invalid'));
assert(form.querySelector('[name=scenario_student_document]').parentElement.hidden);
form.elements.product.value='student_account';form.elements.product.dispatchEvent(new w.Event('change',{bubbles:true}));
assert.equal(form.elements.scenario_profile.value,'student_demo');assert.equal(form.elements.scenario_employment.value,'student');
assert(!form.elements.scenario_student_document.parentElement.hidden);
form.elements.documents_ready.checked=true;
form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await pause(20);
assert(form.querySelector('.form-error').textContent.includes('核对声明'));
form.elements.scenario_declaration.checked=true;form.elements.scenario_declaration.dispatchEvent(new w.Event('input',{bubbles:true}));
form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await until(()=>!w.document.getElementById('serviceForm'));
assert(w.document.querySelector('.scenario-summary').textContent.includes('Jamie Demo'));
[...w.document.querySelectorAll('#serviceBody button')].find(b=>b.textContent==='返回修改').click();
form=w.document.getElementById('serviceForm');assert(form.elements.scenario_declaration.checked);assert.equal(form.elements.scenario_profile.value,'student_demo');
w.document.getElementById('serviceDialog').close();await ui.switchBankMode('student');assert.equal(w.document.body.dataset.bankMode,'student');
ui.openService('transfer_demo',{transfer_type:'international',recipient:'Demo college',amount:'100.05'});form=w.document.getElementById('serviceForm');
assert.equal(form.elements.scenario_payee_profile.value,'europe_demo');assert.equal(form.elements.scenario_payer.value,'student_demo');
assert(w.document.querySelector('.scenario-profile').textContent.includes('DEMO-IBAN-EU-NOT-VALID'));
form.elements.scenario_execution.value='scheduled';form.elements.scenario_execution.dispatchEvent(new w.Event('change',{bubbles:true}));
assert(!form.elements.scenario_execution_date.parentElement.hidden);assert(form.elements.scenario_execution_date.required);
form.elements.scenario_execution.value='now';form.elements.scenario_execution.dispatchEvent(new w.Event('change',{bubbles:true}));
assert(form.elements.scenario_execution_date.disabled);
form.elements.scenario_declaration.checked=true;previewFailure=true;
form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await until(()=>w.document.querySelector('.scenario-preview .form-error'));
assert(w.document.getElementById('serviceForm'));assert(w.document.querySelector('.scenario-preview').textContent.includes('不匹配'));
previewFailure=false;form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await until(()=>!w.document.getElementById('serviceForm'));
assert(w.document.querySelector('.scenario-summary').textContent.includes('108.05'));
[...w.document.querySelectorAll('#serviceBody button')].find(b=>b.textContent==='确认提交演示请求').click();await until(()=>w.document.querySelector('.receipt .scenario-summary'));
assert.equal(records[0].scenario.quote.receive_amount,'117.06');assert(w.document.querySelector('.receipt .scenario-summary'));
w.document.getElementById('serviceDialog').close();await ui.showRequests();assert(w.document.querySelector('.request-details .scenario-summary'));
ui.S.lang='en';ui.openService('open_account');
assert(!/[\u4e00-\u9fff]/.test(w.document.getElementById('serviceDialog').textContent),'Scenario form contains untranslated Chinese');
console.log(JSON.stringify({account_profile_and_student_requirements:true,explicit_declaration_required:true,review_back_preserves_scenario:true,
  transfer_type_selects_fictional_payee:true,scheduled_date_is_conditional:true,invalid_preview_blocks_review:true,
  canonical_quote_in_review_receipt_and_history:true,mode_attribute_changes_with_navigation:true}));dom.window.close();
