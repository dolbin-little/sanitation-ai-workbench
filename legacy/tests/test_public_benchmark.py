import copy,math,unittest
from pathlib import Path
from backend.public_benchmark import read_instance,solve,verify,NativeEvaluator,arrival,integrate_speed,td_shortest,raw_td_network
ROOT=Path(__file__).resolve().parents[1]/'data/public-benchmarks'

class PublicBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vrp=read_instance(next((ROOT/'solomon').rglob('c101.txt')))
        cls.carp=read_instance(next((ROOT/'gdb').rglob('gdb1.dat')))
        cls.td=read_instance(next((ROOT/'tdcarp').rglob('C01.tdsp')))

    def test_solomon_all_customers_hard_windows(self):
        s=solve(self.vrp,'insertion',0);self.assertTrue(verify(self.vrp,s)['feasible'])
        # Reverse a constructed feasible route to violate real time windows.
        s['routes']=[r[::-1] for r in s['routes']]
        self.assertTrue(any(x.startswith('window:') for x in verify(self.vrp,s)['errors']))

    def test_capacity_is_not_soft(self):
        ev=NativeEvaluator(self.carp)
        self.assertIsNone(ev.route(tuple(range(1,7))))

    def test_duplicate_and_missing_detected(self):
        s=solve(self.carp,'insertion',0);s['routes'][0][0]=s['routes'][1][0]
        c=verify(self.carp,s);self.assertFalse(c['feasible']);self.assertIn('duplicate_service',c['errors'])
        self.assertTrue(c['unassigned'])

    def test_alns_cannot_lose_best_incumbent(self):
        for p in (self.vrp,self.carp,self.td):
            a=solve(p,'insertion',0);b=solve(p,'adaptive_alns',0,3,20)
            self.assertLessEqual(b['objective'],a['objective']);self.assertTrue(verify(p,b)['valid_partial'])

    def test_signed_required_arc_orientation(self):
        p=self.carp;ev=NativeEvaluator(p)
        value,path=ev.route((1,2,3));self.assertEqual({abs(i) for i in path},{1,2,3})
        s={'routes':[list(path)],'objective':(p['n']-3,value),'unassigned':list(range(4,p['n']+1))}
        self.assertTrue(verify(p,s)['valid_partial'])

    def test_tdsp_matches_raw_speed_network(self):
        p=self.td;adj,edges,factor=raw_td_network(p['raw'])
        for t in (0.,20.5,42.,120.,200.):
            for u,v in [(p['depot'],p['jobs'][i]['u']) for i in range(1,8)]:
                self.assertAlmostEqual(arrival(p['travel'][u,v],t),td_shortest(adj,u,v,t),places=5)
            for i in range(1,8):
                j=p['jobs'][i]
                self.assertAlmostEqual(arrival(p['service'][i],t),integrate_speed(edges[j['u'],j['v']],t,factor),places=5)

    def test_speed_integration_crosses_breakpoint(self):
        e=(1,20.,[10.],[1.,2.]);self.assertEqual(integrate_speed(e,0),15.)
        self.assertEqual(integrate_speed(e,5),17.5)

    def test_td_route_replayed_independently(self):
        s=solve(self.td,'adaptive_alns',1,3,20);self.assertTrue(verify(self.td,s)['valid_partial'])

    def test_explicit_unassigned_is_failure(self):
        p=self.carp;s={'routes':[],'objective':(p['n'],0.),'unassigned':list(range(1,p['n']+1))}
        c=verify(p,s);self.assertTrue(c['valid_partial']);self.assertFalse(c['feasible'])

    def test_fleet_limit_is_hard(self):
        s=solve(self.carp,'insertion',0);p=copy.deepcopy(self.carp);p['vehicles']=1
        self.assertIn('fleet',verify(p,s)['errors'])

    def test_compact_reader_preserves_all_profile_values(self):
        from backend.public_td_compact import read_td
        other=read_td(self.td['raw'])
        for key,profile in self.td['travel'].items():
            for t in (0.,10.,120.,300.):
                self.assertEqual(arrival(profile,t),arrival(other['travel'][key],t))
        for key,profile in self.td['service'].items():
            for t in (0.,10.,120.,300.):
                self.assertEqual(arrival(profile,t),arrival(other['service'][key],t))

    def test_non_triangle_td_profiles_reject_invalid_destroy(self):
        def delay(d):return ([100.],[(100.,100.+d,1.)])
        p={'kind':'tdcarp','n':3,'depot':0,'capacity':3,'vehicles':1,'horizon':10.,
           'jobs':[None]+[{'u':i,'v':i,'demand':1} for i in range(1,4)],
           'service':{s:delay(0) for i in range(1,4) for s in (i,-i)},
           'travel':{(u,v):delay(0 if u==v else 1) for u in range(4) for v in range(4)}}
        p['travel'][0,3]=delay(20)
        for seed in range(10):
            s=solve(p,'adaptive_alns',seed,1,100)
            self.assertEqual(s['unassigned'],[])

if __name__=='__main__':unittest.main()
