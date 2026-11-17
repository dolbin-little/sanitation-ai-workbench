import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from backend.service import Store
from server import handler


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),handler(Store(Path(cls.tmp.name)/'api.db')))
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join();cls.tmp.cleanup()

    def get(self,path):
        with urllib.request.urlopen(self.base+path) as r:return r.read()

    def post(self,name,body,origin=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        req=urllib.request.Request(self.base+'/api/'+name,data=json.dumps(body).encode(),headers=headers)
        with urllib.request.urlopen(req) as r:return json.load(r)

    def test_end_to_end(self):
        self.assertIn(b'app.js',self.get('/'))
        self.assertTrue(json.loads(self.get('/api/health'))['ok'])
        s=self.post('reset',{})
        s=self.post('plan',{})
        # Rolling planning may defer future tasks; every task must still be accounted for.
        draft=s['draft']
        assigned=[a['task'] for seq in draft['routes'].values() for a in seq if a.get('task')]
        deferred=set(draft.get('deferred',[]))
        unassigned={u['id'] for u in draft['unassigned']}
        self.assertGreater(len(assigned),0)
        self.assertEqual(len(assigned),len(set(assigned)))
        self.assertFalse(set(assigned)&(deferred|unassigned))
        self.assertFalse(deferred&unassigned)
        self.assertEqual(set(assigned)|deferred|unassigned,{t['id'] for t in s['tasks']})
        self.assertEqual(draft['metrics']['scheduled'],len(assigned))
        s=self.post('accept',{})
        s=self.post('advance',{'minutes':20})
        self.assertGreater(sum(t['status']=='done' for t in s['tasks']),0)
        s=self.post('event',{'kind':'overflow'})
        self.assertEqual(len(s['tasks']),121)
        self.post('plan',{});self.post('accept',{})
        s=self.post('advance',{'minutes':10})
        self.assertEqual(s['now'],450)
        template=json.loads(self.get('/api/template'))
        self.assertEqual(len(self.post('import',{'scenario':template})['tasks']),120)
        self.assertIn('vehicles',json.loads(self.get('/api/export')))

    def test_cross_origin_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post('plan',{},'https://untrusted.example')
        self.assertEqual(ctx.exception.code,403)

    def test_invalid_action_does_not_modify_state(self):
        before=self.get('/api/state')
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post('event',{'kind':'failure','vehicle':'missing'})
        self.assertEqual(ctx.exception.code,400)
        self.assertEqual(before,self.get('/api/state'))

    def test_path_traversal_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get('/../server.py')
        self.assertEqual(ctx.exception.code,404)

