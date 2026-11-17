"""Ground-truth world. Only sensors and evaluation may inspect its actors."""
from dataclasses import dataclass, asdict
import math, random

SCENARIOS = {
    'collection': ('定点收运靠站', '沿服务道路到达收集点，停车完成3秒模拟收运。'),
    'sweeping': ('连续道路清扫', '保持低速完成清扫服务路段，再靠站停车。'),
    'pedestrian': ('作业区行人横穿', '清扫车在横穿行人前减速让行。'),
    'parked': ('违停车辆绕行', '感知占道车辆，生成可行绕行轨迹。'),
    'closure': ('服务道路临时封闭', '接收封路事件，沿替代服务道路到达工单点。'),
    'signal': ('路口红灯等待', '遵守虚拟红灯并在放行后继续作业。'),
    'sensor_stale': ('传感器陈旧故障', '感知时间戳过期后进入最小风险停车。'),
    'network_loss': ('边缘链路退化', '合成RTT增大、带宽降低时保持车端避障和制动。'),
    'brake_fault': ('制动效率突降', '注入未提前告知控制器的制动衰减，记录失败与恢复。'),
}
ROADS = [(0., 30., 100., 50.), (20., 10., 80., 28.), (20., 18., 38., 44.), (62., 18., 80., 44.)]
GOAL = (92., 40.)

def clip(x,lo,hi):return max(lo,min(hi,x))
def wrap(a):return (a+math.pi)%(2*math.pi)-math.pi
def on_road(x,y,pad=0.):
    return any(a+pad<=x<=c-pad and b+pad<=y<=d-pad for a,b,c,d in ROADS)

def body_point(ego,u,v):
    return ego['x']+u*math.cos(ego['yaw'])-v*math.sin(ego['yaw']),ego['y']+u*math.sin(ego['yaw'])+v*math.cos(ego['yaw'])

def footprint_on_road(ego):
    # Rear-axle reference; 2.8m wheelbase, 0.7m front/rear overhang, 1.8m width.
    return all(on_road(*body_point(ego,u,v)) for u in [-.7,.35,1.4,2.45,3.5] for v in [-.9,0.,.9])

def body_clearance(ego,obj,t=0.):
    cx,cy=body_point(ego,1.4,0.);dx=obj['x']+obj.get('vx',0)*t-cx;dy=obj['y']+obj.get('vy',0)*t-cy
    co,si=math.cos(ego['yaw']),math.sin(ego['yaw']);u=dx*co+dy*si;v=-dx*si+dy*co
    return math.hypot(max(abs(u)-2.1,0.),max(abs(v)-.9,0.))-obj['radius']

@dataclass
class Actor:
    id:str;x:float;y:float;radius:float;kind:str='vehicle';vx:float=0.;vy:float=0.;start:float=0.
    def snapshot(self,t):
        age=max(0.,t-self.start)
        return {**asdict(self),'x':self.x+self.vx*age,'y':self.y+self.vy*age}

class World:
    def __init__(self,scenario='pedestrian',seed=1000):
        if scenario not in SCENARIOS:raise ValueError('未知环卫驾驶场景')
        self.scenario=scenario;self.seed=seed;self.rng=random.Random(seed);self.time=0.;self.events=[]
        self.actors=[];self.sensor_fault=False;self.network_bad=False;self.brake_efficiency=1.;self.signal='green'
        jitter=self.rng.uniform(-1.2,1.2)
        self.ego_start={'x':8+self.rng.uniform(-.6,.6),'y':40+self.rng.uniform(-.3,.3),'yaw':self.rng.uniform(-.015,.015),'v':0.,'steer':0.,'accel':0.}
        self.release=16+self.rng.uniform(0,4);self.fault_start=5+self.rng.uniform(0,1);self.loss_start=4+self.rng.uniform(0,2)
        if scenario in ('pedestrian','brake_fault'):
            self.actors=[Actor('P1',47+jitter,24,.55,'pedestrian',0,1.25,4.)]
        if scenario=='parked':self.actors=[Actor('C1',43+jitter,40,1.5)]
        if scenario=='closure':
            self.actors=[Actor('B'+str(i),54,31+i*2.5,1.35,'barrier') for i in range(8)]
        if scenario=='signal':self.signal='red'
        if scenario=='sweeping':self.actors=[Actor('BIN',70,47,.6,'bin')]
        if scenario in ('sensor_stale','network_loss'):self.actors=[Actor('C1',46+jitter,40,1.4)]
        self.injected=set()
    def tick(self,dt):
        self.time=round(self.time+dt,8)
        if self.scenario=='signal' and self.time>=self.release:self.signal='green'
        if self.scenario=='sensor_stale' and self.fault_start<=self.time<self.fault_start+5:self.sensor_fault=True
        else:self.sensor_fault=False
        self.network_bad=self.scenario=='network_loss' and self.loss_start<=self.time<self.loss_start+20
        self.brake_efficiency=.35 if self.scenario=='brake_fault' and self.time>=8 else 1.
    def objects(self):return [a.snapshot(self.time) for a in self.actors if self.time>=a.start and -5<=a.snapshot(self.time)['y']<=75]
    def notices(self):
        # A road service message is a distinct observation channel, not obstacle truth.
        return [{'kind':'closure','x':54.,'y':40.,'radius':11.,'at':self.time,'authenticated':True}] if self.scenario=='closure' else []
    def collide(self,ego):
        for a in self.objects():
            if body_clearance(ego,a)<=0:return a['id']
        return None
    def snapshot(self):return {'roads':ROADS,'actors':self.objects(),'goal':GOAL,'signal':self.signal,'stopline':58.,'scenario':self.scenario,'time':self.time}

def bicycle(ego,steer,accel,dt,brake_efficiency=1.):
    # Use the identical actuator integration in prediction and physical execution.
    if dt>.05000001:
        q=dict(ego);remaining=dt
        while remaining>1e-9:
            step=min(.05,remaining);q=bicycle(q,steer,accel,step,brake_efficiency);remaining-=step
        return q
    v=ego['v'];a=clip(accel,-3.,1.8)
    if a<0:a*=brake_efficiency
    nv=clip(v+a*dt,0.,5.)
    # Trapezoidal translation reduces discretisation-dependent stop distances.
    active=min(dt,v/-a) if a<0 and v>0 else dt
    distance=max(0.,v*active+.5*a*active*active) if a<0 else (v+nv)*.5*dt
    delta=clip(clip(steer,-.52,.52),ego.get('steer',0.)-.8*dt,ego.get('steer',0.)+.8*dt)
    increment=distance/2.8*math.tan(delta);yaw=wrap(ego['yaw']+increment)
    mid=ego['yaw']+increment*.5
    return {'x':ego['x']+distance*math.cos(mid),'y':ego['y']+distance*math.sin(mid),'yaw':yaw,'v':nv,'steer':delta,'accel':a}
