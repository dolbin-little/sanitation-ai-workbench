"""Reproducible API workflow timing; not a human usability study."""
import copy,json,sys,tempfile,time,uuid,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import server
from assistant_service import Assistant
from backend.service import dispatch

def fresh(folder):
    store=server.fleet_server.Store(Path(folder)/(uuid.uuid4().hex+'.sqlite3'));s=store.read();s['tasks']=s['tasks'][:3];s['vehicles']=s['vehicles'][:6];s['settings']={'iterations':8,'budget':3};store.save(s);return store

def main():
    trials=[]
    with tempfile.TemporaryDirectory() as folder:
        for i in range(3):
            store=fresh(folder);started=time.perf_counter();store.action('event',{'kind':'failure','vehicle':'V01'});store.action('plan',{'strategy':'halns'});elapsed=time.perf_counter()-started;s=store.read()
            trials.append({'trial':i+1,'flow':'manual_equivalent','seconds':round(elapsed,3),'business_submissions':2,'success':not s['vehicles'][0]['enabled'] and s['draft'] is not None and s['plan'] is None})
            store=fresh(folder);ai=Assistant(store);started=time.perf_counter()
            try:
                out=ai.call('chat',{'message':'登记V01车辆故障，并为剩余任务生成候选调度方案。不要下发。','execute':True,'session_id':'benchmark-'+uuid.uuid4().hex,'request_id':str(uuid.uuid4()),'revision':store.read()['revision']})
                s=store.read();success=not s['vehicles'][0]['enabled'] and s['draft'] is not None and s['plan'] is None
                trials.append({'trial':i+1,'flow':'assistant','seconds':round(time.perf_counter()-started,3),'business_submissions':1,'tool_steps':len(out.get('results',[])),'success':success,'answer':out['answer']})
            except Exception as e:trials.append({'trial':i+1,'flow':'assistant','seconds':round(time.perf_counter()-started,3),'success':False,'error':str(e)})
        store=fresh(folder);ai=Assistant(store)
        row={'任务编号':'ENTERPRISE-1','任务名称':'市场收运','车型':'压缩收运车','作业地点':'N1-4','开始时间':'08:00','完成时限':'09:30','作业时长':8,'用水量':0,'优先级':3}
        session='missing-'+uuid.uuid4().hex
        def ask(q,**extra):return ai.call('chat',{'message':q,'execute':True,'session_id':session,'request_id':str(uuid.uuid4()),'revision':store.read()['revision'],**extra})
        a=ask('导入附件任务。缺少的业务参数请先问我，不要猜测。',attachment={'filename':'enterprise.json','content':json.dumps([row],ensure_ascii=False)})
        first_no_write=not any(t['id']=='ENTERPRISE-1' for t in store.read()['tasks'])
        b=ask('补充：垃圾量1吨。请继续导入该任务，不要下发。')
        cases=[{'case':'企业清单缺项→多轮补充→导入','passed':first_no_write and any(t['id']=='ENTERPRISE-1' for t in store.read()['tasks']),'first_answer':a['answer'],'second_answer':b['answer'],'results':b.get('results',[])}]
        batch=store.read().get('import_batches',[])
        if batch:
            c=ask('撤回刚导入的批次 '+batch[-1]['id']+'，未执行任务应归档保留。')
            cases.append({'case':'自然语言撤回批次','passed':not any(t['id']=='ENTERPRISE-1' for t in store.read()['tasks']) and bool(store.read()['import_batches'][-1]['archived']),'answer':c['answer'],'results':c.get('results',[])})
    summary={}
    for flow in ('manual_equivalent','assistant'):
        rows=[r for r in trials if r['flow']==flow];summary[flow]={'success':sum(r['success'] for r in rows),'n':len(rows),'median_seconds':round(statistics.median(r['seconds'] for r in rows),3)}
    report={'protocol':'同一合成场景3任务6车，8迭代3秒预算；每组3次，从新数据库开始。人工路径为按钮对应业务接口的程序重放，未测真人点击/阅读时间；助手含真实API等待。不以此声称真人效率提升。','trials':trials,'summary':summary,'cases':cases}
    (ROOT/'evidence/assistant_round3_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False));print('cases',[(c['case'],c['passed']) for c in cases])
if __name__=='__main__':main()
