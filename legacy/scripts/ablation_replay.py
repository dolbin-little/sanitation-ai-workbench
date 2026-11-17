"""Configurable paired dynamic/ablation harness; saves raw failures too."""
import argparse
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.scenario import research_demo,fresh
from backend.prediction import train,synthetic_history,forecast
from backend.model import settings,upgrade
from backend.optimizer import solve_v2
from backend.control import respond
from backend.service import dispatch


def replay(seed,variant,model,tasks=12,budget=1):
    s=fresh(research_demo(seed=seed,count=tasks));upgrade(s)
    s['settings'].update(budget=budget,iterations=6,exact_every=3,auto_control=False)
    model=copy.deepcopy(model)
    if variant=='no_calibration':
        for m in model['models'].values():m['gamma']=0
    if variant=='point_prediction':
        for m in model['models'].values():m['quantiles']=[m['quantiles'][1]]*3;m['gamma']=0
    s['forecast']=forecast(s,model)
    if variant=='no_cvar':s['settings']['risk_enabled']=False
    if variant=='no_stability':s['settings']['stability_weight']=0
    if variant=='no_freeze':s['settings']['freeze']=0
    if variant=='separate_types':
        # Allocation already enforces types; separation experiment removes shared facility competition.
        # Explicitly labeled relaxation, NOT a true alternative VRPTW/CARP implementation.
        for f in s['facilities']:f['bays']=999
    results=[]
    for step in range(4):
        if step:
            dispatch(s,'event',{'kind':['overflow','congestion','failure'][step-1],'vehicle':'V01'})
        if variant=='fixed15' or variant=='no_game':s['draft']=solve_v2(s)
        else:respond(s,['initial','overflow','congestion','failure'][step],force=True)
        p=s.get('draft')
        results.append({'at':s['now'],'step':step,'level':s['controller']['level'],'metrics':p['metrics'] if p else None,'shield':p.get('shield') if p else None,'objective':p.get('objective') if p else None})
        if not p or not p['shield']['passed']:break
        dispatch(s,'accept',{});dispatch(s,'advance',{'minutes':15})
    return {'seed':seed,'variant':variant,'results':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seeds',type=int,default=3);parser.add_argument('--tasks',type=int,default=12);parser.add_argument('--budget',type=float,default=1)
    a=parser.parse_args();bundle=train(synthetic_history(400));rows=[]
    for seed in range(a.seeds):
        for variant in ('full','fixed15','no_game','point_prediction','no_calibration','no_cvar','no_stability','no_freeze','separate_types'):
            rows.append(replay(seed,variant,bundle,a.tasks,a.budget));print(seed,variant,flush=True)
    path=Path(__file__).resolve().parents[1]/'data'/'ablation-replay.json'
    path.write_text(json.dumps({'source':'synthetic','rows':rows,'limitations':'同一合成事件轨迹的可配置回放。separate_types仅为设施容量放宽对照；不冒充独立VRPTW/CARP。fixed15与no_game在该15分钟事件轨迹上可能相同，应使用更细时间轨迹另测触发收益。'},ensure_ascii=False,indent=2),encoding='utf-8')
