// Offline DOM tests. This does not automate a real browser or Windows login dialog.
import fs from "node:fs/promises";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const { JSDOM } = await import(
  pathToFileURL(
    path.join(root, ".build_frontend/node_modules/jsdom/lib/api.js"),
  ).href
);
const catalog = JSON.parse(
  await fs.readFile(
    path.join(root, "tests/fixtures/portal_catalog.json"),
    "utf8",
  ),
);
const dom = new JSDOM(
  await fs.readFile(path.join(root, "web/index.html"), "utf8"),
  {
    url: "http://localhost:8502/",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  },
);
const w = dom.window;
Object.defineProperty(w, "crypto", {
  value: { randomUUID: crypto.randomUUID },
});
w.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute("open", "");
};
w.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute("open");
};
let supportSync;
w.setInterval = (callback) => {
  supportSync = callback;
  return 0;
};
Object.defineProperty(w.navigator, "clipboard", {
  value: { writeText: async () => {} },
});
let user = null;
const chats = [];
const requests = [];
const calls = [];
const tickets = [];
w.fetch = async (url, options = {}) => {
  const method = options.method || "GET";
  const body = options.body ? JSON.parse(options.body) : null;
  calls.push({ url, method, body });
  let value;
  if (url === "/api/bootstrap")
    value = {
      ...catalog,
      user,
      csrf: "test-csrf",
      api_available: true,
      version: "2.0.0",
    };
  else if (url === "/api/chats" && method === "GET")
    value = chats.map((c) => ({
      id: c.id,
      title: c.title,
      created_at: c.created_at,
      updated_at: c.updated_at,
    }));
  else if (url === "/api/chats" && method === "POST") {
    value = {
      id: crypto.randomUUID().replaceAll("-", ""),
      title: "新对话",
      bank_mode:body?.bank_mode || 'general',
      messages: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      ticket: null,
    };
    chats.unshift(value);
  } else if (/^\/api\/chats\/[^/]+\/messages$/.test(url)) {
    const id = url.split("/")[3];
    value = chats.find((c) => c.id === id);
    value.title = body.text.slice(0, 30);
    value.messages.push(
      { role: "user", content: body.text, metadata: {} },
      {
        role: "assistant",
        content: "请从开户窗口核对信息。",
        metadata: { actions: [{ service_id: "open_account" }],response_language:'zh',followups:['开户需要哪些材料？','月费和最低存款要注意什么？','怎样在线办理并查看申请进度？'] },
      },
    );
  } else if (/^\/api\/chats\/[^/]+$/.test(url))
    value = chats.find((c) => c.id === url.split("/")[3]);
  else if (url === "/api/register") {
    user = {
      id: "test",
      username: body.username,
      display_name: body.display_name,
      is_admin: 1,
    };
    value = { user, csrf: "signed-in-csrf", portal_role: body.portal_role };
  } else if (/^\/api\/chats\/[^/]+\/handoff$/.test(url)) {
    const chat = chats.find((c) => c.id === url.split("/")[3]);
    const ticket = {
      id: "CB-SUPPORT-DOM",
      chat_id: chat.id,
      subject: chat.title,
      description: "请处理当前咨询",
      status: "waiting",
      customer_name: user.display_name,
      updated_at: new Date().toISOString(),
      message_count: chat.messages.length,
    };
    tickets.push(ticket);
    chat.ticket = { id: ticket.id, status: "waiting" };
    chat.messages.push({
      role: "assistant",
      content: "已转人工客服。",
      metadata: { sender: "service" },
    });
    value = { ticket, chat, existing: false };
  } else if (url === "/api/admin/staff-invites")
    value = {
      invite_code: "SYNTHETIC-INVITE",
      expires_at: new Date(Date.now() + 86400000).toISOString(),
    };
  else if (url === "/api/session/role")
    value = { user, csrf: "role-csrf", portal_role: body.portal_role };
  else if (url === "/api/support-tickets") value = tickets;
  else if (/^\/api\/support-tickets\/[^/]+$/.test(url)) {
    const ticket = tickets.find((t) => t.id === url.split("/")[3]);
    value = { ticket, chat: chats.find((c) => c.id === ticket.chat_id) };
  } else if (url === "/api/admin/tickets") value = tickets;
  else if (/^\/api\/admin\/tickets\/[^/]+$/.test(url)) {
    const ticket = tickets.find((t) => t.id === url.split("/")[4]);
    value = { ticket, chat: chats.find((c) => c.id === ticket.chat_id) };
  } else if (
    /^\/api\/admin\/tickets\/[^/]+\/(claim|reply|resolve)$/.test(url)
  ) {
    const ticket = tickets.find((t) => t.id === url.split("/")[4]);
    const chat = chats.find((c) => c.id === ticket.chat_id);
    const action = url.split("/")[5];
    ticket.status = action === "resolve" ? "resolved" : "active";
    ticket.assigned_to = user.id;
    ticket.assigned_name = user.display_name;
    if (action === "reply")
      chat.messages.push({
        role: "assistant",
        content: body.text,
        metadata: { sender: "staff", staff_name: user.display_name },
      });
    chat.ticket =
      action === "resolve" ? null : { id: ticket.id, status: ticket.status };
    ticket.updated_at = new Date().toISOString();
    ticket.message_count = chat.messages.length;
    value = ticket;
  } else if(url==='/api/testing/staff-session') {
    user={id:'test',username:'test_staff',display_name:'Test staff',is_admin:0,is_staff:1};value={user,csrf:'test-staff-csrf',portal_role:'staff',testing_staff:true};
  } else if(url==='/api/admin/requests')value=requests.filter(r=>r.service_id!=='human_support');
  else if(/^\/api\/admin\/requests\/[^/]+$/.test(url)) {
    const row=requests.find(r=>r.id===url.split('/')[4]);
    if(method==='PATCH'){row.status=body.status;row.staff_note=body.note;row.events||=[];row.events.push({actor:'Test staff',status:body.status,note:body.note,created_at:new Date().toISOString()});}
    value={...row,events:row.events||[]};
  } else if (url === "/api/requests" && method === "GET") value = requests;
  else if (url === "/api/requests" && method === "POST") {
    value = {
      id: "CB-DOM-TEST-"+(requests.length+1),
      service_id: body.service_id,
      title: "在线开户申请",
      status: "pending",
      payload: body.payload,
      created_at: new Date().toISOString(),
      bank_mode:body.bank_mode || 'general',customer_name:'Demo customer',staff_note:'',
    };
    requests.push(value);
  } else throw new Error("Unexpected mocked route " + method + " " + url);
  return { ok: true, json: async () => JSON.parse(JSON.stringify(value)) };
};
w.eval(
  (await fs.readFile(path.join(root, "web/app.js"), "utf8")) +
    "\nwindow.__test={S,showChat,showStaff,switchPortalRole,showSupportHistory,showCustomerTicket,startHandoff,newChat,selectChat,sendMessage,showServices,openService,showRequests,showReferences,renderChat,openAuth,authKind,markdown,setLanguage,switchBankMode,enterTestStaff,refreshBusinessRequests};",
);
async function flush() {
  for (let i = 0; i < 20; i++)
    await new Promise((resolve) => setImmediate(resolve));
}
await flush();
const ui = w.__test;
assert.equal(w.document.querySelectorAll("#businessNav button").length, 6);
assert.equal(w.document.querySelectorAll(".suggestion").length, 6);
await ui.newChat();
const first = ui.S.current.id;
w.document.getElementById("messageInput").value = "我要开学生账户";
await ui.sendMessage();
assert.equal(w.document.querySelectorAll(".message").length, 2);
assert.equal(w.document.querySelectorAll(".service-action").length, 1);
await ui.newChat();
assert.equal(w.document.querySelectorAll(".history-entry").length, 2);
await ui.selectChat(first);
assert.equal(w.document.querySelectorAll(".message").length, 2);
w.document.getElementById("messageInput").value = "那需要什么材料？";
await ui.sendMessage();
assert.equal(w.document.querySelectorAll(".message").length, 4);
ui.showServices("cards");
assert.equal(w.document.querySelectorAll(".service-card").length, 2);
ui.openService("open_account");
assert(w.document.getElementById("serviceDialog").open);
assert(w.document.querySelector("#serviceForm [name=product]"));
ui.openAuth("register");
const auth = w.document.getElementById("authForm");
auth.elements.username.value = "dom_tester";
auth.elements.password.value = "DomTestPass2026";
auth.elements.display_name.value = "<img src=x onerror=alert(1)>";
auth.dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true }));
await flush();
assert.equal(ui.S.boot.user.username, "dom_tester");
assert.equal(w.document.querySelector("#profileName img"), null);
ui.openService("open_account");
const form = w.document.getElementById("serviceForm");
form.elements.applicant.value = "演示申请人";
form.elements.documents_ready.checked = true;
form.dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true }));
await flush();
const confirm = [...w.document.querySelectorAll("#serviceBody button")].find(
  (b) => b.textContent.includes("确认提交"),
);
assert(confirm);
confirm.click();
await flush();
assert.equal(requests.length, 1);
assert.equal(
  calls.find((c) => c.url === "/api/requests" && c.method === "POST").body
    .confirmed,
  true,
);
assert(
  w.document
    .querySelector(".reference-number")
    .textContent.includes("CB-DOM-TEST"),
);
await ui.showRequests();
assert.equal(w.document.querySelectorAll(".request-row").length, 1);
ui.showReferences();
assert.equal(w.document.querySelectorAll(".reference-card").length, 4);
ui.renderChat();
assert.equal(w.document.querySelectorAll(".message").length, 4);
const malicious = {
  role: "assistant",
  content: "<img src=x onerror=alert(1)> **safe text**",
  metadata: {},
};
ui.S.current.messages.push(malicious);
ui.renderChat();
assert.equal(w.document.querySelector("#content img"), null);

