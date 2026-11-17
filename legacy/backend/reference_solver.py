"""Small-instance CP-SAT reference model, independent of the heuristic.

Scope: fresh state, <=8 tasks/3 vehicles, integer-minute static road snapshot,
two visits per compatible facility/vehicle. Directed service variants, resource
recurrences, circuit connectivity, optional/mandatory coverage, facility cumulative
capacity and lexicographic service/cost objectives. This restricted deterministic
oracle is NOT a global optimum certificate for stochastic rolling RH-HMNASRP.
"""
import math
import time
from .model import Network, compatible, assign_crews, upgrade


def reference(s,budget=10):
    from ortools.sat.python import cp_model
    upgrade(s);assign_crews(s)
    ts=[t for t in s['tasks'] if t['status']=='pending'];vs=[v for v in s['vehicles'] if v['enabled']]
    if len(ts)>8 or len(vs)>3 or s.get('plan') or any(v['active'] for v in vs):
        raise ValueError('精确参照模型限初始状态、8任务/3车辆；请使用小实例')
    model=cp_model.CpModel();net=Network(s);cover={t['id']:[] for t in ts};cal={f['id']:[] for f in s['facilities']}
    first=[];cost=[];vars_by_vehicle={};start=time.perf_counter()
    for v in vs:
        nodes=[{'kind':'depot','start':v['node'],'end':v['home'],'service':0,'demand':0,'water':0,'energy':0}]
        for t in ts:
            if not compatible(s,v,t):continue
            path=t.get('service_path',[t['start']] if t['start']==t['end'] else [t['start'],t['end']])
            for direction in ([path,list(reversed(path))] if t.get('reversible') and len(path)>1 else [path]):
                pc=net.path_cost(direction,s['now'],v)
                if pc:nodes.append({**t,'kind':'task','id':t['id'],'start':direction[0],'end':direction[-1],
                                    'service':math.ceil(max(t['service'],pc[0])),'service_km':pc[1]})
        for f in s['facilities']:
            if f.get('closed') or v['kind'] not in f['kinds']:continue
            for repeat in range(2):nodes.append({**f,'kind':'facility','start':f['node'],'end':f['node'],'service':math.ceil(f['minutes']+f['queue']),
                'demand':0,'water':0,'energy':0})
        n=len(nodes);uses=[model.new_bool_var(f'{v["id"]}_u{i}') for i in range(n)]
        begin=[model.new_int_var(s['now'],1440,f'{v["id"]}_t{i}') for i in range(n)];model.add(begin[0]==s['now'])
        # Resource units scaled to hundredths; capacities floored, usage rounded up conservatively.
        capacities=[int(v['capacity']*100),int(v['water_capacity']*100),int(v.get('energy_capacity',100000)*100)]
        resources=[[model.new_int_var(0,cap,f'{v["id"]}_r{r}_{i}') for i in range(n)] for r,cap in enumerate(capacities)]
        model.add(resources[0][0]==round(v['load']*100));model.add(resources[1][0]==round((v['water_capacity']-v['water'])*100))
        model.add(resources[2][0]==round((v.get('energy_capacity',100000)-v.get('energy',v.get('energy_capacity',100000)))*100))
        arcs=[];arcvars={};time_return=model.new_int_var(s['now'],1440,f'{v["id"]}_return')
        person=next((p for p in s.get('personnel',[]) if p['id']==v.get('crew')),None)
        end=min(v['shift_end']+v.get('max_overtime',0),person['shift_end'] if person else 1440)
        model.add(time_return<=end)
        for i,a in enumerate(nodes):
            arcs.append((i,i,uses[i].Not()))
            if i:
                model.add_implication(uses[i],uses[0]);model.add(begin[i]+a['service']<=end).only_enforce_if(uses[i])
                earliest=a.get('earliest',a.get('open',s['now']));latest=a.get('hard_end',a.get('close',1440))
                model.add(begin[i]>=math.ceil(earliest)).only_enforce_if(uses[i]);model.add(begin[i]+a['service']<=math.floor(latest)).only_enforce_if(uses[i])
                if a['kind']=='task':
                    cover[a['id']].append(uses[i]);late=model.new_int_var(0,1440,'late')
                    model.add(late>=begin[i]+a['service']-math.floor(a['deadline'])).only_enforce_if(uses[i]);model.add(late==0).only_enforce_if(uses[i].Not())
                    first.append(a['priority']*late)
                else:
                    interval=model.new_optional_fixed_size_interval_var(begin[i],a['service'],uses[i],'bay');cal[a['id']].append(interval)
            for j,b in enumerate(nodes):
                if i==j:continue
                trip=net.path(a['end'] if i else v['node'],b['start'] if j else v['home'],s['now'],v)
                if trip is None:continue
                x=model.new_bool_var(f'{v["id"]}_x{i}_{j}');arcs.append((i,j,x));arcvars[(i,j)]=x
                travel=math.ceil(trip[0]);duration=a['service'] if i else 0
                if j:model.add(begin[j]>=begin[i]+duration+travel).only_enforce_if(x)
                else:
                    model.add(time_return>=begin[i]+duration+travel).only_enforce_if(x)
                    model.add(resources[0][i]==0).only_enforce_if(x)
                    model.add(resources[2][i]+math.ceil(trip[1]*v.get('energy_per_km',0)*100)<=capacities[2]).only_enforce_if(x)
                if j:
                    use=[math.ceil(b.get('demand',0)*100),math.ceil(b.get('water',0)*100),math.ceil(((trip[1]+b.get('service_km',0))*v.get('energy_per_km',0)+b.get('energy',0))*100)]
                    for r,key in enumerate(['load','water','energy']):
                        if b['kind']=='facility' and key in b.get('resets',['load','water','energy']):
                            model.add(resources[r][j]==0).only_enforce_if(x)
                            if r==2:model.add(resources[r][i]+use[r]<=capacities[r]).only_enforce_if(x)
                        else:model.add(resources[r][j]==resources[r][i]+use[r]).only_enforce_if(x)
                cost.append(math.ceil((trip[1]+b.get('service_km',0))*100)*x)
        model.add_circuit(arcs);vars_by_vehicle[v['id']]=(nodes,arcvars,begin,resources,time_return)
    for t in ts:
        drop=model.new_bool_var('drop_'+t['id']);model.add(sum(cover[t['id']])+drop==1)
        if t.get('mandatory',True):first.append(10000*t['priority']*drop)
    for f in s['facilities']:
        if cal[f['id']]:model.add_cumulative(cal[f['id']],[1]*len(cal[f['id']]),f.get('bays',999))
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.random_seed=42
    stages=[];solution=None
    for objective in (sum(first),sum(cost)):
        remaining=budget-(time.perf_counter()-start)
        if remaining<=0:break
        solver.parameters.max_time_in_seconds=remaining;model.minimize(objective);status=solver.solve(model)
        stages.append({'status':solver.status_name(status),'value':solver.objective_value,'bound':solver.best_objective_bound})
        if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):break
        solution={}
        for vid,(nodes,arcs,times,res,ret) in vars_by_vehicle.items():
            nexts={i:j for (i,j),x in arcs.items() if solver.value(x)};order=[];i=nexts.get(0,0)
            while i:
                order.append({'kind':nodes[i]['kind'],'id':nodes[i]['id'],'start':nodes[i]['start'],'end':nodes[i]['end'],'begin':solver.value(times[i])});i=nexts[i]
            solution[vid]=order
        if status!=cp_model.OPTIMAL:break
        model.add(objective<=round(solver.objective_value))
    return {'stages':stages,'routes':solution,'elapsed':time.perf_counter()-start,
        'scope':'小规模静态整数时间CP-SAT参照：每车每设施最多2访次；两层确定性目标；不是完整随机滚动模型全局最优证书'}
