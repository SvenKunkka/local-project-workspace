import json, os, subprocess, tempfile, time, unittest, urllib.request, urllib.error

LOCAL=18865
LAN=18866
def request(port,path,data=None,token=None):
    headers={'Origin':f'http://127.0.0.1:{port}'}
    if data is not None: headers['Content-Type']='application/json'
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request(f'http://127.0.0.1:{port}/api/{path}',data=None if data is None else json.dumps(data).encode(),headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=3) as r: return r.status,json.load(r)
    except urllib.error.HTTPError as e:
        with e: return e.code,json.load(e)

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();env=dict(os.environ,PROJECT_MANAGER_DATA=cls.temp.name,PROJECT_MANAGER_PORT=str(LOCAL),PROJECT_MANAGER_LAN_PORT=str(LAN),NO_BROWSER='1')
        cls.proc=subprocess.Popen([os.environ.get('TEST_SERVER','python3'),*([os.path.join(os.path.dirname(__file__),'server.py')] if not os.environ.get('TEST_SERVER') else [])],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        for _ in range(200):
            try:
                if request(LOCAL,'state')[0]==200: break
            except OSError: time.sleep(.1)
        else:
            cls.proc.terminate(); cls.proc.wait(timeout=5)
            raise RuntimeError('server did not start: '+cls.proc.stderr.read().decode())
    @classmethod
    def tearDownClass(cls): cls.proc.terminate();cls.proc.wait(timeout=5);cls.proc.stderr.close();cls.temp.cleanup()
    def test_workflow(self):
        status,p=request(LOCAL,'project',{'name':'测试项目'});self.assertEqual(status,200)
        status,t=request(LOCAL,'task',{'project_id':p['id'],'title':'任务','status':'进行中','start_date':'2026-10-20','due_date':'2026-10-30','subtasks':[{'title':'核验','done':True}]});self.assertEqual(status,200)
        status,_=request(LOCAL,'reminder',{'task_id':t['id'],'remind_at':'2020-01-01T10:00','mode':'once'});self.assertEqual(status,200)
        due=request(LOCAL,'reminders-due')[1];self.assertEqual(len(due),1);self.assertEqual(request(LOCAL,'reminder-ack',{'id':due[0]['id']})[0],200);self.assertEqual(len(request(LOCAL,'reminders-due')[1]),0)
        self.assertEqual(request(LOCAL,'sharing',{'enabled':True})[0],200)
        self.assertEqual(request(LAN,'state')[0],401)
        _,v=request(LOCAL,'member',{'name':'只读','role':'viewer'});viewer=v['url'].split('#invite=')[1]
        self.assertEqual(request(LAN,'state',token=viewer)[0],200)
        self.assertEqual(request(LAN,'task',{'project_id':p['id'],'title':'不应写入'},viewer)[0],403)
        _,e=request(LOCAL,'member',{'name':'编辑','role':'editor'});editor=e['url'].split('#invite=')[1]
        _,member_task=request(LOCAL,'task',{'project_id':p['id'],'title':'成员提醒','owner':'编辑','subtasks':[]})
        request(LOCAL,'reminder',{'task_id':member_task['id'],'remind_at':'2020-01-01T10:00','mode':'once'})
        member_due=request(LAN,'reminders-due',token=editor)[1];self.assertEqual([r['title'] for r in member_due],['成员提醒'])
        self.assertEqual(request(LAN,'reminder-ack',{'id':member_due[0]['id']},editor)[0],200)
        self.assertEqual(request(LAN,'reminders-due',token=editor)[1],[])
        self.assertEqual(request(LAN,'lock',{'id':t['id']},editor)[0],200)
        task=next(item for item in request(LOCAL,'state')[1]['tasks'] if item['id']==t['id']);task['subtasks']=json.loads(task['subtasks']);task['status']='已完成'
        self.assertEqual(request(LOCAL,'task',task)[0],400)
        self.assertEqual(request(LAN,'lock',{'id':t['id'],'release':True},editor)[0],200)
        self.assertEqual(request(LOCAL,'task',dict(task,_expected={'status':'不存在'}))[0],400)
        self.assertEqual(request(LOCAL,'task',dict(task,_expected={'status':'进行中'}))[0],200)
        self.assertEqual(next(item for item in request(LOCAL,'state')[1]['tasks'] if item['id']==t['id'])['status'],'已完成')
        self.assertEqual(request(LOCAL,'reorder',{'id':t['id'],'status':'进行中','before_id':None})[0],200)
        backup=request(LOCAL,'state')[1];self.assertTrue(any(x.get('new_status')=='进行中' for x in backup['events']))
        self.assertEqual(request(LOCAL,'import',{'backup':backup})[0],200)
        self.assertEqual(len(request(LOCAL,'state')[1]['tasks']),4)
        member=next(m for m in request(LOCAL,'state')[1]['members'] if m['name']=='只读')
        self.assertEqual(request(LOCAL,'member-disable',{'id':member['id']})[0],200)
        self.assertEqual(request(LAN,'state',token=viewer)[0],401)
        self.assertEqual(request(LOCAL,'sharing',{'enabled':False})[0],200)

if __name__=='__main__': unittest.main()
