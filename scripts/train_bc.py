"""Reproducible, episode-disjoint synthetic behavior-cloning experiment."""
import sys,json,hashlib,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from drive.session import Session
from drive.learning import train,infer
SCENES=['collection','sweeping','pedestrian','parked','closure','signal','sensor_stale','network_loss','brake_fault']
def collect(seeds):
    rows=[];episodes=[]
    for seed in seeds:
        for scene in SCENES:
            s=Session(scene,seed)
            while not s.done:s.step(100,collect=True)
            rows.extend(s.feature_rows[::2]);episodes.append(s.metrics())
        print('collected seed',seed,flush=True)
    return rows,episodes
def main():
    begin=time.perf_counter();rows,train_episodes=collect(range(8));valid,val_episodes=collect(range(80,82))
    model=train(rows,epochs=150,seed=42)
    model.update(train_episode_seeds=list(range(8)),validation_episode_seeds=list(range(80,82)),test_episode_seeds=list(range(1000,1010)),training_samples=len(rows),teacher='A* + velocity/steering rollout; pre-shield labels')
    path=ROOT/'data/bc_model.json';path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
    def errors(rs):
        es=[(infer(model,r['x'])['steer']/.52-r['y'][0],infer(model,r['x'])['accel']/3-r['y'][1]) for r in rs]
        return {'normalized_action_mae':sum(abs(a)+abs(b) for a,b in es)/(2*len(es)),'normalized_action_mse':sum(a*a+b*b for a,b in es)/(2*len(es)),'samples':len(es)}
    result={'status':'measured','train':errors(rows),'validation':errors(valid),'train_episodes':train_episodes,'validation_episodes':val_episodes,'seconds':time.perf_counter()-begin,'weights_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'architecture':'18 → 32 tanh → 16 tanh → 2 linear; Adam .003,150 epochs','limits':'自建二维仿真低维观测行为克隆，不是图像端到端、真实驾驶数据训练或基础模型；闭环测试另行报告'}
    (ROOT/'evidence/bc_training.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if not k.endswith('episodes')},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
