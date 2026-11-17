"""Reproducible synthetic service-unit scenario. No external map/data required."""
import copy
import math
import random

KINDS = {"collection": "压缩收运车", "hook": "勾臂运输车", "sweeper": "道路洗扫车"}


def demo(seed=42, count=120):
    rng = random.Random(seed)
    nodes = [{"id": f"N{x}-{y}", "x": x, "y": y} for y in range(9) for x in range(11)]
    edges = []
    for n in nodes:
        x, y = n["x"], n["y"]
        for dx, dy in [(1, 0), (0, 1)]:
            if x + dx < 11 and y + dy < 9:
                b = f"N{x+dx}-{y+dy}"
                for a, z in [(n["id"], b), (b, n["id"])]:
                    edges.append({"a": a, "b": z, "km": 0.5, "minutes": 1.3 if y in (2, 6) else 1.8})
    facilities = [
        {"id": "F1", "name": "西片区综合补给站", "node": "N1-4", "open": 360, "close": 1200, "minutes": 8, "queue": 3, "kinds": list(KINDS)},
        {"id": "F2", "name": "东片区综合补给站", "node": "N9-4", "open": 360, "close": 1200, "minutes": 8, "queue": 5, "kinds": list(KINDS)},
    ]
    vehicles = []
    for i in range(24):
        kind = list(KINDS)[i % 3]
        vehicles.append({"id": f"V{i+1:02}", "name": f"环卫-{i+1:02}", "kind": kind,
            "node": "N5-7", "home": "N5-7", "capacity": 6 if kind != "hook" else 10,
            "water_capacity": 6 if kind == "sweeper" else 0,
            "load": 0, "water": 6 if kind == "sweeper" else 0,
            "shift_end": 1020, "enabled": True, "km": 0, "active": None})
    tasks = []
    names = ["社区收集点", "市场清运点", "商业街收集点", "园区收集点"]
    for i in range(count):
        kind = list(KINDS)[i % 3]
        x, y = rng.randrange(11), rng.randrange(9)
        start = f"N{x}-{y}"
        end = f"N{min(10,x+1) if x<10 else x-1}-{y}" if kind == "sweeper" else start
        early = 420 + rng.choice([0, 0, 15, 30, 60])
        tasks.append({"id": f"T{i+1:03}", "name": f"{('道路洗扫段' if kind=='sweeper' else names[i%4])} {i+1:03}",
            "kind": kind, "start": start, "end": end, "earliest": early,
            "deadline": early + rng.choice([75, 100, 140, 180]), "service": rng.randint(5, 11),
            "demand": round(rng.uniform(0.25, 0.8) if kind == "sweeper" else rng.uniform(0.7, 2.4), 2),
            "water": round(rng.uniform(0.8, 1.7), 2) if kind == "sweeper" else 0,
            "priority": rng.choice([1, 1, 2, 3]), "status": "pending", "locked_to": None,
            "completed_at": None})
    return {"name": "昆明环卫 · 示范片区（合成路网）", "seed": seed,
        "nodes": nodes, "edges": edges, "facilities": facilities, "vehicles": vehicles, "tasks": tasks}


def research_demo(seed=42,count=120):
    d=demo(seed,count)
    d['personnel']=[]
    for v in d['vehicles']:
        pid='P'+v['id'][1:]
        d['personnel'].append(dict(id=pid,name='模拟驾驶员'+pid,licenses=[v['kind']],skills=['sanitation'],shift_start=360,shift_end=1080,enabled=True))
        v.update(crew=pid,energy_capacity=100,energy=100,energy_per_km=.25,shift_start=360,weight=12)
    for t in d['tasks']:
        t.update(mandatory=True,skills=['sanitation'])
        if t['kind']=='collection':t.update(bin_capacity=5,fill=t['demand'],safety_margin=.1)
        if t['kind']=='sweeper':t.update(service_path=[t['start'],t['end']],reversible=True,forbidden_weather=[3])
    for f in d['facilities']:f.update(bays=3,resets=['load','water','energy'])
    return d


