import copy
import json
import unittest
from backend.scenario import demo,research_demo,fresh,validate
from backend.model import Network,Evaluator,assign_crews,upgrade,slot
from backend.optimizer import solve_v2,candidate,exact_repair
from backend.shield import inspect
from backend.risk import cvar
from backend.control import trigger,safe_plan
from backend.prediction import train,synthetic_history,forecast,interval
from backend.service import dispatch
import time


class ResearchTests(unittest.TestCase):
    def small(self,n=12):
        s=fresh(research_demo(count=n));s['settings']={'budget':2,'iterations':6,'exact_every':3};upgrade(s);assign_crews(s);return s

    def test_halns_and_exact_execute(self):
        s=self.small();p=solve_v2(s)
        self.assertTrue(p['shield']['passed'],p['shield'])
        self.assertEqual(p['metrics']['scheduled'],12)
        self.assertTrue(p['solver']['weights'])
        ev=Evaluator(s);c=candidate(ev,p['assignment']);result,report=exact_repair(ev,c,time.perf_counter()+5)
        self.assertIn(report['status'],('OPTIMAL','FEASIBLE'))
        self.assertGreater(report['columns'],0)
        self.assertLessEqual(result['objective'],c['objective'])

    def test_cvar_fractional_tail(self):
        self.assertAlmostEqual(cvar([0,10,20,30],.625),(30+.5*20)/1.5)
        self.assertAlmostEqual(cvar([1,2,3],0),2)

    def test_time_dependent_fifo_and_permissions(self):
        s=self.small();e=s['edges'][0];e['traffic']=[{'start':420,'end':430,'factor':3}]
        net=Network(s);v=s['vehicles'][0]
        arrivals=[t+net.traversal(e,t,v)[0] for t in range(419,433)]
        self.assertEqual(arrivals,sorted(arrivals))
        e['allowed_kinds']=['sweeper'];self.assertIsNone(net.traversal(e,420,v))

    def test_shield_rejects_forged_resources_duplicate_and_arc(self):
        s=self.small(6);p=solve_v2(s);self.assertTrue(inspect(s,p)['passed'])
        seq=next(seq for seq in p['routes'].values() if seq)
        seq[0]['load_after']+=1;self.assertFalse(inspect(s,p)['passed'])
        p=solve_v2(s);seq=next(seq for seq in p['routes'].values() if seq);seq.insert(1,copy.deepcopy(seq[0]))
        self.assertFalse(inspect(s,p)['passed'])
        p=solve_v2(s);a=next(a for seq in p['routes'].values() for a in seq if a.get('task') and a['service_km']>0)
        a['service_path']=[a['start']];self.assertFalse(inspect(s,p)['passed'])

    def test_crew_unique_and_skills(self):
        s=self.small();s['personnel']=s['personnel'][:1];assign_crews(s)
        self.assertEqual(sum(v.get('crew') is not None for v in s['vehicles']),1)
        p=solve_v2(s);self.assertTrue(p['shield']['passed']);self.assertGreater(len(p['unassigned']),0)

    def test_bays_and_energy(self):
        self.assertEqual(slot([(0,10),(0,5)],0,4,2),5)
        s=self.small();
        for f in s['facilities']:f['bays']=1
        p=solve_v2(s);self.assertTrue(p['shield']['passed'],p['shield'])
        for v in s['vehicles']:v['energy_capacity']=.01;v['energy']=.01;v['energy_per_km']=1
        p=solve_v2(s);self.assertGreater(p['metrics']['unassigned'],0)

    def test_horizon_and_freeze(self):
        s=self.small();s['settings']['horizon']=15;s['tasks'][0]['earliest']=800
        p=solve_v2(s);self.assertIn(s['tasks'][0]['id'],p['deferred']);self.assertTrue(p['shield']['passed'])
        s['draft']=p;dispatch(s,'accept',{});dispatch(s,'advance',{'minutes':5})
        q=solve_v2(s);self.assertTrue(q['shield']['passed'],q['shield'])
        self.assertTrue(q['frozen'])

    def test_hysteresis_and_hard_event(self):
        s=self.small();s['controller']['last_trigger']=420
        self.assertEqual(trigger(s,'failure'),'L2')
        self.assertEqual(trigger(s), 'L0')
        self.assertEqual(trigger(s,'road_closed'),'L1')

    def test_game_potential_strictly_improves(self):
        s=self.small();p=solve_v2(s);s['draft']=p;dispatch(s,'accept',{})
        p=solve_v2(s,'game');trace=[x['objective'] for x in p['trace']]
        self.assertTrue(all(b<a for a,b in zip(trace,trace[1:])))
        self.assertFalse(p['solver']['equilibrium_claim']);self.assertTrue(p['shield']['passed'])

    def test_l4_no_unsafe_fallback(self):
        s=self.small(3);p=solve_v2(s);s['draft']=p;dispatch(s,'accept',{})
        for e in s['edges']:e['closed']=True
        self.assertIsNone(safe_plan(s));self.assertEqual(s['controller']['level'],'L4')

    def test_prediction_serialization_and_deadline(self):
        b=train(synthetic_history(200));b=json.loads(json.dumps(b));s=self.small(3)
        t=s['tasks'][0];t['fill']=4.49;t['bin_capacity']=5
        f=forecast(s,b);self.assertLess(f['tasks'][t['id']]['deadline'],t['deadline'])
        for target,m in b['models'].items():
            q=interval(b,target,[8,1,0,0,1,0]);self.assertEqual(q,sorted(q));self.assertGreaterEqual(m['gamma'],0)
        self.assertEqual(b['split'],{'train':120,'calibration':40,'test':40})

    def test_invalid_extensions(self):
        d=research_demo(count=3);d['tasks'][2]['service_path']=['N0-0','N10-8']
        with self.assertRaises(ValueError):validate(d)
        d=research_demo();d['settings']={'theta_on':.3,'theta_off':.5}
        with self.assertRaises(ValueError):validate(d)

    def test_accept_rechecks_shield(self):
        s=self.small(3);s['draft']=solve_v2(s)
        next(seq for seq in s['draft']['routes'].values() if seq)[0]['water_after']+=20
        with self.assertRaises(ValueError):dispatch(s,'accept',{})

    def test_congestion_retimes_but_keeps_committed_order(self):
        s=self.small();s['draft']=solve_v2(s);dispatch(s,'accept',{});dispatch(s,'advance',{'minutes':5})
        from backend.model import prefixes
        before={v:[a.get('task') for a in seq] for v,seq in prefixes(s)[0].items()}
        dispatch(s,'event',{'kind':'congestion'})
        after={v:[a.get('task') for a in seq] for v,seq in prefixes(s)[0].items()}
        self.assertEqual(before,after)
        p=solve_v2(s);self.assertTrue(p['shield']['passed'],p['shield'])

    def test_forecast_water_is_reserved_and_checked(self):
        s=self.small(3);t=s['tasks'][2]
        s['forecast']={'tasks':{t['id']:{'water':[1,1.2,1.5],'fill_rate':[0,0,0],'deadline':t['deadline']}},'global':{}}
        p=solve_v2(s);self.assertTrue(p['shield']['passed'])
        a=next(a for seq in p['routes'].values() for a in seq if a.get('task')==t['id'])
        self.assertAlmostEqual(a['water_reserved'],t['water']*1.5)

    def test_sliding_calibration_preserves_test_report(self):
        from backend.prediction import recalibrate
        b=train(synthetic_history(100));original=copy.deepcopy(b['models']['fill_rate']['metrics'])
        rows=synthetic_history(250,seed=19)
        for r in rows:r['at']+=1000;r['y']['fill_rate']+=.03
        report=recalibrate(b,rows)
        self.assertEqual(report['samples'],200)
        self.assertGreater(report['gamma']['fill_rate'],.01)
        self.assertEqual(b['models']['fill_rate']['metrics'],original)

    def test_online_calibration_rejects_reusing_holdout(self):
        from backend.prediction import recalibrate
        rows=synthetic_history(100);b=train(rows)
        with self.assertRaises(ValueError):recalibrate(b,rows[-20:])

if __name__=='__main__':unittest.main()
