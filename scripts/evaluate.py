"""Frozen paired simulation evaluation; includes failures and exposes raw evidence."""
import sys,json,csv,hashlib,platform,statistics,time,math
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from drive.session import Session,POLICIES
from drive.world import SCENARIOS
SEEDS=list(range(1000,1010));POLICY_LIST=['reactive','shielded','no_shield','bc_guarded']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def episode(job):
    scene,seed,policy=job;s=Session(scene,seed,policy)
    while not s.done:s.step(100)
    if seed==1000:(ROOT/f'evidence/replays/{scene}-{policy}.json').write_text(json.dumps({'mission':s.mission,'metrics':s.metrics(),'trace':s.trace,'last_state':s.snapshot()},ensure_ascii=False),encoding='utf-8')
    return {**s.metrics(),'safe_arrival':s.dwell>=3 and not s.collisions and s.offroad_steps==0 and s.red_violations==0,'safe_success':s.mission_complete() and not s.collisions and s.offroad_steps==0 and s.red_violations==0}
def wilson(k,n):
    z=1.96;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(max(0,c-r),4),round(min(1,c+r),4)]
def main():
    root=ROOT/'evidence';(root/'replays').mkdir(exist_ok=True)
    sources={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'drive').glob('*.py')}
    protocol={'status':'frozen_before_test','seeds':SEEDS,'scenarios':list(SCENARIOS),'policies':POLICY_LIST,'train_seeds':list(range(8)),'validation_seeds':[80,81],'control_dt_s':.2,'truth_dt_s':.05,'episode_limit_s':110,'dwell_s':3,'safe_success':'endpoint dwell complete AND sweeping coverage >=90% when sweeping AND zero contact AND zero offroad samples AND zero red-light violations','world_variation':'start pose, actor lateral position, signal release and fault onset; fixed road layout and actor speed','scan_rng':'one Gaussian draw per ray per scan; same seed and simulation frame across policies','observations':'virtual ray intersections + map + ego localisation + synthetic signal/V2X; no actor truth supplied to controller','workers':4,'timing':'perf_counter: full simulation step including sensors/planner/controller/guard and truth evaluation, parallel CPU contention; excludes HTTP/UI; not vehicle real-time latency','weights_sha256':sha(ROOT/'data/bc_model.json'),'source_sha256':sources,'limits':'self-generated 2D sanitation scenarios; not a public driving benchmark, physical safety proof, real lidar evaluation or ISO certification'}
    (root/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8');begin=time.perf_counter();rows=[]
    jobs=[(s,z,p) for s in SCENARIOS for z in SEEDS for p in POLICY_LIST]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,row in enumerate(pool.map(episode,jobs)):
            rows.append(row)
            if (i+1)%40==0:print(f'evaluated {i+1}/{len(jobs)}',flush=True)
    with (root/'runs.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    groups=[]
    for scene in SCENARIOS:
        for policy in POLICY_LIST:
            rs=[r for r in rows if r['scenario']==scene and r['policy']==policy];n=len(rs);safe=sum(r['safe_success'] for r in rs)
            groups.append({'scenario':scene,'scenario_name':SCENARIOS[scene][0],'policy':policy,'policy_name':POLICIES[policy],'n':n,'safe_success':safe,'safe_success_wilson95':wilson(safe,n),'completed':sum(r['completed'] for r in rs),'collision_episodes':sum(r['collision_objects']>0 for r in rs),'offroad_episodes':sum(r['offroad_substeps']>0 for r in rs),'red_episodes':sum(r['red_light_violations']>0 for r in rs),'mean_time_s':round(statistics.mean(r['sim_time_s'] for r in rs),3),'mean_distance_m':round(statistics.mean(r['distance_m'] for r in rs),3),'mean_step_p95_ms':round(statistics.mean(r['step_cpu_p95_ms'] for r in rs),3)})
    totals=[]
    for p in POLICY_LIST:
        rs=[r for r in rows if r['policy']==p];totals.append({'policy':p,'n':len(rs),'safe_success':sum(r['safe_success'] for r in rs),'collision_episodes':sum(r['collision_objects']>0 for r in rs),'offroad_episodes':sum(r['offroad_substeps']>0 for r in rs),'red_episodes':sum(r['red_light_violations']>0 for r in rs)})
    out={'status':'measured','total_runs':len(rows),'scenario_count':len(SCENARIOS),'seeds':SEEDS,'policies':POLICY_LIST,'groups':groups,'totals':totals,'elapsed_seconds':round(time.perf_counter()-begin,2),'scope':'自建二维环卫服务道路闭环仿真；9类场景×10种子×4策略；无实车或公开自动驾驶数据集效果主张。','hardware':{'platform':platform.platform(),'processor':platform.processor(),'python':platform.python_version(),'workers':4},'weights_sha256':protocol['weights_sha256'],'runs_sha256':sha(root/'runs.csv'),'protocol_sha256':sha(root/'protocol.json')}
    (root/'summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(totals),flush=True)
if __name__=='__main__':main()
