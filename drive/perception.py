"""Synthetic LiDAR -> adjacent clustering -> alpha-beta tracking. No actor IDs fed to policy."""
import math,random
from .world import wrap

class Lidar:
    def __init__(self,seed=0,rays=96):self.rng=random.Random(seed);self.rays=rays;self.last=None
    def observe(self,world,ego):
        if world.sensor_fault and self.last:return self.last
        objects=world.objects();points=[];ranges=[];visible=set()
        for i in range(self.rays):
            angle=ego['yaw']-math.pi+2*math.pi*i/self.rays;ux,uy=math.cos(angle),math.sin(angle);hit=24.;oid=None
            noise=self.rng.gauss(0,.015)
            for a in objects:
                dx,dy=a['x']-ego['x'],a['y']-ego['y'];along=dx*ux+dy*uy;disc=a['radius']**2-(dx*dx+dy*dy-along*along)
                if disc>=0 and (along>=0 or dx*dx+dy*dy<=a['radius']**2):
                    dist=max(0.,along-math.sqrt(disc))
                    if 0<=dist<hit:hit=dist;oid=a['id']
            noisy=max(0.,min(24.,hit+noise)) if oid is not None else 24.
            ranges.append(noisy)
            if oid is not None:
                points.append({'ray':i,'x':ego['x']+noisy*ux,'y':ego['y']+noisy*uy,'range':noisy})
                visible.add(oid)
        # Truth visibility belongs only to the evaluator and is removed from policy observation.
        self.last={'at':world.time,'pose':dict(ego),'points':points,'ranges':ranges,'rays':self.rays,'range_max':24.,'signal':world.signal,'stopline':58.,'v2x':world.notices(),'_visible_ids':sorted(visible)}
        return self.last

def clusters(scan):
    groups=[]
    for p in scan['points']:
        if groups and p['ray']-groups[-1][-1]['ray']<=1 and math.hypot(p['x']-groups[-1][-1]['x'],p['y']-groups[-1][-1]['y'])<2.2:groups[-1].append(p)
        else:groups.append([p])
    detections=[]
    for g in groups:
        mx=sum(p['x'] for p in g)/len(g);my=sum(p['y'] for p in g)/len(g)
        width=max((math.hypot(p['x']-q['x'],p['y']-q['y']) for p in g for q in g),default=0.)
        radius=max(.5,min(1.65,width*.65+.4))
        pose=scan['pose'];dx,dy=mx-pose['x'],my-pose['y'];d=max(.001,math.hypot(dx,dy))
        detections.append({'x':mx+dx/d*radius*.65,'y':my+dy/d*radius*.65,'radius':radius,'kind':'small_object' if width<1.1 else 'vehicle_or_barrier','confidence':min(.98,.35+.15*len(g)),'points':len(g)})
    return detections

class Tracker:
    def __init__(self):self.tracks=[];self.serial=0;self.last_at=-1.;self.frame_detections=[]
    def update(self,scan,now):
        if scan['at']==self.last_at:return [dict(t) for t in self.tracks]
        dt=max(.1,scan['at']-self.last_at) if self.last_at>=0 else .2;self.last_at=scan['at'];det=clusters(scan);self.frame_detections=det;used=set()
        for t in self.tracks:
            px,py=t['x']+t['vx']*dt,t['y']+t['vy']*dt
            options=[(math.hypot(d['x']-px,d['y']-py),j,d) for j,d in enumerate(det) if j not in used]
            if options and min(options,key=lambda z:z[0])[0]<3.2:
                _,j,d=min(options,key=lambda z:z[0]);used.add(j);ex,ey=d['x']-px,d['y']-py
                t.update(x=px+.75*ex,y=py+.75*ey,vx=max(-3,min(3,t['vx']+.18*ex/dt)),vy=max(-3,min(3,t['vy']+.18*ey/dt)),radius=d['radius'],confidence=d['confidence'],kind=d['kind'],misses=0,at=scan['at'])
            else:t.update(x=px,y=py,misses=t['misses']+1)
        self.tracks=[t for t in self.tracks if t['misses']<=3]
        for j,d in enumerate(det):
            if j not in used:self.serial+=1;self.tracks.append({**d,'id':'T'+str(self.serial),'vx':0.,'vy':0.,'misses':0,'at':scan['at']})
        return [dict(t) for t in self.tracks]

def observation(scan,tracks,now):
    return {'at':scan['at'],'age':max(0.,now-scan['at']),'pose':scan['pose'],'tracks':tracks,'signal':scan['signal'],'stopline':scan['stopline'],'v2x':[m for m in scan['v2x'] if m.get('authenticated') and now-m['at']<1.], 'ranges':scan['ranges']}