assert(w.document.getElementById("staffNav").hidden);
await ui.switchPortalRole("staff");
assert(
  w.document
    .getElementById("content")
    .textContent.includes("先创建一张人工客服工单"),
);
const createTicket = [...w.document.querySelectorAll("#content button")].find(
  (b) => b.textContent === "创建人工客服工单",
);
assert(createTicket);
createTicket.click();
await flush();
assert(w.document.querySelector("#serviceForm [name=subject]"));
w.document.getElementById("serviceDialog").close();
await ui.startHandoff();
assert(ui.S.current.ticket);
assert(w.document.getElementById("handoffButton").disabled);
await ui.showStaff();
assert.equal(w.document.querySelectorAll(".ticket-item").length, 1);
const draft = w.document.querySelector(".staff-detail textarea");
draft.value = "工作人员的未发送草稿";
draft.dispatchEvent(new w.Event("input"));
const supportChat = chats.find((c) => c.id === first);
supportChat.messages.push({
  role: "user",
  content: "客户新增：请查看我的补卡申请",
  metadata: {},
});
tickets[0].message_count = supportChat.messages.length;
await supportSync();
assert.equal(
  w.document.querySelector(".staff-detail textarea").value,
  "工作人员的未发送草稿",
);
assert(
  w.document
    .querySelector(".staff-transcript")
    .textContent.includes("客户新增"),
);
const staffSend = [
  ...w.document.querySelectorAll(".staff-actions button"),
].find((b) => b.textContent === "发送回复");
staffSend.click();
await flush();
assert.equal(supportChat.messages.at(-1).metadata.sender, "staff");
assert.equal(supportChat.messages.at(-1).content, "工作人员的未发送草稿");
assert.equal(w.document.querySelector(".staff-detail textarea").value, "");
const invitation = [
  ...w.document.querySelectorAll(".staff-toolbar button"),
].find((b) => b.textContent === "邀请工作人员");
invitation.click();
await flush();
assert(w.document.getElementById("staffInviteDialog").open);
w.document.getElementById("staffInviteDialog").close();
const resolve = [...w.document.querySelectorAll(".staff-actions button")].find(
  (b) => b.textContent === "结束工单",
);
resolve.click();
await flush();
assert.equal(w.document.querySelector(".staff-detail textarea"), null);
ui.showChat();
await supportSync();
assert.equal(ui.S.current.ticket, null);
assert(
  w.document
    .getElementById("content")
    .textContent.includes("工作人员的未发送草稿"),
);
assert(!w.document.getElementById("handoffButton").disabled);
await ui.switchPortalRole("customer");
assert(w.document.getElementById("staffNav").hidden);
assert(!w.document.getElementById("supportHistoryNav").hidden);
await ui.showSupportHistory();
assert(
  w.document.getElementById("content").textContent.includes("我的人工客服记录"),
);
await ui.showCustomerTicket(tickets[0].id);
assert.equal(w.document.querySelectorAll("#content textarea").length, 0);
assert(
  w.document
    .getElementById("content")
    .textContent.includes("工作人员的未发送草稿"),
);
assert(
  ![...w.document.querySelectorAll("#content button")].some(
    (b) => b.textContent === "发送回复",
  ),
);
ui.openAuth("login");
w.document.getElementById("portalRole").value = "staff";
w.document.getElementById("portalRole").dispatchEvent(new w.Event("change"));
assert(!w.document.getElementById("staffInviteField").hidden);
w.document.getElementById("authDialog").close();
// Readable tables, including escaped pipes, formatting, safe HTML, and fenced output.
const table = ui.markdown("```markdown\n| Feature | Student | Everyday |\n|---|:---:|---:|\n| **Monthly fee** | No fee | GBP 3 |\n| Documents | Photo ID \\| address | `<script>` |\n```\nNext steps");
assert.equal(table.querySelectorAll("table").length,1);
assert.equal(table.querySelectorAll("thead th").length,3);
assert.equal(table.querySelectorAll("tbody tr").length,2);
assert.equal(table.querySelector("tbody th strong").textContent,"Monthly fee");
assert.equal(table.querySelectorAll("tbody tr")[1].children[1].textContent,"Photo ID | address");
assert.equal(table.querySelector("script"),null);
assert(table.textContent.includes("Next steps"));
assert(!table.textContent.includes("|---"));

