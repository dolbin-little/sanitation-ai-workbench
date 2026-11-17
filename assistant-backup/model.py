"""Service-unit evaluator with explicit arcs, composite assets and facility calendars."""
import copy
import heapq
import math

DEFAULTS=dict(freeze=10,horizon=120,iterations=24,budget=12,seed=42,alpha=.9,
              theta_on=.65,theta_off=.35,cooldown=5,exact_every=8,drop_penalty=10000,
              energy_weight=.1,stability_weight=3,auto_control=False,forecast_enabled=True,risk_enabled=True)


def settings(s):
    return {**DEFAULTS,**s.get('settings',{})}


def upgrade(s):
    s['settings']=settings(s)
    for t in s['tasks']:
        t.setdefault('mandatory',True); t.setdefault('rule_deadline',t['deadline'])
        if t['start']!=t['end']:
            # Legacy demo roads have one explicit adjacent required arc.
            t.setdefault('service_path',[t['start'],t['end']])
            t.setdefault('reversible',False)
    s.setdefault('weather',0)
    s.setdefault('controller',{'level':'L0','latched':False,'last_trigger':-100,'trace':[]})


def compatible(s,v,t):
    if not v['enabled'] or t['kind']!=v['kind'] or (t.get('locked_to') and t['locked_to']!=v['id']): return False
    if s.get('weather',0) in t.get('forbidden_weather',[]): return False
    crew=v.get('crew')
    if s.get('personnel'):
        p=next((p for p in s['personnel'] if p['id']==crew),None)
        if not p or not p.get('enabled',True) or v['kind'] not in p.get('licenses',[]): return False
        if not set(t.get('skills',[])) <= set(p.get('skills',[])): return False
    elif t.get('skills'): return False
    return True


def planned_water(s,t):
    """Reserve calibrated upper water consumption; execution uses this conservative estimate."""
    if not settings(s)['forecast_enabled']:return t['water']
    pred=s.get('forecast',{}).get('tasks',{}).get(t['id'],{})
    return t['water']*max(1,pred.get('water',[1,1,1])[2])


def assign_crews(s):
    """Bipartite augmenting paths: each on-duty person assigned at most one vehicle."""
    people={p['id']:p for p in s.get('personnel',[]) if p.get('enabled',True) and p['shift_start']<=s['now']<p['shift_end']}
    if not s.get('personnel'): return
    owner={}; vs={v['id']:v for v in s['vehicles']}
    def match(vid,seen):
        for pid,p in people.items():
            if pid in seen or vs[vid]['kind'] not in p.get('licenses',[]): continue
            seen.add(pid)
            if pid not in owner or match(owner[pid],seen): owner[pid]=vid; return True
        return False
    # Preserve already executing crews; never rematch these.
    pinned=set()
    for v in s['vehicles']:
        if v.get('active') and v.get('crew') in people:
            owner[v['crew']]=v['id']; pinned.add(v['crew'])
    for v in s['vehicles']:
        if v['enabled'] and v['id'] not in owner.values(): match(v['id'],set(pinned))
    for v in s['vehicles']:
        v['crew']=next((p for p,vid in owner.items() if vid==v['id']),None)


