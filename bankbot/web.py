"""Local banking portal API and static front end. Run python -m bankbot.web."""
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict
from urllib.parse import urlparse
import argparse
import hashlib
import json
import secrets
import threading
import time
import uuid
import queue
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from .config import ROOT, Settings
from .portal_store import PortalStore, PortalError
from .catalog import CATEGORIES, SERVICES, BANK_REFERENCES
from .dialogue import coerce_state
from .history import repair_display
from .language import detect_language
from .ui_runtime import reply_details
from .errors import public_error
from .student_finance import PROGRAMS,search_funding
from .scenarios import validate_scenario

COOKIE='campusbank_session'

class Body(BaseModel):model_config=ConfigDict(extra='forbid')
class LoginBody(Body):
    username:str=Field(min_length=3,max_length=32,pattern=r'^[A-Za-z0-9_]+$')
    password:str=Field(min_length=8,max_length=128)
    portal_role:str=Field(default='customer',pattern=r'^(customer|staff)$')
    invite_code:str=Field(default='',max_length=128)
class RegisterBody(LoginBody):
    display_name:str=Field(min_length=1,max_length=50)
    test_access_code:str=Field(default='',max_length=128)
class SendBody(Body):
    text:str=Field(min_length=1,max_length=2000)
    mode:str=Field(default='agent',pattern=r'^(agent|rag|llm|offline)$')
    request_id:str=Field(default_factory=lambda:uuid.uuid4().hex,pattern=r'^[a-f0-9]{32}$')
    bank_mode:str|None=Field(default=None,pattern=r'^(general|student)$')
class CreateChatBody(Body):
    bank_mode:str=Field(default='general',pattern=r'^(general|student)$')
class ReviewRequestBody(Body):
    status:str=Field(pattern=r'^(processing|completed|needs_info)$')
    note:str=Field(default='',max_length=2000)
class RenameBody(Body):title:str=Field(min_length=1,max_length=80)
class SubmitBody(Body):
    service_id:str
    payload:dict
    chat_id:str|None=None
    confirmed:bool=False
    request_id:str=Field(default_factory=lambda:uuid.uuid4().hex,pattern=r'^[a-f0-9]{32}$')
    bank_mode:str=Field(default='general',pattern=r'^(general|student)$')
    scenario:dict|None=None
class ScenarioBody(Body):
    service_id:str
    payload:dict
    scenario:dict
class ReplyBody(Body):text:str=Field(min_length=1,max_length=2000)
class RoleBody(Body):portal_role:str=Field(pattern=r'^(customer|staff)$')
class ArchiveBody(Body):archived:bool
class FeedbackBody(Body):
    helpful:bool
    reason:str=Field(default='helpful',pattern=r'^(helpful|irrelevant|missing_details|misunderstood|incorrect|other)$')
    comment:str=Field(default='',max_length=300)
class RequestActionBody(Body):
    action:str=Field(pattern=r'^(supplement|withdraw)$')
    payload:dict=Field(default_factory=dict)
    scenario:dict|None=None
    request_id:str=Field(default_factory=lambda:uuid.uuid4().hex,pattern=r'^[a-f0-9]{32}$')


def public_chat(chat):
    result={k:chat[k] for k in ('id','title','created_at','updated_at','messages','ticket')}
    result['service_drafts']=coerce_state(chat['state']).service_drafts
    result['bank_mode']=coerce_state(chat['state']).bank_mode
    result['service_context']={'transfer_currency':coerce_state(chat['state']).constraints.get('transfer_currency')}
    return result


