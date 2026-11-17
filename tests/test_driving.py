import unittest,math,json,tempfile,threading,urllib.request,urllib.error,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from drive.world import bicycle,World,body_clearance,footprint_on_road
from drive.edge import priority_wait,sqrt_allocation,schedule
from drive.session import Session
from drive.perception import Lidar
from drive.learning import load_model,infer,features
from drive.planning import safety_shield

class DrivingTests(unittest.TestCase):
    def test_exact_braking_distance(self):
        e={'x':10.,'y':40.,'yaw':0.,'v':1.,'steer':0.}
        q=bicycle(e,0,-3,1);self.assertAlmostEqual(q['x']-10,1/6);self.assertEqual(q['v'],0)
    def test_yaw_wrap_does_not_reverse_translation(self):
        e={'x':50.,'y':40.,'yaw':math.pi-.001,'v':2.,'steer':.5}
        self.assertLess(bicycle(e,.5,0,.2)['x'],50)
    def test_prediction_execution_use_identical_actuator_steps(self):
        e={'x':30.,'y':40.,'yaw':.01,'v':3.,'steer':0.};q=dict(e)
        for _ in range(4):q=bicycle(q,.5,.5,.05)
        predicted=bicycle(e,.5,.5,.2)
        for key in ['x','y','yaw','v','steer']:self.assertAlmostEqual(q[key],predicted[key],places=10)
    def test_body_geometry_matches_rear_axle(self):
        e={'x':10.,'y':40.,'yaw':0.,'v':0.,'steer':0.}
        self.assertAlmostEqual(body_clearance(e,{'x':14.5,'y':40.,'radius':1.}),0)
        self.assertFalse(footprint_on_road({**e,'y':30.5}))
    def test_queue_allocation_and_overload(self):
        self.assertEqual(priority_wait([5.],[1.],[1]),[None]);self.assertAlmostEqual(sum(sqrt_allocation([1,4],9)),9)
        self.assertAlmostEqual(sqrt_allocation([1,4],9)[1],6)
        w=priority_wait([.1,.1],[1.,1.],[0,1]);self.assertLess(w[0],w[1])
    def test_network_loss_never_offloads_control(self):
        for bad in [False,True]:
            e=schedule(5,bad);self.assertTrue(all(j['placement']=='onboard' for j in e['jobs'] if j['critical']))
            self.assertLessEqual(e['allocated_ghz'],e['edge_cpu_budget_ghz']+1e-9)
        self.assertTrue(all(j['placement']!='edge' for j in schedule(5,True)['jobs']))
    def test_sensor_stale_timestamp_triggers_guard(self):
        s=Session('sensor_stale',1000)
        s.step(45);self.assertGreater(s.obs['age'],.6);self.assertTrue(s.shield['active']);self.assertEqual(s.command['accel'],-3)
    def test_sensor_observation_is_not_ground_truth(self):
        s=Session('parked',1000);s.step(40)
        self.assertNotIn('_visible_ids',s.snapshot()['sensor']);self.assertTrue(all(t['id'].startswith('T') for t in s.obs['tracks']))
        self.assertNotIn('actors',s.obs)
    def test_invalid_external_trajectory(self):
        s=Session()
        for p in [[[0,0],[float('nan'),1]],[[True,0],[1,1]],[[0,0]]]:
            with self.assertRaises(ValueError):s.import_adapter({'model_id':'test','source_url':'https://example.org','waypoints':p})
    def test_collection_and_red_light(self):
        for scene in ['collection','signal','pedestrian','parked','closure','sweeping']:
            with self.subTest(scene=scene):
                s=Session(scene,1000)
                while not s.done:s.step(100)
                self.assertTrue(s.metrics()['completed']);self.assertFalse(s.collisions);self.assertEqual(s.offroad_steps,0);self.assertEqual(s.red_violations,0)
                if scene=='sweeping':self.assertGreater(s.metrics()['sweeping_coverage'],.9)
    def test_bc_weights_and_split(self):
        m=load_model();self.assertFalse(m['foundation_model']);self.assertFalse(set(m['train_episode_seeds'])&set(m['test_episode_seeds']))
        s=Session();cmd=infer(m,features(s.ego,s.obs,s.path));self.assertTrue(-.52<=cmd['steer']<=.52);self.assertTrue(-3<=cmd['accel']<=1.8)
        self.assertEqual(m['feature_count'],18)
    def test_sweeping_arrival_does_not_imply_job_completion(self):
        s=Session('sweeping');s.dwell=3.
        self.assertFalse(s.mission_complete());s.swept_cells=set(range(32));self.assertTrue(s.mission_complete())

class APITests(unittest.TestCase):
    def test_revision_and_simulated_receipt_persist(self):
        from server import DriveStore,fleet_server
        with tempfile.TemporaryDirectory() as d:
            fleet=fleet_server.Store(Path(d)/'f.sqlite3');store=DriveStore(Path(d)/'d.sqlite3',fleet);before=fleet.read()
            missions=store.missions();task=missions[0]['id'];store.action('reset',{'revision':0,'scenario':'collection','mission_id':task})
            with self.assertRaises(ValueError):store.action('step',{'revision':0,'count':1})
            while not store.session.done:store.action('step',{'revision':store.revision,'count':100})
            self.assertEqual(store.runs()[0]['mission']['id'],task);self.assertEqual(fleet.read(),before)
            self.assertTrue(DriveStore(Path(d)/'d.sqlite3',fleet).runs())
    def test_http_origin_json_and_dispatch(self):
        from server import DriveStore,fleet_server,handler,ThreadingHTTPServer
        with tempfile.TemporaryDirectory() as d:
            f=fleet_server.Store(Path(d)/'f.sqlite3');ds=DriveStore(Path(d)/'d.sqlite3',f);http=ThreadingHTTPServer(('127.0.0.1',0),handler(f,ds));t=threading.Thread(target=http.serve_forever,daemon=True);t.start();url='http://127.0.0.1:'+str(http.server_port)
            try:
                for path in ['/','/dispatch','/api/state','/api/drive/state']:
                    self.assertEqual(urllib.request.urlopen(url+path).status,200)
                r=urllib.request.Request(url+'/api/drive/step',data=b'{"revision":0,"count":1}',headers={'Content-Type':'application/json','Origin':'https://example.org'})
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(r)
                self.assertEqual(e.exception.code,403)
                r=urllib.request.Request(url+'/api/drive/manual',data=b'{"revision":0,"enabled":true,"steer":NaN}',headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(r)
                self.assertEqual(e.exception.code,400)
            finally:http.shutdown();http.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
