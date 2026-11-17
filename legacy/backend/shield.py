"""Independent plan replay; does not trust solver resource/time/metric fields."""
import math
from collections import Counter
from .model import Network, compatible, prefixes, planned_water


def inspect(s,plan):
    errors=[]; tasks={t['id']:t for t in s['tasks']}; net=Network(s); prefix,reserved=prefixes(s)
    seen=[]; calendars={};tol=1e-5
    routes=plan.get('routes',{})
    if set(routes)-{v['id'] for v in s['vehicles']}:errors.append('未知车辆')
    for v in s['vehicles']:
        seq=routes.get(v['id'],[])
        if not v['enabled'] and seq:errors.append(v['id']+':故障车辆收到任务')
        if seq[:len(prefix.get(v['id'],[]))]!=prefix.get(v['id'],[]):errors.append(v['id']+':冻结前缀改变')
        node=v['node'];time=s['now'];load=v['load'];water=v['water'];energy=v.get('energy',v.get('energy_capacity',1e9))
        if v['active']:
            a=v['active'];node=a['end'];time=a['finish'];load=a['load_after'];water=a['water_after'];energy=a.get('energy_after',energy)
            if a.get('task'):seen.append(a['task'])
            if a['kind']=='facility':calendars.setdefault(a.get('facility') or a['start'],[]).append((a['begin'],a['finish']))
        person=next((p for p in s.get('personnel',[]) if p['id']==v.get('crew')),None)
        if s.get('personnel') and seq and (not person or not person.get('enabled',True) or v['kind'] not in person.get('licenses',[])):errors.append(v['id']+':缺少合法当班驾驶员')
        for a in seq:
            tag=f"{v['id']}:{a.get('task') or a.get('kind')}"
            nums=['depart','arrive','begin','finish','load_after','water_after','km','service_km']
            if any(not isinstance(a.get(k),(int,float)) or not math.isfinite(a[k]) for k in nums):errors.append(tag+':非有限字段');continue
            if a['source']!=node or a['depart']<time-tol or a['arrive']<a['depart']-tol or a['begin']<a['arrive']-tol or a['finish']<a['begin']-tol:errors.append(tag+':时空不连续')
            path=a.get('path',[]);service_path=a.get('service_path',[])
            if not path or path[0]!=node or path[-1]!=a['start'] or not service_path or service_path[0]!=a['start'] or service_path[-1]!=a['end']:
                errors.append(tag+':路径端点错误');continue
            trip=net.path_cost(path,a['depart'],v);work=net.path_cost(service_path,a['begin'],v)
            if trip is None or work is None:errors.append(tag+':道路封闭/通行权限/作业方向违规');continue
            if a['arrive']+tol<a['depart']+trip[0] or abs(a['km']-trip[1])>tol or abs(a['service_km']-work[1])>tol:errors.append(tag+':行驶时间/距离不符')
            energy-=(trip[1]+work[1])*v.get('energy_per_km',0)
            if energy < -tol:errors.append(tag+':途中能量耗尽')
            if a.get('task'):
                tid=a['task'];seen.append(tid);t=tasks.get(tid)
                if not t:errors.append(tag+':未知任务');continue
                if t['status']=='done' or not compatible(s,v,t):errors.append(tag+':任务状态/复合资产不兼容')
                required=t.get('service_path',[t['start']] if t['start']==t['end'] else [t['start'],t['end']])
                if service_path!=required and not (t.get('reversible') and service_path==list(reversed(required))):errors.append(tag+':未覆盖指定服务弧')
                if a['begin']<t['earliest']-tol or a['finish']>t.get('hard_end',1440)+tol or a['finish']-a['begin']+tol<max(t['service'],work[0]):errors.append(tag+':服务时间或硬窗违规')
                required_water=planned_water(s,t)
                # Exact frozen action equality was checked above. Its committed resource estimate
                # remains fixed when newer forecasts arrive; changed suffix uses the new envelope.
                frozen_action=any(a==old for old in prefix.get(v['id'],[]))
                if frozen_action:required_water=a.get('water_reserved',t['water'])
                load+=t['demand'];water-=required_water;energy-=t.get('energy',0)
            elif a['kind']=='facility':
                f=next((f for f in s['facilities'] if f['node']==a['start'] and (not a.get('facility') or f['id']==a['facility'])),None)
                if not f:errors.append(tag+':未知设施');continue
                if f.get('closed') or v['kind'] not in f['kinds'] or a['begin']<f['open']-tol or a['finish']>f['close']+tol or a['finish']-a['begin']+tol<f['minutes']:errors.append(tag+':设施约束违规')
                reset=f.get('resets',['load','water','energy'])
                if 'load' in reset:load=0
                if 'water' in reset:water=v['water_capacity']
                if 'energy' in reset:energy=v.get('energy_capacity',1e9)
                calendars.setdefault(f['id'],[]).append((a['begin'],a['finish']))
            elif a['kind']!='depot':errors.append(tag+':未知动作')
            if load>v['capacity']+tol or water< -tol or energy< -tol:errors.append(tag+':资源越界')
            if abs(load-a['load_after'])>tol or abs(water-a['water_after'])>tol or ('energy_after' in a and abs(energy-a['energy_after'])>tol):errors.append(tag+':资源状态伪造')
            limit=min(v['shift_end']+v.get('max_overtime',0),person['shift_end'] if person else 1440)
            if a['finish']>limit+tol or a['depart']<max(v.get('shift_start',0),person['shift_start'] if person else 0)-tol:errors.append(tag+':人员/车辆班次违规')
            node=a['end'];time=a['finish']
        if v['enabled'] and (seq or v['active'] or load>0 or node!=v['home']) and (node!=v['home'] or load>tol):errors.append(v['id']+':未卸载返场')
    for f in s['facilities']:
        events=[]
        for a,b in calendars.get(f['id'],[])+calendars.get(f['node'],[]):events.extend([(a,1),(b,-1)])
        count=0
        for _,delta in sorted(events):
            count+=delta
            if count>f.get('bays',999):errors.append(f['id']+':泊位重叠');break
    counts=Counter(seen)
    if any(n>1 for n in counts.values()):errors.append('任务重复执行')
    unfinished={t['id'] for t in s['tasks'] if t['status']!='done'}
    unassigned=[u['id'] for u in plan.get('unassigned',[])];deferred=plan.get('deferred',[])
    accounted=seen+unassigned+deferred
    if set(accounted)!=unfinished or len(accounted)!=len(set(accounted)):errors.append('任务覆盖账目不完整/重复')
    crews=[v.get('crew') for v in s['vehicles'] if v['enabled'] and routes.get(v['id']) and v.get('crew')]
    if len(crews)!=len(set(crews)):errors.append('人员同时绑定多辆作业车')
    return {'passed':not errors,'errors':errors,'checked_tasks':len(seen),'checked_at':s['now'],'revision':s['revision']}
