"""Feasible insertion + bounded relocate search on a directed service-unit graph.

This is an explainable prototype heuristic, not H-ALNS / a global-optimum claim.
All times are minutes since midnight; task deadlines are SOFT completion deadlines.
Vehicle shift end, compatibility, capacities and facility hours are HARD constraints.
"""
import copy
import heapq
import time


class Roads:
    def __init__(self, state):
        self.adj = {n["id"]: [] for n in state["nodes"]}
        self.cache = {}
        congestion = state.get("congestion")
        for e in state["edges"]:
            factor = 1
            if congestion and state["now"] < congestion["until"]:
                # Snapshot assumption: factor remains constant over this planning horizon.
                if e["a"] in congestion["nodes"] or e["b"] in congestion["nodes"]:
                    factor = congestion["factor"]
            self.adj[e["a"]].append((e["b"], e["minutes"]*factor, e["km"]))

    def get(self, source, target):
        if source not in self.cache:
            distances = {source: (0, 0, [source])}
            heap = [(0, source)]
            while heap:
                minutes, a = heapq.heappop(heap)
                if minutes > distances[a][0]:
                    continue
                for b, dur, km in self.adj[a]:
                    if minutes + dur < distances.get(b, (float("inf"),))[0]:
                        distances[b] = (minutes+dur, distances[a][1]+km, distances[a][2]+[b])
                        heapq.heappush(heap, (minutes+dur, b))
            self.cache[source] = distances
        return self.cache[source].get(target)


def origins(state, freeze=True):
    """Active action is immutable; preserve announced queue prefix for 10 min."""
    result, reserved = {}, set()
    old = (state.get("plan") or {}).get("routes", {})
    for v in state["vehicles"]:
        if not v["enabled"]:
            continue
        o = dict(node=v["node"], time=state["now"], load=v["load"], water=v["water"], prefix=[])
        if v["active"]:
            a = v["active"]
            o.update(node=a["end"], time=a["finish"], load=a["load_after"], water=a["water_after"])
            if a.get("task"):
                reserved.add(a["task"])
        if freeze:
            for a in old.get(v["id"], []):
                if a["depart"] > state["now"] + 10:
                    break
                o["prefix"].append(copy.deepcopy(a))
                o.update(node=a["end"], time=a["finish"], load=a["load_after"], water=a["water_after"])
                if a.get("task"):
                    reserved.add(a["task"])
        result[v["id"]] = o
    return result, reserved


def evaluate(state, roads, vehicle, origin, ids, tasks):
    node, clock, load, water = origin["node"], origin["time"], origin["load"], origin["water"]
    steps = copy.deepcopy(origin["prefix"])
    def move(end, kind, label, service=0, earliest=0, task=None, deadline=None, demand=0, consume=0, path_end=None, close=None):
        nonlocal node, clock, load, water
        trip = roads.get(node, end)
        if trip is None:
            return False
        travel, km, path = trip
        arrive = clock + travel
        begin = max(arrive, earliest)
        service_km, service_path = 0, [end]
        if path_end and path_end != end:
            edge = roads.get(end, path_end)
            if edge is None:
                return False
            service_km, service_path = edge[1], edge[2]
            service = max(service, edge[0])
        finish = begin + service
        if finish > vehicle["shift_end"] + 1e-8 or (close is not None and finish > close):
            return False
        new_load = 0 if kind == "facility" else load + demand
        new_water = vehicle["water_capacity"] if kind == "facility" else water - consume
        if new_load > vehicle["capacity"]+1e-8 or new_water < -1e-8:
            return False
        steps.append(dict(kind=kind, task=task, label=label, source=node, start=end, end=path_end or end,
            depart=clock, arrive=arrive, begin=begin, finish=finish, path=path, service_path=service_path,
            km=km, service_km=service_km, load_after=new_load, water_after=max(0,new_water),
            deadline=deadline, late=max(0,finish-deadline) if deadline is not None else 0))
        node, clock, load, water = path_end or end, finish, new_load, max(0,new_water)
        return True
    def replenish():
        choices = []
        for f in state["facilities"]:
            route = roads.get(node, f["node"])
            if vehicle["kind"] in f["kinds"] and route:
                finish = max(clock+route[0], f["open"]) + f["minutes"] + f["queue"]
                if finish <= min(f["close"], vehicle["shift_end"]):
                    choices.append((finish, f["id"], f))
        if not choices:
            return False
        f = min(choices)[2]
        return move(f["node"], "facility", f["name"], f["minutes"]+f["queue"], f["open"], close=f["close"])
    for tid in ids:
        t = tasks[tid]
        if t["kind"] != vehicle["kind"] or (t.get("locked_to") and t["locked_to"] != vehicle["id"]):
            return None
        if t["demand"] > vehicle["capacity"] or t["water"] > vehicle["water_capacity"]:
            return None
        if load+t["demand"] > vehicle["capacity"]+1e-8 or water < t["water"]-1e-8:
            if not replenish():
                return None
        if not move(t["start"], "task", t["name"], t["service"], t["earliest"], tid, t["deadline"],
                    t["demand"], t["water"], t["end"]):
            return None
    if ids or steps or vehicle["active"]:
        if load > 0 and not replenish():
            return None
        if not move(vehicle["home"], "depot", "返回车场"):
            return None
    elif node != vehicle["home"] or load > 0:
        if load > 0 and not replenish():
            return None
        if not move(vehicle["home"], "depot", "返回车场"):
            return None
    return steps


