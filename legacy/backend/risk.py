"""Finite equally weighted scenario replay; fractional tail CVaR."""
import math


def cvar(losses,alpha=.9):
    if not losses or not 0<=alpha<1: raise ValueError('CVaR需要非空损失及0<=alpha<1')
    tail=(1-alpha)*len(losses); left=tail; result=0
    for loss in sorted(losses,reverse=True):
        mass=min(1,left);result+=mass*loss;left-=mass
        if left<=1e-10:break
    return result/tail


def scenarios(s):
    f=s.get('forecast',{}).get('global',{})
    # Common ranks induce correlated stress across traffic, consumption and facilities.
    q=f.get('travel_factor',[.9,1,1.25]);w=f.get('water_factor',[.9,1,1.2]);queue=f.get('queue',[0,3,8])
    def interp(a,p):return a[0]+(a[1]-a[0])*p*2 if p<=.5 else a[1]+(a[2]-a[1])*(p-.5)*2
    return [dict(traffic=interp(q,p),water=interp(w,p),queue=interp(queue,p),p=.2) for p in (.05,.25,.5,.75,.95)]


def assess(s,routes,tasks,config):
    losses=[];lates=[]; details=[]
    for scenario in scenarios(s):
        loss=late_total=0
        for v in s['vehicles']:
            if v['id'] not in routes:continue
            active=v.get('active');now=active['finish'] if active else s['now'];water=active['water_after'] if active else v['water']
            for a in routes[v['id']]:
                travel=(a['arrive']-a['depart'])*scenario['traffic']
                now=max(now+travel,a['begin']); duration=a['finish']-a['begin']
                if a['kind']=='facility':
                    f=next((f for f in s['facilities'] if f['node']==a['start']),{})
                    now+=max(0,scenario['queue']-f.get('queue',0));
                    if 'water' in f.get('resets',['load','water','energy']):water=v['water_capacity']
                    loss+=scenario['queue']*.2
                now+=duration
                if a.get('task'):
                    t=tasks[a['task']]; late=max(0,now-a['deadline'])*t['priority'];late_total+=late;loss+=late
                    water-=t['water']*scenario['water']; loss+=max(0,-water)*20
                    pred=s.get('forecast',{}).get('tasks',{}).get(t['id'])
                    if pred and t.get('bin_capacity'):
                        fill=t.get('fill',t['demand'])+pred['fill_rate'][2]*max(0,now-s['now'])
                        loss+=max(0,fill-t['bin_capacity'])*100
            loss+=max(0,now-v['shift_end'])*5
        losses.append(loss);lates.append(late_total);details.append({'loss':round(loss,3),**scenario})
    return {'cvar':cvar(losses,config['alpha']),'expected_late':sum(lates)/len(lates),'scenarios':details,
            'assumption':'五个等概率共同分位压力情景；并非真实联合概率分布'}