def create_app(db_path=None,service=None):
    from .service import ChatService
    app=FastAPI(title='CampusBank local demo portal',docs_url=None,redoc_url=None)
    settings=Settings.load()
    store=PortalStore(db_path or settings.database_path or ROOT/'logs/portal.sqlite3',bootstrap_code=settings.bootstrap_code if settings.cloud_mode else '',open_staff_testing=settings.open_staff_testing,staff_access_code=settings.staff_access_code)
    bot=service or ChatService(settings)
    app.state.store=store;app.state.bot=bot
    locks={};locks_guard=threading.Lock();login_attempts={};send_attempts={};quota_guard=threading.Lock()

    def session(req):
        value=store.session(req.cookies.get(COOKIE))
        if not value:raise PortalError(401,'会话已失效，请刷新页面。')
        return value

    def mutate(req):
        who=session(req)
        if not secrets.compare_digest(req.headers.get('X-CSRF-Token',''),who['csrf']):raise PortalError(403,'页面验证失败，请刷新。')
        origin=req.headers.get('origin')
        if settings.cloud_mode and not settings.public_url:raise PortalError(503,'公网地址尚未配置完成，请联系部署者。')
        expected=settings.public_url or str(req.base_url).rstrip('/')
        if origin and origin!=expected:
            raise PortalError(403,'只接受本页面发起的请求。')
        return who

    def admin(req,write=False):
        who=mutate(req) if write else session(req)
        if who['portal_role']!='staff':raise PortalError(403,'当前是客户身份，请先切换到工作人员身份。')
        if not who['user'] or not (who['user']['is_admin'] or who['user']['is_staff']):raise PortalError(403,'需要工作人员权限。')
        return who

    def manager(req,write=False):
        who=admin(req,write)
        if not who['user']['is_admin']:raise PortalError(403,'此操作需要管理员权限。')
        return who

    def set_cookie(response,token,req):
        response.set_cookie(COOKIE,token,max_age=604800,httponly=True,samesite='strict',secure=settings.cloud_mode or req.url.scheme=='https',path='/')

    @app.exception_handler(PortalError)
    async def portal_error(req,exc):
        retry=getattr(exc,'retry_after',60) if exc.status==429 else None
        return JSONResponse({'detail':public_error(exc.message,req.headers.get('Accept-Language','zh')),
                            **({'retry_after':retry} if retry else {})},status_code=exc.status,
                            headers={'Retry-After':str(retry)} if retry else None)

    @app.middleware('http')
    async def security_headers(req,call_next):
        response=await call_next(req)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers['Cache-Control']='no-store, no-transform' if response.headers.get('content-type','').startswith('text/event-stream') else 'no-store'
        return response

    @app.get('/api/bootstrap')
    def bootstrap(req:Request,response:Response):
        who=store.session(req.cookies.get(COOKIE))
        if not who:
            token,who=store.new_session();set_cookie(response,token,req)
        return {'user':who['user'],'csrf':who['csrf'],'categories':CATEGORIES,'services':list(SERVICES.values()),
                'bank_references':BANK_REFERENCES,'api_available':bool(settings.api_key),'version':'2.6.1','portal_role':who['portal_role'],
                'open_staff_testing':settings.open_staff_testing,'testing_staff':who.get('testing_staff',False),'funding_programs':PROGRAMS,
                'today':datetime.now(timezone.utc).date().isoformat(),
                'requires_login':settings.cloud_mode,'registration_access_code_required':settings.cloud_mode,
                'limits':{'account_per_minute':settings.demo_rpm if who.get('user') and who['user']['username'].casefold() in settings.demo_accounts else settings.account_rpm,'global_per_minute':settings.global_rpm,'demo_profile':bool(who.get('user') and who['user']['username'].casefold() in settings.demo_accounts)},
                'first_admin_setup_required':settings.cloud_mode and not store.has_admin()}

    def sign_in(req,response,user,old,portal_role='customer',test_staff=False):
        token,_=store.new_session(user,portal_role,test_staff)
        who=store.session(token)
        store.claim_guest(old['owner'],who['owner'])
        store.revoke(req.cookies.get(COOKIE));set_cookie(response,token,req)
        return {'user':who['user'],'csrf':who['csrf'],'portal_role':portal_role,'testing_staff':who.get('testing_staff',False)}

    @app.post('/api/register')
    def register(body:RegisterBody,req:Request,response:Response):
        old=mutate(req)
        if old['user']:raise PortalError(409,'请先退出当前账户。')
        if not body.display_name.strip():raise PortalError(400,'请填写称呼。')
        if settings.cloud_mode and body.portal_role=='customer' and not secrets.compare_digest(body.test_access_code.encode(),settings.test_access_code.encode()):
            raise PortalError(403,'请输入部署者提供的小组测试邀请码。')
        testing=settings.open_staff_testing and body.portal_role=='staff'
        user=store.register(body.username,body.password,body.display_name.strip(),'customer' if testing else body.portal_role,body.invite_code.strip(),allow_first_admin=not testing)
        return sign_in(req,response,user,old,body.portal_role,testing)

    @app.post('/api/login')
    def login(body:LoginBody,req:Request,response:Response):
        old=mutate(req);key=(req.client.host if req.client else 'local',body.username.casefold())
        if old['user']:raise PortalError(409,'请先退出当前账户。')
        attempts=[t for t in login_attempts.get(key,[]) if t>time.time()-300]
        if len(attempts)>=8:raise PortalError(429,'登录尝试过于频繁，请稍后再试。')
        try:user=store.login(body.username,body.password)
        except PortalError:login_attempts[key]=attempts+[time.time()];raise
        testing=settings.open_staff_testing and body.portal_role=='staff'
        if body.portal_role=='staff' and not testing and not (user['is_admin'] or user['is_staff']):
            if not body.invite_code.strip():raise PortalError(403,'此账户尚未开通工作人员权限，请向管理员申请邀请码。')
            user=store.enroll_staff(user,body.invite_code.strip())
        login_attempts.pop(key,None)
        return sign_in(req,response,user,old,body.portal_role,testing)

    @app.post('/api/testing/staff-session')
    def testing_staff(req:Request,response:Response):
        old=mutate(req)
        if not settings.open_staff_testing:raise PortalError(403,'测试客服入口已关闭，请使用工作人员邀请码。')
        key=('testing_staff',req.client.host if req.client else 'local')
        recent=[t for t in login_attempts.get(key,[]) if t>time.time()-60]
        if len(recent)>=30:raise PortalError(429,'请稍后再进入测试客服。')
        login_attempts[key]=recent+[time.time()]
        user=old['user'] or store.register('test_staff_'+secrets.token_hex(4),secrets.token_urlsafe(32),'测试客服-'+secrets.token_hex(2),allow_first_admin=False)
        return sign_in(req,response,user,old,'staff',True)

    @app.post('/api/logout')
    def logout(req:Request,response:Response):
        mutate(req);store.revoke(req.cookies.get(COOKIE))
        token,who=store.new_session();set_cookie(response,token,req)
        return {'user':None,'csrf':who['csrf'],'portal_role':'customer'}

    @app.post('/api/session/role')
    def switch_role(body:RoleBody,req:Request,response:Response):
        who=mutate(req);user=who['user']
        if not user:raise PortalError(401,'请先登录。')
        testing=settings.open_staff_testing and body.portal_role=='staff'
        if body.portal_role=='staff' and not testing and not (user['is_admin'] or user['is_staff']):raise PortalError(403,'此账户尚未开通工作人员权限。')
        return sign_in(req,response,user,who,body.portal_role,testing)

    @app.get('/api/chats')
    def chats(req:Request,archived:bool=False):return store.chats(session(req)['owner'],archived)

    @app.patch('/api/chats/{id_}/archive')
    def archive_chat(id_:str,body:ArchiveBody,req:Request):return store.archive_chat(mutate(req)['owner'],id_,body.archived)

    @app.post('/api/chats/{id_}/messages/{message_id}/feedback')
    def feedback(id_:str,message_id:int,body:FeedbackBody,req:Request):return store.save_feedback(mutate(req)['owner'],id_,message_id,body.helpful,body.reason,body.comment)

    @app.post('/api/chats')
    def new_chat(req:Request,body:CreateChatBody|None=None):return public_chat(store.create_chat(mutate(req)['owner'],bank_mode=body.bank_mode if body else 'general'))

    @app.get('/api/student-funding')
    def student_funding(level:str|None=None,kind:str|None=None):return {'fictional':True,'programs':search_funding(level=level,kind=kind)}

    @app.get('/api/chats/{id_}')
    def chat(id_:str,req:Request):return public_chat(store.chat(session(req)['owner'],id_))

    @app.patch('/api/chats/{id_}')
    def rename(id_:str,body:RenameBody,req:Request):
        who=mutate(req);store.rename_chat(who['owner'],id_,body.title.strip());return {'ok':True}

    @app.post('/api/chats/{id_}/handoff')
    def handoff(id_:str,req:Request):
        who=mutate(req)
        if not who['user']:raise PortalError(401,'请先登录，以便接收工作人员回复。')
        with locks_guard:lock=locks.setdefault(id_,threading.Lock())
        with lock:
            current=store.chat(who['owner'],id_)
            if current['ticket']:return {'ticket':store.ticket(current['ticket']['id']),'chat':public_chat(current),'existing':True}
            recent=[m['content'] for m in current['messages'] if m['role']=='user']
            description=recent[-1] if recent else '客户从聊天窗口请求人工客服。'
            result=store.submit(who['owner'],'human_support',{'category':'other','subject':current['title'][:80] if current['title']!='新对话' else '聊天转人工客服','description':description},id_)
            return {'ticket':store.ticket(result['id']),'chat':public_chat(store.chat(who['owner'],id_)),'existing':False}

    def perform_send(id_:str,body:SendBody,req:Request,on_event=None):
        request_started=time.monotonic()
        who=mutate(req);store.chat(who['owner'],id_)
        if settings.cloud_mode and not who['user']:raise PortalError(401,'请登录后再开始咨询。')
        if not body.text.strip():raise PortalError(400,'请输入问题。')
        with locks_guard:lock=locks.setdefault(id_,threading.Lock())
        with lock:
            fresh,saved=store.begin_send(id_,body.request_id)
            queue_wait_ms=round((time.monotonic()-request_started)*1000)
            if not fresh:
                if saved:return saved
                raise PortalError(409,'这条消息正在处理，请稍后查看记录。')
            current=store.chat(who['owner'],id_)
            if settings.cloud_mode and not current['ticket'] and body.mode!='offline':
                with quota_guard:
                    stamp=time.time()
                    recent=[t for t in send_attempts.get(who['owner'],[]) if t>stamp-60]
                    global_recent=[t for t in send_attempts.get('*',[]) if t>stamp-60]
                    hourly=[t for t in send_attempts.get('hour',[]) if t>stamp-3600]
                    limit=settings.demo_rpm if who['user'] and who['user']['username'].casefold() in settings.demo_accounts else settings.account_rpm
                    if len(recent)>=limit or len(global_recent)>=settings.global_rpm or len(hourly)>=settings.hourly_requests:
                        # Release this idempotency reservation so the same message can be retried later.
                        with store.db() as c:c.execute('DELETE FROM sends WHERE chat_id=? AND request_id=?',(id_,body.request_id))
                        error=PortalError(429,'咨询过于频繁，请稍等一分钟后重试。')
                        blocked,window=(hourly,3600) if len(hourly)>=settings.hourly_requests else (recent,60) if len(recent)>=limit else (global_recent,60)
                        error.retry_after=max(1,int(window-(stamp-min(blocked)))+1)
                        raise error
                    send_attempts[who['owner']]=recent+[stamp];send_attempts['*']=global_recent+[stamp]
                    send_attempts['hour']=hourly+[stamp]
            store.append_message(id_,'user',body.text)
            if current['title']=='新对话':store.rename_chat(who['owner'],id_,body.text[:30])
            if current['ticket']:
                language=detect_language(body.text)
                answer='消息已送入人工客服队列，工作人员接单后会在这里回复。' if language=='zh' else 'Your message is saved in the support queue. A demo staff member can reply here.'
                meta={'sender':'service','ticket_id':current['ticket']['id'],'actions':[],'mode':'human_queue'}
            else:
                state=coerce_state(current['state'])
                if body.bank_mode:state.bank_mode=body.bank_mode
                try:
                    reply=bot.respond_stream(body.text,state,body.mode,on_event=on_event) if on_event is not None and hasattr(bot,'respond_stream') else bot.respond(body.text,state,body.mode)
                    answer=reply.answer;meta=reply_details(reply,body.text,state.language)
                    meta['actions']=getattr(reply,'actions',[])
                    meta['followups']=getattr(reply,'followups',[])
                    for action in meta['actions']:
                        if action['service_id']=='open_account' and reply.state.product in ('student_account','everyday_account'):
                            action.setdefault('prefill',{})['product']=reply.state.product
                    store.update_state(id_,reply.state)
                except Exception:
                    answer='处理时发生错误，问题与历史已经保留，请稍后重试。' if detect_language(body.text)=='zh' else 'I could not process this request. Your messages are saved; please try again.'
                    meta={'mode':'error','error':'application_error','actions':[]}
                    state.turns.append([{'role':'user','content':body.text},{'role':'assistant','content':answer}]);store.update_state(id_,state)
            meta['server_ms']=round((time.monotonic()-request_started)*1000)
            meta['queue_ms']=queue_wait_ms
            store.append_message(id_,'assistant',answer,meta)
            result=public_chat(store.chat(who['owner'],id_));store.finish_send(id_,body.request_id,result)
            return result

    @app.post('/api/chats/{id_}/messages')
    def send(id_:str,body:SendBody,req:Request):return perform_send(id_,body,req)

    @app.post('/api/chats/{id_}/stream')
    def stream_send(id_:str,body:SendBody,req:Request):
        who=mutate(req);store.chat(who['owner'],id_)
        if settings.cloud_mode and not who['user']:raise PortalError(401,'请登录后再开始咨询。')
        if not body.text.strip():raise PortalError(400,'请输入问题。')
        events=queue.SimpleQueue();abandoned=threading.Event()
        def emit(event):
            if not abandoned.is_set():events.put(event)
        def work():
            try:emit({'type':'complete','chat':perform_send(id_,body,req,on_event=emit)})
            except PortalError as exc:emit({'type':'error','status':exc.status,'detail':public_error(exc.message,req.headers.get('Accept-Language','zh')),'retry_after':getattr(exc,'retry_after',60) if exc.status==429 else 0})
            except Exception:emit({'type':'error','status':500,'detail':'连接中断，请刷新记录后重试。' if req.headers.get('Accept-Language','zh').startswith('zh') else 'The connection was interrupted. Refresh your history before retrying.'})
            finally:events.put(None)
        def chunks():
            try:
                yield 'data: '+json.dumps({'type':'start'})+'\n\n'
                threading.Thread(target=work,daemon=True).start()
                while True:
                    try:event=events.get(timeout=10)
                    except queue.Empty:yield ': keepalive\n\n';continue
                    if event is None:break
                    yield 'data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
            finally:abandoned.set()
        return StreamingResponse(chunks(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no','Cache-Control':'no-store, no-transform'})

    @app.get('/api/requests')
    def requests(req:Request,archived:bool=False):return store.requests(session(req)['owner'],archived)

    @app.patch('/api/requests/{id_}/archive')
    def archive_request(id_:str,body:ArchiveBody,req:Request):return store.archive_request(mutate(req)['owner'],id_,body.archived)

    @app.get('/api/requests/{id_}')
    def own_request(id_:str,req:Request):return store.own_request(session(req)['owner'],id_)

    @app.post('/api/requests/{id_}/action')
    def request_action(id_:str,body:RequestActionBody,req:Request):return store.customer_request_action(mutate(req)['owner'],id_,body.action,body.payload,body.scenario,body.request_id)

    @app.post('/api/scenarios/preview')
    def scenario_preview(body:ScenarioBody,req:Request):
        mutate(req)
        service=SERVICES.get(body.service_id)
        if not service or not service.get('scenario'):raise PortalError(400,'没有对应服务窗口。')
        # Preview calculates the scenario; final submission checks every actual consent.
        preview={**body.payload,**{f['name']:True for f in service['fields'] if f['type']=='checkbox'}}
        clean=store.validate_form(body.service_id,preview)
        try:return validate_scenario(body.service_id,body.scenario,clean,today=datetime.now(timezone.utc).date(),confirm=False)
        except ValueError as exc:raise PortalError(400,str(exc)) from None

    @app.get('/api/support-tickets')
    def customer_tickets(req:Request):return store.tickets(session(req)['owner'])

    @app.get('/api/support-tickets/{id_}')
    def customer_ticket(id_:str,req:Request):
        who=session(req);t=store.ticket(id_)
        if t['owner']!=who['owner']:raise PortalError(404,'工单不存在或无权访问。')
        return {'ticket':t,'chat':public_chat(store.chat(who['owner'],t['chat_id'])) if t['chat_id'] else None}

    @app.post('/api/requests')
    def submit(body:SubmitBody,req:Request):
        who=mutate(req)
        if not body.confirmed:raise PortalError(400,'请核对信息后确认提交。')
        return store.submit(who['owner'],body.service_id,body.payload,body.chat_id,body.request_id,body.bank_mode,scenario=body.scenario)

    @app.get('/api/admin/requests')
    def business_requests(req:Request,archived:bool=False):admin(req);return store.business_requests(archived)

    @app.get('/api/admin/requests/{id_}')
    def business_request(id_:str,req:Request):admin(req);return store.business_request(id_)

    @app.patch('/api/admin/requests/{id_}')
    def review_request(id_:str,body:ReviewRequestBody,req:Request):return store.review_request(id_,admin(req,True)['user'],body.status,body.note)

    @app.post('/api/tickets/{id_}/resume-ai')
    def resume(id_:str,req:Request):return store.resolve_ticket(id_,mutate(req)['owner'])

    @app.get('/api/admin/tickets')
    def tickets(req:Request):admin(req);return store.tickets()

    @app.get('/api/admin/tickets/{id_}')
    def ticket(id_:str,req:Request):
        admin(req);t=store.ticket(id_)
        return {'ticket':t,'chat':public_chat(store.chat(t['owner'],t['chat_id'])) if t['chat_id'] else None}

    @app.post('/api/admin/tickets/{id_}/claim')
    def claim(id_:str,req:Request):return store.claim_ticket(id_,admin(req,True)['user']['id'])

    @app.post('/api/admin/tickets/{id_}/reply')
    def staff_reply(id_:str,body:ReplyBody,req:Request):return store.staff_reply(id_,admin(req,True)['user'],body.text)

    @app.post('/api/admin/tickets/{id_}/resolve')
    def resolve(id_:str,req:Request):
        who=admin(req,True);return store.resolve_ticket(id_,staff_id=None if who['user']['is_admin'] else who['user']['id'])

    @app.post('/api/admin/staff-invites')
    def staff_invite(req:Request):return store.create_staff_invite(manager(req,True)['user']['id'])

    @app.post('/api/admin/import-legacy')
    def import_legacy(req:Request):
        who=manager(req,True);records=[]
        for file in (ROOT/'logs/conversations').glob('*.json'):
            try:
                uuid.UUID(file.stem)
                if file.stat().st_size>8_000_000:continue
                r=json.loads(file.read_text(encoding='utf-8'))
                display=repair_display(r.get('display',[]),r.get('state'))
                if not any(m.get('role')=='user' for m in display):continue
                records.append({'id':file.stem,'time':datetime.fromtimestamp(file.stat().st_mtime,timezone.utc).isoformat(),'state':r.get('state'),'display':display})
            except (OSError,ValueError,TypeError,AttributeError):continue
        return {'imported':store.import_legacy(who['owner'],records)}

    @app.get('/api/health')
    def health():return {'ok':True,'version':'2.6.1'}

    app.mount('/assets',StaticFiles(directory=ROOT/'web'),name='assets')
    @app.get('/')
    def index():
        assets=ROOT/'web'
        revision=hashlib.sha256()
        for name in ('index.html','app.js','style.css'):
            revision.update((assets/name).read_bytes())
        version=revision.hexdigest()[:12]
        html=(assets/'index.html').read_text(encoding='utf-8')
        for name in ('app.js','style.css'):
            html=html.replace(f'/assets/{name}',f'/assets/{name}?v={version}')
        return HTMLResponse(html)
    return app


def main():
    import uvicorn
    p=argparse.ArgumentParser(description='Start the local CampusBank web portal.')
    p.add_argument('--port',type=int,default=8501)
    p.add_argument('--host',choices=('127.0.0.1','0.0.0.0'),default='127.0.0.1',help='Use 0.0.0.0 for an explicitly requested LAN demo.')
    args=p.parse_args()
    if not 1 <= args.port <= 65535:
        p.error('--port must be between 1 and 65535')
    print('CampusBank: loading local knowledge and chat storage...',flush=True)
    app=create_app()
    print(f'Open in your browser after startup completes: http://127.0.0.1:{args.port}',flush=True)
    print('Keep this terminal open. Press Ctrl+C to stop the server.',flush=True)
    if args.host=='0.0.0.0':print(f'LAN demo enabled: other computers use http://<this computer LAN IPv4>:{args.port}',flush=True)
    uvicorn.run(app,host=args.host,port=args.port,log_level='info')


if __name__=='__main__':main()
