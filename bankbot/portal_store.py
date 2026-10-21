"""SQLite account, conversation and service records for the local demo portal."""
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from .catalog import SERVICES
from .dialogue import coerce_state
from dataclasses import asdict
from .language import detect_language


class PortalError(Exception):
    def __init__(self,status,message):super().__init__(message);self.status=status;self.message=message


def now():return datetime.now(timezone.utc).isoformat()
def ident():return uuid.uuid4().hex
def digest(token):return hashlib.sha256(token.encode()).hexdigest()


class PortalStore:
    def __init__(self,path,bootstrap_code='',open_staff_testing=False):
        self.bootstrap_code=bootstrap_code
        self.open_staff_testing=open_staff_testing
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript('''
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL, salt TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, user_id TEXT,
                csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
                state_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sends(chat_id TEXT NOT NULL, request_id TEXT NOT NULL, result TEXT,
                PRIMARY KEY(chat_id,request_id));
            CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, owner TEXT NOT NULL, service_id TEXT NOT NULL,
                chat_id TEXT, payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS request_submissions(owner TEXT NOT NULL, request_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(owner,request_key));
            CREATE TABLE IF NOT EXISTS request_events(id INTEGER PRIMARY KEY AUTOINCREMENT,request_id TEXT NOT NULL,
                actor TEXT NOT NULL,status TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, owner TEXT NOT NULL, chat_id TEXT,
                subject TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
                status TEXT NOT NULL, assigned_to TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS chats_owner ON chats(owner,updated_at);
            CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id,id);
            CREATE TABLE IF NOT EXISTS staff_invites(token_hash TEXT PRIMARY KEY,created_by TEXT NOT NULL,
                expires REAL NOT NULL,used_by TEXT);
            ''')
            if 'is_staff' not in {r['name'] for r in c.execute('PRAGMA table_info(users)')}:
                c.execute('ALTER TABLE users ADD COLUMN is_staff INTEGER NOT NULL DEFAULT 0')
            if 'portal_role' not in {r['name'] for r in c.execute('PRAGMA table_info(sessions)')}:
                c.execute("ALTER TABLE sessions ADD COLUMN portal_role TEXT NOT NULL DEFAULT 'customer'")
            if 'test_staff' not in {r['name'] for r in c.execute('PRAGMA table_info(sessions)')}:
                c.execute('ALTER TABLE sessions ADD COLUMN test_staff INTEGER NOT NULL DEFAULT 0')
            columns={r['name'] for r in c.execute('PRAGMA table_info(requests)')}
            for name,default in [('bank_mode','general'),('staff_note','')]:
                if name not in columns:c.execute(f"ALTER TABLE requests ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'")

    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=20);c.row_factory=sqlite3.Row
        try:yield c;c.commit()
        except Exception:c.rollback();raise
        finally:c.close()

    def new_session(self,user=None,portal_role='customer',test_staff=False):
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        owner='u:'+user['id'] if user else 'g:'+ident()
        with self.db() as c:c.execute('INSERT INTO sessions(token_hash,owner,user_id,csrf,expires,portal_role,test_staff) VALUES(?,?,?,?,?,?,?)',(digest(token),owner,user['id'] if user else None,csrf,time.time()+604800,portal_role,int(test_staff)))
        return token,{'owner':owner,'user':user,'csrf':csrf,'portal_role':portal_role}

    def session(self,token):
        if not token:return None
        with self.db() as c:
            row=c.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?',(digest(token),time.time())).fetchone()
            if not row:return None
            if row['test_staff'] and not self.open_staff_testing:return None
            user=c.execute('SELECT id,username,display_name,is_admin,is_staff FROM users WHERE id=?',(row['user_id'],)).fetchone() if row['user_id'] else None
        user=dict(user) if user else None
        if user and row['test_staff']:user['is_staff']=1
        return {'owner':row['owner'],'user':user,'csrf':row['csrf'],'portal_role':row['portal_role'],'testing_staff':bool(row['test_staff'])}

    def revoke(self,token):
        if token:
            with self.db() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(digest(token),))

    def register(self,username,password,display_name,portal_role='customer',invite_code='',allow_first_admin=True):
        username=username.casefold();salt=secrets.token_hex(16)
        hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
        id_=ident()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            staff=portal_role=='staff'
            if self.bootstrap_code:
                admin=staff and not bool(c.execute('SELECT 1 FROM users WHERE is_admin=1 LIMIT 1').fetchone()) and secrets.compare_digest(invite_code.encode(),self.bootstrap_code.encode())
            else:admin=allow_first_admin and not bool(c.execute('SELECT 1 FROM users LIMIT 1').fetchone())
            if staff and not admin:self._consume_invite(c,invite_code,id_)
            try:c.execute('INSERT INTO users(id,username,display_name,password_hash,salt,is_admin,created_at,is_staff) VALUES(?,?,?,?,?,?,?,?)',(id_,username,display_name,hashed,salt,int(admin),now(),int(staff)))
            except sqlite3.IntegrityError:raise PortalError(409,'该用户名已被使用。') from None
        return {'id':id_,'username':username,'display_name':display_name,'is_admin':int(admin),'is_staff':int(staff)}

    def has_admin(self):
        with self.db() as c:return bool(c.execute('SELECT 1 FROM users WHERE is_admin=1 LIMIT 1').fetchone())

    def login(self,username,password):
        with self.db() as c:row=c.execute('SELECT * FROM users WHERE username=?',(username.casefold(),)).fetchone()
        # Dummy work keeps unknown-account and wrong-password attempts similar.
        salt=bytes.fromhex(row['salt']) if row else bytes(16)
        hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,600000).hex()
        if not row or not hmac.compare_digest(hashed,row['password_hash']):raise PortalError(401,'用户名或密码不正确。')
        return {k:row[k] for k in ('id','username','display_name','is_admin','is_staff')}

    def reset_password(self,username,password):
        """Local recovery only; deliberately not exposed through any HTTP route."""
        if not isinstance(password,str) or not 8<=len(password)<=128 or not password.strip():
            raise PortalError(400,'新密码需要 8 至 128 个字符，且不能全部为空格。')
        salt=secrets.token_hex(16)
        hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            user=c.execute('SELECT id,username FROM users WHERE username=?',(username.casefold(),)).fetchone()
            if not user:raise PortalError(404,'找不到这个用户名，请核对登录用户名。')
            c.execute('UPDATE users SET password_hash=?,salt=? WHERE id=?',(hashed,salt,user['id']))
            revoked=c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],)).rowcount
        return {'username':user['username'],'revoked_sessions':revoked}

    def create_staff_invite(self,user_id):
        code=secrets.token_urlsafe(24);expires=time.time()+86400
        with self.db() as c:
            user=c.execute('SELECT is_admin FROM users WHERE id=?',(user_id,)).fetchone()
            if not user or not user['is_admin']:raise PortalError(403,'只有管理员可以邀请工作人员。')
            c.execute('INSERT INTO staff_invites VALUES(?,?,?,NULL)',(digest(code),user_id,expires))
        return {'invite_code':code,'expires_at':datetime.fromtimestamp(expires,timezone.utc).isoformat(),'single_use':True}

    def _consume_invite(self,c,code,user_id):
        invite=c.execute('SELECT * FROM staff_invites WHERE token_hash=?',(digest(code),)).fetchone()
        if not invite or invite['used_by'] or invite['expires']<=time.time():
            raise PortalError(403,'工作人员需要管理员提供的有效邀请码；邀请码只能使用一次。')
        c.execute('UPDATE staff_invites SET used_by=? WHERE token_hash=?',(user_id,digest(code)))

    def enroll_staff(self,user,code):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE');self._consume_invite(c,code,user['id'])
            c.execute('UPDATE users SET is_staff=1 WHERE id=?',(user['id'],))
        return {**user,'is_staff':1}

    def claim_guest(self,guest,owner):
        if not guest.startswith('g:'):return
        with self.db() as c:c.execute('UPDATE chats SET owner=? WHERE owner=?',(owner,guest))

    def create_chat(self,owner,title='新对话',bank_mode='general'):
        id_=ident();stamp=now()
        state=coerce_state();state.bank_mode=bank_mode
        with self.db() as c:c.execute('INSERT INTO chats VALUES(?,?,?,?,?,?)',(id_,owner,title,json.dumps(asdict(state)),stamp,stamp))
        return self.chat(owner,id_)

    def chat(self,owner,id_):
        with self.db() as c:
            row=c.execute('SELECT * FROM chats WHERE owner=? AND id=?',(owner,id_)).fetchone()
            if not row:raise PortalError(404,'会话不存在或无权访问。')
            messages=[dict(r) for r in c.execute('SELECT * FROM messages WHERE chat_id=? ORDER BY id',(id_,))]
            ticket=c.execute("SELECT id,status FROM tickets WHERE chat_id=? AND status IN ('waiting','active') ORDER BY created_at DESC LIMIT 1",(id_,)).fetchone()
        result=dict(row);result['state']=json.loads(result.pop('state_json'))
        for m in messages:m['metadata']=json.loads(m['metadata'])
        result['messages']=messages;result['ticket']=dict(ticket) if ticket else None
        return result

    def chats(self,owner):
        with self.db() as c:
            return [dict(r) for r in c.execute('SELECT id,title,created_at,updated_at FROM chats WHERE owner=? ORDER BY updated_at DESC',(owner,))]

    def rename_chat(self,owner,id_,title):
        self.chat(owner,id_)
        with self.db() as c:c.execute('UPDATE chats SET title=?,updated_at=? WHERE id=?',(title,now(),id_))

    def append_message(self,id_,role,content,metadata=None):
        with self.db() as c:
            c.execute('INSERT INTO messages(chat_id,role,content,metadata,created_at) VALUES(?,?,?,?,?)',(id_,role,content,json.dumps(metadata or {},ensure_ascii=False),now()))
            c.execute('UPDATE chats SET updated_at=? WHERE id=?',(now(),id_))
            c.execute("UPDATE tickets SET updated_at=? WHERE chat_id=? AND status IN ('waiting','active')",(now(),id_))

    def update_state(self,id_,state):
        with self.db() as c:c.execute('UPDATE chats SET state_json=?,updated_at=? WHERE id=?',(json.dumps(asdict(coerce_state(state)),ensure_ascii=False),now(),id_))

    def begin_send(self,id_,request_id):
        with self.db() as c:
            row=c.execute('SELECT result FROM sends WHERE chat_id=? AND request_id=?',(id_,request_id)).fetchone()
            if row:return (False,json.loads(row['result']) if row['result'] else None)
            c.execute('INSERT INTO sends VALUES(?,?,NULL)',(id_,request_id))
        return True,None

    def finish_send(self,id_,request_id,result):
        with self.db() as c:c.execute('UPDATE sends SET result=? WHERE chat_id=? AND request_id=?',(json.dumps(result,ensure_ascii=False),id_,request_id))

    def validate_form(self,service_id,payload):
        service=SERVICES.get(service_id)
        if not service:raise PortalError(400,'没有对应服务窗口。')
        allowed={f['name'] for f in service['fields']}
        if set(payload)-allowed:raise PortalError(400,'请求包含未知字段。')
        clean={}
        for f in service['fields']:
            value=payload.get(f['name'],'')
            if f['type']=='checkbox':
                if not isinstance(value,bool) or (f['required'] and not value):raise PortalError(400,'请核对并勾选：'+f['label'])
                clean[f['name']]=value;continue
            if not isinstance(value,str):raise PortalError(400,'请填写有效的 '+f['label'])
            value=value.strip()
            if (f['required'] and not value) or len(value)>2000:raise PortalError(400,'请填写 '+f['label'])
            if f['type']=='select' and value not in {o['value'] for o in f['options']}:raise PortalError(400,'请选择有效的 '+f['label'])
            if f['type']=='number':
                try:n=Decimal(value)
                except InvalidOperation:raise PortalError(400,'金额格式不正确。') from None
                minimum=Decimal(10) if f['name']=='opening_deposit' else Decimal('0.01')
                if not n.is_finite() or not minimum<=n<=1000000 or n.as_tuple().exponent < -2:raise PortalError(400,'金额超出允许范围或超过两位小数。')
                value=str(n)
            if f['type']=='date':
                try:visit=date.fromisoformat(value)
                except ValueError:raise PortalError(400,'日期格式不正确。') from None
                if visit < datetime.now(timezone.utc).date():raise PortalError(400,'预约日期不能早于今天。')
            clean[f['name']]=value
        return clean

    def submit(self,owner,service_id,payload,chat_id=None,request_id=None,bank_mode='general'):
        if not owner.startswith('u:'):raise PortalError(401,'请登录后保存办理请求。')
        if chat_id:self.chat(owner,chat_id)
        fingerprint=hashlib.sha256(json.dumps([service_id,payload,chat_id],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        id_='CB'+datetime.now().strftime('%y%m%d')+'-'+secrets.token_hex(4).upper()
        stamp=now()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if request_id:
                previous=c.execute('SELECT fingerprint,result FROM request_submissions WHERE owner=? AND request_key=?',(owner,request_id)).fetchone()
                if previous:
                    if previous['fingerprint']!=fingerprint:raise PortalError(409,'提交标识已用于其他内容，请重新打开服务窗口。')
                    return json.loads(previous['result'])
            clean=self.validate_form(service_id,payload)
            if service_id=='human_support' and chat_id and c.execute("SELECT 1 FROM tickets WHERE chat_id=? AND status IN ('waiting','active')",(chat_id,)).fetchone():
                raise PortalError(409,'当前对话已有人工客服工单，请返回对话继续补充问题。')
            mode='student' if service_id in ('education_loan','funding_enquiry') else coerce_state(self.chat(owner,chat_id)['state']).bank_mode if chat_id else bank_mode
            c.execute('INSERT INTO requests(id,owner,service_id,chat_id,payload,status,created_at,bank_mode) VALUES(?,?,?,?,?,?,?,?)',(id_,owner,service_id,chat_id,json.dumps(clean,ensure_ascii=False),'pending',stamp,mode))
            if service_id=='human_support':
                c.execute('INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?,?,?)',(id_,owner,chat_id,clean['subject'],clean['description'],clean['category'],'waiting',None,stamp,stamp))
            result={'id':id_,'service_id':service_id,'title':SERVICES[service_id]['title'],'status':'pending','created_at':stamp,'payload':clean,'demo':True}
            if request_id:c.execute('INSERT INTO request_submissions VALUES(?,?,?,?)',(owner,request_id,fingerprint,json.dumps(result,ensure_ascii=False)))
        if service_id=='human_support' and chat_id:
            chat=self.chat(owner,chat_id)
            last=next((m['content'] for m in reversed(chat['messages']) if m['role']=='user'),clean['description'])
            language=detect_language(last,coerce_state(chat['state']).language)
            message=('已创建人工客服工单 '+id_+'，等待工作人员接单。后续消息和人工回复会保留在此会话中。') if language=='zh' else ('Support ticket '+id_+' is waiting for a staff member. Your messages and manual replies will stay in this conversation.')
            self.append_message(chat_id,'assistant',message,{'sender':'service','ticket_id':id_})
        return result

    def requests(self,owner):
        with self.db() as c:rows=[dict(r) for r in c.execute('SELECT * FROM requests WHERE owner=? ORDER BY created_at DESC',(owner,))]
        for r in rows:r['payload']=json.loads(r['payload']);r['title']=SERVICES[r['service_id']]['title']
        return rows

    def business_requests(self):
        with self.db() as c:
            rows=[dict(r) for r in c.execute("SELECT r.*,u.display_name AS customer_name FROM requests r LEFT JOIN users u ON r.owner='u:'||u.id WHERE r.service_id!='human_support' ORDER BY r.created_at DESC")]
        for row in rows:
            row['payload']=json.loads(row['payload']);row['title']=SERVICES[row['service_id']]['title']
        return rows

    def business_request(self,id_):
        row=next((r for r in self.business_requests() if r['id']==id_),None)
        if not row:raise PortalError(404,'业务申请不存在。')
        with self.db() as c:row['events']=[dict(r) for r in c.execute('SELECT actor,status,note,created_at FROM request_events WHERE request_id=? ORDER BY id',(id_,))]
        return row

    def review_request(self,id_,user,status,note):
        if status not in ('processing','completed','needs_info'):raise PortalError(400,'请选择有效的业务处理状态。')
        if not isinstance(note,str) or len(note)>2000:raise PortalError(400,'处理备注最长2000字。')
        if status=='needs_info' and not note.strip():raise PortalError(400,'请说明需要客户补充哪些材料。')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT * FROM requests WHERE id=? AND service_id!='human_support'",(id_,)).fetchone()
            if not row:raise PortalError(404,'业务申请不存在。')
            c.execute('UPDATE requests SET status=?,staff_note=? WHERE id=?',(status,note.strip(),id_))
            c.execute('INSERT INTO request_events(request_id,actor,status,note,created_at) VALUES(?,?,?,?,?)',(id_,user['display_name'],status,note.strip(),now()))
        return self.business_request(id_)

    def tickets(self,owner=None):
        query='''SELECT t.*,u.display_name AS customer_name,u.username AS customer_username,
            s.display_name AS assigned_name,(SELECT COUNT(*) FROM messages m WHERE m.chat_id=t.chat_id) AS message_count
            FROM tickets t LEFT JOIN users u ON t.owner='u:'||u.id LEFT JOIN users s ON t.assigned_to=s.id'''
        if owner is not None:query+=' WHERE t.owner=?'
        query+=" ORDER BY CASE t.status WHEN 'waiting' THEN 0 WHEN 'active' THEN 1 ELSE 2 END,t.updated_at DESC"
        with self.db() as c:return [dict(r) for r in c.execute(query,(owner,) if owner is not None else ())]

    def ticket(self,id_):
        with self.db() as c:r=c.execute("SELECT t.*,u.display_name AS customer_name,s.display_name AS assigned_name FROM tickets t LEFT JOIN users u ON t.owner='u:'||u.id LEFT JOIN users s ON t.assigned_to=s.id WHERE t.id=?",(id_,)).fetchone()
        if not r:raise PortalError(404,'工单不存在。')
        return dict(r)

    def claim_ticket(self,id_,user_id):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE');t=c.execute('SELECT * FROM tickets WHERE id=?',(id_,)).fetchone()
            if not t:raise PortalError(404,'工单不存在。')
            if t['status']=='resolved':raise PortalError(409,'工单已结束。')
            if t['assigned_to'] and t['assigned_to']!=user_id:raise PortalError(409,'其他工作人员已接单，请选择待接单工单。')
            c.execute('UPDATE tickets SET status=?,assigned_to=?,updated_at=? WHERE id=?',('active',user_id,now(),id_))
            c.execute('UPDATE requests SET status=? WHERE id=?',('processing',id_))
        return self.ticket(id_)

    def staff_reply(self,id_,user,content):
        if not content.strip():raise PortalError(400,'请输入人工回复。')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE');t=c.execute('SELECT * FROM tickets WHERE id=?',(id_,)).fetchone()
            if not t:raise PortalError(404,'工单不存在。')
            if t['status']=='resolved':raise PortalError(409,'工单已结束。')
            if t['assigned_to'] and t['assigned_to']!=user['id']:raise PortalError(409,'这张工单由其他工作人员处理。')
            stamp=now()
            c.execute('UPDATE tickets SET status=?,assigned_to=?,updated_at=? WHERE id=?',('active',user['id'],stamp,id_))
            c.execute('UPDATE requests SET status=? WHERE id=?',('processing',id_))
            if t['chat_id']:
                metadata=json.dumps({'sender':'staff','staff_name':user['display_name'],'ticket_id':id_},ensure_ascii=False)
                c.execute('INSERT INTO messages(chat_id,role,content,metadata,created_at) VALUES(?,?,?,?,?)',(t['chat_id'],'assistant',content.strip(),metadata,stamp))
                row=c.execute('SELECT state_json FROM chats WHERE id=?',(t['chat_id'],)).fetchone()
                state=coerce_state(json.loads(row['state_json']))
                last=c.execute("SELECT content FROM messages WHERE chat_id=? AND role='user' ORDER BY id DESC LIMIT 1",(t['chat_id'],)).fetchone()
                state.turns.append([{'role':'user','content':last['content'] if last else t['description']},{'role':'assistant','content':content.strip()}])
                c.execute('UPDATE chats SET state_json=?,updated_at=? WHERE id=?',(json.dumps(asdict(state),ensure_ascii=False),stamp,t['chat_id']))
        return self.ticket(id_)

    def resolve_ticket(self,id_,owner=None,staff_id=None):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE');t=c.execute('SELECT * FROM tickets WHERE id=?',(id_,)).fetchone()
            if not t:raise PortalError(404,'工单不存在。')
            if owner is not None and t['owner']!=owner:raise PortalError(404,'工单不存在。')
            if staff_id and t['assigned_to'] and t['assigned_to']!=staff_id:raise PortalError(409,'这张工单由其他工作人员处理。')
            c.execute('UPDATE tickets SET status=?,updated_at=? WHERE id=?',('resolved',now(),id_))
            c.execute('UPDATE requests SET status=? WHERE id=?',('completed',id_))
        return self.ticket(id_)

    def import_legacy(self,owner,records):
        imported=0
        for record in records:
            id_=record['id'];state=coerce_state(record['state']);display=record['display']
            title=next((m['content'][:35] for m in display if m.get('role')=='user'),'旧版会话')
            with self.db() as c:
                if c.execute('SELECT 1 FROM chats WHERE id=?',(id_,)).fetchone():continue
                c.execute('INSERT INTO chats VALUES(?,?,?,?,?,?)',(id_,owner,title,json.dumps(asdict(state),ensure_ascii=False),record['time'],record['time']))
                for m in display:
                    if m.get('role') in ('user','assistant') and isinstance(m.get('content'),str):
                        c.execute('INSERT INTO messages(chat_id,role,content,metadata,created_at) VALUES(?,?,?,?,?)',(id_,m['role'],m['content'],json.dumps(m.get('details',{}),ensure_ascii=False),record['time']))
                imported+=1
        return imported
