import copy
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .engine import solve, origins
from .scenario import demo, research_demo, fresh, validate
from .model import upgrade, settings, assign_crews, prefixes
from .control import safe_plan, respond
from .shield import inspect
from .schema_v2 import validate_settings


class Store:
    def __init__(self, filename):
        self.filename = str(filename)
        self.lock = threading.RLock()
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
            if not c.execute("SELECT 1 FROM state WHERE id=1").fetchone():
                c.execute("INSERT INTO state VALUES (1, ?)", (json.dumps(fresh(demo()),ensure_ascii=False),))

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.filename, timeout=30)
        try:
            with c:
                yield c
        finally:
            c.close()

    def read(self):
        with self.connect() as c:
            return json.loads(c.execute("SELECT data FROM state WHERE id=1").fetchone()[0])

    def save(self, s):
        with self.connect() as c:
            c.execute("UPDATE state SET data=? WHERE id=1", (json.dumps(s,ensure_ascii=False,allow_nan=False),))

    def action(self, name, data):
        with self.lock:
            s = self.read()
            result = dispatch(s, name, data)
            self.save(s)
            return result if result is not None else s


def audit(s, message):
    s["audit"].insert(0, {"at": s["now"], "revision": s["revision"], "message": message})
    s["audit"] = s["audit"][:200]


def change(s, message):
    s["revision"] += 1
    s["draft"] = None
    audit(s, message)


def find(rows, id):
    for r in rows:
        if r["id"] == id:
            return r
    raise ValueError("未找到指定对象")


def advance(s, minutes):
    if not s.get("plan"):
        raise ValueError("请先生成并确认计划")
    if s.get("needs_replan"):
        raise ValueError("事件改变了约束，请先确认重调度方案再推进仿真")
    if isinstance(minutes,bool) or not isinstance(minutes,int) or not 1 <= minutes <= 60:
        raise ValueError("单次推进须为 1—60 个整数分钟")
    if s["now"] + minutes > 1440:
        raise ValueError("演示日已结束，请重置场景")
    for _ in range(minutes):
        # Dispatch at the old clock, then advance and complete actions.
        for v in s["vehicles"]:
            queue = s["plan"]["routes"].get(v["id"], [])
            if v["enabled"] and not v["active"] and queue:
                a = queue.pop(0)
                v["active"] = a
                if a.get("task"):
                    find(s["tasks"],a["task"])["status"] = "running"
        s["now"] += 1
        for v in s["vehicles"]:
            # Consume any actions starting/ending before this tick, including zero-length depot returns.
            while v["enabled"] and v["active"] and v["active"]["finish"] <= s["now"]+1e-8:
                a = v["active"]
                v.update(node=a["end"], load=a["load_after"], water=a["water_after"], active=None)
                if 'energy_after' in a: v['energy']=a['energy_after']
                v["km"] += a["km"] + a["service_km"]
                if a.get("task"):
                    t = find(s["tasks"],a["task"])
                    t.update(status="done",completed_at=a["finish"],completed_by=v["id"])
                queue = s["plan"]["routes"].get(v["id"], [])
                if queue:
                    v["active"] = queue.pop(0)
                    if v["active"].get("task"):
                        find(s["tasks"],v["active"]["task"])["status"] = "running"
    s["history"].append({"at":s["now"], "completed":sum(t["status"]=="done" for t in s["tasks"]),
                         "km":round(sum(v["km"] for v in s["vehicles"]),2)})
    s["history"] = s["history"][-100:]
    change(s, f"仿真时钟推进 {minutes} 分钟；旧候选方案失效")
    if settings(s)['auto_control']:
        if s.get('model_bundle'):
            from .prediction import forecast
            s['forecast']=forecast(s,s['model_bundle'])
        respond(s)


