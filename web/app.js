"use strict";
const $ = (id) => document.getElementById(id);
const S = {
  boot: null,
  chats: [],
  current: null,
  view: "chat",
  busy: false,
  mode: "agent",
  bankMode: localStorage.getItem("campusbank_bank_mode") || "general",
  generalTheme:localStorage.getItem('campusbank_general_theme') || 'ruby',
  staffTab: "tickets",
  debug: false,
  lang: localStorage.getItem("campusbank_language") || "zh",
  afterLogin: null,
  authKind: "login",
  service: null,
  ticket: null,
  staffId: null,
  staffFingerprint: "",
  staffDetailFingerprint: "",
  staffPolling: false,
  handoffBusy: false,
  formDrafts: new Map(),
  cooldownUntil: 0,
};
const icons = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  chat: '<path d="M21 11a8 8 0 0 1-8 8H5l-3 3V11a9 9 0 0 1 19 0Z"/><path d="M7 10h10M7 14h6"/>',
  wallet:
    '<path d="M3 6h17v14H3zM3 6V3h14v3M15 11h7v5h-7z"/><path d="M18 13.5h.1"/>',
  card: '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="M2 9h20M6 15h5"/>',
  transfer: '<path d="M4 7h16l-4-4M20 17H4l4 4M20 7l-4 4M4 17l4-4"/>',
  savings:
    '<path d="M4 10h14l2 3v5h-3v3h-3v-3H8v3H5v-5H2v-5h2zM7 5h7M10 3v4M18 9l2-3M7 12h.1"/>',
  loan: '<path d="M12 3 2 8h20L12 3ZM4 21h16M5 9v9M10 9v9M15 9v9M20 9v9M3 18h18"/>',
  support:
    '<path d="M4 12V9a8 8 0 0 1 16 0v3M4 10H2v8h4v-8H4ZM20 10h2v8h-4v-8h2ZM20 18v3h-6"/>',
  shield:
    '<path d="m12 2 8 3v6c0 5-8 11-8 11S4 16 4 11V5l8-3Z"/><path d="m8 11 3 3 5-6"/>',
  location:
    '<path d="M20 9c0 6-8 13-8 13S4 15 4 9a8 8 0 1 1 16 0Z"/><circle cx="12" cy="9" r="2.5"/>',
  external: '<path d="M14 3h7v7M21 3l-11 11M10 3H3v18h18v-7"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.1M3 12h.1M3 18h.1"/>',
  search: '<circle cx="10" cy="10" r="7"/><path d="m16 16 6 6"/>',
  menu: '<path d="M3 5h18M3 12h18M3 19h18"/>',
  settings:
    '<path d="M3 6h18M3 12h18M3 18h18"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
  arrow: '<path d="M12 20V4M5 11l7-7 7 7"/>',
  spark: '<path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7Z"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  import: '<path d="M12 3v12m-5-5 5 5 5-5M3 17v4h18v-4"/>',
};
function icon(name) {
  const e = document.createElement("span");
  e.className = "icon";
  e.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.chat}</svg>`;
  return e;
}
function el(tag, className = "", text) {
  const e = document.createElement(tag);
  e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}
function t(zh, en) {
  return S.lang === "zh" ? zh : en;
}
function hasStaffAccess() {
  return (
    S.boot?.portal_role === "staff" &&
    !!(S.boot?.user?.is_admin || S.boot?.user?.is_staff)
  );
}
const identityChannel =
  typeof BroadcastChannel !== "undefined"
    ? new BroadcastChannel("campusbank-identity")
    : null;
if (identityChannel) identityChannel.onmessage = () => refreshSessionIdentity();
async function refreshSessionIdentity() {
  if (!S.boot) return;
  if (S.busy) {
    S.pendingIdentityRefresh = true;
    return;
  }
  S.pendingIdentityRefresh = false;
  try {
    const next = await api("/api/bootstrap");
    const changedUser = next.user?.id !== S.boot.user?.id;
    S.boot = next;
    if (changedUser) {
      S.current = null;
      setChatUrl(null);
    }
    await refreshHistory();
    renderSidebar();
    if (hasStaffAccess()) await showStaff();
    else if (changedUser || S.view === "staff") showChat();
  } catch (e) {
    toast(e.message);
  }
}
function button(text, className, fn) {
  const b = el("button", className, text);
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
}
function toast(text) {
  $("toast").textContent = text;
  $("toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("toast").hidden = true), 3500);
}
async function api(path, method = "GET", body) {
  const headers = { "Content-Type": "application/json", "Accept-Language": S.lang };
  if (S.boot?.csrf) headers["X-CSRF-Token"] = S.boot.csrf;
  let r;
  try { r = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  }); } catch {
    const error = Error(t("网络连接中断，请检查网络后重试；填写内容已保留。", "Connection interrupted. Check your network and retry; your input is preserved."));
    error.retryable = true;
    throw error;
  }
  let data;
  try {
    data = await r.json();
  } catch {
    throw Error(t("服务暂时不可用", "Service unavailable"));
  }
  if (!r.ok) {
    const error = Error(
      typeof data.detail === "string"
        ? data.detail
        : t("请检查填写内容后重试", "Please check the form"),
    );
    error.status = r.status;
    error.retryAfter = r.status === 429 ? Number(data.retry_after || r.headers?.get?.("Retry-After") || 60) : 0;
    error.retryable = r.status >= 500 || r.status === 429;
    throw error;
  }
  return data;
}
function setChatUrl(id) {
  const u = new URL(location.href);
  if (id) u.searchParams.set("chat", id);
  else u.searchParams.delete("chat");
  history.replaceState(null, "", u);
}
function closeMobile() {
  $("sidebar").classList.remove("open");
}
function busy(value) {
  S.busy = value;
  $("sendButton").disabled = value || S.cooldownUntil > Date.now();
  $("messageInput").disabled = value;
}
function timeText(value) {
  return new Date(value).toLocaleString(S.lang === "zh" ? "zh-CN" : "en-GB", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
function statusText(value) {
  return (
    {
      pending: t("待审核", "Pending"),
      processing: t("处理中", "Processing"),
      completed: t("已完成", "Completed"),
      needs_info: t("待补充材料", "More information needed"),
      waiting: t("等待接单", "Waiting"),
      active: t("客服处理中", "Active"),
      resolved: t("已结束", "Resolved"),
    }[value] || value
  );
}
function escapeHTML(v) {
  return String(v)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
function inline(v) {
  return escapeHTML(v)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}
function tableCells(line) {
  let value = line.trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|") && !value.endsWith("\\|")) value = value.slice(0, -1);
  const cells = []; let cell = "", ticks = false;
  for (let i = 0; i < value.length; i++) {
    if (value[i] === "\\" && value[i + 1] === "|") { cell += "|"; i++; }
    else if (value[i] === "`") { ticks = !ticks; cell += value[i]; }
    else if (value[i] === "|" && !ticks) { cells.push(cell.trim()); cell = ""; }
    else cell += value[i];
  }
  cells.push(cell.trim());
  return cells;
}
function tableSeparator(line) {
  const cells = tableCells(line || "");
  return cells.length >= 2 && cells.every(c => /^:?-{3,}:?$/.test(c));
}
function markdown(text) {
  const root = el("div");
  let list = null,
    code = null, tableFence = false;
  const lines = String(text).replaceAll("\r\n", "\n").split("\n");
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    if (/^```(?:markdown|md)?\s*$/i.test(line) && (tableFence || tableSeparator(lines[index + 2]))) {
      tableFence = !tableFence; list = null; continue;
    }
    if (line.startsWith("```")) {
      if (code) {
        code = null;
      } else {
        code = el("pre");
        const c = el("code");
        code.append(c);
        root.append(code);
      }
      list = null;
      continue;
    }
    if (code) {
      code.firstChild.textContent += line + "\n";
      continue;
    }
    if (line.includes("|") && tableSeparator(lines[index + 1])) {
      const headers = tableCells(line), separators = tableCells(lines[index + 1]);
      if (headers.length === separators.length) {
        list = null;
        const wrap = el("div", "answer-table-wrap");
        wrap.tabIndex = 0;
        wrap.setAttribute("role", "region");
        wrap.setAttribute("aria-label", t("信息对比表，可横向滚动", "Comparison table; scroll horizontally"));
        const table = el("table", "answer-table"), head = el("thead"), row = el("tr"), body = el("tbody");
        headers.forEach((value, col) => {
          const cell = el("th"); cell.scope = "col"; cell.innerHTML = inline(value);
          const align = separators[col]; cell.dataset.align = align.startsWith(":") && align.endsWith(":") ? "center" : align.endsWith(":") ? "right" : "left";
          row.append(cell);
        });
        head.append(row); table.append(head, body); index += 2;
        while (index < lines.length && lines[index].trim() && lines[index].includes("|") && !lines[index].startsWith("```")) {
          const values = tableCells(lines[index]), tr = el("tr");
          // Extra separators in malformed content stay visible in the final cell.
          const normalized = headers.map((_, c) => c === headers.length - 1 ? values.slice(c).join(" | ") : (values[c] || ""));
          normalized.forEach((value, col) => { const cell = el(col === 0 ? "th" : "td"); if (col === 0) cell.scope = "row"; cell.innerHTML = inline(value); cell.dataset.align = row.children[col].dataset.align; tr.append(cell); });
          body.append(tr); index++;
        }
        index--; wrap.append(table); root.append(wrap, el("p", "table-hint", t("左右滑动查看完整表格", "Swipe horizontally to see the full table"))); continue;
      }
    }
    if (!line.trim()) {
      list = null;
      continue;
    }
    const quote=line.match(/^\s*>\s?(.*)$/);
    if(quote){list=null;const note=el('blockquote','answer-note');note.innerHTML=inline(quote[1]);root.append(note);continue;}
    const item = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)$/);
    if (item) {
      const ordered = /^\s*\d+\./.test(line);
      if (!list || list.tagName !== (ordered ? "OL" : "UL")) {
        list = el(ordered ? "ol" : "ul");
        root.append(list);
      }
      const li = el("li");
      li.innerHTML = inline(item[1]);
      list.append(li);
    } else {
      list = null;
      const h = line.match(/^#{1,4}\s+(.*)$/);
      if (h) root.append(el("h3", "", h[1]));
      else if (!/^---+$/.test(line)) {
        const p = el("p");
        p.innerHTML = inline(line);
        root.append(p);
      }
    }
  }
  return root;
}
function servicesFor(category) {
  return S.boot.services.filter((s) => s.category === category);
}
function updateBankModeUI() {
  const student=S.bankMode==='student';
  $("generalBankMode").textContent=t("社会银行","General banking");
  $("studentBankMode").textContent=t("学生银行","Student banking");
  $("generalBankMode").classList.toggle("active",!student);
  $("studentBankMode").classList.toggle("active",student);
  $("generalBankMode").setAttribute("aria-pressed",String(!student));
  $("studentBankMode").setAttribute("aria-pressed",String(student));
  $("bankModeHint").textContent=student?t("账户、学费与学习生活支持","Accounts, tuition and student support"):t("日常生活与个人金融服务","Everyday and personal finance");
  document.body.dataset.bankMode=S.bankMode;
  localStorage.setItem("campusbank_bank_mode",S.bankMode);
  updateGeneralTheme();
}
function updateGeneralTheme() {
  const labels={blue:['亮蓝','Blue'],ruby:['酒红','Ruby'],violet:['紫色','Violet'],navy:['深蓝','Navy']};
  if(!labels[S.generalTheme])S.generalTheme='ruby';
  document.body.dataset.generalTheme=S.generalTheme;
  const picker=$('generalThemePicker');picker.hidden=S.bankMode==='student';
  picker.setAttribute('aria-label',t('社会银行配色','General banking colours'));
  $('themePickerLabel').textContent=t('配色预览','Try a colour');
  for(const b of picker.querySelectorAll('button')){
    const [zh,en]=labels[b.dataset.theme];b.textContent=t(zh,en);
    b.setAttribute('aria-label',t(zh+'配色',en+' theme'));
    b.setAttribute('aria-pressed',String(b.dataset.theme===S.generalTheme));
    b.onclick=()=>{S.generalTheme=b.dataset.theme;localStorage.setItem('campusbank_general_theme',S.generalTheme);updateGeneralTheme();};
  }
}
async function switchBankMode(mode) {
  if (S.busy || S.bankMode===mode) return;
  S.bankMode=mode;updateBankModeUI();renderSidebar();
  await newChat();
}
function serviceBy(id) {
  return S.boot.services.find((s) => s.id === id);
}
function updateIdentity() {
  const u = S.boot.user;
  $("profileAvatar").textContent = u ? u.display_name[0] || "U" : t("访", "G");
  $("profileName").replaceChildren(
    document.createTextNode(
      u ? u.display_name : t("登录 / 注册", "Sign in / Register"),
    ),
    el(
      "small",
      "",
      u
        ? "@" + u.username
        : t("保存个人对话与办理记录", "Keep chats and requests"),
    ),
  );
  $("staffNav").hidden = !hasStaffAccess();
  $("legacyImport").hidden = !hasStaffAccess() || !u?.is_admin;
  $("supportHistoryNav").hidden = S.boot?.portal_role === "staff";
  $("onlineIndicator").textContent = S.boot.api_available
    ? t("自然对话 · 已连接", "AI connected")
    : t("离线应急", "Offline");
}
function renderSidebar() {
  const nav = $("businessNav");
  nav.replaceChildren();
  for (const c of S.boot.categories) {
    if (c.modes && !c.modes.includes(S.bankMode)) continue;
    const b = button("", "", () => showServices(c.id));
    b.append(icon(c.icon), document.createTextNode(t(c.name, c.en)));
    nav.append(b);
  }
  renderHistory();
  updateIdentity();
}
function renderHistory() {
  const container = $("historyList");
  container.replaceChildren();
  const search = $("historySearch").value.toLowerCase();
  const items = S.chats.filter((c) => c.title.toLowerCase().includes(search));
  if (!items.length) {
    container.append(
      el(
        "p",
        "muted tiny",
        search ? t("没有匹配的对话。", "No matching conversations.") : t(
          "开始一段对话，它会保留在这里。",
          "Your conversations will appear here.",
        ),
      ),
    );
    return;
  }
  let group = "";
  for (const c of items) {
    const today =
      new Date(c.updated_at).toDateString() === new Date().toDateString();
    const label = t(today ? "今天" : "之前", today ? "Today" : "Earlier");
    if (group !== label) {
      container.append(el("div", "history-group", label));
      group = label;
    }
    const row = el(
      "div",
      "history-entry" + (S.current?.id === c.id ? " active" : ""),
    );
    const b = button(c.title, "", () => selectChat(c.id));
    b.title = c.title;
    const rename = button("···", "rename", async () => {
      const title = prompt(t("重命名对话", "Rename conversation"), c.title);
      if (title?.trim()) {
        try {
          await api("/api/chats/" + c.id, "PATCH", { title: title.trim() });
          await refreshHistory();
          if (S.current?.id === c.id) S.current.title = title.trim();
        } catch (e) {
          toast(e.message);
        }
      }
    });
    rename.setAttribute(
      "aria-label",
      t("重命名 " + c.title, "Rename " + c.title),
    );
    row.append(b, rename);
    container.append(row);
  }
}
async function refreshHistory() {
  S.chats = await api("/api/chats");
  renderHistory();
}
function title(value) {
  $("pageTitle").textContent = value;
  document
    .querySelectorAll(".primary-nav button")
    .forEach((b) => b.classList.remove("active"));
}
function showComposer(value) {
  $("composerArea").hidden = !value;
}
function showChat(scroll = true) {
  S.view = "chat";
  closeMobile();
  title(t("智能咨询", "Banking assistant"));
  $("homeNav").classList.add("active");
  showComposer(true);
  renderChat(scroll);
  renderHistory();
}
async function selectChat(id) {
  if (S.busy) return;
  try {
    S.current = await api("/api/chats/" + id);
    S.bankMode=S.current.bank_mode || 'general';updateBankModeUI();renderSidebar();
    setChatUrl(id);
    showChat();
  } catch (e) {
    toast(e.message);
  }
}
async function newChat() {
  if (S.busy) return;
  busy(true);
  try {
    S.current = await api("/api/chats", "POST", {bank_mode:S.bankMode});
    setChatUrl(S.current.id);
    await refreshHistory();
    showChat();
  } catch (e) {
    toast(e.message);
  } finally {
    busy(false);
    $("messageInput").focus();
  }
}
async function ensureChat() {
  if (!S.current) {
    S.current = await api("/api/chats", "POST", {bank_mode:S.bankMode});
    setChatUrl(S.current.id);
    await refreshHistory();
  }
  return S.current;
}
async function startHandoff() {
  if (S.handoffBusy || S.busy) return;
  if (!S.boot.user) {
    openAuth("login", startHandoff);
    return;
  }
  S.handoffBusy = true;
  $("handoffButton").disabled = true;
  try {
    const chat = await ensureChat();
    const result = await api("/api/chats/" + chat.id + "/handoff", "POST");
    S.current = result.chat;
    setChatUrl(S.current.id);
    await refreshHistory();
    showChat();
    toast(
      result.existing
        ? t("已在人工客服队列中", "Already in the support queue")
        : t(
            "已转人工，工作人员将收到当前对话",
            "Sent to staff with your conversation",
          ),
    );
  } catch (e) {
    toast(e.message);
  } finally {
    S.handoffBusy = false;
    if (S.view === "chat") renderChat(false);
  }
}
function renderWelcome() {
  const root = el("div", "welcome");
  root.append(
    el(
      "div",
      "greeting",
      S.bankMode==='student'?t("从账户到学费，一起规划学生生活","From accounts to tuition: plan student life"):t("你好，让办理变得更简单", "Hello, let’s make banking simpler"),
    ),
    el("h1", "", t("今天有什么可以帮你？", "How can I help you today?")),
    el(
      "p",
      "",
      t(
        "直接描述你的需要。我们可以一起了解要求，然后进入对应的在线服务窗口。",
        "Describe what you need. We can explore your options and open the right service window.",
      ),
    ),
  );
  const suggestions = el("div", "suggestions");
  const items = S.bankMode==='student' ? [
    ["wallet","我要开学生账户","Open a student account","open_account"],
    ["loan","助学贷款需要什么条件？","What are the student loan requirements?","education_loan"],
    ["savings","查询奖学金项目","Find scholarship programs","funding_enquiry"],
    ["support","学费和生活费有哪些补助？","What grants support tuition and living costs?","funding_enquiry"],
    ["transfer","国际转账费用是多少？","What are international transfer fees?","transfer_demo"],
    ["location","预约网点咨询学生业务","Book a student banking visit","branch_appointment"],
  ] : [
    ["wallet", "我想开日常账户", "Open an everyday account", "open_account"],
    ["card", "银行卡丢了怎么办", "Help with a lost card", "replace_card"],
    ["transfer", "了解网上转账费用", "Online transfer fees", "transfer_demo"],
    ["savings", "看看储蓄账户", "Explore savings", "open_savings"],
    ["loan", "个人贷款怎么申请", "Apply for a loan", "apply_loan"],
    ["location", "预约附近的网点", "Book a branch visit", "branch_appointment"],
  ];
  for (const [i, zh, en, id] of items) {
    const b = button("", "suggestion", () => {
      const s = serviceBy(id);
      $("messageInput").value = t(zh, en);
      sendMessage();
    });
    b.append(
      icon(i),
      el("strong", "", t(zh, en)),
      el("small", "", t("咨询并获取服务入口", "Ask and find a service")),
    );
    suggestions.append(b);
  }
  root.append(suggestions);
  const cap = el("div", "welcome-caption");
  cap.append(
    icon("shield"),
    document.createTextNode(
      t(
        "咨询、办理入口和历史记录，在一个地方。",
        "Advice, service windows and chat history in one place.",
      ),
    ),
  );
  root.append(cap);
  return root;
}
function renderMessage(m) {
  const meta = m.metadata || {};
  const row = el(
    "article",
    "message " + m.role + (meta.sender === "staff" ? " staff" : ""),
  );
  if (m.role !== "user")
    row.append(
      el(
        "div",
        "assistant-avatar",
        meta.sender === "staff" ? t("人", "H") : "C",
      ),
    );
  const body = el("div", "message-body");
  body.append(markdown(m.streaming ? stableStreamMarkdown(m.content) : m.content));
  if(m.streaming){body.append(el('span','streaming-cursor','▍'));row.append(body);return row;}
  if (m.role !== "user") {
    const actions = el("div", "service-actions");
    for (const action of meta.actions || []) {
      const service = serviceBy(action.service_id);
      if (!service) continue;
      const b = button("", "service-action", () => {
        if (service.id === "human_support") startHandoff();
        else openService(service.id, action.prefill || {});
      });
      b.append(
        icon(service.icon),
        document.createTextNode(
          service.id === "human_support"
            ? t("转接人工客服", "Talk to staff")
            : t("进入" + service.title, "Open " + service.en),
        ),
        icon("chevron"),
      );
      actions.append(b);
    }
    if (actions.childNodes.length) body.append(actions);
    const latest=S.current?.messages?.filter(x=>x.role==='assistant').at(-1);
    if (meta.followups?.length && latest===m && !S.current?.ticket) {
      const suggestions=el("div","followup-suggestions");
      suggestions.append(el("p","followup-heading",meta.response_language==='en'?"You may also want to ask":"你可能还想了解"));
      for (const question of meta.followups.slice(0,3)) {
        const chip=button(question,"followup-chip",()=>{ if(S.busy)return; $("messageInput").value=question; sendMessage(); });
        chip.disabled=S.busy;suggestions.append(chip);
      }
      body.append(suggestions);
    }
    const foot = el("div", "message-meta");
    if (meta.sender === "staff")
      foot.append(
        el(
          "span",
          "",
          t("人工客服（演示）", "Demo staff") +
            (meta.staff_name ? " · " + meta.staff_name : ""),
        ),
      );
    else if (meta.error)
      foot.append(el("span", "", t("离线应急回答", "Offline fallback")));
    const copy = button(t("复制", "Copy"), "copy-button", () =>
      navigator.clipboard
        .writeText(m.content)
        .then(() => toast(t("已复制", "Copied"))),
    );
    foot.append(copy);
    body.append(foot);
    if (S.debug) {
      const d = el("details", "source-details");
      d.append(
        el("summary", "", t("资料与工具详情", "Sources and tools")),
        el("pre", "", JSON.stringify(meta, null, 2)),
      );
      body.append(d);
    }
  }
  row.append(body);
  return row;
}
function renderChat(scroll = true) {
  const content = $("content");
  content.replaceChildren();
  if (!S.current?.messages?.length) content.append(renderWelcome());
  else {
    const list = el("div", "message-list");
    for (const m of S.current.messages) list.append(renderMessage(m));
    if(S.streaming?.chatId===S.current.id && S.streaming.shown){
      list.append(renderMessage({role:'assistant',content:S.streaming.shown,metadata:{},streaming:true}));
    }else if (S.busy) {
      const pending = el("article", "message assistant");
      pending.append(
        el("div", "assistant-avatar", "C"),
        el(
          "div",
          "thinking",
          S.streaming?.status || t("正在理解你的问题", "Thinking about your request"),
        ),
      );
      list.append(pending);
    }
    content.append(list);
  }
  const ticket = S.current?.ticket;
  $("handoffButton").disabled = !!ticket || S.handoffBusy;
  $("handoffButton").textContent = ticket
    ? t("已转人工", "In support queue")
    : t("转人工客服", "Talk to staff");
  const banner = $("handoffBanner");
  banner.hidden = !ticket;
  banner.replaceChildren();
  if (ticket) {
    banner.append(
      el(
        "span",
        "",
        t("人工客服队列 · ", "Support queue · ") + statusText(ticket.status),
      ),
      button(t("返回 AI 咨询", "Return to AI"), "", async () => {
        try {
          await api("/api/tickets/" + ticket.id + "/resume-ai", "POST");
          S.current = await api("/api/chats/" + S.current.id);
          renderChat(false);
        } catch (e) {
          toast(e.message);
        }
      }),
    );
  }
  if (scroll)
    requestAnimationFrame(
      () => ($("scrollArea").scrollTop = S.current?.messages?.length ? $("scrollArea").scrollHeight : 0),
    );
}
async function sendMessage() {
  const text = $("messageInput").value.trim();
  if (!text || S.busy) return;
  if (S.cooldownUntil > Date.now()) return;
  if (S.boot.requires_login && !S.boot.user) {
    openAuth("login", sendMessage);
    return;
  }
  busy(true);
  try {
    await ensureChat();
    showChat(false);
    $("messageInput").value = "";
    S.current.messages.push({ role: "user", content: text, metadata: {} });
    renderChat(true);
    const retry = S.retryMessage;
    const requestId = retry?.chatId === S.current.id && retry.text === text ? retry.id : crypto.randomUUID().replaceAll("-", "");
    S.retryMessage = {chatId:S.current.id, text, id:requestId};
    S.streaming={chatId:S.current.id,target:'',shown:'',timer:null,status:''};
    const finalChat = await requestStream("/api/chats/" + S.current.id, {
      text,
      mode: S.mode,
      bank_mode:S.current?.bank_mode || S.bankMode,
      request_id: requestId,
    },handleStreamEvent);
    const finalAnswer=finalChat.messages?.filter(m=>m.role==='assistant').at(-1)?.content || '';
    finishStreamText(finalAnswer);
    await waitForReveal();
    S.current=finalChat;S.streaming=null;
    S.retryMessage = null;
    $("sendFeedback").hidden = true;
    await refreshHistory();
  } catch (e) {
    if(S.streaming?.timer)clearTimeout(S.streaming.timer);S.streaming=null;
    toast(e.message);
    showSendFeedback(e);
    if (!$("messageInput").value) $("messageInput").value = text;
    if (S.current) {
      try {
        S.current = await api("/api/chats/" + S.current.id);
      } catch {}
    }
  } finally {
    busy(false);
    if (S.view === "chat") renderChat(true);
    $("messageInput").focus();
    if (S.pendingIdentityRefresh) await refreshSessionIdentity();
  }
}
function stableStreamMarkdown(text) {
  const lines=String(text).split('\n');let table=false;
  for(let i=0;i<lines.length;i++){
    if(tableSeparator(lines[i])){table=true;continue;}
    if(!lines[i].trim())table=false;
    if(!table&&lines[i].trim().startsWith('|')&&(!lines[i+1]||/^\s*[|:\-\s]*$/.test(lines[i+1])&&!tableSeparator(lines[i+1])))return lines.slice(0,i).join('\n');
  }
  // Do not briefly flash a bare heading/list marker before its text arrives.
  if(/^\s*(?:#{1,6}|[-*+] |\d+[.)] )\s*$/.test(lines.at(-1)))lines.pop();
  return lines.join('\n');
}
function handleStreamEvent(event) {
  const stream=S.streaming;if(!stream)return;
  if(event.type==='delta'){stream.target+=event.text || '';scheduleReveal();}
  else if(event.type==='replace'){stream.target=event.text || '';stream.shown='';scheduleReveal();}
  else if(event.type==='status'){stream.status=event.text || '';if(!stream.shown)renderChat(false);}
}
function scheduleReveal() {
  const stream=S.streaming;if(!stream||stream.timer)return;
  const step=()=>{
    stream.timer=null;if(S.streaming!==stream)return;
    const remaining=stream.target.length-stream.shown.length;
    if(remaining<=0)return;
    const amount=Math.min(32,Math.max(3,Math.ceil(remaining/18)));
    let end=Math.min(stream.target.length,stream.shown.length+amount);
    if(end<stream.target.length && /[\uD800-\uDBFF]/.test(stream.target[end-1]))end++;
    stream.shown=stream.target.slice(0,end);
    const area=$('scrollArea');const atBottom=area.scrollHeight-area.scrollTop-area.clientHeight<100;
    if(S.view==='chat')renderChat(atBottom);
    if(stream.shown.length<stream.target.length)stream.timer=setTimeout(step,24);
  };
  stream.timer=setTimeout(step,16);
}
function finishStreamText(answer) {
  const stream=S.streaming;if(!stream)return;
  if(!answer.startsWith(stream.shown))stream.shown='';
  stream.target=answer;scheduleReveal();
}
async function waitForReveal() {
  while(S.streaming && S.streaming.shown!==S.streaming.target)await new Promise(resolve=>setTimeout(resolve,24));
}
async function requestStream(chatPath,body,onEvent) {
  // Older browsers can still use the original endpoint with the same reveal UI.
  if(!window.ReadableStream || !window.TextDecoder)return api(chatPath+'/messages','POST',body);
  const headers={'Content-Type':'application/json','Accept':'text/event-stream','Accept-Language':S.lang};
  if(S.boot?.csrf)headers['X-CSRF-Token']=S.boot.csrf;
  let response;
  try{response=await fetch(chatPath+'/stream',{method:'POST',headers,credentials:'same-origin',body:JSON.stringify(body)});}
  catch{throw Error(t('网络连接中断，问题已保留，可稍后重试。','Connection interrupted. Your question is preserved; retry shortly.'));}
  if(!response.ok){const data=await response.json();const error=Error(typeof data.detail==='string'?data.detail:t('请检查填写内容后重试','Please check the form'));error.status=response.status;error.retryAfter=data.retry_after || (response.status===429?60:0);throw error;}
  if(!response.body?.getReader)return response.json();
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',result=null;
  function packet(block){
    const payload=block.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trim()).join('\n');
    if(!payload)return;
    const event=JSON.parse(payload);
    if(event.type==='error'){const error=Error(event.detail || t('回答中断，请稍后重试。','The answer was interrupted. Please retry.'));error.status=event.status;error.retryAfter=event.retry_after || 0;throw error;}
    if(event.type==='complete')result=event.chat;else onEvent(event);
  }
  try{
    while(true){
      const {value,done}=await reader.read();buffer+=decoder.decode(value || new Uint8Array(),{stream:!done});buffer=buffer.replaceAll('\r\n','\n');
      let split;while((split=buffer.indexOf('\n\n'))>=0){packet(buffer.slice(0,split));buffer=buffer.slice(split+2);}
      if(done)break;
    }
    if(buffer.trim())packet(buffer);
    if(!result)throw Error(t('回答连接中断，请刷新记录或重试；问题已保留。','The answer connection ended early. Refresh history or retry; your question is preserved.'));
    return result;
  }catch(error){
    if(error.status)throw error;
    throw Error(t('回答连接中断，请刷新记录或重试；问题已保留。','The answer connection ended early. Refresh history or retry; your question is preserved.'));
  }finally{reader.releaseLock();}
}
function showSendFeedback(error) {
  const root = $("sendFeedback");
  clearTimeout(S.cooldownTimer);
  if (error.retryAfter) S.cooldownUntil = Date.now() + Math.min(120, Math.max(1, error.retryAfter)) * 1000;
  root.hidden = false;
  const tick = () => {
    root.replaceChildren();
    const seconds = Math.max(0, Math.ceil((S.cooldownUntil - Date.now()) / 1000));
    root.append(el("span", "", seconds ? t(`请等待 ${seconds} 秒后重试，问题已保留。`, `Retry in ${seconds}s; your question is preserved.`) : error.message));
    const retry = button(t("重试发送", "Retry sending"), "text-button", () => { root.hidden = true; sendMessage(); });
    retry.disabled = !!seconds || S.busy;
    root.append(retry);
    $("sendButton").disabled = S.busy || !!seconds;
    if (seconds) S.cooldownTimer = setTimeout(tick, 1000);
  };
  tick();
}
function showServices(category) {
  if (S.busy) return;
  S.view = "services";
  S.category = category;
  closeMobile();
  showComposer(false);
  const c = S.boot.categories.find((c) => c.id === category);
  title(c ? t(c.name, c.en) : t("在线服务中心", "Service centre"));
  const page = el("section", "page-section");
  page.append(
    el("h1", "", c ? t(c.name, c.en) : t("在线服务中心", "Online services")),
    el(
      "p",
      "page-subtitle",
      t(
        "选择业务即可进入服务窗口。填写、核对、提交后，可在“我的办理记录”查看进度。",
        "Choose a service, review the details and save a demo request. Track its progress under My requests.",
      ),
    ),
  );
  const grid = el("div", "service-grid");
  for (const s of c ? servicesFor(c.id) : S.boot.services) {
    const b = button("", "service-card", () => openService(s.id));
    b.append(
      icon(s.icon),
      el("h3", "", t(s.title, s.en)),
      el("p", "", t(s.description, s.description_en || s.en)),
      el("span", "card-link", t("进入服务窗口 →", "Open service window →")),
    );
    grid.append(b);
  }
  page.append(grid);
  $("content").replaceChildren(page);
  $("scrollArea").scrollTop = 0;
}
async function showRequests() {
  if (S.busy) return;
  S.view = "requests";
  closeMobile();
  showComposer(false);
  title(t("我的办理记录", "My requests"));
  $("requestsNav").classList.add("active");
  const page = el("section", "page-section");
  page.append(
    el("h1", "", t("每一步，都有记录", "Your service progress")),
    el(
      "p",
      "page-subtitle",
      t(
        "查看你的演示申请、预约与客服工单。",
        "Track your demo applications, appointments and support tickets.",
      ),
    ),
  );
  if (!S.boot.user) {
    page.append(
      el(
        "div",
        "empty-state",
        t(
          "登录个人账户后，可保存并查看办理记录。",
          "Sign in to save and track requests.",
        ),
      ),
      button(t("登录 / 注册", "Sign in / Register"), "primary-button", () =>
        openAuth("login", showRequests),
      ),
    );
    $("content").replaceChildren(page);
    return;
  }
  try {
    const records = await api("/api/requests");
    if (!records.length)
      page.append(
        el(
          "div",
          "empty-state",
          t(
            "还没有办理记录。可以从左侧业务入口开始。",
            "No requests yet. Choose a service in the sidebar.",
          ),
        ),
      );
    for (const r of records) {
      const wrap = el("div");
      const row = el("div", "request-row");
      row.append(icon(serviceBy(r.service_id)?.icon));
      const main = el("div", "request-main");
      main.append(
        el("strong", "", t(r.title, serviceBy(r.service_id)?.en || r.title)),
        el("small", "", r.id + " · " + timeText(r.created_at)),
      );
      row.append(main, el("span", "status " + r.status, statusText(r.status)));
      wrap.append(row);
      const d = el("details", "request-details");
      d.append(el("summary", "", t("查看登记信息", "View request details")));
      for (const f of serviceBy(r.service_id).fields) {
        const value = r.payload[f.name];
        if (value === undefined || value === "") continue;
        d.append(
          el(
            "div",
            "",
            fieldLabel(f) +
              "：" +
              (typeof value === "boolean"
                ? value
                  ? t("已确认", "Confirmed")
                  : "—"
                : optionLabel(f, value)),
          ),
        );
      }
      if(r.scenario)d.append(scenarioTable(r.scenario));
      wrap.append(d);
      if (r.staff_note) wrap.append(el("p","staff-review-note",t("工作人员备注：","Staff note: ")+r.staff_note));
      page.append(wrap);
    }
  } catch (e) {
    toast(e.message);
  }
  $("content").replaceChildren(page);
}
async function showSupportHistory() {
  if (S.busy) return;
  if (!S.boot.user) {
    openAuth("login", showSupportHistory);
    return;
  }
  S.view = "supportHistory";
  closeMobile();
  showComposer(false);
  title(t("人工客服记录", "Support history"));
  $("supportHistoryNav").classList.add("active");
  try {
    const tickets = await api("/api/support-tickets");
    if (S.view !== "supportHistory") return;
    const page = el("section", "page-section");
    page.append(
      el("h1", "", t("我的人工客服记录", "My support history")),
      el(
        "p",
        "page-subtitle",
        t(
          "查看你发起的工单、咨询历史和人工回复。需要补充问题时，可进入原对话。",
          "View your tickets, questions and staff replies. Open the original chat to add information.",
        ),
      ),
    );
    if (!tickets.length)
      page.append(
        el(
          "div",
          "empty-state",
          t(
            "还没有人工客服工单，可在聊天中点击转人工客服。",
            "No support tickets yet. Use Talk to staff in your chat.",
          ),
        ),
      );
    for (const ticket of tickets) {
      const row = el("div", "request-row"),
        body = el("div", "request-main");
      body.append(el("strong", "", ticket.subject), el("small", "", ticket.id));
      row.append(
        icon("support"),
        body,
        el("span", "status " + ticket.status, statusText(ticket.status)),
        button(t("查看记录", "View history"), "secondary-button", () =>
          showCustomerTicket(ticket.id),
        ),
      );
      page.append(row);
    }
    $("content").replaceChildren(page);
  } catch (e) {
    toast(e.message);
  }
}
async function showCustomerTicket(id) {
  S.view = "supportDetail";
  S.supportTicketId = id;
  closeMobile();
  showComposer(false);
  title(t("人工客服记录", "Support history"));
  try {
    const data = await api("/api/support-tickets/" + id);
    if (S.view !== "supportDetail" || S.supportTicketId !== id) return;
    const page = el("section", "page-section"),
      ticket = data.ticket;
    page.append(
      button(
        t("返回工单列表", "Back to tickets"),
        "secondary-button",
        showSupportHistory,
      ),
      el("h1", "", ticket.subject),
      el("p", "muted small", ticket.description),
      el("span", "status " + ticket.status, statusText(ticket.status)),
    );
    if (ticket.assigned_name)
      page.append(
        el(
          "p",
          "muted small",
          t("工作人员：", "Staff: ") + ticket.assigned_name,
        ),
      );
    const transcript = el("div", "staff-transcript");
    for (const m of data.chat?.messages || []) {
      const line = el("div");
      line.append(
        el(
          "strong",
          "",
          m.role === "user"
            ? t("你：", "You: ")
            : m.metadata?.sender === "staff"
              ? t("人工客服：", "Staff: ")
              : t("助手：", "Assistant: "),
        ),
        markdown(m.content),
      );
      transcript.append(line);
    }
    page.append(
      transcript,
      el(
        "p",
        "muted small",
        t(
          "这里只显示咨询记录和收到的回复。",
          "This view shows your questions and the replies you received.",
        ),
      ),
    );
    if (data.chat)
      page.append(
        button(
          t("查看原对话 / 补充问题", "Open chat / add information"),
          "primary-button",
          () => selectChat(data.chat.id),
        ),
      );
    $("content").replaceChildren(page);
  } catch (e) {
    toast(e.message);
  }
}
function showReferences() {
  S.view = "references";
  closeMobile();
  showComposer(false);
  title(t("银行官网参考", "Official bank references"));
  const page = el("section", "page-section");
  page.append(
    el("h1", "", t("我们参考的银行服务体验", "Banking experiences we studied")),
    el(
      "p",
      "page-subtitle",
      t(
        "以下链接指向银行官方页面，用于了解业务分类、数字助手和服务入口。本站办理流程属于 CampusBank 课程演示。",
        "Official bank pages for navigation, digital assistants and service entry points. CampusBank forms are fictional coursework flows.",
      ),
    ),
  );
  const list = el("div", "reference-list");
  for (const r of S.boot.bank_references) {
    const a = el("a", "reference-card");
    a.href = r.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    const body = el("div");
    body.append(el("strong", "", t(r.name,r.name_en || r.name)), el("small", "", t(r.detail,r.detail_en || r.detail)));
    a.append(body, icon("external"));
    list.append(a);
  }
  page.append(list);
  $("content").replaceChildren(page);
}
function fieldLabel(f) {
  const en = {
    product: "Account type",
    applicant: "Demo applicant name",
    channel: "Application channel",
    documents_ready: "I have reviewed the demo document requirements",
    card_type: "Card type",
    linked_product: "Linked account",
    purpose: "Purpose",
    reviewed: "I have reviewed the demo requirements",
    reason: "Reason",
    action: "Requested service",
    note: "Additional notes",
    transfer_type: "Transfer type",
    recipient: "Demo recipient nickname",
    amount: "Demo amount (GBP)",
    opening_deposit: "Demo opening deposit (GBP, minimum 10)",
    city: "City",
    date: "Requested visit date",
    category: "Issue category",
    subject: "Subject",
    description: "Describe your request",
  };
  return t(f.label, f.label_en || en[f.name] || f.label);
}
function optionLabel(field, value) {
  const option = field.options?.find(o => o.value === value);
  return option ? t(option.label, option.label_en || option.value.replaceAll("_", " ")) : value;
}
function draftKey(id) { return `${S.boot.user?.id || "guest"}:${S.current?.id || "none"}:${id}`; }
function scenarioDefaults(service,base) {
  if(!service.scenario)return null;
  const values=Object.fromEntries(service.scenario.fields.map(f=>[f.name,f.default]));
  if(service.id==='open_account' && base.product==='student_account')Object.assign(values,{profile:'student_demo',employment:'student',account_purpose:'study',funding_source:'family'});
  if(service.id==='transfer_demo') {
    if(S.bankMode==='student')values.payer='student_demo';
    if(base.transfer_type==='international')Object.assign(values,{payee_profile:'europe_demo',payee_name:'Example EU College'});
  }
  return values;
}
function scenarioTable(record,compact=false) {
  const wrap=el('section','scenario-summary');
  wrap.append(el('h3','',t('场景核对明细','Scenario review details')));
  if(record?.quote){
    const q=record.quote;const hero=el('div','payment-amounts');
    for(const [zh,en,amount] of [['预计总扣款（模拟）','Estimated debit (simulation)','GBP '+q.total],['预计到账（模拟）','Estimated recipient amount',q.receive_currency+' '+q.receive_amount]]){
      const cell=el('div');cell.append(el('small','',t(zh,en)),el('strong','',amount));hero.append(cell);
    }
    hero.append(el('p','',t('本金 ','Amount ')+q.amount+' GBP · '+t('演示手续费 ','Fictional fee ')+q.fee+' GBP'));wrap.append(hero);
  }
  const table=el('table','request-form-table');const rows=el('tbody');
  for(const item of record?.summary || []){
    if(compact && !['付款账户','收款账户名称','名称核对（仅演示数据）','转账本金','演示手续费','预计总扣款（模拟）','预计剩余余额（模拟）','预计到账（模拟）','演示固定汇率','预约日期','材料状态'].includes(item.label))continue;
    const row=el('tr');row.append(el('th','',t(item.label,item.label_en)),el('td','',t(item.value,item.value_en)));rows.append(row);
  }
  table.append(rows);wrap.append(table);return wrap;
}
function mountScenario(form,service) {
  const schema=service.scenario;if(!schema)return null;
  const values=S.serviceScenario || scenarioDefaults(service,{});
  const section=el('section','scenario-section');
  section.append(el('h3','',service.id==='open_account'?t('2 · 申请人资料与材料','2 · Applicant and documents'):t('2 · 付款账户与收款资料','2 · Payer and payee details')),
    el('p','muted small',t('使用预设演示档案；DEMO 标识不是真实银行资料。','Use the fictional profiles below. DEMO identifiers are not real banking details.')));
  const profile=el('div','scenario-profile');const grid=el('div','scenario-grid');const preview=el('div','scenario-preview');
  preview.setAttribute('aria-live','polite');
  const controls={},labels={};
  for(const f of schema.fields){
    const label=el('label',f.type==='checkbox'?'check-label':'',f.type==='checkbox'?'':t(f.label,f.label_en));
    const input=el(f.type==='select'?'select':'input');input.name='scenario_'+f.name;
    if(f.type==='select')for(const o of f.options){const option=el('option','',t(o.label,o.label_en));option.value=o.value;input.append(option);}
    else input.type=f.type;
    if(f.type==='checkbox')input.checked=!!values[f.name];else input.value=values[f.name]??'';
    if(f.type==='date')input.min=S.boot.today;
    if(f.type==='text')input.maxLength=100;
    input.required=!f.when && f.type!=='checkbox';
    label.append(input);if(f.type==='checkbox')label.append(document.createTextNode(t(f.label,f.label_en)));
    if(f.name==='declaration')label.classList.add('scenario-declaration');
    controls[f.name]=input;labels[f.name]=label;grid.append(label);
  }
  section.append(profile,grid,preview);form.append(section);
  let sequence=0,timer,lastRecord=null;
  const read=()=>Object.fromEntries(schema.fields.map(f=>[f.name,f.type==='checkbox'?controls[f.name].checked:controls[f.name].value.trim()]));
  const save=()=>{
    S.serviceScenario=read();
    const current=S.formDrafts.get(draftKey(service.id)) || {signature:S.serviceSignature,values:S.servicePrefill};
    S.formDrafts.set(draftKey(service.id),{...current,scenario:read()});
  };
  const baseValues=()=>Object.fromEntries(service.fields.map(f=>[f.name,f.type==='checkbox'?form.elements[f.name].checked:form.elements[f.name].value.trim()]));
  function detail(zh,en,value){const row=el('div');row.append(el('small','',t(zh,en)),el('strong','',value));profile.append(row);}
  function update(changed){
    profile.replaceChildren();
    if(service.id==='open_account'){
      const student=form.elements.product.value==='student_account';
      if(changed==='product'){
        controls.profile.value=student?'student_demo':'adult_demo';controls.employment.value=student?'student':'employed';
        controls.account_purpose.value=student?'study':'daily';controls.funding_source.value=student?'family':'salary';
      }
      const person=schema.profiles.find(p=>p.id===controls.profile.value);
      if(changed==='profile' || changed==='product')form.elements.applicant.value=person.name;
      if(!form.elements.applicant.value.trim())form.elements.applicant.value=person.name;
      detail('演示法定姓名','Fictional legal name',person.name);detail('演示出生日期','Fictional birth date',person.birth_date);
      detail('演示邮箱','Fictional email',person.email);detail('演示居住地址','Fictional address',person.address);
      detail('身份记录','Identity record',person.identity);if(student&&person.institution)detail('演示学校','Fictional institution',person.institution);
      labels.student_document.hidden=!student;controls.student_document.disabled=!student;
    }else{
      const type=form.elements.transfer_type.value;
      for(const o of controls.payee_profile.options){const p=schema.payees.find(p=>p.id===o.value);o.hidden=p.type!==type;o.disabled=p.type!==type;}
      if(schema.payees.find(p=>p.id===controls.payee_profile.value)?.type!==type){controls.payee_profile.value=type==='international'?'europe_demo':'alex_demo';changed='payee_profile';}
      const payee=schema.payees.find(p=>p.id===controls.payee_profile.value);const payer=schema.payers.find(p=>p.id===controls.payer.value);
      if(changed==='payee_profile'){controls.payee_name.value=payee.name;controls.payee_ack.checked=false;form.elements.recipient.value=payee.name;}
      if(!form.elements.recipient.value.trim())form.elements.recipient.value=payee.name;
      detail('演示付款账户','Fictional payer',t(payer.label,payer.label_en));detail('场景可用余额（不实际扣减）','Scenario balance (no actual debit)','GBP '+payer.balance);
      detail('演示收款银行／国家','Fictional payee bank / country',payee.bank+' / '+payee.country);
      detail('演示路由标识','Fictional routing ID',payee.routing);detail('演示收款标识','Fictional payee ID',payee.account);
      detail('收款币种','Recipient currency',payee.currency);
      const scheduled=controls.execution.value==='scheduled';labels.execution_date.hidden=!scheduled;controls.execution_date.disabled=!scheduled;controls.execution_date.required=scheduled;
      if(!scheduled)controls.execution_date.value='';
      labels.payee_ack.hidden=lastRecord?.payee_match!=='close';controls.payee_ack.disabled=labels.payee_ack.hidden;
    }
  }
  async function calculate(){
    clearTimeout(timer);const n=++sequence;
    if(service.id==='transfer_demo'&&!form.elements.amount.value.trim()){
      preview.replaceChildren(el('p','muted small',t('输入金额后，这里会显示收款名称核对、费用和预计到账明细。','Enter an amount to see the payee check, fees and estimated recipient amount.')));return null;
    }
    try{
      const record=await api('/api/scenarios/preview','POST',{service_id:service.id,payload:baseValues(),scenario:read()});
      if(n!==sequence||!form.isConnected)return null;
      lastRecord=record;preview.replaceChildren(scenarioTable(record,true));
      if(service.id==='transfer_demo'){
        const close=record.payee_match==='close';labels.payee_ack.hidden=!close;controls.payee_ack.disabled=!close;
        if(close)preview.prepend(el('p','scenario-warning',t('收款名称存在细微差异，请核对后勾选确认。','There is a minor name difference. Review it and confirm below.')));
      }
      if(record.needs_info)preview.prepend(el('p','scenario-warning',t('有材料待补充：可登记申请，工作人员会跟进。','Some information is missing. You can submit for staff follow-up.')));
      return record;
    }catch(e){
      if(n!==sequence||!form.isConnected)return null;
      lastRecord=null;preview.replaceChildren(el('p','form-error',e.message));
      if(service.id==='transfer_demo'){labels.payee_ack.hidden=true;controls.payee_ack.disabled=true;}
      return null;
    }
  }
  form.addEventListener('input',e=>{update(e.target.name.replace('scenario_',''));save();clearTimeout(timer);timer=setTimeout(calculate,250);});
  form.addEventListener('change',e=>{update(e.target.name.replace('scenario_',''));save();clearTimeout(timer);timer=setTimeout(calculate,80);});
  update();save();timer=setTimeout(calculate,80);
  return {read,calculate,get record(){return lastRecord;}};
}
function openService(id, prefill = {}) {
  const service = serviceBy(id);
  if (!service) return;
  S.service = service;
  const base = {...prefill, ...(S.current?.service_drafts?.[id] || {})};
  if(id==='open_account'&&!base.product)base.product=S.bankMode==='student'?'student_account':'everyday_account';
  if(id==='apply_card'&&!base.linked_product)base.linked_product=S.bankMode==='student'?'student_account':'everyday_account';
  const signature = JSON.stringify(base);
  const saved = S.formDrafts.get(draftKey(id));
  prefill = saved?.signature === signature ? {...base, ...saved.values} : base;
  S.servicePrefill = prefill;
  S.serviceSignature = signature;
  S.serviceSubmission = saved?.submission || null;
  S.scenarioRecord=null;
  S.serviceScenario=saved?.signature===signature&&saved.scenario?{...saved.scenario}:scenarioDefaults(service,prefill);
  $("serviceTitle").textContent = t(service.title, service.en);
  renderServiceForm(prefill);
  if (!$("serviceDialog").open) $("serviceDialog").showModal();
}
function renderServiceForm(prefill) {
  const s = S.service;
  const body = $("serviceBody");
  body.replaceChildren();
  body.append(el("p", "drawer-desc", t(s.description,s.description_en || s.en)));
  const steps = el("div", "steps");
  steps.append(
    el("span", "active", t("01 填写信息", "01 Details")),
    el("span", "", t("02 核对确认", "02 Review")),
    el("span", "", t("03 受理编号", "03 Reference")),
  );
  body.append(steps);
  const form = el("form");
  form.id = "serviceForm";
  for (const f of s.fields) {
    const label = el(
      "label",
      f.type === "checkbox" ? "check-label" : "",
      f.type === "checkbox" ? "" : fieldLabel(f),
    );
    let input;
    if (f.type === "select") {
      input = el("select");
      for (const o of f.options) {
        const opt = el("option", "", optionLabel(f,o.value));
        opt.value = o.value;
        input.append(opt);
      }
    } else if (f.type === "textarea") input = el("textarea");
    else {
      input = el("input");
      input.type =
        f.type === "checkbox"
          ? "checkbox"
          : f.type === "number"
            ? "number"
            : f.type === "date"
              ? "date"
              : "text";
      if (f.type === "number") {
        input.min = f.name === "opening_deposit" ? "10" : "0.01";
        input.step = ".01";
        input.max = "1000000";
      }
      if (f.type === "date") input.min = S.boot.today || new Date().toISOString().slice(0,10);
    }
    input.name = f.name;
    input.required = f.required;
    input.maxLength = 2000;
    if (prefill[f.name] !== undefined) {
      if (f.type === "checkbox") input.checked = !!prefill[f.name];
      else input.value = prefill[f.name];
    } else if (f.name === "applicant" && S.boot.user)
      input.value = S.boot.user.display_name;
    else if (s.id === "human_support" && S.current) {
      const last = [...S.current.messages]
        .reverse()
        .find((m) => m.role === "user");
      if (last && ["subject", "description"].includes(f.name))
        input.value = last.content.slice(0, f.name === "subject" ? 80 : 2000);
    }
    label.append(input);
    if (f.type === "checkbox")
      label.append(document.createTextNode(fieldLabel(f)));
    form.append(label);
  }
  const scenarioUI=mountScenario(form,s);
  form.append(el("div", "service-notice", t(s.notice,s.notice_en || s.en)));
  const error = el("p", "form-error");
  form.append(error);
  const submit = el(
    "button",
    "primary-button full",
    t("下一步，核对信息", "Next, review details"),
  );
  submit.type = "submit";
  form.append(submit);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const values = {};
    for (const f of s.fields) {
      const i = form.elements[f.name];
      values[f.name] = f.type === "checkbox" ? i.checked : i.value.trim();
      if (f.required && (f.type === "checkbox" ? !i.checked : !values[f.name])) {
        error.textContent = t("请填写或确认：", "Please complete or confirm: ") + fieldLabel(f); i.focus(); return;
      }
      if (f.type === "date" && values[f.name] < (S.boot.today || new Date().toISOString().slice(0,10))) {
        error.textContent = t("预约日期不能早于今天。", "The visit date cannot be earlier than today."); i.focus(); return;
      }
    }
    if (!form.reportValidity()) return;
    if(scenarioUI){
      const scenario=scenarioUI.read();
      if(!scenario.declaration){error.textContent=t('请勾选演示资料核对声明。','Confirm that you reviewed the fictional details.');return;}
      submit.disabled=true;
      const record=await scenarioUI.calculate();submit.disabled=false;
      if(!record){error.textContent=t('请先修正场景核对中显示的问题。','Resolve the scenario checks before continuing.');return;}
      if(record.payee_match==='close'&&!scenario.payee_ack){error.textContent=t('请确认收款名称的细微差异。','Confirm the minor payee name difference.');return;}
      S.scenarioRecord=record;S.serviceScenario=scenario;
    }
    S.formDrafts.set(draftKey(s.id), {signature:S.serviceSignature, values, submission:S.serviceSubmission,scenario:S.serviceScenario});
    renderReview(values);
  });
  form.addEventListener("input", () => {
    const values = Object.fromEntries(s.fields.map(f => [f.name, f.type === "checkbox" ? form.elements[f.name].checked : form.elements[f.name].value]));
    S.formDrafts.set(draftKey(s.id), {signature:S.serviceSignature, values, submission:S.serviceSubmission,scenario:scenarioUI?.read() || null});
    error.textContent = "";
  });
  body.append(form);
  if (s.id==='funding_enquiry') {
    const directory=el('section','funding-directory');
    directory.append(el('h3','',t('奖学金与补助目录（演示）','Scholarship and grant directory (demo)')));
    const cards=el('div','funding-programs');directory.append(cards);body.prepend(directory);
    const renderPrograms=()=>{
      cards.replaceChildren();const level=form.elements.study_level.value;const kind=form.elements.funding_type.value;
      for(const p of S.boot.funding_programs || []) {
        if(p.kind==='loan'||!p.levels.includes(level)||kind!=='all'&&!(kind==='grants'?['grant','emergency'].includes(p.kind):p.kind===kind))continue;
        const card=el('article','funding-program');
        card.append(el('strong','',t(p.title,p.title_en)),el('p','',t(p.summary,p.summary_en)),el('p','funding-amount',t(p.amount,p.amount_en)),el('p','muted small',t(p.documents,p.documents_en)));
        cards.append(card);
      }
    };
    form.elements.study_level.addEventListener('change',renderPrograms);form.elements.funding_type.addEventListener('change',renderPrograms);renderPrograms();
  }
}
function renderReview(values) {
  const s = S.service;
  const body = $("serviceBody");
  const scenario=S.serviceScenario?{...S.serviceScenario}:null;
  const record=S.scenarioRecord;
  const fingerprint = JSON.stringify([s.id, values, S.current?.id || null,scenario]);
  if (!S.serviceSubmission || S.serviceSubmission.fingerprint !== fingerprint)
    S.serviceSubmission = {fingerprint, key:crypto.randomUUID().replaceAll("-", "")};
  body.replaceChildren();
  const steps = el("div", "steps");
  steps.append(
    el("span", "", t("01 填写信息", "01 Details")),
    el("span", "active", t("02 核对确认", "02 Review")),
    el("span", "", t("03 受理编号", "03 Reference")),
  );
  body.append(steps);
  for (const f of s.fields) {
    let value = values[f.name];
    if (value === "") continue;
    if (f.type === "select")
      value = optionLabel(f,value);
    if (f.type === "checkbox")
      value = value ? t("已确认", "Confirmed") : t("未确认", "Not confirmed");
    const row = el("div", "review-row");
    row.append(el("span", "", fieldLabel(f)), el("span", "", value));
    body.append(row);
  }
  if(s.scenario && record)body.append(scenarioTable(record));
  body.append(el("div", "service-notice", t(s.notice,s.notice_en || s.en)));
  const actions = el("div", "section-actions");
  let submitting = false;
  actions.append(
    button(t("返回修改", "Back"), "secondary-button", () => {
      S.serviceScenario=scenario;renderServiceForm(values);
    }),
    button(
      S.boot.user
        ? t("确认提交演示请求", "Confirm demo request")
        : t("登录并保存申请", "Sign in and save"),
      "primary-button",
      async () => {
        if (submitting) return;
        if (!S.boot.user) {
          $("serviceDialog").close();
          openAuth("login", () => {
            openService(s.id, values);
            S.serviceScenario=scenario;S.scenarioRecord=record;
            renderReview(values);
          });
          return;
        }
        try {
          submitting = true;
          for (const b of actions.querySelectorAll("button")) b.disabled = true;
          const submission = S.serviceSubmission;
          S.formDrafts.set(draftKey(s.id), {signature:S.serviceSignature, values, submission,scenario});
          let chatId = S.current?.id;
          if (s.id === "human_support" && !chatId)
            chatId = (await ensureChat()).id;
          const r = await api("/api/requests", "POST", {
            service_id: s.id,
            payload: values,
            chat_id: chatId || null,
            confirmed: true,
            request_id: submission.key,
            bank_mode:S.bankMode,
            scenario,
          });
          S.formDrafts.delete(draftKey(s.id));
          renderReceipt(r);
          if (S.current) {
            S.current = await api("/api/chats/" + S.current.id);
            if (S.view === "chat") renderChat(false);
          }
          await refreshHistory();
        } catch (e) {
          submitting = false;
          for (const b of actions.querySelectorAll("button")) b.disabled = false;
          toast(e.message);
          const alert = el("p", "form-error", e.message); alert.setAttribute("role", "alert");
          body.querySelector(".form-error")?.remove(); body.append(alert);
        }
      },
    ),
  );
  body.append(actions);
}
function renderReceipt(r) {
  const body = $("serviceBody");
  body.replaceChildren();
  const receipt = el("div", "receipt");
  receipt.append(
    el("div", "success-mark", "✓"),
    el("h3", "", t("演示请求已登记", "Demo request received")),
    el(
      "p",
      "",
      t(
        "你的记录已保存，可以随时查看进度。",
        "Your request is saved and ready to track.",
      ),
    ),
    el("div", "reference-number", r.id),
    el(
      "p",
      "",
      t('当前状态：','Status: ')+statusText(r.status),
    ),
    button(
      t("查看我的办理记录", "View my requests"),
      "primary-button full",
      () => {
        $("serviceDialog").close();
        showRequests();
      },
    ),
  );
  if(r.scenario)receipt.append(scenarioTable(r.scenario),el('p','muted small',t('以上余额、姓名核对和汇率仅用于本次场景演示，不代表真实扣款、身份验证或支付成功。','Balances, name checks and exchange rates are scenario examples only. No real debit, identity verification or successful payment is implied.')));
  if (r.service_id === "human_support") {
    receipt.append(
      button(
        t("返回转接会话", "Back to support chat"),
        "secondary-button full",
        () => {
          $("serviceDialog").close();
          showChat();
        },
      ),
    );
    if (hasStaffAccess())
      receipt.append(
        button(
          t("进入工作人员演示台", "Open staff workspace"),
          "secondary-button full",
          () => {
            $("serviceDialog").close();
            showStaff();
          },
        ),
      );
  }
  body.append(receipt);
}
function authKind(kind) {
  S.authKind = kind;
  const register = kind === "register";
  $("loginTab").classList.toggle("active", !register);
  $("registerTab").classList.toggle("active", register);
  $("displayNameField").hidden = !register;
  $("authForm").elements.display_name.required = register;
  $("authTitle").textContent = register
    ? t("创建你的账户", "Create your account")
    : t("欢迎回来", "Welcome back");
  $("authSubtitle").textContent = t(
    "登录后，你的对话与服务进度都在这里。",
    "Your chats and service progress in one place.",
  );
  $("authSubmit").textContent = register
    ? t("注册并登录", "Register and sign in")
    : t("登录", "Sign in");
  $("authError").textContent = "";
  $("authForm").elements.password.autocomplete = register
    ? "new-password"
    : "current-password";
  updateAuthRole();
}
function updateAuthRole() {
  const staff = $("portalRole").value === "staff";
  $("staffInviteField").hidden = !staff || !!S.boot?.open_staff_testing;
  $("staffTestEntry").hidden=!S.boot?.open_staff_testing;
  const groupCode =
    S.authKind === "register" &&
    !staff &&
    S.boot?.registration_access_code_required;
  $("groupTestCodeField").hidden = !groupCode;
  $("authForm").elements.test_access_code.required = !!groupCode;
  $("staffInviteField").firstChild.textContent =
    staff && S.authKind === "register" && S.boot?.first_admin_setup_required
      ? t("管理员初始化邀请码", "Administrator setup invitation")
      : t("工作人员邀请码", "Staff invitation");
  $("authSubtitle").textContent = staff && S.boot?.open_staff_testing
    ? t('当前为测试阶段，工作人员注册和登录无需邀请码，也可一键进入测试客服。','Staff registration and sign-in need no invitation during testing. You can also use the one-click test entry.')
    : staff
    ? t(
        "工作人员进入客服端。首次开通需要管理员邀请码；已开通的账户无需再次填写。",
        "Staff enter the support workspace. An invitation is required only when first enabling staff access.",
      )
    : t(
        "客户登录后可咨询、办理业务并接收人工回复。",
        "Customers can chat, open services and receive staff replies.",
      );
}
function openAuth(kind = "login", after = null) {
  S.afterLogin = after;
  authKind(kind === "register" ? "register" : "login");
  $("authDialog").showModal();
}
async function submitAuth(e) {
  e.preventDefault();
  const f = $("authForm");
  const body = {
    username: f.elements.username.value.trim(),
    password: f.elements.password.value,
    portal_role: f.elements.portal_role.value,
    invite_code: f.elements.invite_code.value.trim(),
  };
  if (S.authKind === "register") {
    body.display_name = f.elements.display_name.value.trim();
    body.test_access_code = f.elements.test_access_code.value.trim();
  }
  $("authSubmit").disabled = true;
  try {
    const data = await api(
      "/api/" + (S.authKind === "register" ? "register" : "login"),
      "POST",
      body,
    );
    S.boot.user = data.user;
    S.boot.csrf = data.csrf;
    S.boot.portal_role = data.portal_role || body.portal_role;
    identityChannel?.postMessage("identity-changed");
    if (data.user.is_admin) S.boot.first_admin_setup_required = false;
    $("authDialog").close();
    f.reset();
    $("authError").textContent = "";
    await refreshHistory();
    renderSidebar();
    if (S.current) S.current = await api("/api/chats/" + S.current.id);
    if (S.view === "chat") renderChat(false);
    toast(t("欢迎，", "Welcome, ") + data.user.display_name);
    const callback = S.afterLogin;
    S.afterLogin = null;
    if (callback) await callback();
    else if (S.boot.portal_role === "staff") await showStaff();
  } catch (e) {
    $("authError").textContent = e.message;
  } finally {
    $("authSubmit").disabled = false;
  }
}
function showProfile() {
  if (!S.boot.user) {
    openAuth("login");
    return;
  }
  const p = $("profileDetails");
  p.replaceChildren(
    el("p", "", S.boot.user.display_name),
    el("p", "muted small", "@" + S.boot.user.username),
    el(
      "p",
      "muted tiny",
      S.boot.user.is_admin
        ? t(
            "管理员：可邀请工作人员、处理工单及导入旧记录。",
            "Administrator: invite staff, handle tickets and import legacy chats.",
          )
        : S.boot.user.is_staff
          ? t(
              "工作人员：可接单、查看客户需求并回复。",
              "Staff: accept tickets, view customer requests and reply.",
            )
          : t(
              "仅显示本账户的历史与服务记录。",
              "Only your chats and requests are visible.",
            ),
    ),
  );
  p.append(
    el(
      "p",
      "muted small",
      t("当前身份：", "Current role: ") +
        (S.boot.portal_role === "staff"
          ? t("工作人员", "Staff")
          : t("客户", "Customer")),
    ),
  );
  if (S.boot.user.is_admin || S.boot.user.is_staff)
    p.append(
      button(
        S.boot.portal_role === "staff"
          ? t("切换到客户界面", "Switch to customer")
          : t("切换到工作人员界面", "Switch to staff"),
        "secondary-button full",
        () =>
          switchPortalRole(
            S.boot.portal_role === "staff" ? "customer" : "staff",
          ),
      ),
    );
  else if(S.boot.open_staff_testing)p.append(button(t('一键进入测试客服','Enter test staff workspace'),'secondary-button full',enterTestStaff));
  $("profileDialog").showModal();
}
async function switchPortalRole(role) {
  if (S.busy) return;
  try {
    const result = await api("/api/session/role", "POST", {
      portal_role: role,
    });
    S.boot.user = result.user;
    S.boot.csrf = result.csrf;
    S.boot.portal_role = result.portal_role;
    identityChannel?.postMessage("identity-changed");
    $("profileDialog").close();
    S.staffId = null;
    S.staffDrafts = {};
    renderSidebar();
    if (role === "staff") await showStaff();
    else showChat();
    toast(
      role === "staff"
        ? t("已切换为工作人员", "Staff mode active")
        : t("已切换为客户", "Customer mode active"),
    );
  } catch (e) {
    toast(e.message);
  }
}
async function inviteStaff() {
  try {
    const data = await api("/api/admin/staff-invites", "POST");
    $("staffInviteCode").value = data.invite_code;
    $("staffInviteExpiry").textContent =
      t("有效期至：", "Expires: ") +
      new Date(data.expires_at).toLocaleString() +
      t(" · 仅可使用一次", " · Single use");
    $("staffInviteDialog").showModal();
  } catch (e) {
    toast(e.message);
  }
}
async function showStaff() {
  if (!hasStaffAccess()) return;
  S.view = "staff";
  closeMobile();
  showComposer(false);
  title(t("工作人员演示台", "Staff workspace"));
  const page = el("section", "page-section");
  page.append(
    el("h1", "", t("工作人员工作台", "Staff workspace")),
    el(
      "p",
      "page-subtitle",
      t(
        "业务申请、客服工单和客户新消息每 3 秒同步。表单处理状态与备注会保存供客户查看。",
        "Applications, support tickets and messages sync every 3 seconds. Application review status and notes are saved for customers to view.",
      ),
    ),
  );
  const toolbar = el("div", "staff-toolbar");
  toolbar.append(
    button(t("刷新工作台", "Refresh workspace"), "secondary-button", () =>
      refreshStaff(),
    ),
  );
  if (S.boot.user.is_admin)
    toolbar.append(
      button(
        t("邀请工作人员", "Invite staff"),
        "secondary-button",
        inviteStaff,
      ),
    );
  const status = el("span", "muted tiny", t("正在同步…", "Syncing…"));
  status.id = "staffSyncStatus";
  toolbar.append(status);
  page.append(toolbar);
  const tabs=el('div','staff-tabs');
  for(const [id,zh,en] of [['tickets','人工客服工单','Support tickets'],['requests','业务申请与表单','Applications and forms']])
    tabs.append(button(t(zh,en),'staff-tab'+(S.staffTab===id?' active':''),()=>{S.staffTab=id;showStaff();}));
  page.append(tabs);
  if(S.boot.open_staff_testing)page.append(el('p','testing-banner',t('测试客服入口已开放。仅处理演示数据；关闭测试开关后恢复邀请码限制。','Open staff testing is enabled. Use demonstration data only; switching testing off restores invitation requirements.')));
  const layout = el("div", "staff-layout");
  const list = el("div");
  list.id = "staffTicketList";
  const detail = el("div", "staff-detail");
  detail.id = "staffTicketDetail";
  detail.append(
    el(
      "p",
      "muted small",
      t(
        "选择工单查看上下文并回复。",
        "Choose a ticket to view context and reply.",
      ),
    ),
  );
  layout.append(list, detail);
  layout.hidden=S.staffTab==='requests';
  page.append(layout);
  const business=el('section','business-workbench');business.id='businessWorkbench';business.hidden=S.staffTab!=='requests';
  page.append(business);
  $("content").replaceChildren(page);
  S.staffFingerprint = "";
  $('scrollArea').scrollTop=0;
  S.staffDetailFingerprint = "";
  await refreshStaff();
}
async function enterTestStaff() {
  if(S.busy)return;
  const buttonEl=$('staffTestLogin');buttonEl.disabled=true;
  try {
    const data=await api('/api/testing/staff-session','POST',{});
    Object.assign(S.boot,data);S.current=null;S.staffTab='requests';S.afterLogin=null;
    $('authDialog').close();if($('profileDialog').open)$('profileDialog').close();setChatUrl(null);renderSidebar();await refreshHistory();await showStaff();
    identityChannel?.postMessage('identity-changed');
  }catch(e){$('authError').textContent=e.message;}finally{buttonEl.disabled=false;}
}
async function refreshBusinessRequests() {
  if(S.view!=='staff'||!hasStaffAccess()||S.businessPolling)return;
  S.businessPolling=true;
  try {
    const rows=await api('/api/admin/requests');
    if(S.view!=='staff'||S.staffTab!=='requests')return;
    S.businessData=rows;const root=$('businessWorkbench');if(!root)return;
    let list=$('businessRequestList'),detail=$('businessRequestDetail');
    if(!list){
      const filters=el('div','business-filters');
      const mode=el('select');mode.id='businessModeFilter';mode.setAttribute('aria-label',t('筛选银行模式','Filter banking mode'));
      for(const [value,zh,en] of [['all','全部模式','All modes'],['general','社会银行','General banking'],['student','学生银行','Student banking']]){const o=el('option','',t(zh,en));o.value=value;mode.append(o);}
      const status=el('select');status.id='businessStatusFilter';status.setAttribute('aria-label',t('筛选处理状态','Filter status'));
      for(const value of ['all','pending','processing','needs_info','completed']){const o=el('option','',value==='all'?t('全部状态','All statuses'):statusText(value));o.value=value;status.append(o);}
      mode.value=S.businessModeFilter||'all';status.value=S.businessStatusFilter||'all';
      mode.onchange=()=>{S.businessModeFilter=mode.value;refreshBusinessRequests();};status.onchange=()=>{S.businessStatusFilter=status.value;refreshBusinessRequests();};
      const stats=el('span','muted small');stats.id='businessRequestStats';filters.append(mode,status,stats);
      list=el('div','business-request-list');list.id='businessRequestList';detail=el('section','business-request-detail');detail.id='businessRequestDetail';
      const layout=el('div','business-layout');layout.append(list,detail);root.append(filters,layout);
    }
    $('businessRequestStats').textContent=t(`共 ${rows.length} 条业务申请，${rows.filter(x=>x.status==='pending').length} 条待处理`,` ${rows.length} applications; ${rows.filter(x=>x.status==='pending').length} pending`);
    const filtered=rows.filter(r=>(!S.businessModeFilter||S.businessModeFilter==='all'||r.bank_mode===S.businessModeFilter)&&(!S.businessStatusFilter||S.businessStatusFilter==='all'||r.status===S.businessStatusFilter));
    list.replaceChildren();
    if(!filtered.length){detail.replaceChildren(el('h3','',t('暂无匹配的业务申请','No matching applications')),el('p','muted',t('客户提交开户、转账、贷款或学生资助咨询后，表单内容会在这里自动同步。','Customer account, transfer, loan and student-finance submissions appear here automatically.')));S.businessId=null;return;}
    if(!filtered.some(r=>r.id===S.businessId))S.businessId=filtered[0].id;
    for(const row of filtered){
      const item=button('','business-request-item'+(S.businessId===row.id?' active':''),()=>{S.businessId=row.id;S.businessFingerprint='';refreshBusinessRequests();});
      const service=serviceBy(row.service_id);item.append(el('strong','',t(service?.title||row.title,service?.en||row.title)),el('span','',row.customer_name||t('演示客户','Demo customer')),el('small','',row.id+' · '+statusText(row.status)));list.append(item);
    }
    const row=await api('/api/admin/requests/'+S.businessId);
    if(S.view!=='staff'||S.staffTab!=='requests'||S.businessId!==row.id)return;
    const fingerprint=JSON.stringify(row);if(S.businessFingerprint===fingerprint&&detail.dataset.id===row.id)return;
    const focused=detail.contains(document.activeElement);const selection=focused&&document.activeElement.selectionStart!==undefined?[document.activeElement.selectionStart,document.activeElement.selectionEnd]:null;
    S.businessDrafts ||= {};detail.dataset.id=row.id;detail.replaceChildren();
    const service=serviceBy(row.service_id);detail.append(el('h2','',t(service.title,service.en)),el('p','muted small',row.id+' · '+timeText(row.created_at)),el('p','',t('客户：','Customer: ')+(row.customer_name||'—')+' · '+(row.bank_mode==='student'?t('学生银行','Student banking'):t('社会银行','General banking'))),el('span','status '+row.status,statusText(row.status)));
    const table=el('table','request-form-table');const tbody=el('tbody');
    for(const field of service.fields){const value=row.payload[field.name];if(value===undefined||value==='')continue;const tr=el('tr');tr.append(el('th','',fieldLabel(field)),el('td','',typeof value==='boolean'?(value?t('已确认','Confirmed'):'—'):optionLabel(field,value)));tbody.append(tr);}
    table.append(tbody);detail.append(table);
    if(row.scenario)detail.append(scenarioTable(row.scenario));
    detail.append(el('p','service-notice',t(service.notice,service.notice_en||service.en)));
    const note=el('textarea','business-review-note');note.setAttribute('aria-label',t('业务处理备注','Application review note'));note.placeholder=t('填写演示处理说明或需要客户补充的内容','Add a demo review note or explain what the customer should supplement');note.value=S.businessDrafts[row.id]??row.staff_note??'';note.oninput=()=>S.businessDrafts[row.id]=note.value;
    const feedback=el('p','form-error');feedback.setAttribute('role','status');detail.append(note,feedback);
    const actions=el('div','business-actions');let sending=false;
    for(const [value,zh,en] of [['processing','标记处理中','Mark processing'],['needs_info','请客户补充','Request information'],['completed','演示核对完成','Complete demo review']])actions.append(button(t(zh,en),'secondary-button',async()=>{
      if(sending)return;if(value==='needs_info'&&!note.value.trim()){feedback.textContent=t('请说明需要补充什么材料。','Explain what information is needed.');return;}
      sending=true;for(const b of actions.querySelectorAll('button'))b.disabled=true;
      try{await api('/api/admin/requests/'+row.id,'PATCH',{status:value,note:note.value.trim()});delete S.businessDrafts[row.id];S.businessFingerprint='';feedback.textContent=t('处理状态已保存，客户可在办理记录中查看。','Review saved; the customer can see it under My requests.');await refreshBusinessRequests();}
      catch(e){feedback.textContent=e.message;}finally{sending=false;for(const b of actions.querySelectorAll('button'))b.disabled=false;}
    }));detail.append(actions);
    if(row.events?.length){const history=el('details','request-review-history');history.append(el('summary','',t('处理记录','Review history')));for(const e of row.events)history.append(el('p','small',timeText(e.created_at)+' · '+e.actor+' · '+statusText(e.status)+(e.note?' · '+e.note:'')));detail.append(history);}
    S.businessFingerprint=fingerprint;if(focused){note.focus();if(selection)note.setSelectionRange(...selection);}
    if($('staffSyncStatus'))$('staffSyncStatus').textContent=t('业务申请每 3 秒同步','Applications sync every 3 seconds');
  }catch(e){toast(e.message);}finally{S.businessPolling=false;}
}
function staffEmpty(detail) {
  detail.replaceChildren(
    el("h3", "", t("先创建一张人工客服工单", "Create a support ticket first")),
    el(
      "p",
      "muted small",
      t(
        "客户在聊天中点击“转人工客服”，工单和对话会自动出现在这里。也可以用当前账户走一遍演示。",
        "When a customer clicks Talk to staff, their ticket and conversation appear here. You can also try the flow with this account.",
      ),
    ),
  );
  const steps = el("ol", "muted small");
  for (const step of [
    t(
      "客户登录，正常咨询后点击聊天中的转人工按钮。",
      "A customer signs in, chats, then clicks Talk to staff.",
    ),
    t(
      "工作人员选择工单并接单，查看完整对话后回复。",
      "Staff select and accept the ticket, review the conversation and reply.",
    ),
    t(
      "客户原对话自动显示人工回复，处理完后可结束工单。",
      "The original customer chat shows the reply automatically. Resolve the ticket when done.",
    ),
  ])
    steps.append(el("li", "", step));
  detail.append(
    steps,
    button(
      t("创建人工客服工单", "Create support ticket"),
      "primary-button",
      async () => {
        if (!S.current) await newChat();
        if (S.current) openService("human_support");
      },
    ),
  );
}
async function refreshStaff(quiet = false) {
  if(S.staffTab==='requests') {await refreshBusinessRequests();return;}
  if (S.staffPolling || S.view !== "staff" || !hasStaffAccess()) return;
  S.staffPolling = true;
  try {
    const tickets = await api("/api/admin/tickets");
    if (S.view !== "staff") return;
    const list = $("staffTicketList"),
      detail = $("staffTicketDetail");
    if (!list || !detail) return;
    const fingerprint = JSON.stringify(tickets);
    if (fingerprint !== S.staffFingerprint) {
      S.staffFingerprint = fingerprint;
      list.replaceChildren();
      if (!tickets.length) {
        S.staffId = null;
        list.append(
          el("div", "empty-state", t("暂无客服工单", "No tickets yet")),
        );
        staffEmpty(detail);
      } else {
        if (!tickets.some((x) => x.id === S.staffId)) {
          S.staffId = (
            tickets.find((x) => x.status !== "resolved") || tickets[0]
          ).id;
          S.staffDetailFingerprint = "";
        }
        for (const ticket of tickets) {
          const b = button(
            "",
            "ticket-item" + (ticket.id === S.staffId ? " active" : ""),
            async () => {
              const currentDraft = detail.querySelector("textarea");
              if (currentDraft && detail.dataset.ticketId) {
                S.staffDrafts ||= {};
                S.staffDrafts[detail.dataset.ticketId] = currentDraft.value;
              }
              S.staffId = ticket.id;
              S.staffDetailFingerprint = "";
              for (const item of list.querySelectorAll("button"))
                item.classList.remove("active");
              b.classList.add("active");
              try {
                await staffDetail(ticket.id, detail);
              } catch (e) {
                toast(e.message);
              }
            },
          );
          b.append(
            el("strong", "", ticket.subject),
            el("small", "", ticket.id + " · " + statusText(ticket.status)),
            el(
              "small",
              "",
              t("客户：", "Customer: ") +
                (ticket.customer_name || "—") +
                (ticket.assigned_name
                  ? t(" · 接单：", " · Assigned: ") + ticket.assigned_name
                  : ""),
            ),
          );
          list.append(b);
        }
      }
    }
    if (S.staffId) await staffDetail(S.staffId, detail);
    if ($("staffSyncStatus"))
      $("staffSyncStatus").textContent =
        t("自动同步中 · ", "Live sync · ") + new Date().toLocaleTimeString();
  } catch (e) {
    if ($("staffSyncStatus"))
      $("staffSyncStatus").textContent = t(
        "同步失败，请刷新或重新登录",
        "Sync failed; refresh or sign in again",
      );
    if (!quiet) toast(e.message);
  } finally {
    S.staffPolling = false;
  }
}
async function staffDetail(id, detail) {
  try {
    const data = await api("/api/admin/tickets/" + id);
    if (S.view !== "staff" || S.staffId !== id) return;
    const fingerprint = JSON.stringify(data);
    if (
      fingerprint === S.staffDetailFingerprint &&
      detail.dataset.ticketId === id
    )
      return;
    const previous = detail.querySelector("textarea");
    const focused = previous && document.activeElement === previous;
    const selection = previous
      ? [previous.selectionStart, previous.selectionEnd]
      : null;
    S.staffDrafts ||= {};
    if (previous && detail.dataset.ticketId === id)
      S.staffDrafts[id] = previous.value;
    const ticket = data.ticket;
    detail.dataset.ticketId = id;
    detail.replaceChildren(
      el("h3", "", ticket.subject),
      el("p", "muted small", ticket.description),
      el(
        "p",
        "muted small",
        t("客户：", "Customer: ") +
          (ticket.customer_name || "—") +
          (ticket.assigned_name
            ? t(" · 处理人：", " · Staff: ") + ticket.assigned_name
            : ""),
      ),
      el("span", "status " + ticket.status, statusText(ticket.status)),
    );
    if (data.chat) {
      const transcript = el("div", "staff-transcript");
      for (const m of data.chat.messages)
        transcript.append(
          el(
            "p",
            "",
            (m.role === "user"
              ? t("客户：", "Customer: ")
              : m.metadata?.sender === "staff"
                ? t("人工客服：", "Staff: ")
                : t("助手：", "Assistant: ")) + m.content,
          ),
        );
      detail.append(transcript);
    }
    if (ticket.status === "resolved") {
      detail.append(
        el(
          "p",
          "muted small",
          t(
            "工单已结束，仅可查看历史记录。",
            "This ticket is resolved. History is read-only.",
          ),
        ),
      );
      S.staffDetailFingerprint = fingerprint;
      return;
    }
    if (ticket.assigned_to && ticket.assigned_to !== S.boot.user.id) {
      detail.append(
        el(
          "p",
          "muted small",
          t(
            "此工单由其他工作人员处理，仅可查看历史。",
            "Another staff member owns this ticket. History is read-only.",
          ),
        ),
      );
      if (S.boot.user.is_admin)
        detail.append(
          button(t("结束工单", "Resolve"), "secondary-button", async () => {
            try {
              await api("/api/admin/tickets/" + id + "/resolve", "POST");
              S.staffDetailFingerprint = "";
              await refreshStaff();
            } catch (e) {
              toast(e.message);
            }
          }),
        );
      S.staffDetailFingerprint = fingerprint;
      return;
    }
    const input = el("textarea");
    input.placeholder = t(
      "输入人工回复（课程演示）",
      "Enter a manual demo reply",
    );
    input.setAttribute("aria-label", t("人工客服回复", "Staff reply"));
    input.maxLength = 2000;
    input.value = S.staffDrafts[id] || "";
    input.addEventListener("input", () => {
      S.staffDrafts[id] = input.value;
    });
    const unavailable =
      ticket.status === "resolved" ||
      (ticket.assigned_to && ticket.assigned_to !== S.boot.user.id);
    input.disabled = !!unavailable;
    detail.append(input);
    const actions = el("div", "staff-actions");
    const restoreControls = () => {
      [...actions.querySelectorAll("button")].forEach((b, index) => {
        b.disabled =
          ticket.status === "resolved" ||
          (!!unavailable && !(index === 2 && S.boot.user.is_admin));
      });
    };
    const act = async (suffix, body) => {
      for (const b of actions.querySelectorAll("button")) b.disabled = true;
      try {
        await api("/api/admin/tickets/" + id + "/" + suffix, "POST", body);
        if (suffix === "reply") {
          input.value = "";
          S.staffDrafts[id] = "";
          toast(t("人工回复已发送", "Staff reply sent"));
        }
        S.staffDetailFingerprint = "";
        await refreshStaff();
      } catch (e) {
        restoreControls();
        toast(e.message);
      }
    };
    actions.append(
      button(t("接单", "Accept"), "secondary-button", () => act("claim")),
      button(t("发送回复", "Send reply"), "primary-button", () => {
        if (!input.value.trim()) {
          toast(t("请先输入回复", "Enter a reply first"));
          return;
        }
        return act("reply", { text: input.value.trim() });
      }),
      button(t("结束工单", "Resolve"), "secondary-button", () =>
        act("resolve"),
      ),
    );
    restoreControls();
    if (unavailable && ticket.status !== "resolved")
      detail.append(
        el(
          "p",
          "muted small",
          t(
            "此工单已由其他工作人员接单。",
            "Another staff member is handling this ticket.",
          ),
        ),
      );
    detail.append(actions);
    S.staffDetailFingerprint = fingerprint;
    if (focused && !input.disabled) {
      input.focus();
      if (selection) input.setSelectionRange(...selection);
    }
  } catch (e) {
    throw e;
  }
}
const STATIC_TEXT = {
 "你的银行服务助手":"Your banking service assistant", "课程演示":"Coursework demo", "搜索历史":"Search history", "搜索对话标题":"Search conversation titles",
 "打开侧边栏":"Open sidebar", "对话设置":"Conversation settings", "聊天消息":"Chat message", "发送消息":"Send message",
 "关闭登录窗口":"Close sign-in window", "关闭服务窗口":"Close service window", "登录身份":"Sign-in role", "客户":"Customer", "工作人员 / 管理员":"Staff / Administrator",
 "登录":"Sign in", "注册":"Register", "用户名":"Username", "密码":"Password", "怎么称呼你":"Display name", "你的称呼":"Your display name", "至少 8 个字符":"At least 8 characters",
 "工作人员邀请码":"Staff invitation code", "首次开通工作人员身份时填写":"Required when enabling staff access", "小组测试邀请码":"Group testing access code", "向项目负责人获取":"Ask the project owner",
 "由部署者提供，供组员注册测试":"Provided privately by the project owner for group testing", "3–32 位字母、数字或下划线":"3–32 letters, digits, or underscores",
 "这是 CampusBank 课程演示账户，与真实银行账户无关。":"This is a local CampusBank demo account, unrelated to real bank accounts.",
 "回答方式":"Answer mode", "自然对话 Agent（推荐）":"Conversational agent (recommended)", "离线应急资料":"Offline reference mode", "实验：固定 RAG":"Experiment: retrieval-augmented generation", "实验：无资料 LLM":"Experiment: model without reference records",
 "显示资料与工具细节":"Show sources and tool details", "导出当前对话":"Export current conversation", "切换方式保留记录。自然对话需要已配置的 DeepSeek API。":"Changing modes preserves history. Conversational mode requires a configured DeepSeek API.",
 "个人账户":"Your account", "退出登录":"Sign out", "邀请工作人员":"Invite staff", "一次性邀请码":"Single-use invitation code", "复制邀请码":"Copy invitation code",
 "将邀请码交给组员。对方在注册或登录时选择“工作人员 / 管理员”并填写邀请码，即可进入客服端。":"Share the invitation privately. Choose Staff / Administrator and enter the code when registering or signing in to enable staff access."
};
function localizeStatic() {
  const reverse = Object.fromEntries(Object.entries(STATIC_TEXT).map(([zh,en]) => [en,zh]));
  const translate = value => {
    const key = value.trim().replace(/\s+/g," ");
    const translated = S.lang === "en" ? STATIC_TEXT[key] : reverse[key];
    return translated ? value.replace(value.trim(),translated) : value;
  };
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walk.nextNode())) {
    if (!node.parentElement?.closest(".message-body, .staff-transcript, .request-details, #serviceBody, script, style, pre, code")) node.nodeValue = translate(node.nodeValue);
  }
  for (const element of document.querySelectorAll("[placeholder], [aria-label]")) {
    for (const attribute of ["placeholder","aria-label"]) {
      const value = element.getAttribute(attribute); if (value) element.setAttribute(attribute,translate(value));
    }
  }
}
function setLanguage() {
  localStorage.setItem("campusbank_language", S.lang);
  document.documentElement.lang = S.lang === "zh" ? "zh-CN" : "en";
  $("languageToggle").textContent = S.lang === "zh" ? "English" : "中文";
  $("newChat").children[1].textContent = t("新建对话", "New chat");
  $("homeNav").lastChild.textContent = t("智能咨询", "Assistant");
  $("requestsNav").lastChild.textContent = t("我的办理记录", "My requests");
  $("supportHistoryNav").lastChild.textContent = t(
    "人工客服记录",
    "Support history",
  );
  $("messageInput").placeholder = t(
    "描述你想办理的业务，或继续追问…",
    "Describe what you need, or ask a follow-up…",
  );
  $("composerHint").textContent = t(
    "中文 / English · 自动跟随消息语言",
    "Chinese / English · Reply follows your message",
  );
  document.querySelector(".composer-note").textContent = t(
    "CampusBank 为虚构银行。业务窗口只登记演示请求，请勿提供真实银行卡号、密码或验证码。",
    "CampusBank is a fictional bank. Forms record demo requests only. Please use example situations.",
  );
  document.querySelector(".history-head>span").textContent = t(
    "历史对话",
    "Chat history",
  );
  document.querySelector(".section-title").firstChild.textContent = t(
    "业务服务 ",
    "Banking services ",
  );
  document.querySelector(".section-title>span").textContent = t(
    "可直接进入办理",
    "Open a service directly",
  );
  $("referencesNav").lastChild.textContent = t(
    "银行官网参考",
    "Official bank references",
  );
  $("legacyImport").lastChild.textContent = t(
    "导入旧版聊天记录",
    "Import legacy chats",
  );
  $("staffNav").lastChild.textContent = t("工作人员演示台", "Staff workspace");
  updateBankModeUI();
  $('staffTestNotice').textContent=t('测试期间可免邀请码进入客服端，不额外授予管理员权限。','Test staff can enter without an invitation; no additional administrator permissions are granted.');
  $('staffTestLogin').textContent=t('一键进入测试客服','Enter test staff workspace');
  renderSidebar();
  if (S.view === "chat") showChat(false);
  else if (S.view === "requests") showRequests();
  else if (S.view === "references") showReferences();
  else if (S.view === "services") showServices(S.category);
  else if (S.view === "staff") showStaff();
  else if (S.view === "supportHistory") showSupportHistory();
  else if (S.view === "supportDetail") showCustomerTicket(S.supportTicketId);
  localizeStatic();
  if ($("serviceDialog").open && S.service) {
    const form = $("serviceForm");
    const values = form ? Object.fromEntries(S.service.fields.map(f => [f.name,f.type === "checkbox" ? form.elements[f.name].checked : form.elements[f.name].value])) : S.servicePrefill;
    $("serviceTitle").textContent = t(S.service.title,S.service.en);
    if (form) renderServiceForm(values);
  }
}
async function init() {
  document
    .querySelectorAll("[data-icon]")
    .forEach((e) => e.replaceChildren(icon(e.dataset.icon).firstChild));
  document
    .querySelectorAll("[data-close]")
    .forEach((b) =>
      b.addEventListener("click", () => $(b.dataset.close).close()),
    );
  $("newChat").onclick = newChat;
  $('generalBankMode').onclick=()=>switchBankMode('general');
  $('studentBankMode').onclick=()=>switchBankMode('student');
  $('staffTestLogin').onclick=enterTestStaff;
  $("brandHome").onclick = () => showChat();
  $("homeNav").onclick = () => showChat();
  $("requestsNav").onclick = showRequests;
  $("supportHistoryNav").onclick = showSupportHistory;
  $("referencesNav").onclick = showReferences;
  $("staffNav").onclick = showStaff;
  $("historySearchToggle").onclick = () => {
    $("historySearch").hidden = !$("historySearch").hidden;
    if (!$("historySearch").hidden) $("historySearch").focus();
  };
  $("historySearch").oninput = renderHistory;
  $("accountButton").onclick = showProfile;
  $("composer").onsubmit = (e) => {
    e.preventDefault();
    sendMessage();
  };
  $("messageInput").onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendMessage();
    }
  };
  $("menuToggle").onclick = () => $("sidebar").classList.toggle("open");
  $("settingsButton").onclick = () => $("settingsDialog").showModal();
  $("modeSelect").onchange = (e) => {
    S.mode = e.target.value;
    toast(t("回答方式已切换，历史保留", "Mode changed; history preserved"));
  };
  $("debugCheckbox").onchange = (e) => {
    S.debug = e.target.checked;
    if (S.view === "chat") renderChat(false);
  };
  $("exportChat").onclick = () => {
    if (!S.current) return;
    const blob = new Blob([JSON.stringify(S.current, null, 2)], {
      type: "application/json",
    });
    const a = el("a");
    a.href = URL.createObjectURL(blob);
    a.download = "campusbank_chat.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  $("loginTab").onclick = () => authKind("login");
  $("registerTab").onclick = () => authKind("register");
  $("authForm").onsubmit = submitAuth;
  $("portalRole").onchange = updateAuthRole;
  $("handoffButton").onclick = startHandoff;
  $("copyStaffInvite").onclick = async () => {
    try {
      await navigator.clipboard.writeText($("staffInviteCode").value);
      toast(t("邀请码已复制", "Invitation copied"));
    } catch {
      toast(
        t("请选中邀请码手动复制", "Select the invitation and copy it manually"),
      );
    }
  };
  $("languageToggle").onclick = () => {
    S.lang = S.lang === "zh" ? "en" : "zh";
    setLanguage();
  };
  $("logoutButton").onclick = async () => {
    try {
      const r = await api("/api/logout", "POST");
      S.boot.user = r.user;
      S.boot.csrf = r.csrf;
      S.boot.portal_role = "customer";
      identityChannel?.postMessage("identity-changed");
      S.staffId = null;
      S.staffDrafts = {};
      S.current = null;
      setChatUrl(null);
      $("profileDialog").close();
      await refreshHistory();
      renderSidebar();
      showChat();
    } catch (e) {
      toast(e.message);
    }
  };
  $("legacyImport").onclick = async () => {
    try {
      const r = await api("/api/admin/import-legacy", "POST");
      await refreshHistory();
      toast(
        t(
          "已导入 " + r.imported + " 段旧会话",
          "Imported " + r.imported + " legacy chats",
        ),
      );
    } catch (e) {
      toast(e.message);
    }
  };
  try {
    S.boot = await api("/api/bootstrap");
    S.chats = await api("/api/chats");
    const requested = new URL(location.href).searchParams.get("chat");
    if (requested) {
      try {
        S.current = await api("/api/chats/" + requested);
      } catch {
        setChatUrl(null);
      }
    }
    setLanguage();
    showChat();
    if (S.boot.portal_role === "staff" && hasStaffAccess()) await showStaff();
    const requestedService = new URL(location.href).searchParams.get("service");
    if (requestedService && serviceBy(requestedService))
      openService(requestedService);
  } catch (e) {
    $("content").replaceChildren(el("div", "empty-state", e.message));
  }
}
setInterval(async () => {
  if (document.hidden) return;
  if (S.view === "staff") {
    await refreshStaff(true);
    return;
  }
  if (S.busy || S.view !== "chat" || !S.current?.ticket) return;
  try {
    const r = await api("/api/chats/" + S.current.id);
    if (
      r.messages.length !== S.current.messages.length ||
      r.ticket?.status !== S.current.ticket?.status
    ) {
      const area = $("scrollArea");
      const bottom =
        area.scrollHeight - area.scrollTop - area.clientHeight < 100;
      S.current = r;
      renderChat(bottom);
    }
  } catch {}
}, 3000);
init();
