"""Generate reproducible S/M/L/XL synthetic research inputs and training template."""
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.scenario import research_demo,validate
from backend.prediction import synthetic_history

out=Path(__file__).resolve().parents[1]/'data'/'instances';out.mkdir(exist_ok=True)
for label,tasks,vehicles in [('S',50,5),('M',200,20),('L',500,50),('XL',1000,100)]:
    d=research_demo(seed=42,count=tasks);base=d['vehicles'];d['vehicles']=[];d['personnel']=[]
    for i in range(vehicles):
        v=copy.deepcopy(base[i%len(base)]);v.update(id=f'V{i+1:03}',name=f'合成车辆{i+1:03}',crew=f'P{i+1:03}')
        d['vehicles'].append(v);d['personnel'].append(dict(id=v['crew'],name='合成人员'+v['crew'],licenses=[v['kind']],skills=['sanitation'],shift_start=360,shift_end=1080))
    d['name']=f'{label}级合成研究实例：{tasks}任务/{vehicles}车辆'
    validate(d)
    (out/(label+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'history-template.json').write_text(json.dumps({'source':'synthetic','rows':synthetic_history(400)},ensure_ascii=False,indent=2),encoding='utf-8')
