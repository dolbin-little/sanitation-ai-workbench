import math,time,json,random
from pathlib import Path
from .world import World,SCENARIOS,GOAL,bicycle,footprint_on_road,body_clearance,clip
from .perception import Lidar,Tracker,observation
from .planning import astar,local_plan,pursuit,safety_shield,clearance
from .learning import features,infer,load_model
from .edge import schedule

POLICIES={'reactive':'固定路径＋反应式制动','shielded':'环卫规划＋独立安全监控','no_shield':'消融：关闭独立安全监控','bc_guarded':'行为克隆基线＋安全监控','adapter':'外部轨迹记录＋安全监控'}

class Session:
    DT=.2
    def __init__(self,scenario='pedestrian',seed=1000,policy='shielded',mission=None):
        if policy not in POLICIES:raise ValueError('未知驾驶策略')
        self.world=World(scenario,int(seed));self.seed=int(seed);self.policy=policy;self.ego=dict(self.world.ego_start)
        self.sensor=Lidar(self.seed,96);self.tracker=Tracker();self.path=astar((self.ego['x'],self.ego['y']),GOAL,[])
        self.command={'steer':0.,'accel':0.,'target_speed':0.};self.shield={'active':False,'reasons':[]};self.local={};self.obs=None;self.scan=None
        self.frame=0;self.dwell=0.;self.done=False;self.emergency=False;self.manual=False;self.manual_command={'steer':0.,'accel':-3.};self.adapter=None;self.model=load_model();self.swept_cells=set()
        self.mission=mission or {'id':'SIM-CLEAN-001','name':'服务道路清扫与靠站收运','source':'synthetic','kind':'sweeping' if scenario=='sweeping' else 'collection'}
        self.logs=[];self.trace=[];self.collisions=set();self.last_shield=False;self.interventions=0;self.distance=0.;self.offroad_steps=0;self.red_violations=0;self.crossed_red=False;self.cpu_ms=[];self.jerks=[];self.last_accel=0.;self.min_true_clearance=100.;self.observed_total=0;self.detected_total=0;self.feature_rows=[]
        self.edge=schedule(0);self.scan=self.sensor.observe(self.world,self.ego);self.obs=observation(self.scan,self.tracker.update(self.scan,0),0)
        self.obs['task_speed_limit']=1.8 if self.world.scenario=='sweeping' else 3.4
        self.plan_reason='等待开始环卫驾驶仿真';self.log('环卫工单已载入；所有车辆、传感器和控制均为仿真')
    def log(self,text):self.logs.insert(0,{'at':round(self.world.time,2),'text':text});self.logs=self.logs[:60]
    def mission_complete(self):return self.dwell>=3. and (self.world.scenario!='sweeping' or len(self.swept_cells)/35>=.9)
    def import_adapter(self,data):
        if not isinstance(data,dict) or not isinstance(data.get('model_id'),str) or not data.get('source_url'):raise ValueError('须填写模型标识与来源URL')
        points=data.get('waypoints')
        if not isinstance(points,list) or not 2<=len(points)<=500:raise ValueError('轨迹记录须为2—500个点')
        clean=[]
        for p in points:
            if not isinstance(p,list) or len(p)!=2 or not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and -10<=x<=110 for x in p):raise ValueError('轨迹坐标无效')
            clean.append([float(p[0]),float(p[1])])
        self.adapter={'model_id':data['model_id'][:100],'source_url':data['source_url'][:500],'license':str(data.get('license','未提供'))[:100],'waypoints':clean,'inference_executed':False}
        self.policy='adapter';self.log('已导入外部轨迹记录；不代表本机运行了该模型权重')
    def step(self,count=1,collect=False):
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=100:raise ValueError('步数须为1—100的整数')
        for _ in range(count):
            if self.done:break
            begin=time.perf_counter();self.frame+=1
            self.scan=self.sensor.observe(self.world,self.ego);tracks=self.tracker.update(self.scan,self.world.time);self.obs=observation(self.scan,tracks,self.world.time)
            self.obs['task_speed_limit']=1.8 if self.world.scenario=='sweeping' else 3.4
            # The planner receives only map, own CAN/localisation and virtual sensor observations.
            obstacles=[t for t in tracks if abs(t['vx'])+abs(t['vy'])<.8]+[{'x':m['x'],'y':m['y'],'radius':m['radius']} for m in self.obs['v2x']]
            if self.frame%5==1:
                self.path=astar((self.ego['x'],self.ego['y']),GOAL,obstacles)
            teacher=local_plan(self.ego,self.path,self.obs,max_speed=1.8 if self.world.scenario=='sweeping' else 3.4)
            if collect:self.feature_rows.append({'x':features(self.ego,self.obs,self.path),'y':[teacher['steer']/.52,teacher['accel']/3.]})
            command={k:teacher[k] for k in ('steer','accel','target_speed')};self.local=teacher
            if self.policy=='reactive':
                path=[(self.ego['x'],40.),GOAL];speed=3.2 if clearance(self.ego,tracks)>4 else 0.
                command={'steer':pursuit(self.ego,path),'accel':clip(1.6*(speed-self.ego['v']),-3,1.8),'target_speed':speed}
            elif self.policy=='bc_guarded':
                if self.model:command={**infer(self.model,features(self.ego,self.obs,self.path)),'target_speed':None}
                else:command={'steer':0.,'accel':-3.,'target_speed':0.};self.plan_reason='行为克隆权重不存在，停车'
            elif self.policy=='adapter':
                if self.adapter:command={'steer':pursuit(self.ego,self.adapter['waypoints']),'accel':clip(1.6*(2.-self.ego['v']),-3,1.8),'target_speed':2.}
                else:command={'steer':0.,'accel':-3.,'target_speed':0.}
            if self.manual:command={**self.manual_command,'target_speed':None}
            if self.emergency:command={'steer':self.ego['steer'],'accel':-3.,'target_speed':0.}
            if self.policy not in ('reactive','no_shield'):
                command,self.shield=safety_shield(self.ego,command,self.obs)
            else:self.shield={'active':False,'reasons':['研究消融：独立安全监控未启用'],'clearance':clearance(self.ego,tracks)}
            remaining=math.hypot(GOAL[0]-self.ego['x'],GOAL[1]-self.ego['y'])
            if remaining<2.0:command={'steer':self.ego['steer'],'accel':-3.,'target_speed':0.}
            if self.shield['active'] and not self.last_shield:self.interventions+=1;self.log('安全监控介入：'+'、'.join(self.shield['reasons']))
            self.last_shield=self.shield['active'];self.command=command;self.plan_reason=teacher['reason']
            previous=dict(self.ego)
            # Four 50ms truth-evaluation substeps, never exposed to the controller as observations.
            for sub in range(4):
                self.world.tick(.05);self.ego=bicycle(self.ego,command['steer'],command['accel'],.05,self.world.brake_efficiency)
                hit=self.world.collide(self.ego)
                if hit:
                    self.collisions.add(hit);self.done=True;self.log('仿真接触，终止本次试验并记录失败')
                for a in self.world.objects():self.min_true_clearance=min(self.min_true_clearance,body_clearance(self.ego,a))
                if not footprint_on_road(self.ego):self.offroad_steps+=1
                if self.world.signal=='red' and self.ego['x']+3.5>58 and not self.crossed_red:self.red_violations+=1;self.crossed_red=True
                if hit:break
            self.distance+=math.hypot(self.ego['x']-previous['x'],self.ego['y']-previous['y']);self.jerks.append(abs(self.ego['accel']-self.last_accel)/self.DT);self.last_accel=self.ego['accel']
            if self.world.scenario=='sweeping' and 20<=self.ego['x']<90 and abs(self.ego['y']-40)<2.5 and .2<self.ego['v']<=2.2:
                self.swept_cells.add(int((self.ego['x']-20)/2))
            if self.scan['at']>=self.world.time-.3:
                visible=self.scan['_visible_ids'];self.observed_total+=len(visible)
                objects={a['id']:a for a in self.world.objects()}
                self.detected_total+=sum(any(math.hypot(t['x']-objects[i]['x'],t['y']-objects[i]['y'])<3 for t in tracks) for i in visible if i in objects)
            if remaining<2.2 and self.ego['v']<.15:self.dwell+=self.DT
            else:self.dwell=0.
            if self.dwell>=3.:
                self.done=True;self.log('环卫模拟工单完成' if self.mission_complete() else '已到点驻留，但清扫覆盖未达90%，工单未完成')
            if self.world.time>=110:self.done=True;self.log('达到110秒试验上限，未完成工单按失败/等待记录')
            self.edge=schedule(self.world.time,self.world.network_bad)
            self.cpu_ms.append((time.perf_counter()-begin)*1000)
            self.trace.append({'t':round(self.world.time,2),**{k:round(v,5) for k,v in self.ego.items()},'shield':self.shield['active'],'sensor_age':round(self.obs['age'],2),'collisions':len(self.collisions),'mission_complete':self.mission_complete()})
        return self.snapshot()
    def metrics(self):
        times=sorted(self.cpu_ms);p95=times[min(len(times)-1,int(.95*len(times)))] if times else 0.
        return {'scenario':self.world.scenario,'seed':self.seed,'policy':self.policy,'completed':self.mission_complete(),'arrival_complete':self.dwell>=3.,'sim_time_s':round(self.world.time,3),'distance_m':round(self.distance,3),'collision_objects':len(self.collisions),'offroad_substeps':self.offroad_steps,'red_light_violations':self.red_violations,'safety_interventions':self.interventions,'step_cpu_p95_ms':round(p95,3),'mean_abs_jerk_mps3':round(sum(self.jerks)/len(self.jerks),3) if self.jerks else 0.,'minimum_true_clearance_m':round(self.min_true_clearance,3) if self.min_true_clearance<100 else None,'ray_hit_neighbor_association_rate':round(self.detected_total/self.observed_total,4) if self.observed_total else None,'visible_object_count':self.observed_total,'trajectory_steps':self.frame,'sweeping_coverage':round(len(self.swept_cells)/35,4) if self.world.scenario=='sweeping' else None}
    def snapshot(self):
        return {'version':'1.0.0-aic-sanitation-sim','scenario':self.world.scenario,'scenario_name':SCENARIOS[self.world.scenario][0],'description':SCENARIOS[self.world.scenario][1],'seed':self.seed,'policy':self.policy,'policy_name':POLICIES[self.policy],'world':self.world.snapshot(),'ego':self.ego,'sensor':{k:v for k,v in (self.scan or {}).items() if k!='_visible_ids'},'perception':self.obs,'route':self.path,'local_plan':self.local,'command':self.command,'safety':self.shield,'edge':self.edge,'mission':self.mission,'mission_dwell_s':round(self.dwell,2),'done':self.done,'emergency':self.emergency,'manual':self.manual,'metrics':self.metrics(),'logs':self.logs,'trace':self.trace[-220:],'model':{'bc_available':self.model is not None,'foundation_inference_executed':False,'adapter':self.adapter,'scope':'低维观测＋导航/作业限速特征行为克隆；非图像端到端或预训练自动驾驶基础模型'},'scope':'独立二维环卫服务道路闭环仿真；不代表实车部署或汽车功能安全认证'}