class Network:
    def __init__(self,s):
        self.s=s; self.edges={(e['a'],e['b']):e for e in s['edges']}; self.adj={n['id']:[] for n in s['nodes']}; self.cache={}
        for e in s['edges']: self.adj[e['a']].append(e)

    def traversal(self,e,depart,v):
        if e.get('closed') or (e.get('allowed_kinds') and v['kind'] not in e['allowed_kinds']): return None
        if v.get('weight',0)>e.get('max_weight',math.inf): return None
        # Integrate time-dependent speed. Nonnegative speed yields FIFO arrival times.
        remaining=e['minutes']; at=depart
        while remaining>1e-8:
            if at>1440: return None
            factor=1.; boundaries=[]
            for seg in e.get('traffic',[]):
                if seg['start']<=at<seg['end']: factor*=seg['factor']; boundaries.append(seg['end'])
                elif seg['start']>at: boundaries.append(seg['start'])
            c=self.s.get('congestion')
            if c and at<c['until'] and (e['a'] in c['nodes'] or e['b'] in c['nodes']):
                factor*=c['factor']; boundaries.append(c['until'])
            boundary=min(boundaries,default=math.inf)
            duration=remaining*factor
            if at+duration<=boundary: at+=duration; remaining=0
            else: remaining-=(boundary-at)/factor; at=boundary
        return at-depart,e['km']

    def path_cost(self,path,at,v):
        begin=at; km=0
        for a,b in zip(path,path[1:]):
            e=self.edges.get((a,b)); cost=self.traversal(e,at,v) if e else None
            if cost is None: return None
            at+=cost[0]; km+=cost[1]
        return at-begin,km

    def path(self,a,b,at,v):
        key=(a,b,round(at,6),v['kind'],v.get('weight',0))
        if key in self.cache: return self.cache[key]
        dist={a:at}; heap=[(at,a,0,[a])]; result=None
        while heap:
            t,n,km,p=heapq.heappop(heap)
            if t>dist[n]+1e-8: continue
            if n==b: result=(t-at,km,p); break
            for e in self.adj[n]:
                cost=self.traversal(e,t,v)
                if cost and t+cost[0]<dist.get(e['b'],math.inf)-1e-8:
                    dist[e['b']]=t+cost[0]; heapq.heappush(heap,(dist[e['b']],e['b'],km+cost[1],p+[e['b']]))
        if len(self.cache)>80000: self.cache.clear()
        self.cache[key]=result
        return result


def slot(calendar,earliest,duration,bays):
    t=earliest
    for _ in range(len(calendar)*2+2):
        hits=[(a,b) for a,b in calendar if a<t+duration-1e-8 and b>t+1e-8]
        points=sorted({t,*[max(t,a) for a,b in hits]})
        conflict=next((p for p in points if sum(a<=p+1e-8<b for a,b in hits)>=bays),None)
        if conflict is None: return t
        t=min(b for a,b in hits if a<=conflict+1e-8<b)
    return math.inf


def prefixes(s):
    result={}; reserved=set(); lock=settings(s)['freeze']
    changed=s.get('needs_replan') and s.get('events') and s['events'][0]['kind'] in ('congestion','road_closed','facility_closed','weather')
    net=Network(s) if changed else None
    tasks={t['id']:t for t in s['tasks']}
    for v in s['vehicles']:
        if not v['enabled']: continue
        seq=[]
        for a in (s.get('plan') or {}).get('routes',{}).get(v['id'],[]):
            if a['depart']>s['now']+lock: break
            seq.append(copy.deepcopy(a))
        if changed:
            previous=v['active'];at=previous['finish'] if previous else s['now'];node=previous['end'] if previous else v['node']
            for a in seq:
                trip=net.path(node,a['start'],at,v)
                if trip is None:break # Leave infeasible commitment visible for shield/L4.
                duration=a['finish']-a['begin'];arrive=at+trip[0]
                task=tasks.get(a.get('task'));earliest=task['earliest'] if task else 0
                if a['kind']=='facility':
                    f=next((f for f in s['facilities'] if f['node']==a['start']),{})
                    earliest=f.get('open',0);arrive_for_service=arrive+f.get('queue',0)
                else:arrive_for_service=arrive
                begin=max(arrive_for_service,earliest)
                pc=net.path_cost(a['service_path'],begin,v)
                if pc is None:break
                a.update(source=node,depart=at,arrive=arrive,begin=begin,finish=begin+max(duration,pc[0]),path=trip[2],km=trip[1],service_km=pc[1])
                if a.get('deadline') is not None:a['late']=max(0,a['finish']-a['deadline'])
                if 'energy_after' in a:
                    previous_energy=previous.get('energy_after',v.get('energy',v.get('energy_capacity',1e9))) if previous else v.get('energy',v.get('energy_capacity',1e9))
                    a['energy_after']=previous_energy-(trip[1]+pc[1])*v.get('energy_per_km',0)-(task.get('energy',0) if task else 0)
                    if a['kind']=='facility' and 'energy' in f.get('resets',['load','water','energy']):a['energy_after']=v.get('energy_capacity',1e9)
                at=a['finish'];node=a['end'];previous=a
        result[v['id']]=seq
        reserved.update(a['task'] for a in seq if a.get('task'))
        if v['active'] and v['active'].get('task'): reserved.add(v['active']['task'])
    return result,reserved


