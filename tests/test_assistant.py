import unittest,tempfile,sys,json,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from assistant_service import Assistant,snapshot

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=server.fleet_server.Store(Path(self.tmp.name)/'state.db');self.ai=Assistant(self.store)
        self.row=dict(id='TEST-AI',name='测试',kind='collection',start='N1-4',end='N1-4',earliest=600,deadline=900,service=8,demand=1,water=0,priority=3)
    def tearDown(self):self.tmp.cleanup()
    def request(self,**kw):return dict(revision=self.store.read()['revision'],request_id=str(uuid.uuid4()),**kw)
    def test_import_dedup_and_preserve(self):
        before=self.store.read();b=self.request();actions=[dict(tool='import_tasks',tasks=[self.row])]
        out=self.ai.mutate(b,actions);self.assertEqual(out['results'][0]['imported'],['TEST-AI'])
        self.assertTrue(self.ai.mutate(b,actions)['duplicate'])
        after=self.store.read();self.assertEqual(len(after['tasks']),len(before['tasks'])+1);self.assertEqual(after['tasks'][:-1],before['tasks']);self.assertEqual(after['plan'],before['plan'])
    def test_partial_validation(self):
        out=self.ai.mutate(self.request(),[dict(tool='import_tasks',tasks=[self.row,{**self.row,'id':'BAD','start':'不存在'}])])
        self.assertEqual(len(out['results'][0]['errors']),1);self.assertEqual(out['results'][0]['imported'],['TEST-AI'])
    def test_no_accept_tool(self):
        with self.assertRaises(ValueError):self.ai.mutate(self.request(),[dict(tool='accept')])
    def test_revision(self):
        b=self.request();b['revision']=-1
        with self.assertRaises(ValueError):self.ai.mutate(b,[dict(tool='import_tasks',tasks=[self.row])])
    def test_missing_event_target(self):
        before=self.store.read();out=self.ai.mutate(self.request(),[dict(tool='event',data={'kind':'overflow'})]);self.assertIn('error',out['results'][0]);self.assertEqual(len(self.store.read()['tasks']),len(before['tasks']))
    def test_fault(self):
        out=self.ai.mutate(self.request(),[dict(tool='event',data={'kind':'failure','vehicle':'V01'})]);self.assertNotIn('error',out['results'][0]);self.assertFalse(self.store.read()['vehicles'][0]['enabled']);self.assertIsNone(self.store.read()['plan'])
    def test_no_key(self):
        with patch('assistant_service.config',return_value=dict(base_url='',model='',api_key='')):
            with self.assertRaises(ValueError):self.ai.model(self.request(message='查询'))
    def test_preview_no_mutation(self):
        before=self.store.read();out=self.ai.call('preview',{'filename':'a.json','content':json.dumps([self.row])});self.assertEqual(len(out['rows']),1);self.assertEqual(before,self.store.read())
    def test_nonfinite(self):
        rows,errors=self.ai.prepare_rows(self.store.read(),[{**self.row,'demand':float('nan')}]);self.assertEqual(rows,[]);self.assertEqual(len(errors),1)
    def test_model_mock_readonly_and_execute(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,*a):return json.dumps({'choices':[{'message':{'content':json.dumps({'answer':'将登记故障','actions':[{'tool':'event','data':{'kind':'failure','vehicle':'V01'}}]})}}]}).encode()
        with patch('assistant_service.config',return_value=dict(base_url='https://example.com/v1',model='mock',api_key='test')),patch('urllib.request.urlopen',return_value=Response()):
            out=self.ai.model(self.request(message='查询',execute=False));self.assertNotIn('results',out);self.assertTrue(self.store.read()['vehicles'][0]['enabled'])
            with self.assertRaises(ValueError):self.ai.model(self.request(message='如果V01故障会怎样',execute=True))
            out=self.ai.model(self.request(message='登记V01故障',execute=True));self.assertIn('results',out);self.assertFalse(self.store.read()['vehicles'][0]['enabled'])
    def test_diff(self):
        s=self.store.read();a={'task':'T1','finish':500,'start':'N1-4','end':'N1-4'};s['plan']={'routes':{'V01':[a]}};s['draft']={'routes':{'V02':[{**a,'finish':510}]}}
        diff=snapshot(s)['changes'][0];self.assertEqual(diff['before']['vehicle'],'V01');self.assertEqual(diff['after']['finish'],510)

if __name__=='__main__':unittest.main()
