import json, os, sqlite3, threading, webbrowser, sys, secrets, time, hashlib, socket, ssl
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
try:
    import certifi
except ImportError:
    certifi=None

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
PORT = int(os.environ.get('PROJECT_MANAGER_PORT', '8765'))
LAN_PORT = int(os.environ.get('PROJECT_MANAGER_LAN_PORT', '18766'))
lan_server = None
locks = {}
locks_guard = threading.Lock()
default_data = (Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'LocalProjectWorkspace') if sys.platform == 'win32' else (Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'local-project-manager')
DATA = Path(os.environ.get('PROJECT_MANAGER_DATA', default_data))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'projects.sqlite3'

if DB.exists() and DB.stat().st_size:
    with sqlite3.connect(DB) as existing:
        present={r[1] for r in existing.execute('PRAGMA table_info(tasks)')}
        event_present={r[1] for r in existing.execute('PRAGMA table_info(events)')}
        if present and (not {'tags','sort_order'} <= present or not {'old_status','new_status','project_id'} <= event_present):
            backup_path=DATA / ('projects-before-upgrade-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)+'.sqlite3')
            with sqlite3.connect(backup_path) as backup: existing.backup(backup)

def db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

with db() as c:
    c.executescript("""CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), title TEXT NOT NULL, status TEXT NOT NULL DEFAULT '待开始', priority TEXT NOT NULL DEFAULT '中', owner TEXT NOT NULL DEFAULT '', start_date TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL DEFAULT '', actual_start TEXT NOT NULL DEFAULT '', actual_end TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', subtasks TEXT NOT NULL DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, task_id INTEGER, description TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, enabled INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, remind_at TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'once', enabled INTEGER NOT NULL DEFAULT 1, last_fired TEXT NOT NULL DEFAULT '');""")
    columns={r['name'] for r in c.execute('PRAGMA table_info(tasks)')}
    if 'tags' not in columns: c.execute("ALTER TABLE tasks ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
    if 'sort_order' not in columns: c.execute('ALTER TABLE tasks ADD COLUMN sort_order REAL NOT NULL DEFAULT 0')
    event_columns={r['name'] for r in c.execute('PRAGMA table_info(events)')}
    for column in ('old_status','new_status','project_id'):
        if column not in event_columns: c.execute('ALTER TABLE events ADD COLUMN '+column+' '+('INTEGER' if column=='project_id' else 'TEXT'))
    c.execute('CREATE TABLE IF NOT EXISTS reminder_deliveries(reminder_id INTEGER NOT NULL, member_id INTEGER NOT NULL, last_fired TEXT NOT NULL, PRIMARY KEY(reminder_id,member_id))')
c.close()

def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()
def lan_address():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try: s.connect(('192.0.2.1',9)); return s.getsockname()[0]
    except OSError: return '请填写主机的局域网 IP'
    finally: s.close()

def start_lan():
    global lan_server
    if lan_server is None:
        lan_server=ThreadingHTTPServer(('0.0.0.0',LAN_PORT),Handler)
        lan_server.lan=True
        threading.Thread(target=lan_server.serve_forever,daemon=True).start()

def stop_lan():
    global lan_server
    if lan_server:
        server=lan_server; lan_server=None
        server.shutdown(); server.server_close()

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
    def out(self, obj, status=200):
        body=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def body(self):
        n=int(self.headers.get('Content-Length','0'))
        if n>20000000: raise ValueError('请求过大（最多 20 MB）')
        return json.loads(self.rfile.read(n) or b'{}')
    def identity(self):
        if not getattr(self.server,'lan',False):
            host=self.headers.get('Host','').split(':')[0]
            if host not in ('127.0.0.1','localhost','[::1]'): return None
            return {'id':0,'name':'本机主机','role':'owner'}
        auth=self.headers.get('Authorization','')
        if not auth.startswith('Bearer '): return None
        with db() as c:
            row=c.execute('SELECT id,name,role FROM members WHERE token_hash=? AND enabled=1',(token_hash(auth[7:]),)).fetchone()
            return dict(row) if row else None
    def authorized(self, write=False):
        user=self.identity()
        if not user: self.out({'error':'请使用主机签发的邀请链接加入'},401); return None
        if write and user['role']=='viewer': self.out({'error':'当前身份为只读'},403); return None
        return user
    def owner(self,user):
        if user['role']!='owner': self.out({'error':'仅主机可执行此操作'},403); return False
        return True
    def do_GET(self):
        if self.path == '/api/state':
            user=self.authorized()
            if not user: return
            with db() as c:
                state={k:[dict(r) for r in c.execute('SELECT * FROM '+k+' ORDER BY id DESC')] for k in ('projects','tasks','events','reminders')}
                state['identity']=user; state['sharing']=bool(lan_server)
                if user['role']=='owner':
                    state['members']=[dict(r) for r in c.execute('SELECT id,name,role,enabled FROM members ORDER BY id DESC')]
                    state['reminder_deliveries']=[dict(r) for r in c.execute('SELECT reminder_id,member_id,last_fired FROM reminder_deliveries WHERE member_id=0')]
                self.out(state)
        elif self.path == '/api/reminders-due':
            user=self.authorized()
            if not user: return
            now=datetime.now(); due=[]
            with db() as c:
                for row in c.execute("SELECT r.*,t.title,t.status,t.owner FROM reminders r JOIN tasks t ON t.id=r.task_id WHERE r.enabled=1 AND t.status!='已完成'").fetchall():
                    try: when=datetime.fromisoformat(row['remind_at'])
                    except ValueError: continue
                    if user['role']!='owner' and user['name'] not in [n.strip() for n in row['owner'].replace('，',',').split(',')]: continue
                    delivery=c.execute('SELECT last_fired FROM reminder_deliveries WHERE reminder_id=? AND member_id=?',(row['id'],user['id'])).fetchone()
                    fired=delivery['last_fired'] if delivery else (row['last_fired'] if user['id']==0 else '')
                    if now>=when and (not fired if row['mode']=='once' else fired[:10]!=now.date().isoformat() and now.time()>=when.time()):
                        due.append({'id':row['id'],'title':row['title']})
            self.out(due)
        else: super().do_GET()
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            host=self.headers.get('Host','')
            if origin != 'http://'+host or self.headers.get_content_type() != 'application/json':
                self.out({'error':'请求来源不被允许'},403); return
            data=self.body()
            user=self.authorized(write=self.path not in ('/api/ai','/api/reminder-ack'))
            if not user: return
            if self.path == '/api/reminder-ack':
                reminder_id=int(data['id']);now=datetime.now().isoformat()
                with db() as c:
                    row=c.execute('SELECT r.id,t.owner FROM reminders r JOIN tasks t ON t.id=r.task_id WHERE r.id=? AND r.enabled=1',(reminder_id,)).fetchone()
                    if not row or (user['role']!='owner' and user['name'] not in [n.strip() for n in row['owner'].replace('，',',').split(',')]): raise ValueError('提醒不存在或未分配给你')
                    c.execute('INSERT INTO reminder_deliveries(reminder_id,member_id,last_fired) VALUES (?,?,?) ON CONFLICT(reminder_id,member_id) DO UPDATE SET last_fired=excluded.last_fired',(reminder_id,user['id'],now))
                self.out({'ok':True});return
            if self.path == '/api/sharing':
                if not self.owner(user): return
                if data.get('enabled'): start_lan()
                else: stop_lan()
                self.out({'enabled':bool(lan_server),'address':lan_address(),'port':LAN_PORT}); return
            if self.path == '/api/member':
                name=str(data.get('name','')).strip(); role=data.get('role')
                if not name or role not in ('admin','editor','viewer'): raise ValueError('请填写成员名称和有效角色')
                if user['role'] not in ('owner','admin') or (user['role']=='admin' and role=='admin'):
                    self.out({'error':'无权签发该角色'},403); return
                token=secrets.token_urlsafe(32)
                with db() as c: c.execute('INSERT INTO members(name,role,token_hash) VALUES (?,?,?)',(name,role,token_hash(token)))
                self.out({'url':f'http://{lan_address()}:{LAN_PORT}/#invite={token}'}); return
            if self.path == '/api/member-disable':
                if not self.owner(user): return
                with db() as c: c.execute('UPDATE members SET enabled=0 WHERE id=?',(data.get('id'),))
                self.out({'ok':True}); return
            if self.path == '/api/lock':
                task_id=int(data['id']); now=time.time()
                with locks_guard:
                    lock=locks.get(task_id)
                    if data.get('release'):
                        if lock and lock['id']==user['id']: locks.pop(task_id,None)
                    elif lock and lock['expires']>now and lock['id']!=user['id']:
                        self.out({'error':'该任务正在由 '+lock['name']+' 编辑'},409); return
                    else: locks[task_id]={'id':user['id'],'name':user['name'],'expires':now+120}
                self.out({'ok':True}); return
            if self.path == '/api/ai':
                url=str(data.get('url','')).rstrip('/')
                if not url.startswith(('http://','https://')): raise ValueError('请填写模型 API 地址')
                request=Request(url+'/chat/completions',data=json.dumps({'model':data['model'],'messages':data['messages'],'temperature':0.2}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+data.get('key','')},method='POST')
                try:
                    context=ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()
                    with urlopen(request,timeout=60,context=context) as resp: result=json.load(resp)
                except HTTPError as e: raise ValueError('模型接口返回 HTTP '+str(e.code))
                self.out({'content':result['choices'][0]['message']['content']}); return
            if self.path == '/api/import':
                if not self.owner(user): return
                incoming=data.get('backup',{}); projects=incoming.get('projects'); tasks=incoming.get('tasks'); reminders=incoming.get('reminders',[]); events=incoming.get('events',[])
                if not isinstance(projects,list) or not isinstance(tasks,list) or not isinstance(reminders,list) or not isinstance(events,list): raise ValueError('备份格式无效')
                if len(projects)>1000 or len(tasks)>10000 or len(events)>100000 or len(reminders)>20000: raise ValueError('备份过大')
                if len({p.get('id') for p in projects})!=len(projects) or len({t.get('id') for t in tasks})!=len(tasks): raise ValueError('备份包含重复 ID')
                project_map={}; task_map={}; reminder_map={}; orphans={}
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    for p in projects:
                        name=str(p.get('name','')).strip()
                        if not name or p.get('id') is None: raise ValueError('项目内容无效')
                        cur=c.execute('INSERT INTO projects(name,description,created_at) VALUES (?,?,?)',(name,str(p.get('description','')),p.get('created_at') or datetime.utcnow().isoformat(' ')))
                        project_map[p['id']]=cur.lastrowid
                    fields=['title','status','priority','owner','start_date','due_date','actual_start','actual_end','notes','subtasks','tags','sort_order','created_at','updated_at']
                    for t in tasks:
                        if t.get('project_id') not in project_map or not str(t.get('title','')).strip() or t.get('id') is None: raise ValueError('任务内容无效')
                        vals=[t.get(k,{'subtasks':'[]','sort_order':0}.get(k,'')) for k in fields]
                        if isinstance(vals[9],list): vals[9]=json.dumps(vals[9],ensure_ascii=False)
                        if not isinstance(json.loads(vals[9]),list): raise ValueError('子任务格式无效')
                        cur=c.execute('INSERT INTO tasks(project_id,'+','.join(fields)+') VALUES ('+','.join('?' for _ in range(len(fields)+1))+')',[project_map[t['project_id']]]+vals);task_map[t['id']]=cur.lastrowid
                    for r in reminders:
                        if r.get('task_id') not in task_map: continue
                        cur=c.execute('INSERT INTO reminders(task_id,remind_at,mode,enabled,last_fired) VALUES (?,?,?,?,?)',(task_map[r['task_id']],r.get('remind_at',''),r.get('mode','once'),r.get('enabled',1),r.get('last_fired','')))
                        reminder_map[r.get('id')]=cur.lastrowid
                    for delivery in incoming.get('reminder_deliveries',[]):
                        if delivery.get('member_id')==0 and delivery.get('reminder_id') in reminder_map: c.execute('INSERT INTO reminder_deliveries(reminder_id,member_id,last_fired) VALUES (?,0,?)',(reminder_map[delivery['reminder_id']],delivery.get('last_fired','')))
                    for e in events:
                        old_id=e.get('task_id')
                        if old_id not in task_map:
                            if old_id not in orphans: orphans[old_id]=(c.execute('SELECT COALESCE(MIN(task_id),0)-1 AS n FROM events WHERE task_id<0').fetchone()['n']-len(orphans))
                            new_id=orphans[old_id]
                        else: new_id=task_map[old_id]
                        c.execute('INSERT INTO events(task_id,description,created_at,old_status,new_status,project_id) VALUES (?,?,?,?,?,?)',(new_id,str(e.get('description','')),e.get('created_at') or datetime.utcnow().isoformat(' '),e.get('old_status'),e.get('new_status'),project_map.get(e.get('project_id'))))
                self.out({'projects':len(project_map),'tasks':len(task_map)});return
            if self.path == '/api/reorder':
                task_id=int(data.get('id',0)); before=data.get('before_id'); status=data.get('status')
                if status not in ('待开始','进行中','已阻塞','已完成'): raise ValueError('状态无效')
                with locks_guard:
                    lock=locks.get(task_id)
                    if lock and lock['expires']>time.time() and lock['id']!=user['id']: raise ValueError('任务正由 '+lock['name']+' 编辑')
                with db() as c:
                    c.execute('BEGIN IMMEDIATE'); task=c.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
                    if not task: raise ValueError('任务不存在')
                    ids=[r['id'] for r in c.execute('SELECT id FROM tasks WHERE status=? AND id!=? ORDER BY sort_order,id',(status,task_id))]
                    if before is not None and int(before) not in ids: raise ValueError('目标位置已改变，请重试')
                    ids.insert(ids.index(int(before)) if before is not None else len(ids),task_id)
                    for i,item in enumerate(ids): c.execute('UPDATE tasks SET sort_order=? WHERE id=?',(i+1,item))
                    c.execute('UPDATE tasks SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,task_id))
                    if task['status']!=status: c.execute('INSERT INTO events(task_id,description,old_status,new_status,project_id) VALUES (?,?,?,?,?)',(task_id,'状态变更：'+task['title'],task['status'],status,task['project_id']))
                self.out({'ok':True});return
            with db() as c:
                if self.path == '/api/project':
                    name=str(data.get('name','')).strip()
                    if not name: raise ValueError('请输入项目名称')
                    cur=c.execute('INSERT INTO projects(name,description) VALUES (?,?)',(name,str(data.get('description','')))); self.out({'id':cur.lastrowid}); return
                if self.path == '/api/task':
                    c.execute('BEGIN IMMEDIATE')
                    fields=['project_id','title','status','priority','owner','start_date','due_date','actual_start','actual_end','notes','subtasks','tags']
                    title=str(data.get('title','')).strip()
                    if not title: raise ValueError('请输入任务名称')
                    if not c.execute('SELECT id FROM projects WHERE id=?',(data.get('project_id'),)).fetchone(): raise ValueError('项目不存在')
                    if data.get('id'):
                        with locks_guard:
                            lock=locks.get(int(data['id']))
                            if lock and lock['expires']>time.time() and lock['id']!=user['id']: raise ValueError('该任务正在由 '+lock['name']+' 编辑')
                        expected=data.get('_expected',{})
                        if expected:
                            current=c.execute('SELECT * FROM tasks WHERE id=?',(data['id'],)).fetchone()
                            if not current or any(k not in ('status','priority','start_date','due_date') or current[k]!=v for k,v in expected.items()): raise ValueError('任务已被修改，请重新生成建议')
                    vals=[data.get(k, {'status':'待开始','priority':'中','subtasks':[]}.get(k,'')) for k in fields]
                    vals[10]=json.dumps(vals[10],ensure_ascii=False)
                    if data.get('id'):
                        current=c.execute('SELECT * FROM tasks WHERE id=?',(data['id'],)).fetchone()
                        if not current: raise ValueError('任务不存在')
                        c.execute('UPDATE tasks SET '+','.join(k+'=?' for k in fields)+',updated_at=CURRENT_TIMESTAMP WHERE id=?',vals+[data['id']]); task_id=data['id']
                        c.execute('INSERT INTO events(task_id,description,old_status,new_status,project_id) VALUES (?,?,?,?,?)',(task_id,'更新任务：'+title,current['status'],data.get('status','待开始'),data['project_id']))
                    else:
                        cur=c.execute('INSERT INTO tasks('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',vals); task_id=cur.lastrowid
                        c.execute('UPDATE tasks SET sort_order=? WHERE id=?',(task_id,task_id))
                        c.execute('INSERT INTO events(task_id,description,old_status,new_status,project_id) VALUES (?,?,?,?,?)',(task_id,'创建任务：'+title,None,data.get('status','待开始'),data['project_id']))
                    self.out({'id':task_id}); return
                if self.path == '/api/reminder':
                    task_id=int(data['task_id']); remind_at=str(data.get('remind_at','')); mode=data.get('mode','once')
                    if not c.execute('SELECT id FROM tasks WHERE id=?',(task_id,)).fetchone(): raise ValueError('任务不存在')
                    if not remind_at or mode not in ('once','daily','advance'): raise ValueError('请输入提醒时间')
                    when=datetime.fromisoformat(remind_at)
                    if mode=='advance':
                        minutes=int(data.get('advance_minutes',30))
                        if not 1<=minutes<=10080: raise ValueError('提前时间需在 1 分钟至 7 天之间')
                        c.execute('INSERT INTO reminders(task_id,remind_at,mode) VALUES (?,?,?)',(task_id,(when-timedelta(minutes=minutes)).isoformat(timespec='minutes'),'once'))
                    c.execute('INSERT INTO reminders(task_id,remind_at,mode) VALUES (?,?,?)',(task_id,remind_at,'once' if mode=='advance' else mode)); self.out({'ok':True}); return
                if self.path == '/api/reminder-disable':
                    c.execute('UPDATE reminders SET enabled=0 WHERE id=?',(data['id'],)); self.out({'ok':True}); return
                if self.path == '/api/delete-task':
                    with locks_guard:
                        lock=locks.get(int(data['id']))
                        if lock and lock['expires']>time.time() and lock['id']!=user['id']: raise ValueError('该任务正在由 '+lock['name']+' 编辑')
                    row=c.execute('SELECT title FROM tasks WHERE id=?',(data['id'],)).fetchone()
                    if row:
                        original=c.execute('SELECT status,project_id FROM tasks WHERE id=?',(data['id'],)).fetchone()
                        c.execute('DELETE FROM tasks WHERE id=?',(data['id'],)); c.execute('INSERT INTO events(task_id,description,old_status,new_status,project_id) VALUES (?,?,?,?,?)',(data['id'],'删除任务：'+row['title'],original['status'],None,original['project_id']))
                    self.out({'ok':True}); return
            self.out({'error':'未找到接口'},404)
        except Exception as e: self.out({'error':str(e)},400)
    def log_message(self,*args): pass

if __name__ == '__main__':
    os.chdir(ROOT)
    server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(errors='backslashreplace')
    print(f'项目工作台：http://127.0.0.1:{PORT}\n数据文件：'+str(DB),flush=True)
    if os.environ.get('NO_BROWSER') != '1': threading.Timer(0.7,lambda:webbrowser.open(f'http://127.0.0.1:{PORT}')).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: stop_lan(); server.server_close()
