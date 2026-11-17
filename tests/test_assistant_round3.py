import copy,json,tempfile,unittest,uuid,urllib.error,importlib.util
from pathlib import Path
from unittest.mock import patch
import server
from assistant_service import Assistant
from assistant_imports import normalize
from backend.model import Evaluator,upgrade,assign_crews
from backend.optimizer import insertions

class Round3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=server.fleet_server.Store(Path(self.tmp.name)/'fleet.db');self.ai=Assistant(self.store)
        self.row={'任务编号':'R3-1','任务名称':'市场清运','作业类型':'垃圾收运','作业地点':'东门','开始时间':'08:00','完成时限':'10:30','作业时长':8,'垃圾量':1,'用水量':0,'优先级':3}
        self.opts={'locations':{'东门':'N1-4'}}
    def tearDown(self):self.tmp.cleanup()
    def b(self):return {'revision':self.store.read()['revision'],'request_id':str(uuid.uuid4())}
    def import_(self,rows=None,opts=None):return self.ai.mutate(self.b(),[{'tool':'import_tasks','tasks':rows or [self.row],'options':opts or self.opts}])['results'][0]
    def test_chinese_time_location(self):
        out=self.import_();self.assertEqual(out['imported'],['R3-1']);t=self.store.read()['tasks'][-1];self.assertEqual(t['earliest'],480);self.assertEqual(t['end'],'N1-4')
    def test_custom_header(self):
        row={**self.row,'企业字段A':self.row['任务名称']};del row['任务名称']
        o=self.import_([row],{**self.opts,'mapping':{'name':'企业字段A'}});self.assertEqual(o['imported'],['R3-1'])
    def test_plate_lock(self):
        s=self.store.read();s['vehicles'][0]['plate']='云A12345';self.store.save(s)
        self.import_([{**self.row,'车牌号':'云A12345'}]);self.assertEqual(self.store.read()['tasks'][-1]['locked_to'],'V01')
    def test_duplicate_upload(self):
        x=self.import_();n=len(self.store.read()['tasks']);y=self.import_();self.assertTrue(y['duplicate']);self.assertEqual(x['batch_id'],y['batch_id']);self.assertEqual(n,len(self.store.read()['tasks']))
    def test_retry_failed_only(self):
        bad={**self.row,'任务编号':'R3-2'};del bad['垃圾量']
        x=self.import_([self.row,bad]);self.assertEqual(len(x['errors']),1)
        y=self.ai.mutate(self.b(),[{'tool':'retry_import','batch_id':x['batch_id'],'options':{'defaults':{'demand':2}}}])['results'][0]
        self.assertEqual(y['imported'],['R3-2']);self.assertEqual(sum(t['id']=='R3-1' for t in self.store.read()['tasks']),1)
    def test_withdraw_archives(self):
        x=self.import_();y=self.ai.mutate(self.b(),[{'tool':'withdraw','batch_id':x['batch_id']}])['results'][0]
        self.assertEqual(y['removed'],['R3-1']);s=self.store.read();self.assertFalse(any(t['id']=='R3-1' for t in s['tasks']));self.assertEqual(s['import_batches'][0]['archived'][0]['id'],'R3-1')
    def test_withdraw_protects_started_and_confirmed(self):
        x=self.import_([self.row,{**self.row,'任务编号':'R3-2'}]);s=self.store.read();s['tasks'][-1]['status']='running';s['plan']={'routes':{'V01':[{'task':'R3-1','depart':900}]}};self.store.save(s)
        y=self.ai.mutate(self.b(),[{'tool':'withdraw','batch_id':x['batch_id']}])['results'][0];self.assertEqual(y['removed'],[]);self.assertEqual(len(y['blocked']),2)
    def test_stale_batch_operation(self):
        b=self.b();x=self.import_()
        with self.assertRaises(ValueError):self.ai.mutate(b,[{'tool':'withdraw','batch_id':x['batch_id']}])
    def test_geo_requires_calibration(self):
        row={**self.row,'作业地点':'N1-4','经度':102.7,'纬度':25,'坐标系':'WGS84'}
        x=self.import_([row]);self.assertEqual(x['imported'],[]);self.assertIn('已配准',x['errors'][0]['error'])
    def test_geo_unique_match(self):
        s=self.store.read();n=next(n for n in s['nodes'] if n['id']=='N1-4');n.update(longitude=102.7,latitude=25,coordinate_system='WGS84');self.store.save(s)
        row={**self.row,'经度':102.7,'纬度':25,'坐标系':'WGS84'};del row['作业地点'];x=self.import_([row]);self.assertEqual(x['imported'],['R3-1'])
    def test_group_missing(self):
        row={**self.row};del row['作业时长'];del row['垃圾量'];_,errors,_=normalize(self.store.read(),[row],self.opts)
        self.assertIn('service',errors[0]['missing']);self.assertIn('demand',errors[0]['missing'])
    def test_duplicate_csv_headers(self):
        with self.assertRaisesRegex(ValueError,'重复'):self.ai.parse_file({'filename':'bad.csv','content':'id,id\na,b'})
    def test_failed_rows_not_reported_as_full_success(self):
        bad={**self.row};del bad['垃圾量'];out=self.ai.mutate(self.b(),[{'tool':'import_tasks','tasks':[bad],'options':self.opts}])
        self.assertEqual(out['feedback']['completed_steps'],0);self.assertEqual(out['feedback']['failed_items'],1)
    def test_network_failure_no_mutation(self):
        before=self.store.read();b={**self.b(),'message':'登记V01故障','execute':True}
        with patch('assistant_service.config',return_value={'base_url':'https://example.com','model':'mock','api_key':'test'}),patch('urllib.request.urlopen',side_effect=urllib.error.URLError('offline')):
            with self.assertRaises(ValueError):self.ai.model(b)
        self.assertEqual(before,self.store.read())
    def test_record_rejection_and_feasible(self):
        s=self.store.read();upgrade(s);assign_crews(s);s['vehicles'][0]['enabled']=False;ev=Evaluator(s);a={v:[] for v in ev.vs};insertions(ev,a,'T001')
        self.assertIn('车型不兼容',ev.decision_evidence[('T001','V02')]['rejections']);self.assertGreater(ev.decision_evidence[('T001','V04')]['feasible'],0)
        self.assertTrue(ev.decision_evidence[('T001','V01')]['rejections'])
    def test_capacity_reason(self):
        s=self.store.read();upgrade(s);s['tasks'][0]['demand']=999;ev=Evaluator(s);self.assertIsNone(ev.route('V01',['T001']));self.assertIn('单项需求',ev.last_failure)
    def test_route_behavior_unchanged(self):
        p=Path(__file__).resolve().parents[1]/'backups/round2/model.py';spec=importlib.util.spec_from_file_location('backend.model_previous',p);previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
        s=self.store.read();upgrade(s);assign_crews(s);new,old=Evaluator(copy.deepcopy(s)),previous.Evaluator(copy.deepcopy(s))
        for v,ids in [('V01',['T001']),('V02',['T002']),('V03',['T003']),('V01',['T002'])]:self.assertEqual(new.route(v,ids),old.route(v,ids))

if __name__=='__main__':unittest.main()