class Evaluator:
    def __init__(self,s):
        self.s=s; self.net=Network(s); self.tasks={t['id']:t for t in s['tasks']}; self.vs={v['id']:v for v in s['vehicles'] if v['enabled']}
        self.prefix,self.reserved=prefixes(s); self.config=settings(s)
        self.pending={t['id'] for t in s['tasks'] if t['status']=='pending' and t['id'] not in self.reserved}
        self.eligible={i for i in self.pending if self.tasks[i]['earliest']<=s['now']+self.config['horizon']}
        self.previous={a['task']:vid for vid,seq in (s.get('plan') or {}).get('routes',{}).items() for a in seq if a.get('task')}
        self.calendar={f['id']:[] for f in s['facilities']}
        for v in s['vehicles']:
            for a in ([v['active']] if v['active'] else [])+self.prefix.get(v['id'],[]):
                if a['kind']=='facility':
                    f=next((f for f in s['facilities'] if f['node']==a['start']),None)
                    if f: self.calendar[f['id']].append((a['begin'],a['finish']))

    def route(self,vid,ids,calendar=None):
        v=self.vs[vid]; s=self.s; crew=next((p for p in s.get('personnel',[]) if p['id']==v.get('crew')),None)
        if s.get('personnel') and not crew and (ids or v['active'] or v['node']!=v['home'] or v['load']>0):return None
        clock=max(s['now'],v.get('shift_start',s['now']),crew['shift_start'] if crew else 0)
        end_shift=min(v['shift_end']+v.get('max_overtime',0),crew['shift_end'] if crew else 1440)
        node=v['node']; load=v['load']; water=v['water']; energy=v.get('energy',v.get('energy_capacity',1e9))
        steps=copy.deepcopy(self.prefix[vid]); cal=copy.deepcopy(self.calendar if calendar is None else calendar)
        fixed=([v['active']] if v['active'] else [])+steps
        if fixed:
            a=fixed[-1]; node=a['end']; clock=a['finish']; load=a['load_after']; water=a['water_after']; energy=a.get('energy_after',energy)
        def move(destination,kind,label,duration=0,earliest=0,close=1440,task=None,path=None,facility=None):
            nonlocal node,clock,load,water,energy
            trip=self.net.path(node,destination,clock,v)
            if trip is None:return False
            arrival=clock+trip[0]; begin=max(arrival,earliest)
            if facility:
                begin=slot(cal[facility['id']],begin+facility.get('queue',0),duration,facility.get('bays',999))
            pc=self.net.path_cost(path,begin,v) if path else (0,0)
            if pc is None:return False
            finish=begin+max(duration,pc[0]); km=trip[1]+pc[1]
            after_energy=energy-km*v.get('energy_per_km',0)-(task.get('energy',0) if task else 0)
            if after_energy < -1e-8 or finish>end_shift+1e-8 or finish>close+1e-8:return False
            newload=load+(task['demand'] if task else 0); newwater=water-(planned_water(s,task) if task else 0)
            if newload>v['capacity']+1e-8 or newwater< -1e-8:return False
            if facility:
                reset=facility.get('resets',['load','water','energy'])
                if 'load' in reset:newload=0
                if 'water' in reset:newwater=v['water_capacity']
                if 'energy' in reset:after_energy=v.get('energy_capacity',1e9)
                cal[facility['id']].append((begin,finish))
            dl=task['deadline'] if task else None
            if task and self.config['forecast_enabled']:
                dl=min(dl,s.get('forecast',{}).get('tasks',{}).get(task['id'],{}).get('deadline',dl))
            steps.append(dict(kind=kind,label=label,task=task['id'] if task else None,source=node,start=destination,
                end=path[-1] if path else destination,depart=clock,arrive=arrival,begin=begin,finish=finish,
                path=trip[2],service_path=path or [destination],km=trip[1],service_km=pc[1],
                load_after=newload,water_after=max(0,newwater),energy_after=max(0,after_energy),
                deadline=dl,late=max(0,finish-dl) if dl is not None else 0,facility=facility['id'] if facility else None,
                water_reserved=planned_water(s,task) if task else 0))
            node=steps[-1]['end'];clock=finish;load=newload;water=max(0,newwater);energy=max(0,after_energy)
            return True
        def replenish(needs):
            nonlocal node,clock,load,water,energy,steps,cal
            options=[]
            for f in s['facilities']:
                if f.get('closed') or v['kind'] not in f['kinds'] or not set(needs)<=set(f.get('resets',['load','water','energy'])):continue
                trip=self.net.path(node,f['node'],clock,v)
                if trip:
                    begin=slot(cal[f['id']],max(clock+trip[0],f['open'])+f.get('queue',0),f['minutes'],f.get('bays',999))
                    options.append((begin+f['minutes'],f['id'],f))
            for _,__,f in sorted(options):
                if move(f['node'],'facility',f['name'],f['minutes'],f['open'],f['close'],facility=f):return True
            return False
        for tid in ids:
            t=self.tasks[tid]
            if not compatible(s,v,t):return None
            demand_water=planned_water(s,t)
            if t['demand']>v['capacity'] or demand_water>v['water_capacity']:return None
            needs=[]
            if load+t['demand']>v['capacity']:needs.append('load')
            if water<demand_water:needs.append('water')
            if energy<v.get('energy_capacity',0)*.25:needs.append('energy')
            if needs and not replenish(needs):return None
            paths=[t.get('service_path',[t['start']] if t['start']==t['end'] else [t['start'],t['end']])]
            if t.get('reversible') and len(paths[0])>1:paths.append(list(reversed(paths[0])))
            choices=[]
            for path in paths:
                trip=self.net.path(node,path[0],clock,v)
                if trip and self.net.path_cost(path,max(clock+trip[0],t['earliest']),v):choices.append((trip[0],path))
            success=False
            for _,path in sorted(choices):
                if move(path[0],'task',t['name'],t['service'],t['earliest'],t.get('hard_end',1440),task=t,path=path):success=True;break
            if not success:return None
        if ids or steps or v['active'] or node!=v['home'] or load:
            if load>0 and not replenish(['load']):return None
            if not move(v['home'],'depot','返回车场'):return None
        return steps

    def build(self,assignment):
        routes={}; cal=copy.deepcopy(self.calendar)
        for vid in self.vs:
            seq=self.route(vid,assignment.get(vid,[]),cal)
            if seq is None:return None
            routes[vid]=seq
            for a in seq[len(self.prefix[vid]):]:
                if a.get('facility'):cal[a['facility']].append((a['begin'],a['finish']))
        return routes

    def objective(self,routes,assignment):
        from .risk import assess
        covered={i for ids in assignment.values() for i in ids}
        missing=self.eligible-covered
        risk_state=self.s if self.config['forecast_enabled'] else {**self.s,'forecast':{}}
        risk=assess(risk_state,routes,self.tasks,self.config)
        f1=sum(self.config['drop_penalty']*self.tasks[i]['priority'] for i in missing if self.tasks[i].get('mandatory',True))+risk['expected_late']
        km=sum(a['km']+a['service_km'] for seq in routes.values() for a in seq)
        changes=sum(self.previous.get(i,vid)!=vid for vid,ids in assignment.items() for i in ids)
        old_orders={vid:[a['task'] for a in seq if a.get('task')] for vid,seq in (self.s.get('plan') or {}).get('routes',{}).items()}
        old_edges={(vid,a,b) for vid,seq in old_orders.items() for a,b in zip(seq,seq[1:])}
        new_edges={(vid,a,b) for vid,ids in assignment.items() for a,b in zip(ids,ids[1:])}
        stability=changes+.5*len(old_edges.symmetric_difference(new_edges)) if old_edges else changes
        hours=sum(max(0,seq[-1]['finish']-self.s['now'])/60 for seq in routes.values() if seq)
        energy=sum((a['km']+a['service_km'])*self.vs[vid].get('energy_per_km',.25) for vid,seq in routes.items() for a in seq)
        optional=sum(self.tasks[i].get('benefit',0) for i in covered if not self.tasks[i].get('mandatory',True))
        cost=km+hours*2+sum(bool(ids) for ids in assignment.values())*5+self.config['energy_weight']*energy+self.config['stability_weight']*stability-optional
        return (round(f1,5),round(risk['cvar'],5) if self.config['risk_enabled'] else 0,round(cost,5)),risk
