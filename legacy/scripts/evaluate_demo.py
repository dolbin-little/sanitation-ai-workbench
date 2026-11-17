"""Generate reproducible demo input and multi-seed comparison artifacts."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.scenario import demo,fresh
from backend.engine import solve

out=ROOT/'data'
out.mkdir(exist_ok=True)
(out/'demo-scenario.json').write_text(json.dumps(demo(),ensure_ascii=False,indent=2),encoding='utf-8')
results=[]
for seed,count in [(42,120),(7,120),(19,120),(42,300)]:
    state=fresh(demo(seed,count))
    for strategy in ('fixed','nearest','adaptive'):
        p=solve(state,strategy)
        results.append({'seed':seed,'tasks':count,'strategy':strategy,**p['metrics']})
report={'description':'合成路网/合成任务；三策略使用相同约束，不代表企业实际收益。runtime_ms因机器不同而变化。', 'results':results}
(out/'benchmark-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
for r in results:print(r)
