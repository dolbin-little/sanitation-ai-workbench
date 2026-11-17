"""Loopback-only sanitation dispatch + low-speed driving research workbench."""
import argparse,importlib.util,json,math,mimetypes,sqlite3,sys,threading
from pathlib import Path
from contextlib import closing
from urllib.parse import urlparse
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'legacy'))
spec=importlib.util.spec_from_file_location('fleet_server',ROOT/'legacy/server.py')
fleet_server=importlib.util.module_from_spec(spec);spec.loader.exec_module(fleet_server)
from drive.session import Session,POLICIES
from drive.world import SCENARIOS,clip

class DriveStore:
    def __init__(self,db,fleet):
        self.lock=threading.RLock();self.db=str(db);self.fleet=fleet;self.revision=0;self.session=Session();self.saved_frame=-1
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('CREATE TABLE IF NOT EXISTS drive_runs (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)');c.commit()
    def missions(self):
        with self.fleet.lock:s=self.fleet.read()
        assignment={}
        for v,route in (s.get('plan') or {}).get('routes',{}).items():
            for a in route:
                if a.get('task'):assignment[a['task']]=v
        rows=[]
        for t in s['tasks']:
            assigned=assignment.get(t['id'],t.get('assigned_vehicle',t.get('completed_by')))
            compatible=sorted([v for v in s['vehicles'] if v.get('enabled') and v['kind']==t['kind']],key=lambda v:(len((s.get('plan') or {}).get('routes',{}).get(v['id'],[])),v['id']))
            rows.append({'id':t['id'],'name':t['name'],'kind':t['kind'],'status':t.get('status'),'vehicle':assigned or (compatible[0]['id'] if compatible else None),'assignment_status':'confirmed_snapshot' if assigned else 'simulation_recommendation','source':'fleet_snapshot','fleet_revision':s['revision']})
        return rows
    def state(self):return {**self.session.snapshot(),'revision':self.revision}
    def record(self):
        s=self.session
        if s.done and self.saved_frame!=s.frame:
            payload={'mission':s.mission,'metrics':s.metrics(),'trace':s.trace,'logs':s.logs,'scope':'仅模拟作业回执，不扣减车队库存、不标记实车工单完成'}
            with closing(sqlite3.connect(self.db)) as c:
                c.execute('INSERT INTO drive_runs(payload) VALUES (?)',(json.dumps(payload,ensure_ascii=False,allow_nan=False),));c.commit()
            self.saved_frame=s.frame
    def runs(self):
        with closing(sqlite3.connect(self.db)) as c:rows=c.execute('SELECT id,payload FROM drive_runs ORDER BY id DESC LIMIT 100').fetchall()
        return [{'id':i,**json.loads(p)} for i,p in rows]
    def action(self,name,b):
        with self.lock:
            if type(b.get('revision')) is not int or b['revision']!=self.revision:raise ValueError('页面状态已变化，请刷新后操作')
            if name=='reset':
                seed=b.get('seed',1000)
                if type(seed) is not int or not 0<=seed<=999999:raise ValueError('种子须为0—999999整数')
                mission=None
                if b.get('mission_id'):
                    mission=next((m for m in self.missions() if m['id']==b['mission_id']),None)
                    if not mission:raise ValueError('工单已失效，请重新读取任务中心')
                    mission={**mission,'scope':'真实字段来自本地合成车队快照；100×70米服务道路为独立抽象，不复现原路网'}
                self.session=Session(b.get('scenario','pedestrian'),seed,b.get('policy','shielded'),mission);self.saved_frame=-1
            elif name=='step':self.session.step(b.get('count',1));self.record()
            elif name=='emergency':
                if type(b.get('enabled')) is not bool:raise ValueError('enabled须为布尔值')
                self.session.emergency=b['enabled'];self.session.log('调度员'+('按下仿真急停' if b['enabled'] else '解除仿真急停'))
            elif name=='manual':
                if type(b.get('enabled')) is not bool:raise ValueError('enabled须为布尔值')
                steer=b.get('steer',0);accel=b.get('accel',-3)
                if any(type(v) not in (int,float) or not math.isfinite(v) for v in (steer,accel)):raise ValueError('控制量须为有限数值')
                self.session.manual=b['enabled'];self.session.manual_command={'steer':clip(steer,-.52,.52),'accel':clip(accel,-3,1.8)}
                self.session.log('人工模拟控制'+('接管；安全监控仍按所选策略工作' if b['enabled'] else '退出'))
            elif name=='adapter':self.session.import_adapter(b.get('record'))
            else:raise ValueError('未知驾驶接口')
            self.revision+=1;return self.state()

def handler(fleet,drive):
    class Handler(fleet_server.handler(fleet)):
        def do_GET(self):
            path=urlparse(self.path).path
            if path=='/api/drive/state':
                with drive.lock:return self.send(drive.state())
            if path=='/api/drive/config':return self.send({'scenarios':SCENARIOS,'policies':POLICIES,'mission_scope':'环卫工单字段与独立服务道路驾驶仿真关联'})
            if path=='/api/drive/missions':return self.send(drive.missions())
            if path=='/api/drive/runs':return self.send(drive.runs())
            if path=='/api/drive/evaluation':
                p=ROOT/'evidence/summary.json';return self.send(json.loads(p.read_text('utf-8')) if p.exists() else {'status':'尚未运行，请执行 scripts/evaluate.py'})
            if path=='/api/drive/sources':
                out=[]
                for folder in ['driving','mentor']:
                    p=ROOT/f'references/{folder}/source_registry.json'
                    if p.exists():out.append({'group':folder,'registry':json.loads(p.read_text('utf-8-sig'))})
                return self.send(out)
            if path=='/api/drive/export':
                with drive.lock:return self.send({'state':drive.state(),'runs':drive.runs()})
            if path=='/dispatch':
                return self.send((ROOT/'legacy/web/index.html').read_bytes(),content_type='text/html; charset=utf-8')
            if path=='/':return self.send((ROOT/'web/index.html').read_bytes(),content_type='text/html; charset=utf-8')
            if path.startswith('/assets/'):
                relative=path.removeprefix('/assets/');p=(ROOT/'web/assets'/relative).resolve()
                if not p.is_relative_to((ROOT/'web/assets').resolve()) or not p.is_file():return self.send({'error':'文件不存在'},404)
                return self.send(p.read_bytes(),content_type=(mimetypes.guess_type(str(p))[0] or 'application/octet-stream')+'; charset=utf-8')
            return super().do_GET()
        def do_POST(self):
            if not self.path.startswith('/api/drive/'):return super().do_POST()
            if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):return self.send({'error':'不接受跨站请求'},403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send({'error':'须使用application/json'},415)
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=100000:return self.send({'error':'请求须在100KB以内'},413)
                b=json.loads(self.rfile.read(n),parse_constant=lambda _:(_ for _ in ()).throw(ValueError('不接受非有限数值')))
                if not isinstance(b,dict):raise ValueError('请求须为对象')
                return self.send(drive.action(self.path.rsplit('/',1)[-1],b))
            except (ValueError,KeyError,TypeError) as e:return self.send({'error':str(e)},400)
    return Handler

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8780);a=p.parse_args()
    fleet=fleet_server.Store(ROOT/'data/fleet.sqlite3');drive=DriveStore(ROOT/'data/driving.sqlite3',fleet)
    server=ThreadingHTTPServer(('127.0.0.1',a.port),handler(fleet,drive))
    print(f'环卫智枢 · 低速作业驾驶协同 http://127.0.0.1:{a.port}/',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