def route_score(steps, tasks, vehicle_id, previous):
    late = sum(a["late"] * tasks[a["task"]]["priority"] for a in steps if a.get("task"))
    km = sum(a["km"] for a in steps)
    changes = sum(1 for a in steps if a.get("task") in previous and previous[a["task"]] != vehicle_id)
    return late, km + changes*3


def solve(state, strategy="adaptive", improve=True):
    if strategy not in ("adaptive", "nearest", "fixed"):
        raise ValueError("未知调度策略")
    start_time = time.perf_counter()
    roads = Roads(state)
    bases, reserved = origins(state)
    tasks = {t["id"]: t for t in state["tasks"]}
    vs = {v["id"]: v for v in state["vehicles"] if v["enabled"]}
    previous = {a["task"]: vid for vid, seq in (state.get("plan") or {}).get("routes", {}).items() for a in seq if a.get("task")}
    ids = {v: [] for v in vs}
    routes = {v: evaluate(state, roads, vs[v], bases[v], [], tasks) or bases[v]["prefix"] for v in vs}
    pending = [t for t in state["tasks"] if t["status"] == "pending" and t["id"] not in reserved]
    pending.sort(key=(lambda t: t["id"]) if strategy == "fixed" else (lambda t: (-t["priority"], t["deadline"], t["id"])))
    unresolved = []
    for t in pending:
        candidates = []
        for vid, v in vs.items():
            if t["kind"] != v["kind"] or (t.get("locked_to") and t["locked_to"] != vid):
                continue
            positions = range(len(ids[vid])+1) if strategy == "adaptive" else [len(ids[vid])]
            oldscore = route_score(routes[vid], tasks, vid, previous)
            for pos in positions:
                trial = ids[vid][:pos]+[t["id"]]+ids[vid][pos:]
                steps = evaluate(state, roads, v, bases[vid], trial, tasks)
                if steps is None:
                    continue
                score = route_score(steps, tasks, vid, previous)
                delta = (score[0]-oldscore[0], score[1]-oldscore[1])
                if strategy == "nearest":
                    last = tasks[ids[vid][-1]]["end"] if ids[vid] else bases[vid]["node"]
                    delta = (roads.get(last, t["start"])[0], score[0])
                elif strategy == "fixed":
                    delta = (len(ids[vid]), vid)
                candidates.append((delta, vid, pos, steps))
        if not candidates:
            unresolved.append({"id": t["id"], "reason": "车型/锁定、容量、设施开放时间、路网连通性或班次约束下无可行插入"})
            continue
        _, vid, pos, steps = min(candidates, key=lambda z: (z[0], z[1], z[2]))
        ids[vid].insert(pos, t["id"])
        routes[vid] = steps
    # Bounded inter/intra-route relocate improvement; preserve frozen prefix and explicit locks.
    improvements = 0
    if strategy == "adaptive" and improve:
        trials = 0
        for source in vs:
            for tid in list(ids[source]):
                if trials >= 700:
                    break
                source_trial = [i for i in ids[source] if i != tid]
                stripped = evaluate(state, roads, vs[source], bases[source], source_trial, tasks)
                if stripped is None:
                    continue
                found = False
                for dest in vs:
                    if dest == source or vs[dest]["kind"] != tasks[tid]["kind"]:
                        continue
                    before1 = route_score(routes[source], tasks, source, previous)
                    before2 = route_score(routes[dest], tasks, dest, previous)
                    before = tuple(a+b for a,b in zip(before1,before2))
                    for pos in range(len(ids[dest])+1):
                        trials += 1
                        test = ids[dest][:pos]+[tid]+ids[dest][pos:]
                        seq = evaluate(state, roads, vs[dest], bases[dest], test, tasks)
                        if seq is None:
                            continue
                        after = tuple(a+b for a,b in zip(route_score(stripped,tasks,source,previous), route_score(seq,tasks,dest,previous)))
                        if after < (before[0]-1e-7, before[1]) or (abs(after[0]-before[0])<1e-7 and after[1] < before[1]-1e-7):
                            ids[source], ids[dest] = source_trial, test
                            routes[source], routes[dest] = stripped, seq
                            improvements += 1
                            found = True
                            break
                    if found or trials >= 700:
                        break
    all_steps = [a for seq in routes.values() for a in seq] + [v["active"] for v in state["vehicles"] if v["active"]]
    scheduled = [a for a in all_steps if a.get("task")]
    changed = [{"task": a["task"], "from": previous[a["task"]], "to": vid} for vid, seq in routes.items() for a in seq
               if a.get("task") in previous and previous[a["task"]] != vid]
    metric = {"scheduled": len(scheduled), "unassigned": len(unresolved),
        "late_tasks": sum(a["late"]>0 for a in scheduled), "late_minutes": round(sum(a["late"] for a in scheduled),1),
        "deadhead_km": round(sum(a["km"] for a in all_steps),2), "service_km": round(sum(a["service_km"] for a in all_steps),2),
        "changes": len(changed), "vehicles_used": sum(bool(seq) for seq in routes.values()),
        "runtime_ms": round((time.perf_counter()-start_time)*1000,1)}
    return {"strategy": strategy, "base_revision": state["revision"], "at": state["now"], "routes": routes,
        "unassigned": unresolved, "metrics": metric, "changes": changed, "improvements": improvements,
        "frozen": sorted(reserved), "explanation": "按优先级和截止时间插入任务；先减少加权逾期，再减少空驶及改派；执行中动作和未来10分钟已承诺前缀保持不变。"}