// A stale action must open the latest saved server draft, without losing unchanged slots.
ui.S.current.service_drafts = {transfer_demo:{transfer_type:"international",recipient:"Sam",amount:"500"}};
ui.openService("transfer_demo",{transfer_type:"domestic",amount:"2000"});
let reviewForm = w.document.getElementById("serviceForm");
assert.equal(reviewForm.elements.transfer_type.value,"international");
assert.equal(reviewForm.elements.recipient.value,"Sam");
assert.equal(reviewForm.elements.amount.value,"500");
reviewForm.dispatchEvent(new w.Event("submit",{bubbles:true,cancelable:true}));
const requestCount = calls.filter(c=>c.url==="/api/requests" && c.method==="POST").length;
const confirmTwice = [...w.document.querySelectorAll("#serviceBody button")].find(b=>b.textContent.includes("确认提交"));
assert(confirmTwice); confirmTwice.click(); confirmTwice.click(); await flush();
const newRequests=calls.filter(c=>c.url==="/api/requests" && c.method==="POST");
assert.equal(newRequests.length,requestCount+1);
assert.match(newRequests.at(-1).body.request_id,/^[a-f0-9]{32}$/);

ui.openService("branch_appointment"); reviewForm=w.document.getElementById("serviceForm");
reviewForm.elements.date.value="2000-01-01"; reviewForm.elements.purpose.value="Demo visit";
reviewForm.dispatchEvent(new w.Event("submit",{bubbles:true,cancelable:true}));
assert(w.document.querySelector("#serviceForm .form-error").textContent.includes("不能早于"));
reviewForm.elements.date.value=new Date().toISOString().slice(0,10); reviewForm.elements.purpose.value="   ";
reviewForm.dispatchEvent(new w.Event("submit",{bubbles:true,cancelable:true}));
assert(w.document.querySelector("#serviceForm .form-error").textContent.includes("请填写"));
reviewForm.elements.purpose.value="Demo visit"; reviewForm.dispatchEvent(new w.Event("input",{bubbles:true}));
w.document.getElementById("serviceDialog").close(); ui.openService("branch_appointment");
assert.equal(w.document.getElementById("serviceForm").elements.purpose.value,"Demo visit");
w.document.getElementById("serviceDialog").close();

