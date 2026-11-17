import unittest,tempfile,uuid,json,base64,io
from pathlib import Path
from unittest.mock import patch
import server
from assistant_service import Assistant
from assistant_files import extract
from assistant_knowledge import Knowledge

class Round2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=server.fleet_server.Store(Path(self.tmp.name)/'fleet.db');self.ai=Assistant(self.store)
    def tearDown(self):self.tmp.cleanup()
    def b(self,**kw):return {'revision':self.store.read()['revision'],'request_id':str(uuid.uuid4()),'session_id':'round2-test',**kw}
    def test_knowledge_index(self):
        k=self.ai.knowledge;self.assertGreater(len(k.chunks),30);rows=k.search('导师 优先级 卸载 priority_wait');self.assertTrue(any('edge.py' in r['source'] or 'mentor/' in r['source'] for r in rows));self.assertTrue(all(r['id'].startswith('K-') for r in rows))
    def test_empty_search(self):self.assertEqual(self.ai.retrieve('zzzxxyyqqq'),[])
    def test_session_invalid(self):
        with self.assertRaises(ValueError):self.ai.conversation('../../key')
    def test_manual_is_candidate_only(self):
        s=self.store.read();s['tasks']=s['tasks'][:1];s['vehicles']=s['vehicles'][:6];self.store.save(s)
        result=self.ai.mutate(self.b(),[{'tool':'manual','data':{'task':'T001','vehicle':'V04'}}])
        self.assertNotIn('error',result['results'][0]);s=self.store.read();self.assertIsNotNone(s['draft']);self.assertIsNone(s['plan']);self.assertIsNone(s['tasks'][0].get('locked_to'))
    def test_excel(self):
        import openpyxl
        w=openpyxl.Workbook();w.active.append(['id','name']);w.active.append(['A','收运']);b=io.BytesIO();w.save(b)
        out=extract({'filename':'任务.xlsx','base64':base64.b64encode(b.getvalue()).decode()});self.assertEqual(json.loads(out['content']),[{'id':'A','name':'收运'}])
    def test_formula_rejected(self):
        import openpyxl
        w=openpyxl.Workbook();w.active.append(['id','demand']);w.active.append(['A','=1+1']);b=io.BytesIO();w.save(b)
        with self.assertRaises(ValueError):extract({'filename':'a.xlsx','base64':base64.b64encode(b.getvalue()).decode()})
    def test_empty_pdf(self):
        from pypdf import PdfWriter
        w=PdfWriter();w.add_blank_page(100,100);b=io.BytesIO();w.write(b)
        with self.assertRaisesRegex(ValueError,'没有可提取文字'):extract({'filename':'blank.pdf','base64':base64.b64encode(b.getvalue()).decode()})
    def test_bad_file(self):
        with self.assertRaises(ValueError):extract({'filename':'a.xlsx','base64':'notbase64!'})
    def test_multiturn_and_retry(self):
        seen=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps({'choices':[{'message':{'content':json.dumps({'answer':'请补充车辆编号','actions':[],'citations':['fake-id']})}}]}).encode()
        def capture(req,**kw):seen.append(json.loads(req.data));return Response()
        with patch('assistant_service.config',return_value={'base_url':'https://example.com','model':'mock','api_key':'test'}),patch('urllib.request.urlopen',side_effect=capture):
            b=self.b(message='登记车辆故障',execute=True);out=self.ai.call('chat',b);self.assertEqual(out['citations'],[])
            self.assertTrue(self.ai.call('chat',b)['duplicate']);self.assertEqual(len(seen),1)
            self.ai.call('chat',self.b(message='车辆V01',execute=False));payload=json.loads(seen[-1]['messages'][1]['content']);self.assertEqual(payload['history'][0]['user']['message'],'登记车辆故障')
        self.assertEqual(len(Assistant(self.store).conversation('round2-test')),2)
        self.assertEqual(self.ai.conversation('different-session'),[])

if __name__=='__main__':unittest.main()
