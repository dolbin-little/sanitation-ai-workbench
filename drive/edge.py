"""Reduced queue/allocation/configuration subproblems, inspired by cited mentor work.
This is not the full patent implementation or a two-layer Nash-game reproduction.
Network, arrival and CPU assumptions are synthetic; control stays onboard.
"""
import math

def priority_wait(arrivals,services,priorities):
    """Nonpreemptive M/G/1 with deterministic-service second moments, stable case only."""
    rho=sum(a*s for a,s in zip(arrivals,services));w0=.5*sum(a*s*s for a,s in zip(arrivals,services))
    if rho>=.95:return [None]*len(services)
    waits=[]
    for p in priorities:
        high=sum(a*s for a,s,q in zip(arrivals,services,priorities) if q<p)
        same=sum(a*s for a,s,q in zip(arrivals,services,priorities) if q==p)
        waits.append(w0/((1-high)*(1-high-same)))
    return waits

def sqrt_allocation(coefficients,budget):
    if not coefficients or budget<=0 or any(c<=0 for c in coefficients):raise ValueError('资源分配参数无效')
    weights=[math.sqrt(c) for c in coefficients];total=sum(weights)
    return [budget*w/total for w in weights]

def choose_profile(profiles,budget_ms,prefer_quality=True):
    feasible=[p for p in profiles if p['latency_ms']<=budget_ms]
    if not feasible:return None
    return max(feasible,key=lambda p:p['rays']) if prefer_quality else min(feasible,key=lambda p:p['latency_ms'])

def schedule(time,network_bad=False,budget_ms=50.,edge_ghz=8.):
    jobs=[{'name':'制动与转向控制','critical':True,'priority':0,'placement':'onboard','deadline_ms':200.,'note':'关键控制禁止卸载'},
          {'name':'独立安全监控','critical':True,'priority':0,'placement':'onboard','deadline_ms':200.,'note':'不依赖边缘网络'},
          {'name':'清扫感知批次复核','critical':False,'priority':1,'cycles_g':.08,'bits_mb':.2,'deadline_ms':250.,'arrival_hz':2.,'weight':3.},
          {'name':'下一片区路线重排','critical':False,'priority':2,'cycles_g':.12,'bits_mb':.1,'deadline_ms':450.,'arrival_hz':1.,'weight':2.},
          {'name':'环卫工单与遥测归档','critical':False,'priority':3,'cycles_g':.03,'bits_mb':.06,'deadline_ms':800.,'arrival_hz':1.,'weight':1.}]
    optional=jobs[2:];allocation=sqrt_allocation([j['weight']*j['cycles_g'] for j in optional],edge_ghz)
    service=[j['cycles_g']/f for j,f in zip(optional,allocation)];wait=priority_wait([j['arrival_hz'] for j in optional],service,[j['priority'] for j in optional])
    rtt=1.2 if network_bad else .02;rate=.5 if network_bad else 50.
    for j,f,s,w in zip(optional,allocation,service,wait):
        predicted=None if w is None else (rtt+j['bits_mb']/rate+s+w)*1000
        okay=predicted is not None and predicted<=j['deadline_ms'] and not network_bad
        j.update(cpu_ghz=f,predicted_latency_ms=predicted,placement='edge' if okay else 'defer_local_archive',queue_wait_ms=None if w is None else w*1000,note='通过设定时限门控' if okay else '链路或时限不满足，延后可选工作')
    # Candidate costs are declared settings until the measured profile script replaces them.
    profiles=[{'name':'稀疏扫描','rays':48,'latency_ms':8.},{'name':'标准扫描','rays':96,'latency_ms':18.},{'name':'密集扫描','rays':144,'latency_ms':35.}]
    return {'jobs':jobs,'edge_cpu_budget_ghz':edge_ghz,'allocated_ghz':sum(allocation),'network_bad':network_bad,'network_model':'合成RTT/带宽/到达率；非实测网络','profile':choose_profile(profiles,budget_ms),'profiles':profiles,'profile_cost_scope':'配置成本为设定值，不是识别准确率或硬件测试值','method':'优先级队列 + 简化KKT平方根分配 + 时限配置筛选'}
