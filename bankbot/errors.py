"""Translate public portal errors without leaking internal exceptions."""
MESSAGES = {
 '请选择有效的反馈原因。':'Choose a valid feedback reason.',
 '反馈选项与原因不一致。':'The feedback choice and reason do not match.',
 '只能评价 AI 咨询回答。':'Only AI consultation answers can be rated.',
 '只能归档已完成或已撤回的申请。':'Only completed or withdrawn requests can be archived.',
 '工作人员标记待补充资料后才能补充。':'Staff must mark the request as needing information before it can be supplemented.',
 '这项申请已结束，不能再修改。':'This request has ended and cannot be changed.',
 '这项申请已经撤回。':'This request has already been withdrawn.',
 '请先结束当前人工客服工单。':'Finish the active support ticket first.',
 '请保留原申请的场景资料。':'Keep the original request scenario details.',
 '预约日期不能早于今天。':'The visit date cannot be earlier than today.',
 '日期格式不正确。':'Enter a valid visit date.',
 '金额格式不正确。':'Enter a valid amount.',
 '金额超出允许范围或超过两位小数。':'Enter an amount within the allowed range with at most two decimal places.',
 '咨询过于频繁，请稍等一分钟后重试。':'Too many questions. Please wait before retrying.',
 '提交标识已用于其他内容，请重新打开服务窗口。':'This submission ID belongs to different details. Reopen the service window.',
 '请核对信息后确认提交。':'Review the details before confirming.',
 '请登录后保存办理请求。':'Sign in before saving a request.',
 '请登录后再开始咨询。':'Sign in before starting a conversation.',
 '请输入问题。':'Enter a question.',
 '用户名或密码不正确。':'The username or password is incorrect.',
 '用户名已被使用。':'That username is already in use.',
 '会话已失效，请刷新页面。':'Your session expired. Refresh the page and sign in again.',
 '当前对话已有人工客服工单，请返回对话继续补充问题。':'This chat already has a support ticket. Continue in the original conversation.',
}

def public_error(message, language):
    if not language.lower().startswith('en'):return message
    if message in MESSAGES:return MESSAGES[message]
    from .scenarios import ERRORS
    if message in ERRORS:return ERRORS[message]
    from .catalog import SERVICES
    for prefix,translated in [('请填写有效的 ','Enter a valid value for: '),('请填写 ','Please complete: '),('请选择有效的 ','Please select: '),('请核对并勾选：','Please review and confirm: ')]:
        if message.startswith(prefix):
            label=message[len(prefix):]
            field=next((f for s in SERVICES.values() for f in s['fields'] if f['label']==label),None)
            return translated+(field['label_en'] if field else 'the required field')
    return 'Unable to complete this request. Check your details, permissions, and current session, then retry.'