def validate(data):
    """Validate an imported *fresh* scenario, never trusting runtime state."""
    if not isinstance(data, dict):
        raise ValueError("场景必须是 JSON 对象")
    d = copy.deepcopy(data)
    for key in ('model_bundle','forecast','prediction_report','controller','handovers'):
        d.pop(key,None)
    for key, maximum in [("nodes", 5000), ("edges", 30000), ("vehicles", 200), ("tasks", 2000), ("facilities", 100)]:
        if not isinstance(d.get(key), list) or not 1 <= len(d[key]) <= maximum:
            raise ValueError(f"{key} 数量须在 1—{maximum} 之间")
        if any(not isinstance(row, dict) for row in d[key]):
            raise ValueError(f"{key} 中每条记录必须是对象")
    def number(row, key, low, high):
        v = row.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"{key} 应为 {low}—{high} 的有限数值")
    def identifiers(rows):
        ids = [r.get("id") for r in rows]
        if any(not isinstance(i, str) or not i or len(i)>50 for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("ID 必须是非空且不重复的短字符串")
        return set(ids)
    nodes = identifiers(d["nodes"])
    for n in d["nodes"]:
        number(n, "x", -10000, 10000); number(n, "y", -10000, 10000)
    pairs = set()
    for e in d["edges"]:
        if e.get("a") not in nodes or e.get("b") not in nodes or (e["a"], e["b"]) in pairs:
            raise ValueError("道路端点无效或有重复有向边")
        pairs.add((e["a"], e["b"]))
        number(e, "km", 0.001, 100); number(e, "minutes", 0.01, 600)
    vids = identifiers(d["vehicles"])
    identifiers(d["tasks"]); identifiers(d["facilities"])
    for v in d["vehicles"]:
        if v.get("kind") not in KINDS or v.get("home") not in nodes or v.get("node") not in nodes:
            raise ValueError("车辆类型或位置无效")
        number(v, "capacity", 0.1, 100); number(v, "water_capacity", 0, 100)
        number(v, "shift_end", 421, 1440)
        v.update(load=0, water=v["water_capacity"], enabled=True, active=None, km=0)
    for f in d["facilities"]:
        if f.get("node") not in nodes or not f.get("kinds") or any(k not in KINDS for k in f["kinds"]):
            raise ValueError("设施位置或兼容类型无效")
        for key, low, high in [("open", 0, 1440), ("close", 0, 1440), ("minutes", 0.1, 120), ("queue", 0, 240)]:
            number(f, key, low, high)
        if f["open"] >= f["close"]:
            raise ValueError("设施关闭时间必须晚于开放时间")
    for t in d["tasks"]:
        if t.get("kind") not in KINDS or t.get("start") not in nodes or t.get("end") not in nodes:
            raise ValueError("任务类型或端点无效")
        for key, low, high in [("earliest", 0, 1440), ("deadline", 0, 1440), ("service", 0.1, 180), ("demand", 0, 100), ("water", 0, 100), ("priority", 1, 3)]:
            number(t, key, low, high)
        if t["earliest"] >= t["deadline"]:
            raise ValueError("任务截止时间须晚于最早时间")
        if t["priority"] not in (1, 2, 3):
            raise ValueError("priority 只能为1、2、3")
        lock = t.get("locked_to")
        if lock is not None and lock not in vids:
            raise ValueError("锁定车辆不存在")
        t.update(status="pending", completed_at=None, locked_to=lock)
    for rows in [d["tasks"], d["vehicles"], d["facilities"]]:
        for r in rows:
            r["name"] = str(r.get("name", r["id"]))[:100]
    d["name"] = str(d.get("name", "导入场景"))[:100]
    from .schema_v2 import validate_extensions
    return validate_extensions(d)


def fresh(scenario):
    s = copy.deepcopy(scenario)
    s.update(now=420, revision=1, plan=None, draft=None, events=[], audit=[], history=[], congestion=None)
    return s
