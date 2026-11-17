"""Native public benchmark track. No municipal units or constraints are substituted.

This is a benchmark-specific ALNS implementation, not the complete municipal
forecast/control pipeline. Original data and independently replayable routes are
retained. Signed arc IDs encode which direction is actually serviced.
"""
import bisect
import hashlib
import heapq
import math
from pathlib import Path
import random
import re
import time
from functools import lru_cache


def header(text):
    return dict(re.findall(r'^\s*(\w+)\s*:\s*([^\n]+)', text, re.M))


def read_instance(path):
    path = Path(path)
    text = path.read_text(encoding='latin1')
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.suffix.lower() == '.txt':
        rows = [list(map(float, line.split())) for line in text.splitlines()
                if re.fullmatch(r'\s*\d+(?:\s+\d+(?:\.\d+)?){6}\s*', line)]
        fleet = re.search(r'NUMBER\s+CAPACITY\s+(\d+)\s+(\d+)', text)
        assert len(rows) == 101 and [r[0] for r in rows] == list(range(101))
        coords = [(r[1], r[2]) for r in rows]
        dist = [[math.dist(a, b) for b in coords] for a in coords]
        return dict(name=path.stem, family='Solomon', kind='vrptw', sha256=sha,
                    capacity=float(fleet[2]), vehicles=int(fleet[1]), depot=0,
                    n=100, jobs=[None]+[dict(u=i,v=i,demand=r[3],ready=r[4],due=r[5],service=r[6])
                                          for i,r in enumerate(rows[1:],1)],
                    dist=dist, horizon=rows[0][5], raw=str(path))
    h = header(text)
    if path.suffix == '.tdsp':
        n, vertices = int(h['EDG_REQ']), int(h['VERTICES'])
        body = text.split('[REQUIRED_EDGES]')[1].split('[NETWORK_DATA]')
        lines = [x.split() for x in body[0].splitlines() if x.strip()]
        def profile(tokens):
            nums=list(map(float,tokens)); assert len(nums)%3 == 0
            triples=list(zip(nums[::3],nums[1::3],nums[2::3]))
            assert all(a[0] <= b[0]+1e-8 for a,b in zip(triples,triples[1:]))
            return ([x[0] for x in triples], triples)
        jobs=[None]; service={}
        for i in range(n):
            a,b=lines[2*i:2*i+2];u,v=int(a[0]),int(a[1])
            assert (int(b[0]),int(b[1]))==(v,u)
            jobs.append(dict(u=u,v=v,demand=float(a[3]),cost=float(a[2])))
            service[i+1]=profile(a[5:]);service[-i-1]=profile(b[5:])
        travel={}
        for line in body[1].splitlines():
            a=line.split()
            if a:
                u,v,k=map(int,a[:3]); travel[u,v]=profile(a[3:]) if k else None
        assert len(travel)==vertices*vertices
        return dict(name=path.stem,family='TDCARP-'+path.parent.name,kind='tdcarp',sha256=sha,
                    capacity=float(h['CAPACITY']),vehicles=int(h['VEHICLES']),depot=int(h['DEPOT']),
                    n=n,jobs=jobs,travel=travel,service=service,horizon=float(h['ENDTIME']),raw=str(path))
    vertices=int(h['VERTICES']); req=int(h['ARISTAS_REQ']); edges=[]
    for line in text.splitlines():
        m=re.search(r'\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*coste\s+(\d+)(?:\s+demanda\s+(\d+))?',line,re.I)
        if m: edges.append(tuple(map(int,(m[1],m[2],m[3],m[4] or '0'))))
    assert len(edges)==req+int(h['ARISTAS_NOREQ'])
    dist=[[math.inf]*(vertices+1) for _ in range(vertices+1)]
    for i in range(vertices+1):dist[i][i]=0.
    for u,v,c,d in edges:dist[u][v]=dist[v][u]=min(dist[u][v],c)
    for k in range(1,vertices+1):
        for i in range(1,vertices+1):
            dik=dist[i][k]
            for j in range(1,vertices+1):
                dist[i][j]=min(dist[i][j],dik+dist[k][j])
    return dict(name=path.stem,family=path.parents[1].name,kind='carp',sha256=sha,
                capacity=float(h['CAPACIDAD']),vehicles=int(h['VEHICULOS']),depot=int(h['DEPOSITO']),
                n=req,jobs=[None]+[dict(u=u,v=v,cost=c,demand=d) for u,v,c,d in edges[:req]],
                dist=dist,edges=edges,horizon=math.inf,raw=str(path))


