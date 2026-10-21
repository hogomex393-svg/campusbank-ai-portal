// Deterministic DOM and browser-stream protocol checks, without live API calls.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {JSDOM}=await import(pathToFileURL(path.join(root,'.build_frontend/node_modules/jsdom/lib/api.js')).href);
const catalog=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/portal_catalog.json'),'utf8'));
const dom=new JSDOM(await fs.readFile(path.join(root,'web/index.html'),'utf8'),{
  url:'http://localhost:8516/',runScripts:'outside-only',pretendToBeVisual:true,
});
const w=dom.window;
Object.defineProperty(w,'crypto',{value:{randomUUID:crypto.randomUUID}});
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
w.setInterval=()=>0;w.ReadableStream=ReadableStream;w.TextDecoder=TextDecoder;
const encoder=new TextEncoder();let controller,streamRequest;
const chat={id:'a'.repeat(32),title:'Streaming test',bank_mode:'general',messages:[],ticket:null};
w.fetch=async(url,options={})=>{
  if(url.endsWith('/stream')){
    streamRequest={url,options};
    return {ok:true,body:new ReadableStream({start(c){controller=c;}})};
  }
  const value=url==='/api/bootstrap'?{...catalog,csrf:'test-csrf',api_available:true,requires_login:false,user:null,portal_role:'customer'}
    :url==='/api/chats'?(options.method==='POST'?structuredClone(chat):[]):[];
  return {ok:true,json:async()=>structuredClone(value)};
};
w.eval(await fs.readFile(path.join(root,'web/app.js'),'utf8')+
  '\nwindow.__stream={S,newChat,sendMessage,requestStream,stableStreamMarkdown};');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const until=async(test)=>{const end=Date.now()+5000;while(!test()){assert(Date.now()<end,'Timed out waiting for streaming UI');await pause(15);}};
await until(()=>w.__stream.S.boot);
const ui=w.__stream;await ui.newChat();
w.document.getElementById('messageInput').value='帮我比较两种账户';
const sending=ui.sendMessage();await until(()=>controller);
assert.equal(streamRequest.url,`/api/chats/${chat.id}/stream`);
assert.equal(streamRequest.options.headers['X-CSRF-Token'],'test-csrf');
function emit(event){controller.enqueue(encoder.encode('data: '+JSON.stringify(event)+'\r\n\r\n'));}
const intro='可以，下面是两种账户的对比。';
emit({type:'delta',text:intro});
await until(()=>w.document.querySelector('.streaming-cursor'));
assert(ui.S.busy);assert.equal(ui.S.current.messages.length,1);
assert.equal(w.document.querySelectorAll('.service-action,.followup-chip').length,0);
await until(()=>ui.S.streaming.shown===intro);
assert(w.document.querySelector('.message-list').textContent.includes(intro));
const incomplete='\n\n| 账户 | 月费 |\n|--';
emit({type:'delta',text:incomplete});await until(()=>ui.S.streaming.shown===intro+incomplete);
assert(!w.document.querySelector('.message-list').textContent.includes('| 账户'));
assert.equal(w.document.querySelectorAll('.message-list table').length,0);
const ending='-|---|\n| 学生账户 | 无月费 |\n| 日常账户 | GBP 3 |\n\n请按你的用途选择。';
emit({type:'delta',text:ending});
const answer=intro+incomplete+ending;
await until(()=>ui.S.streaming.shown===answer);
assert.equal(w.document.querySelectorAll('.message-list table').length,1);
assert.equal(w.document.querySelectorAll('.service-action,.followup-chip').length,0);
const finalChat={...chat,messages:[{role:'user',content:'帮我比较两种账户',metadata:{}},
  {role:'assistant',content:answer,metadata:{actions:[{service_id:'open_account'}],followups:['开户需要哪些材料？']}}]};
emit({type:'complete',chat:finalChat});controller.close();await sending;
assert(!ui.S.busy);assert.equal(w.document.querySelectorAll('.message-list .message').length,2);
assert.equal(w.document.querySelectorAll('.streaming-cursor').length,0);
assert.equal(w.document.querySelectorAll('.service-action').length,1);
assert.equal(w.document.querySelectorAll('.followup-chip').length,1);
assert.equal(ui.S.current.messages.at(-1).content,answer);

// Split inside Chinese UTF-8 bytes and SSE delimiters, and include heartbeats.
const collected=[];
const reading=ui.requestStream('/api/chats/test',{text:'中文'},e=>collected.push(e));
await pause(0);
const bytes=encoder.encode(': ping\r\n\r\ndata: {"type":"delta","text":"中文😀"}\r\n\r\ndata: '+JSON.stringify({type:'complete',chat:finalChat})+'\r\n\r\n');
for(let i=0;i<bytes.length;i+=2)controller.enqueue(bytes.slice(i,i+2));
controller.close();const parsed=await reading;
assert.equal(collected[0].text,'中文😀');assert.equal(parsed.messages.at(-1).content,answer);
const failed=ui.requestStream('/api/chats/test',{text:'retry'},()=>{});await pause(0);
emit({type:'error',status:429,detail:'Please wait',retry_after:12});controller.close();
await assert.rejects(failed,e=>e.status===429&&e.retryAfter===12);
const interrupted=ui.requestStream('/api/chats/test',{text:'retry'},()=>{});await pause(0);
emit({type:'delta',text:'partial'});controller.close();
await assert.rejects(interrupted,/ended early|连接中断/);
console.log(JSON.stringify({progressive_content_before_completion:true,partial_table_header_hidden:true,
  table_renders_while_streaming:true,actions_and_followups_only_after_completion:true,full_history_preserved:true,
  fragmented_utf8_and_crlf_supported:true,quota_error_retains_retry_delay:true,incomplete_stream_rejected:true}));
dom.window.close();