w.document.getElementById("historySearch").value="no-such-conversation";
w.document.getElementById("historySearch").dispatchEvent(new w.Event("input"));
assert(w.document.getElementById("historyList").textContent.includes("没有匹配"));
w.document.getElementById("historySearch").value="";
ui.S.lang="en"; ui.setLanguage();
for (const service of catalog.services) {
  ui.openService(service.id);
  const text=w.document.getElementById("serviceDialog").textContent;
  assert(!/[\u4e00-\u9fff]/.test(text),`Untranslated service: ${service.id}`);
  w.document.getElementById("serviceDialog").close();
}
assert(!/[\u4e00-\u9fff]/.test(w.document.getElementById("settingsDialog").textContent));
// Interrupted requests retain the question, offer retry, and reuse the original send ID.
ui.showChat(); const originalFetch=w.fetch;
w.fetch=async(url,options)=> { if (url.endsWith("/messages")) throw new TypeError("Failed to fetch"); return originalFetch(url,options); };
w.document.getElementById("messageInput").value="Retry this question";
await ui.sendMessage();
assert.equal(w.document.getElementById("messageInput").value,"Retry this question");
assert(w.document.getElementById("sendFeedback").textContent.includes("Retry sending"));
assert(!w.document.getElementById("sendFeedback").textContent.includes("Failed to fetch"));
const failedId=ui.S.retryMessage.id; w.fetch=originalFetch;
await ui.sendMessage(); assert.equal(calls.filter(c=>c.url.endsWith("/messages")).at(-1).body.request_id,failedId);
w.fetch=async(url,options)=>url.endsWith("/messages") ? {ok:false,status:429,json:async()=>({detail:"Rate limited",retry_after:2})} : originalFetch(url,options);
w.document.getElementById("messageInput").value="Please wait"; await ui.sendMessage();
assert(w.document.getElementById("sendFeedback").textContent.includes("Retry in"));
assert(w.document.getElementById("sendButton").disabled);
w.clearTimeout(ui.S.cooldownTimer); w.fetch=originalFetch;
ui.S.cooldownUntil=0;ui.S.lang='zh';ui.setLanguage();
await ui.switchBankMode('student');
assert.equal(ui.S.current.bank_mode,'student');
assert.equal(w.document.querySelectorAll('#businessNav button').length,7);
assert(w.document.getElementById('content').textContent.includes('助学贷款'));
const studentChatId=ui.S.current.id;
w.document.getElementById('messageInput').value='助学贷款需要哪些材料？';await ui.sendMessage();
assert.equal(w.document.querySelectorAll('.followup-chip').length,3);
const followup=w.document.querySelector('.followup-chip');const suggested=followup.textContent;
followup.click();await flush();assert.equal(calls.filter(c=>c.url.endsWith('/messages')).at(-1).body.text,suggested);
assert.equal(calls.filter(c=>c.url.endsWith('/messages')).at(-1).body.bank_mode,'student');
ui.openService('funding_enquiry');assert.equal(w.document.querySelectorAll('.funding-program').length,3);
w.document.getElementById('serviceForm').elements.funding_type.value='scholarship';
w.document.getElementById('serviceForm').elements.funding_type.dispatchEvent(new w.Event('change'));
assert.equal(w.document.querySelectorAll('.funding-program').length,1);
w.document.getElementById('serviceDialog').close();
await ui.switchBankMode('general');assert.equal(w.document.querySelectorAll('#businessNav button').length,6);
await ui.selectChat(studentChatId);assert.equal(ui.S.bankMode,'student');
assert(w.document.getElementById('studentBankMode').classList.contains('active'));