def arrival(profile,t):
    if profile is None:return t
    xs, pieces=profile
    k=min(bisect.bisect_right(xs,t),len(xs)-1)
    x,y,slope=pieces[k]
    return y+t-x if t>xs[-1] else y+(t-x)*slope


@lru_cache(maxsize=4)
def raw_td_network(path):
    raw=Path(str(path).replace('TDCARP-withSP','TDCARP-withoutSP')).with_suffix('.dat')
    text=raw.read_text();h=header(text);adj={};edges={}
    for line in text.split('[NETWORK_DATA]')[1].splitlines():
        parts=line.split('[')
        if len(parts)<3:continue
        u,v,length,demand,k=map(float,parts[0].split())
        breaks=list(map(float,parts[1].split(']')[0].split()))
        speeds=list(map(float,parts[2].split(']')[0].split()))
        edge=(int(v),length,breaks,speeds)
        adj.setdefault(int(u),[]).append(edge);edges[int(u),int(v)]=edge
    return adj,edges,float(h['SERVICE_SPEED_FACTOR'])


def integrate_speed(edge,t,factor=1.):
    _,remaining,breaks,speeds=edge;k=bisect.bisect_right(breaks,t)
    while k<len(breaks):
        length=(breaks[k]-t)*speeds[k]*factor
        if remaining<=length+1e-10:return t+remaining/(speeds[k]*factor)
        remaining-=length;t=breaks[k];k+=1
    return t+remaining/(speeds[-1]*factor)


def td_shortest(adj,u,v,t):
    ds={u:t};heap=[(t,u)]
    while heap:
        clock,x=heapq.heappop(heap)
        if clock!=ds[x]:continue
        if x==v:return clock
        for edge in adj[x]:
            end=integrate_speed(edge,clock);y=edge[0]
            if end<ds.get(y,math.inf):ds[y]=end;heapq.heappush(heap,(end,y))
    return math.inf


class NativeEvaluator:
    def __init__(self, p):
        self.p=p
        self.route=lru_cache(maxsize=40000)(self._route)

    def _route(self,seq):
        p=self.p;jobs=p['jobs']; depot=p['depot']
        if sum(jobs[i]['demand'] for i in seq)>p['capacity']+1e-7:return None
        if p['kind']=='vrptw':
            t=0.;cost=0.;prev=depot
            for i in seq:
                d=p['dist'][prev][i];cost+=d;t=max(t+d,jobs[i]['ready'])
                if t>jobs[i]['due']+1e-7:return None
                t+=jobs[i]['service'];prev=i
            cost+=p['dist'][prev][depot];t+=p['dist'][prev][depot]
            return (cost,tuple(seq)) if t<=p['horizon']+1e-7 else None
        # Two-state dynamic program selects optimal edge orientation for this order.
        states=[(0.,depot,())]
        for i in seq:
            j=jobs[i];new=[]
            for sign,u,v in ((i,j['u'],j['v']),(-i,j['v'],j['u'])):
                candidates=[]
                for t,prev,path in states:
                    if p['kind']=='carp':end=t+p['dist'][prev][u]+j['cost']
                    else:end=arrival(p['service'][sign],arrival(p['travel'][prev,u],t))
                    candidates.append((end,v,path+(sign,)))
                new.append(min(candidates))
            states=new
        best=min((t+p['dist'][prev][depot] if p['kind']=='carp' else arrival(p['travel'][prev,depot],t),path)
                 for t,prev,path in states)
        return best if best[0]<=p['horizon']+1e-7 else None

    def objective(self,routes):
        rs=[r for r in routes if r]; covered=sum(map(len,rs)); cost=sum(self.route(tuple(r))[0] for r in rs)
        return (self.p['n']-covered,len(rs),cost) if self.p['kind']=='vrptw' else (self.p['n']-covered,cost)


