"""Hysteresis trigger, L0-L4 control, checked fallback and incident handover."""
import copy
import time
from .model import upgrade, settings
from .optimizer import solve_v2
from .shield import inspect


def risk_signal(s,event=None):
    pending=[t for t in s['tasks'] if t['status']=='pending']
    late=max([min(1,max(0,(s['now']+15-t['deadline'])/30)) for t in pending] or [0])
    pending_ids={t['id'] for t in pending}
    forecast={k:v for k,v in s.get('forecast',{}).get('tasks',{}).items() if k in pending_ids}
    over=max([min(1,max(0,(s['now']+30-x['deadline'])/30)) for x in forecast.values()] or [0])
    resource=max([max(v['load']/v['capacity'],1-v['water']/v['water_capacity'] if v['water_capacity'] else 0) for v in s['vehicles'] if v['enabled']] or [0])
    c=s.get('congestion');traffic=min(1,(c['factor']-1)/2) if c and s['now']<c['until'] else 0
    fault=1 if event in ('failure','road_closed','facility_closed') else 0
    return dict(late=late,overflow=over,resource=resource,fault=fault,traffic=traffic)


def trigger(s,event=None,force=False):
    upgrade(s);c=s['controller'];cfg=settings(s);components=risk_signal(s,event);risk=max(components.values())
    hard=event in ('failure','road_closed','facility_closed','overflow')
    if risk<=cfg['theta_off']:c['latched']=False
    periodic=s['now']>=c.get('next_roll',s['now']+1)
    new_task=event in ('overflow','complaint')
    fired=force or hard or new_task or periodic or (risk>=cfg['theta_on'] and not c['latched'] and s['now']-c['last_trigger']>=cfg['cooldown'])
    if not fired:level='L0'
    elif event in ('road_closed','congestion'):level='L1'
    elif event in ('failure','overflow','complaint','recovery'):level='L2'
    else:level='L3'
    c.update(level=level,risk=round(risk,3),components=components,event=event,reason='硬事件/新任务/滚动到期/风险阈值' if fired else '低风险或滞回冷却：保持计划')
    if fired:c.update(latched=True,last_trigger=s['now'],next_roll=s['now']+min(15,cfg['horizon']))
    c['trace'].insert(0,{'at':s['now'],'level':level,'risk':round(risk,3),'event':event,'fired':fired});c['trace']=c['trace'][:100]
    return level


def safe_plan(s,mode='halns'):
    upgrade(s);started=time.perf_counter();error=None
    try:
        p=solve_v2(s,mode,{'budget':.5 if mode=='reroute' else 2 if mode=='game' else settings(s)['budget']})
        if p['shield']['passed']:
            if p['unassigned']:
                s['controller']['level']='L4';s['controller']['reason']='预算内仍有未分配任务，需外援/延期决策'
            return p
        error='; '.join(p['shield']['errors'][:4])
    except (ValueError,RuntimeError,ImportError,KeyError) as exc:error=str(exc)
    # Old plan is not intrinsically safe after an event: re-check against current state.
    old=copy.deepcopy(s.get('plan'))
    if old:
        old['shield']=inspect(s,old)
        if old['shield']['passed']:
            old['base_revision']=s['revision'];old['at']=s['now'];old['fallback']={'reason':error,'elapsed':time.perf_counter()-started}
            return old
    s['controller'].update(level='L4',reason='无通过安全盾的可回退计划：'+str(error))
    s['needs_replan']=True
    return None


def respond(s,event=None,force=False):
    level=trigger(s,event,force)
    if level=='L0':return
    mode={'L1':'reroute','L2':'game','L3':'halns'}.get(level,'halns')
    p=safe_plan(s,mode)
    # If local handling cannot restore coverage, escalate to rolling optimization.
    if (p is None or p.get('unassigned')) and level in ('L1','L2'):
        s['controller']['level']='L3';p=safe_plan(s,'halns')
    s['draft']=p
    if p:s['controller']['last_solver']=p['strategy']
    # Candidates always require dispatcher acceptance; auto-control never dispatches directly.
