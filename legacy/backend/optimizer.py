"""H-ALNS with adaptive destroy/repair, bounded exact repair, and potential game."""
import copy
import itertools
import math
import random
import time
from .model import Evaluator, compatible, incompatibility, settings, upgrade, assign_crews
from .shield import inspect


def candidate(ev,a):
    routes=ev.build(a)
    if routes is None:return None
    obj,risk=ev.objective(routes,a)
    return {'assignment':a,'routes':routes,'objective':obj,'risk':risk}


def insertions(ev,a,tid,limit=3):
    choices=[];t=ev.tasks[tid]
    def record(vid,reason=None,feasible=False):
        key=(tid,vid)
        if key not in ev.decision_evidence and len(ev.decision_evidence)>=12000:ev.evidence_truncated=True;return
        r=ev.decision_evidence.setdefault(key,{'task':tid,'vehicle':vid,'tested':0,'feasible':0,'rejections':{}})
        r['tested']+=1;r['feasible']+=int(feasible)
        if reason:r['rejections'][reason]=r['rejections'].get(reason,0)+1
    for v in ev.s['vehicles']:
        if not v['enabled']:record(v['id'],'车辆故障或禁用，未进入插入候选')
    # Screen with single route checks, then compare full calendar-aware schedules.
    for vid,v in ev.vs.items():
        if not compatible(ev.s,v,t):record(vid,incompatibility(ev.s,v,t));continue
        for pos in range(len(a[vid])+1):
            seq=a[vid][:pos]+[tid]+a[vid][pos:]
            steps=ev.route(vid,seq)
            if steps is None:record(vid,ev.last_failure or '当前插入路线不可行');continue
            record(vid,feasible=True)
            local=(sum(x['late']*ev.tasks[x['task']]['priority'] for x in steps if x.get('task')),
                   sum(x['km'] for x in steps))
            choices.append((local,vid,pos))
    result=[]
    for _,vid,pos in sorted(choices)[:max(limit,3)]:
        b=copy.deepcopy(a);b[vid].insert(pos,tid);c=candidate(ev,b)
        if c:result.append(c)
    return sorted(result,key=lambda c:c['objective'])


def repair(ev,a,removed,rng,method='regret2',deadline=math.inf):
    pool=set(removed)
    while pool and time.perf_counter()<deadline:
        # Bounded regret pool ensures interactive latency; mandatory and urgent tasks first.
        ordered=sorted(pool,key=lambda i:(not ev.tasks[i].get('mandatory',True),-ev.tasks[i]['priority'],ev.tasks[i]['deadline']))
        batch=ordered[:3] if method!='greedy' else ordered[:1]
        options=[]
        for tid in batch:
            cs=insertions(ev,a,tid,3 if method=='regret3' else 2)
            if cs:
                best=cs[0];other=cs[min(len(cs)-1,2 if method=='regret3' else 1)]
                # Lexicographic regret vector, not mixed units.
                regret=tuple(x-y for x,y in zip(other['objective'],best['objective'])) if len(cs)>1 else (1e12,0,0)
                options.append((regret,tid,best))
            else:pool.remove(tid)
        if not options:continue
        _,tid,best=max(options,key=lambda x:(x[0],x[1]));pool.remove(tid)
        if not ev.tasks[tid].get('mandatory',True):
            current=candidate(ev,a)
            if current and best['objective']>=current['objective']:continue
        a=best['assignment']
    return a