def solve(p,method,seed,budget=1.,iterations=100):
    start=time.perf_counter(); cpu_start=time.process_time();deadline=cpu_start+budget;rng=random.Random(seed);ev=NativeEvaluator(p)
    jobs=p['jobs'];alljobs=list(range(1,p['n']+1));evaluations=0
    def options(routes,i):
        choices=[]
        for k,r in enumerate(routes):
            old=ev.route(tuple(r))[0]
            for pos in range(len(r)+1):
                route=r[:pos]+[i]+r[pos:];result=ev.route(tuple(route))
                if result:choices.append((0,result[0]-old,k,pos))
        if len(routes)<p['vehicles']:
            result=ev.route((i,))
            if result:choices.append((1 if p['kind']=='vrptw' else 0,result[0],len(routes),0))
        return sorted(choices)
    def repair(routes,pool,regret=False,interrupt=False):
        pool=list(pool)
        while pool:
            if interrupt and time.process_time()>deadline:break
            batch=pool[:3] if regret else pool[:1];choices=[]
            for i in batch:
                opts=options(routes,i)
                if opts:
                    a=opts[0];b=opts[min(1,len(opts)-1)]
                    urgency=(b[0]-a[0])*1000000+b[1]-a[1] if len(opts)>1 else 1e9
                    choices.append((-urgency if regret else 0,a,i))
            if not choices:
                pool.remove(batch[0]);continue
            _,(_,_,k,pos),i=min(choices)
            if k==len(routes):routes.append([])
            routes[k].insert(pos,i);pool.remove(i)
        return [r for r in routes if r]
    # Common deterministic seed solution, construction is timed and never silently truncated.
    order=sorted(alljobs,key=lambda i:(jobs[i].get('due',math.inf),-jobs[i]['demand'],i))
    if method=='nearest':
        routes=[];pending=set(order)
        while pending and len(routes)<p['vehicles']:
            r=[]
            while pending:
                opts=[]
                for i in pending:
                    c=ev.route(tuple(r+[i]))
                    if c:opts.append((c[0],i))
                if not opts:break
                _,i=min(opts);r.append(i);pending.remove(i)
            if not r:break
            routes.append(r)
    else:routes=repair([],order)
    best=[r[:] for r in routes];bestobj=ev.objective(best);current=bestobj
    weights=[1.]*4;counts=[0]*4;accepted=0;trace=[]
    if method in ('static_alns','adaptive_alns'):
        for it in range(iterations):
            if time.process_time()>=deadline:break
            op=rng.choices(range(4),weights=weights if method=='adaptive_alns' else None)[0];counts[op]+=1
            assigned=[i for r in routes for i in r];q=min(len(assigned),max(2,int(p['n']*rng.uniform(.05,.18))))
            if not assigned:break
            if op==0:removed=set(rng.sample(assigned,q))
            elif op==1:removed=set(rng.choice(routes))
            elif op==2:
                removed=set(sorted(assigned,key=lambda i:-jobs[i]['demand'])[:q])
            else:
                pivot=rng.choice(assigned);removed=set(sorted(assigned,key=lambda i:abs(i-pivot))[:q])
            partial=[[i for i in r if i not in removed] for r in routes];partial=[r for r in partial if r]
            # Author-supplied TDSP pair functions can violate time-dependent
            # triangle consistency. Removing a service can therefore make the
            # shortened route infeasible. Reject that destroy move, keep incumbent.
            if any(ev.route(tuple(r)) is None for r in partial):continue
            pool=list(removed | (set(alljobs)-set(assigned)));rng.shuffle(pool)
            cand=repair(partial,pool,method=='adaptive_alns' and it%2==0,True);obj=ev.objective(cand)
            reward=1.
            if obj<bestobj:
                best,bestobj=[r[:] for r in cand],obj;reward=8.;trace.append((it,obj))
            temperature=max(.001,bestobj[-1]*.02*(1-it/max(1,iterations)))
            if obj<=current or (obj[:-1]==current[:-1] and rng.random()<math.exp(min(0,(current[-1]-obj[-1])/temperature))):
                routes,current=cand,obj;accepted+=1;reward=max(3.,reward)
            weights[op]=.8*weights[op]+.2*reward;evaluations+=1
    signed=[list(ev.route(tuple(r))[1]) for r in best]
    return dict(routes=signed,objective=bestobj,runtime_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu_start,
                iterations=evaluations,operator_counts=counts,operator_weights=weights,accepted=accepted,
                improvement_trace=trace,cache=ev.route.cache_info()._asdict(),
                unassigned=sorted(set(alljobs)-{abs(i) for r in signed for i in r}))


