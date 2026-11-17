"""Paired seed study with reproducible raw results, bootstrap CI and Wilcoxon/Holm.
Run: python scripts/research_experiment.py --seeds 30 --tasks 12 --budget 1
For scale studies change --tasks to 50/200/500/1000; do not infer production SLAs.
"""
import argparse
import copy
import json
from pathlib import Path
import random
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.scenario import research_demo,fresh
from backend.optimizer import solve_v2


def summary(values):
    r=random.Random(42);boots=sorted(statistics.mean(r.choices(values,k=len(values))) for _ in range(1000))
    return dict(mean=statistics.mean(values),median=statistics.median(values),ci95=[boots[25],boots[974]])


def run(seeds=30,tasks=12,budget=1):
    from scipy.stats import wilcoxon,friedmanchisquare
    raw=[]
    for seed in range(seeds):
        s=fresh(research_demo(seed=seed,count=tasks));s['settings']={'budget':budget,'iterations':8,'exact_every':4}
        row={'seed':seed,'tasks':tasks,'results':{}}
        for method in ('fixed','nearest','adaptive','halns'):
            p=solve_v2(copy.deepcopy(s),method)
            row['results'][method]={'metrics':p['metrics'],'objective':p['objective'],'shield':p['shield']['passed']}
        raw.append(row)
        print(f'seed {seed+1}/{seeds}',flush=True)
    stats={m:{k:summary([x['results'][m]['metrics'][k] for x in raw]) for k in ('scheduled','unassigned','late_tasks','deadhead_km','runtime_ms')} for m in raw[0]['results']}
    pairs=[]
    for m in ('fixed','nearest','adaptive'):
        delta=[x['results']['halns']['objective'][0]-x['results'][m]['objective'][0] for x in raw]
        p=float(wilcoxon(delta).pvalue) if any(delta) else 1.
        pairs.append({'baseline':m,'metric':'F1','delta':summary(delta),'p':p,'paired_effect_dz':statistics.mean(delta)/statistics.stdev(delta) if len(delta)>1 and statistics.stdev(delta)>0 else None})
    running=0
    for rank,pair in enumerate(sorted(pairs,key=lambda x:x['p'])):
        running=max(running,min(1,pair['p']*(len(pairs)-rank)));pair['holm_p']=running
    columns=[[x['results'][m]['objective'][0] for x in raw] for m in ('fixed','nearest','adaptive','halns')]
    friedman=None
    if any(len(set(v))>1 for v in zip(*columns)):
        test=friedmanchisquare(*columns);friedman={'statistic':float(test.statistic),'p':float(test.pvalue)}
    return {'source':'synthetic','seeds':seeds,'tasks':tasks,'budget_seconds':budget,'raw':raw,'summary':stats,'paired':pairs,'friedman':friedman,
            'limitations':'同硬件/预算的合成静态配对试验。不是公开基准、真实历史回放、现场试验或全套消融。时间预算造成迭代数差异，原始记录保留。'}


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--seeds',type=int,default=30);a.add_argument('--tasks',type=int,default=12);a.add_argument('--budget',type=float,default=1)
    args=a.parse_args();report=run(args.seeds,args.tasks,args.budget)
    output=Path(__file__).resolve().parents[1]/'data'/'research-experiment.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
