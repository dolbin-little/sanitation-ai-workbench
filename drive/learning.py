"""Small behavior-cloning baseline. Not a pretrained driving foundation model."""
import json,math
from pathlib import Path
from .world import clip,wrap
from .planning import pursuit
ROOT=Path(__file__).resolve().parents[1]

def features(ego,obs,path):
    ranges=obs['ranges'];n=len(ranges)
    # Raw scan sectors plus measured ego and navigation geometry; no obstacle truth.
    sectors=[min(ranges[int(i*n/8):int((i+1)*n/8)] or [24.])/24. for i in range(8)]
    turn=pursuit(ego,path)/.52
    return sectors+[ego['v']/4.,math.sin(ego['yaw']),math.cos(ego['yaw']),turn,clip((92.-ego['x'])/90.,-1,1),clip((40.-ego['y'])/20.,-1,1),float(obs['signal']=='red'),clip((obs['stopline']-ego['x'])/25.,-1,1),min(obs['age'],2.)/2.,obs.get('task_speed_limit',3.4)/3.4]

def infer(model,x):
    x=[(v-m)/max(s,1e-6) for v,m,s in zip(x,model['mean'],model['scale'])]
    for i,layer in enumerate(model['layers']):
        x=[sum(a*b for a,b in zip(row,x))+bias for row,bias in zip(layer['weights'],layer['bias'])]
        if i<len(model['layers'])-1:x=[math.tanh(v) for v in x]
    return {'steer':clip(x[0]*.52,-.52,.52),'accel':clip(x[1]*3.,-3.,1.8)}

def load_model():
    p=ROOT/'data/bc_model.json'
    return json.loads(p.read_text('utf-8')) if p.exists() else None

def train(rows,epochs=250,seed=42):
    import sys
    sys.path.insert(0,str(ROOT/'legacy/.vendor'))
    import numpy as np
    rng=np.random.default_rng(seed);x=np.array([r['x'] for r in rows],dtype=float);y=np.array([r['y'] for r in rows],dtype=float)
    mean=x.mean(0);scale=x.std(0);scale[scale<.05]=1.;x=(x-mean)/scale
    shapes=[(x.shape[1],32),(32,16),(16,2)];weights=[rng.normal(0,1/math.sqrt(a),(a,b)) for a,b in shapes];bias=[np.zeros(b) for _,b in shapes]
    mw=[np.zeros_like(w) for w in weights];vw=[np.zeros_like(w) for w in weights];mb=[np.zeros_like(b) for b in bias];vb=[np.zeros_like(b) for b in bias];t=0
    for epoch in range(epochs):
        for batch in np.array_split(rng.permutation(len(x)),max(1,len(x)//256)):
            a=[x[batch]]
            for i in range(3):
                z=a[-1]@weights[i]+bias[i];a.append(np.tanh(z) if i<2 else z)
            grad=2*(a[-1]-y[batch])/len(batch);dw=[None]*3;db=[None]*3
            for i in range(2,-1,-1):
                dw[i]=a[i].T@grad;db[i]=grad.sum(0)
                if i:grad=(grad@weights[i].T)*(1-a[i]**2)
            t+=1
            for i in range(3):
                mw[i]=.9*mw[i]+.1*dw[i];vw[i]=.999*vw[i]+.001*dw[i]**2;mb[i]=.9*mb[i]+.1*db[i];vb[i]=.999*vb[i]+.001*db[i]**2
                weights[i]-=.003*(mw[i]/(1-.9**t))/(np.sqrt(vw[i]/(1-.999**t))+1e-8)
                bias[i]-=.003*(mb[i]/(1-.9**t))/(np.sqrt(vb[i]/(1-.999**t))+1e-8)
    out={'kind':'low_dimensional_sanitation_behavior_cloning','feature_count':x.shape[1],'mean':mean.tolist(),'scale':scale.tolist(),'layers':[{'weights':w.T.tolist(),'bias':b.tolist()} for w,b in zip(weights,bias)],'training_seed':seed,'epochs':epochs,'source':'synthetic teacher rollouts; no public driving training dataset','foundation_model':False}
    return out
