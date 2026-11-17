"""A* service-road path, bicycle velocity/steering rollout, Pure Pursuit/P speed control."""
import math,heapq
from .world import on_road,footprint_on_road,body_clearance,bicycle,clip,wrap,GOAL

def astar(start,goal,obstacles):
    grid=2.;s=(round(start[0]/grid),round(start[1]/grid));g=(round(goal[0]/grid),round(goal[1]/grid))
    def free(n):
        x,y=n[0]*grid,n[1]*grid
        return on_road(x,y,1.6) and all(math.hypot(x-o['x'],y-o['y'])>o['radius']+2.2 for o in obstacles)
    if not free(g):return []
    queue=[(0.,s)];cost={s:0.};parent={};visited=set()
    while queue and len(visited)<2400:
        _,n=heapq.heappop(queue)
        if n in visited:continue
        visited.add(n)
        if n==g:
            route=[g]
            while route[-1]!=s:route.append(parent[route[-1]])
            route=[(a*grid,b*grid) for a,b in route[::-1]]
            return route
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
            m=(n[0]+dx,n[1]+dy)
            if not free(m):continue
            if dx and dy and (not free((n[0]+dx,n[1])) or not free((n[0],n[1]+dy))):continue
            v=cost[n]+math.hypot(dx,dy)
            if v<cost.get(m,1e9):cost[m]=v;parent[m]=n;heapq.heappush(queue,(v+math.hypot(m[0]-g[0],m[1]-g[1]),m))
    return []

def pursuit(ego,path,lookahead=None):
    if not path:return 0.
    near=min(range(len(path)),key=lambda i:math.hypot(path[i][0]-ego['x'],path[i][1]-ego['y']))
    target=path[-1];distance=lookahead or max(4.,ego['v']*1.3)
    for p in path[near:]:
        if math.hypot(p[0]-ego['x'],p[1]-ego['y'])>=distance:target=p;break
    dx,dy=target[0]-ego['x'],target[1]-ego['y'];ld=max(.5,math.hypot(dx,dy));alpha=wrap(math.atan2(dy,dx)-ego['yaw'])
    return clip(math.atan2(2*2.8*math.sin(alpha),ld),-.52,.52)

def clearance(ego,tracks,t=0.):
    return min((body_clearance(ego,o,t) for o in tracks),default=50.)

def local_plan(ego,path,obs,dt=.2,max_speed=3.4):
    base=pursuit(ego,path);remaining=math.hypot(GOAL[0]-ego['x'],GOAL[1]-ego['y']);desired=min(max_speed,remaining*.6)
    if abs(base)>.22:desired=min(desired,2.)
    if obs['signal']=='red' and ego['x']<obs['stopline']:
        desired=min(desired,math.sqrt(2*1.8*max(0,obs['stopline']-ego['x']-4.6)))
    # Yield to small crossing objects rather than deliberately weaving around people.
    for o in obs['tracks']:
        dx,dy=o['x']-ego['x'],o['y']-ego['y']
        if o['kind']=='small_object' and abs(o['vy'])>.35 and 0<dx<18 and 24<o['y']<45:
            desired=0.
    candidates=[];best=None
    start_index=min(range(len(path)),key=lambda j:math.hypot(path[j][0]-ego['x'],path[j][1]-ego['y'])) if path else 0
    if not path:return {'steer':0.,'accel':-3.,'target_speed':0.,'path':[],'candidates':[],'reason':'服务道路暂不可达，停车等待'}
    for offset in [-.28,-.14,0.,.14,.28]:
        delta=clip(base+offset,-.52,.52)
        for factor in [1.,.55,0.]:
            speed=desired*factor;accel=clip(1.8*(speed-ego['v']),-3.,1.8);q=dict(ego);trajectory=[];minimum=50.;safe=True
            for k in range(12):
                q=bicycle(q,delta,accel,.2);trajectory.append([q['x'],q['y']]);minimum=min(minimum,clearance(q,obs['tracks'],(k+1)*.2))
                if minimum<.35 or not footprint_on_road(q):safe=False;break
            finish_index=min(range(len(path)),key=lambda j:math.hypot(path[j][0]-q['x'],path[j][1]-q['y']))
            nearest=math.hypot(path[finish_index][0]-q['x'],path[finish_index][1]-q['y'])
            progress=(finish_index-start_index)*2.
            score=progress*2.-nearest*2.5-abs(offset)*1.8+min(minimum,4)*.15+speed*.08
            candidate={'steer':delta,'accel':accel,'target_speed':speed,'path':trajectory,'safe':safe,'score':round(score,4)};candidates.append(candidate)
            if safe and (best is None or score>best['score']):best=candidate
    if best is None:best={'steer':base,'accel':-3.,'target_speed':0.,'path':[],'reason':'预测轨迹受阻，减速等待'}
    return {**best,'candidates':candidates,'reason':best.get('reason','沿环卫工单服务道路行驶')}

def safety_shield(ego,command,obs):
    reasons=[];steer=command['steer'];accel=command['accel'];closest=clearance(ego,obs['tracks']);stop=ego['v']*.4+ego['v']**2/(2*2.)+1.
    if obs['age']>.6:reasons.append('感知陈旧超过0.6秒')
    if obs['signal']=='red' and 0<obs['stopline']-ego['x']-3.5<stop+1.:reasons.append('红灯停车线保护')
    # Independent forward verification of the actual proposed command.
    q=dict(ego);min_future=50.
    for k in range(10):
        q=bicycle(q,steer,accel,.2)
        min_future=min(min_future,clearance(q,obs['tracks'],(k+1)*.2))
        if min_future<.2:reasons.append('拟执行轨迹与观测目标间距不足');break
        if not footprint_on_road(q):reasons.append('拟执行轨迹越出服务道路');break
    if reasons:return {'steer':steer,'accel':-3.,'target_speed':0.}, {'active':True,'reasons':reasons,'stopping_distance':stop,'clearance':closest,'minimum_predicted_clearance':min_future}
    return command,{'active':False,'reasons':[],'stopping_distance':stop,'clearance':closest,'minimum_predicted_clearance':min_future}