def destroy(ev,a,operator,rng):
    allids=[i for ids in a.values() for i in ids]
    if not allids:return copy.deepcopy(a),[]
    n=min(len(allids),max(2,min(7,len(allids)//8)))
    seed=rng.choice(allids);nodes={n['id']:n for n in ev.s['nodes']};origin=nodes[ev.tasks[seed]['start']]
    if operator=='worst':
        cs=candidate(ev,a);late={x['task']:x['late'] for seq in cs['routes'].values() for x in seq if x.get('task')}
        ranked=sorted(allids,key=lambda i:late.get(i,0),reverse=True)
    elif operator in ('related','cluster'):
        ranked=sorted(allids,key=lambda i:abs(nodes[ev.tasks[i]['start']]['x']-origin['x'])+abs(nodes[ev.tasks[i]['start']]['y']-origin['y'])+(abs(ev.tasks[i]['deadline']-ev.tasks[seed]['deadline'])/60 if operator=='related' else 0))
    elif operator=='route':ranked=list(rng.choice([ids for ids in a.values() if ids]));n=min(10,len(ranked))
    elif operator=='facility':
        cs=candidate(ev,a);vid=max(cs['routes'],key=lambda v:sum(x['kind']=='facility' for x in cs['routes'][v]));ranked=list(a[vid])
    else:ranked=rng.sample(allids,len(allids))
    removed=ranked[:n];b={v:[i for i in ids if i not in removed] for v,ids in a.items()}
    return b,removed


def exact_repair(ev,current,deadline,max_tasks=3):
    """CP-SAT exact selection over enumerated restricted route columns.

    Neighborhood fixes all other task orders. CP-SAT optimality is only for these
    columns; facility scheduling interactions are checked again globally.
    """
    from ortools.sat.python import cp_model
    a=current['assignment'];available=[i for ids in a.values() for i in ids]
    available+=sorted(ev.eligible-set(available))
    if not available:return current,{'status':'EMPTY','columns':0}
    selected=sorted(available,key=lambda i:(-ev.tasks[i]['priority'],ev.tasks[i]['deadline']))[:max_tasks]
    base={v:[i for i in ids if i not in selected] for v,ids in a.items()}
    affected=[v for v in ev.vs if any(compatible(ev.s,ev.vs[v],ev.tasks[i]) for i in selected)][:6]
    columns=[]
    for vid in affected:
        for count in range(len(selected)+1):
            for sub in itertools.permutations(selected,count):
                # Enumerate contiguous block insertions plus original route column.
                for pos in range(len(base[vid])+1):
                    seq=base[vid][:pos]+list(sub)+base[vid][pos:]
                    steps=ev.route(vid,seq)
                    if steps is not None:
                        local={v:[] for v in ev.vs};local[vid]=seq
                        obj,_=ev.objective({vid:steps},local)
                        columns.append((vid,seq,set(sub),tuple(int(round(x*100)) for x in obj)))
                if time.perf_counter()>deadline:break
            if time.perf_counter()>deadline:break
    model=cp_model.CpModel();xs=[model.new_bool_var('c'+str(i)) for i in range(len(columns))]
    for vid in affected:model.add(sum(xs[i] for i,c in enumerate(columns) if c[0]==vid)==1)
    drops=[]
    for tid in selected:
        d=model.new_bool_var('drop_'+tid);drops.append(d)
        model.add(sum(xs[i] for i,c in enumerate(columns) if tid in c[2])+d==1)
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.random_seed=42
    status=None;values=None;levels=[]
    # Column objectives include missing penalties; common constant per selected vehicle cancels.
    for level in range(3):
        remain=deadline-time.perf_counter()
        if remain<=0:break
        objective=sum(x*c[3][level] for x,c in zip(xs,columns))
        model.minimize(objective);solver.parameters.max_time_in_seconds=min(1.,remain)
        status=solver.solve(model);levels.append(solver.status_name(status))
        if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):break
        values=[solver.value(x) for x in xs]
        model.add(objective<=int(round(solver.objective_value)))
        if status!=cp_model.OPTIMAL:break
    b=copy.deepcopy(base)
    if values:
        for on,c in zip(values,columns):
            if on:b[c[0]]=c[1]
        proposal=candidate(ev,b)
        if proposal and proposal['objective']<current['objective']:current=proposal
    return current,{'status':levels[-1] if levels else 'TIME_LIMIT','levels':levels,'columns':len(columns),'tasks':selected,
                    'scope':'枚举路线列上的受限邻域最优；不代表完整路由全局最优'}


def local_moves(ev,a,rng):
    vs=[v for v in a if a[v]]
    for source in vs:
        ids=a[source]
        if len(ids)>1:
            i=rng.randrange(len(ids)-1);j=min(len(ids),i+3);b=copy.deepcopy(a);b[source][i:j]=reversed(b[source][i:j]);yield '2-opt',b
        for tid in ids[:3]:
            for dest in list(ev.vs):
                if dest==source or not compatible(ev.s,ev.vs[dest],ev.tasks[tid]):continue
                b=copy.deepcopy(a);b[source].remove(tid);b[dest].append(tid);yield 'transfer',b
                if a[dest]:
                    other=a[dest][-1]
                    b=copy.deepcopy(a);b[source][b[source].index(tid)]=other;b[dest][-1]=tid;yield 'swap',b


def package(ev,c,strategy,started,trace,extra=None):
    routes=c['routes'];allsteps=[x for seq in routes.values() for x in seq]+[v['active'] for v in ev.s['vehicles'] if v['active']]
    tasks=[x for x in allsteps if x.get('task')]; assigned={i for ids in c['assignment'].values() for i in ids}
    changes=[{'task':i,'from':ev.previous[i],'to':v} for v,ids in c['assignment'].items() for i in ids if i in ev.previous and ev.previous[i]!=v]
    p=dict(strategy=strategy,base_revision=ev.s['revision'],at=ev.s['now'],routes=routes,
        unassigned=[dict(id=i,reason='在本次搜索预算与复合资产/资源/路网/设施约束内未找到插入；需人工或外援处理') for i in sorted(ev.eligible-assigned)],
        deferred=sorted(ev.pending-ev.eligible),frozen=sorted(ev.reserved),changes=changes,assignment=c['assignment'],
        objective=list(c['objective']),risk=c['risk'],trace=trace,solver=extra or {},version=2,
        metrics=dict(scheduled=len(tasks),unassigned=len(ev.eligible-assigned),deferred=len(ev.pending-ev.eligible),
            late_tasks=sum(x['late']>0 for x in tasks),late_minutes=round(sum(x['late'] for x in tasks),2),
            deadhead_km=round(sum(x['km'] for x in allsteps),2),service_km=round(sum(x['service_km'] for x in allsteps),2),
            changes=len(changes),vehicles_used=sum(bool(seq) for seq in routes.values()),runtime_ms=round((time.perf_counter()-started)*1000,1)),
        explanation='H-ALNS / 三层词典序 / 五情景CVaR / 独立安全盾。合成预测与代理成本不代表企业实测收益。')
    p['shield']=inspect(ev.s,p)
    p['decision_evidence']=list(ev.decision_evidence.values())
    p['evidence_scope']='求解期间实际尝试的插入/筛选记录。原因只适用于当时路线与插入位置；可行未选不代表更差，也不证明全局不可行。未记录的组合不能推断为已评估。'+('记录达到12000组合上限，已截断。' if ev.evidence_truncated else '')
    return p


def solve_v2(s,mode='halns',overrides=None):
    if mode not in ('halns','game','reroute','fixed','nearest','adaptive'):raise ValueError('未知V2算法')
    upgrade(s);assign_crews(s);ev=Evaluator(s);cfg={**settings(s),**(overrides or {})};rng=random.Random(cfg['seed']);start=time.perf_counter();deadline=start+cfg['budget']
    a={v:[] for v in ev.vs}
    # Warm start the unfrozen suffix and discard incompatible work only.
    for v,seq in (s.get('plan') or {}).get('routes',{}).items():
        if v not in a:continue
        for x in seq:
            tid=x.get('task')
            if tid in ev.eligible and compatible(s,ev.vs[v],ev.tasks[tid]):a[v].append(tid)
    if candidate(ev,a) is None:a={v:[] for v in ev.vs}
    missing=ev.eligible-{i for ids in a.values() for i in ids}
    # Initialization shares total wall-clock budget. Preserve best feasible partial plan.
    if mode in ('fixed','nearest'):
        a={v:[] for v in ev.vs}
        order=sorted(ev.eligible,key=(lambda i:i) if mode=='fixed' else (lambda i:(-ev.tasks[i]['priority'],ev.tasks[i]['deadline'])))
        for tid in order:
            if time.perf_counter()>deadline:break
            cs=[]
            for vid in ev.vs:
                if not compatible(s,ev.vs[vid],ev.tasks[tid]):continue
                b=copy.deepcopy(a);b[vid].append(tid);trial=candidate(ev,b)
                if trial:
                    step=next(x for x in trial['routes'][vid] if x.get('task')==tid)
                    cs.append(((len(a[vid]),vid) if mode=='fixed' else (step['arrive']-step['depart'],vid),trial))
            if cs:a=min(cs,key=lambda x:x[0])[1]['assignment']
    elif mode!='reroute':a=repair(ev,a,missing,rng,'greedy' if mode=='adaptive' else 'regret2',deadline)
    current=candidate(ev,a)
    if current is None:
        empty={'assignment':a,'routes':{v:[] for v in ev.vs},'objective':(1e12,1e12,1e12),'risk':{'cvar':0,'expected_late':0,'scenarios':[]}}
        return package(ev,empty,mode,start,[],{'status':'NO_FEASIBLE_RETURN'})
    best=current;trace=[{'iteration':0,'objective':list(best['objective']),'operator':'initial'}];exact=[]
    if mode in ('fixed','nearest','adaptive'):return package(ev,current,mode,start,trace,{'baseline':True})
    names=['random','worst','related','cluster','route','facility'];weights={n:1. for n in names};repairs={'greedy':1.,'regret2':1.,'regret3':1.}
    if mode=='game':
        examined=0;accepted=0;exhausted=False
        while time.perf_counter()<deadline:
            improved=False
            for op,b in local_moves(ev,current['assignment'],rng):
                if time.perf_counter()>deadline:break
                proposal=candidate(ev,b);examined+=1
                if proposal and proposal['objective']<current['objective']:
                    p=package(ev,proposal,mode,start,[])
                    if not p['shield']['passed']:continue
                    current=proposal;accepted+=1;improved=True;trace.append({'iteration':accepted,'operator':op,'objective':list(current['objective'])});break
            if not improved:exhausted=time.perf_counter()<deadline;break
        return package(ev,current,mode,start,trace,{'examined':examined,'accepted':accepted,'neighborhood_exhausted':exhausted,
            'equilibrium_claim':False,'potential':'共享词典序目标的负值；严格改进，有限候选状态无循环；预算停止不声称纳什均衡'})
    if mode=='reroute':return package(ev,current,mode,start,trace,{'status':'same_order_replay'})
    for iteration in range(1,cfg['iterations']+1):
        if time.perf_counter()>=deadline:break
        op=rng.choices(names,[weights[n] for n in names])[0];rp=rng.choices(list(repairs),list(repairs.values()))[0]
        b,removed=destroy(ev,current['assignment'],op,rng);removed+=list(ev.eligible-{i for ids in current['assignment'].values() for i in ids})
        b=repair(ev,b,removed,rng,rp,deadline);trial=candidate(ev,b);reward=.1
        if trial:
            if trial['objective']<best['objective']:best=trial;reward=8
            firstdiff=next((k for k in range(3) if trial['objective'][k]!=current['objective'][k]),2)
            temperature=max(.01,1-iteration/max(1,cfg['iterations']))*10
            # Service/risk never worsened by temperature; diversify only at equal F1,F2.
            accept=trial['objective']<=current['objective'] or (firstdiff==2 and rng.random()<math.exp(-min(700,max(0,trial['objective'][2]-current['objective'][2])/temperature)))
            if accept:current=trial;reward=max(reward,2)
        weights[op]=.8*weights[op]+.2*reward;repairs[rp]=.8*repairs[rp]+.2*reward
        if iteration%4==0 and time.perf_counter()<deadline:
            for name,b in itertools.islice(local_moves(ev,best['assignment'],rng),8):
                if time.perf_counter()>deadline:break
                trial=candidate(ev,b)
                if trial and trial['objective']<best['objective']:best=trial;current=trial
        if cfg['exact_every'] and iteration%cfg['exact_every']==0 and time.perf_counter()<deadline:
            best,report=exact_repair(ev,best,min(deadline,time.perf_counter()+2));exact.append(report)
        trace.append({'iteration':iteration,'operator':op,'repair':rp,'objective':list(best['objective'])})
    # Final shield filters all routes, regardless of source algorithm.
    return package(ev,best,mode,start,trace,{'weights':weights,'repair_weights':repairs,'exact':exact,'seed':cfg['seed'],
        'budget_seconds':cfg['budget'],'elapsed_seconds':round(time.perf_counter()-start,3),'iterations':len(trace)-1})
