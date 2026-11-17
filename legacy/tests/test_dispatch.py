import copy
import json
import tempfile
import unittest
from pathlib import Path

from backend.engine import solve, Roads, origins
from backend.scenario import demo, fresh, validate
from backend.service import dispatch, Store, advance


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.s = fresh(demo())

    def assert_feasible(self, s, p):
        ids = []
        tasks = {t['id']:t for t in s['tasks']}
        for v in s['vehicles']:
            seq = ([v['active']] if v['active'] else []) + p['routes'].get(v['id'], [])
            for i, a in enumerate(seq):
                self.assertLessEqual(a['load_after'], v['capacity']+1e-6)
                self.assertGreaterEqual(a['water_after'], 0)
                self.assertLessEqual(a['water_after'], v['water_capacity']+1e-6)
                self.assertLessEqual(a['finish'], v['shift_end']+1e-6)
                self.assertGreaterEqual(a['finish'], a['begin'])
                if i:
                    self.assertEqual(a['source'],seq[i-1]['end'])
                    self.assertGreaterEqual(a['depart'],seq[i-1]['finish']-1e-6)
                if a.get('task'):
                    t=tasks[a['task']]; ids.append(t['id'])
                    self.assertEqual(t['kind'],v['kind'])
                    self.assertGreaterEqual(a['begin'],t['earliest'])
                    if t['locked_to']:
                        self.assertEqual(t['locked_to'],v['id'])
                if a['kind']=='facility':
                    f=next(f for f in s['facilities'] if f['name']==a['label'])
                    self.assertGreaterEqual(a['begin'],f['open'])
                    self.assertLessEqual(a['finish'],f['close'])
            if seq:
                self.assertEqual(seq[-1]['end'],v['home'])
        self.assertEqual(len(ids),len(set(ids)))
        unfinished={t['id'] for t in s['tasks'] if t['status']!='done'}
        self.assertEqual(set(ids)|{u['id'] for u in p['unassigned']},unfinished)

    def test_all_baselines_hard_constraints(self):
        for strategy in ('fixed','nearest','adaptive'):
            p=solve(self.s,strategy)
            self.assert_feasible(self.s,p)
        self.assertEqual(p['metrics']['scheduled'],120)

    def test_capacity_replenishment(self):
        for v in self.s['vehicles']:
            v['capacity']=3
        p=solve(self.s)
        self.assert_feasible(self.s,p)
        self.assertTrue(any(a['kind']=='facility' for seq in p['routes'].values() for a in seq))

    def test_oversize_task_unassigned(self):
        self.s['tasks'][0]['demand']=200
        p=solve(self.s)
        self.assertIn(self.s['tasks'][0]['id'],[u['id'] for u in p['unassigned']])

    def test_shift_and_facilities(self):
        for v in self.s['vehicles']:
            v['shift_end']=440
        p=solve(self.s)
        self.assert_feasible(self.s,p)
        self.assertGreater(p['metrics']['unassigned'],0)

    def test_frozen_and_stale(self):
        dispatch(self.s,'plan',{});dispatch(self.s,'accept',{})
        advance(self.s,10)
        original=copy.deepcopy(self.s)
        bases,reserved=origins(self.s)
        dispatch(self.s,'event',{'kind':'overflow'})
        dispatch(self.s,'plan',{})
        p=self.s['draft']
        self.assert_feasible(self.s,p)
        for vid,b in bases.items():
            self.assertEqual(p['routes'][vid][:len(b['prefix'])],b['prefix'])
        dispatch(self.s,'accept',{})
        dispatch(self.s,'plan',{})
        advance(self.s,1)
        with self.assertRaises(ValueError):dispatch(self.s,'accept',{})

    def test_failure_recovery_preserves_load(self):
        dispatch(self.s,'plan',{});dispatch(self.s,'accept',{})
        advance(self.s,25)
        v=next(v for v in self.s['vehicles'] if v['load']>0)
        before=v['load']
        dispatch(self.s,'event',{'kind':'failure','vehicle':v['id']})
        self.assertEqual(before,v['load'])
        with self.assertRaises(ValueError):advance(self.s,1)
        p=solve(self.s);self.assert_feasible(self.s,p)
        dispatch(self.s,'event',{'kind':'recovery','vehicle':v['id']})
        self.assertEqual(before,v['load'])

    def test_simulation_completes_exactly_once(self):
        dispatch(self.s,'plan',{});dispatch(self.s,'accept',{})
        for _ in range(10):advance(self.s,60)
        self.assertTrue(all(t['status']=='done' for t in self.s['tasks']))
        self.assertTrue(all(v['active'] is None for v in self.s['vehicles']))
        self.assertTrue(all(v['node']==v['home'] and v['load']==0 for v in self.s['vehicles']))
        self.assertAlmostEqual(sum(v['km'] for v in self.s['vehicles']), self.s['plan']['metrics']['deadhead_km']+self.s['plan']['metrics']['service_km'])

    def test_lock(self):
        self.s['tasks'][0]['locked_to']='V04'
        p=solve(self.s);self.assert_feasible(self.s,p)
        self.assertIn('T001',[a.get('task') for a in p['routes']['V04']])

    def test_benchmark_no_mutation(self):
        before=copy.deepcopy(self.s)
        r=dispatch(self.s,'benchmark',{})
        self.assertEqual(self.s,before);self.assertEqual(len(r['results']),4)

    def test_manual_requires_confirmation_and_reject_is_safe(self):
        dispatch(self.s,'plan',{});dispatch(self.s,'accept',{})
        reserved=origins(self.s)[1]
        t=next(t for t in self.s['tasks'] if t['id'] not in reserved and t['kind']=='collection')
        old=copy.deepcopy(self.s['plan'])
        dispatch(self.s,'manual',{'task':t['id'],'vehicle':'V22'})
        self.assertIsNone(t['locked_to'])
        self.assertEqual(self.s['plan'],old)
        dispatch(self.s,'reject',{})
        self.assertIsNone(t['locked_to'])
        dispatch(self.s,'manual',{'task':t['id'],'vehicle':'V22'})
        dispatch(self.s,'accept',{})
        self.assertEqual(t['locked_to'],'V22')
        self.assert_feasible(self.s,self.s['plan'])

    def test_congestion_changes_shortest_time(self):
        old=Roads(self.s).get('N5-0','N10-0')[0]
        dispatch(self.s,'event',{'kind':'congestion'})
        new=Roads(self.s).get('N5-0','N10-0')[0]
        self.assertGreater(new,old)
        self.assert_feasible(self.s,solve(self.s))

    def test_deadline_is_soft_and_visible(self):
        for t in self.s['tasks']:
            t['earliest']=420;t['deadline']=421
        p=solve(self.s)
        self.assertGreater(p['metrics']['late_tasks'],0)
        self.assert_feasible(self.s,p)

    def test_persistence_atomic_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            before=store.read()
            with self.assertRaises(ValueError):store.action('event',{'kind':'failure','vehicle':'missing'})
            self.assertEqual(before,store.read())
            store.action('plan',{});store.action('accept',{})
            self.assertIsNotNone(Store(Path(tmp)/'test.db').read()['plan'])

    def test_import_rejects_bad_values(self):
        for value in (float('nan'),-1,'1'):
            bad=demo();bad['tasks'][0]['demand']=value
            with self.assertRaises(ValueError):validate(bad)
        self.assertEqual(len(validate(demo())['tasks']),120)

    def test_disconnected_graph(self):
        self.s['edges']=[e for e in self.s['edges'] if e['a']!='N5-7']
        p=solve(self.s)
        self.assertEqual(p['metrics']['unassigned'],120)


if __name__=='__main__':unittest.main()