def verify(p,solution):
    """Independent forward replay; no route evaluator/objective called here."""
    errors=[];seen=[];cost=0.;routes=solution['routes'];jobs=p['jobs']
    if len(routes)>p['vehicles']:errors.append('fleet')
    # Recompute static CARP paths from adjacency with Dijkstra, not Floyd-Warshall.
    adjacency={};cache={}
    for u,v,c,d in p.get('edges',[]):
        adjacency.setdefault(u,[]).append((v,c));adjacency.setdefault(v,[]).append((u,c))
    if p['kind']=='tdcarp':tdadj,tdedges,factor=raw_td_network(p['raw'])
    def distance(u,v):
        if p['kind']=='vrptw':return p['dist'][u][v]
        if u not in cache:
            ds={u:0.};heap=[(0.,u)]
            while heap:
                t,x=heapq.heappop(heap)
                if t!=ds[x]:continue
                for y,c in adjacency[x]:
                    if t+c<ds.get(y,math.inf):ds[y]=t+c;heapq.heappush(heap,(t+c,y))
            cache[u]=ds
        return cache[u][v]
    for rid,r in enumerate(routes):
        t=0.;load=0.;prev=p['depot'];routecost=0.
        for signed in r:
            i=abs(signed)
            if not 1<=i<=p['n']:errors.append('unknown');continue
            seen.append(i);j=jobs[i];load+=j['demand'];u,v=(j['u'],j['v']) if signed>0 else (j['v'],j['u'])
            if p['kind']=='vrptw':
                d=distance(prev,u);routecost+=d;t=max(t+d,j['ready'])
                if t>j['due']+1e-6:errors.append(f'window:{rid}:{i}')
                t+=j['service']
            elif p['kind']=='carp':t+=distance(prev,u)+j['cost']
            else:t=integrate_speed(tdedges[u,v],td_shortest(tdadj,prev,u,t),factor)
            prev=v
        if load>p['capacity']+1e-6:errors.append(f'capacity:{rid}')
        if p['kind']=='tdcarp':t=td_shortest(tdadj,prev,p['depot'],t)
        else:
            d=distance(prev,p['depot']);t+=d;routecost+=d
        if t>p['horizon']+1e-6:errors.append(f'horizon:{rid}')
        cost+=routecost if p['kind']=='vrptw' else t
    missing=sorted(set(range(1,p['n']+1))-set(seen))
    if len(seen)!=len(set(seen)):errors.append('duplicate_service')
    if missing!=solution['unassigned']:errors.append('missing_accounting')
    if abs(cost-solution['objective'][-1])>max(1e-5,p['n']*2e-6):errors.append('cost_mismatch')
    return dict(feasible=not errors and not missing,valid_partial=not errors,errors=errors,
                unassigned=missing,vehicles=len(routes),cost=cost,covered=len(set(seen)))