def dispatch(s, name, data):
    if name!='benchmark':upgrade(s)
    if name == "plan":
        strategy=data.get('strategy','halns')
        candidate = safe_plan(s,strategy)
        if candidate is None:
            raise ValueError("未能生成可通过安全验收的候选方案，请检查服务启动环境和运行记录")
        s["draft"] = candidate
        audit(s, "生成候选调度方案，等待人工确认")
    elif name == "accept":
        d = s.get("draft")
        if not d or d["base_revision"] != s["revision"]:
            raise ValueError("候选方案已失效，请重新计算")
        work=copy.deepcopy(s)
        for tid,vid in d.get('overrides',{}).items():find(work['tasks'],tid)['locked_to']=vid
        if d.get('version')==2:
            report=inspect(work,d)
            if not report['passed']:raise ValueError('安全盾拒绝：'+'; '.join(report['errors'][:5]))
        for tid, vid in d.get("overrides",{}).items():
            find(s["tasks"],tid)["locked_to"] = vid
        s["plan"] = copy.deepcopy(d)
        s["needs_replan"] = False
        s['controller']['next_roll']=s['now']+15
        change(s, f"人工确认计划：{d['metrics']['scheduled']} 项待执行任务，{d['metrics']['unassigned']} 项待处理")
    elif name == "reject":
        s["draft"] = None
        audit(s,"人工拒绝候选方案，保留原执行计划")
    elif name == "advance":
        advance(s, data.get("minutes",10))
    elif name == "event":
        kind = data.get("kind")
        if kind in ("overflow", "complaint"):
            if len(s["tasks"])>=2000:
                raise ValueError("当前导入上限为2000项任务，求解质量须按规模验证")
            node = data.get("node",s["nodes"][len(s["events"])*7 % len(s["nodes"])]["id"])
            find(s["nodes"],node)
            tid = f"E{len(s['events'])+1:03}"
            while any(t["id"]==tid for t in s["tasks"]):
                tid += "A"
            s["tasks"].append(dict(id=tid,name=("垃圾满溢" if kind=="overflow" else "投诉清运")+f" · {node}",
                kind="collection",start=node,end=node,earliest=s["now"],deadline=s["now"]+(30 if kind=="overflow" else 45),
                service=8,demand=1.5,water=0,priority=3,status="pending",locked_to=None,completed_at=None))
            label = f"新增{('满溢' if kind=='overflow' else '投诉')}任务 {tid}，需人工确认新计划"
        elif kind == "failure":
            v = find(s["vehicles"],data.get("vehicle"))
            if not v["enabled"]:
                raise ValueError("车辆已处于故障状态")
            a = v["active"]
            if a:
                if a.get("task"):
                    t = find(s["tasks"],a["task"])
                    t["status"] = "pending"
                # Prototype interruptions snap to latest path node; partial service rolled back.
                path = a["path"]
                if s["now"] >= a["arrive"]:
                    v["node"] = a["start"]
                    v["km"] += a["km"]
                else:
                    p = max(0,min(1,(s["now"]-a["depart"])/max(0.001,a["arrive"]-a["depart"])))
                    v["node"] = path[min(len(path)-1,int(p*(len(path)-1)))]
                    v["km"] += a["km"]*p
                v["active"] = None
            if s["plan"]:
                s["plan"]["routes"][v["id"]] = []
            for t in s["tasks"]:
                if t.get("locked_to") == v["id"] and t["status"] != "done":
                    t["locked_to"] = None
            v["enabled"] = False
            label = f"{v['name']}故障，冻结例外：释放未完成任务及车辆锁定；车内既有载荷留车待救援"
        elif kind == "congestion":
            s["congestion"] = {"nodes":[n["id"] for n in s["nodes"] if n["x"]>=5], "factor":2.5,"until":s["now"]+60}
            label = "东片区通行时间调整为 2.5 倍（60分钟），进行中动作保留原行程估计"
        elif kind == 'road_closed':
            edge=next((e for e in s['edges'] if e['a']==data.get('a') and e['b']==data.get('b')),None)
            if not edge:raise ValueError('指定有向道路不存在')
            edge['closed']=True
            label=f"有向道路 {edge['a']} → {edge['b']} 封闭"
        elif kind == 'facility_closed':
            f=find(s['facilities'],data.get('facility'));f['closed']=True;label=f['name']+'关闭'
        elif kind == 'weather':
            value=data.get('value')
            if not isinstance(value,int) or not 0<=value<=10:raise ValueError('天气编码须为0—10整数')
            s['weather']=value;label='天气规则变更：'+str(value)
        elif kind == "recovery":
            v = find(s["vehicles"],data.get("vehicle"))
            if v["enabled"]:
                raise ValueError("车辆未故障")
            v["enabled"] = True
            label = f"{v['name']}恢复可用，保留故障前已完成收运的载荷"
        else:
            raise ValueError("未知事件类型")
        s["needs_replan"] = True
        s["events"].insert(0,{"at":s["now"],"kind":kind,"label":label})
        change(s,label)
        if settings(s)['auto_control']:respond(s,kind)
    elif name == "lock":
        t = find(s["tasks"],data.get("task"))
        if t["status"] != "pending":
            raise ValueError("只可修改未开始任务的车辆锁定")
        owner = next((vid for vid, seq in (s["plan"] or {}).get("routes",{}).items() if any(a.get("task")==t["id"] for a in seq)),None)
        if not owner:
            raise ValueError("任务尚未分配，请先确认计划或人工改派")
        t["locked_to"] = None if t.get("locked_to") else owner
        change(s,f"{t['id']} {'锁定车辆 '+owner if t['locked_to'] else '解除车辆锁定'}")
    elif name == "manual":
        t = find(s["tasks"],data.get("task"))
        v = find(s["vehicles"],data.get("vehicle"))
        if t["status"] != "pending" or t["id"] in prefixes(s)[1]:
            raise ValueError("执行中或冻结窗口内已承诺任务不能普通改派")
        if v["kind"] != t["kind"] or not v["enabled"]:
            raise ValueError("目标车辆故障或车型不兼容")
        work = copy.deepcopy(s)
        find(work["tasks"],t["id"])["locked_to"] = v["id"]
        d = safe_plan(work)
        if d is None:raise ValueError('人工改派未通过安全盾')
        if any(u["id"] == t["id"] for u in d["unassigned"]):
            raise ValueError("指定车辆无法在硬约束内执行任务；未改变原计划")
        d["overrides"] = {t["id"]:v["id"]}
        s["draft"] = d
        audit(s,f"人工改派候选：{t['id']} → {v['id']}，确认后生效并锁定车辆")
    elif name == "benchmark":
        work = copy.deepcopy(s)
        # Each solver uses identical current state, frozen prefix, locks and constraints.
        results = []
        from .optimizer import solve_v2
        for strategy in ("fixed","nearest","adaptive"):
            p = solve_v2(work,strategy)
            results.append({"strategy":strategy,**p["metrics"],'objective':p['objective'],'shield':p['shield']})
        p=safe_plan(work)
        if p:results.append({'strategy':'halns',**p['metrics'],'objective':p.get('objective'),'shield':p.get('shield')})
        return {"at":s["now"],"revision":s["revision"],"results":results,
                "note":"同一当前快照、相同硬约束；固定顺序策略为合成基线，不代表真实人工调度。仅比较规划结果，不是实车节省率。"}
    elif name=='settings':
        cfg=validate_settings({**settings(s),**data})
        s['settings']=cfg
        change(s,'算法参数已更新，旧候选失效')
    elif name=='train':
        from .prediction import train, synthetic_history, forecast
        rows=data.get('rows')
        bundle=train(rows if rows is not None else synthetic_history(),source='imported' if rows is not None else 'synthetic')
        s['model_bundle']=bundle;s['forecast']=forecast(s,bundle)
        s['prediction_report']={k:v for k,v in bundle.items() if k!='models'}
        s['prediction_report']['metrics']={k:v['metrics'] for k,v in bundle['models'].items()}
        change(s,'分位数GBDT训练及独立校准完成；来源：'+bundle['source'])
    elif name=='recalibrate':
        from .prediction import recalibrate,forecast
        if not s.get('model_bundle'):raise ValueError('请先训练预测器')
        report=recalibrate(s['model_bundle'],data.get('rows'))
        s['prediction_report']['online_calibration']=report
        s['forecast']=forecast(s,s['model_bundle']);change(s,'使用最近200条已观测样本完成滑动校准')
    elif name=='forecast':
        from .prediction import forecast
        if not s.get('model_bundle'):raise ValueError('请先训练或导入历史数据训练预测器')
        s['forecast']=forecast(s,s['model_bundle']);change(s,'预测区间与风险截止期已更新')
    elif name=='reference':
        from .reference_solver import reference
        small=fresh(research_demo(count=6));small['vehicles']=small['vehicles'][:3]
        s['reference_report']=reference(small,budget=5)
        audit(s,'运行6任务/3车辆的小规模静态CP-SAT参照；不改变当前计划')
    elif name=='control':
        respond(s,force=True);audit(s,'执行分级恢复评估，候选仍需人工确认')
    elif name=='handover':
        decision=data.get('decision');note=str(data.get('note','')).strip()
        if decision not in ('external','defer','support') or not note:raise ValueError('需选择外援/延期/跨区支援，并填写处置依据')
        s.setdefault('handovers',[]).append({'at':s['now'],'decision':decision,'note':note[:1000],
            'tasks':[u['id'] for u in (s.get('draft') or {}).get('unassigned',[])]})
        audit(s,'人工处置登记：'+decision+'；'+note[:200])
    elif name in ("reset","import","research_demo"):
        scenario = validate(data["scenario"]) if name=="import" else research_demo() if name=='research_demo' else demo()
        backup_revision = s["revision"]
        s.clear(); s.update(fresh(scenario)); s["revision"] = backup_revision+1
        audit(s,"载入新演示场景" if name=="reset" else "导入场景并清空运行状态")
    else:
        raise ValueError("不支持的操作")