ui.S.boot.open_staff_testing=true;ui.openAuth('login');
w.document.getElementById('portalRole').value='staff';w.document.getElementById('portalRole').dispatchEvent(new w.Event('change'));
assert(w.document.getElementById('staffInviteField').hidden);assert(!w.document.getElementById('staffTestEntry').hidden);
await ui.enterTestStaff();assert.equal(ui.S.boot.user.is_admin,0);assert.equal(ui.S.staffTab,'requests');
assert(w.document.getElementById('businessRequestDetail').querySelector('table'));
const reviewNote=w.document.querySelector('.business-review-note');reviewNote.value='Please add a demo document summary.';reviewNote.dispatchEvent(new w.Event('input'));
await supportSync();assert.equal(w.document.querySelector('.business-review-note').value,'Please add a demo document summary.');
[...w.document.querySelectorAll('.business-actions button')].find(b=>b.textContent.includes('请客户补充')).click();await flush();
assert.equal(requests[0].status,'needs_info');assert.equal(requests[0].staff_note,'Please add a demo document summary.');
await ui.switchPortalRole('customer');await ui.showRequests();
assert(w.document.querySelector('.staff-review-note').textContent.includes('demo document summary'));
const summary = {
  dual_mode_navigation_and_history:true,
  student_funding_directory_filters:true,
  followup_bubbles_send_contextual_question:true,
  invitation_free_test_staff_entry:true,
  business_forms_visible_to_staff:true,
  business_review_draft_survives_polling:true,
  review_note_and_status_reach_customer:true,
  readable_tables_and_safe_cells:true,
  latest_chat_draft_prefills_form:true,
  confirmation_double_click_only_posts_once:true,
  past_dates_and_whitespace_block_review:true,
  form_draft_retained_on_reopen:true,
  english_service_catalog_and_settings:true,
  readable_search_empty_state:true,
  network_retry_preserves_message_and_send_id:true,
  rate_limit_countdown_and_retry:true,
  customer_history_has_no_reply_controls: true,
  staff_controls_require_active_staff_role: true,
  resolved_ticket_is_read_only: true,
  chat_handoff_posts_context: true,
  staff_queue_auto_syncs: true,
  staff_reply_draft_survives_customer_update: true,
  manual_reply_visible_in_customer_chat: true,
  invitation_and_role_picker_wired: true,

  test_type: "offline DOM with mock HTTP responses",
  categories: 6,
  history_after_new_chat: true,
  all_messages_preserved: true,
  service_button_opens_form: true,
  registration_form_wired: true,
  confirmation_form_posts_request: true,
  requests_visible: true,
  official_reference_links: 4,
  user_and_model_html_escaped: true,
  real_browser_layout_inspected: false,
};
await fs.writeFile(
  path.join(root, "evaluation/results/portal_frontend_dom.json"),
  JSON.stringify(summary, null, 2) + "\n",
);
console.log(JSON.stringify(summary));
dom.window.close();
